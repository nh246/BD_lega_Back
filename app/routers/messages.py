"""
Direct messaging router: Pro-only messaging channel between citizens and approved lawyers.
Endpoints under prefix "/api/messages".
"""

from datetime import datetime
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.core.plans import get_user_plan
from app.models import DirectMessage, LawyerProfile, User

router = APIRouter(prefix="/api/messages", tags=["Messages"])
compat_router = APIRouter(prefix="/api/lawyer", tags=["LawyerMessagesCompat"])


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1)


def _parse_uuid(id_str: str, entity_name: str = "Resource") -> uuid.UUID:
    """Helper to safely parse UUID strings, raising 404 on malformed values."""
    try:
        return uuid.UUID(str(id_str))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_name} not found",
        )


def _serialize_message(m: DirectMessage) -> dict:
    created_at_val = (
        m.created_at.isoformat()
        if hasattr(m.created_at, "isoformat")
        else str(m.created_at)
    )
    return {
        "id": str(m.id),
        "sender_user_id": str(m.sender_user_id),
        "lawyer_profile_id": str(m.lawyer_profile_id),
        "recipient_user_id": str(m.recipient_user_id) if m.recipient_user_id else None,
        "content": m.content,
        "is_read": bool(m.is_read),
        "created_at": created_at_val,
    }


def _is_unread(msg: DirectMessage) -> bool:
    return not bool(msg.is_read)


# ==============================================================================
# Lawyer Direct Message & Inbox Endpoints (prefix: /api/messages)
# NOTE: Static route /lawyer/inbox MUST be defined before /lawyer/{lawyer_id}
# ==============================================================================

@router.get("/lawyer/inbox")
def get_lawyer_inbox(
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Lawyer inbox: Return one row per citizen who has messaged this lawyer:
    - user_id, full_name (joined from users table)
    - last_message (content of most recent message in thread)
    - last_time (created_at of most recent message)
    - unread_count (count of messages where sender_user_id != lawyer.user_id and is_read == false)
    Ordered by last_time descending.
    """
    profile = (
        db.query(LawyerProfile)
        .filter(LawyerProfile.user_id == current_user.id)
        .first()
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found",
        )

    all_msgs = (
        db.query(DirectMessage)
        .filter(DirectMessage.lawyer_profile_id == profile.id)
        .order_by(DirectMessage.created_at.desc())
        .all()
    )

    threads = {}
    for msg in all_msgs:
        citizen_id = (
            msg.sender_user_id
            if msg.sender_user_id != current_user.id
            else msg.recipient_user_id
        )
        if not citizen_id:
            continue

        cid_str = str(citizen_id)
        if cid_str not in threads:
            citizen = db.query(User).filter(User.id == citizen_id).first()
            full_name = citizen.full_name if citizen else "Citizen"
            created_at_str = (
                msg.created_at.isoformat()
                if hasattr(msg.created_at, "isoformat")
                else str(msg.created_at)
            )
            threads[cid_str] = {
                "user_id": cid_str,
                "full_name": full_name,
                "name": full_name,
                "last_message": msg.content,
                "last_time": created_at_str,
                "unread_count": 0,
                "_raw_time": msg.created_at,
            }

        if msg.sender_user_id != current_user.id and _is_unread(msg):
            threads[cid_str]["unread_count"] += 1

    sorted_threads = sorted(
        threads.values(),
        key=lambda x: x["_raw_time"],
        reverse=True,
    )
    for t in sorted_threads:
        t.pop("_raw_time", None)

    return sorted_threads


@router.get("/lawyer/thread/{user_id}")
def get_lawyer_thread(
    user_id: str,
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Lawyer thread: Load lawyer profile and return all messages between that citizen
    and this lawyer, ordered by created_at.
    Marks incoming messages (sender_user_id == user_id) as is_read=true.
    """
    profile = (
        db.query(LawyerProfile)
        .filter(LawyerProfile.user_id == current_user.id)
        .first()
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found",
        )

    target_uuid = _parse_uuid(user_id, "Citizen user")

    messages = (
        db.query(DirectMessage)
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

    has_unread = False
    for m in messages:
        if m.sender_user_id == target_uuid and not m.is_read:
            m.is_read = True
            has_unread = True
    if has_unread:
        db.commit()

    return [_serialize_message(m) for m in messages]


@router.post("/lawyer/reply/{user_id}", status_code=status.HTTP_201_CREATED)
def reply_to_citizen(
    user_id: str,
    payload: MessageCreate,
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    """
    Lawyer replies to a citizen's message:
    Creates DirectMessage(sender_user_id=lawyer.user_id, lawyer_profile_id=lawyer.id, content=...).
    Returns 201 with message details.
    """
    profile = (
        db.query(LawyerProfile)
        .filter(LawyerProfile.user_id == current_user.id)
        .first()
    )
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

    content_text = payload.content.strip()
    if not content_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message content cannot be empty",
        )

    reply_msg = DirectMessage(
        id=uuid.uuid4(),
        sender_user_id=current_user.id,
        lawyer_profile_id=profile.id,
        recipient_user_id=citizen.id,
        content=content_text,
        is_read=False,
        created_at=datetime.utcnow(),
    )
    db.add(reply_msg)
    db.commit()
    db.refresh(reply_msg)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=_serialize_message(reply_msg),
    )


# ==============================================================================
# Citizen / User Direct Message Endpoints (prefix: /api/messages)
# ==============================================================================

@router.post("/lawyer/{lawyer_id}", status_code=status.HTTP_201_CREATED)
def send_message_to_lawyer(
    lawyer_id: str,
    payload: MessageCreate,
    current_user: User = Depends(require_role("user")),
    db: Session = Depends(get_db),
):
    """
    Citizen sends a direct message to an approved lawyer.
    Requires user_pro plan. Free plan users receive 402 with pro_required.
    """
    plan = get_user_plan(db, current_user)
    if plan == "user_free":
        return JSONResponse(
            status_code=402,
            content={
                "error": "pro_required",
                "message": "Direct messaging with verified lawyers is a Pro feature.",
            },
        )

    lawyer_uuid = _parse_uuid(lawyer_id, "Lawyer profile")
    lawyer = (
        db.query(LawyerProfile)
        .filter(LawyerProfile.id == lawyer_uuid)
        .first()
    )

    if not lawyer or lawyer.verification_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approved lawyer profile not found",
        )

    content_text = payload.content.strip()
    if not content_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message content cannot be empty",
        )

    new_message = DirectMessage(
        id=uuid.uuid4(),
        sender_user_id=current_user.id,
        lawyer_profile_id=lawyer.id,
        recipient_user_id=lawyer.user_id,
        content=content_text,
        is_read=False,
        created_at=datetime.utcnow(),
    )
    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=_serialize_message(new_message),
    )


@router.get("/lawyer/{lawyer_id}")
def get_user_messages_with_lawyer(
    lawyer_id: str,
    current_user: User = Depends(require_role("user")),
    db: Session = Depends(get_db),
):
    """
    Citizen retrieves the conversation thread with a specific lawyer, ordered by created_at.
    Marks incoming messages (sender != current_user) as is_read=true.
    """
    lawyer_uuid = _parse_uuid(lawyer_id, "Lawyer profile")
    lawyer = (
        db.query(LawyerProfile)
        .filter(LawyerProfile.id == lawyer_uuid)
        .first()
    )
    if not lawyer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lawyer profile not found",
        )

    messages = (
        db.query(DirectMessage)
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

    has_unread = False
    for m in messages:
        if m.sender_user_id != current_user.id and not m.is_read:
            m.is_read = True
            has_unread = True
    if has_unread:
        db.commit()

    return [_serialize_message(m) for m in messages]


# ==============================================================================
# Compatibility Endpoints for Lawyer Dashboard (/api/lawyer/messages)
# ==============================================================================

@compat_router.get("/messages")
def compat_lawyer_inbox(
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    return get_lawyer_inbox(current_user=current_user, db=db)


@compat_router.get("/messages/{user_id}")
def compat_lawyer_thread(
    user_id: str,
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    return get_lawyer_thread(user_id=user_id, current_user=current_user, db=db)


@compat_router.post("/messages/{user_id}", status_code=status.HTTP_201_CREATED)
def compat_reply_to_citizen(
    user_id: str,
    payload: MessageCreate,
    current_user: User = Depends(require_role("lawyer")),
    db: Session = Depends(get_db),
):
    return reply_to_citizen(user_id=user_id, payload=payload, current_user=current_user, db=db)
