"""
Bookings router: Client booking creation, client's bookings listing,
and lawyer booking management (confirmation/cancellation).
"""

from datetime import datetime, timezone, date
from typing import List
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models import Booking, LawyerProfile, Schedule, User, Subscription, Plan
from app.schemas import BookingCreate, BookingResponse, BookingUpdate
from app.audit import log_audit

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

    # Create pending booking
    new_booking = Booking(
        user_id=current_user.id,
        lawyer_id=schedule.lawyer_id,
        schedule_id=schedule.id,
        status="pending",
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
    return bookings


@router.get("/lawyer/bookings", response_model=List[LawyerBookingResponse])
@router.get("/lawyer/requests", response_model=List[LawyerBookingResponse])
def get_lawyer_bookings(
    current_user: User = Depends(require_role("lawyer")),
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
        .filter(Plan.code == "user_pro")
        .filter(Subscription.expires_at > datetime.now(timezone.utc))
        .all()
    )

    booking_dicts = []
    for booking in bookings:
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

    if target_status not in ["confirmed", "cancelled"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status. Must be 'confirmed' or 'cancelled'",
        )

    old_status = booking.status
    booking.status = target_status

    # If status changed to cancelled, reopen the schedule slot
    if target_status == "cancelled" and booking.schedule:
        booking.schedule.is_booked = False

    db.commit()
    db.refresh(booking)

    # Audit logging
    audit_action = "booking_confirmed" if target_status == "confirmed" else "booking_cancelled"
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
    if target_status not in ["cancelled", "declined"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clients can only cancel bookings with status 'cancelled'",
        )

    old_status = booking.status
    booking.status = "cancelled"

    if booking.schedule:
        booking.schedule.is_booked = False

    db.commit()
    db.refresh(booking)

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="booking_cancelled",
        target_type="booking",
        target_id=str(booking.id),
        details={
            "old_status": old_status,
            "new_status": "cancelled",
            "cancelled_by": "client" if is_owner else "admin",
            "schedule_id": str(booking.schedule_id),
        },
    )

    return booking
