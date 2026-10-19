"""
LLM Configuration router for administrators: view and update active AI model parameters.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.models import LlmConfig, User
from app.schemas import LlmConfigResponse, LlmConfigUpdate
from app.audit import log_audit

router = APIRouter(prefix="/api/admin", tags=["LLM Config"])


@router.get("/llm-config", response_model=LlmConfigResponse)
def get_active_llm_config(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Returns the currently active LLM configuration.
    If none exists, seeds and returns a default active config.
    """
    active_config = (
        db.query(LlmConfig)
        .filter(LlmConfig.is_active == True)  # noqa: E712
        .order_by(LlmConfig.created_at.desc())
        .first()
    )

    if not active_config:
        active_config = LlmConfig(
            provider="gemini",
            model_name="gemini-1.5-flash",
            temperature=0.7,
            max_tokens=2048,
            system_prompt="You are an AI legal assistant specialized in the laws of Bangladesh.",
            disclaimer="This information is for educational purposes and not a substitute for professional legal advice.",
            is_active=True,
        )
        db.add(active_config)
        db.commit()
        db.refresh(active_config)

    return active_config


@router.put("/llm-config", response_model=LlmConfigResponse)
def update_llm_config(
    payload: LlmConfigUpdate,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Deactivates all existing configs, creates/activates the new config,
    and logs an audit trail ('llm_config_updated').
    """
    # Deactivate all current configs
    db.query(LlmConfig).update({LlmConfig.is_active: False})

    new_config = LlmConfig(
        provider=payload.provider,
        model_name=payload.model_name,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        system_prompt=payload.system_prompt,
        disclaimer=payload.disclaimer,
        is_active=payload.is_active,
    )
    db.add(new_config)
    db.commit()
    db.refresh(new_config)

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="llm_config_updated",
        target_type="llm_config",
        target_id=str(new_config.id),
        details={
            "provider": new_config.provider,
            "model_name": new_config.model_name,
            "temperature": new_config.temperature,
            "max_tokens": new_config.max_tokens,
            "is_active": new_config.is_active,
        },
    )

    return new_config
