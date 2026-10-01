"""Train and evaluate the text classifier (TF-IDF + linear SVM).

    python training/build_dataset.py   # first, to read the pages with OCR
    python training/train_text.py

Saves classification/model_files/text_model.joblib and text_model_metrics.json.
"""

import csv
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import joblib
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from classification.text_model import MODEL_FILE, normalize  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"


def load_split(split):
    texts = {r["path"]: r["text"] for r in map(json.loads, (DATA_DIR / "texts.jsonl").open())}
    rows = [r for r in csv.DictReader((DATA_DIR / "manifest.csv").open()) if r["split"] == split]
    return rows, [texts[r["path"]] for r in rows], [r["doc_type"] for r in rows]


def build_model():
    features = FeatureUnion([
        # Words and word pairs ("discharge summary", "reference range")
        ("words", TfidfVectorizer(preprocessor=normalize, ngram_range=(1, 2), min_df=3,
                                  max_features=60000, sublinear_tf=True)),
        # Pieces of 3-5 letters, so OCR typos ("Haemog1obin") still share most features
        ("chars", TfidfVectorizer(preprocessor=normalize, analyzer="char_wb", ngram_range=(3, 5), min_df=3,
                                  max_features=120000, sublinear_tf=True)),
    ])
    # LinearSVC gives scores, not probabilities. Calibration turns them into
    # probabilities, which the app needs to decide "confident enough or not".
    classifier = CalibratedClassifierCV(LinearSVC(C=0.5, class_weight="balanced"), cv=5, method="sigmoid")
    return Pipeline([("features", features), ("classifier", classifier)])


def main():
    train_rows, train_texts, train_labels = load_split("train")
    test_rows, test_texts, test_labels = load_split("test")
    print(f"train {len(train_texts)} pages, test {len(test_texts)} pages, {len(set(train_labels))} types")

    model = build_model()
    started = time.time()
    model.fit(train_texts, train_labels)
    print(f"trained in {time.time() - started:.1f}s")

    started = time.time()
    probabilities = model.predict_proba(test_texts)
    per_page_ms = (time.time() - started) / len(test_texts) * 1000
    predicted = [model.classes_[p.argmax()] for p in probabilities]
    confidence = [p.max() for p in probabilities]

    accuracy = accuracy_score(test_labels, predicted)
    print(f"\nTEST ACCURACY: {accuracy:.1%}   ({per_page_ms:.1f} ms per page)")

    by_source = defaultdict(list)
    for row, truth, guess in zip(test_rows, test_labels, predicted):
        by_source[row["source"]].append(truth == guess)
    for source, hits in sorted(by_source.items()):
        print(f"  {source:10} {sum(hits) / len(hits):.1%}  ({len(hits)} pages)")

    print("\n" + classification_report(test_labels, predicted, digits=3, zero_division=0))

    mistakes = Counter((t, g) for t, g in zip(test_labels, predicted) if t != g)
    if mistakes:
        print("most common mistakes (true -> predicted):")
        for (truth, guess), n in mistakes.most_common(10):
            print(f"  {truth:20} -> {guess:20} x{n}")

    # How accurate are the pages the model is sure about? (used to pick a threshold)
    print("\nconfidence threshold vs accuracy / pages kept:")
    for threshold in (0.0, 0.5, 0.6, 0.7, 0.8, 0.9):
        kept = [(t == g) for t, g, c in zip(test_labels, predicted, confidence) if c >= threshold]
        if kept:
            print(f"  >= {threshold:.1f}: accuracy {sum(kept) / len(kept):.1%}, keeps {len(kept) / len(test_labels):.0%} of pages")

    MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_FILE, compress=3)
    labels = list(model.classes_)
    metrics = {
        "accuracy": accuracy,
        "accuracy_by_source": {s: sum(h) / len(h) for s, h in by_source.items()},
        "ms_per_page": per_page_ms,
        "labels": labels,
        "confusion_matrix": confusion_matrix(test_labels, predicted, labels=labels).tolist(),
        "train_pages": len(train_texts),
        "test_pages": len(test_texts),
    }
    MODEL_FILE.with_name("text_model_metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"\nsaved {MODEL_FILE.relative_to(MODEL_FILE.parents[2])} ({MODEL_FILE.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
