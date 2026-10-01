"""Image classifier: SigLIP 2 turns a page image into 768 numbers that describe how
the page *looks* (tables, ID card, letterhead...), then a small trained classifier
picks the document type. Trained by training/train_image.py.

The SigLIP vision model needs about 800 MB of RAM, which is a lot for the 2 GB
server, so it's loaded only while pages are being classified and released after.
"""

import gc
from pathlib import Path

import numpy as np
from PIL import Image

SIGLIP_MODEL = "google/siglip2-base-patch16-224"
MODEL_DIR = Path(__file__).resolve().parent / "model_files"
HEAD_FILE = MODEL_DIR / "image_head.joblib"

# The model looks at 224 x 224 pixels, so a small page image is plenty
PAGE_IMAGE_SIZE = (600, 600)


def release_free_memory():
    # After the model is deleted, glibc's allocator keeps the freed memory for later
    # instead of giving it back (measured: ~320 MB stayed). malloc_trim returns it to
    # the operating system. Only exists on Linux with glibc, so ignore it elsewhere.
    try:
        import ctypes

        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


class ImageEmbedder:
    """Use as `with ImageEmbedder() as embedder:` to load SigLIP once for many pages."""

    def __enter__(self):
        from fastembed import ImageEmbedding

        self.model = ImageEmbedding(SIGLIP_MODEL)
        return self

    def __exit__(self, *exc):
        del self.model
        gc.collect()
        release_free_memory()


    def embed(self, images: list[Image.Image]) -> np.ndarray:
        prepared = []
        for image in images:
            image = image.convert("RGB")
            image.thumbnail(PAGE_IMAGE_SIZE)
            prepared.append(image)
        return np.array(list(self.model.embed(prepared, batch_size=16)))


_head = None


def load_head():
    global _head
    if _head is None:
        import joblib

        _head = joblib.load(HEAD_FILE)
    return _head


def predict_embedding(embedding: np.ndarray) -> dict[str, float]:
    """Probability for every document type from one page's SigLIP embedding."""
    head = load_head()
    probabilities = head.predict_proba(embedding.reshape(1, -1))[0]
    return {doc_type: float(p) for doc_type, p in zip(head.classes_, probabilities)}
