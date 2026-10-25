"""
Case Board router for BD Legal Guide AI.
Handles posting cases by Pro clients, and bidding by Gold Verified lawyers.
"""

from datetime import datetime, timezone, timedelta, date
from typing import List, Optional, Union
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.plans import get_user_plan, is_pro_plan
from app.models import (
    Booking,
    CasePost,
    CaseBid,
    LawyerProfile,
    ProfileAsset,
    Review,
    Schedule,
    User,
)
from app.schemas import (
    CaseBidCreate,
    CaseBidResponse,
    CaseBidAcceptResponse,
    CaseBidRejectResponse,
    CasePostCreate,
    CasePostResponse,
)
from app.services.notifications import trigger_notification

router = APIRouter(prefix="/api", tags=["Case Board"])


def _parse_uuid(val: Union[str, uuid.UUID], label: str = "Case") -> uuid.UUID:
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(str(val).strip())
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{label} not found",
        )


def _get_user_avatar_id(db: Session, user_id: uuid.UUID) -> Optional[str]:
    asset = (
        db.query(ProfileAsset)
        .filter(ProfileAsset.owner_user_id == user_id, ProfileAsset.kind == "avatar")
        .order_by(ProfileAsset.created_at.desc())
        .first()
    )
    return str(asset.id) if asset else None


def _get_lawyer_rating(db: Session, lawyer_user_id: uuid.UUID) -> Optional[float]:
    stat = db.query(func.avg(Review.rating)).filter(Review.reviewee_id == lawyer_user_id).first()
    return round(float(stat[0]), 1) if (stat and stat[0] is not None) else None


def _is_gold_verified_lawyer(user: User, db: Session) -> tuple[bool, Optional[LawyerProfile]]:
    """Checks whether the lawyer is approved and has paid for the gold verified badge."""
    if user.role not in ["lawyer", "admin"]:
        return False, None
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == user.id).first()
    if not profile:
        return False, None
    if user.role == "admin":
        return True, profile
    is_gold = (profile.verification_status == "approved") and (profile.verification_paid is True)
    return is_gold, profile


def _enrich_case_post(case: CasePost, db: Session, include_bids: bool = False) -> CasePostResponse:
    user = db.query(User).filter(User.id == case.user_id).first()
    user_name = user.full_name if user else None
    user_avatar = _get_user_avatar_id(db, case.user_id)

    bids_list = None
    bid_count = len(case.bids) if case.bids else 0

    if include_bids:
        bids_list = []
        for b in (case.bids or []):
            lawyer = b.lawyer_profile
            l_name = lawyer.name if lawyer else None
            l_avatar = _get_user_avatar_id(db, lawyer.user_id) if lawyer else None
            l_rating = _get_lawyer_rating(db, lawyer.user_id) if lawyer else None
            bids_list.append(
                CaseBidResponse(
                    id=str(b.id),
                    case_id=str(b.case_id),
                    lawyer_profile_id=str(b.lawyer_profile_id),
                    proposed_fee=b.proposed_fee,
                    pitch_message=b.pitch_message,
                    status=b.status,
                    created_at=b.created_at.isoformat() if hasattr(b.created_at, "isoformat") else str(b.created_at),
                    lawyer_name=l_name,
                    lawyer_avatar_asset_id=l_avatar,
                    lawyer_avg_rating=l_rating,
                )
            )

    return CasePostResponse(
        id=str(case.id),
        user_id=str(case.user_id),
        title=case.title,
        category=case.category,
        description=case.description,
        status=case.status,
        attachment_asset_ids=[str(a) for a in (case.attachment_asset_ids or [])],
        created_at=case.created_at.isoformat() if hasattr(case.created_at, "isoformat") else str(case.created_at),
        user_name=user_name,
        user_avatar_asset_id=user_avatar,
        bids=bids_list,
        bid_count=bid_count,
    )


# 1) POST /api/cases (Client creates a case)
@router.post("/cases", status_code=status.HTTP_201_CREATED, response_model=CasePostResponse)
def create_case_post(
    payload: CasePostCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Client creates a legal case on the Case Board.
    - Requires role "user".
    - CHECK PLAN: Must be active Pro plan ("user_pro_monthly", "user_pro_6m", "user_pro_1y", "user_pro").
    - If Free user: return 403 {"error":"pro_required","message":"Posting cases to the Case Board is a Pro feature."}
    """
    if current_user.role != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only client users can create case posts.",
        )

    # Check Plan
    plan_code = get_user_plan(db, current_user)
    if not is_pro_plan(plan_code):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": "pro_required",
                "message": "Posting cases to the Case Board is a Pro feature.",
            },
        )

    # Clean attachment ids
    cleaned_attachments = [str(a) for a in (payload.attachment_asset_ids or []) if a]

    case = CasePost(
        id=uuid.uuid4(),
        user_id=current_user.id,
        title=payload.title.strip(),
        category=payload.category.strip(),
        description=payload.description.strip(),
        status="open",
        attachment_asset_ids=cleaned_attachments,
        created_at=datetime.now(timezone.utc),
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    return _enrich_case_post(case, db, include_bids=False)


# 2) GET /api/cases (Lawyers view the board)
@router.get("/cases", response_model=List[CasePostResponse])
def list_open_cases(
    category: Optional[str] = Query(None, description="Optional category filter"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lawyers view open cases on the Case Board.
    - Requires role "lawyer".
    - CHECK VERIFICATION: Lawyer must have verification_status == "approved" AND verification_paid == True.
    - If not verified/paid: return 403 {"error":"verified_required","message":"Only Gold Verified lawyers can view the Case Board."}
    - Return list of CasePosts where status == "open", ordered by created_at DESC.
    """
    if current_user.role not in ["lawyer", "admin"]:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": "verified_required",
                "message": "Only Gold Verified lawyers can view the Case Board.",
            },
        )

    is_gold, profile = _is_gold_verified_lawyer(current_user, db)
    if not is_gold or not profile:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": "verified_required",
                "message": "Only Gold Verified lawyers can view the Case Board.",
            },
        )

    query = db.query(CasePost).filter(CasePost.status == "open")
    if category:
        query = query.filter(CasePost.category.ilike(f"%{category.strip()}%"))

    cases = query.order_by(CasePost.created_at.desc()).all()
    return [_enrich_case_post(c, db, include_bids=False) for c in cases]


# 2.5) GET /api/cases/mine (Client views their posted cases)
@router.get("/cases/mine", response_model=List[CasePostResponse])
def list_my_cases(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Client views all cases they have posted (open, assigned, closed).
    Includes bids so client can review incoming pitches and statuses.
    """
    cases = (
        db.query(CasePost)
        .filter(CasePost.user_id == current_user.id)
        .order_by(CasePost.created_at.desc())
        .all()
    )
    return [_enrich_case_post(c, db, include_bids=True) for c in cases]


# 3) GET /api/cases/{case_id} (View details & bids)
@router.get("/cases/{case_id}", response_model=CasePostResponse)
def get_case_details(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    View details and bids for a specific case:
    - Client can view if they own it.
    - Lawyer can view if they are Verified/Paid.
    - Include the list of CaseBids for this case.
    """
    target_uuid = _parse_uuid(case_id, label="Case")
    case = db.query(CasePost).filter(CasePost.id == target_uuid).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )

    is_owner = (case.user_id == current_user.id)
    is_gold, profile = _is_gold_verified_lawyer(current_user, db)
    is_staff = current_user.role in ["admin", "moderator"]

    if not (is_owner or is_gold or is_staff):
        if current_user.role == "lawyer":
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": "verified_required",
                    "message": "Only Gold Verified lawyers can view the Case Board.",
                },
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view this case.",
        )

    return _enrich_case_post(case, db, include_bids=True)


# 4) POST /api/cases/{case_id}/bid (Lawyer submits a bid)
@router.post("/cases/{case_id}/bid", status_code=status.HTTP_201_CREATED, response_model=CaseBidResponse)
def submit_case_bid(
    case_id: str,
    payload: CaseBidCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lawyer submits a proposed fee and pitch message on an open case.
    - Requires Verified/Paid lawyer.
    - Case status must be "open".
    - Create CaseBid row.
    """
    if current_user.role not in ["lawyer", "admin"]:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": "verified_required",
                "message": "Only Gold Verified lawyers can view the Case Board.",
            },
        )

    is_gold, profile = _is_gold_verified_lawyer(current_user, db)
    if not is_gold or not profile:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": "verified_required",
                "message": "Only Gold Verified lawyers can view the Case Board.",
            },
        )

    target_uuid = _parse_uuid(case_id, label="Case")
    case = db.query(CasePost).filter(CasePost.id == target_uuid).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )

    if case.status != "open":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Case is not open for bidding.",
        )

    # Check for existing bid
    existing_bid = (
        db.query(CaseBid)
        .filter(
            CaseBid.case_id == case.id,
            CaseBid.lawyer_profile_id == profile.id,
        )
        .first()
    )
    if existing_bid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already submitted a bid for this case.",
        )

    bid = CaseBid(
        id=uuid.uuid4(),
        case_id=case.id,
        lawyer_profile_id=profile.id,
        proposed_fee=payload.proposed_fee,
        pitch_message=payload.pitch_message.strip(),
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db.add(bid)
    db.commit()
    db.refresh(bid)

    # In-app notification for the case owner
    try:
        trigger_notification(
            db=db,
            user_id=case.user_id,
            type="case_bid_received",
            title="New Case Bid",
            message=f"{profile.name} submitted a bid of {payload.proposed_fee} BDT on your case '{case.title}'.",
            link=f"/client/cases/{case.id}",
        )
    except Exception:
        pass

    l_avatar = _get_user_avatar_id(db, profile.user_id)
    l_rating = _get_lawyer_rating(db, profile.user_id)

    return CaseBidResponse(
        id=str(bid.id),
        case_id=str(bid.case_id),
        lawyer_profile_id=str(bid.lawyer_profile_id),
        proposed_fee=bid.proposed_fee,
        pitch_message=bid.pitch_message,
        status=bid.status,
        created_at=bid.created_at.isoformat() if hasattr(bid.created_at, "isoformat") else str(bid.created_at),
        lawyer_name=profile.name,
        lawyer_avatar_asset_id=l_avatar,
        lawyer_avg_rating=l_rating,
    )


# 5) POST /api/cases/{case_id}/bids/{bid_id}/accept (Client accepts lawyer bid)
@router.post(
    "/cases/{case_id}/bids/{bid_id}/accept",
    status_code=status.HTTP_200_OK,
    response_model=CaseBidAcceptResponse,
)
def accept_case_bid(
    case_id: str,
    bid_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Client accepts a lawyer's bid on a CasePost.
    - Requires auth: current user MUST be the owner of the CasePost (client).
    - Case status must be 'open'.
    - Bid status must be 'pending'.
    - Atomically:
      a) CaseBid status -> 'accepted'
      b) CasePost status -> 'assigned'
      c) Creates Booking record (status='awaiting_payment', case_brief=...)
      d) Triggers notification to the lawyer
      e) Commits transaction
    - Returns 200 OK with booking ID and success message.
    """
    case_uuid = _parse_uuid(case_id, label="Case")
    bid_uuid = _parse_uuid(bid_id, label="Bid")

    case = db.query(CasePost).filter(CasePost.id == case_uuid).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )

    if case.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the case owner can accept bids.",
        )

    if case.status != "open":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot accept bid for a case with status '{case.status}'. Only 'open' cases can accept bids.",
        )

    bid = (
        db.query(CaseBid)
        .filter(CaseBid.id == bid_uuid, CaseBid.case_id == case.id)
        .first()
    )
    if not bid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bid not found for this case",
        )

    if bid.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only pending bids can be accepted. Current bid status is '{bid.status}'.",
        )

    # 1. Update Bid and Case status
    bid.status = "accepted"
    case.status = "assigned"

    # 2. Resolve schedule for Booking (unique and non-nullable constraint in Booking model)
    today = datetime.now(timezone.utc).date()
    assigned_schedule = (
        db.query(Schedule)
        .filter(
            Schedule.lawyer_id == bid.lawyer_profile_id,
            Schedule.is_booked == False,
            Schedule.date >= today,
        )
        .order_by(Schedule.date.asc(), Schedule.start_time.asc())
        .first()
    )

    if assigned_schedule:
        assigned_schedule.is_booked = True
    else:
        # Create a dedicated consultation schedule
        consult_date = today + timedelta(days=1)
        assigned_schedule = Schedule(
            id=uuid.uuid4(),
            lawyer_id=bid.lawyer_profile_id,
            date=consult_date,
            start_time="10:00 AM",
            end_time="10:30 AM",
            is_booked=True,
        )
        db.add(assigned_schedule)
        db.flush()

    # 3. Fetch LawyerProfile to retrieve meeting_link and lawyer's user_id
    lawyer_profile = (
        db.query(LawyerProfile)
        .filter(LawyerProfile.id == bid.lawyer_profile_id)
        .first()
    )
    meeting_link_prefill = getattr(lawyer_profile, "meeting_link", None) if lawyer_profile else None

    # 4. Create new Booking record
    booking = Booking(
        id=uuid.uuid4(),
        user_id=case.user_id,
        lawyer_id=bid.lawyer_profile_id,
        schedule_id=assigned_schedule.id,
        status="awaiting_payment",
        case_brief=f"Case Acceptance: {case.title}. Lawyer Pitch: {bid.pitch_message}",
        meeting_link=meeting_link_prefill,
        created_at=datetime.utcnow(),
    )
    db.add(booking)
    db.flush()

    # 5. Trigger notification to the lawyer
    lawyer_user_id = lawyer_profile.user_id if lawyer_profile else None
    if lawyer_user_id:
        try:
            trigger_notification(
                db=db,
                user_id=lawyer_user_id,
                type="case_accepted",
                title="Case Accepted!",
                message=f"Your bid for '{case.title}' was accepted. Check your bookings for payment details.",
                link="/lawyer/dashboard",
            )
        except Exception:
            pass

    # 6. Commit transaction
    db.commit()
    db.refresh(booking)

    return CaseBidAcceptResponse(
        message="Bid accepted successfully and booking created.",
        booking_id=str(booking.id),
        case_id=str(case.id),
        bid_id=str(bid.id),
        status=booking.status,
    )


# 6) POST /api/cases/{case_id}/bids/{bid_id}/reject (Client rejects lawyer bid)
@router.post(
    "/cases/{case_id}/bids/{bid_id}/reject",
    status_code=status.HTTP_200_OK,
    response_model=CaseBidRejectResponse,
)
def reject_case_bid(
    case_id: str,
    bid_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Client rejects a lawyer's bid on a CasePost.
    - Requires auth (case owner).
    - Bid status must be 'pending'.
    - Updates CaseBid status to 'rejected'.
    - Commits transaction and returns 200 OK.
    """
    case_uuid = _parse_uuid(case_id, label="Case")
    bid_uuid = _parse_uuid(bid_id, label="Bid")

    case = db.query(CasePost).filter(CasePost.id == case_uuid).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )

    if case.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the case owner can reject bids.",
        )

    bid = (
        db.query(CaseBid)
        .filter(CaseBid.id == bid_uuid, CaseBid.case_id == case.id)
        .first()
    )
    if not bid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bid not found for this case",
        )

    if bid.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only pending bids can be rejected. Current bid status is '{bid.status}'.",
        )

    bid.status = "rejected"

    # Optional notification for the lawyer
    lawyer_profile = (
        db.query(LawyerProfile)
        .filter(LawyerProfile.id == bid.lawyer_profile_id)
        .first()
    )
    if lawyer_profile and lawyer_profile.user_id:
        try:
            trigger_notification(
                db=db,
                user_id=lawyer_profile.user_id,
                type="case_bid_rejected",
                title="Case Bid Update",
                message=f"Your bid for '{case.title}' was not selected.",
                link="/lawyer/dashboard",
            )
        except Exception:
            pass

    db.commit()

    return CaseBidRejectResponse(
        message="Bid rejected successfully.",
        case_id=str(case.id),
        bid_id=str(bid.id),
        status="rejected",
    )
