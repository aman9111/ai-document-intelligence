import io

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from classification.labels import CATEGORIES, DOC_TYPES, category_of
from classification.pages import classify_document, doc_type_label, page_image, summarize
from database import SessionLocal
from dependencies import get_current_user, get_db
from models import Document, DocumentPage, User
from routers.documents import UPLOAD_DIR, get_user_document
from schemas import ClassificationOptions, DocTypeOption, DocumentOut, PageOut, PageTypeUpdate

router = APIRouter(tags=["pages"])


def to_page_out(page: DocumentPage) -> PageOut:
    return PageOut(
        page_number=page.page_number,
        doc_type=page.doc_type,
        doc_type_label=doc_type_label(page.doc_type),
        category=page.category,
        confidence=page.doc_type_confidence,
        needs_review=page.needs_review,
        reason=page.doc_type_reason,
        corrected=page.doc_type_corrected,
        text_preview=" ".join(page.text.split())[:160],
    )


def get_page(document: Document, page_number: int) -> DocumentPage:
    for page in document.pages:
        if page.page_number == page_number:
            return page
    raise HTTPException(status_code=404, detail="Page not found")


@router.get("/classification/types", response_model=ClassificationOptions)
def list_doc_types(current_user: User = Depends(get_current_user)):
    return ClassificationOptions(
        categories=CATEGORIES,
        types=[DocTypeOption(value=t, label=info["label"], category=info["category"]) for t, info in DOC_TYPES.items()],
    )


@router.get("/documents/{document_id}/pages", response_model=list[PageOut])
def list_pages(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_user_document(document_id, current_user, db)
    return [to_page_out(p) for p in sorted(document.pages, key=lambda p: p.page_number)]


@router.get("/documents/{document_id}/pages/{page_number}/image")
def get_page_image(
    document_id: int,
    page_number: int,
    width: int = Query(default=320, ge=80, le=1200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_user_document(document_id, current_user, db)
    get_page(document, page_number)

    image = page_image(UPLOAD_DIR / document.stored_filename, document.content_type, page_number,
                       dpi=60 if width <= 400 else 120)
    if image is None:
        raise HTTPException(status_code=404, detail="This file has no page images")

    image.thumbnail((width, width * 2))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=80)
    # Thumbnails never change for a page, so the browser may keep them for an hour
    return Response(buffer.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.patch("/documents/{document_id}/pages/{page_number}", response_model=PageOut)
def update_page_type(
    document_id: int,
    page_number: int,
    update: PageTypeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if update.doc_type not in DOC_TYPES:
        raise HTTPException(status_code=400, detail="Unknown document type")

    document = get_user_document(document_id, current_user, db)
    page = get_page(document, page_number)

    # A person chose this: keep it, and never let re-classification overwrite it
    page.doc_type = update.doc_type
    page.category = category_of(update.doc_type)
    page.doc_type_confidence = 1.0
    page.needs_review = False
    page.doc_type_reason = "changed by user"
    page.doc_type_corrected = True
    summarize(document)
    db.commit()
    return to_page_out(page)


def classify_in_background(document_id: int) -> None:
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if document is None:
            return
        try:
            classify_document(document, UPLOAD_DIR / document.stored_filename)
        finally:
            document.status = "ready"
            db.commit()


@router.post("/documents/{document_id}/classify", response_model=DocumentOut)
def classify_pages_again(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Classify (again) the pages of a document, e.g. one uploaded before classification
    existed. Pages whose type was set by hand are kept."""
    document = get_user_document(document_id, current_user, db)

    if document.status == "processing":
        raise HTTPException(status_code=409, detail="Document is already being processed")
    if not document.pages:
        raise HTTPException(status_code=409, detail="Document has no pages yet")

    document.status = "processing"
    db.commit()
    db.refresh(document)
    background_tasks.add_task(classify_in_background, document.id)
    return document
