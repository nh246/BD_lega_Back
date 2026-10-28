"""
Bookings router: Client booking creation, client's bookings listing,
and lawyer booking management (confirmation/cancellation).
"""

from datetime import datetime, timezone, date, timedelta
import re
from typing import List
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import get_current_user, require_role, check_account_restriction, require_verified_lawyer
from app.models import Booking, LawyerProfile, Schedule, User, Subscription, Plan, AuditLog
from app.schemas import BookingCreate, BookingPaymentSubmit, BookingResponse, BookingUpdate
from app.audit import log_audit
from app.services.notifications import trigger_notification

router = APIRouter(prefix="/api", tags=["Bookings"])


class LawyerBookingResponse(BookingResponse):
    is_pro: bool = False


def _parse_uuid(id_str: str, entity_name: str = "Booking") -> uuid.UUID:
    """Helper to safely parse UUID strings, raising 404 on malformed values."""
    try:
        return uuid.UUID(id_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_name} not found",
        )


def _check_and_apply_lazy_autocomplete(booking: Booking, db: Session) -> bool:
    """
    Lazy Auto-Complete:
    If status == 'completion_requested' and (now - completion_requested_at) > 48 hours,
    update status to 'completed', completed_at = now, and commit.
    """
    if booking.status == "completion_requested" and booking.completion_requested_at:
        now = datetime.now(timezone.utc)
        req_at = booking.completion_requested_at
        if req_at.tzinfo is None:
            req_at = req_at.replace(tzinfo=timezone.utc)
        if (now - req_at) > timedelta(hours=48):
            booking.status = "completed"
            booking.completed_at = now
            log_audit(
                db=db,
                actor_id=booking.user_id,
                action="booking_auto_completed",
                target_type="booking",
                target_id=str(booking.id),
                details={"auto_completed_after_hours": 48},
            )
            db.commit()
            db.refresh(booking)
            return True
    return False


@router.post("/bookings", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking(
    booking_in: BookingCreate,
    current_user: User = Depends(require_role("user")),
    db: Session = Depends(get_db),
):
    """
    Client booking creation.
    Depends on require_role("user").
    Supports both direct schedule_id booking or lawyer_id + slot booking.
    """
    restriction = check_account_restriction(current_user)
    if restriction:
        return restriction

    schedule = None

    if booking_in.schedule_id:
        schedule_uuid = _parse_uuid(booking_in.schedule_id, "Schedule slot")
        schedule = (
            db.query(Schedule)
            .options(joinedload(Schedule.lawyer))
            .filter(Schedule.id == schedule_uuid)
            .first()
        )
        if not schedule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Schedule slot not found",
            )
        if schedule.is_booked:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Schedule slot is already booked",
            )
    elif booking_in.lawyer_id:
        lawyer_uuid = _parse_uuid(booking_in.lawyer_id, "Lawyer profile")
        lawyer = db.query(LawyerProfile).filter(LawyerProfile.id == lawyer_uuid).first()
        if not lawyer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lawyer profile not found",
            )

        # Parse requested slot
        date_str = None
        time_str = "10:00 AM"
        if isinstance(booking_in.slot, dict):
            day_val = booking_in.slot.get("day") or booking_in.slot.get("date")
            time_val = booking_in.slot.get("time") or booking_in.slot.get("start_time")
            if day_val:
                date_str = str(day_val)
            if time_val:
                time_str = str(time_val)
        elif booking_in.date or booking_in.start_time:
            if booking_in.date:
                date_str = str(booking_in.date)
            if booking_in.start_time:
                time_str = str(booking_in.start_time)

        parsed_target_date = None
        if date_str:
            try:
                parsed_target_date = datetime.strptime(str(date_str).strip(), "%Y-%m-%d").date()
            except Exception:
                pass
        if not parsed_target_date:
            parsed_target_date = datetime.now(timezone.utc).date()

        # Look for existing open schedule slot
        schedule = (
            db.query(Schedule)
            .filter(
                Schedule.lawyer_id == lawyer_uuid,
                Schedule.is_booked == False,
                Schedule.date == parsed_target_date,
                Schedule.start_time == time_str,
            )
            .first()
        )

        if not schedule:
            schedule = Schedule(
                id=uuid.uuid4(),
                lawyer_id=lawyer_uuid,
                date=parsed_target_date,
                start_time=time_str,
                end_time=f"{time_str} (30m)",
                is_booked=True,
            )
            db.add(schedule)
            db.flush()
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either schedule_id or lawyer_id must be provided",
        )

    # Mark slot as booked
    schedule.is_booked = True

    # Check lawyer hourly_rate: > 0 -> awaiting_payment, == 0 -> confirmed
    lawyer_profile = schedule.lawyer
    if not lawyer_profile:
        lawyer_profile = db.query(LawyerProfile).filter(LawyerProfile.id == schedule.lawyer_id).first()

    hourly_rate = lawyer_profile.hourly_rate if lawyer_profile and lawyer_profile.hourly_rate is not None else 0
    initial_status = "awaiting_payment" if hourly_rate > 0 else "confirmed"

    # Create booking
    meeting_link_prefill = getattr(lawyer_profile, "meeting_link", None) if lawyer_profile else None
    new_booking = Booking(
        user_id=current_user.id,
        lawyer_id=schedule.lawyer_id,
        schedule_id=schedule.id,
        status=initial_status,
        meeting_link=meeting_link_prefill,
    )
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)

    # Log audit entry
    log_audit(
        db=db,
        actor_id=current_user.id,
        action="booking_created",
        target_type="booking",
        target_id=str(new_booking.id),
        details={
            "schedule_id": str(schedule.id),
            "lawyer_id": str(schedule.lawyer_id),
            "date": schedule.date.isoformat() if hasattr(schedule.date, "isoformat") else str(schedule.date),
            "start_time": schedule.start_time,
            "end_time": schedule.end_time,
            "case_brief": booking_in.case_brief,
        },
    )

    # Re-fetch with relationships loaded for complete response serialization
    booking_loaded = (
        db.query(Booking)
        .options(
            joinedload(Booking.user),
            joinedload(Booking.lawyer),
            joinedload(Booking.schedule),
        )
        .filter(Booking.id == new_booking.id)
        .first()
    )

    return booking_loaded


@router.get("/bookings/mine", response_model=List[BookingResponse])
def get_my_bookings(
    current_user: User = Depends(require_role("user")),
    db: Session = Depends(get_db),
):
    """
    Returns all bookings for the currently authenticated user, joined with lawyer name.
    """
    bookings = (
        db.query(Booking)
        .options(
            joinedload(Booking.user),
            joinedload(Booking.lawyer),
            joinedload(Booking.schedule),
        )
        .filter(Booking.user_id == current_user.id)
        .order_by(Booking.created_at.desc())
        .all()
    )
    for b in bookings:
        _check_and_apply_lazy_autocomplete(b, db)
    return bookings


@router.get("/lawyer/bookings", response_model=List[LawyerBookingResponse])
@router.get("/lawyer/requests", response_model=List[LawyerBookingResponse])
@router.get("/lawyer/consultations", response_model=List[LawyerBookingResponse])
def get_lawyer_bookings(
    current_user: User = Depends(require_verified_lawyer),
    db: Session = Depends(get_db),
):
    """
    Returns all bookings/requests where the schedule belongs to the current lawyer,
    joined with user name and is_pro flag. Supports both /lawyer/bookings and /lawyer/requests.
    Sorted Pro users first (is_pro == True), then by created_at ascending (oldest first).
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have an associated lawyer profile",
        )

    bookings = (
        db.query(Booking)
        .options(
            joinedload(Booking.user),
            joinedload(Booking.lawyer),
            joinedload(Booking.schedule),
        )
        .filter(Booking.lawyer_id == profile.id)
        .all()
    )

    pro_user_ids = set(
        sub.user_id for sub in db.query(Subscription)
        .join(Plan)
        .filter(Subscription.status == "active")
        .filter(Plan.code.in_(["user_pro", "user_pro_monthly", "user_pro_6m", "user_pro_1y"]))
        .filter(Subscription.expires_at > datetime.now(timezone.utc))
        .all()
    )

    booking_dicts = []
    for booking in bookings:
        _check_and_apply_lazy_autocomplete(booking, db)
        b_dict = BookingResponse.model_validate(booking).model_dump()
        b_dict["is_pro"] = (booking.user_id in pro_user_ids) or (str(booking.user_id) in {str(u) for u in pro_user_ids})
        booking_dicts.append(b_dict)

    sorted_bookings = sorted(booking_dicts, key=lambda b: (not b["is_pro"], b["created_at"]))
    return sorted_bookings


@router.get("/lawyer/requests/{booking_id}", response_model=BookingResponse)
def get_lawyer_request_detail(
    booking_id: str,
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Lawyer single booking/request detail endpoint.
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have an associated lawyer profile",
        )

    booking_uuid = _parse_uuid(booking_id, "Booking")
    booking = (
        db.query(Booking)
        .options(
            joinedload(Booking.user),
            joinedload(Booking.lawyer),
            joinedload(Booking.schedule),
        )
        .filter(Booking.id == booking_uuid)
        .first()
    )
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    if booking.lawyer_id != profile.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this booking",
        )

    _check_and_apply_lazy_autocomplete(booking, db)

    return booking


@router.get("/bookings/{booking_id}", response_model=BookingResponse)
def get_booking_detail(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Single booking detail endpoint for client or assigned lawyer or admin.
    """
    booking_uuid = _parse_uuid(booking_id, "Booking")
    booking = (
        db.query(Booking)
        .options(
            joinedload(Booking.user),
            joinedload(Booking.lawyer),
            joinedload(Booking.schedule),
        )
        .filter(Booking.id == booking_uuid)
        .first()
    )
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    # Ensure access rights
    is_owner = booking.user_id == current_user.id
    is_lawyer = (
        current_user.lawyer_profile
        and booking.lawyer_id == current_user.lawyer_profile.id
    )
    is_staff = current_user.role in ["admin", "moderator"]

    if not (is_owner or is_lawyer or is_staff):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this booking",
        )

    _check_and_apply_lazy_autocomplete(booking, db)

    return booking


@router.patch("/lawyer/bookings/{booking_id}", response_model=BookingResponse)
@router.patch("/lawyer/requests/{booking_id}", response_model=BookingResponse)
def update_lawyer_booking(
    booking_id: str,
    update_data: BookingUpdate,
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Lawyer booking update endpoint.
    Takes BookingUpdate with status ('confirmed' or 'cancelled'/'declined').
    CRITICAL: Verify the booking belongs to the current lawyer.
    If status is changed to 'cancelled', set associated schedule is_booked = False.
    Log audit ('booking_confirmed' or 'booking_cancelled').
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have an associated lawyer profile",
        )

    booking_uuid = _parse_uuid(booking_id, "Booking")
    booking = (
        db.query(Booking)
        .options(
            joinedload(Booking.schedule),
            joinedload(Booking.user),
            joinedload(Booking.lawyer),
        )
        .filter(Booking.id == booking_uuid)
        .first()
    )
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    # CRITICAL: Verify the booking belongs to the current lawyer
    if booking.lawyer_id != profile.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this booking",
        )

    target_status = update_data.status.strip().lower()
    if target_status == "declined":
        target_status = "cancelled"

    if target_status not in ["confirmed", "cancelled", "refund_due"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status. Must be 'confirmed', 'cancelled', or 'refund_due'",
        )

    old_status = booking.status
    booking.status = target_status

    # If status changed to cancelled or refund_due, reopen the schedule slot
    if target_status in ["cancelled", "refund_due"] and booking.schedule:
        booking.schedule.is_booked = False

    db.commit()
    db.refresh(booking)

    # Audit logging
    audit_action = (
        "booking_confirmed"
        if target_status == "confirmed"
        else ("booking_refund_flagged" if target_status == "refund_due" else "booking_cancelled")
    )
    log_audit(
        db=db,
        actor_id=current_user.id,
        action=audit_action,
        target_type="booking",
        target_id=str(booking.id),
        details={
            "old_status": old_status,
            "new_status": target_status,
            "schedule_id": str(booking.schedule_id),
            "lawyer_id": str(booking.lawyer_id),
        },
    )

    if target_status == "refund_due":
        try:
            from app.services.notifications import trigger_admin_notification
            client_name = booking.user.full_name if booking.user else "Client"
            trigger_admin_notification(
                db=db,
                type="refund_flagged",
                title="Booking Refund Flagged",
                message=f"Booking #{str(booking.id)[:8]} for client {client_name} marked refund_due.",
                link="/admin",
            )
        except Exception:
            pass

    if target_status == "confirmed":
        lawyer_name = booking.lawyer.name if booking.lawyer and booking.lawyer.name else "Advocate"
        try:
            trigger_notification(
                db=db,
                user_id=booking.user_id,
                type="booking_confirmed",
                title="Booking Confirmed",
                message=f"Your booking with {lawyer_name} is confirmed.",
                link="/client/bookings",
            )
        except Exception:
            pass

    return booking


@router.patch("/bookings/{booking_id}", response_model=BookingResponse)
def client_cancel_booking(
    booking_id: str,
    update_data: BookingUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Allows a client to cancel their own booking, reopening the associated schedule slot.
    """
    booking_uuid = _parse_uuid(booking_id, "Booking")
    booking = (
        db.query(Booking)
        .options(
            joinedload(Booking.schedule),
            joinedload(Booking.user),
            joinedload(Booking.lawyer),
        )
        .filter(Booking.id == booking_uuid)
        .first()
    )
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    # Verify authorization: user is the client who booked it, or admin
    is_owner = booking.user_id == current_user.id
    is_admin = current_user.role == "admin"
    if not (is_owner or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this booking",
        )

    target_status = update_data.status.strip().lower()
    if target_status not in ["cancelled", "declined", "refund_due"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status must be 'cancelled' or 'refund_due'",
        )

    old_status = booking.status
    booking.status = "refund_due" if target_status == "refund_due" else "cancelled"

    if booking.schedule:
        booking.schedule.is_booked = False

    db.commit()
    db.refresh(booking)

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="booking_refund_flagged" if target_status == "refund_due" else "booking_cancelled",
        target_type="booking",
        target_id=str(booking.id),
        details={
            "old_status": old_status,
            "new_status": booking.status,
            "cancelled_by": "client" if is_owner else "admin",
            "schedule_id": str(booking.schedule_id),
        },
    )

    if target_status == "refund_due":
        try:
            from app.services.notifications import trigger_admin_notification
            client_name = booking.user.full_name if booking.user else "Client"
            trigger_admin_notification(
                db=db,
                type="refund_flagged",
                title="Booking Refund Flagged",
                message=f"Booking #{str(booking.id)[:8]} for client {client_name} marked refund_due.",
                link="/admin",
            )
        except Exception:
            pass

    return booking


@router.post("/bookings/{booking_id}/submit-payment", response_model=BookingResponse)
def submit_booking_payment(
    booking_id: str,
    payment_in: BookingPaymentSubmit,
    current_user: User = Depends(require_role("user")),
    db: Session = Depends(get_db),
):
    """
    Client submits payment details (TrxID and optional screenshot asset ID).
    Booking status must be 'awaiting_payment'.
    Transitions status to 'payment_submitted'.
    """
    booking_uuid = _parse_uuid(booking_id, "Booking")
    booking = (
        db.query(Booking)
        .options(
            joinedload(Booking.user),
            joinedload(Booking.lawyer),
            joinedload(Booking.schedule),
        )
        .filter(Booking.id == booking_uuid)
        .first()
    )
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    if booking.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only submit payment for your own bookings",
        )

    if booking.status != "awaiting_payment":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot submit payment for booking with status '{booking.status}'. Must be 'awaiting_payment'.",
        )

    if not payment_in.trx_id or not payment_in.trx_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transaction ID (trx_id) is required",
        )

    booking.trx_id = payment_in.trx_id.strip()

    if payment_in.screenshot_asset_id:
        try:
            booking.screenshot_asset_id = uuid.UUID(str(payment_in.screenshot_asset_id))
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid screenshot_asset_id UUID format",
            )
    else:
        booking.screenshot_asset_id = None

    booking.status = "payment_submitted"

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="booking_payment_submitted",
        target_type="booking",
        target_id=str(booking.id),
        details={
            "trx_id": booking.trx_id,
            "screenshot_asset_id": str(booking.screenshot_asset_id) if booking.screenshot_asset_id else None,
        },
    )

    db.commit()
    db.refresh(booking)

    if booking.lawyer and booking.lawyer.user_id:
        try:
            trigger_notification(
                db=db,
                user_id=booking.lawyer.user_id,
                type="payment_submitted",
                title="Payment Proof Submitted",
                message="Client submitted payment proof. Please verify.",
                link="/lawyer/dashboard",
            )
        except Exception:
            pass

    return booking


@router.post("/bookings/{booking_id}/confirm-payment", response_model=BookingResponse)
@router.post("/lawyer/bookings/{booking_id}/confirm-payment", response_model=BookingResponse)
def confirm_booking_payment(
    booking_id: str,
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Lawyer confirms receipt of payment.
    Booking status must be 'payment_submitted'.
    Transitions status to 'confirmed'.
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have an associated lawyer profile",
        )

    booking_uuid = _parse_uuid(booking_id, "Booking")
    booking = (
        db.query(Booking)
        .options(
            joinedload(Booking.user),
            joinedload(Booking.lawyer),
            joinedload(Booking.schedule),
        )
        .filter(Booking.id == booking_uuid)
        .first()
    )
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    if booking.lawyer_id != profile.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage this booking",
        )

    if booking.status != "payment_submitted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot confirm payment for booking with status '{booking.status}'. Must be 'payment_submitted'.",
        )

    booking.status = "confirmed"

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="booking_payment_confirmed",
        target_type="booking",
        target_id=str(booking.id),
        details={
            "trx_id": booking.trx_id,
            "new_status": "confirmed",
        },
    )

    db.commit()
    db.refresh(booking)

    try:
        trigger_notification(
            db=db,
            user_id=booking.user_id,
            type="payment_confirmed",
            title="Payment Confirmed",
            message="Your payment was confirmed by the lawyer.",
            link="/client/bookings",
        )
    except Exception:
        pass

    return booking


@router.post("/bookings/{booking_id}/reject-payment", response_model=BookingResponse)
@router.post("/lawyer/bookings/{booking_id}/reject-payment", response_model=BookingResponse)
def reject_booking_payment(
    booking_id: str,
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Lawyer rejects payment submission (e.g. invalid TrxID).
    Booking status must be 'payment_submitted'.
    Transitions status back to 'awaiting_payment' so client can retry.
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have an associated lawyer profile",
        )

    booking_uuid = _parse_uuid(booking_id, "Booking")
    booking = (
        db.query(Booking)
        .options(
            joinedload(Booking.user),
            joinedload(Booking.lawyer),
            joinedload(Booking.schedule),
        )
        .filter(Booking.id == booking_uuid)
        .first()
    )
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    if booking.lawyer_id != profile.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage this booking",
        )

    if booking.status != "payment_submitted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reject payment for booking with status '{booking.status}'. Must be 'payment_submitted'.",
        )

    booking.status = "awaiting_payment"

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="booking_payment_rejected",
        target_type="booking",
        target_id=str(booking.id),
        details={
            "trx_id": booking.trx_id,
            "new_status": "awaiting_payment",
        },
    )

    db.commit()
    db.refresh(booking)
    return booking


def _parse_slot_time(t_str: str):
    if not t_str:
        return datetime.min.time()
    clean = re.sub(r"\(.*?\)", "", t_str).strip()
    for fmt in ("%I:%M %p", "%H:%M", "%I %p"):
        try:
            return datetime.strptime(clean, fmt).time()
        except Exception:
            pass
    return datetime.min.time()


@router.post("/bookings/{booking_id}/start-meeting", response_model=BookingResponse)
def start_meeting(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Starts consultation meeting for a confirmed booking.
    Can be called by either the client or the lawyer.
    Sets meeting_started_at and clears meeting_ended_at.
    """
    booking_uuid = _parse_uuid(booking_id, "Booking")
    booking = (
        db.query(Booking)
        .options(
            joinedload(Booking.user),
            joinedload(Booking.lawyer),
            joinedload(Booking.schedule),
        )
        .filter(Booking.id == booking_uuid)
        .first()
    )
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    # Permission check: client or lawyer or admin/moderator
    is_client = booking.user_id == current_user.id
    is_lawyer = bool(booking.lawyer and booking.lawyer.user_id == current_user.id)
    is_staff = current_user.role in ["admin", "moderator"]
    if not (is_client or is_lawyer or is_staff):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to start this meeting",
        )

    if booking.status != "confirmed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only confirmed bookings can start a meeting",
        )

    booking.meeting_started_at = datetime.now(timezone.utc)
    booking.meeting_ended_at = None

    if not booking.meeting_link and booking.lawyer and booking.lawyer.meeting_link:
        booking.meeting_link = booking.lawyer.meeting_link

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="meeting_started",
        target_type="booking",
        target_id=str(booking.id),
        details={"started_at": booking.meeting_started_at.isoformat()},
    )

    db.commit()
    db.refresh(booking)
    return booking


@router.post("/bookings/{booking_id}/extend-meeting")
def extend_meeting(
    booking_id: str,
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Lawyer extends the consultation meeting by 30 minutes if their next schedule slot is free.
    If next slot is booked: returns 400 {"error":"next_slot_booked","message":"Cannot extend. Your next client starts at [time]."}
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have an associated lawyer profile",
        )

    booking_uuid = _parse_uuid(booking_id, "Booking")
    booking = (
        db.query(Booking)
        .options(
            joinedload(Booking.user),
            joinedload(Booking.lawyer),
            joinedload(Booking.schedule),
        )
        .filter(Booking.id == booking_uuid)
        .first()
    )
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    if booking.lawyer_id != profile.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage this booking",
        )

    if booking.status != "confirmed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only confirmed bookings can be extended",
        )

    current_sched = booking.schedule
    curr_date = current_sched.date if current_sched else datetime.now(timezone.utc).date()
    curr_start_t = _parse_slot_time(current_sched.start_time) if current_sched else datetime.min.time()
    curr_end_t = _parse_slot_time(current_sched.end_time) if current_sched else datetime.min.time()

    curr_start_dt = datetime.combine(curr_date, curr_start_t)
    curr_end_dt = datetime.combine(curr_date, curr_end_t)
    if curr_end_dt <= curr_start_dt:
        curr_end_dt = curr_start_dt + timedelta(minutes=30)

    effective_end_dt = curr_end_dt + timedelta(minutes=booking.extended_minutes or 0)

    # Fetch lawyer's subsequent schedule slots on or after this date
    subsequent_slots = (
        db.query(Schedule)
        .filter(
            Schedule.lawyer_id == profile.id,
            Schedule.id != (current_sched.id if current_sched else None),
            Schedule.date >= curr_date,
        )
        .all()
    )

    candidates = []
    for s in subsequent_slots:
        s_start_dt = datetime.combine(s.date, _parse_slot_time(s.start_time))
        if s_start_dt >= effective_end_dt:
            candidates.append((s_start_dt, s))

    candidates.sort(key=lambda x: x[0])

    if candidates:
        next_dt, next_slot = candidates[0]
        if next_slot.is_booked:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": "next_slot_booked",
                    "message": f"Cannot extend. Your next client starts at {next_slot.start_time}.",
                },
            )

    booking.extended_minutes = (booking.extended_minutes or 0) + 30

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="meeting_extended",
        target_type="booking",
        target_id=str(booking.id),
        details={"extended_minutes": booking.extended_minutes},
    )

    db.commit()
    db.refresh(booking)

    return BookingResponse.model_validate(booking)


@router.post("/bookings/{booking_id}/end-meeting", response_model=BookingResponse)
def end_meeting(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Ends consultation meeting for a booking.
    Can be called by either the client or the lawyer.
    Sets meeting_ended_at.
    """
    booking_uuid = _parse_uuid(booking_id, "Booking")
    booking = (
        db.query(Booking)
        .options(
            joinedload(Booking.user),
            joinedload(Booking.lawyer),
            joinedload(Booking.schedule),
        )
        .filter(Booking.id == booking_uuid)
        .first()
    )
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    # Permission check: client or lawyer or admin/moderator
    is_client = booking.user_id == current_user.id
    is_lawyer = bool(booking.lawyer and booking.lawyer.user_id == current_user.id)
    is_staff = current_user.role in ["admin", "moderator"]
    if not (is_client or is_lawyer or is_staff):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to end this meeting",
        )

    booking.meeting_ended_at = datetime.now(timezone.utc)

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="meeting_ended",
        target_type="booking",
        target_id=str(booking.id),
        details={"ended_at": booking.meeting_ended_at.isoformat()},
    )

    db.commit()
    db.refresh(booking)
    return booking


@router.post("/bookings/{booking_id}/request-completion", response_model=BookingResponse)
def request_booking_completion(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Either party (client or lawyer) requests completion of the consultation.
    Requires booking status to be 'confirmed'.
    Sets status = 'completion_requested', completion_requested_at = now.
    """
    booking_uuid = _parse_uuid(booking_id, "Booking")
    booking = (
        db.query(Booking)
        .options(
            joinedload(Booking.user),
            joinedload(Booking.lawyer),
            joinedload(Booking.schedule),
        )
        .filter(Booking.id == booking_uuid)
        .first()
    )
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    is_client = booking.user_id == current_user.id
    is_lawyer = bool(booking.lawyer and booking.lawyer.user_id == current_user.id)
    if not (is_client or is_lawyer):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to request completion for this booking",
        )

    if booking.status != "confirmed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot request completion for booking with status '{booking.status}'. Status must be 'confirmed'.",
        )

    now = datetime.now(timezone.utc)
    booking.status = "completion_requested"
    booking.completion_requested_at = now
    booking.completion_requested_by = "client" if is_client else "lawyer"

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="booking_completion_requested",
        target_type="booking",
        target_id=str(booking.id),
        details={
            "requested_by": "client" if is_client else "lawyer",
            "requested_at": now.isoformat(),
        },
    )

    db.commit()
    db.refresh(booking)
    return booking


@router.post("/bookings/{booking_id}/confirm-completion", response_model=BookingResponse)
def confirm_booking_completion(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    The other party confirms completion of the consultation.
    Requires booking status to be 'completion_requested'.
    Sets status = 'completed', completed_at = now.
    """
    booking_uuid = _parse_uuid(booking_id, "Booking")
    booking = (
        db.query(Booking)
        .options(
            joinedload(Booking.user),
            joinedload(Booking.lawyer),
            joinedload(Booking.schedule),
        )
        .filter(Booking.id == booking_uuid)
        .first()
    )
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    is_client = booking.user_id == current_user.id
    is_lawyer = bool(booking.lawyer and booking.lawyer.user_id == current_user.id)
    if not (is_client or is_lawyer):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to confirm this booking",
        )

    if booking.status != "completion_requested":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Booking is not awaiting completion confirmation. Current status: '{booking.status}'.",
        )

    # Validate that current user is the OTHER party (not the one who requested completion)
    last_req = (
        db.query(AuditLog)
        .filter(
            AuditLog.target_type == "booking",
            AuditLog.target_id == str(booking.id),
            AuditLog.action == "booking_completion_requested",
        )
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    if last_req and last_req.actor_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot confirm completion requested by yourself. The other party must confirm.",
        )

    now = datetime.now(timezone.utc)
    booking.status = "completed"
    booking.completed_at = now

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="booking_completed",
        target_type="booking",
        target_id=str(booking.id),
        details={
            "confirmed_by": "lawyer" if is_lawyer else "client",
            "completed_at": now.isoformat(),
        },
    )

    db.commit()
    db.refresh(booking)
    return booking



