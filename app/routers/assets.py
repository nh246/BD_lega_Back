"""
Assets router: Profile avatars and verification documents.
Provides endpoints for uploading, listing, streaming, and deleting profile assets.
"""

import io
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, get_optional_current_user
from app.models import Booking, CaseBid, CasePost, DirectMessage, LawyerProfile, ProfileAsset, User
from sqlalchemy import cast, String

router = APIRouter(tags=["Assets"])

AVATAR_ALLOWED_EXTS = {"png", "jpg", "jpeg", "webp"}
AVATAR_MIMES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}

VERIFICATION_ALLOWED_EXTS = {"pdf", "png", "jpg", "jpeg"}
VERIFICATION_MIMES = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}

PAYMENT_SCREENSHOT_ALLOWED_EXTS = {"png", "jpg", "jpeg", "webp"}
PAYMENT_SCREENSHOT_MIMES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}

ATTACHMENT_TEXT_EXTS = {"pdf", "txt", "doc", "docx"}
ATTACHMENT_TEXT_MIMES = {
    "pdf": "application/pdf",
    "txt": "text/plain",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

ATTACHMENT_IMAGE_EXTS = {"png", "jpg", "jpeg", "webp"}
ATTACHMENT_IMAGE_MIMES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


def _check_verification_access(
    db: Session,
    owner_user_id: uuid.UUID,
    requester: Optional[User],
) -> bool:
    """
    Verification rows are accessible if:
    1. Owner has an approved lawyer_profile (publicly accessible).
    2. Requester is the owner.
    3. Requester is an admin or moderator.
    """
    # 1. Owner has approved lawyer profile
    lawyer = (
        db.query(LawyerProfile)
        .filter(
            LawyerProfile.user_id == owner_user_id,
            LawyerProfile.verification_status == "approved",
        )
        .first()
    )
    if lawyer:
        return True

    # 2. Requester is owner
    if requester and requester.id == owner_user_id:
        return True

    # 3. Requester is admin or moderator
    if requester and requester.role in ("admin", "moderator"):
        return True

    return False


@router.post("/api/profile/assets", status_code=status.HTTP_201_CREATED)
@router.post("/api/profile/assets/", status_code=status.HTTP_201_CREATED)
async def upload_profile_asset(
    kind: str = Form(...),
    file: UploadFile = File(...),
    slot: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload a profile asset (kind: 'avatar', 'verification', or 'payment_screenshot').
    - 'avatar': images only (png/jpg/jpeg/webp), max 1 MB. Replaces previous avatar.
    - 'verification': pdf/png/jpg/jpeg, max 2 MB. Max 3 verification docs per user.
    - 'payment_screenshot': images only (png/jpg/jpeg/webp), max 2 MB. No count limit.
    - 'slot': Optional slot name for verification docs ('nid', 'bar_council_cert', 'practicing_license').
    """
    if kind not in ("avatar", "verification", "payment_screenshot", "text", "image"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid asset kind. Must be 'avatar', 'verification', 'payment_screenshot', 'text', or 'image'.",
        )

    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided.",
        )

    filename = file.filename
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content_type = (file.content_type or "").lower()

    if kind == "avatar":
        if ext not in AVATAR_ALLOWED_EXTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file type for avatar. Allowed types: png, jpg, jpeg, webp.",
            )
        if (
            content_type
            and content_type != "application/octet-stream"
            and not (content_type.startswith("image/") or content_type in AVATAR_MIMES.values())
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid MIME type for avatar. Must be an image.",
            )

        content_bytes = await file.read()
        if len(content_bytes) > 1 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Avatar exceeds maximum limit of 1 MB.",
            )

        mime_type = AVATAR_MIMES.get(ext) or content_type or "image/png"

        # Delete any existing avatar row of this user first (replace)
        db.query(ProfileAsset).filter(
            ProfileAsset.owner_user_id == current_user.id,
            ProfileAsset.kind == "avatar",
        ).delete()
        db.commit()

    elif kind == "payment_screenshot":
        if ext not in PAYMENT_SCREENSHOT_ALLOWED_EXTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file type for payment screenshot. Allowed types: png, jpg, jpeg, webp.",
            )
        if (
            content_type
            and content_type != "application/octet-stream"
            and not (content_type.startswith("image/") or content_type in PAYMENT_SCREENSHOT_MIMES.values())
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid MIME type for payment screenshot. Must be an image.",
            )

        content_bytes = await file.read()
        if len(content_bytes) > 2 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment screenshot exceeds maximum limit of 2 MB.",
            )

        mime_type = PAYMENT_SCREENSHOT_MIMES.get(ext) or content_type or "image/png"

    elif kind == "text":
        if ext not in ATTACHMENT_TEXT_EXTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type for text attachment. Allowed: {', '.join(sorted(ATTACHMENT_TEXT_EXTS))}",
            )
        content_bytes = await file.read()
        if len(content_bytes) > 2 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Attachment exceeds maximum limit of 2 MB.",
            )
        mime_type = ATTACHMENT_TEXT_MIMES.get(ext) or content_type or "text/plain"

    elif kind == "image":
        if ext not in ATTACHMENT_IMAGE_EXTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type for image attachment. Allowed: {', '.join(sorted(ATTACHMENT_IMAGE_EXTS))}",
            )
        content_bytes = await file.read()
        if len(content_bytes) > 2 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Attachment exceeds maximum limit of 2 MB.",
            )
        mime_type = ATTACHMENT_IMAGE_MIMES.get(ext) or content_type or "image/png"

    else:  # kind == "verification"
        if ext not in VERIFICATION_ALLOWED_EXTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file type for verification. Allowed types: pdf, png, jpg, jpeg.",
            )
        if (
            content_type
            and content_type != "application/octet-stream"
            and content_type != "application/pdf"
            and not (content_type.startswith("image/") or content_type in VERIFICATION_MIMES.values())
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid MIME type for verification document.",
            )

        # Slot-based replacement for lawyers
        clean_slot = slot.strip().lower() if slot else None
        lawyer_prof = None
        if current_user.role == "lawyer":
            lawyer_prof = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
            if lawyer_prof and clean_slot in ("nid", "bar_council_cert", "practicing_license"):
                current_checklist = dict(lawyer_prof.verification_checklist or {})
                old_asset_id = current_checklist.get(clean_slot)
                if old_asset_id:
                    try:
                        old_aid = uuid.UUID(str(old_asset_id))
                        db.query(ProfileAsset).filter(
                            ProfileAsset.id == old_aid,
                            ProfileAsset.owner_user_id == current_user.id,
                        ).delete()
                        db.commit()
                    except Exception:
                        pass

        # Max 3 verification rows per user, else 400 {"error":"limit","message":"Maximum 3 verification documents."}
        verif_count = (
            db.query(ProfileAsset)
            .filter(
                ProfileAsset.owner_user_id == current_user.id,
                ProfileAsset.kind == "verification",
            )
            .count()
        )
        if verif_count >= 3:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": "limit",
                    "message": "Maximum 3 verification documents.",
                },
            )

        content_bytes = await file.read()
        if len(content_bytes) > 2 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification document exceeds maximum limit of 2 MB.",
            )

        mime_type = VERIFICATION_MIMES.get(ext) or content_type or "application/octet-stream"

    asset = ProfileAsset(
        owner_user_id=current_user.id,
        kind=kind,
        filename=filename,
        mime_type=mime_type,
        file_bytes=content_bytes,
        size_bytes=len(content_bytes),
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    if kind == "verification" and current_user.role == "lawyer":
        lawyer_prof = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
        if lawyer_prof:
            clean_slot = slot.strip().lower() if slot else None
            checklist = dict(lawyer_prof.verification_checklist or {})
            if clean_slot in ("nid", "bar_council_cert", "practicing_license"):
                checklist[clean_slot] = str(asset.id)
            else:
                # If no slot provided, fill first empty slot
                for s in ("nid", "bar_council_cert", "practicing_license"):
                    if not checklist.get(s):
                        checklist[s] = str(asset.id)
                        clean_slot = s
                        break
            lawyer_prof.verification_checklist = checklist
            db.commit()
            db.refresh(lawyer_prof)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "id": str(asset.id),
            "kind": asset.kind,
            "filename": asset.filename,
            "mime_type": asset.mime_type,
            "size_bytes": asset.size_bytes,
            "slot": slot,
            "checklist": lawyer_prof.verification_checklist if (kind == "verification" and lawyer_prof) else None,
        },
    )


@router.get("/api/profile/assets")
@router.get("/api/profile/assets/")
def get_own_assets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get current user's own profile assets (metadata only, no file bytes).
    """
    assets = (
        db.query(ProfileAsset)
        .filter(ProfileAsset.owner_user_id == current_user.id)
        .order_by(ProfileAsset.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(a.id),
            "kind": a.kind,
            "filename": a.filename,
            "mime_type": a.mime_type,
            "size_bytes": a.size_bytes,
            "created_at": a.created_at.isoformat() if hasattr(a.created_at, "isoformat") else str(a.created_at),
        }
        for a in assets
    ]


@router.get("/api/users/{user_id}/assets")
@router.get("/api/users/{user_id}/assets/")
def get_user_assets(
    user_id: str,
    requester: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Get assets for a user:
    - avatar rows: always included.
    - verification rows: included ONLY IF requester == owner, OR requester is admin/moderator,
      OR owner has an approved lawyer_profile. Otherwise excluded silently.
    """
    try:
        target_uid = uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    target_user = db.query(User).filter(User.id == target_uid).first()
    if not target_user:
        # Fallback: check if target_uid is a lawyer_profile id
        lp = db.query(LawyerProfile).filter(LawyerProfile.id == target_uid).first()
        if lp:
            target_user = db.query(User).filter(User.id == lp.user_id).first()
            if target_user:
                target_uid = target_user.id

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    can_view_verif = _check_verification_access(db, target_uid, requester)

    query = db.query(ProfileAsset).filter(ProfileAsset.owner_user_id == target_uid)
    if not can_view_verif:
        query = query.filter(ProfileAsset.kind == "avatar")

    assets = query.order_by(ProfileAsset.created_at.desc()).all()
    return [
        {
            "id": str(a.id),
            "kind": a.kind,
            "filename": a.filename,
            "mime_type": a.mime_type,
            "size_bytes": a.size_bytes,
            "created_at": a.created_at.isoformat() if hasattr(a.created_at, "isoformat") else str(a.created_at),
        }
        for a in assets
    ]


def _stream_asset(asset: ProfileAsset) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(asset.file_bytes),
        media_type=asset.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{asset.filename}"'
        },
    )


@router.get("/api/assets/{asset_id}/file")
def get_asset_file(
    asset_id: str,
    requester: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Stream asset file contents.
    Visibility permission rules (in order):
    1. Owner of the asset -> allow
    2. admin / moderator -> allow
    3. Asset id present in a CasePost.attachment_asset_ids AND requester is
       the case owner OR a lawyer who has a CaseBid on that case -> allow
    4. Asset id present in any DirectMessage.attachment_asset_ids AND
       requester is a participant of that thread (sender/recipient; for case
       discussion threads: case owner or the bid's lawyer) -> allow
    5. Avatar rows -> allow for authenticated users
    6. Payment screenshots -> allow for assigned booking lawyer
    7. Verification rows -> allow if owner has an approved lawyer profile
    8. else -> 404 (never leak existence)
    Unauthenticated requests are rejected with 401 via get_current_user dependency.
    """
    try:
        aid = uuid.UUID(str(asset_id))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )

    asset = db.query(ProfileAsset).filter(ProfileAsset.id == aid).first()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )

    # 1. Owner of the asset
    if asset.owner_user_id == requester.id:
        return _stream_asset(asset)

    # 2. admin / moderator
    if requester.role in ("admin", "moderator"):
        return _stream_asset(asset)

    aid_str = str(asset.id)

    # 3. Asset id present in CasePost.attachment_asset_ids
    # AND requester is the case owner OR a lawyer who has a CaseBid on that case
    matching_cases = (
        db.query(CasePost)
        .filter(cast(CasePost.attachment_asset_ids, String).like(f"%{aid_str}%"))
        .all()
    )
    for case in matching_cases:
        case_asset_ids = [str(x) for x in (case.attachment_asset_ids or [])]
        if aid_str in case_asset_ids:
            # Case owner
            if case.user_id == requester.id:
                return _stream_asset(asset)

            # Lawyer who has a CaseBid on that case
            if requester.role == "lawyer":
                lawyer_prof = (
                    db.query(LawyerProfile)
                    .filter(LawyerProfile.user_id == requester.id)
                    .first()
                )
                if lawyer_prof:
                    bid = (
                        db.query(CaseBid)
                        .filter(
                            CaseBid.case_id == case.id,
                            CaseBid.lawyer_profile_id == lawyer_prof.id,
                        )
                        .first()
                    )
                    if bid:
                        return _stream_asset(asset)

    # 4. Asset id present in any DirectMessage.attachment_asset_ids (attachments)
    # AND requester is a participant of that thread (sender/recipient; for case discussion threads: case owner or bid's lawyer)
    matching_dms = (
        db.query(DirectMessage)
        .filter(cast(DirectMessage.attachments, String).like(f"%{aid_str}%"))
        .all()
    )
    for dm in matching_dms:
        dm_att_ids = [str(x) for x in (dm.attachments or [])]
        if aid_str in dm_att_ids:
            # Sender or recipient
            if requester.id in (dm.sender_user_id, dm.recipient_user_id):
                return _stream_asset(asset)

            # Lawyer profile of the direct message
            if dm.lawyer_profile_id:
                lp = db.query(LawyerProfile).filter(LawyerProfile.id == dm.lawyer_profile_id).first()
                if lp and lp.user_id == requester.id:
                    return _stream_asset(asset)

            # Case discussion threads: case owner or bid's lawyer
            if dm.case_id:
                case = db.query(CasePost).filter(CasePost.id == dm.case_id).first()
                if case and case.user_id == requester.id:
                    return _stream_asset(asset)

            if dm.bid_id:
                bid = db.query(CaseBid).filter(CaseBid.id == dm.bid_id).first()
                if bid:
                    lp = db.query(LawyerProfile).filter(LawyerProfile.id == bid.lawyer_profile_id).first()
                    if lp and lp.user_id == requester.id:
                        return _stream_asset(asset)

    # 5. Avatar rows are viewable by authenticated users
    if asset.kind == "avatar":
        return _stream_asset(asset)

    # 6. Payment screenshot rows are viewable by the assigned booking lawyer
    if asset.kind == "payment_screenshot" and requester.role == "lawyer":
        lawyer_prof = db.query(LawyerProfile).filter(LawyerProfile.user_id == requester.id).first()
        if lawyer_prof:
            booking = (
                db.query(Booking)
                .filter(
                    Booking.screenshot_asset_id == asset.id,
                    Booking.lawyer_id == lawyer_prof.id,
                )
                .first()
            )
            if booking:
                return _stream_asset(asset)

    # 7. Verification rows are viewable if the lawyer has an approved profile
    if asset.kind == "verification":
        approved_lawyer = (
            db.query(LawyerProfile)
            .filter(
                LawyerProfile.user_id == asset.owner_user_id,
                LawyerProfile.verification_status == "approved",
            )
            .first()
        )
        if approved_lawyer:
            return _stream_asset(asset)

    # 8. Otherwise -> 404 (never leak existence)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Asset not found",
    )


@router.delete("/api/profile/assets/{asset_id}")
def delete_profile_asset(
    asset_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete a profile asset. Only the owner or an admin can delete, else 404.
    """
    try:
        aid = uuid.UUID(str(asset_id))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )

    asset = db.query(ProfileAsset).filter(ProfileAsset.id == aid).first()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )

    if asset.owner_user_id != current_user.id and current_user.role != "admin":
        # Unauthorized -> 404 (do not reveal existence)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )

    if current_user.role == "lawyer":
        lawyer_prof = db.query(LawyerProfile).filter(LawyerProfile.user_id == current_user.id).first()
        if lawyer_prof and lawyer_prof.verification_checklist:
            checklist = dict(lawyer_prof.verification_checklist)
            changed = False
            for k, v in list(checklist.items()):
                if v == str(asset.id):
                    checklist[k] = None
                    changed = True
            if changed:
                lawyer_prof.verification_checklist = checklist

    db.delete(asset)
    db.commit()
    return {"message": "Asset deleted successfully"}
