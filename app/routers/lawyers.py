from datetime import datetime
import re
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.deps import get_optional_current_user, require_scope, require_role
from app.models import Booking, LawyerProfile, ProfileAsset, Schedule, User, Review
from app.schemas import (
    LawyerListResponse,
    LawyerMeetingInfoResponse,
    LawyerMeetingSettingsUpdate,
    LawyerPaymentInfoResponse,
    LawyerPaymentSettingsUpdate,
    LawyerResponse,
    LawyerUpdate,
)
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


def _enrich_lawyers_bulk(
    lawyers: List[LawyerProfile],
    db: Session,
    viewer: Optional[User] = None,
    allow_phone: bool = False,
) -> List[LawyerResponse]:
    """
    Enriches a list of LawyerProfiles in batch with:
    - avatar_asset_id from ProfileAsset
    - next_available slot from Schedule
    - hourly_rate (fee), years_exp, and languages
    - presence_status
    - avg_rating and review_count from Review
    - phone (permission checked)
    """
    if not lawyers:
        return []

    lawyer_ids = [l.id for l in lawyers]
    user_ids = [l.user_id for l in lawyers if l.user_id]

    # 1. Bulk Avatars
    avatar_map = {}
    if user_ids:
        avatars = (
            db.query(ProfileAsset.owner_user_id, ProfileAsset.id)
            .filter(
                ProfileAsset.owner_user_id.in_(user_ids),
                ProfileAsset.kind == "avatar",
            )
            .order_by(ProfileAsset.created_at.desc())
            .all()
        )
        for u_id, a_id in avatars:
            if u_id not in avatar_map:
                avatar_map[u_id] = str(a_id)

    # 2. Bulk Open Slots for next_available
    today = datetime.now().date()
    open_slots = (
        db.query(Schedule)
        .filter(
            Schedule.lawyer_id.in_(lawyer_ids),
            Schedule.is_booked == False,
            Schedule.date >= today,
        )
        .order_by(Schedule.lawyer_id, Schedule.date.asc(), Schedule.start_time.asc())
        .all()
    )

    def _parse_time(t_str: str):
        try:
            return datetime.strptime(t_str.strip(), "%I:%M %p").time()
        except Exception:
            try:
                return datetime.strptime(t_str.strip(), "%H:%M").time()
            except Exception:
                return datetime.min.time()

    slots_by_lawyer = {}
    for s in open_slots:
        slots_by_lawyer.setdefault(s.lawyer_id, []).append(s)

    next_available_map = {}
    for l_id, slots in slots_by_lawyer.items():
        min_date = slots[0].date
        same_date = [s for s in slots if s.date == min_date]
        best_slot = min(same_date, key=lambda s: _parse_time(s.start_time))
        date_str = best_slot.date.isoformat() if hasattr(best_slot.date, "isoformat") else str(best_slot.date)
        next_available_map[l_id] = {
            "date": date_str,
            "start_time": best_slot.start_time,
        }

    # 3. Active meetings presence
    active_meetings = (
        db.query(Booking.lawyer_id)
        .filter(
            Booking.lawyer_id.in_(lawyer_ids),
            Booking.meeting_started_at.isnot(None),
            Booking.meeting_ended_at.is_(None),
        )
        .all()
    )
    busy_lawyer_ids = {m[0] for m in active_meetings}

    # 4. Review stats
    review_map = {}
    if user_ids:
        review_stats = (
            db.query(Review.reviewee_id, func.avg(Review.rating), func.count(Review.id))
            .filter(Review.reviewee_id.in_(user_ids))
            .group_by(Review.reviewee_id)
            .all()
        )
        for u_id, avg_r, count_r in review_stats:
            avg_rating = round(float(avg_r), 1) if avg_r is not None else None
            review_map[u_id] = (avg_rating, count_r or 0)

    # 5. Phone visibility map
    phone_map = {}
    if allow_phone:
        is_staff = viewer and viewer.role in ["admin", "moderator"]
        confirmed_lawyer_ids = set()
        if viewer and not is_staff:
            confirmed_bookings = (
                db.query(Booking.lawyer_id)
                .filter(
                    Booking.user_id == viewer.id,
                    Booking.lawyer_id.in_(lawyer_ids),
                    Booking.status == "confirmed",
                )
                .all()
            )
            confirmed_lawyer_ids = {b[0] for b in confirmed_bookings}

        for l in lawyers:
            can_view = False
            if is_staff:
                can_view = True
            elif viewer and viewer.id == l.user_id:
                can_view = True
            elif l.id in confirmed_lawyer_ids:
                can_view = True
            phone_map[l.id] = l.phone if can_view else None

    # Assemble responses
    results = []
    for lawyer in lawyers:
        avatar_asset_id = avatar_map.get(lawyer.user_id)
        next_available = next_available_map.get(lawyer.id)
        presence_status = "in_consultation" if lawyer.id in busy_lawyer_ids else "available"
        avg_rating, review_count = review_map.get(lawyer.user_id, (None, 0))
        phone = phone_map.get(lawyer.id) if allow_phone else None

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

        results.append(
            LawyerResponse(
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
                presence_status=presence_status,
                avg_rating=avg_rating,
                review_count=review_count,
                meeting_provider=getattr(lawyer, "meeting_provider", None),
                meeting_link=getattr(lawyer, "meeting_link", None),
                payment_methods=getattr(lawyer, "payment_methods", []) or [],
                payment_instructions=getattr(lawyer, "payment_instructions", None),
            )
        )
    return results


def _enrich_lawyer(
    lawyer: LawyerProfile,
    db: Session,
    viewer: Optional[User] = None,
    allow_phone: bool = False,
) -> LawyerResponse:
    """Helper for single lawyer profile enrichment."""
    return _enrich_lawyers_bulk([lawyer], db, viewer=viewer, allow_phone=allow_phone)[0]


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
    return _enrich_lawyers_bulk(lawyers, db, viewer=current_user, allow_phone=False)


# Note: Admin lawyer endpoints are located in app/routers/admin.py



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


@router.put("/lawyer/me/payment-settings", response_model=LawyerPaymentInfoResponse)
def update_my_payment_settings(
    settings_in: LawyerPaymentSettingsUpdate,
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Updates the authenticated lawyer's payment methods and instructions.
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

    profile.payment_methods = settings_in.payment_methods
    profile.payment_instructions = settings_in.payment_instructions.strip() if settings_in.payment_instructions else None

    db.commit()
    db.refresh(profile)

    return {
        "payment_methods": profile.payment_methods or [],
        "payment_instructions": profile.payment_instructions,
    }


@router.get("/lawyer/me/payment-settings", response_model=LawyerPaymentInfoResponse)
def get_my_payment_settings(
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Returns current lawyer's payment methods and instructions.
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        return {"payment_methods": [], "payment_instructions": None}

    return {
        "payment_methods": profile.payment_methods or [],
        "payment_instructions": profile.payment_instructions,
    }


@router.get("/lawyers/{lawyer_id}/payment-info", response_model=LawyerPaymentInfoResponse)
def get_lawyer_payment_info(
    lawyer_id: str,
    db: Session = Depends(get_db),
):
    """
    Public endpoint: returns payment methods and instructions for a lawyer.
    Supports either lawyer_profile.id or lawyer_profile.user_id.
    """
    target_uuid = _parse_uuid(lawyer_id)
    profile = (
        db.query(LawyerProfile)
        .filter((LawyerProfile.id == target_uuid) | (LawyerProfile.user_id == target_uuid))
        .first()
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found",
        )

    return {
        "payment_methods": profile.payment_methods or [],
        "payment_instructions": profile.payment_instructions,
    }


@router.put("/lawyer/me/meeting-settings", response_model=LawyerMeetingInfoResponse)
def update_my_meeting_settings(
    settings_in: LawyerMeetingSettingsUpdate,
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Updates the authenticated lawyer's meeting provider and meeting link.
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

    profile.meeting_provider = settings_in.meeting_provider.strip() if settings_in.meeting_provider else None
    profile.meeting_link = settings_in.meeting_link.strip() if settings_in.meeting_link else None

    db.commit()
    db.refresh(profile)

    return {
        "meeting_provider": profile.meeting_provider,
        "meeting_link": profile.meeting_link,
    }


@router.get("/lawyer/me/meeting-settings", response_model=LawyerMeetingInfoResponse)
def get_my_meeting_settings(
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Returns the authenticated lawyer's meeting provider and meeting link.
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        return {"meeting_provider": None, "meeting_link": None}

    return {
        "meeting_provider": profile.meeting_provider,
        "meeting_link": profile.meeting_link,
    }


@router.get("/lawyers/{lawyer_id}/meeting-info", response_model=LawyerMeetingInfoResponse)
def get_lawyer_meeting_info(
    lawyer_id: str,
    db: Session = Depends(get_db),
):
    """
    Returns a lawyer's meeting provider and meeting link.
    Supports either lawyer_profile.id or lawyer_profile.user_id.
    """
    target_uuid = _parse_uuid(lawyer_id)
    profile = (
        db.query(LawyerProfile)
        .filter((LawyerProfile.id == target_uuid) | (LawyerProfile.user_id == target_uuid))
        .first()
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found",
        )

    return {
        "meeting_provider": profile.meeting_provider,
        "meeting_link": profile.meeting_link,
    }



