"""
Notifications router: in-app notifications listing and read status management.
"""

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Notification, User
from app.schemas import NotificationResponse, NotificationListResponse

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])
compat_router = APIRouter(prefix="/notifications", tags=["NotificationsCompat"])


def _parse_uuid(id_str: str, entity_name: str = "Notification") -> uuid.UUID:
    """Helper to safely parse UUID strings, raising 404 on malformed values."""
    try:
        return uuid.UUID(str(id_str).strip())
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_name} not found",
        )


@router.get("", response_model=NotificationListResponse)
@compat_router.get("", response_model=NotificationListResponse)
def get_user_notifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get latest 20 notifications for the authenticated user, ordered by created_at DESC.
    Also returns unread_count (total unread notifications).
    """
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(20)
        .all()
    )

    unread_count = (
        db.query(func.count(Notification.id))
        .filter(
            Notification.user_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
        .scalar()
        or 0
    )

    return NotificationListResponse(
        notifications=[NotificationResponse.model_validate(n) for n in notifications],
        unread_count=unread_count,
    )


@router.post("/read-all")
@compat_router.post("/read-all")
def mark_all_notifications_as_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Mark all unread notifications for the authenticated user as read.
    """
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False,  # noqa: E712
    ).update({"is_read": True}, synchronize_session=False)

    db.commit()

    return {
        "message": "All notifications marked as read",
        "unread_count": 0,
    }


@router.post("/{notification_id}/read", response_model=NotificationResponse)
@compat_router.post("/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_as_read(
    notification_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Mark a single notification as read.
    """
    notif_uuid = _parse_uuid(notification_id, "Notification")
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notif_uuid,
            Notification.user_id == current_user.id,
        )
        .first()
    )
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    if not notification.is_read:
        notification.is_read = True
        db.commit()
        db.refresh(notification)

    return NotificationResponse.model_validate(notification)
