"""Run the page classifier on a stored document and save the results."""

import logging
from collections import Counter
from pathlib import Path

from pdf2image import convert_from_path
from PIL import Image
from sqlalchemy.orm import object_session

from classification.classify import classify_pages
from classification.labels import DOC_TYPES, FAILED
from classification.memory import apply_corrections
from models import Document

logger = logging.getLogger(__name__)

# Page images for the classifier and for thumbnails. SigLIP only looks at 224 x 224,
# so 80 dpi is plenty and keeps memory low for long PDFs.
PAGE_IMAGE_DPI = 80


def page_images(file_path: Path, content_type: str, page_count: int) -> list[Image.Image | None]:
    if content_type == "application/pdf":
        return convert_from_path(file_path, dpi=PAGE_IMAGE_DPI)
    if content_type.startswith("image/"):
        with Image.open(file_path) as image:
            return [image.convert("RGB")]
    # DOCX has no page images
    return [None] * page_count


def page_image(file_path: Path, content_type: str, page_number: int, dpi: int = PAGE_IMAGE_DPI) -> Image.Image | None:
    """One page as an image (for thumbnails), or None if the file has no page images."""
    if content_type == "application/pdf":
        images = convert_from_path(file_path, dpi=dpi, first_page=page_number, last_page=page_number)
        return images[0] if images else None
    if content_type.startswith("image/") and page_number == 1:
        with Image.open(file_path) as image:
            return image.convert("RGB")
    return None


def summarize(document: Document) -> None:
    """The file-level summary: its most common page type and pages per category."""
    pages = [p for p in document.pages if p.doc_type]
    if not pages:
        return
    types = Counter(p.doc_type for p in pages if p.doc_type != FAILED) or Counter(p.doc_type for p in pages)
    main_type = types.most_common(1)[0][0]
    document.doc_type = main_type
    document.doc_type_confidence = round(
        sum(p.doc_type_confidence or 0 for p in pages if p.doc_type == main_type) / types[main_type], 4)
    document.doc_type_scores = dict(Counter(p.category for p in pages))
    document.doc_type_corrected = any(p.doc_type_corrected for p in pages)


def classify_document(document: Document, file_path: Path) -> None:
    """Classify every page of a document in place (the caller commits)."""
    pages = sorted(document.pages, key=lambda p: p.page_number)
    images = page_images(file_path, document.content_type, len(pages))

    results = classify_pages([(page.text, image) for page, image in zip(pages, images)])

    for page, result in zip(pages, results):
        if page.doc_type_corrected:
            continue  # never overwrite a type the user chose
        page.doc_type = result.doc_type
        page.category = result.category
        page.doc_type_confidence = result.confidence
        page.doc_type_scores = result.scores
        page.needs_review = result.needs_review
        page.doc_type_reason = result.reason or None

    # Pages like ones the user corrected before get the user's type
    db = object_session(document)
    if db is not None:
        apply_corrections(db, document)
    summarize(document)


def doc_type_label(doc_type: str | None) -> str:
    if doc_type == FAILED:
        return "Failed page"
    return DOC_TYPES.get(doc_type, {}).get("label", "Not classified")
