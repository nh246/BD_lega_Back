"""
Reviews router: consultation reviews creation and lawyer reviews listing.
"""

from datetime import datetime, timezone
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Review, Booking, LawyerProfile, User, ProfileAsset
from app.schemas import ReviewCreate, ReviewResponse
from app.audit import log_audit
from app.services.notifications import trigger_notification

router = APIRouter(prefix="/api", tags=["Reviews"])


def _parse_uuid(id_str: str, entity_name: str = "Resource") -> uuid.UUID:
    """Helper to safely parse UUID strings, raising 404 on malformed values."""
    try:
        return uuid.UUID(str(id_str).strip())
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_name} not found",
        )


@router.post("/reviews", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
def create_review(
    review_in: ReviewCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Submit a review for a completed consultation.
    - Booking status must be 'completed'.
    - Reviewer must be client or lawyer in the booking.
    - Reviewer cannot review themselves (reviewee is the other party).
    - Unique review per booking.
    """
    booking_uuid = _parse_uuid(review_in.booking_id, "Booking")
    booking = (
        db.query(Booking)
        .options(
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

    # Validate status
    if booking.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only completed consultations can be reviewed. Current status is '{booking.status}'.",
        )

    # Validate participation
    is_client = booking.user_id == current_user.id
    is_lawyer = bool(booking.lawyer and booking.lawyer.user_id == current_user.id)
    if not (is_client or is_lawyer):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this consultation",
        )

    # Target reviewee is the other party
    if is_client:
        if not booking.lawyer:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Booking does not have an assigned lawyer",
            )
        reviewee_id = booking.lawyer.user_id
    else:
        reviewee_id = booking.user_id

    # Check for existing review on this booking
    existing_review = db.query(Review).filter(Review.booking_id == booking.id).first()
    if existing_review:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A review for this booking has already been submitted",
        )

    review = Review(
        id=uuid.uuid4(),
        booking_id=booking.id,
        reviewer_id=current_user.id,
        reviewee_id=reviewee_id,
        rating=review_in.rating,
        comment=review_in.comment.strip() if review_in.comment else None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(review)

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="review_created",
        target_type="review",
        target_id=str(review.id),
        details={
            "booking_id": str(booking.id),
            "reviewee_id": str(reviewee_id),
            "rating": review_in.rating,
        },
    )

    db.commit()
    db.refresh(review)

    link = "/lawyer/dashboard" if is_client else "/client/bookings"
    try:
        trigger_notification(
            db=db,
            user_id=reviewee_id,
            type="review_received",
            title="New Review",
            message=f"You received a new {review_in.rating}-star review.",
            link=link,
        )
    except Exception:
        pass

    # Fetch avatar if any
    avatar_asset = (
        db.query(ProfileAsset)
        .filter(
            ProfileAsset.owner_user_id == current_user.id,
            ProfileAsset.kind == "avatar",
        )
        .order_by(ProfileAsset.created_at.desc())
        .first()
    )
    avatar_asset_id = str(avatar_asset.id) if avatar_asset else None

    return ReviewResponse(
        id=str(review.id),
        booking_id=str(review.booking_id),
        reviewer_id=str(review.reviewer_id),
        reviewee_id=str(review.reviewee_id),
        rating=review.rating,
        comment=review.comment,
        created_at=review.created_at.isoformat() if hasattr(review.created_at, "isoformat") else str(review.created_at),
        reviewer_name=current_user.full_name,
        reviewer_avatar_asset_id=avatar_asset_id,
    )


@router.get("/lawyers/{lawyer_id}/reviews", response_model=List[ReviewResponse])
def get_lawyer_reviews(
    lawyer_id: str,
    db: Session = Depends(get_db),
):
    """
    Returns list of reviews for the lawyer (joined with reviewer name and avatar).
    lawyer_id can be either lawyer_profiles.id or users.id.
    """
    lawyer_uuid = _parse_uuid(lawyer_id, "Lawyer")
    profile = (
        db.query(LawyerProfile)
        .filter(or_(LawyerProfile.id == lawyer_uuid, LawyerProfile.user_id == lawyer_uuid))
        .first()
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found",
        )

    reviews = (
        db.query(Review)
        .options(joinedload(Review.reviewer))
        .filter(Review.reviewee_id == profile.user_id)
        .order_by(Review.created_at.desc())
        .all()
    )

    # Bulk or per-reviewer avatar lookup
    reviewer_ids = {r.reviewer_id for r in reviews}
    avatars = (
        db.query(ProfileAsset)
        .filter(
            ProfileAsset.owner_user_id.in_(reviewer_ids),
            ProfileAsset.kind == "avatar",
        )
        .all()
    ) if reviewer_ids else []
    avatar_map = {a.owner_user_id: str(a.id) for a in avatars}

    results = []
    for r in reviews:
        reviewer_name = r.reviewer.full_name if r.reviewer else "Anonymous"
        avatar_asset_id = avatar_map.get(r.reviewer_id)
        results.append(
            ReviewResponse(
                id=str(r.id),
                booking_id=str(r.booking_id),
                reviewer_id=str(r.reviewer_id),
                reviewee_id=str(r.reviewee_id),
                rating=r.rating,
                comment=r.comment,
                created_at=r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at),
                reviewer_name=reviewer_name,
                reviewer_avatar_asset_id=avatar_asset_id,
            )
        )
    return results
