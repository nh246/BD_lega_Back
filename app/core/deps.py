"""
FastAPI dependencies for authentication, role verification, and scope validation.
"""

from typing import Callable, List, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_optional_current_user(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Returns current user if a valid bearer token is provided, or None if unauthenticated.
    """
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        email: str = payload.get("sub") or payload.get("email")
        if not email:
            return None
        user = db.query(User).filter(User.email == email).first()
        if user and user.status != "blocked":
            return user
        return None
    except Exception:
        return None


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Decodes the JWT bearer token and verifies the user exists and is active.
    Raises 401 if invalid or not found.
    Raises 403 if user.status == 'blocked'.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        email: str = payload.get("sub") or payload.get("email")
        if not email:
            raise credentials_exception
    except Exception:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise credentials_exception

    if user.status == "blocked":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account blocked",
        )

    return user


def check_account_restriction(user: Optional[User]):
    """
    Checks if user account is restricted.
    Returns 403 JSONResponse with 'account_restricted' if restricted, else None.
    """
    if user and getattr(user, "status", None) == "restricted":
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": "account_restricted",
                "message": "Your account is restricted. Contact support.",
                "detail": "Your account is restricted. Contact support.",
            },
        )
    return None



def require_role(*allowed_roles: str) -> Callable:
    """
    Returns a dependency verifying current_user.role is within allowed_roles.
    Raises 403 if insufficient permissions.
    """
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return role_checker


def require_scope(scope: str) -> Callable:
    """
    Returns a dependency verifying that the user has the required permission scope.
    Admins automatically possess all scopes.
    Moderators must have the specific scope in their user.scopes list.
    Raises 403 if missing required scope or invalid role.
    """
    def scope_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role == "admin":
            return current_user

        if current_user.role == "moderator":
            user_scopes = current_user.scopes or []
            if isinstance(user_scopes, list) and scope in user_scopes:
                return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required scope",
        )

    return scope_checker
