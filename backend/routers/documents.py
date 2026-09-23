import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from dependencies import get_current_user, get_db
from models import Document, User
from schemas import DocumentOut

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
CHUNK_SIZE = 1024 * 1024  # 1 MB

ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def get_user_document(document_id: int, user: User, db: Session) -> Document:
    document = db.get(Document, document_id)

    # Same 404 for "doesn't exist" and "belongs to someone else",
    # so users can't discover other people's document ids
    if document is None or document.user_id != user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    return document


@router.post("", response_model=DocumentOut, status_code=201)
def upload_document(
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    original_filename = Path(file.filename or "").name
    extension = Path(original_filename).suffix.lower()

    if extension not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, DOCX, PNG and JPG files are allowed",
        )

    stored_filename = f"{uuid.uuid4().hex}{extension}"
    file_path = UPLOAD_DIR / stored_filename
    size_bytes = 0

    # Save in 1 MB chunks so a big file never has to fit in memory
    with file_path.open("wb") as buffer:
        while chunk := file.file.read(CHUNK_SIZE):
            size_bytes += len(chunk)

            if size_bytes > MAX_FILE_SIZE:
                buffer.close()
                file_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File is larger than 10 MB")

            buffer.write(chunk)

    if size_bytes == 0:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="File is empty")

    document = Document(
        user_id=current_user.id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        content_type=ALLOWED_TYPES[extension],
        size_bytes=size_bytes,
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return document


@router.get("", response_model=list[DocumentOut])
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .all()
    )


@router.get("/{document_id}/file")
def download_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_user_document(document_id, current_user, db)
    file_path = UPLOAD_DIR / document.stored_filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File is missing on the server")

    return FileResponse(
        file_path,
        media_type=document.content_type,
        filename=document.original_filename,
        content_disposition_type="inline",
    )


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_user_document(document_id, current_user, db)

    (UPLOAD_DIR / document.stored_filename).unlink(missing_ok=True)

    db.delete(document)
    db.commit()
