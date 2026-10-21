"""
Lawyer Profiles router: Public listing, profile details, and Admin verification.
"""

from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_optional_current_user, require_scope, require_role
from app.models import LawyerProfile, User
from app.schemas import LawyerResponse, LawyerUpdate
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


@router.get("/lawyers", response_model=List[LawyerResponse])
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
    return lawyers


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
    return query.order_by(LawyerProfile.created_at.desc()).all()


@router.get("/lawyers/{lawyer_id}", response_model=LawyerResponse)
def get_lawyer_profile(
    lawyer_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieves full details for a single lawyer profile.
    """
    target_uuid = _parse_uuid(lawyer_id)
    profile = db.query(LawyerProfile).filter(LawyerProfile.id == target_uuid).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found",
        )
    return profile


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
    return profile


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
    return profile


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

    db.commit()
    db.refresh(profile)
    return profile
