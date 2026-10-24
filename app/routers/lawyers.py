from datetime import datetime
import re
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_optional_current_user, require_scope, require_role
from app.models import Booking, LawyerProfile, ProfileAsset, Schedule, User
from app.schemas import LawyerListResponse, LawyerResponse, LawyerUpdate
from app.audit import log_audit

router = APIRouter(prefix="/api", tags=["Lawyers"])


def _parse_uuid(id_str: str) -> uuid.UUID:
    """Helper to safely parse UUID strings, raising 404 on malformed values."""
    try:
        return uuid.UUID(id_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found",
        )


def _can_view_phone(lawyer: LawyerProfile, viewer: Optional[User], db: Session) -> bool:
    """
    Checks if viewer is permitted to see the lawyer's phone number:
    - Lawyer themselves
    - Admin or moderator
    - User with a confirmed booking with this lawyer
    """
    if not viewer:
        return False
    if viewer.id == lawyer.user_id:
        return True
    if viewer.role in ["admin", "moderator"]:
        return True
    has_confirmed = (
        db.query(Booking)
        .filter(
            Booking.user_id == viewer.id,
            Booking.lawyer_id == lawyer.id,
            Booking.status == "confirmed",
        )
        .first()
        is not None
    )
    return has_confirmed


def _enrich_lawyer(
    lawyer: LawyerProfile,
    db: Session,
    viewer: Optional[User] = None,
    allow_phone: bool = False,
) -> LawyerResponse:
    """
    Enriches a LawyerProfile with decision-making information:
    - avatar_asset_id from ProfileAsset
    - next_available slot from Schedule
    - hourly_rate (fee), years_exp, and languages
    - phone: only populated if allow_phone is True and viewer has permission
    """
    # 1. avatar_asset_id
    avatar_asset = (
        db.query(ProfileAsset)
        .filter(
            ProfileAsset.owner_user_id == lawyer.user_id,
            ProfileAsset.kind == "avatar",
        )
        .order_by(ProfileAsset.created_at.desc())
        .first()
    )
    avatar_asset_id = str(avatar_asset.id) if avatar_asset else None

    # 2. next_available slot (is_booked == False and date >= today, earliest date & time)
    today = datetime.now().date()
    open_slots = (
        db.query(Schedule)
        .filter(
            Schedule.lawyer_id == lawyer.id,
            Schedule.is_booked == False,
            Schedule.date >= today,
        )
        .order_by(Schedule.date.asc(), Schedule.start_time.asc())
        .all()
    )

    next_available = None
    if open_slots:
        min_date = open_slots[0].date
        same_date_slots = [s for s in open_slots if s.date == min_date]

        def _parse_time(t_str: str):
            try:
                return datetime.strptime(t_str.strip(), "%I:%M %p").time()
            except Exception:
                try:
                    return datetime.strptime(t_str.strip(), "%H:%M").time()
                except Exception:
                    return datetime.min.time()

        best_slot = min(same_date_slots, key=lambda s: _parse_time(s.start_time))
        date_str = best_slot.date.isoformat() if hasattr(best_slot.date, "isoformat") else str(best_slot.date)
        next_available = {
            "date": date_str,
            "start_time": best_slot.start_time,
        }

    # 3. Decision metrics: fee/hourly_rate, years_exp, languages
    rate = getattr(lawyer, "hourly_rate", None)
    if rate is None or rate == 0:
        rate = 2500 if lawyer.verification_paid else 1500

    exp = getattr(lawyer, "years_exp", None)
    if exp is None or exp == 0:
        exp = 8
        if lawyer.bar_council_id:
            m = re.search(r"\b(19\d\d|20\d\d)\b", lawyer.bar_council_id)
            if m:
                exp = max(1, 2026 - int(m.group(1)))

    langs = getattr(lawyer, "languages", None) or "Bangla, English"

    # 4. Protected phone field
    phone = lawyer.phone if (allow_phone and _can_view_phone(lawyer, viewer, db)) else None

    return LawyerResponse(
        id=str(lawyer.id),
        name=lawyer.name,
        district=lawyer.district,
        specialization=lawyer.specialization,
        phone=phone,
        verification_status=lawyer.verification_status,
        bar_council_id=lawyer.bar_council_id,
        verification_paid=lawyer.verification_paid,
        avatar_asset_id=avatar_asset_id,
        next_available=next_available,
        hourly_rate=rate,
        years_exp=exp,
        languages=langs,
    )


@router.get("/lawyers", response_model=List[LawyerListResponse])
def get_lawyers(
    district: Optional[str] = Query(None, description="Filter by district"),
    specialization: Optional[str] = Query(None, description="Filter by specialization"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Public and authenticated listing of lawyers.
    CRITICAL: Non-admin/moderator users ONLY see lawyers with verification_status == 'approved'.
    Supports filtering by district and specialization.
    Phone is completely omitted from the public listing.
    """
    query = db.query(LawyerProfile)

    # Permission check: Only admins and moderators can see pending/rejected lawyers
    is_staff = current_user and current_user.role in ["admin", "moderator"]
    if not is_staff:
        query = query.filter(LawyerProfile.verification_status == "approved")

    if district:
        query = query.filter(LawyerProfile.district.ilike(f"%{district.strip()}%"))
    if specialization:
        query = query.filter(LawyerProfile.specialization.ilike(f"%{specialization.strip()}%"))

    lawyers = query.order_by(LawyerProfile.name.asc()).all()
    return [_enrich_lawyer(l, db, viewer=current_user, allow_phone=False) for l in lawyers]


@router.get("/admin/lawyers", response_model=List[LawyerResponse])
def get_admin_lawyers(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by verification status"),
    current_user: User = Depends(require_scope("lawyers:view")),
    db: Session = Depends(get_db),
):
    """
    Admin listing of all lawyer profiles across all verification states.
    Requires 'lawyers:view' scope (or admin role).
    """
    query = db.query(LawyerProfile)
    if status_filter:
        query = query.filter(LawyerProfile.verification_status == status_filter.strip())
    lawyers = query.order_by(LawyerProfile.created_at.desc()).all()
    return [_enrich_lawyer(l, db, viewer=current_user, allow_phone=True) for l in lawyers]


@router.get("/lawyers/{lawyer_id}", response_model=LawyerResponse)
def get_lawyer_profile(
    lawyer_id: str,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves full details for a single lawyer profile.
    Phone is revealed only to the lawyer themselves, staff, or a user with a confirmed booking.
    """
    target_uuid = _parse_uuid(lawyer_id)
    profile = db.query(LawyerProfile).filter(LawyerProfile.id == target_uuid).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found",
        )
    return _enrich_lawyer(profile, db, viewer=current_user, allow_phone=True)


@router.patch("/admin/lawyers/{lawyer_id}", response_model=LawyerResponse)
def update_lawyer_verification(
    lawyer_id: str,
    update_data: LawyerUpdate,
    current_user: User = Depends(require_scope("lawyers:verify")),
    db: Session = Depends(get_db),
):
    """
    Admin endpoint to verify or reject lawyer profiles.
    Requires 'lawyers:verify' scope (or admin role).
    Logs an audit trail ('lawyer_verified', 'lawyer_rejected', or 'lawyer_status_updated').
    """
    target_uuid = _parse_uuid(lawyer_id)
    profile = db.query(LawyerProfile).filter(LawyerProfile.id == target_uuid).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found",
        )

    old_status = profile.verification_status

    if update_data.name is not None:
        profile.name = update_data.name.strip()
    if update_data.district is not None:
        profile.district = update_data.district.strip()
    if update_data.specialization is not None:
        profile.specialization = update_data.specialization.strip()
    if update_data.phone is not None:
        profile.phone = update_data.phone.strip()
    if update_data.verification_status is not None:
        profile.verification_status = update_data.verification_status.strip()
    if update_data.hourly_rate is not None:
        profile.hourly_rate = update_data.hourly_rate
    if update_data.years_exp is not None:
        profile.years_exp = update_data.years_exp
    if update_data.languages is not None:
        profile.languages = update_data.languages.strip()

    # Log audit entry on status change or update
    if old_status != profile.verification_status:
        if profile.verification_status == "approved":
            action_name = "lawyer_verified"
        elif profile.verification_status == "rejected":
            action_name = "lawyer_rejected"
        else:
            action_name = "lawyer_status_updated"

        log_audit(
            db=db,
            actor_id=current_user.id,
            action=action_name,
            target_type="lawyer_profile",
            target_id=str(profile.id),
            details={
                "old_status": old_status,
                "new_status": profile.verification_status,
                "lawyer_name": profile.name,
            },
        )

    db.commit()
    db.refresh(profile)
    return _enrich_lawyer(profile, db, viewer=current_user, allow_phone=True)


@router.get("/lawyer/me", response_model=LawyerResponse)
def get_my_lawyer_profile(
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Returns the currently logged-in lawyer's profile, including verification status.
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        # Create profile on-the-fly if missing
        profile = LawyerProfile(
            id=uuid.uuid4(),
            user_id=current_user.id,
            name=current_user.full_name or "Advocate",
            verification_status="pending",
            verification_paid=False,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return _enrich_lawyer(profile, db, viewer=current_user, allow_phone=True)


@router.put("/lawyer/me", response_model=LawyerResponse)
def update_my_lawyer_profile(
    update_data: LawyerUpdate,
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Updates the authenticated lawyer's profile details.
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        profile = LawyerProfile(
            id=uuid.uuid4(),
            user_id=current_user.id,
            name=current_user.full_name or "Advocate",
            verification_status="pending",
            verification_paid=False,
        )
        db.add(profile)

    if update_data.name is not None:
        profile.name = update_data.name.strip()
    if update_data.district is not None:
        profile.district = update_data.district.strip()
    if update_data.specialization is not None:
        profile.specialization = update_data.specialization.strip()
    if update_data.phone is not None:
        profile.phone = update_data.phone.strip()
    if update_data.hourly_rate is not None:
        profile.hourly_rate = update_data.hourly_rate
    if update_data.years_exp is not None:
        profile.years_exp = update_data.years_exp
    if update_data.languages is not None:
        profile.languages = update_data.languages.strip()

    db.commit()
    db.refresh(profile)
    return _enrich_lawyer(profile, db, viewer=current_user, allow_phone=True)

