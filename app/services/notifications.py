"""
Notification service for BD Legal Guide AI.
Provides helper functions to create in-app notifications for users.
"""

import uuid
from typing import Optional, Union
from sqlalchemy.orm import Session
from app.models import Notification


def trigger_notification(
    db: Session,
    user_id: Union[uuid.UUID, str],
    type: str,
    title: str,
    message: str,
    link: Optional[str] = None,
) -> Notification:
    """
    Creates a new Notification row and commits it to the database.
    """
    if isinstance(user_id, str):
        try:
            user_uuid = uuid.UUID(user_id.strip())
        except (ValueError, TypeError):
            user_uuid = user_id
    else:
        user_uuid = user_id

    notif = Notification(
        id=uuid.uuid4(),
        user_id=user_uuid,
        type=type,
        title=title,
        message=message,
        link=link,
        is_read=False,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif
