"""
Admin Router: User, Moderator, and Audit Log management.
"""

from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role, require_scope
from app.core.security import get_password_hash
from app.models import User, AuditLog
from app.schemas import UserUpdate, ModeratorCreate, UserResponse, AuditLogResponse
from app.audit import log_audit

router = APIRouter(prefix="/api/admin", tags=["Admin"])


def _parse_uuid(id_str: str) -> uuid.UUID:
    """Helper to safely parse UUID strings, raising 404 on malformed values."""
    try:
        return uuid.UUID(id_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )


@router.get("/users", response_model=List[UserResponse])
def get_users(
    role: Optional[str] = Query(None, description="Filter by user role"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by user status"),
    current_user: User = Depends(require_scope("users:view")),
    db: Session = Depends(get_db),
):
    """
    List all users with optional filtering by role and status.
    Requires 'users:view' scope (or admin role).
    """
    query = db.query(User)
    if role:
        query = query.filter(User.role == role.strip())
    if status_filter:
        query = query.filter(User.status == status_filter.strip())

    users = query.order_by(User.created_at.desc()).all()
    return users


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    update_data: UserUpdate,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Updates a user's details (full_name, role, or status).
    Requires 'admin' role.
    Logs an audit trail when status or role is altered.
    """
    target_uuid = _parse_uuid(user_id)
    user = db.query(User).filter(User.id == target_uuid).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    old_status = user.status
    old_role = user.role

    if update_data.full_name is not None:
        user.full_name = update_data.full_name.strip()
    if update_data.role is not None:
        user.role = update_data.role.strip()
    if update_data.status is not None:
        user.status = update_data.status.strip()

    # If status or role is modified, record an audit log
    if old_status != user.status or old_role != user.role:
        log_audit(
            db=db,
            actor_id=current_user.id,
            action="user_updated",
            target_type="user",
            target_id=str(user.id),
            details={
                "old_status": old_status,
                "new_status": user.status,
                "old_role": old_role,
                "new_role": user.role,
            },
        )

    db.commit()
    db.refresh(user)
    return user


@router.get("/moderators", response_model=List[UserResponse])
def get_moderators(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    List all moderator accounts with their scopes.
    Requires 'admin' role.
    """
    moderators = (
        db.query(User)
        .filter(User.role == "moderator")
        .order_by(User.created_at.desc())
        .all()
    )
    return moderators


@router.post("/moderators", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_moderator(
    data: ModeratorCreate,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Creates a new moderator account with specified scopes.
    Requires 'admin' role.
    """
    normalized_email = data.email.lower().strip()
    existing_user = db.query(User).filter(User.email == normalized_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    hashed_password = get_password_hash(data.password)
    new_moderator = User(
        id=uuid.uuid4(),
        email=normalized_email,
        password_hash=hashed_password,
        full_name=data.full_name.strip(),
        role="moderator",
        status="active",
        scopes=data.scopes,
    )
    db.add(new_moderator)
    db.commit()
    db.refresh(new_moderator)

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="moderator_created",
        target_type="user",
        target_id=str(new_moderator.id),
        details={
            "email": new_moderator.email,
            "scopes": new_moderator.scopes,
        },
    )

    return new_moderator


@router.delete("/moderators/{user_id}", response_model=UserResponse)
def revoke_moderator(
    user_id: str,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Revokes moderator privileges: changes user's role back to 'user' and clears scopes.
    Requires 'admin' role.
    """
    target_uuid = _parse_uuid(user_id)
    user = db.query(User).filter(User.id == target_uuid).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    old_scopes = user.scopes
    user.role = "user"
    user.scopes = None

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="moderator_revoked",
        target_type="user",
        target_id=str(user.id),
        details={"previous_scopes": old_scopes},
    )

    db.commit()
    db.refresh(user)
    return user


@router.get("/audit-logs", response_model=List[AuditLogResponse])
def get_audit_logs(
    limit: int = Query(50, ge=1, le=200, description="Number of logs to retrieve"),
    current_user: User = Depends(require_scope("audit:view")),
    db: Session = Depends(get_db),
):
    """
    Returns recent audit logs ordered by creation time descending.
    Requires 'audit:view' scope (or admin role).
    """
    logs = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return logs
