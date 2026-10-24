"""
Plan evaluation and gating utilities for BD Legal Guide AI.
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models import Subscription, Plan, User

PRO_PLAN_CODES = {"user_pro", "user_pro_monthly", "user_pro_6m", "user_pro_1y"}

PLAN_DEFINITIONS = [
    {
        "code": "user_free",
        "name": "Free Plan",
        "price_monthly": 0.0,
        "duration_days": None,
        "features": [
            "15 AI messages per month",
            "3-turn chat memory",
            "Browse Lawyer Directory",
            "Book Consultations",
            "Basic Session History",
        ],
    },
    {
        "code": "user_pro_monthly",
        "name": "Pro Monthly",
        "price_monthly": 299.0,
        "duration_days": 30,
        "features": [
            "Unlimited AI queries",
            "20-turn chat memory",
            "Direct messaging with verified lawyers",
            "Priority consultation booking",
            "Document analysis",
        ],
    },
    {
        "code": "user_pro_6m",
        "name": "Pro 6 Months",
        "price_monthly": 1499.0,
        "duration_days": 180,
        "features": [
            "All Pro features for 6 months",
            "Unlimited AI queries",
            "20-turn chat memory",
            "Direct messaging with verified lawyers",
            "Priority consultation booking",
        ],
    },
    {
        "code": "user_pro_1y",
        "name": "Pro 1 Year",
        "price_monthly": 2499.0,
        "duration_days": 365,
        "features": [
            "All Pro features for 1 full year",
            "Unlimited AI queries",
            "20-turn chat memory",
            "Direct messaging with verified lawyers",
            "Priority consultation booking",
            "Maximum value",
        ],
    },
]


def is_pro_plan(plan_code: Optional[str]) -> bool:
    if not plan_code:
        return False
    return plan_code in PRO_PLAN_CODES or (plan_code.startswith("user_pro") and plan_code != "user_free")


def get_user_plan(db: Session, user: Optional[User]) -> str:
    """
    Returns the user's active plan code (e.g. 'user_pro_monthly', 'user_free').
    Returns 'user_free' if user is unauthenticated or has no active/valid subscription.
    Checks if subscription's expires_at is greater than datetime.now(timezone.utc).
    If expired, treats as 'user_free'.
    """
    if not user:
        return "user_free"

    now_utc = datetime.now(timezone.utc)

    subscriptions = (
        db.query(Subscription)
        .join(Plan, Subscription.plan_id == Plan.id)
        .filter(
            Subscription.user_id == user.id,
            Subscription.status == "active",
        )
        .order_by(Subscription.started_at.desc())
        .all()
    )

    for sub in subscriptions:
        if sub.expires_at is not None:
            exp = sub.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp <= now_utc:
                # Expired subscription
                continue
        if sub.plan and sub.plan.code:
            return sub.plan.code

    return "user_free"


def ensure_plans_exist(db: Session):
    """
    Ensures all standard plans exist in the database with their expected attributes.
    """
    for p_data in PLAN_DEFINITIONS:
        plan = db.query(Plan).filter(Plan.code == p_data["code"]).first()
        if not plan:
            plan = Plan(
                code=p_data["code"],
                name=p_data["name"],
                price_monthly=p_data["price_monthly"],
                duration_days=p_data["duration_days"],
                features=p_data["features"],
            )
            db.add(plan)
        else:
            plan.name = p_data["name"]
            plan.price_monthly = p_data["price_monthly"]
            if hasattr(plan, "duration_days"):
                plan.duration_days = p_data["duration_days"]
            plan.features = p_data["features"]
    db.commit()

