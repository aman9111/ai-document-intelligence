import logging

from database import SessionLocal
from extraction import extract_pages
from models import Document, DocumentPage

logger = logging.getLogger(__name__)


def process_document(document_id: int, file_path) -> None:
    # Runs after the response is sent, so the request's db session is already
    # closed. A background task has to open (and close) its own session.
    db = SessionLocal()

    try:
        document = db.get(Document, document_id)
        if document is None:
            return

        document.status = "processing"
        document.pages.clear()
        db.commit()

        try:
            extracted = extract_pages(file_path, document.content_type)

            for page in extracted:
                document.pages.append(
                    DocumentPage(
                        page_number=page.page_number,
                        text=page.text,
                        method=page.method,
                    )
                )

            has_text = any(page.text for page in extracted)
            document.status = "ready" if has_text else "failed"
        except Exception:
            logger.exception("Text extraction failed for document %s", document_id)
            db.rollback()
            document = db.get(Document, document_id)
            if document is None:
                return
            document.status = "failed"

        db.commit()
    finally:
        db.close()
