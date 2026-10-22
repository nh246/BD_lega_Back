"""
Documents router: User document uploads for AI chat references.
Allows Pro users to upload .txt, .md, and .pdf documents.
"""

from datetime import datetime
import io
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
import pypdf
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.plans import get_user_plan
from app.models import Document, User

router = APIRouter(prefix="/api/chat/documents", tags=["Documents"])


IMAGE_MIME_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}
ALLOWED_EXTENSIONS = ["txt", "md", "pdf", "png", "jpg", "jpeg", "webp"]


@router.post("", response_model=None)
@router.post("/", response_model=None)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload a document (.txt, .md, .pdf, .png, .jpg, .jpeg, .webp) for AI reference context.
    Pro feature only (plan != 'user_free').
    """
    plan = get_user_plan(db, current_user)
    if plan == "user_free":
        return JSONResponse(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            content={
                "error": "pro_required",
                "message": "Document upload is a Pro feature.",
            },
        )

    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided.",
        )

    filename = file.filename
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Supported types are .txt, .md, .pdf, .png, .jpg, .jpeg, and .webp.",
        )

    content_bytes = await file.read()
    if len(content_bytes) > 2 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds maximum limit of 2 MB.",
        )

    if ext in IMAGE_MIME_TYPES:
        kind = "image"
        mime_type = IMAGE_MIME_TYPES[ext]
        file_bytes = content_bytes
        extracted_text = ""
        char_count = len(content_bytes)
    else:
        kind = "text"
        mime_type = "text/plain" if ext == "txt" else ("text/markdown" if ext == "md" else "application/pdf")
        file_bytes = None

        if ext in ["txt", "md"]:
            extracted_text = content_bytes.decode("utf-8", errors="ignore").strip()
        elif ext == "pdf":
            try:
                reader = pypdf.PdfReader(io.BytesIO(content_bytes))
                pages_text = []
                for page in reader.pages:
                    page_t = page.extract_text()
                    if page_t:
                        pages_text.append(page_t)
                extracted_text = "\n".join(pages_text).strip()
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to extract text from PDF: {str(e)}",
                )

        if len(extracted_text) < 50:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": "no_text",
                    "message": "No extractable text found. Scanned or image-only PDFs are not supported.",
                },
            )

        extracted_text = extracted_text[:200000]
        char_count = len(extracted_text)

    doc = Document(
        owner_user_id=current_user.id,
        filename=filename,
        file_type=ext,
        kind=kind,
        mime_type=mime_type,
        file_bytes=file_bytes,
        extracted_text=extracted_text,
        char_count=char_count,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "id": str(doc.id),
        "filename": doc.filename,
        "file_type": doc.file_type,
        "kind": doc.kind,
        "char_count": doc.char_count,
        "created_at": doc.created_at.isoformat() if hasattr(doc.created_at, "isoformat") else str(doc.created_at),
    }


@router.get("", response_model=None)
@router.get("/", response_model=None)
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List current user's uploaded documents (excluding full text content).
    """
    docs = (
        db.query(Document)
        .filter(Document.owner_user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(d.id),
            "filename": d.filename,
            "file_type": d.file_type,
            "kind": d.kind or "text",
            "char_count": d.char_count,
            "created_at": d.created_at.isoformat() if hasattr(d.created_at, "isoformat") else str(d.created_at),
        }
        for d in docs
    ]


@router.delete("/{doc_id}")
def delete_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete an uploaded document. Only the owner can delete their document.
    """
    try:
        d_uuid = uuid.UUID(doc_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    doc = (
        db.query(Document)
        .filter(Document.id == d_uuid, Document.owner_user_id == current_user.id)
        .first()
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    db.delete(doc)
    db.commit()
    return {"message": "Document deleted successfully"}
