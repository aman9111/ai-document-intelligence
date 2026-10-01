"""Decide the document type of every page of a file.

For each page:
  1. Failed?  No OCR text, and the page is too dark or blank / too blurred -> "failed"
  2. Text model (TF-IDF + SVM on the OCR text)      -> probability per type
  3. Image model (SigLIP + classifier on the image) -> probability per type
  4. Combine both, trusting the model that is more sure (confidence-weighted).
     With little OCR text (ID cards, handwriting) only the image model decides,
     and if it isn't sure either the page is "failed"
  5. Below REVIEW_THRESHOLD -> keep the best guess but mark it for review
Then across the file:
  6. An "other" page right after a multi-page type (e.g. the last page of a bill)
     is treated as a continuation of it

The choices (combination method, threshold, rules) were compared in
training/evaluate.py; the numbers are in model_files/ensemble_metrics.json.
"""

from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from classification.image_model import ImageEmbedder, predict_embedding
from classification.labels import FAILED, category_of
from classification.text_model import predict_text

# Below this combined confidence a page is flagged "needs review". On the test set,
# pages at or above it were 100% correct and covered 97% of pages.
REVIEW_THRESHOLD = 0.6

# A page with fewer letters/digits than this has no usable text for the text model
MIN_TEXT_CHARS = 15
# Pages with less dark "ink" than this (0.5% of pixels) are treated as blank
MIN_INK_SHARE = 0.005

# Types that often run over several pages; their later pages can look like nothing
MULTI_PAGE_TYPES = {"hospital_bill", "pharmacy_bill", "discharge_summary", "lab_report", "policy_document",
                    "claim_form", "preauth_form", "radiology_report", "consultation_notes"}
# How much of the previous page's type an "other" page must still show to inherit it
CONTINUATION_MIN_SCORE = 0.05


@dataclass
class PageResult:
    doc_type: str
    category: str
    confidence: float
    needs_review: bool
    scores: dict = field(default_factory=dict)  # {"text": {...}, "image": {...}, "combined": {...}}
    reason: str = ""  # why it failed, or "continuation of previous page"


def has_text(text: str) -> bool:
    return sum(ch.isalnum() for ch in text) >= MIN_TEXT_CHARS


def pixel_failed_reason(image: Image.Image) -> str | None:
    """Pages that are unreadable no matter what: too dark, or (almost) nothing on them."""
    gray = image.convert("L")
    gray.thumbnail((300, 300))
    pixels = np.asarray(gray, dtype=np.float32)
    if pixels.mean() < 60 and pixels.std() < 15:
        return "page is too dark"
    # Share of "ink" pixels. Blank and very blurred pages have ~0%, any real page,
    # even a small ID card on a white page, has well over 1%.
    if (pixels < 128).mean() < MIN_INK_SHARE:
        return "page is blank or too blurred to read"
    return None


def combine(text_scores: dict, image_scores: dict) -> dict:
    # Each model's vote counts as much as it is sure of itself
    text_weight, image_weight = max(text_scores.values()), max(image_scores.values())
    total = text_weight + image_weight
    return {t: (text_weight * text_scores[t] + image_weight * image_scores.get(t, 0.0)) / total for t in text_scores}


def decide(text_scores: dict | None, image_scores: dict) -> PageResult:
    if text_scores is None:
        # Little or no OCR text (ID cards, handwriting, photos): only the image model can tell.
        # If it isn't sure either, the page can't be classified.
        doc_type = max(image_scores, key=image_scores.get)
        confidence = image_scores[doc_type]
        if confidence < REVIEW_THRESHOLD:
            return PageResult(FAILED, FAILED, round(confidence, 4), True,
                              scores={"image": {t: round(p, 4) for t, p in image_scores.items()}},
                              reason="no readable text and the image wasn't recognised")
        return PageResult(doc_type, category_of(doc_type), round(confidence, 4), confidence < 0.8,
                          scores={"image": {t: round(p, 4) for t, p in image_scores.items()}},
                          reason="decided from the image only (little text)")

    combined = combine(text_scores, image_scores)
    doc_type = max(combined, key=combined.get)
    confidence = combined[doc_type]
    return PageResult(
        doc_type=doc_type,
        category=category_of(doc_type),
        confidence=round(confidence, 4),
        needs_review=confidence < REVIEW_THRESHOLD,
        scores={name: {t: round(p, 4) for t, p in s.items()}
                for name, s in (("text", text_scores), ("image", image_scores), ("combined", combined))},
    )


def apply_page_context(results: list[PageResult]) -> list[PageResult]:
    for previous, page in zip(results, results[1:]):
        if page.doc_type == "other" and previous.doc_type in MULTI_PAGE_TYPES:
            score = page.scores.get("combined", {}).get(previous.doc_type, 0.0)
            if score >= CONTINUATION_MIN_SCORE:
                page.doc_type = previous.doc_type
                page.category = previous.category
                page.confidence = round(score, 4)
                page.needs_review = True
                page.reason = "continuation of previous page"
    return results


def classify_pages(pages: list[tuple[str, Image.Image]]) -> list[PageResult]:
    """pages: (OCR text, page image) for every page of one file, in order."""
    results: list[PageResult | None] = [None] * len(pages)
    readable = []
    for i, (text, image) in enumerate(pages):
        # Only pages without text can be "failed": scanned text is often light grey,
        # so a page with OCR text is never judged by its pixels
        reason = None if has_text(text) else pixel_failed_reason(image)
        if reason:
            results[i] = PageResult(FAILED, FAILED, 0.0, True, reason=reason)
        else:
            readable.append(i)

    if readable:
        # Load SigLIP once for the whole file, then release its memory
        with ImageEmbedder() as embedder:
            embeddings = []
            for start in range(0, len(readable), 4):  # small batches keep peak RAM low
                batch = readable[start:start + 4]
                embeddings.extend(embedder.embed([pages[i][1] for i in batch]))
        for i, embedding in zip(readable, embeddings):
            text = pages[i][0]
            text_scores = predict_text(text) if has_text(text) else None
            results[i] = decide(text_scores, predict_embedding(np.asarray(embedding)))

    return apply_page_context(results)
