"""
Direct messaging router: Pro-only messaging channel between citizens and approved lawyers.
Endpoints under prefix "/api/messages".
"""

from datetime import datetime
from typing import List, Optional, Union
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.core.plans import get_user_plan, is_pro_plan
from app.models import DirectMessage, LawyerProfile, User, Booking, ProfileAsset
from app.services.notifications import trigger_notification

router = APIRouter(prefix="/api/messages", tags=["Messages"])
compat_router = APIRouter(prefix="/api/lawyer", tags=["LawyerMessagesCompat"])


class MessageCreate(BaseModel):
    content: Optional[str] = ""
    attachment_asset_ids: Optional[List[Union[uuid.UUID, str]]] = Field(default=None)


def _parse_uuid(id_str: str, entity_name: str = "Resource") -> uuid.UUID:
    """Helper to safely parse UUID strings, raising 404 on malformed values."""
    try:
        return uuid.UUID(str(id_str))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_name} not found",
        )


def _validate_and_extract_attachments(
    payload: MessageCreate,
    current_user: User,
    db: Session,
) -> List[str]:
    attachment_ids = []
    if payload.attachment_asset_ids is not None:
        if len(payload.attachment_asset_ids) > 4:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 4 attachments allowed per message",
            )
        for raw_id in payload.attachment_asset_ids:
            try:
                aid = uuid.UUID(str(raw_id))
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid asset ID format: {raw_id}",
                )

            asset = db.query(ProfileAsset).filter(ProfileAsset.id == aid).first()
            if not asset:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Asset {raw_id} not found",
                )
            if asset.owner_user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Asset {raw_id} is not owned by the sender",
                )
            if asset.kind not in ("text", "image", "payment_screenshot"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Asset {raw_id} kind '{asset.kind}' is not allowed as an attachment. Must be text, image, or payment_screenshot.",
                )
            attachment_ids.append(str(aid))
    return attachment_ids


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
        "attachments": [str(a) for a in (m.attachments or [])],
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
    - Query Booking where lawyer_profile_id == current_lawyer.id and user_id == user_id.
    - If no booking OR booking.status != "confirmed": return 403 {"error":"no_active_booking","message":"No active consultation with this client."}
    - If status == "completed": return 403 {"error":"booking_completed","message":"This consultation is completed. Thread is read-only."}
    - Supports up to 4 attachments.
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

    # Query bookings between current lawyer and citizen
    bookings = (
        db.query(Booking)
        .filter(
            Booking.lawyer_id == profile.id,
            Booking.user_id == citizen.id,
        )
        .order_by(Booking.created_at.desc())
        .all()
    )

    has_confirmed = any(b.status == "confirmed" for b in bookings)
    has_completed = any(b.status == "completed" for b in bookings)

    if not has_confirmed:
        if has_completed:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": "booking_completed",
                    "message": "This consultation is completed. Thread is read-only.",
                },
            )
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": "no_active_booking",
                "message": "No active consultation with this client.",
            },
        )

    attachment_ids = _validate_and_extract_attachments(payload, current_user, db)

    content_text = (payload.content or "").strip()
    if not content_text and not attachment_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message content cannot be empty",
        )

    reply_msg = DirectMessage(
        id=uuid.uuid4(),
        sender_user_id=current_user.id,
        lawyer_profile_id=profile.id,
        recipient_user_id=citizen.id,
        content=content_text or "(Attachment)",
        attachments=attachment_ids,
        is_read=False,
        created_at=datetime.utcnow(),
    )
    db.add(reply_msg)
    db.commit()
    db.refresh(reply_msg)

    sender_name = current_user.full_name or "Advocate"
    try:
        trigger_notification(
            db=db,
            user_id=citizen.id,
            type="new_message",
            title="New Message",
            message=f"{sender_name} sent you a message.",
            link="/client/bookings",
        )
    except Exception:
        pass

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
    Citizen sends a direct message to an approved lawyer:
    - Pro users can message any verified lawyer without booking.
    - Free users can only message lawyers with a confirmed booking.
    - If consultation is completed, thread is read-only -> 403 {"error":"booking_completed", ...}.
    - If no booking exists: return 403 {"error":"no_booking", ...}.
    - Supports up to 4 attachments.
    """
    lawyer_uuid = _parse_uuid(lawyer_id, "Lawyer profile")
    lawyer = (
        db.query(LawyerProfile)
        .filter(or_(LawyerProfile.id == lawyer_uuid, LawyerProfile.user_id == lawyer_uuid))
        .first()
    )

    if not lawyer or lawyer.verification_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approved lawyer profile not found",
        )

    plan = get_user_plan(db, current_user)
    is_pro = is_pro_plan(plan) or plan == "user_pro"

    # Query bookings between current_user and lawyer
    bookings = (
        db.query(Booking)
        .filter(
            Booking.user_id == current_user.id,
            Booking.lawyer_id == lawyer.id,
        )
        .order_by(Booking.created_at.desc())
        .all()
    )
    has_confirmed = any(b.status == "confirmed" for b in bookings)
    has_completed = any(b.status == "completed" for b in bookings)

    if not is_pro:
        # Free user
        if not has_confirmed:
            if has_completed:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "error": "booking_completed",
                        "message": "This consultation is completed. Thread is read-only.",
                    },
                )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": "no_booking",
                    "message": "You can only message lawyers you have a confirmed booking with. Upgrade to Pro for direct access.",
                },
            )

    attachment_ids = _validate_and_extract_attachments(payload, current_user, db)

    content_text = (payload.content or "").strip()
    if not content_text and not attachment_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message content cannot be empty",
        )

    new_message = DirectMessage(
        id=uuid.uuid4(),
        sender_user_id=current_user.id,
        lawyer_profile_id=lawyer.id,
        recipient_user_id=lawyer.user_id,
        content=content_text or "(Attachment)",
        attachments=attachment_ids,
        is_read=False,
        created_at=datetime.utcnow(),
    )
    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    sender_name = current_user.full_name or "Client"
    try:
        trigger_notification(
            db=db,
            user_id=lawyer.user_id,
            type="new_message",
            title="New Message",
            message=f"{sender_name} sent you a message.",
            link="/lawyer/inbox",
        )
    except Exception:
        pass

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
