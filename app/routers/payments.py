"""
Payments and Subscriptions router:
Public plans listing, subscription checkout, lawyer verification purchases,
and administrator transaction auditing.
"""

from datetime import datetime
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models import LawyerProfile, Payment, Plan, Subscription, User
from app.schemas import (
    CheckoutRequest,
    CheckoutResponse,
    PaymentResponse,
    PlanResponse,
    SubscriptionResponse,
)
from app.services.pay.base import create_checkout_session

router = APIRouter(prefix="/api", tags=["Payments"])


@router.get("/plans", response_model=List[PlanResponse])
def get_plans(db: Session = Depends(get_db)):
    """
    Public endpoint. Returns all subscription plans from the database.
    """
    plans = db.query(Plan).order_by(Plan.price_monthly.asc()).all()
    if not plans:
        # Fallback default plans if not yet seeded
        defaults = [
            Plan(
                code="user_free",
                name="Free Plan",
                price_monthly=0.0,
                features=["Standard Gemini AI Chat", "Browse Lawyer Directory", "Book Consultations"],
            ),
            Plan(
                code="user_pro",
                name="Pro Plan",
                price_monthly=299.0,
                features=["RAG Legal Citations", "Document Analysis", "Priority Consultations", "Unlimited AI"],
            ),
            Plan(
                code="lawyer_basic",
                name="Lawyer Basic",
                price_monthly=0.0,
                features=["Directory Listing", "Receive Consultation Requests"],
            ),
            Plan(
                code="lawyer_verified",
                name="Lawyer Verified Badge",
                price_monthly=999.0,
                features=["Verified Badge", "Priority Ranking", "Video Consultation"],
            ),
        ]
        for d in defaults:
            db.add(d)
        db.commit()
        plans = db.query(Plan).order_by(Plan.price_monthly.asc()).all()

    return plans


@router.post("/subscriptions", response_model=CheckoutResponse)
def create_subscription_checkout(
    payload: CheckoutRequest,
    current_user: User = Depends(require_role("user", "lawyer")),
    db: Session = Depends(get_db),
):
    """
    Creates a pending Subscription and executes payment session creation.
    Defaults to instant-approval 'demo' provider for testing.
    """
    plan = db.query(Plan).filter(Plan.code == payload.plan_code.strip()).first()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan '{payload.plan_code}' not found",
        )

    # Create pending Subscription record
    subscription = Subscription(
        user_id=current_user.id,
        plan_id=plan.id,
        status="pending",
        started_at=datetime.utcnow(),
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)

    # Provider: default to demo
    provider_name = payload.provider or "demo"

    # Call payment service adapter
    checkout_session = create_checkout_session(
        db=db,
        user_id=current_user.id,
        type="subscription",
        amount=plan.price_monthly,
        provider=provider_name,
        subscription_id=subscription.id,
    )

    return CheckoutResponse(
        checkout_url=checkout_session["checkout_url"],
        status=checkout_session.get("status", "pending"),
        subscription_id=str(subscription.id),
        payment_id=checkout_session.get("payment_id"),
    )


@router.post("/lawyer/verification-purchase", response_model=CheckoutResponse)
def create_lawyer_verification_purchase(
    payload: Optional[CheckoutRequest] = None,
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Lawyer verification purchase endpoint.
    Verifies user has a lawyer_profiles row (403 if not).
    Calls create_checkout_session with type='verification'.
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have an associated lawyer profile",
        )

    provider_name = (payload.provider if payload and payload.provider else "demo")

    # One-time verification fee: 999.0 BDT
    checkout_session = create_checkout_session(
        db=db,
        user_id=current_user.id,
        type="verification",
        amount=999.0,
        provider=provider_name,
        lawyer_profile_id=profile.id,
    )

    return CheckoutResponse(
        checkout_url=checkout_session["checkout_url"],
        status=checkout_session.get("status", "pending"),
        payment_id=checkout_session.get("payment_id"),
    )


@router.get("/subscriptions/mine", response_model=Optional[SubscriptionResponse])
def get_my_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns the currently logged-in user's active/latest subscription.
    """
    subscription = (
        db.query(Subscription)
        .options(joinedload(Subscription.plan))
        .filter(Subscription.user_id == current_user.id)
        .order_by(Subscription.started_at.desc())
        .first()
    )
    return subscription


@router.get("/admin/payments", response_model=List[PaymentResponse])
def get_admin_payments(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Admin listing of all payments and transactions joined with user details.
    """
    payments = (
        db.query(Payment)
        .options(
            joinedload(Payment.subscription).joinedload(Subscription.user),
            joinedload(Payment.subscription).joinedload(Subscription.plan),
            joinedload(Payment.lawyer_profile).joinedload(LawyerProfile.user),
        )
        .order_by(Payment.created_at.desc())
        .all()
    )

    results = []
    for p in payments:
        user_email = None
        client_name = None

        if p.subscription and p.subscription.user:
            user_email = p.subscription.user.email
            client_name = p.subscription.user.full_name
        elif p.lawyer_profile:
            client_name = p.lawyer_profile.name
            if p.lawyer_profile.user:
                user_email = p.lawyer_profile.user.email

        results.append(
            PaymentResponse(
                id=str(p.id),
                type=p.type,
                amount=p.amount,
                provider=p.provider,
                status=p.status,
                created_at=p.created_at.isoformat() if hasattr(p.created_at, "isoformat") else str(p.created_at),
                user_email=user_email,
                client_name=client_name,
                user_name=client_name,
                transaction_id=p.external_ref or str(p.id),
                method=p.provider,
            )
        )

    return results
