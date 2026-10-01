"""Classify the pages of every document that hasn't been classified yet.

    python -m classification.backfill            # only documents with unclassified pages
    python -m classification.backfill --all      # every document again (keeps pages set by hand)

In Docker:  docker compose exec backend python -m classification.backfill
"""

import argparse
import logging

from classification.pages import classify_document
from database import SessionLocal
from models import Document
from routers.documents import UPLOAD_DIR


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="re-classify documents that already have types")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    with SessionLocal() as db:
        documents = db.query(Document).filter(Document.status == "ready").order_by(Document.id).all()
        todo = [d for d in documents if args.all or any(p.doc_type is None for p in d.pages)]
        print(f"{len(todo)} of {len(documents)} ready documents to classify")

        for document in todo:
            path = UPLOAD_DIR / document.stored_filename
            if not path.exists():
                print(f"  #{document.id} {document.original_filename}: file missing, skipped")
                continue
            try:
                classify_document(document, path)
                db.commit()
                print(f"  #{document.id} {document.original_filename}: {document.doc_type_scores}")
            except Exception as error:  # keep going with the other documents
                db.rollback()
                print(f"  #{document.id} {document.original_filename}: failed ({error})")


if __name__ == "__main__":
    main()
