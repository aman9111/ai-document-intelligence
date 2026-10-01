"""Evaluate the whole page classifier, like the numbers on the design whiteboard.

    python training/evaluate.py

1. Test set: text model, image model and the combined result
2. Failed pages: are blank/unreadable pages caught, and are good pages left alone?
3. Bundles: whole multi-page PDFs through the real pipeline (OCR -> classify_pages),
   with and without the page-context rule
Saves classification/model_files/ensemble_metrics.json.
"""

import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from pdf2image import convert_from_path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from classification.classify import REVIEW_THRESHOLD, classify_pages, decide, has_text, pixel_failed_reason  # noqa: E402
from classification.image_model import ImageEmbedder, load_head, predict_embedding  # noqa: E402
from classification.text_model import load_model  # noqa: E402
from extraction import ocr_image  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"
METRICS_FILE = Path(__file__).resolve().parent.parent / "classification" / "model_files" / "ensemble_metrics.json"


def test_set():
    texts = {r["path"]: r["text"] for r in map(json.loads, (DATA_DIR / "texts.jsonl").open())}
    cache = np.load(DATA_DIR / "image_embeddings.npz", allow_pickle=True)
    vectors = dict(zip(cache["paths"], cache["vectors"]))
    rows = [r for r in csv.DictReader((DATA_DIR / "manifest.csv").open()) if r["split"] == "test"]

    text_model, image_head = load_model(), load_head()
    classes = list(text_model.classes_)
    text_probs = text_model.predict_proba([texts[r["path"]] for r in rows])
    image_probs = image_head.predict_proba(np.array([vectors[r["path"]] for r in rows]))

    results = {"text": [], "image": [], "combined": []}
    review = []
    for row, tp, ip in zip(rows, text_probs, image_probs):
        text_scores, image_scores = dict(zip(classes, tp)), dict(zip(classes, ip))
        page = decide(text_scores, image_scores)
        results["text"].append(max(text_scores, key=text_scores.get) == row["doc_type"])
        results["image"].append(max(image_scores, key=image_scores.get) == row["doc_type"])
        results["combined"].append(page.doc_type == row["doc_type"])
        review.append(page.needs_review)

    print(f"1. TEST SET ({len(rows)} pages)")
    summary = {}
    for name, hits in results.items():
        summary[name] = sum(hits) / len(hits)
        print(f"   {name:9} accuracy {summary[name]:.1%}")
    sure = [hit for hit, flagged in zip(results["combined"], review) if not flagged]
    summary["combined_not_flagged"] = sum(sure) / max(len(sure), 1)
    summary["flagged_for_review"] = sum(review) / len(review)
    print(f"   pages flagged for review (< {REVIEW_THRESHOLD}): {summary['flagged_for_review']:.1%}")
    print(f"   accuracy of pages NOT flagged: {summary['combined_not_flagged']:.1%}")
    return summary


def failed_pages():
    """Runs the real per-page decision on every page, using cached embeddings where possible."""
    texts = {r["path"]: r["text"] for r in map(json.loads, (DATA_DIR / "texts.jsonl").open())}
    cache = np.load(DATA_DIR / "image_embeddings.npz", allow_pickle=True)
    vectors = dict(zip(cache["paths"], cache["vectors"]))
    rows = list(csv.DictReader((DATA_DIR / "manifest.csv").open()))

    # Pages that reach the image-only path but have no cached embedding (the failed set)
    need = [r["path"] for r in rows if r["path"] not in vectors and not has_text(texts[r["path"]])]
    if need:
        with ImageEmbedder() as embedder:
            vectors.update(zip(need, embedder.embed([Image.open(DATA_DIR / p) for p in need])))

    caught, false_alarms, image_only = Counter(), [], []
    for row in rows:
        text = texts[row["path"]]
        failed = None
        if not has_text(text):
            with Image.open(DATA_DIR / row["path"]) as image:
                failed = pixel_failed_reason(image)
        if not failed and not has_text(text):
            page = decide(None, predict_embedding(vectors[row["path"]]))
            failed = page.reason if page.doc_type == "failed" else None
            if not failed and row["split"] != "failed":
                image_only.append(page.doc_type == row["doc_type"])
        if row["split"] == "failed":
            caught[row["mode"], bool(failed)] += 1
        elif failed:
            false_alarms.append((row["path"], failed))

    failed_total = sum(caught.values())
    detected = sum(n for (_, hit), n in caught.items() if hit)
    print(f"\n2. FAILED PAGES: caught {detected}/{failed_total}")
    for kind in sorted({k for k, _ in caught}):
        print(f"   {kind:11} caught {caught[kind, True]}/{caught[kind, True] + caught[kind, False]}")
    good_pages = len([r for r in rows if r["split"] != "failed"])
    print(f"   good pages wrongly marked failed: {len(false_alarms)}/{good_pages}")
    for path, reason in false_alarms[:8]:
        print(f"     {path}: {reason}")
    if image_only:
        print(f"   pages with little text decided by image only: {sum(image_only)}/{len(image_only)} correct")
    return {"failed_caught": detected / max(failed_total, 1), "good_marked_failed": len(false_alarms) / good_pages}


def bundles():
    print("\n3. BUNDLES (whole PDFs through OCR + classify_pages)")
    correct = total = context_fixed = context_broke = 0
    for pdf in sorted((DATA_DIR / "bundles").glob("bundle_*.pdf")):
        expected = json.loads(pdf.with_suffix(".json").read_text())
        images = convert_from_path(pdf, dpi=200)
        results = classify_pages([(ocr_image(image), image) for image in images])

        hits = sum(r.doc_type == e for r, e in zip(results, expected))
        correct, total = correct + hits, total + len(expected)
        print(f"   {pdf.name}: {hits}/{len(expected)} correct")
        for n, (r, e) in enumerate(zip(results, expected), start=1):
            if r.reason == "continuation of previous page":
                # The rule changed this page from "other": was that right?
                context_fixed += r.doc_type == e
                context_broke += r.doc_type != e
            if r.doc_type != e or r.reason:
                note = f" ({r.reason})" if r.reason else ""
                print(f"     page {n:2}: expected {e:18} got {r.doc_type:18} {r.confidence:.2f}{note}")
    accuracy = correct / total
    print(f"   overall: {correct}/{total} = {accuracy:.1%}")
    print(f"   page-context rule: fixed {context_fixed}, broke {context_broke}")
    return {"bundle_accuracy": accuracy, "context_fixed": context_fixed, "context_broke": context_broke}


def main():
    metrics = {"review_threshold": REVIEW_THRESHOLD}
    metrics.update(test_set())
    metrics.update(failed_pages())
    metrics.update(bundles())
    METRICS_FILE.write_text(json.dumps(metrics, indent=2))
    print(f"\nsaved {METRICS_FILE.name}")


if __name__ == "__main__":
    main()
