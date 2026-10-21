"""
Plan evaluation and gating utilities for BD Legal Guide AI.
"""

from datetime import datetime, timezone
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.models import Subscription, Plan, User


def get_user_plan(db: Session, user: User) -> str:
    """
    Returns the user's active plan code (e.g. 'user_pro', 'user_free').
    Returns 'user_free' if user is unauthenticated or has no active/valid subscription.
    """
    if not user:
        return "user_free"

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    subscription = (
        db.query(Subscription)
        .join(Plan, Subscription.plan_id == Plan.id)
        .filter(
            Subscription.user_id == user.id,
            Subscription.status == "active",
            or_(
                Subscription.expires_at.is_(None),
                Subscription.expires_at > now_utc,
            ),
        )
        .order_by(Subscription.started_at.desc())
        .first()
    )

    if subscription and subscription.plan:
        return subscription.plan.code or "user_free"

    return "user_free"
