"""
Chat router: AI legal consultation sessions and messaging.
Connects with active LLM configuration or mock fallback.
"""

from typing import List
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.models import ChatMessage, ChatSession, LlmConfig, User
from app.schemas import (
    ChatMessageCreate,
    ChatMessageResponse,
    ChatResponse,
    ChatSessionResponse,
)
from app.services.llm.base import generate_response

router = APIRouter(prefix="/api", tags=["Chat"])


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
    payload: ChatMessageCreate,
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
                .limit(5)
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
        )
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "error": "AI service temporarily unavailable. Please try again.",
                "detail": "AI service temporarily unavailable. Please try again.",
            },
        )

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
    )
    db.add(user_msg)
    db.add(assistant_msg)
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
