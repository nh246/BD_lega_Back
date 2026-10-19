"""
Schedules router: Lawyer availability slots management and public slot querying.
"""

from typing import List
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.models import LawyerProfile, Schedule, User
from app.schemas import ScheduleCreate, ScheduleResponse

router = APIRouter(prefix="/api", tags=["Schedules"])


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


@router.post("/lawyer/schedules", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
def create_lawyer_schedule(
    schedule_in: ScheduleCreate,
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Creates a new schedule slot for the currently logged-in lawyer.
    CRITICAL: Verify the logged-in user actually has a lawyer_profiles row. If not, return 403.
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have an associated lawyer profile",
        )

    new_schedule = Schedule(
        lawyer_id=profile.id,
        date=schedule_in.date.strip(),
        start_time=schedule_in.start_time.strip(),
        end_time=schedule_in.end_time.strip(),
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
