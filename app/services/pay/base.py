"""
Payment adapter service.
Supports 'demo' provider (instant approval & subscription activation)
alongside structure for Stripe and Paddle integrations.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union
import uuid
from sqlalchemy.orm import Session

from app.core.config import STRIPE_SECRET_KEY
from app.models import LawyerProfile, Payment, Subscription
from app.audit import log_audit


def create_checkout_session(
    db: Session,
    user_id: Union[str, uuid.UUID],
    type: str,
    amount: float,
    provider: str = "demo",
    subscription_id: Optional[Union[str, uuid.UUID]] = None,
    lawyer_profile_id: Optional[Union[str, uuid.UUID]] = None,
) -> Dict[str, Any]:
    """
    Creates a checkout session or executes instant demo approval.

    If provider == 'demo':
      - Instantly creates a Payment record with status='paid'.
      - If type == 'subscription', activates the Subscription (status='active', started_at=now, expires_at=now+30d).
      - If type == 'verification', updates the LawyerProfile to set verification_paid=True.
      - Logs audit 'payment_completed_demo'.
      - Returns {"checkout_url": "http://localhost:5173/payment-success?demo=true", "status": "paid", "payment_id": str(payment.id)}.

    If provider == 'stripe' or 'paddle':
      - Attempts to create a real session if API keys are configured, or returns a mock checkout URL.
    """
    prov = (provider or "demo").strip().lower()
    u_uuid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
    sub_uuid = uuid.UUID(str(subscription_id)) if subscription_id and not isinstance(subscription_id, uuid.UUID) else subscription_id
    prof_uuid = uuid.UUID(str(lawyer_profile_id)) if lawyer_profile_id and not isinstance(lawyer_profile_id, uuid.UUID) else lawyer_profile_id

    if prov == "demo":
        now = datetime.utcnow()
        expires_at = now + timedelta(days=30)
        pay_type = "subscription" if type == "subscription" else "verification_one_time"

        # Resolve lawyer profile if verification
        if type == "verification" and not prof_uuid:
            prof = db.query(LawyerProfile).filter(LawyerProfile.user_id == u_uuid).first()
            if prof:
                prof_uuid = prof.id

        payment = Payment(
            subscription_id=sub_uuid,
            lawyer_profile_id=prof_uuid,
            type=pay_type,
            amount=float(amount),
            provider="demo",
            external_ref=f"demo_tx_{uuid.uuid4().hex[:12]}",
            status="paid",
            created_at=now,
        )
        db.add(payment)

        # Activate subscription if type is subscription
        if type == "subscription" and sub_uuid:
            sub = db.query(Subscription).filter(Subscription.id == sub_uuid).first()
            if sub:
                sub.status = "active"
                sub.started_at = now
                sub.expires_at = expires_at

        # Mark lawyer profile verification_paid if verification
        if type == "verification":
            prof = None
            if prof_uuid:
                prof = db.query(LawyerProfile).filter(LawyerProfile.id == prof_uuid).first()
            if not prof:
                prof = db.query(LawyerProfile).filter(LawyerProfile.user_id == u_uuid).first()
            if prof:
                prof.verification_paid = True
                payment.lawyer_profile_id = prof.id

        db.commit()
        db.refresh(payment)

        log_audit(
            db=db,
            actor_id=u_uuid,
            action="payment_completed_demo",
            target_type="payment",
            target_id=str(payment.id),
            details={
                "type": type,
                "amount": float(amount),
                "provider": "demo",
                "status": "paid",
                "subscription_id": str(sub_uuid) if sub_uuid else None,
                "lawyer_profile_id": str(prof_uuid) if prof_uuid else None,
            },
        )

        return {
            "checkout_url": "http://localhost:5173/payment-success?demo=true",
            "status": "paid",
            "payment_id": str(payment.id),
        }

    # Stripe Provider Handler
    if prov == "stripe" and STRIPE_SECRET_KEY:
        try:
            import stripe
            stripe.api_key = STRIPE_SECRET_KEY
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": "bdt",
                        "product_data": {
                            "name": f"BD Legal Guide AI - {type.replace('_', ' ').capitalize()}",
                        },
                        "unit_amount": int(amount * 100),
                    },
                    "quantity": 1,
                }],
                mode="payment",
                success_url="http://localhost:5173/payment-success?session_id={CHECKOUT_SESSION_ID}",
                cancel_url="http://localhost:5173/pricing",
                client_reference_id=str(u_uuid),
            )
            return {"checkout_url": session.url, "status": "pending"}
        except Exception:
            pass

    # Fallback checkout URL for external providers without live keys during testing/demo
    return {
        "checkout_url": f"https://checkout.{prov}.com/pay/mock_session_{uuid.uuid4().hex[:12]}",
        "status": "pending",
    }
