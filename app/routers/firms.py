"""
Law Firms Router: Admin listing and status verification.
"""

from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_scope
from app.models import LawFirm, User
from app.schemas import FirmResponse, FirmUpdate
from app.audit import log_audit

router = APIRouter(prefix="/api/admin/firms", tags=["Law Firms"])


def _parse_uuid(id_str: str) -> uuid.UUID:
    """Helper to safely parse UUID strings, raising 404 on malformed values."""
    try:
        return uuid.UUID(id_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Law firm not found",
        )


@router.get("", response_model=List[FirmResponse])
@router.get("/", response_model=List[FirmResponse], include_in_schema=False)
def get_law_firms(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by firm status"),
    current_user: User = Depends(require_scope("firms:view")),
    db: Session = Depends(get_db),
):
    """
    List all law firms.
    Requires 'firms:view' scope (or admin role).
    """
    query = db.query(LawFirm)
    if status_filter:
        query = query.filter(LawFirm.status == status_filter.strip())

    firms = query.order_by(LawFirm.created_at.desc()).all()
    return firms


@router.patch("/{firm_id}", response_model=FirmResponse)
def update_firm_status(
    firm_id: str,
    update_data: FirmUpdate,
    current_user: User = Depends(require_scope("firms:verify")),
    db: Session = Depends(get_db),
):
    """
    Updates a law firm's details or verification status.
    Requires 'firms:verify' scope (or admin role).
    Logs an audit trail ('firm_status_updated').
    """
    target_uuid = _parse_uuid(firm_id)
    firm = db.query(LawFirm).filter(LawFirm.id == target_uuid).first()
    if not firm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Law firm not found",
        )

    old_status = firm.status

    if update_data.name is not None:
        firm.name = update_data.name.strip()
    if update_data.contact_person is not None:
        firm.contact_person = update_data.contact_person.strip()
    if update_data.phone is not None:
        firm.phone = update_data.phone.strip()
    if update_data.address is not None:
        firm.address = update_data.address.strip()
    if update_data.status is not None:
        firm.status = update_data.status.strip()

    if old_status != firm.status:
        log_audit(
            db=db,
            actor_id=current_user.id,
            action="firm_status_updated",
            target_type="law_firm",
            target_id=str(firm.id),
            details={
                "old_status": old_status,
                "new_status": firm.status,
                "firm_name": firm.name,
            },
        )

    db.commit()
    db.refresh(firm)
    return firm
