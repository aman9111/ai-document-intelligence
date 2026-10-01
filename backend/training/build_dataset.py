"""Read the text of every training page with OCR, the same way the app does.

    python training/build_dataset.py

Writes training/data/texts.jsonl: one {"path": ..., "text": ...} line per page.
The text model (train.py) learns from this text, so it sees the same OCR mistakes
it will see in the app. Pages are processed in parallel, one per CPU core.
"""

import csv
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


def read_page(path):
    with Image.open(DATA_DIR / path) as image:
        return path, ocr_image(image.convert("RGB"))


def main():
    rows = list(csv.DictReader((DATA_DIR / "manifest.csv").open()))
    out_file = DATA_DIR / "texts.jsonl"

    done = {}
    if out_file.exists():  # resume: keep pages already read
        done = {r["path"]: r["text"] for r in map(json.loads, out_file.open())}
    todo = [r["path"] for r in rows if r["path"] not in done]
    print(f"{len(done)} pages already read, {len(todo)} to go")

    with out_file.open("a") as out, ProcessPoolExecutor() as pool:
        for i, (path, text) in enumerate(pool.map(read_page, todo, chunksize=4), start=1):
            out.write(json.dumps({"path": path, "text": text}) + "\n")
            if i % 100 == 0:
                print(f"  {i}/{len(todo)}", flush=True)
    print("done")


if __name__ == "__main__":
    main()
