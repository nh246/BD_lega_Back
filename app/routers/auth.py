"""
Authentication router: Registration, Login, Token generation, and Current User endpoints.
"""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import get_password_hash, verify_password, create_access_token
from app.models import User, LawyerProfile
from app.schemas import UserCreate, UserLogin, UserResponse, Token
from app.audit import log_audit

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
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

    return new_user


@router.post("/login", response_model=Token)
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

    return Token(access_token=access_token, token_type="bearer")


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
):
    """
    Retrieves the authenticated user's profile.
    """
    return current_user
