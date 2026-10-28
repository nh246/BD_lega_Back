"""
Security utilities: password hashing with bcrypt and JWT handling with PyJWT.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import bcrypt
import jwt
from app.core.config import JWT_SECRET

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt-hashed password."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Generate bcrypt password hash."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token with 24h expiration."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)

    to_encode.update({
        "exp": expire,
        "iat": now,
    })
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT access token. Raises ValueError on failure."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError as e:
        raise ValueError(f"Invalid or expired token: {e}") from e


def create_password_reset_token(email: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT password reset token expiring in 30 minutes."""
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta if expires_delta else timedelta(minutes=30))
    payload = {
        "sub": email,
        "type": "password_reset",
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def decode_password_reset_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT password reset token. Raises ValueError on failure."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        if payload.get("type") != "password_reset":
            raise ValueError("Token is not a password reset token")
        return payload
    except jwt.PyJWTError as e:
        raise ValueError(f"Invalid or expired token: {e}") from e
