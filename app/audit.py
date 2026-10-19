"""
Audit logging helper for BD Legal Guide AI.
"""

from typing import Any, Optional
from sqlalchemy.orm import Session
from app.models import AuditLog


def log_audit(
    db: Session,
    actor_id: Any,
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[Any] = None,
    details: Optional[dict] = None,
) -> AuditLog:
    """
    Inserts a row into audit_logs and commits the transaction.
    Returns the created AuditLog record.
    """
    audit_entry = AuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=details,
    )
    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)
    return audit_entry
