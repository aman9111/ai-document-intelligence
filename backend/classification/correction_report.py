"""What do users correct? Counts only, never any document text.

    python -m classification.correction_report

Shows, for pages whose type a user changed by hand, what the model had said and
what the user chose, and how many pages the correction memory (memory.py) fixed.
Use it to decide which kinds of pages the training generator needs more of
(training/generate_samples.py), then retrain. The pages themselves are users'
documents and are never used for training.
"""

from collections import Counter

from database import SessionLocal
from models import DocumentPage


def model_guess(page: DocumentPage) -> str:
    combined = (page.doc_type_scores or {}).get("combined") or (page.doc_type_scores or {}).get("text")
    return max(combined, key=combined.get) if combined else "(not classified)"


def main():
    with SessionLocal() as db:
        corrected = db.query(DocumentPage).filter(DocumentPage.doc_type_corrected.is_(True)).all()
        remembered = db.query(DocumentPage).filter(DocumentPage.doc_type_reason.like("like page % which you corrected")).count()
        total = db.query(DocumentPage).filter(DocumentPage.doc_type.isnot(None)).count()

    changes = Counter((model_guess(p), p.doc_type) for p in corrected)
    wrong = sum(n for (guess, chosen), n in changes.items() if guess != chosen)

    print(f"classified pages: {total}")
    print(f"corrected by users: {len(corrected)} ({wrong} where the model was wrong)")
    print(f"fixed automatically from earlier corrections: {remembered}\n")
    if changes:
        print("model said -> user chose")
        for (guess, chosen), n in changes.most_common():
            mark = "" if guess != chosen else "   (same, only confirmed)"
            print(f"  {guess:20} -> {chosen:20} x{n}{mark}")


if __name__ == "__main__":
    main()
