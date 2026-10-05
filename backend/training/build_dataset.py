"""Read the text of every training page with OCR, the same way the app does.

    python training/build_dataset.py

Writes training/data/texts.jsonl: one {"path": ..., "hash": ..., "text": ...} line per page.
The text model (train.py) learns from this text, so it sees the same OCR mistakes
it will see in the app. Pages are processed in parallel, one per CPU core.

Pages are recognised by a hash of the image file, not by its name: a page that was
regenerated with different content is read again, an unchanged one comes from the
last run. So there is no need to delete anything after editing the generator.
"""

import csv
import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

# One Tesseract thread per process; we run many processes side by side instead
os.environ["OMP_THREAD_LIMIT"] = "1"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extraction import ocr_image  # noqa: E402
from PIL import Image  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"


def file_hash(path):
    return hashlib.sha1((DATA_DIR / path).read_bytes()).hexdigest()


def read_page(path):
    with Image.open(DATA_DIR / path) as image:
        return path, ocr_image(image.convert("RGB"))


def main():
    rows = list(csv.DictReader((DATA_DIR / "manifest.csv").open()))
    out_file = DATA_DIR / "texts.jsonl"

    hashes = {r["path"]: file_hash(r["path"]) for r in rows}

    # Text of every image read before, by content (lines without a hash are from
    # before hashing was added and are read again)
    known = {}
    if out_file.exists():
        known = {r["hash"]: r["text"] for r in map(json.loads, out_file.open()) if "hash" in r}
    todo = [path for path, h in hashes.items() if h not in known]
    print(f"{len(hashes) - len(todo)} pages unchanged since the last run, {len(todo)} to read")

    with ProcessPoolExecutor() as pool:
        for i, (path, text) in enumerate(pool.map(read_page, todo, chunksize=4), start=1):
            known[hashes[path]] = text
            if i % 100 == 0:
                print(f"  {i}/{len(todo)}", flush=True)

    # Written fresh with exactly the pages in the manifest, so nothing stale is left
    with out_file.open("w") as out:
        for path, h in hashes.items():
            out.write(json.dumps({"path": path, "hash": h, "text": known[h]}) + "\n")
    print("done")


if __name__ == "__main__":
    main()
