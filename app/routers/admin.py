from datetime import datetime, timezone, timedelta
from typing import List, Optional
import uuid
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, and_, case
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role, require_scope
from app.core.plans import get_user_plan, is_pro_plan
from app.core.security import get_password_hash
from app.models import (
    User,
    AuditLog,
    LawyerProfile,
    Booking,
    CasePost,
    Review,
    MonthlyUsage,
    Subscription,
    Plan,
    Payment,
    ChatMessage,
    ChatSession,
    ProfileAsset,
    LlmConfig,
    ProviderCredential,
)
from app.schemas import (
    UserUpdate,
    ModeratorCreate,
    UserResponse,
    AuditLogResponse,
    AdminOverviewResponse,
    AdminQueryLogResponse,
    AdminQueryRevealRequest,
    AdminQueryRevealResponse,
    AdminLawyerResponse,
    AdminLawyerApproveRequest,
    AdminLawyerRejectRequest,
    AdminLawyerGoldRequest,
    AdminPlanActionRequest,
    AdminUserStatusRequest,
    AdminUserUsageResponse,
    ModeratorPromoteRequest,
    ModeratorEditRequest,
    PlanResponse,
    PlanCreateRequest,
    PlanEditRequest,
    LlmConfigResponse,
    LlmConfigUpdate,
    LlmTestPromptRequest,
    LlmTestPromptResponse,
    ProviderCredentialUpdate,
    ProviderCredentialResponse,
    ProviderCredentialListResponse,
)
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
    if not users:
        return []

    user_ids = [u.id for u in users]
    now_utc = datetime.now(timezone.utc)

    # Fetch active subscriptions
    active_subs = (
        db.query(Subscription)
        .join(Plan, Subscription.plan_id == Plan.id)
        .filter(
            Subscription.user_id.in_(user_ids),
            Subscription.status == "active",
        )
        .order_by(Subscription.started_at.desc())
        .all()
    )
    user_active_sub = {}
    for sub in active_subs:
        if sub.user_id in user_active_sub:
            continue
        if sub.expires_at is not None:
            exp = sub.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp <= now_utc:
                continue
        user_active_sub[sub.user_id] = sub

    # Fetch monthly usages for current year & month
    usages = (
        db.query(MonthlyUsage)
        .filter(
            MonthlyUsage.user_id.in_(user_ids),
            MonthlyUsage.year == now_utc.year,
            MonthlyUsage.month == now_utc.month,
        )
        .all()
    )
    user_usage_map = {m.user_id: m.messages_used for m in usages}

    results = []
    for u in users:
        sub = user_active_sub.get(u.id)
        plan_code = sub.plan.code if (sub and sub.plan) else "user_free"
        plan_exp_str = None
        if sub and sub.expires_at:
            plan_exp_str = sub.expires_at.isoformat() if hasattr(sub.expires_at, "isoformat") else str(sub.expires_at)
        msgs = user_usage_map.get(u.id, 0)

        results.append(
            UserResponse(
                id=str(u.id),
                email=u.email,
                full_name=u.full_name,
                role=u.role,
                status=u.status,
                scopes=u.scopes or [],
                plan=plan_code,
                is_pro=is_pro_plan(plan_code),
                plan_code=plan_code,
                plan_expires_at=plan_exp_str,
                messages_this_month=msgs,
            )
        )
    return results


@router.post("/users/{user_id}/plan")
def manage_user_plan(
    user_id: str,
    payload: AdminPlanActionRequest,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Grant or revoke user Pro plan.
    - grant: create/extend Subscription with plan code mapped from duration
      (user_pro_monthly / user_pro_6m / user_pro_1y), payment_method='admin_grant',
      price 0, expires_at = now + duration_days.
    - revoke: set the active subscription expires_at = now (or status cancelled).
    - Audit log 'admin_plan_grant' / 'admin_plan_revoke' with duration.
    """
    target_uuid = _parse_uuid(user_id)
    user = db.query(User).filter(User.id == target_uuid).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    now_utc = datetime.now(timezone.utc)
    action = (payload.action or "").lower().strip()

    if action == "grant":
        duration = payload.duration_days or 30
        if duration >= 365:
            plan_code = "user_pro_1y"
        elif duration >= 180:
            plan_code = "user_pro_6m"
        else:
            plan_code = "user_pro_monthly"

        plan = db.query(Plan).filter(Plan.code == plan_code).first()
        if not plan:
            from app.core.plans import ensure_plans_exist
            ensure_plans_exist(db)
            plan = db.query(Plan).filter(Plan.code == plan_code).first()

        new_expires_at = now_utc + timedelta(days=duration)

        active_sub = (
            db.query(Subscription)
            .filter(
                Subscription.user_id == user.id,
                Subscription.status == "active",
            )
            .order_by(Subscription.started_at.desc())
            .first()
        )

        if active_sub:
            active_sub.plan_id = plan.id
            active_sub.status = "active"
            active_sub.expires_at = new_expires_at
            sub = active_sub
        else:
            sub = Subscription(
                id=uuid.uuid4(),
                user_id=user.id,
                plan_id=plan.id,
                status="active",
                started_at=now_utc,
                expires_at=new_expires_at,
            )
            db.add(sub)
            db.flush()

        payment = Payment(
            id=uuid.uuid4(),
            subscription_id=sub.id,
            type="subscription",
            amount=0.0,
            provider="admin_grant",
            status="paid",
            created_at=now_utc,
        )
        db.add(payment)
        db.commit()
        db.refresh(sub)

        log_audit(
            db=db,
            actor_id=current_user.id,
            action="admin_plan_grant",
            target_type="user",
            target_id=str(user.id),
            details={
                "duration_days": duration,
                "plan_code": plan_code,
                "expires_at": new_expires_at.isoformat(),
            },
        )
        return {
            "success": True,
            "message": f"Granted {plan.name} for {duration} days",
            "plan_code": plan_code,
            "expires_at": new_expires_at.isoformat(),
        }

    elif action == "revoke":
        active_subs = (
            db.query(Subscription)
            .filter(
                Subscription.user_id == user.id,
                Subscription.status == "active",
            )
            .all()
        )
        for s in active_subs:
            s.status = "cancelled"
            s.expires_at = now_utc
        db.commit()

        log_audit(
            db=db,
            actor_id=current_user.id,
            action="admin_plan_revoke",
            target_type="user",
            target_id=str(user.id),
            details={
                "revoked_at": now_utc.isoformat(),
            },
        )
        return {
            "success": True,
            "message": "User plan revoked. Reverted to Free plan.",
            "plan_code": "user_free",
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid action. Must be 'grant' or 'revoke'.",
        )


@router.post("/users/{user_id}/status")
def set_user_status(
    user_id: str,
    payload: AdminUserStatusRequest,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Set user account status: active | restricted | blocked.
    Audit log 'admin_user_status'.
    """
    target_uuid = _parse_uuid(user_id)
    user = db.query(User).filter(User.id == target_uuid).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    new_status = (payload.status or "").lower().strip()
    if new_status not in ["active", "restricted", "blocked"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status must be 'active', 'restricted', or 'blocked'.",
        )

    old_status = user.status
    user.status = new_status
    db.commit()
    db.refresh(user)

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="admin_user_status",
        target_type="user",
        target_id=str(user.id),
        details={
            "old_status": old_status,
            "new_status": user.status,
        },
    )
    return {
        "success": True,
        "message": f"User status updated to {new_status}",
        "status": user.status,
    }


@router.get("/users/{user_id}/usage", response_model=AdminUserUsageResponse)
def get_user_usage(
    user_id: str,
    current_user: User = Depends(require_scope("users:view")),
    db: Session = Depends(get_db),
):
    """
    Retrieve user usage statistics:
    {plan_code, messages_this_month, monthly_limit, sessions_count, bookings_count, cases_count, reviews_given}.
    """
    target_uuid = _parse_uuid(user_id)
    user = db.query(User).filter(User.id == target_uuid).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    now_utc = datetime.now(timezone.utc)
    plan_code = get_user_plan(db, user)
    is_pro = is_pro_plan(plan_code)
    monthly_limit = None if is_pro else 15

    usage_row = (
        db.query(MonthlyUsage)
        .filter(
            MonthlyUsage.user_id == user.id,
            MonthlyUsage.year == now_utc.year,
            MonthlyUsage.month == now_utc.month,
        )
        .first()
    )
    messages_this_month = usage_row.messages_used if usage_row else 0

    sessions_count = db.query(func.count(ChatSession.id)).filter(ChatSession.user_id == user.id).scalar() or 0
    bookings_count = db.query(func.count(Booking.id)).filter(Booking.user_id == user.id).scalar() or 0
    cases_count = db.query(func.count(CasePost.id)).filter(CasePost.user_id == user.id).scalar() or 0
    reviews_given = db.query(func.count(Review.id)).filter(Review.reviewer_id == user.id).scalar() or 0

    return AdminUserUsageResponse(
        plan_code=plan_code,
        messages_this_month=messages_this_month,
        monthly_limit=monthly_limit,
        sessions_count=sessions_count,
        bookings_count=bookings_count,
        cases_count=cases_count,
        reviews_given=reviews_given,
    )


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


@router.post("/moderators/promote", response_model=UserResponse)
def promote_user_to_moderator(
    payload: ModeratorPromoteRequest,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Promote an existing user (role='user') to moderator with scopes.
    Validates user exists and is currently role='user'.
    Sets user.role = 'moderator', user.scopes = scopes.
    Audit log 'moderator_promoted' with scopes list.
    """
    target_uuid = _parse_uuid(payload.user_id)
    user = db.query(User).filter(User.id == target_uuid).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.role != "user":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only standard users (role='user') can be promoted to moderator. User currently has role '{user.role}'.",
        )

    clean_scopes = [s.strip() for s in (payload.scopes or []) if s and s.strip()]
    user.role = "moderator"
    user.scopes = clean_scopes

    db.commit()
    db.refresh(user)

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="moderator_promoted",
        target_type="user",
        target_id=str(user.id),
        details={
            "email": user.email,
            "full_name": user.full_name,
            "scopes": clean_scopes,
        },
    )
    return user


@router.post("/moderators/{id}/demote", response_model=UserResponse)
@router.delete("/moderators/{id}", response_model=UserResponse)
def demote_moderator(
    id: str,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Demotes a moderator back to standard user role and clears scopes.
    Sets user.role = 'user', user.scopes = [].
    Audit log 'moderator_demoted'.
    """
    target_uuid = _parse_uuid(id)
    user = db.query(User).filter(User.id == target_uuid).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Moderator not found",
        )

    previous_scopes = user.scopes or []
    user.role = "user"
    user.scopes = []

    db.commit()
    db.refresh(user)

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="moderator_demoted",
        target_type="user",
        target_id=str(user.id),
        details={
            "email": user.email,
            "full_name": user.full_name,
            "previous_scopes": previous_scopes,
        },
    )
    return user


@router.post("/moderators/{id}/edit", response_model=UserResponse)
def edit_moderator(
    id: str,
    payload: ModeratorEditRequest,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Updates moderator's name and scopes.
    Audit log 'moderator_updated' with old/new scopes.
    """
    target_uuid = _parse_uuid(id)
    user = db.query(User).filter(User.id == target_uuid).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Moderator not found",
        )

    old_name = user.full_name
    old_scopes = user.scopes or []

    clean_name = payload.name.strip() if payload.name else old_name
    clean_scopes = [s.strip() for s in (payload.scopes or []) if s and s.strip()]

    user.full_name = clean_name
    user.scopes = clean_scopes

    db.commit()
    db.refresh(user)

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="moderator_updated",
        target_type="user",
        target_id=str(user.id),
        details={
            "old_name": old_name,
            "new_name": clean_name,
            "old_scopes": old_scopes,
            "new_scopes": clean_scopes,
        },
    )
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


@router.get("/overview", response_model=AdminOverviewResponse)
@router.get("/analytics", response_model=AdminOverviewResponse)
def get_admin_overview(
    current_user: User = Depends(require_scope("analytics:view")),
    db: Session = Depends(get_db),
):
    """
    Returns platform overview metrics:
    - total_users (User.role == 'user')
    - total_lawyers (User.role == 'lawyer')
    - pending_lawyers (LawyerProfile.verification_status == 'pending')
    - total_bookings (Booking count)
    - open_cases (CasePost.status == 'open')
    - total_reviews (Review count)
    - monthly_messages (sum of MonthlyUsage.messages_used for current month)
    - monthly_revenue_est (sum of Subscription price where expires_at > now) + (sum of LawyerProfile where verification_paid=True * 999)
    """
    now = datetime.utcnow()
    total_users = db.query(func.count(User.id)).filter(User.role == "user").scalar() or 0
    total_lawyers = db.query(func.count(User.id)).filter(User.role == "lawyer").scalar() or 0
    pending_lawyers = (
        db.query(func.count(LawyerProfile.id))
        .filter(LawyerProfile.verification_status == "pending")
        .scalar()
        or 0
    )
    total_bookings = db.query(func.count(Booking.id)).scalar() or 0
    open_cases = (
        db.query(func.count(CasePost.id))
        .filter(CasePost.status == "open")
        .scalar()
        or 0
    )
    total_reviews = db.query(func.count(Review.id)).scalar() or 0

    monthly_messages = (
        db.query(func.sum(MonthlyUsage.messages_used))
        .filter(MonthlyUsage.year == now.year, MonthlyUsage.month == now.month)
        .scalar()
        or 0
    )

    active_subs_rev = (
        db.query(func.sum(Plan.price_monthly))
        .join(Subscription, Subscription.plan_id == Plan.id)
        .filter(
            or_(
                Subscription.expires_at > now,
                and_(Subscription.status == "active", Subscription.expires_at.is_(None)),
            )
        )
        .scalar()
        or 0.0
    )

    paid_lawyers_count = (
        db.query(func.count(LawyerProfile.id))
        .filter(LawyerProfile.verification_paid == True)
        .scalar()
        or 0
    )

    monthly_revenue_est = round(float(active_subs_rev + (paid_lawyers_count * 999.0)), 2)

    return AdminOverviewResponse(
        total_users=total_users,
        total_lawyers=total_lawyers,
        pending_lawyers=pending_lawyers,
        total_bookings=total_bookings,
        open_cases=open_cases,
        total_reviews=total_reviews,
        monthly_messages=monthly_messages,
        monthly_revenue_est=monthly_revenue_est,
        active_lawyers=total_lawyers,
        pending_verifications=pending_lawyers,
    )


@router.get("/queries", response_model=List[AdminQueryLogResponse])
def get_admin_queries(
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_scope("queries:view")),
    db: Session = Depends(get_db),
):
    """
    Returns the last 50 AI chat queries ordered by created_at DESC.
    Includes user name, active subscription plan, and char_count.
    Content is privacy-masked by default (no content or content_excerpt returned).
    """
    msgs = (
        db.query(ChatMessage)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .join(User, ChatSession.user_id == User.id)
        .filter(ChatMessage.role == "user")
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )

    results = []
    for m in msgs:
        u = m.session.user if m.session else None
        user_name = u.full_name if u else "Anonymous"
        plan_code = get_user_plan(db, u) if u else "user_free"
        created_at_str = (
            m.created_at.isoformat()
            if hasattr(m.created_at, "isoformat")
            else str(m.created_at)
        )
        char_count = len(m.content or "")
        results.append(
            AdminQueryLogResponse(
                id=str(m.id),
                user_name=user_name,
                plan_code=plan_code,
                created_at=created_at_str,
                char_count=char_count,
            )
        )

    return results


@router.post("/queries/{id}/reveal", response_model=AdminQueryRevealResponse)
def reveal_admin_query(
    id: str,
    data: Optional[AdminQueryRevealRequest] = Body(None),
    current_user: User = Depends(require_scope("queries:view")),
    db: Session = Depends(get_db),
):
    """
    Reveals the full message content of a privacy-masked AI query.
    Requires a non-empty justification reason.
    Logs an audit entry with action='admin_query_reveal' with actor, target user,
    and reason BEFORE returning anything.
    Missing/empty reason raises HTTP 400.
    """
    if not data or not data.reason or not data.reason.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Justification reason is required and cannot be empty",
        )

    clean_reason = data.reason.strip()
    msg_uuid = _parse_uuid(id)
    msg = db.query(ChatMessage).filter(ChatMessage.id == msg_uuid).first()
    if not msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Query message not found",
        )

    # Resolve target user from message session
    target_user = None
    if msg.session and msg.session.user:
        target_user = msg.session.user
    elif msg.session_id:
        session = db.query(ChatSession).filter(ChatSession.id == msg.session_id).first()
        if session and session.user_id:
            target_user = db.query(User).filter(User.id == session.user_id).first()

    target_user_id = str(target_user.id) if target_user else None
    target_user_name = target_user.full_name if target_user else "Unknown"

    # Log audit entry BEFORE returning anything
    log_audit(
        db=db,
        actor_id=current_user.id,
        action="admin_query_reveal",
        target_type="user",
        target_id=target_user_id,
        details={
            "query_id": str(msg.id),
            "target_user_id": target_user_id,
            "target_user_name": target_user_name,
            "reason": clean_reason,
            "char_count": len(msg.content or ""),
        },
    )

    return AdminQueryRevealResponse(
        id=str(msg.id),
        content=msg.content or "",
    )


def _enrich_admin_lawyers(lawyers: List[LawyerProfile], db: Session) -> List[AdminLawyerResponse]:
    """Helper to enrich LawyerProfile rows with assets, reviews, and bookings in batch."""
    if not lawyers:
        return []

    lawyer_ids = [l.id for l in lawyers]
    user_ids = [l.user_id for l in lawyers if l.user_id]

    # Verification assets for each lawyer's user_id
    verif_assets = (
        db.query(ProfileAsset.owner_user_id, ProfileAsset.id)
        .filter(
            ProfileAsset.owner_user_id.in_(user_ids),
            ProfileAsset.kind == "verification",
        )
        .order_by(ProfileAsset.created_at.desc())
        .all()
    )
    verif_assets_map = {}
    for u_id, a_id in verif_assets:
        verif_assets_map.setdefault(u_id, []).append(str(a_id))

    # Booking counts per lawyer
    booking_counts = (
        db.query(Booking.lawyer_id, func.count(Booking.id))
        .filter(Booking.lawyer_id.in_(lawyer_ids))
        .group_by(Booking.lawyer_id)
        .all()
    )
    booking_count_map = {l_id: cnt for l_id, cnt in booking_counts}

    # Review stats per lawyer (Review.reviewee_id == l.user_id)
    review_stats = (
        db.query(Review.reviewee_id, func.avg(Review.rating), func.count(Review.id))
        .filter(Review.reviewee_id.in_(user_ids))
        .group_by(Review.reviewee_id)
        .all()
    )
    review_map = {
        u_id: (round(float(avg_r), 1) if avg_r is not None else 0.0, cnt or 0)
        for u_id, avg_r, cnt in review_stats
    }

    results = []
    for l in lawyers:
        avg_r, rev_cnt = review_map.get(l.user_id, (0.0, 0))
        b_cnt = booking_count_map.get(l.id, 0)
        v_assets = verif_assets_map.get(l.user_id, [])
        u_email = l.user.email if l.user else None
        created_at_str = (
            l.created_at.isoformat()
            if hasattr(l.created_at, "isoformat")
            else str(l.created_at)
        )

        results.append(
            AdminLawyerResponse(
                id=str(l.id),
                user_id=str(l.user_id),
                name=l.name,
                email=u_email,
                phone=l.phone,
                bar_council_id=l.bar_council_id,
                district=l.district,
                specialization=l.specialization,
                years_experience=l.years_exp or 0,
                years_exp=l.years_exp or 0,
                avg_rating=avg_r,
                review_count=rev_cnt,
                booking_count=b_cnt,
                verification_status=l.verification_status,
                verification_paid=bool(l.verification_paid),
                verification_note=l.verification_note,
                verification_asset_ids=v_assets,
                created_at=created_at_str,
            )
        )
    return results


@router.get("/lawyers", response_model=List[AdminLawyerResponse])
def get_admin_lawyers(
    status: Optional[str] = Query(None, description="Filter by status: pending, approved, rejected, all"),
    current_user: User = Depends(require_scope("lawyers:view")),
    db: Session = Depends(get_db),
):
    """
    Admin listing of lawyer profiles enriched with:
    - verification_status ('pending', 'approved', 'rejected')
    - verification_asset_ids (list of ProfileAsset IDs with kind='verification')
    - bar_council_id, district, specialization, years_experience
    - avg_rating, review_count, booking_count
    - verification_paid (gold flag)
    - verification_note
    """
    query = db.query(LawyerProfile)
    if status and status.strip() and status.strip().lower() != "all":
        query = query.filter(LawyerProfile.verification_status == status.strip().lower())

    # Order with pending status first, then by created_at descending
    case_order = case(
        (LawyerProfile.verification_status == "pending", 1),
        (LawyerProfile.verification_status == "approved", 2),
        (LawyerProfile.verification_status == "rejected", 3),
        else_=4,
    )
    lawyers = query.order_by(case_order, LawyerProfile.created_at.desc()).all()
    return _enrich_admin_lawyers(lawyers, db)


@router.post("/lawyers/{id}/approve", response_model=AdminLawyerResponse)
def approve_lawyer(
    id: str,
    data: Optional[AdminLawyerApproveRequest] = Body(None),
    current_user: User = Depends(require_scope("lawyers:approve")),
    db: Session = Depends(get_db),
):
    """
    Approves a lawyer's verification status.
    Sets verification_status='approved'.
    Logs audit entry 'lawyer_verified'.
    """
    target_uuid = _parse_uuid(id)
    profile = (
        db.query(LawyerProfile)
        .filter(or_(LawyerProfile.id == target_uuid, LawyerProfile.user_id == target_uuid))
        .first()
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found",
        )

    note = data.note.strip() if (data and data.note and data.note.strip()) else None
    profile.verification_status = "approved"
    if note:
        profile.verification_note = note

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="lawyer_verified",
        target_type="lawyer_profile",
        target_id=str(profile.id),
        details={
            "lawyer_name": profile.name,
            "lawyer_user_id": str(profile.user_id),
            "note": note,
        },
    )

    db.commit()
    db.refresh(profile)
    enriched = _enrich_admin_lawyers([profile], db)
    return enriched[0]


@router.post("/lawyers/{id}/reject", response_model=AdminLawyerResponse)
def reject_lawyer(
    id: str,
    data: Optional[AdminLawyerRejectRequest] = Body(None),
    current_user: User = Depends(require_scope("lawyers:approve")),
    db: Session = Depends(get_db),
):
    """
    Rejects a lawyer's verification status with a required non-empty reason.
    Sets verification_status='rejected', stores reason in verification_note.
    Missing/empty reason raises HTTP 400.
    Logs audit entry 'lawyer_rejected'.
    """
    if not data or not data.reason or not data.reason.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rejection reason is required and cannot be empty",
        )

    clean_reason = data.reason.strip()
    target_uuid = _parse_uuid(id)
    profile = (
        db.query(LawyerProfile)
        .filter(or_(LawyerProfile.id == target_uuid, LawyerProfile.user_id == target_uuid))
        .first()
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found",
        )

    profile.verification_status = "rejected"
    profile.verification_note = clean_reason

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="lawyer_rejected",
        target_type="lawyer_profile",
        target_id=str(profile.id),
        details={
            "lawyer_name": profile.name,
            "lawyer_user_id": str(profile.user_id),
            "reason": clean_reason,
        },
    )

    db.commit()
    db.refresh(profile)
    enriched = _enrich_admin_lawyers([profile], db)
    return enriched[0]


@router.post("/lawyers/{id}/gold", response_model=AdminLawyerResponse)
def toggle_lawyer_gold(
    id: str,
    data: AdminLawyerGoldRequest,
    current_user: User = Depends(require_scope("lawyers:approve")),
    db: Session = Depends(get_db),
):
    """
    Sets verification_paid = grant (manual Gold override for comps/revokes).
    Logs audit entry 'lawyer_gold_override'.
    """
    target_uuid = _parse_uuid(id)
    profile = (
        db.query(LawyerProfile)
        .filter(or_(LawyerProfile.id == target_uuid, LawyerProfile.user_id == target_uuid))
        .first()
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found",
        )

    profile.verification_paid = bool(data.grant)

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="lawyer_gold_override",
        target_type="lawyer_profile",
        target_id=str(profile.id),
        details={
            "lawyer_name": profile.name,
            "lawyer_user_id": str(profile.user_id),
            "verification_paid": profile.verification_paid,
            "granted": profile.verification_paid,
        },
    )

    db.commit()
    db.refresh(profile)
    enriched = _enrich_admin_lawyers([profile], db)
    return enriched[0]


@router.get("/plans", response_model=List[PlanResponse])
def get_admin_plans(
    current_user: User = Depends(require_scope("plans:edit")),
    db: Session = Depends(get_db),
):
    """
    Returns all subscription plans, including inactive ones.
    """
    from app.core.plans import ensure_plans_exist

    total_count = db.query(Plan).count()
    if total_count == 0:
        ensure_plans_exist(db)

    plans = (
        db.query(Plan)
        .order_by(Plan.sort_order.asc(), Plan.price_monthly.asc())
        .all()
    )
    return plans


@router.post("/plans", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
def create_admin_plan(
    data: PlanCreateRequest,
    current_user: User = Depends(require_scope("plans:edit")),
    db: Session = Depends(get_db),
):
    """
    Creates a new subscription plan and logs audit 'plan_created'.
    """
    code = data.code.strip()
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plan code cannot be empty",
        )

    # Normalize role in code if needed
    role = (data.role or "user").strip().lower()
    if role == "lawyer" and "lawyer" not in code.lower():
        code = f"lawyer_{code}"

    existing = db.query(Plan).filter(Plan.code == code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Plan with code '{code}' already exists",
        )

    new_plan = Plan(
        code=code,
        name=data.name.strip(),
        price_monthly=float(data.price_monthly),
        duration_days=data.duration_days if data.duration_days is not None else 30,
        is_active=True if data.is_active is None else bool(data.is_active),
        features=data.features or [],
        description=data.description.strip() if data.description else None,
        is_popular=bool(data.is_popular) if data.is_popular is not None else False,
        sort_order=int(data.sort_order) if data.sort_order is not None else 0,
    )
    db.add(new_plan)
    db.flush()

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="plan_created",
        target_type="plan",
        target_id=str(new_plan.id),
        details={
            "code": new_plan.code,
            "name": new_plan.name,
            "price_monthly": new_plan.price_monthly,
            "duration_days": new_plan.duration_days,
            "is_active": new_plan.is_active,
            "role": new_plan.target_role,
            "description": new_plan.description,
            "features": new_plan.features,
            "is_popular": new_plan.is_popular,
            "sort_order": new_plan.sort_order,
        },
    )

    db.commit()
    db.refresh(new_plan)
    return new_plan


@router.post("/plans/{id}/edit", response_model=PlanResponse, status_code=status.HTTP_200_OK)
def edit_admin_plan(
    id: str,
    data: PlanEditRequest,
    current_user: User = Depends(require_scope("plans:edit")),
    db: Session = Depends(get_db),
):
    """
    Updates an existing subscription plan and logs audit 'plan_updated' with old and new values.
    """
    plan = None
    try:
        plan_uuid = uuid.UUID(id)
        plan = db.query(Plan).filter(Plan.id == plan_uuid).first()
    except (ValueError, TypeError):
        pass

    if not plan:
        plan = db.query(Plan).filter(Plan.code == id).first()

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    old_values = {
        "name": plan.name,
        "price_monthly": plan.price_monthly,
        "duration_days": plan.duration_days,
        "is_active": plan.is_active,
        "description": plan.description,
        "features": plan.features,
        "is_popular": plan.is_popular,
        "sort_order": plan.sort_order,
    }

    if data.name is not None:
        plan.name = data.name.strip()
    if data.price_monthly is not None:
        plan.price_monthly = float(data.price_monthly)
    if data.duration_days is not None:
        plan.duration_days = int(data.duration_days)
    if data.is_active is not None:
        plan.is_active = bool(data.is_active)
    if data.description is not None:
        plan.description = data.description.strip() if data.description else None
    if data.features is not None:
        plan.features = [f.strip() for f in data.features if f.strip()]
    if data.is_popular is not None:
        plan.is_popular = bool(data.is_popular)
    if data.sort_order is not None:
        plan.sort_order = int(data.sort_order)

    new_values = {
        "name": plan.name,
        "price_monthly": plan.price_monthly,
        "duration_days": plan.duration_days,
        "is_active": plan.is_active,
        "description": plan.description,
        "features": plan.features,
        "is_popular": plan.is_popular,
        "sort_order": plan.sort_order,
    }

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="plan_updated",
        target_type="plan",
        target_id=str(plan.id),
        details={
            "code": plan.code,
            "old_values": old_values,
            "new_values": new_values,
        },
    )

    db.commit()
    db.refresh(plan)
    return plan


@router.post("/plans/{id}/delete", status_code=status.HTTP_200_OK)
def delete_admin_plan(
    id: str,
    current_user: User = Depends(require_scope("plans:edit")),
    db: Session = Depends(get_db),
):
    """
    Hard deletes a plan ONLY if no Subscription references this plan_id.
    If referenced: returns 400 {"error": "plan_in_use", "message": "This plan has subscriptions. Deactivate it instead."}.
    Audit logs 'plan_deleted'.
    """
    plan = None
    try:
        plan_uuid = uuid.UUID(id)
        plan = db.query(Plan).filter(Plan.id == plan_uuid).first()
    except (ValueError, TypeError):
        pass

    if not plan:
        plan = db.query(Plan).filter(Plan.code == id).first()

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    # Check if any Subscription references this plan_id
    sub_count = db.query(Subscription).filter(Subscription.plan_id == plan.id).count()
    if sub_count > 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "plan_in_use",
                "message": "This plan has subscriptions. Deactivate it instead.",
            },
        )

    plan_id_str = str(plan.id)
    plan_code = plan.code
    plan_name = plan.name

    db.delete(plan)

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="plan_deleted",
        target_type="plan",
        target_id=plan_id_str,
        details={
            "code": plan_code,
            "name": plan_name,
        },
    )

    db.commit()
    return {"message": "Plan deleted successfully", "code": plan_code}


# ==============================================================================
# LLM Configuration & Provider Credentials Endpoints
# ==============================================================================

SUPPORTED_PROVIDERS = ["gemini", "openai", "anthropic", "mock"]


def _get_provider_credential_details(db: Session, provider: str) -> dict:
    from app.services.llm.base import resolve_provider_credential
    api_key, base_url, source = resolve_provider_credential(provider)

    row = db.query(ProviderCredential).filter(ProviderCredential.provider == provider).first()
    masked_key = None
    if row and row.api_key and row.api_key.strip():
        k = row.api_key.strip()
        masked_key = f"....{k[-4:]}" if len(k) >= 4 else f"....{k}"
        base_url = row.base_url
    elif source == "env" and api_key and provider != "mock":
        k = api_key.strip()
        masked_key = f"....{k[-4:]}" if len(k) >= 4 else f"....{k}"

    return {
        "provider": provider,
        "has_key": bool(api_key),
        "source": source,
        "masked_key": masked_key,
        "base_url": base_url,
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
    }


def _get_llm_api_key_status(db: Session = None) -> dict:
    from app.services.llm.base import resolve_provider_credential
    return {
        prov: bool(resolve_provider_credential(prov)[0])
        for prov in ["openai", "anthropic", "gemini", "openrouter", "mock"]
    }


def _get_llm_credential_status(db: Session = None) -> dict:
    from app.services.llm.base import resolve_provider_credential
    cred_map = {}
    for prov in ["gemini", "openai", "anthropic", "mock", "openrouter"]:
        api_key, base_url, source = resolve_provider_credential(prov)
        cred_map[prov] = {
            "has_key": bool(api_key),
            "source": source,
            "base_url": base_url,
        }
    return cred_map


DEFAULT_BD_LEGAL_SYSTEM_PROMPT = (
    "You are BD Legal AI, a Bangladesh legal assistant specializing in Bangladesh law "
    "(Penal Code 1860, Evidence Act 1872, CPC 1908, CrPC 1898, Family Courts Ordinance 1985, "
    "Land laws, Company Act 1994). Always:\n"
    "- Cite specific sections/acts when advising\n"
    "- Structure responses: Legal Analysis → Key Sections → Practical Steps\n"
    "- State confidence level (High/Medium/Low) based on clarity of facts\n"
    "- If facts are ambiguous, ask clarifying questions before advising\n"
    "- Never give definitive legal advice; always recommend consulting a lawyer\n"
    "- Use plain English with Bengali legal terms in parentheses when helpful\n"
    "- Decline non-legal questions politely"
)
DEFAULT_DISCLAIMER = "This information is for educational purposes and not a substitute for professional legal advice."


def _get_or_create_active_llm_config(db: Session) -> LlmConfig:
    active_config = (
        db.query(LlmConfig)
        .filter(LlmConfig.is_active == True)  # noqa: E712
        .order_by(LlmConfig.created_at.desc())
        .first()
    )
    if not active_config:
        active_config = LlmConfig(
            provider="gemini",
            model_name="gemini-2.5-flash",
            temperature=0.7,
            max_tokens=2048,
            system_prompt=DEFAULT_BD_LEGAL_SYSTEM_PROMPT,
            disclaimer=DEFAULT_DISCLAIMER,
            is_active=True,
        )
        db.add(active_config)
        db.commit()
        db.refresh(active_config)
    return active_config


@router.get("/credentials", response_model=ProviderCredentialListResponse)
def get_admin_credentials(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Returns per-provider key configuration status, source ('db' | 'env' | 'none'),
    masked key (last 4 chars only, e.g. '....ab12'), and base_url. NEVER full key.
    """
    items = [_get_provider_credential_details(db, p) for p in SUPPORTED_PROVIDERS]
    return {"credentials": items}


@router.post("/credentials", response_model=ProviderCredentialResponse)
def update_admin_credential(
    payload: ProviderCredentialUpdate,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Saves or clears provider credentials in DB. Empty api_key clears to NULL (falls back to env).
    Audits 'credential_updated' WITHOUT the key value anywhere.
    """
    prov = payload.provider.strip().lower()
    if prov not in SUPPORTED_PROVIDERS and prov != "openrouter":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider: {payload.provider}",
        )

    cred = db.query(ProviderCredential).filter(ProviderCredential.provider == prov).first()
    if not cred:
        cred = ProviderCredential(provider=prov)
        db.add(cred)

    if payload.api_key is not None:
        clean_key = payload.api_key.strip()
        cred.api_key = clean_key if clean_key else None

    if payload.base_url is not None:
        clean_url = payload.base_url.strip()
        cred.base_url = clean_url if clean_url else None

    cred.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(cred)

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="credential_updated",
        target_type="provider_credential",
        target_id=str(cred.id),
        details={
            "provider": prov,
            "has_api_key": bool(cred.api_key),
            "has_base_url": bool(cred.base_url),
            "source": "db" if cred.api_key else "fallback",
        },
    )

    return _get_provider_credential_details(db, prov)


@router.get("/llm-config", response_model=LlmConfigResponse)
def get_admin_llm_config(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Returns active LLM configuration, provider credentials status, and API key status.
    """
    config = _get_or_create_active_llm_config(db)
    res = LlmConfigResponse.model_validate(config)
    res.api_key_status = _get_llm_api_key_status(db)
    res.credential_status = _get_llm_credential_status(db)
    return res


@router.post("/llm-config", response_model=LlmConfigResponse)
@router.put("/llm-config", response_model=LlmConfigResponse)
def update_admin_llm_config(
    payload: LlmConfigUpdate,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Updates active LLM configuration and logs audit 'llm_config_updated'.
    """
    db.query(LlmConfig).update({LlmConfig.is_active: False})

    new_config = LlmConfig(
        provider=payload.provider.strip().lower(),
        model_name=(payload.model_name or payload.model or "gemini-2.5-flash").strip(),
        temperature=float(payload.temperature),
        max_tokens=int(payload.max_tokens),
        system_prompt=payload.system_prompt,
        disclaimer=payload.disclaimer,
        is_active=payload.is_active,
    )
    db.add(new_config)
    db.commit()
    db.refresh(new_config)

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="llm_config_updated",
        target_type="llm_config",
        target_id=str(new_config.id),
        details={
            "provider": new_config.provider,
            "model_name": new_config.model_name,
            "temperature": new_config.temperature,
            "max_tokens": new_config.max_tokens,
            "is_active": new_config.is_active,
        },
    )

    res = LlmConfigResponse.model_validate(new_config)
    res.api_key_status = _get_llm_api_key_status(db)
    res.credential_status = _get_llm_credential_status(db)
    return res


@router.post("/llm-config/test", response_model=LlmTestPromptResponse)
def test_admin_llm_config(
    payload: LlmTestPromptRequest,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Sends a test prompt to the currently configured provider and returns the AI reply.
    Logs audit 'llm_test_prompt'.
    """
    config = _get_or_create_active_llm_config(db)
    prompt_text = (payload.prompt or "").strip()
    if not prompt_text:
        prompt_text = "Test prompt: What is the statute of limitations for civil suits in Bangladesh?"

    from app.services.llm.base import generate_response

    combined_system = f"{config.system_prompt or ''}\n\n{config.disclaimer or ''}".strip()
    messages = [
        {"role": "system", "content": combined_system or "You are an AI legal assistant."},
        {"role": "user", "content": prompt_text},
    ]

    try:
        reply_text = generate_response(
            provider=config.provider,
            model=config.model_name,
            messages=messages,
            temp=config.temperature,
            max_tokens=config.max_tokens,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"LLM test prompt failed: {str(exc)}",
        )

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="llm_test_prompt",
        target_type="llm_config",
        target_id=str(config.id),
        details={
            "provider": config.provider,
            "model": config.model_name,
            "prompt": prompt_text[:100],
        },
    )

    return LlmTestPromptResponse(
        response=reply_text,
        reply=reply_text,
        provider=config.provider,
        model=config.model_name,
    )


@router.post("/llm-config/reset", response_model=LlmConfigResponse)
def reset_admin_llm_config(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Reverts LLM configuration to default values (gemini-2.5-flash / 0.7 / 2048) and logs audit 'llm_config_reset'.
    """
    db.query(LlmConfig).update({LlmConfig.is_active: False})

    default_config = LlmConfig(
        provider="gemini",
        model_name="gemini-2.5-flash",
        temperature=0.7,
        max_tokens=2048,
        system_prompt=DEFAULT_BD_LEGAL_SYSTEM_PROMPT,
        disclaimer=DEFAULT_DISCLAIMER,
        is_active=True,
    )
    db.add(default_config)
    db.commit()
    db.refresh(default_config)

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="llm_config_reset",
        target_type="llm_config",
        target_id=str(default_config.id),
        details={
            "reset_to": "defaults",
            "provider": default_config.provider,
            "model": default_config.model_name,
        },
    )

    res = LlmConfigResponse.model_validate(default_config)
    res.api_key_status = _get_llm_api_key_status(db)
    res.credential_status = _get_llm_credential_status(db)
    return res


