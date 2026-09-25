# Backend: FastAPI + OCR tools + local embedding model
FROM python:3.10-slim

# Tesseract reads text from images (OCR), Poppler turns PDF pages into images
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_PATH=/app/models \
    UPLOAD_DIR=/app/uploads

# Install packages first, so Docker can reuse this layer when only code changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the embedding model now, so the container doesn't need to on first use
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

COPY . .

# Don't run as root inside the container
RUN useradd --create-home appuser \
    && mkdir -p /app/uploads \
    && chown -R appuser /app/uploads /app/models
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
