"""
Payment Adapter Service.
Provides checkout session initialization, simulated card processing,
and idempotent order fulfillment for Subscriptions and Lawyer Verifications.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union
import uuid
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import STRIPE_SECRET_KEY
from app.models import LawyerProfile, Payment, Plan, Subscription
from app.audit import log_audit


def fulfill_order(db: Session, payment: Payment) -> None:
    """
    Fulfills a paid order idempotently:
    - subscription: activates or extends Subscription for plan duration_days (default 30).
    - verification: marks lawyer verification_paid=True and triggers admin notification.
    - logs audit 'order_fulfilled'.
    Repeat calls for an already fulfilled payment are no-ops.
    """
    # Idempotency check: if already paid, do not re-fulfill or double-extend
    if payment.status == "paid":
        return

    now = datetime.utcnow()

    # 1. Subscription fulfillment
    if payment.type == "subscription" and payment.subscription_id:
        sub = db.query(Subscription).filter(Subscription.id == payment.subscription_id).first()
        if sub:
            plan = db.query(Plan).filter(Plan.id == sub.plan_id).first()
            duration_days = int(plan.duration_days) if plan and plan.duration_days else 30
            if sub.status == "active" and sub.expires_at and sub.expires_at > now:
                sub.expires_at = sub.expires_at + timedelta(days=duration_days)
            else:
                sub.started_at = now
                sub.expires_at = now + timedelta(days=duration_days)
            sub.status = "active"

            # If this was a lawyer verified subscription plan, also update verification
            if plan and plan.code == "lawyer_verified":
                prof = db.query(LawyerProfile).filter(LawyerProfile.user_id == sub.user_id).first()
                if prof:
                    prof.verification_paid = True
                    try:
                        from app.services.notifications import trigger_admin_notification
                        trigger_admin_notification(
                            db=db,
                            type="verification_fee_paid",
                            title="Lawyer Verification Fee Paid",
                            message=f"Lawyer {prof.name} has paid for verified status.",
                            link="/admin/lawyers",
                        )
                    except Exception:
                        pass

    # 2. Verification fulfillment (one-time fee)
    if payment.type in ["verification", "verification_one_time"]:
        prof = None
        if payment.lawyer_profile_id:
            prof = db.query(LawyerProfile).filter(LawyerProfile.id == payment.lawyer_profile_id).first()
        if not prof and payment.subscription and payment.subscription.user_id:
            prof = db.query(LawyerProfile).filter(LawyerProfile.user_id == payment.subscription.user_id).first()
        if prof:
            prof.verification_paid = True
            try:
                from app.services.notifications import trigger_admin_notification
                trigger_admin_notification(
                    db=db,
                    type="verification_fee_paid",
                    title="Lawyer Verification Fee Paid",
                    message=f"Lawyer {prof.name} has paid the verification badge fee.",
                    link="/admin/lawyers",
                )
            except Exception:
                pass

    payment.status = "paid"
    db.commit()
    db.refresh(payment)

    actor_id = None
    if payment.subscription and payment.subscription.user_id:
        actor_id = payment.subscription.user_id
    elif payment.lawyer_profile and payment.lawyer_profile.user_id:
        actor_id = payment.lawyer_profile.user_id

    log_audit(
        db=db,
        actor_id=actor_id,
        action="order_fulfilled",
        target_type="payment",
        target_id=str(payment.id),
        details={
            "payment_id": str(payment.id),
            "type": payment.type,
            "amount": float(payment.amount),
            "provider": payment.provider,
            "status": "paid",
        },
    )


def create_simulated_session(db: Session, payment: Payment) -> str:
    """
    Creates a simulated checkout session token for test cards.
    """
    session_token = f"sim_sess_{uuid.uuid4().hex}"
    payment.provider = "simulated"
    payment.external_ref = session_token
    db.commit()
    db.refresh(payment)
    return session_token


def confirm_simulated_payment(
    db: Session,
    session_token: str,
    card_number: str,
    expiry: Optional[str] = None,
    cvc: Optional[str] = None,
) -> Payment:
    """
    Processes simulated offline test cards:
    - 4242 4242 4242 4242 -> success (payment paid + order fulfilled)
    - 4000 0000 0000 0000 -> 402 Payment Required (declined)
    - Other -> 400 Bad Request (invalid card format)
    """
    clean_token = session_token.strip() if session_token else ""
    payment = db.query(Payment).filter(Payment.external_ref == clean_token).first()
    if not payment:
        try:
            p_uuid = uuid.UUID(clean_token)
            payment = db.query(Payment).filter(Payment.id == p_uuid).first()
        except Exception:
            pass

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment session not found or expired",
        )

    clean_card = "".join(c for c in str(card_number) if c.isdigit())
    if clean_card == "4242424242424242":
        payment.provider = "simulated"
        fulfill_order(db, payment)
        return payment
    elif clean_card == "4000000000000000":
        payment.status = "failed"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Card declined. Insufficient funds or card restriction.",
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid card format. Supported test cards: 4242 4242 4242 4242 (success) or 4000 0000 0000 0000 (decline).",
        )


def create_checkout_session(
    db: Session,
    user_id: Union[str, uuid.UUID],
    type: str,
    amount: float,
    provider: str = "simulated",
    subscription_id: Optional[Union[str, uuid.UUID]] = None,
    lawyer_profile_id: Optional[Union[str, uuid.UUID]] = None,
) -> Dict[str, Any]:
    """
    Creates an initial Payment row with status='initiated'.
    Instant approval is killed. Returns checkout session details.
    """
    prov = (provider or "simulated").strip().lower()
    sub_uuid = uuid.UUID(str(subscription_id)) if subscription_id and not isinstance(subscription_id, uuid.UUID) else subscription_id
    prof_uuid = uuid.UUID(str(lawyer_profile_id)) if lawyer_profile_id and not isinstance(lawyer_profile_id, uuid.UUID) else lawyer_profile_id

    pay_type = "subscription" if type == "subscription" else "verification_one_time"

    payment = Payment(
        subscription_id=sub_uuid,
        lawyer_profile_id=prof_uuid,
        type=pay_type,
        amount=float(amount),
        provider=prov,
        external_ref=f"tx_{uuid.uuid4().hex[:12]}",
        status="initiated",
        created_at=datetime.utcnow(),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    return {
        "payment_id": str(payment.id),
        "amount": float(payment.amount),
        "checkout_required": True,
        "status": "initiated",
        "checkout_url": f"/checkout?payment_id={payment.id}",
    }
