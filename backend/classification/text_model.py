"""Text classifier: TF-IDF features + a linear SVM (the "Tesseract -> TF-IDF -> SVLinear"
path from the design). Trained by training/train_text.py, used by the app at runtime.
"""

import re
from functools import lru_cache
from pathlib import Path

MODEL_FILE = Path(__file__).resolve().parent / "model_files" / "text_model.joblib"

DIGIT = re.compile(r"\d")
SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    # Every digit becomes 0: "4521 8890 1234" -> "0000 0000 0000". The model learns
    # the *shape* of numbers (a 12 digit Aadhaar, a "Rs 0,000.00" amount) but never
    # stores real numbers, and a new number looks the same as the ones it trained on.
    return SPACES.sub(" ", DIGIT.sub("0", text.lower())).strip()


@lru_cache(maxsize=1)
def load_model():
    import joblib

    return joblib.load(MODEL_FILE)


def predict_text(text: str) -> dict[str, float]:
    """Probability for every document type, e.g. {"lab_report": 0.93, "prescription": 0.02, ...}."""
    model = load_model()
    probabilities = model.predict_proba([text])[0]
    return {doc_type: float(p) for doc_type, p in zip(model.classes_, probabilities)}
