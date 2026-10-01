"""Add pages from public datasets to the training data made by generate_samples.py.

    python training/prepare_public_data.py

Needs the files in training/public_data/ (git-ignored; see the URLs below):

- RVL-CDIP, 100 examples per class (real scanned office documents, research use):
  https://huggingface.co/datasets/jordyvl/rvl_cdip_100_examples_per_class
  Used for the "other" type. Its form, questionnaire, invoice and budget classes are
  skipped, because they look like our claim forms and bills and would teach the
  model that those are "other".
- MTSamples (real, de-identified medical transcriptions, Apache-2.0):
  https://huggingface.co/datasets/harishnair04/mtsamples
  Real doctors' wording, rendered with our page layouts and scan effects, for
  discharge summaries, radiology reports and consultation notes.

Pages are written next to the synthetic ones (training/data/<split>/<doc_type>/)
and added to manifest.csv with their source, so the evaluation can report how the
models do on real pages separately.
"""

import csv
import io
import random
import re
from pathlib import Path

import pandas as pd
from PIL import Image

from generate_samples import (OUT_DIR, TEST_FONTS, TRAIN_FONTS, degrade, doctor, heading, hospital, kv,
                              make_style, para, patient_fields, render_page, save, sign, title)

PUBLIC_DIR = Path(__file__).resolve().parent / "public_data"

RVL_CLASSES = ["letter", "form", "email", "handwritten", "advertisement", "scientific_report",
               "scientific_publication", "specification", "file_folder", "news_article", "budget",
               "invoice", "presentation", "questionnaire", "resume", "memo"]
RVL_SKIP = {"form", "questionnaire", "invoice", "budget"}
RVL_PER_CLASS = {"train": 12, "test": 6}  # 12 classes kept -> ~144 train / ~72 test "other" pages

MTSAMPLES_TYPES = {
    "Discharge Summary": "discharge_summary",
    "Radiology": "radiology_report",
    "Consult - History and Phy.": "consultation_notes",
    "SOAP / Chart / Progress Notes": "consultation_notes",
    "Office Notes": "consultation_notes",
    "Emergency Room Reports": "consultation_notes",
}
MTSAMPLES_LIMIT = {"train": 90, "test": 25}  # per doc type, to keep the classes balanced

TITLES = {"discharge_summary": "DISCHARGE SUMMARY", "radiology_report": "RADIOLOGY REPORT",
          "consultation_notes": "CONSULTATION NOTES"}


def rvl_pages(rows):
    for split, file in [("train", "rvl_train.parquet"), ("test", "rvl_test.parquet")]:
        df = pd.read_parquet(PUBLIC_DIR / file)
        for label, group in df.groupby("label"):
            name = RVL_CLASSES[label]
            if name in RVL_SKIP:
                continue
            for i, image in enumerate(group["image"].head(RVL_PER_CLASS[split])):
                page = Image.open(io.BytesIO(image["bytes"])).convert("RGB")
                path = OUT_DIR / split / "other" / f"rvl_{name}_{i:02d}.jpg"
                save(page, path)
                rows.append({"path": str(path.relative_to(OUT_DIR)), "split": split, "doc_type": "other",
                             "category": "other", "mode": "real_scan", "source": "rvl_cdip"})
        print(f"rvl_cdip {split}: done")


def transcription_blocks(text, doc_type, rng):
    # MTSamples puts section names in capitals followed by ":" ("HISTORY OF PRESENT ILLNESS:,")
    text = re.sub(r",\s*([A-Z][A-Z /]+:)", r"\n\1", text.replace(":,", ":"))
    blocks = [title(TITLES[doc_type]), kv(patient_fields(rng))]
    for part in [p.strip() for p in text.split("\n") if p.strip()][:12]:
        match = re.match(r"^([A-Z][A-Z /]{3,40}):\s*(.*)$", part)
        if match:
            blocks.append(heading(match.group(1).title()))
            if match.group(2).strip(" ,"):
                blocks.append(para(match.group(2).strip(" ,")[:700]))
        elif part.strip(" ,"):
            blocks.append(para(part.strip(" ,")[:700]))
    blocks.append(sign(doctor(rng)))
    return blocks


def mtsamples_pages(rows):
    df = pd.read_csv(PUBLIC_DIR / "mtsamples.csv").dropna(subset=["transcription"])
    df["medical_specialty"] = df["medical_specialty"].str.strip()
    df = df[df["medical_specialty"].isin(MTSAMPLES_TYPES)].sample(frac=1, random_state=11)
    df["doc_type"] = df["medical_specialty"].map(MTSAMPLES_TYPES)

    for doc_type, group in df.groupby("doc_type"):
        # The first rows go to test, the rest to train: no report is in both
        test_rows = group.head(MTSAMPLES_LIMIT["test"])
        train_rows = group.iloc[MTSAMPLES_LIMIT["test"]:].head(MTSAMPLES_LIMIT["train"])
        for split, part, fonts, seed in [("train", train_rows, TRAIN_FONTS, 21), ("test", test_rows, TEST_FONTS, 22)]:
            rng = random.Random(f"{seed}-{doc_type}")
            for i, text in enumerate(part["transcription"]):
                style = make_style(rng, fonts)
                page = render_page(hospital(rng), transcription_blocks(text, doc_type, rng), style, rng)
                mode = rng.choices(["digital", "scan", "photo"], weights=[0.35, 0.45, 0.2])[0]
                path = OUT_DIR / split / doc_type / f"mts_{i:03d}.jpg"
                save(degrade(page, rng, mode), path)
                rows.append({"path": str(path.relative_to(OUT_DIR)), "split": split, "doc_type": doc_type,
                             "category": "medical", "mode": mode, "source": "mtsamples"})
            print(f"mtsamples {split:5} {doc_type:20} {len(part)} pages")


def main():
    manifest = OUT_DIR / "manifest.csv"
    rows = [r for r in csv.DictReader(manifest.open()) if r.get("source", "synthetic") == "synthetic"]
    for row in rows:
        row["source"] = "synthetic"

    added = []
    rvl_pages(added)
    mtsamples_pages(added)

    with manifest.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["path", "split", "doc_type", "category", "mode", "source"])
        writer.writeheader()
        writer.writerows(rows + added)
    print(f"\nadded {len(added)} public pages, manifest now has {len(rows) + len(added)} rows")


if __name__ == "__main__":
    main()
