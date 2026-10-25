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
from app.models import Booking, LawyerProfile, ProfileAsset, User

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload a profile asset (kind: 'avatar', 'verification', or 'payment_screenshot').
    - 'avatar': images only (png/jpg/jpeg/webp), max 1 MB. Replaces previous avatar.
    - 'verification': pdf/png/jpg/jpeg, max 2 MB. Max 3 verification docs per user.
    - 'payment_screenshot': images only (png/jpg/jpeg/webp), max 2 MB. No count limit.
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

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "id": str(asset.id),
            "kind": asset.kind,
            "filename": asset.filename,
            "mime_type": asset.mime_type,
            "size_bytes": asset.size_bytes,
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


@router.get("/api/assets/{asset_id}/file")
def get_asset_file(
    asset_id: str,
    requester: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Stream asset file contents:
    - avatar rows are public.
    - verification rows accessible only if requester == owner, OR requester is admin/moderator,
      OR owner has an approved lawyer_profile. Otherwise return 404 (do not reveal existence).
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

    # Check if this asset is attached to any DirectMessage between user A and lawyer B
    from app.models import DirectMessage
    from sqlalchemy import cast, String

    dm_matches = (
        db.query(DirectMessage)
        .filter(cast(DirectMessage.attachments, String).like(f"%{asset.id}%"))
        .all()
    )

    is_dm_attachment = False
    is_dm_authorized = False

    if dm_matches:
        for dm in dm_matches:
            att_list = dm.attachments or []
            if str(asset.id) in [str(x) for x in att_list]:
                is_dm_attachment = True
                if requester:
                    if requester.role in ["admin", "moderator"]:
                        is_dm_authorized = True
                        break
                    lawyer_user_id = None
                    if dm.lawyer_profile:
                        lawyer_user_id = dm.lawyer_profile.user_id
                    else:
                        lp = db.query(LawyerProfile).filter(LawyerProfile.id == dm.lawyer_profile_id).first()
                        if lp:
                            lawyer_user_id = lp.user_id

                    allowed_users = {dm.sender_user_id, dm.recipient_user_id, lawyer_user_id}
                    allowed_users.discard(None)
                    if requester.id in allowed_users:
                        is_dm_authorized = True
                        break

    if is_dm_attachment:
        if not is_dm_authorized:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found",
            )
    elif asset.kind == "avatar":
        # Avatars are public
        pass
    elif asset.kind == "verification":
        if not _check_verification_access(db, asset.owner_user_id, requester):
            # Violation -> 404 (do not reveal existence)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found",
            )
    elif asset.kind == "payment_screenshot":
        if not requester:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found",
            )
        is_owner = requester.id == asset.owner_user_id
        is_staff = requester.role in ["admin", "moderator"]
        is_assigned_lawyer = False
        if requester.role == "lawyer":
            lawyer_prof = db.query(LawyerProfile).filter(LawyerProfile.user_id == requester.id).first()
            if lawyer_prof:
                is_assigned_lawyer = (
                    db.query(Booking)
                    .filter(
                        Booking.screenshot_asset_id == asset.id,
                        Booking.lawyer_id == lawyer_prof.id,
                    )
                    .first()
                    is not None
                )
        if not (is_owner or is_staff or is_assigned_lawyer):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found",
            )
    elif asset.kind in ("text", "image"):
        if not requester:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found",
            )
        is_owner = requester.id == asset.owner_user_id
        is_staff = requester.role in ["admin", "moderator"]
        if not (is_owner or is_staff):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )

    return StreamingResponse(
        io.BytesIO(asset.file_bytes),
        media_type=asset.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{asset.filename}"'
        },
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

    db.delete(asset)
    db.commit()
    return {"message": "Asset deleted successfully"}
