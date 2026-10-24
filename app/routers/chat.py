"""
Chat router: AI legal consultation sessions and messaging.
Connects with active LLM configuration or mock fallback.
"""

from datetime import datetime, timezone
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.plans import get_user_plan
from app.models import ChatMessage, ChatSession, MonthlyUsage, Document, LlmConfig, User
from app.schemas import (
    ChatMessageCreate,
    ChatMessageResponse,
    ChatResponse,
    ChatSessionResponse,
)
from app.services.llm.base import generate_response, self_evaluate

router = APIRouter(prefix="/api", tags=["Chat"])


class ChatMessagePayload(ChatMessageCreate):
    document_id: Optional[str] = None
    attachment_ids: List[str] = []


def _parse_uuid(id_str: str, entity_name: str = "Resource") -> uuid.UUID:
    """Helper to safely parse UUID strings, raising 404 on malformed values."""
    try:
        return uuid.UUID(id_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_name} not found",
        )


@router.post("/chat", response_model=ChatResponse)
def send_chat_message(
    payload: ChatMessagePayload,
    current_user: User = Depends(require_role("user", "lawyer", "admin")),
    db: Session = Depends(get_db),
):
    """
    Sends a chat message to the legal AI assistant.
    - If current_user.status == 'restricted', returns 403 'Chat access restricted'.
    - Uses active LlmConfig from database, or defaults to mock fallback.
    - Preserves up to 5 prior messages for conversation context if session_id is provided.
    - Saves user and assistant messages in chat_messages table.
    - Returns 502 with {"error": "AI service temporarily unavailable. Please try again."} on LLM failure.
    """
    # CRITICAL: Restricted status check
    if current_user.status == "restricted":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chat access restricted",
        )

    plan = get_user_plan(db, current_user)

    # Consolidate attachment_ids and legacy document_id
    all_attachment_ids = list(payload.attachment_ids or [])
    if payload.document_id and payload.document_id not in all_attachment_ids:
        all_attachment_ids.append(payload.document_id)

    if len(all_attachment_ids) > 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum of 4 attachments allowed per message.",
        )

    attached_docs = []
    if all_attachment_ids:
        for att_id in all_attachment_ids:
            try:
                d_uuid = uuid.UUID(att_id)
                d = db.query(Document).filter(Document.id == d_uuid).first()
            except (ValueError, TypeError):
                d = None

            if not d or d.owner_user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found",
                )
            attached_docs.append(d)

        if plan == "user_free":
            return JSONResponse(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                content={
                    "error": "pro_required",
                    "message": "Document reference and image analysis is a Pro feature. Upgrade to Pro to use attachments.",
                },
            )

    text_docs = [d for d in attached_docs if d.kind == "text" or not d.kind]
    image_docs = [d for d in attached_docs if d.kind == "image"]

    image_parts = []
    for img in image_docs:
        if img.file_bytes and img.mime_type:
            image_parts.append({
                "mime_type": img.mime_type,
                "data": bytes(img.file_bytes),
            })

    now_utc = datetime.now(timezone.utc)
    current_year = now_utc.year
    current_month = now_utc.month

    monthly_row = (
        db.query(MonthlyUsage)
        .filter(
            MonthlyUsage.user_id == current_user.id,
            MonthlyUsage.year == current_year,
            MonthlyUsage.month == current_month,
        )
        .first()
    )
    if not monthly_row:
        monthly_row = MonthlyUsage(
            user_id=current_user.id,
            year=current_year,
            month=current_month,
            messages_used=0,
        )
        db.add(monthly_row)
        try:
            db.commit()
            db.refresh(monthly_row)
        except Exception:
            db.rollback()
            monthly_row = (
                db.query(MonthlyUsage)
                .filter(
                    MonthlyUsage.user_id == current_user.id,
                    MonthlyUsage.year == current_year,
                    MonthlyUsage.month == current_month,
                )
                .first()
            )

    if plan == "user_free":
        if monthly_row and monthly_row.messages_used >= 15:
            return JSONResponse(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                content={
                    "error": "free_limit",
                    "message": "Monthly free limit reached (15 messages). Upgrade to Pro.",
                },
            )
        k = 3
    else:
        k = 20

    # Fetch active LlmConfig from DB
    config = (
        db.query(LlmConfig)
        .filter(LlmConfig.is_active == True)  # noqa: E712
        .order_by(LlmConfig.created_at.desc())
        .first()
    )

    if config:
        provider = config.provider
        model = config.model_name
        temp = config.temperature
        max_tokens = config.max_tokens
        system_prompt = config.system_prompt or "You are an AI legal assistant specialized in the laws of Bangladesh."
        disclaimer = config.disclaimer or "This information is for educational purposes and not a substitute for professional legal advice."
    else:
        provider = "mock"
        model = "mock-model"
        temp = 0.7
        max_tokens = 2048
        system_prompt = "You are an AI legal assistant specialized in the laws of Bangladesh."
        disclaimer = "This information is for educational purposes and not a substitute for professional legal advice."

    # Check vision support for image attachments
    if image_parts and provider != "gemini":
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "vision_unsupported",
                "message": "Image analysis requires the Gemini provider. Ask the admin to switch model provider.",
            },
        )

    # Session handling
    session = None
    history = []

    if payload.session_id:
        try:
            s_uuid = uuid.UUID(payload.session_id)
            session = (
                db.query(ChatSession)
                .filter(ChatSession.id == s_uuid, ChatSession.user_id == current_user.id)
                .first()
            )
        except (ValueError, TypeError):
            session = None

        if session:
            recent_msgs = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_id == session.id)
                .order_by(ChatMessage.created_at.desc())
                .limit(k)
                .all()
            )
            recent_msgs.reverse()
            history = [{"role": m.role, "content": m.content} for m in recent_msgs]

    if not session:
        session = ChatSession(user_id=current_user.id)
        db.add(session)
        db.commit()
        db.refresh(session)

    # Build messages list
    combined_system = f"{system_prompt}\n\n{disclaimer}".strip()
    messages_list = [{"role": "system", "content": combined_system}]
    if text_docs:
        excerpts = []
        for td in text_docs:
            if td.extracted_text:
                excerpts.append(f"Document '{td.filename}' (excerpt):\n{td.extracted_text[:6000]}")
        if excerpts:
            combined_excerpt = "\n\n".join(excerpts)
            messages_list.append(
                {
                    "role": "system",
                    "content": f"Reference document (excerpt):\n{combined_excerpt}\n\nUse this document when answering the user's question.",
                }
            )
    messages_list.extend(history)
    messages_list.append({"role": "user", "content": payload.content})

    # Call generate_response
    try:
        reply_text = generate_response(
            provider=provider,
            model=model,
            messages=messages_list,
            temp=temp,
            max_tokens=max_tokens,
            images=image_parts,
        )
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "error": "AI service temporarily unavailable. Please try again.",
                "detail": "AI service temporarily unavailable. Please try again.",
            },
        )

    # Self-evaluate confidence for Pro plans
    confidence = None
    reason = None
    if plan != "user_free":
        try:
            eval_res = self_evaluate(
                provider=provider,
                model=model,
                question=payload.content,
                answer=reply_text,
                temp=0.2,
            )
            if eval_res and isinstance(eval_res, dict):
                raw_conf = eval_res.get("confidence")
                if raw_conf is not None:
                    confidence = max(0, min(100, int(raw_conf)))
                reason = eval_res.get("reason")
        except Exception:
            confidence = None
            reason = None

    # Save user message and assistant message
    user_msg = ChatMessage(
        session_id=session.id,
        role="user",
        content=payload.content,
        provider=provider,
        model=model,
    )
    assistant_msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=reply_text,
        provider=provider,
        model=model,
        confidence_score=confidence,
        confidence_reason=reason,
    )
    db.add(user_msg)
    db.add(assistant_msg)
    if monthly_row:
        monthly_row.messages_used += 1
    db.commit()
    db.refresh(assistant_msg)

    return ChatResponse(
        reply=reply_text,
        provider=provider,
        model=model,
        disclaimer=disclaimer,
        session_id=str(session.id),
        id=str(assistant_msg.id),
        content=reply_text,
        response=reply_text,
        message=reply_text,
        confidence=confidence,
        confidence_reason=reason,
        context_window=k,
    )


@router.get("/chat/sessions", response_model=List[ChatSessionResponse])
def get_user_chat_sessions(
    current_user: User = Depends(require_role("user", "lawyer", "admin")),
    db: Session = Depends(get_db),
):
    """
    Returns list of the authenticated user's chat sessions.
    """
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.created_at.desc())
        .all()
    )

    results = []
    for s in sessions:
        first_msg = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == s.id, ChatMessage.role == "user")
            .order_by(ChatMessage.created_at.asc())
            .first()
        )
        if first_msg and first_msg.content:
            title = (first_msg.content[:40] + "...") if len(first_msg.content) > 40 else first_msg.content
        else:
            title = "Legal Consultation"

        results.append(
            ChatSessionResponse(
                id=str(s.id),
                user_id=str(s.user_id),
                title=title,
                created_at=s.created_at.isoformat() if hasattr(s.created_at, "isoformat") else str(s.created_at),
            )
        )
    return results


@router.get("/chat/sessions/{session_id}", response_model=List[ChatMessageResponse])
def get_chat_session_messages(
    session_id: str,
    current_user: User = Depends(require_role("user", "lawyer", "admin")),
    db: Session = Depends(get_db),
):
    """
    Returns messages for a specific session.
    """
    s_uuid = _parse_uuid(session_id, "Chat session")
    session = db.query(ChatSession).filter(ChatSession.id == s_uuid).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )

    # Permission check: owner or staff
    if session.user_id != current_user.id and current_user.role not in ["admin", "moderator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this chat session",
        )

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return messages


@router.get("/chat/usage")
def get_chat_usage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns current plan usage statistics for the authenticated user.
    """
    plan = get_user_plan(db, current_user)
    is_free = (plan == "user_free")

    now_utc = datetime.now(timezone.utc)
    current_year = now_utc.year
    current_month = now_utc.month

    monthly_row = (
        db.query(MonthlyUsage)
        .filter(
            MonthlyUsage.user_id == current_user.id,
            MonthlyUsage.year == current_year,
            MonthlyUsage.month == current_month,
        )
        .first()
    )
    messages_this_month = monthly_row.messages_used if monthly_row else 0

    sessions_used = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id)
        .count()
    )

    monthly_limit = 15 if is_free else None
    context_window = 3 if is_free else 20

    return {
        "plan": plan,
        "messages_this_month": messages_this_month,
        "monthly_limit": monthly_limit,
        "limit": monthly_limit,
        "context_window": context_window,
        "messages_today": messages_this_month,
        "daily_limit": monthly_limit,
        "sessions_used": sessions_used,
        "session_limit": None,
    }


@router.delete("/chat/sessions/{session_id}")
def delete_chat_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Deletes a chat session and all its messages.
    Auth required. If session not found or not owned by user -> 404.
    """
    try:
        s_uuid = uuid.UUID(session_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == s_uuid)
        .first()
    )
    if not session or session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    db.query(ChatMessage).filter(ChatMessage.session_id == session.id).delete(synchronize_session=False)
    db.delete(session)
    db.commit()

    return {"deleted": True}
