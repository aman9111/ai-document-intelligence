import logging

from chunking import chunk_page
from classification.image_model import release_free_memory
from classification.pages import classify_document
from database import SessionLocal
from embeddings import embed_passages
from extraction import extract_pages
from models import Document, DocumentChunk, DocumentPage

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
        document.processing_step = "reading"
        document.pages.clear()
        document.chunks.clear()
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

            # Split every page into chunks, then turn all chunks into
            # embeddings in one go (much faster than one at a time)
            chunks = [
                chunk
                for page in extracted
                for chunk in chunk_page(page.text, page.page_number)
            ]
            vectors = embed_passages([chunk.text for chunk in chunks])

            for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
                document.chunks.append(
                    DocumentChunk(
                        chunk_index=index,
                        page_number=chunk.page_number,
                        text=chunk.text,
                        embedding=vector,
                    )
                )

            # Text and search index are saved; tell the UI that sorting has started
            document.processing_step = "sorting"
            db.commit()

            # Page types (bill, lab report, Aadhaar...). Search and chat work without
            # them, so a classification problem must not fail the whole document.
            if document.pages:
                try:
                    classify_document(document, file_path)
                except Exception:
                    logger.exception("Page classification failed for document %s", document_id)

            document.status = "ready" if chunks else "failed"
        except Exception:
            logger.exception("Text extraction failed for document %s", document_id)
            db.rollback()
            document = db.get(Document, document_id)
            if document is None:
                return
            document.status = "failed"

        document.processing_step = None
        db.commit()
    finally:
        db.close()
        # OCR images and model work leave freed memory that glibc keeps; return it
        # so the small server goes back to its resting size between uploads
        release_free_memory()
