import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from openai import APIError, RateLimitError
from sqlalchemy import text
from sqlalchemy.orm import Session

from dependencies import get_current_user, get_db
from embeddings import embed_query
from llm import LLMNotConfiguredError, Source, answer_question, save_usage
from models import Document, DocumentChunk, User
from processing import process_document
from search import Answer, rank_answers
from schemas import (
    AskRequest,
    AskResponse,
    AskSource,
    AIUsage,
    DocumentOut,
    DocumentPageOut,
    SearchRequest,
    SearchResult,
)

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
CHUNK_SIZE = 1024 * 1024  # 1 MB
CANDIDATE_CHUNKS = 10  # chunks fetched by meaning and by keywords before ranking answers
ASK_SOURCE_CHUNKS = 5  # chunks sent to the LLM as context

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


def get_searchable_document(document_id: int, user: User, db: Session) -> Document:
    document = get_user_document(document_id, user, db)

    if document.status != "ready":
        raise HTTPException(status_code=409, detail="Document is not ready for search yet")

    # Documents processed before search existed have text but no chunks
    has_chunks = db.query(DocumentChunk.id).filter(DocumentChunk.document_id == document.id).first()

    if has_chunks is None:
        raise HTTPException(
            status_code=409,
            detail="This document was processed before search was added. Re-process it to enable search.",
        )

    return document


def retrieve(document: Document, query: str, db: Session) -> tuple[list[Answer], dict[int, DocumentChunk]]:
    query_vector = embed_query(query)

    # Step 1: find candidate chunks in two ways, so neither kind of match is missed

    # a) By meaning: pgvector cosine distance (<=>), closest first
    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    meaning_ids = [
        chunk_id
        for (chunk_id,) in db.query(DocumentChunk.id)
        .filter(DocumentChunk.document_id == document.id)
        .order_by(distance)
        .limit(CANDIDATE_CHUNKS)
    ]

    # b) By exact words: PostgreSQL full-text search. plainto_tsquery turns
    # "dengue test cost" into 'dengu' & 'test' & 'cost' (all words required);
    # replacing & with | means "any of these words", ranked by ts_rank.
    keyword_ids = [
        row.id
        for row in db.execute(
            text(
                """
                SELECT id FROM document_chunks
                WHERE document_id = :document_id
                  AND to_tsvector('english', text) @@ replace(plainto_tsquery('english', :query)::text, '&', '|')::tsquery
                ORDER BY ts_rank(to_tsvector('english', text), replace(plainto_tsquery('english', :query)::text, '&', '|')::tsquery) DESC
                LIMIT :limit
                """
            ),
            {"document_id": document.id, "query": query, "limit": CANDIDATE_CHUNKS},
        )
    ]

    candidate_ids = list(dict.fromkeys(meaning_ids + keyword_ids))
    chunks = {
        chunk.id: chunk
        for chunk in db.query(DocumentChunk).filter(DocumentChunk.id.in_(candidate_ids))
    }

    # Step 2: split candidate chunks into small answers (one line / sentence)
    # and score each one by meaning + exact words (hybrid search)
    answers = rank_answers(
        query,
        query_vector,
        [(chunk_id, chunks[chunk_id].text) for chunk_id in candidate_ids],
    )

    return answers, chunks


def find_sources(document: Document, query: str, db: Session) -> list[Source]:
    # RAG step 1 (Retrieval): take the chunks of the best answers, best first,
    # until we have ASK_SOURCE_CHUNKS different chunks
    answers, chunks = retrieve(document, query, db)

    source_chunks = []
    for answer in answers:
        chunk = chunks[answer.chunk_id]
        if chunk not in source_chunks:
            source_chunks.append(chunk)
        if len(source_chunks) == ASK_SOURCE_CHUNKS:
            break

    return [
        Source(number=number, page_number=chunk.page_number, text=chunk.text)
        for number, chunk in enumerate(source_chunks, start=1)
    ]


def rate_limit_message(error: RateLimitError) -> str:
    # The 429 response also carries the limit headers, so the UI can show them
    limits = save_usage(error.response.headers, None)
    wait = error.response.headers.get("retry-after")

    return (
        "The free AI limit was reached. "
        + (f"Please try again in {wait} seconds." if wait else "Please wait a minute and try again.")
        + (" (No questions left today.)" if limits.requests_remaining == 0 else "")
    )


@router.post("/{document_id}/search", response_model=list[SearchResult])
def search_document(
    document_id: int,
    search: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_searchable_document(document_id, current_user, db)
    answers, chunks = retrieve(document, search.query, db)

    return [
        SearchResult(
            chunk_index=chunks[answer.chunk_id].chunk_index,
            page_number=chunks[answer.chunk_id].page_number,
            text=chunks[answer.chunk_id].text,
            best_line=answer.text,
            score=round(answer.score, 3),
        )
        for answer in answers[: search.top_k]
    ]


@router.post("/{document_id}/ask", response_model=AskResponse)
def ask_document(
    document_id: int,
    ask: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_searchable_document(document_id, current_user, db)
    sources = find_sources(document, ask.question, db)

    # RAG steps 2 + 3 (Augmented Generation): send the question together with
    # the excerpts to the LLM and let it write the answer
    try:
        answer, usage = answer_question(ask.question, sources)
    except LLMNotConfiguredError:
        raise HTTPException(status_code=503, detail="AI is not configured on the server")
    except RateLimitError as error:
        raise HTTPException(status_code=429, detail=rate_limit_message(error))
    except APIError:
        raise HTTPException(status_code=502, detail="The AI service failed. Please try again.")

    return AskResponse(
        answer=answer,
        sources=[
            AskSource(number=source.number, page_number=source.page_number, text=source.text)
            for source in sources
        ],
        usage=AIUsage.model_validate(usage),
    )


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
