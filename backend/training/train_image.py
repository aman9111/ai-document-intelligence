"""Train and evaluate the image classifier (SigLIP 2 embeddings + logistic regression).

    python training/train_image.py

1. Embeds every train/test page with SigLIP (cached in training/data/image_embeddings.npz)
2. Zero-shot baseline: compares page embeddings with the type descriptions in
   classification/labels.py, no training at all
3. Trains a small classifier on top of the embeddings and evaluates it
Saves classification/model_files/image_head.joblib and image_model_metrics.json.
"""

import csv
import hashlib
import json
import resource
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import numpy as np
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import cross_val_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from classification.image_model import HEAD_FILE, SIGLIP_MODEL, ImageEmbedder  # noqa: E402
from classification.labels import DOC_TYPES  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"
CACHE_FILE = DATA_DIR / "image_embeddings.npz"


def peak_ram_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024


def embed_all(paths):
    """{path: embedding}. Embeddings are cached by a hash of the image file, so only
    new or changed pages go through SigLIP (the slow part of training)."""
    hashes = {p: hashlib.sha1((DATA_DIR / p).read_bytes()).hexdigest() for p in paths}
    by_hash = {}
    if CACHE_FILE.exists():
        data = np.load(CACHE_FILE, allow_pickle=True)
        if "hashes" in data:  # caches from before hashing are not trusted
            by_hash = dict(zip(data["hashes"], data["vectors"]))
    cached = {p: by_hash[h] for p, h in hashes.items() if h in by_hash}
    todo = [p for p in paths if p not in cached]
    print(f"{len(cached)} pages unchanged since the last run, {len(todo)} to embed")

    if todo:
        started = time.time()
        with ImageEmbedder() as embedder:
            print(f"SigLIP loaded in {time.time() - started:.1f}s, RAM {peak_ram_mb()} MB")
            started = time.time()
            for i in range(0, len(todo), 32):
                batch = todo[i:i + 32]
                images = [Image.open(DATA_DIR / p) for p in batch]
                for path, vector in zip(batch, embedder.embed(images)):
                    cached[path] = vector
                if (i // 32) % 10 == 0:
                    print(f"  {i + len(batch)}/{len(todo)}", flush=True)
            per_page = (time.time() - started) / len(todo) * 1000
            print(f"embedded at {per_page:.0f} ms per page, peak RAM {peak_ram_mb()} MB")
    # Written fresh with exactly these pages, so nothing stale is left
    np.savez(CACHE_FILE, paths=np.array(paths), hashes=np.array([hashes[p] for p in paths]),
             vectors=np.array([cached[p] for p in paths]))
    return cached


def report(name, rows, truth, predicted, confidence):
    accuracy = accuracy_score(truth, predicted)
    print(f"\n{name} TEST ACCURACY: {accuracy:.1%}")
    by_source = defaultdict(list)
    for row, t, p in zip(rows, truth, predicted):
        by_source[row["source"]].append(t == p)
    for source, hits in sorted(by_source.items()):
        print(f"  {source:10} {sum(hits) / len(hits):.1%}  ({len(hits)} pages)")
    mistakes = Counter((t, p) for t, p in zip(truth, predicted) if t != p)
    if mistakes:
        print("  most common mistakes (true -> predicted):")
        for (t, p), n in mistakes.most_common(8):
            print(f"    {t:20} -> {p:20} x{n}")
    if confidence is not None:
        print("  confidence threshold vs accuracy / pages kept:")
        for threshold in (0.0, 0.5, 0.7, 0.8, 0.9):
            kept = [(t == p) for t, p, c in zip(truth, predicted, confidence) if c >= threshold]
            if kept:
                print(f"    >= {threshold:.1f}: accuracy {sum(kept) / len(kept):.1%}, keeps {len(kept) / len(truth):.0%}")
    return accuracy, {s: sum(h) / len(h) for s, h in by_source.items()}


def main():
    rows = [r for r in csv.DictReader((DATA_DIR / "manifest.csv").open()) if r["split"] in ("train", "test")]
    vectors = embed_all([r["path"] for r in rows])

    train = [r for r in rows if r["split"] == "train"]
    test = [r for r in rows if r["split"] == "test"]
    X_train = np.array([vectors[r["path"]] for r in train])
    X_test = np.array([vectors[r["path"]] for r in test])
    y_train = [r["doc_type"] for r in train]
    y_test = [r["doc_type"] for r in test]

    # Zero-shot: no training, just "which description is this page closest to?"
    from fastembed import TextEmbedding

    text_model = TextEmbedding(SIGLIP_MODEL)
    labels = list(DOC_TYPES)
    label_vectors = np.array(list(text_model.embed([DOC_TYPES[t]["description"] for t in labels])))
    del text_model
    scores = X_test @ label_vectors.T
    zero_shot = [labels[i] for i in scores.argmax(axis=1)]
    zero_shot_accuracy, _ = report("ZERO-SHOT", test, y_test, zero_shot, None)

    # Trained: a logistic regression on top of the embeddings ("linear probe")
    best_c, best_score = None, -1
    for c in (0.5, 1, 2, 5, 10, 20):
        model = LogisticRegression(C=c, max_iter=3000, class_weight="balanced")
        score = cross_val_score(model, X_train, y_train, cv=5).mean()
        print(f"  C={c:<4} cross-validation accuracy {score:.1%}")
        if score > best_score:
            best_c, best_score = c, score
    head = LogisticRegression(C=best_c, max_iter=3000, class_weight="balanced").fit(X_train, y_train)

    probabilities = head.predict_proba(X_test)
    predicted = [head.classes_[p.argmax()] for p in probabilities]
    accuracy, by_source = report(f"TRAINED (C={best_c})", test, y_test, predicted, probabilities.max(axis=1))
    print("\n" + classification_report(y_test, predicted, digits=3, zero_division=0))

    joblib.dump(head, HEAD_FILE)
    HEAD_FILE.with_name("image_model_metrics.json").write_text(json.dumps({
        "zero_shot_accuracy": zero_shot_accuracy,
        "accuracy": accuracy,
        "accuracy_by_source": by_source,
        "C": best_c,
        "labels": list(head.classes_),
        "confusion_matrix": confusion_matrix(y_test, predicted, labels=list(head.classes_)).tolist(),
        "train_pages": len(train),
        "test_pages": len(test),
    }, indent=2))
    print(f"saved {HEAD_FILE.name} ({HEAD_FILE.stat().st_size / 1e3:.0f} KB)")


if __name__ == "__main__":
    main()
