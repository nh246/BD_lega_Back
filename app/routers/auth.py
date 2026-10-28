"""
Authentication router: Registration, Login, Token generation, and Current User endpoints.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_password_reset_token,
    decode_password_reset_token,
)
from app.models import User, LawyerProfile
from app.schemas import (
    UserCreate,
    UserLogin,
    UserResponse,
    Token,
    AuthResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from app.audit import log_audit
from app.core.plans import get_user_plan, is_pro_plan

router = APIRouter(prefix="/api/auth", tags=["Auth"])


def _make_user_response(db: Session, user: User) -> UserResponse:
    user_plan = get_user_plan(db, user)
    return UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        status=user.status,
        scopes=user.scopes or [],
        plan=user_plan,
        is_pro=is_pro_plan(user_plan),
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(
    data: UserCreate,
    db: Session = Depends(get_db),
):
    """
    Registers a new user account.
    Checks for email uniqueness, hashes password, and creates profile if role is lawyer.
    """
    normalized_email = data.email.lower().strip()

    # Check for existing user
    existing_user = db.query(User).filter(User.email == normalized_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create new User entity
    user_id = uuid.uuid4()
    hashed_password = get_password_hash(data.password)

    new_user = User(
        id=user_id,
        email=normalized_email,
        password_hash=hashed_password,
        full_name=data.full_name.strip(),
        role=data.role if data.role in ["admin", "moderator", "lawyer", "user"] else "user",
        status="active",
        scopes=None,
    )
    db.add(new_user)
    db.flush()

    # If the user registers as a lawyer, initialize a pending lawyer profile
    if new_user.role == "lawyer":
        lawyer_profile = LawyerProfile(
            id=uuid.uuid4(),
            user_id=new_user.id,
            name=new_user.full_name,
            verification_status="pending",
            verification_paid=False,
        )
        db.add(lawyer_profile)

    db.commit()
    db.refresh(new_user)

    log_audit(
        db=db,
        actor_id=new_user.id,
        action="user_registered",
        target_type="user",
        target_id=new_user.id,
        details={"role": new_user.role, "email": new_user.email},
    )

    # Generate token so the user is auto-logged-in after registration
    token_payload = {
        "sub": new_user.email,
        "id": str(new_user.id),
        "role": new_user.role,
        "scopes": new_user.scopes or [],
    }
    access_token = create_access_token(data=token_payload)

    return AuthResponse(
        access_token=access_token,
        user=_make_user_response(db, new_user),
    )


@router.post("/login", response_model=AuthResponse)
def login(
    login_data: UserLogin,
    db: Session = Depends(get_db),
):
    """
    Logs in with email and password (JSON payload).
    Returns a JWT access token.
    Raises 401 on invalid credentials.
    Raises 403 if account is blocked.
    """
    normalized_email = login_data.email.lower().strip()
    user = db.query(User).filter(User.email == normalized_email).first()

    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status == "blocked":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account blocked",
        )

    # Note: If user.status == "restricted", login succeeds, but specific restricted actions
    # are gated downstream.

    token_payload = {
        "sub": user.email,
        "id": str(user.id),
        "role": user.role,
        "scopes": user.scopes or [],
    }
    access_token = create_access_token(data=token_payload)

    log_audit(
        db=db,
        actor_id=user.id,
        action="user_logged_in",
        target_type="user",
        target_id=user.id,
    )

    return AuthResponse(
        access_token=access_token,
        user=_make_user_response(db, user),
    )


@router.post("/token", response_model=Token, include_in_schema=False)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    OAuth2 standard password flow endpoint (supporting Swagger UI authorization).
    """
    normalized_email = form_data.username.lower().strip()
    user = db.query(User).filter(User.email == normalized_email).first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status == "blocked":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account blocked",
        )

    token_payload = {
        "sub": user.email,
        "id": str(user.id),
        "role": user.role,
        "scopes": user.scopes or [],
    }
    access_token = create_access_token(data=token_payload)
    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves the authenticated user's profile.
    """
    return _make_user_response(db, current_user)


class UserUpdateMe(BaseModel):
    full_name: Optional[object] = None


@router.patch("/me")
@router.patch("/me/")
def update_me(
    payload: Optional[UserUpdateMe] = Body(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Updates the authenticated user's full_name.
    Validates that full_name stripped is between 2 and 100 characters.
    Does NOT allow changing email, role, or status.
    """
    raw_name = payload.full_name if payload else None
    if not isinstance(raw_name, str):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "invalid_name",
                "message": "Name must be between 2 and 100 characters.",
            },
        )

    cleaned_name = raw_name.strip()
    if len(cleaned_name) < 2 or len(cleaned_name) > 100:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "invalid_name",
                "message": "Name must be between 2 and 100 characters.",
            },
        )

    current_user.full_name = cleaned_name

    # If the user is a lawyer, keep their lawyer profile name in sync
    lawyer_profile = (
        db.query(LawyerProfile)
        .filter(LawyerProfile.user_id == current_user.id)
        .first()
    )
    if lawyer_profile:
        lawyer_profile.name = cleaned_name

    db.commit()
    db.refresh(current_user)

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="user_updated_profile",
        target_type="user",
        target_id=current_user.id,
        details={"full_name": current_user.full_name},
    )

    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
    }


@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Changes the authenticated user's password.
    Requires current_password to match user's existing hashed password.
    """
    if not verify_password(data.current_password, current_user.password_hash):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "current_password_incorrect",
                "message": "Current password is incorrect.",
            },
        )

    current_user.password_hash = get_password_hash(data.new_password)
    db.commit()

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="password_changed",
        target_type="user",
        target_id=current_user.id,
    )

    return {"message": "Password updated successfully"}


@router.post("/forgot-password")
def forgot_password(
    data: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Initiates password reset for a given email address.
    Generates a 30-minute JWT reset token.
    If SMTP env vars exist, sends real email; otherwise returns reset_url in demo mode.
    """
    normalized_email = data.email.lower().strip()
    user = db.query(User).filter(User.email == normalized_email).first()

    if not user:
        # Don't leak existence of the email account
        return {"message": "If that email is registered, a password reset link has been sent."}

    # Generate JWT reset token (expires in 30 minutes)
    reset_token = create_password_reset_token(user.email)
    now = datetime.now(timezone.utc)
    user.reset_token = reset_token
    user.reset_token_expires_at = now + timedelta(minutes=30)
    db.commit()

    log_audit(
        db=db,
        actor_id=user.id,
        action="password_reset_requested",
        target_type="user",
        target_id=user.id,
        details={"email": user.email},
    )

    reset_url = f"/reset-password?token={reset_token}"
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    full_reset_link = f"{frontend_url}{reset_url}"

    # Check for SMTP configuration (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, etc.)
    smtp_host = os.getenv("SMTP_HOST") or os.getenv("SMTP_SERVER")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "noreply@bdlegal.ai")

    if smtp_host and smtp_user:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart("alternative")
            msg["Subject"] = "Password Reset Request - BD Legal AI"
            msg["From"] = smtp_from
            msg["To"] = user.email

            body = (
                f"Hello {user.full_name},\n\n"
                f"A password reset was requested for your BD Legal AI account.\n"
                f"Please click the link below to set a new password:\n\n"
                f"{full_reset_link}\n\n"
                f"This link expires in 30 minutes.\n"
                f"If you did not make this request, you can safely ignore this email.\n"
            )
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                if smtp_password:
                    server.login(smtp_user, smtp_password)
                server.sendmail(smtp_from, [user.email], msg.as_string())

            return {"message": "Password reset link sent to your email."}
        except Exception:
            # Fallback to demo mode if SMTP connection fails
            return {
                "reset_url": reset_url,
                "message": "Reset link generated. In production, this would be emailed.",
            }

    # Demo mode: return reset_url directly
    return {
        "reset_url": reset_url,
        "message": "Reset link generated. In production, this would be emailed.",
    }


@router.post("/reset-password")
def reset_password(
    data: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Confirms password reset using the token.
    Validates token, updates password, and clears reset_token.
    """
    try:
        payload = decode_password_reset_token(data.token)
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "invalid_or_expired_token",
                "message": "Invalid or expired reset token.",
            },
        )

    email = payload.get("sub")
    if not email:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "invalid_or_expired_token",
                "message": "Invalid or expired reset token.",
            },
        )

    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not user.reset_token or user.reset_token != data.token:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "invalid_or_expired_token",
                "message": "Invalid or expired reset token.",
            },
        )

    # Check reset_token_expires_at if stored
    if user.reset_token_expires_at:
        exp_at = user.reset_token_expires_at
        if exp_at.tzinfo is None:
            exp_at = exp_at.replace(tzinfo=timezone.utc)
        if exp_at < datetime.now(timezone.utc):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": "invalid_or_expired_token",
                    "message": "Invalid or expired reset token.",
                },
            )

    user.password_hash = get_password_hash(data.new_password)
    user.reset_token = None
    user.reset_token_expires_at = None
    db.commit()

    log_audit(
        db=db,
        actor_id=user.id,
        action="password_reset_completed",
        target_type="user",
        target_id=user.id,
        details={"email": user.email},
    )

    return {"message": "Password reset successful. You can now log in."}


