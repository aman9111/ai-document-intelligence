"""Learn from the user's own corrections, without retraining and without their
documents ever leaving the database.

When a user changes a page's type, that page becomes an example. A new page whose
text means almost the same thing (same kind of bill from the same lab, same form...)
gets the type the user chose, instead of the model's guess.

Page "meaning" = the average of the page's search-chunk embeddings (bge-small),
which the app already stores, so this costs no extra model.

Only the same user's corrections are used: one user's documents never influence
another user's results.
"""

from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from classification.labels import FAILED, category_of
from models import Document, DocumentChunk, DocumentPage

# On the synthetic test set (training/data), when the most similar page was at
# least this close it had the same type 100% of the time. The closest pair of
# different types (a hospital bill and a payment receipt) was 0.89.
MATCH_THRESHOLD = 0.90


@dataclass
class CorrectedPage:
    vector: np.ndarray
    doc_type: str
    document_id: int
    page_number: int
    filename: str


def page_vector(embeddings: list) -> np.ndarray | None:
    """One unit-length vector for a page from its chunk embeddings."""
    if not embeddings:
        return None
    vector = np.mean(np.asarray(embeddings, dtype=np.float32), axis=0)
    norm = np.linalg.norm(vector)
    return vector / norm if norm else None


def page_vectors(document: Document) -> dict[int, np.ndarray]:
    """{page_number: vector} for every page of a document that has text."""
    by_page: dict[int, list] = {}
    for chunk in document.chunks:
        by_page.setdefault(chunk.page_number, []).append(chunk.embedding)
    vectors = {n: page_vector(e) for n, e in by_page.items()}
    return {n: v for n, v in vectors.items() if v is not None}


def corrected_pages(db: Session, user_id: int) -> list[CorrectedPage]:
    """Every page this user set the type of by hand (and that has text)."""
    rows = (
        db.query(DocumentPage.document_id, DocumentPage.page_number, DocumentPage.doc_type, Document.original_filename)
        .join(Document, Document.id == DocumentPage.document_id)
        .filter(Document.user_id == user_id, DocumentPage.doc_type_corrected.is_(True), DocumentPage.doc_type != FAILED)
        .all()
    )
    examples = []
    for document_id, page_number, doc_type, filename in rows:
        embeddings = [
            e for (e,) in db.query(DocumentChunk.embedding)
            .filter(DocumentChunk.document_id == document_id, DocumentChunk.page_number == page_number)
        ]
        vector = page_vector(embeddings)
        if vector is not None:
            examples.append(CorrectedPage(vector, doc_type, document_id, page_number, filename))
    return examples


def best_match(vector: np.ndarray, examples: list[CorrectedPage], skip: tuple[int, int]) -> tuple[CorrectedPage, float] | None:
    """The most similar corrected page, if it is similar enough."""
    best, best_similarity = None, MATCH_THRESHOLD
    for example in examples:
        if (example.document_id, example.page_number) == skip:
            continue
        similarity = float(vector @ example.vector)
        if similarity >= best_similarity:
            best, best_similarity = example, similarity
    return (best, best_similarity) if best else None


def apply_corrections(db: Session, document: Document) -> int:
    """Give pages the type of a matching page the user corrected. Returns how many pages
    were matched. Pages the user corrected themselves are left alone."""
    examples = corrected_pages(db, document.user_id)
    if not examples:
        return 0

    vectors = page_vectors(document)
    matched = 0
    for page in document.pages:
        vector = vectors.get(page.page_number)
        if page.doc_type_corrected or vector is None:
            continue
        match = best_match(vector, examples, skip=(document.id, page.page_number))
        if match is None:
            continue
        example, similarity = match
        source = "this file" if example.document_id == document.id else example.filename
        page.doc_type = example.doc_type
        page.category = category_of(example.doc_type)
        page.doc_type_confidence = round(similarity, 4)
        page.needs_review = False
        page.doc_type_reason = f"like page {example.page_number} of {source}, which you corrected"[:200]
        page.doc_type_scores = {**(page.doc_type_scores or {}),
                                "memory": {"doc_type": example.doc_type, "similarity": round(similarity, 4)}}
        matched += 1
    return matched
