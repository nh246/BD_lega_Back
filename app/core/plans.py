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
        "duration_days": 30,
        "description": "Essential legal AI guidance and lawyer search for everyday citizens.",
        "is_popular": False,
        "sort_order": 1,
        "is_active": True,
        "features": [
            "15 AI messages per month",
            "3 saved chat sessions",
            "3-turn conversation memory",
            "Browse & book verified lawyers",
            "Standard support",
        ],
    },
    {
        "code": "user_pro_monthly",
        "name": "Pro Monthly",
        "price_monthly": 299.0,
        "duration_days": 30,
        "description": "Deep legal intelligence with 20-turn memory, document & image analysis and priority access.",
        "is_popular": True,
        "sort_order": 2,
        "is_active": True,
        "features": [
            "Unlimited AI messages & sessions",
            "20-turn conversation memory",
            "Document & Image analysis (Vision)",
            "Direct messaging with any lawyer",
            "Priority booking queue",
            "AI Confidence Scores",
        ],
    },
    {
        "code": "user_pro_6m",
        "name": "Pro 6 Months",
        "price_monthly": 1499.0,
        "duration_days": 180,
        "description": "Pro features for 6 months with savings. Deep legal intelligence with priority lawyer access.",
        "is_popular": False,
        "sort_order": 3,
        "is_active": True,
        "features": [
            "All Pro Monthly features for 6 months",
            "Save 16% compared to monthly",
            "Unlimited AI messages & sessions",
            "20-turn conversation memory",
            "Document & Image analysis (Vision)",
            "Direct messaging with any lawyer",
            "Priority booking queue",
        ],
    },
    {
        "code": "user_pro_1y",
        "name": "Pro 1 Year",
        "price_monthly": 2499.0,
        "duration_days": 365,
        "description": "Full annual access with maximum 30% savings. Complete AI legal intelligence and lawyer directory.",
        "is_popular": False,
        "sort_order": 4,
        "is_active": True,
        "features": [
            "All Pro features for 1 full year",
            "Save 30% compared to monthly",
            "Unlimited AI messages & sessions",
            "20-turn conversation memory",
            "Document & Image analysis (Vision)",
            "Direct messaging with any lawyer",
            "Priority booking queue",
        ],
    },
    {
        "code": "lawyer_basic",
        "name": "Lawyer Basic",
        "price_monthly": 0.0,
        "duration_days": 3650,
        "description": "Standard directory presence and direct consultation inquiries from citizens.",
        "is_popular": False,
        "sort_order": 1,
        "is_active": True,
        "features": [
            "Directory Listing in Bangladesh Lawyer Registry",
            "Receive Client Consultation Inquiries",
            "Manual Schedule Management",
            "Standard Profile Page",
        ],
    },
    {
        "code": "lawyer_verified",
        "name": "Lawyer Verified Badge",
        "price_monthly": 999.0,
        "duration_days": 30,
        "description": "Official Bar Council verification, top ranking, and integrated client consultation suite.",
        "is_popular": True,
        "sort_order": 2,
        "is_active": True,
        "features": [
            "Official Bar Council Verified Gold Badge",
            "Top Placement in Lawyer Search Directory",
            "Instant Video Consultation Link Generation",
            "Direct Client Messaging Channel",
            "Priority Payouts and Platform Support",
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
    Ensures standard baseline plans exist in the database with description, features,
    is_popular, and sort_order populated.
    """
    for p_data in PLAN_DEFINITIONS:
        plan = db.query(Plan).filter(Plan.code == p_data["code"]).first()
        if not plan:
            plan = Plan(
                code=p_data["code"],
                name=p_data["name"],
                price_monthly=p_data["price_monthly"],
                duration_days=p_data["duration_days"],
                description=p_data.get("description"),
                features=p_data.get("features") or [],
                is_popular=p_data.get("is_popular", False),
                sort_order=p_data.get("sort_order", 0),
                is_active=p_data.get("is_active", True),
            )
            db.add(plan)
        else:
            if getattr(plan, "is_active", None) is None:
                plan.is_active = True
            if not plan.description and p_data.get("description"):
                plan.description = p_data["description"]
            if (not plan.features or len(plan.features) == 0) and p_data.get("features"):
                plan.features = p_data["features"]
            if getattr(plan, "is_popular", None) is None:
                plan.is_popular = p_data.get("is_popular", False)
            if getattr(plan, "sort_order", None) is None or plan.sort_order == 0:
                plan.sort_order = p_data.get("sort_order", 0)

    # Legacy cleanup: deactivate 'user_pro' so it doesn't duplicate 'user_pro_monthly' in the public grid
    legacy_pro = db.query(Plan).filter(Plan.code == "user_pro").first()
    if legacy_pro and legacy_pro.is_active:
        legacy_pro.is_active = False
        legacy_pro.sort_order = 99
        if not legacy_pro.description:
            legacy_pro.description = "Legacy Pro Plan (Subscriptions active)."

    db.commit()
