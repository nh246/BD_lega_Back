"""
Payments and Subscriptions router:
Public plans listing, subscription checkout, lawyer verification purchases,
checkout session initialization (SSLCommerz & Simulated), test card confirmation,
SSLCommerz gateway return handlers, IPN webhooks, and administrator transaction auditing.
"""

from datetime import datetime
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.core.config import FRONTEND_URL
from app.core.database import get_db
from app.core.deps import get_current_user, get_optional_current_user, require_role, require_scope
from app.models import LawyerProfile, Payment, Plan, Subscription, User
from app.schemas import (
    CheckoutRequest,
    CheckoutResponse,
    CheckoutSessionRequest,
    PaymentResponse,
    PlanResponse,
    SimulatedConfirmRequest,
    SubscriptionResponse,
)
from app.services.pay import (
    confirm_simulated_payment,
    create_simulated_session,
    fulfill_order,
    init_sslcommerz_session,
    validate_sslcommerz_transaction,
)

router = APIRouter(prefix="/api", tags=["Payments"])


@router.get("/plans", response_model=List[PlanResponse])
def get_plans(
    role: Optional[str] = Query(None, description="Filter plans by role: 'user' or 'lawyer'"),
    db: Session = Depends(get_db),
):
    """
    Public endpoint. Returns subscription plans from the database.
    Can be filtered by role (e.g. ?role=user or ?role=lawyer).
    """
    from app.core.plans import ensure_plans_exist
    total_count = db.query(Plan).count()
    if total_count == 0:
        ensure_plans_exist(db)

    plans = (
        db.query(Plan)
        .filter(Plan.is_active == True)
        .order_by(Plan.sort_order.asc(), Plan.price_monthly.asc())
        .all()
    )

    if role:
        r = role.strip().lower()
        if r in ["user", "client"]:
            plans = [p for p in plans if "lawyer" not in (p.code or "").lower()]
        elif r in ["lawyer", "advocate"]:
            plans = [p for p in plans if "lawyer" in (p.code or "").lower()]

    return plans


@router.post("/subscriptions", response_model=CheckoutResponse)
def create_subscription(
    payload: CheckoutRequest,
    current_user: User = Depends(require_role("user", "lawyer")),
    db: Session = Depends(get_db),
):
    """
    TASK 1: Creates a pending Subscription and an initiated Payment row.
    Instant approval is killed. Returns checkout_required: True and payment_id.
    """
    plan = None
    if payload.plan_code:
        plan = db.query(Plan).filter(Plan.code == payload.plan_code.strip()).first()
    if not plan and payload.plan_id:
        try:
            p_uuid = uuid.UUID(payload.plan_id.strip())
            plan = db.query(Plan).filter(Plan.id == p_uuid).first()
        except Exception:
            plan = db.query(Plan).filter(Plan.code == payload.plan_id.strip()).first()

    if not plan:
        target_ref = payload.plan_code or payload.plan_id or "unknown"
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan '{target_ref}' not found",
        )

    # Role matching validation
    if current_user.role == "lawyer" and not plan.code.startswith("lawyer_"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lawyers can only subscribe to Lawyer plans (Lawyer Basic or Lawyer Verified Badge).",
        )
    if current_user.role == "user" and not plan.code.startswith("user_"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clients can only subscribe to Client plans (Free or Pro).",
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

    lawyer_profile_id = None
    if current_user.role == "lawyer":
        profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
        if profile:
            lawyer_profile_id = profile.id

    # Create Payment record with status='initiated'
    payment = Payment(
        subscription_id=subscription.id,
        lawyer_profile_id=lawyer_profile_id,
        type="subscription",
        amount=float(plan.price_monthly),
        provider=payload.provider or "pending",
        external_ref=f"tx_{uuid.uuid4().hex[:12]}",
        status="initiated",
        created_at=datetime.utcnow(),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    return CheckoutResponse(
        payment_id=str(payment.id),
        amount=float(payment.amount),
        checkout_required=True,
        subscription_id=str(subscription.id),
        status="initiated",
        checkout_url=f"/checkout?payment_id={payment.id}",
    )


@router.post("/lawyer/verification-purchase", response_model=CheckoutResponse)
def create_lawyer_verification_purchase(
    payload: Optional[CheckoutRequest] = None,
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    TASK 1: Lawyer verification purchase endpoint.
    Verifies user has a lawyer_profiles row (403 if not).
    Instant approval is killed. Creates a Payment row with status='initiated'.
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have an associated lawyer profile",
        )

    provider_name = (payload.provider if payload and payload.provider else "pending")

    payment = Payment(
        subscription_id=None,
        lawyer_profile_id=profile.id,
        type="verification_one_time",
        amount=999.0,
        provider=provider_name,
        external_ref=f"ver_{uuid.uuid4().hex[:12]}",
        status="initiated",
        created_at=datetime.utcnow(),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    return CheckoutResponse(
        payment_id=str(payment.id),
        amount=999.0,
        checkout_required=True,
        status="initiated",
        checkout_url=f"/checkout?payment_id={payment.id}",
    )


@router.post("/payments/checkout")
def create_payment_checkout(
    payload: CheckoutSessionRequest,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    TASK 2: Checkout session initialization endpoint.
    - provider='sslcommerz': initializes gateway session and returns {redirect_url: <GatewayPageURL>}
    - provider='simulated': returns {session_token} for the frontend test card modal.
    """
    try:
        p_uuid = uuid.UUID(payload.payment_id.strip())
        payment = db.query(Payment).filter(Payment.id == p_uuid).first()
    except (ValueError, TypeError):
        payment = db.query(Payment).filter(Payment.external_ref == payload.payment_id.strip()).first()

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment record not found",
        )

    if payment.status == "paid":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This payment has already been completed.",
        )

    prov = (payload.provider or "simulated").strip().lower()

    if prov == "sslcommerz":
        # Resolve user details for billing contact
        user = current_user
        if not user:
            if payment.subscription and payment.subscription.user:
                user = payment.subscription.user
            elif payment.lawyer_profile and payment.lawyer_profile.user:
                user = payment.lawyer_profile.user

        user_name = user.full_name if user else "Valued Client"
        user_email = user.email if user else "client@bdlegal.ai"
        user_phone = user.phone if user and hasattr(user, "phone") else "01700000000"

        prod_name = (
            f"BD Legal Subscription ({payment.subscription.plan.name})"
            if payment.subscription and payment.subscription.plan
            else "BD Legal Lawyer Verification Badge"
        )

        gw_res = init_sslcommerz_session(
            payment_id=str(payment.id),
            amount=payment.amount,
            user_name=user_name,
            user_email=user_email,
            user_phone=user_phone,
            product_name=prod_name,
        )

        payment.provider = "sslcommerz"
        db.commit()

        return {"redirect_url": gw_res["redirect_url"]}

    elif prov == "simulated":
        session_token = create_simulated_session(db, payment)
        return {"session_token": session_token}

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported checkout provider: '{payload.provider}'. Supported: 'sslcommerz', 'simulated'.",
    )


@router.post("/payments/simulated/confirm")
def confirm_simulated_checkout(
    payload: SimulatedConfirmRequest,
    db: Session = Depends(get_db),
):
    """
    TASK 2: Processes offline test card confirmation.
    - 4242 4242 4242 4242 -> 200 Success, Payment status='paid', provider='simulated', order fulfilled.
    - 4000 0000 0000 0000 -> 402 Declined.
    - Other -> 400 Invalid card format.
    """
    payment = confirm_simulated_payment(
        db=db,
        session_token=payload.session_token,
        card_number=payload.card_number,
        expiry=payload.expiry,
        cvc=payload.cvc,
    )

    return {
        "status": "paid",
        "payment_id": str(payment.id),
        "message": "Payment successful and order fulfilled.",
    }


@router.get("/payments/sslcommerz/success")
@router.post("/payments/sslcommerz/success")
async def sslcommerz_success(
    request: Request,
    val_id: Optional[str] = Query(None),
    tran_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    TASK 3: SSLCommerz success return handler.
    Validates transaction with SSLCommerz Validator API. Requires VALID or VALIDATED status.
    Fulfills order idempotently, then redirects browser to FRONTEND_URL/pricing?status=success.
    """
    if not val_id or not tran_id:
        try:
            form = await request.form()
            val_id = val_id or form.get("val_id")
            tran_id = tran_id or form.get("tran_id")
        except Exception:
            pass

    if not val_id:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/pricing?status=failed&reason=missing_val_id",
            status_code=status.HTTP_302_FOUND,
        )

    # Validate with SSLCommerz Validator API
    validation_res = validate_sslcommerz_transaction(val_id)
    v_status = (validation_res.get("status") or "").strip().upper()

    if v_status not in ["VALID", "VALIDATED"]:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/pricing?status=failed&reason=unvalidated",
            status_code=status.HTTP_302_FOUND,
        )

    # Resolve Payment row
    resolved_tran_id = tran_id or validation_res.get("tran_id")
    payment = None
    if resolved_tran_id:
        try:
            p_uuid = uuid.UUID(str(resolved_tran_id))
            payment = db.query(Payment).filter(Payment.id == p_uuid).first()
        except (ValueError, TypeError):
            payment = db.query(Payment).filter(Payment.external_ref == str(resolved_tran_id)).first()

    if not payment:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/pricing?status=failed&reason=payment_not_found",
            status_code=status.HTTP_302_FOUND,
        )

    # Fulfill order idempotently
    payment.provider = "sslcommerz"
    payment.external_ref = val_id
    fulfill_order(db, payment)

    return RedirectResponse(
        url=f"{FRONTEND_URL}/pricing?status=success",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/payments/sslcommerz/fail")
@router.post("/payments/sslcommerz/fail")
async def sslcommerz_fail(
    request: Request,
    tran_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    TASK 3: SSLCommerz fail return handler.
    Marks payment failed and redirects to FRONTEND_URL/pricing?status=failed.
    """
    if not tran_id:
        try:
            form = await request.form()
            tran_id = form.get("tran_id")
        except Exception:
            pass

    if tran_id:
        try:
            p_uuid = uuid.UUID(str(tran_id))
            payment = db.query(Payment).filter(Payment.id == p_uuid).first()
            if payment and payment.status != "paid":
                payment.status = "failed"
                db.commit()
        except Exception:
            pass

    return RedirectResponse(
        url=f"{FRONTEND_URL}/pricing?status=failed",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/payments/sslcommerz/cancel")
@router.post("/payments/sslcommerz/cancel")
async def sslcommerz_cancel(
    request: Request,
    tran_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    TASK 3: SSLCommerz cancel return handler.
    Marks payment cancelled and redirects to FRONTEND_URL/pricing?status=cancelled.
    """
    if not tran_id:
        try:
            form = await request.form()
            tran_id = form.get("tran_id")
        except Exception:
            pass

    if tran_id:
        try:
            p_uuid = uuid.UUID(str(tran_id))
            payment = db.query(Payment).filter(Payment.id == p_uuid).first()
            if payment and payment.status != "paid":
                payment.status = "cancelled"
                db.commit()
        except Exception:
            pass

    return RedirectResponse(
        url=f"{FRONTEND_URL}/pricing?status=cancelled",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/payments/sslcommerz/ipn")
async def sslcommerz_ipn(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    TASK 3: SSLCommerz IPN (Instant Payment Notification) Webhook.
    Idempotent fulfillment: repeat calls must not double-activate or extend.
    """
    data = {}
    try:
        data = await request.json()
    except Exception:
        try:
            form = await request.form()
            data = dict(form)
        except Exception:
            data = {}

    val_id = data.get("val_id")
    tran_id = data.get("tran_id")

    if not val_id or not tran_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing val_id or tran_id in IPN payload",
        )

    # Find payment
    try:
        p_uuid = uuid.UUID(str(tran_id))
        payment = db.query(Payment).filter(Payment.id == p_uuid).first()
    except (ValueError, TypeError):
        payment = db.query(Payment).filter(Payment.external_ref == str(tran_id)).first()

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    # Idempotency check: repeat calls are no-ops
    if payment.status == "paid":
        return {
            "status": "already_processed",
            "payment_id": str(payment.id),
            "message": "Payment already paid and fulfilled. Repeat IPN ignored.",
        }

    # Validate with SSLCommerz Validator API
    validation_res = validate_sslcommerz_transaction(val_id)
    v_status = (validation_res.get("status") or "").strip().upper()

    if v_status not in ["VALID", "VALIDATED"]:
        payment.status = "failed"
        db.commit()
        return {
            "status": "validation_failed",
            "payment_id": str(payment.id),
            "gateway_status": v_status,
        }

    payment.provider = "sslcommerz"
    payment.external_ref = val_id
    fulfill_order(db, payment)

    return {
        "status": "ok",
        "payment_id": str(payment.id),
        "fulfilled": True,
    }


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
    current_user: User = Depends(require_scope("payments:view")),
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
