"""
Schedules router: Lawyer availability slots management and public slot querying.
"""

import re
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role, require_verified_lawyer
from app.models import LawyerProfile, Schedule, User, LawyerWeeklyAvailability
from app.schemas import ScheduleCreate, ScheduleResponse

router = APIRouter(prefix="/api", tags=["Schedules"])

TIME_REGEX = re.compile(r"^(\d{1,2}):(\d{2})(?:\s*(AM|PM))?$", re.IGNORECASE)
TIME_REGEX_12H = re.compile(r"^(\d{1,2}):(\d{2})\s*(AM|PM)$", re.IGNORECASE)
TIME_REGEX_24H = re.compile(r"^(\d{1,2}):(\d{2})$")


def parse_time_to_minutes(time_str: str) -> Optional[int]:
    """
    Parses a time string formatted strictly as 'HH:MM' (24-hour) or 'hh:mm AM/PM' (12-hour)
    into total minutes from midnight (0 to 1440).
    Returns None if the format or time values are invalid.
    """
    if not isinstance(time_str, str):
        return None
    s = time_str.strip()

    # 1. 12-hour AM/PM format
    m12 = TIME_REGEX_12H.match(s)
    if m12:
        hh, mm, meridiem = int(m12.group(1)), int(m12.group(2)), m12.group(3).upper()
        if hh < 1 or hh > 12 or mm < 0 or mm > 59:
            return None
        if meridiem == "AM":
            hours = 0 if hh == 12 else hh
        else:
            hours = 12 if hh == 12 else hh + 12
        return hours * 60 + mm

    # 2. 24-hour HH:MM format
    m24 = TIME_REGEX_24H.match(s)
    if m24:
        hh, mm = int(m24.group(1)), int(m24.group(2))
        if mm < 0 or mm > 59:
            return None
        if hh < 0 or hh > 24:
            return None
        if hh == 24 and mm > 0:
            return None
        return hh * 60 + mm

    return None



def _parse_uuid(id_str: str, entity_name: str = "Resource") -> uuid.UUID:
    """Helper to safely parse UUID strings, raising 404 on malformed values."""
    try:
        return uuid.UUID(id_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_name} not found",
        )


@router.get("/lawyers/{lawyer_id}/schedules", response_model=List[ScheduleResponse])
def get_lawyer_available_schedules(
    lawyer_id: str,
    db: Session = Depends(get_db),
):
    """
    Public/Auth endpoint.
    Returns list of available schedules for a specific lawyer where is_booked == False.
    """
    target_uuid = _parse_uuid(lawyer_id, "Lawyer profile")

    lawyer = db.query(LawyerProfile).filter(LawyerProfile.id == target_uuid).first()
    if not lawyer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found",
        )

    schedules = (
        db.query(Schedule)
        .filter(
            Schedule.lawyer_id == target_uuid,
            Schedule.is_booked == False,  # noqa: E712
        )
        .order_by(Schedule.date.asc(), Schedule.start_time.asc())
        .all()
    )
    return schedules


@router.get("/lawyer/schedules", response_model=List[ScheduleResponse])
def get_my_schedules(
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Returns all schedules (booked and unbooked) for the currently authenticated lawyer.
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have an associated lawyer profile",
        )

    schedules = (
        db.query(Schedule)
        .filter(Schedule.lawyer_id == profile.id)
        .order_by(Schedule.date.asc(), Schedule.start_time.asc())
        .all()
    )
    return schedules


@router.post("/availability/slots", status_code=status.HTTP_200_OK)
def create_availability_slots(
    payload: Optional[Dict[str, Any]] = None,
    current_user: User = Depends(require_verified_lawyer),
    db: Session = Depends(get_db),
):
    """
    Creates availability slots. Gated to verified lawyers only.
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have an associated lawyer profile",
        )

    if payload and "date" in payload and "start_time" in payload and "end_time" in payload:
        sched_in = ScheduleCreate(**payload)
        return create_lawyer_schedule(schedule_in=sched_in, current_user=current_user, db=db)

    tomorrow = (datetime.utcnow().date() + timedelta(days=1)).strftime("%Y-%m-%d")
    sched = Schedule(
        id=uuid.uuid4(),
        lawyer_id=profile.id,
        date=datetime.strptime(tomorrow, "%Y-%m-%d").date(),
        start_time="10:00 AM",
        end_time="11:00 AM",
        is_booked=False,
    )
    db.add(sched)
    db.commit()
    db.refresh(sched)
    return {
        "id": str(sched.id),
        "date": tomorrow,
        "start_time": sched.start_time,
        "end_time": sched.end_time,
        "is_booked": False,
    }


@router.post("/lawyer/schedules", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
@router.post("/schedules", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
def create_lawyer_schedule(
    schedule_in: ScheduleCreate,
    current_user: User = Depends(require_verified_lawyer),
    db: Session = Depends(get_db),
):
    """
    Creates a new schedule slot for the currently logged-in lawyer.
    Validations:
      1) Date must be ISO YYYY-MM-DD between today and today + 365 days.
      2) start_time and end_time must match regex ^\\d{2}:\\d{2} (AM|PM)$.
      3) end_time > start_time and duration <= 240 minutes.
      4) Overlapping slots on the same date are rejected.
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have an associated lawyer profile",
        )

    # 1. Date Validation
    raw_date = schedule_in.date.strip() if schedule_in.date else ""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", raw_date):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "invalid_date",
                "message": "Enter a valid date between today and one year ahead.",
            },
        )

    try:
        parsed_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "invalid_date",
                "message": "Enter a valid date between today and one year ahead.",
            },
        )

    today = date.today()
    max_date = today + timedelta(days=365)
    if parsed_date < today or parsed_date > max_date:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "invalid_date",
                "message": "Enter a valid date between today and one year ahead.",
            },
        )

    # 2. Time Format Validation
    start_time_str = schedule_in.start_time.strip() if schedule_in.start_time else ""
    end_time_str = schedule_in.end_time.strip() if schedule_in.end_time else ""

    if not TIME_REGEX.match(start_time_str) or not TIME_REGEX.match(end_time_str):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "invalid_time",
                "message": "Start and end times must follow format 'HH:MM' (24h) or 'hh:mm AM/PM'.",
            },
        )

    start_m = parse_time_to_minutes(start_time_str)
    end_m = parse_time_to_minutes(end_time_str)

    if start_m is None or end_m is None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "invalid_time",
                "message": "Invalid time values provided.",
            },
        )

    # Midnight wrap: 00:00 as end time after start_m > 0 represents end of day (1440m)
    if end_m == 0 and start_m > 0:
        end_m = 1440

    # 3. Order & Duration Validation
    if end_m <= start_m:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "invalid_time",
                "message": "End time must be after start time.",
            },
        )

    duration = end_m - start_m
    if duration > 240:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "invalid_time",
                "message": "Slot duration cannot exceed 240 minutes.",
            },
        )

    # 4. Overlap Detection for Same Lawyer & Date
    existing_slots = (
        db.query(Schedule)
        .filter(
            Schedule.lawyer_id == profile.id,
            Schedule.date == parsed_date,
        )
        .all()
    )

    for slot in existing_slots:
        slot_start_m = parse_time_to_minutes(slot.start_time)
        slot_end_m = parse_time_to_minutes(slot.end_time)
        if slot_start_m is not None and slot_end_m is not None:
            # Overlap if max(start1, start2) < min(end1, end2)
            if max(start_m, slot_start_m) < min(end_m, slot_end_m):
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "error": "overlap",
                        "message": "You already have a slot that overlaps this time.",
                    },
                )

    new_schedule = Schedule(
        lawyer_id=profile.id,
        date=parsed_date,
        start_time=start_time_str,
        end_time=end_time_str,
        is_booked=False,
    )
    db.add(new_schedule)
    db.commit()
    db.refresh(new_schedule)

    return new_schedule



@router.delete("/lawyer/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lawyer_schedule(
    schedule_id: str,
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Allows a lawyer to delete an unbooked schedule slot.
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have an associated lawyer profile",
        )

    schedule_uuid = _parse_uuid(schedule_id, "Schedule slot")
    schedule = (
        db.query(Schedule)
        .filter(Schedule.id == schedule_uuid, Schedule.lawyer_id == profile.id)
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
            detail="Cannot delete an already booked schedule slot",
        )

    db.delete(schedule)
    db.commit()
    return None


# Full 24-hour coverage in 30-minute intervals (48 slots)
TIME_PAIRS: Dict[str, str] = {}
for _h in range(24):
    for _m in (0, 30):
        _start_24 = f"{_h:02d}:{_m:02d}"
        _next_m = _m + 30
        _next_h = _h
        if _next_m >= 60:
            _next_m = 0
            _next_h = (_h + 1) % 24
        _end_24 = f"{_next_h:02d}:{_next_m:02d}"
        TIME_PAIRS[_start_24] = _end_24

# Retain legacy 12-hour AM/PM pairs for backward compatibility
LEGACY_12H_PAIRS = {
    "09:00 AM": "10:00 AM",
    "10:00 AM": "11:00 AM",
    "11:00 AM": "12:00 PM",
    "12:00 PM": "01:00 PM",
    "02:00 PM": "03:00 PM",
    "03:00 PM": "04:00 PM",
    "04:00 PM": "05:00 PM",
    "05:00 PM": "06:00 PM",
}
TIME_PAIRS.update(LEGACY_12H_PAIRS)


@router.get("/lawyer/availability")
def get_lawyer_availability(
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Returns weekly recurring availability schedule for the logged-in lawyer.
    If no record exists, infers from any existing future unbooked schedules.
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        return {"schedule": {}}

    rec = (
        db.query(LawyerWeeklyAvailability)
        .filter(LawyerWeeklyAvailability.lawyer_id == profile.id)
        .first()
    )
    if rec and rec.schedule:
        return {"schedule": rec.schedule}

    # Infer from existing unbooked future schedules
    today = date.today()
    future_slots = (
        db.query(Schedule)
        .filter(
            Schedule.lawyer_id == profile.id,
            Schedule.date >= today,
            Schedule.is_booked == False,
        )
        .all()
    )
    inferred = {}
    for slot in future_slots:
        day_name = slot.date.strftime("%A")
        key = f"{day_name}-{slot.start_time}"
        inferred[key] = True

    return {"schedule": inferred}


@router.put("/lawyer/availability")
def update_lawyer_availability(
    payload: Dict[str, Any],
    current_user: User = Depends(require_verified_lawyer),
    db: Session = Depends(get_db),
):
    """
    Updates weekly recurring availability for the lawyer and syncs unbooked slots for the next 14 days.
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have an associated lawyer profile",
        )

    schedule_data = payload.get("schedule", payload)
    if not isinstance(schedule_data, dict):
        schedule_data = {}

    rec = (
        db.query(LawyerWeeklyAvailability)
        .filter(LawyerWeeklyAvailability.lawyer_id == profile.id)
        .first()
    )
    if not rec:
        rec = LawyerWeeklyAvailability(
            id=uuid.uuid4(),
            lawyer_id=profile.id,
            schedule=schedule_data,
            updated_at=datetime.utcnow(),
        )
        db.add(rec)
    else:
        rec.schedule = schedule_data
        rec.updated_at = datetime.utcnow()

    # Sync slots for next 14 days
    today = date.today()
    for offset in range(1, 15):
        day_date = today + timedelta(days=offset)
        day_name = day_date.strftime("%A")
        for start_time, end_time in TIME_PAIRS.items():
            key = f"{day_name}-{start_time}"
            is_enabled = bool(schedule_data.get(key, False))

            existing = (
                db.query(Schedule)
                .filter(
                    Schedule.lawyer_id == profile.id,
                    Schedule.date == day_date,
                    Schedule.start_time == start_time,
                )
                .first()
            )

            if is_enabled and not existing:
                db.add(
                    Schedule(
                        id=uuid.uuid4(),
                        lawyer_id=profile.id,
                        date=day_date,
                        start_time=start_time,
                        end_time=end_time,
                        is_booked=False,
                    )
                )
            elif not is_enabled and existing and not existing.is_booked:
                db.delete(existing)

    db.commit()
    db.refresh(rec)
    return {"schedule": rec.schedule, "message": "Availability schedule updated successfully."}

