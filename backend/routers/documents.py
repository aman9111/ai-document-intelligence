import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from dependencies import get_current_user, get_db
from embeddings import embed_passages, embed_query, similarity
from models import Document, DocumentChunk, User
from processing import process_document
from schemas import DocumentOut, DocumentPageOut, SearchRequest, SearchResult

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
    background_tasks: BackgroundTasks,
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
        status="processing",
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    # Text extraction (especially OCR) is slow, so it runs after the response
    # is sent. The UI polls GET /documents until the status changes.
    background_tasks.add_task(process_document, document.id, file_path)

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


@router.get("/{document_id}/text", response_model=list[DocumentPageOut])
def get_document_text(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_user_document(document_id, current_user, db)
    return document.pages


@router.post("/{document_id}/search", response_model=list[SearchResult])
def search_document(
    document_id: int,
    search: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_user_document(document_id, current_user, db)

    if document.status != "ready":
        raise HTTPException(status_code=409, detail="Document is not ready for search yet")

    # Documents processed before search existed have text but no chunks
    has_chunks = db.query(DocumentChunk.id).filter(DocumentChunk.document_id == document.id).first()

    if has_chunks is None:
        raise HTTPException(
            status_code=409,
            detail="This document was processed before search was added. Re-process it to enable search.",
        )

    query_vector = embed_query(search.query)

    # <=> is pgvector's cosine distance: 0 = same meaning, bigger = less similar
    distance = DocumentChunk.embedding.cosine_distance(query_vector)

    rows = (
        db.query(DocumentChunk, distance.label("distance"))
        .filter(DocumentChunk.document_id == document.id)
        .order_by(distance)
        .limit(search.top_k)
        .all()
    )

    # A chunk has many lines. Find the one line in each chunk that best matches
    # the question, so the UI can highlight it (e.g. "4 Electrolytes 800.00").
    chunk_lines = [
        [line for line in chunk.text.split("\n") if line.strip()] or [chunk.text]
        for chunk, _ in rows
    ]
    line_vectors = iter(embed_passages([line for lines in chunk_lines for line in lines]))

    results = []
    seen_lines = set()

    for (chunk, chunk_distance), lines in zip(rows, chunk_lines):
        vectors = [next(line_vectors) for _ in lines]
        scores = [similarity(query_vector, vector) for vector in vectors]
        best_line = lines[scores.index(max(scores))]

        # Chunks overlap, so two chunks can have the same best line.
        # Rows are sorted best first, so keep only the first one.
        if best_line in seen_lines:
            continue
        seen_lines.add(best_line)

        results.append(
            SearchResult(
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                text=chunk.text,
                best_line=best_line,
                score=round(1 - chunk_distance, 3),
            )
        )

    return results


@router.post("/{document_id}/process", response_model=DocumentOut)
def reprocess_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_user_document(document_id, current_user, db)

    if document.status == "processing":
        raise HTTPException(status_code=409, detail="Document is already being processed")

    file_path = UPLOAD_DIR / document.stored_filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File is missing on the server")

    document.status = "processing"
    db.commit()
    db.refresh(document)

    background_tasks.add_task(process_document, document.id, file_path)

    return document


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
