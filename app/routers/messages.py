"""
Direct messaging router: Pro-only messaging channel between citizens and approved lawyers.
"""

from datetime import datetime
from typing import List
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import require_role
from app.core.plans import get_user_plan
from app.models import DirectMessage, LawyerProfile, User
from app.schemas import (
    DirectMessageCreate,
    DirectMessageResponse,
    LawyerInboxItem,
)

router = APIRouter(prefix="/api", tags=["Messages"])


def _parse_uuid(id_str: str, entity_name: str = "Resource") -> uuid.UUID:
    """Helper to safely parse UUID strings, raising 404 on malformed values."""
    try:
        return uuid.UUID(str(id_str))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_name} not found",
        )


def _format_message(msg: DirectMessage, current_user_id: uuid.UUID) -> DirectMessageResponse:
    """Helper to enrich DirectMessageResponse with display metadata."""
    sender_name = None
    sender_role = "user"
    if msg.sender:
        sender_name = msg.sender.full_name
        sender_role = msg.sender.role
    elif msg.lawyer_profile and msg.sender_user_id == msg.lawyer_profile.user_id:
        sender_name = msg.lawyer_profile.name
        sender_role = "lawyer"

    created_at_str = msg.created_at.isoformat() if hasattr(msg.created_at, "isoformat") else str(msg.created_at)

    return DirectMessageResponse(
        id=str(msg.id),
        sender_user_id=str(msg.sender_user_id),
        lawyer_profile_id=str(msg.lawyer_profile_id),
        recipient_user_id=str(msg.recipient_user_id) if msg.recipient_user_id else None,
        content=msg.content,
        is_read=msg.is_read,
        created_at=created_at_str,
        sender_name=sender_name,
        sender_role=sender_role,
    )


# ==============================================================================
# Citizen / User Direct Message Endpoints
# ==============================================================================

@router.post("/messages/lawyer/{lawyer_id}", response_model=DirectMessageResponse, status_code=status.HTTP_201_CREATED)
def send_message_to_lawyer(
    lawyer_id: str,
    payload: DirectMessageCreate,
    current_user: User = Depends(require_role("user")),
    db: Session = Depends(get_db),
):
    """
    Citizen sends a message to an approved lawyer.
    Requires Pro plan. Free plan users receive 402 Payment Required.
    """
    user_plan = get_user_plan(db, current_user)
    if user_plan == "user_free":
        return JSONResponse(
            status_code=402,
            content={
                "error": "pro_required",
                "message": "Direct messaging with verified lawyers is a Pro feature.",
                "detail": "Direct messaging with verified lawyers is a Pro feature.",
            },
        )

    lawyer_uuid = _parse_uuid(lawyer_id, "Lawyer profile")
    lawyer = (
        db.query(LawyerProfile)
        .options(joinedload(LawyerProfile.user))
        .filter(LawyerProfile.id == lawyer_uuid)
        .first()
    )

    if not lawyer or lawyer.verification_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approved lawyer profile not found",
        )

    new_message = DirectMessage(
        id=uuid.uuid4(),
        sender_user_id=current_user.id,
        lawyer_profile_id=lawyer.id,
        recipient_user_id=lawyer.user_id,
        content=payload.content.strip(),
        is_read=False,
        created_at=datetime.utcnow(),
    )
    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    return _format_message(new_message, current_user.id)


@router.get("/messages/lawyer/{lawyer_id}", response_model=List[DirectMessageResponse])
def get_messages_with_lawyer(
    lawyer_id: str,
    current_user: User = Depends(require_role("user")),
    db: Session = Depends(get_db),
):
    """
    Citizen retrieves the conversation thread with a specific lawyer, ordered by created_at.
    """
    lawyer_uuid = _parse_uuid(lawyer_id, "Lawyer profile")
    lawyer = db.query(LawyerProfile).filter(LawyerProfile.id == lawyer_uuid).first()
    if not lawyer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found",
        )

    messages = (
        db.query(DirectMessage)
        .options(joinedload(DirectMessage.sender), joinedload(DirectMessage.lawyer_profile))
        .filter(
            DirectMessage.lawyer_profile_id == lawyer.id,
            or_(
                DirectMessage.sender_user_id == current_user.id,
                DirectMessage.recipient_user_id == current_user.id,
            ),
        )
        .order_by(DirectMessage.created_at.asc())
        .all()
    )

    # Mark lawyer's incoming messages as read by citizen
    has_unread = False
    for m in messages:
        if m.recipient_user_id == current_user.id and not m.is_read:
            m.is_read = True
            has_unread = True
    if has_unread:
        db.commit()

    return [_format_message(m, current_user.id) for m in messages]


# ==============================================================================
# Lawyer Direct Message & Inbox Endpoints
# ==============================================================================

@router.get("/lawyer/messages", response_model=List[LawyerInboxItem])
def get_lawyer_inbox(
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Lawyer inbox: Returns one row per citizen conversation with name, last message,
    last time, and unread count.
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        return []

    # Query all messages for this lawyer profile ordered by newest first
    all_msgs = (
        db.query(DirectMessage)
        .options(joinedload(DirectMessage.sender), joinedload(DirectMessage.recipient))
        .filter(DirectMessage.lawyer_profile_id == profile.id)
        .order_by(DirectMessage.created_at.desc())
        .all()
    )

    conversations = {}
    for msg in all_msgs:
        # Determine the citizen user ID
        citizen_id = msg.sender_user_id if msg.sender_user_id != current_user.id else msg.recipient_user_id
        if not citizen_id:
            continue

        cid_str = str(citizen_id)
        if cid_str not in conversations:
            # Resolve citizen name
            citizen_user = msg.sender if msg.sender_user_id == citizen_id else msg.recipient
            if not citizen_user:
                citizen_user = db.query(User).filter(User.id == citizen_id).first()

            name = citizen_user.full_name if citizen_user else "Citizen"
            created_at_str = msg.created_at.isoformat() if hasattr(msg.created_at, "isoformat") else str(msg.created_at)

            conversations[cid_str] = {
                "user_id": cid_str,
                "name": name,
                "last_message": msg.content,
                "last_time": created_at_str,
                "unread_count": 0,
            }

        # If incoming from citizen and unread, increment count
        if msg.sender_user_id == citizen_id and not msg.is_read:
            conversations[cid_str]["unread_count"] += 1

    return list(conversations.values())


@router.get("/lawyer/messages/{user_id}", response_model=List[DirectMessageResponse])
def get_lawyer_thread_with_user(
    user_id: str,
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Lawyer retrieves thread with a specific citizen; marks incoming messages as is_read=True.
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found",
        )

    target_uuid = _parse_uuid(user_id, "Citizen user")

    messages = (
        db.query(DirectMessage)
        .options(joinedload(DirectMessage.sender), joinedload(DirectMessage.lawyer_profile))
        .filter(
            DirectMessage.lawyer_profile_id == profile.id,
            or_(
                DirectMessage.sender_user_id == target_uuid,
                DirectMessage.recipient_user_id == target_uuid,
            ),
        )
        .order_by(DirectMessage.created_at.asc())
        .all()
    )

    # Mark incoming messages from citizen as read
    has_unread = False
    for m in messages:
        if m.sender_user_id == target_uuid and not m.is_read:
            m.is_read = True
            has_unread = True
    if has_unread:
        db.commit()

    return [_format_message(m, current_user.id) for m in messages]


@router.post("/lawyer/messages/{user_id}", response_model=DirectMessageResponse, status_code=status.HTTP_201_CREATED)
def reply_to_citizen(
    user_id: str,
    payload: DirectMessageCreate,
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Lawyer replies to a citizen's direct message.
    """
    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found",
        )

    target_uuid = _parse_uuid(user_id, "Citizen user")
    citizen = db.query(User).filter(User.id == target_uuid).first()
    if not citizen:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Citizen user not found",
        )

    reply_message = DirectMessage(
        id=uuid.uuid4(),
        sender_user_id=current_user.id,
        lawyer_profile_id=profile.id,
        recipient_user_id=target_uuid,
        content=payload.content.strip(),
        is_read=False,
        created_at=datetime.utcnow(),
    )
    db.add(reply_message)
    db.commit()
    db.refresh(reply_message)

    return _format_message(reply_message, current_user.id)
