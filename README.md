# AI Document Intelligence

Upload medical reports, bills, insurance forms and ID proofs (PDF, DOCX, PNG, JPG) and chat with them.
The app reads the document (with OCR for scans and photos), sorts every page into a category
(Insurance, Medical, Financial, KYC, Other), and an LLM answers your questions with citations
that point to the page they came from.

## Features

- Login and register (JWT, Argon2 password hashing)
- Upload PDF, DOCX and images (up to 10 MB)
- Text extraction: digital PDFs, DOCX tables, and OCR for scanned PDFs and photos
- Hybrid search: meaning (embeddings + pgvector) plus exact words (PostgreSQL full-text search)
- Ask AI: RAG answers with citations, streamed word by word, with follow-up questions and saved chats.
  Clicking a citation jumps to that page and highlights it
- Page classification: every page gets one of 19 types (hospital bill, lab report, Aadhaar, claim form...)
  in 5 categories, from a text model and an image model combined. Unsure pages are marked "needs a look",
  blank or unreadable pages are caught
- Learns from your corrections: change a page's type and similar pages (in this file and in later
  uploads) follow your choice, without retraining
- Workspace UI: document list, live processing steps, page grid with a large page viewer, side chat,
  drag and drop anywhere, works on phones
- Free AI quota shown in the chat

## Tech stack

| Part | Tools |
|---|---|
| Frontend | React 19, TypeScript, Vite |
| Backend | Python, FastAPI, SQLAlchemy |
| Database | PostgreSQL + pgvector |
| OCR | Tesseract, Poppler (pdf2image), pypdf, python-docx |
| Embeddings | fastembed with `BAAI/bge-small-en-v1.5` (runs locally, 384 dimensions) |
| Page classifier | scikit-learn (TF-IDF + linear SVM on the OCR text), SigLIP 2 image embeddings (ONNX, via fastembed) + logistic regression |
| Migrations | Alembic (run automatically when the backend starts) |
| LLM | Any OpenAI-compatible API, set up for Groq `openai/gpt-oss-120b` (free tier) |

## How it works

```
Upload   →  extract text (OCR if needed)  →  chunks  →  embeddings  →  pgvector
         →  classify every page (text model + image model)  →  categories and page types
Question →  hybrid search (meaning + keywords)  →  top 5 chunks  →  LLM  →  streamed answer with page citations
```

## Page classification

| Category | Page types |
|---|---|
| Insurance | claim form, policy document, pre-authorisation form, health card |
| Medical | discharge summary, lab report, prescription, radiology report, consultation notes |
| Financial | hospital bill, pharmacy bill, payment receipt, cancelled cheque |
| KYC | Aadhaar, PAN card, passport, driving licence, voter ID |
| Other | anything else |

For every page ([`backend/classification/classify.py`](backend/classification/classify.py)):

1. No OCR text and the page is too dark, blank or blurred: **unreadable** page
2. The **text model** (TF-IDF on words and letter groups + linear SVM) reads the OCR text
3. The **image model** (SigLIP 2 embedding + logistic regression) looks at the page layout:
   tables, ID cards, letterheads. Pages with almost no text (ID cards, photos) are decided by it alone
4. Both are combined, trusting the model that is more sure. Below 60% confidence the page is
   marked **needs a look**
5. A page that looks like "other" right after a multi-page type (the last page of a bill) continues that type
6. A page that is almost the same as one **you corrected** (similarity of its text embedding ≥ 0.90) gets
   your type ([`memory.py`](backend/classification/memory.py)). Only your own corrections are used

Results on the test set (375 pages: fictional pages in fonts never used for training, plus real public
pages from RVL-CDIP and MTSamples), from [`ensemble_metrics.json`](backend/classification/model_files/ensemble_metrics.json):

| Model | Accuracy |
|---|---|
| Text model | 98.1% |
| Image model | 99.2% |
| Combined | 99.5% (100% on pages not marked "needs a look") |

These numbers are on mostly synthetic pages. Real documents from other hospitals and labs look
different, so expect lower accuracy on them; that is why pages can be corrected by hand.

### Retraining the models

The training data is generated, never taken from users. Everything lives in
[`backend/training/`](backend/training/) (the generated data itself is git-ignored):

```bash
cd backend
pip install -r training/requirements-training.txt
python training/generate_samples.py      # fictional pages for all 19 types, train + test
python training/prepare_public_data.py   # adds RVL-CDIP and MTSamples pages (see the file for downloads)
rm -f training/data/texts.jsonl training/data/image_embeddings.npz   # after regenerating pages
python training/build_dataset.py         # OCR every page, like the app does
python training/train_text.py            # text model    -> classification/model_files/
python training/train_image.py           # image model   -> classification/model_files/
python training/evaluate.py              # whole pipeline, failed pages and multi-page bundles
python -m classification.backfill        # classify documents uploaded before classification existed
```

To see what users correct (counts only, no document text):

```bash
python -m classification.correction_report      # inside Docker: docker compose exec backend python -m classification.correction_report
```

If a kind of page keeps being corrected, add more fictional examples of it to
`generate_samples.py` and retrain. Users' pages are never used as training data.

## Run with Docker (recommended)

You need [Docker](https://docs.docker.com/engine/install/) with Docker Compose.

```bash
cp .env.example .env        # then edit .env: passwords, SECRET_KEY, LLM_API_KEY
docker compose up --build
```

Open http://localhost:8080. The first build takes a few minutes (it installs OCR tools
and downloads the embedding model).

Three containers start:

| Container | What it does |
|---|---|
| `db` | PostgreSQL with pgvector. Data is kept in the `db-data` volume |
| `backend` | FastAPI on port 8000 (inside Docker only). Uploads are kept in the `uploads` volume |
| `frontend` | nginx on port 8080: serves the React app and forwards `/api/...` to the backend |

Useful commands:

```bash
docker compose logs -f backend    # see backend logs
docker compose down               # stop (data is kept)
docker compose down -v            # stop and DELETE all data and uploads
```

## Deploy to a server

Both guides use the same Docker setup, a free DuckDNS domain and automatic HTTPS with Caddy:

- [`deploy/DEPLOY-AWS.md`](deploy/DEPLOY-AWS.md): AWS EC2 (`t4g.small`), paid from the free plan credits
- [`deploy/DEPLOY-ORACLE.md`](deploy/DEPLOY-ORACLE.md): Oracle Cloud Always Free server (needs a Visa, Mastercard or Amex card)

## Run without Docker (development)

Needs Python 3.10+, Node 20+, PostgreSQL with [pgvector](https://github.com/pgvector/pgvector),
and `tesseract-ocr` + `poppler-utils` installed on the system.

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # then edit it
uvicorn main:app --reload         # http://localhost:8000, API docs at /docs

# Frontend (second terminal)
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

## Settings

| Variable | Where | Meaning |
|---|---|---|
| `DATABASE_URL` | backend | PostgreSQL connection string |
| `SECRET_KEY` | backend | Signs login tokens. Use a long random string |
| `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | backend | LLM provider. Free key: https://console.groq.com |
| `CORS_ORIGINS` | backend | Comma separated frontend addresses allowed to call the API (default `http://localhost:5173`) |
| `UPLOAD_DIR` | backend | Folder for uploaded files (default `backend/uploads`) |
| `ALLOW_REGISTRATION` | backend | `false` stops new sign-ups (use on a public server) |
| `DOMAIN` | docker-compose.prod.yml | Domain for HTTPS with Caddy |
| `VITE_API_URL` | frontend (build time) | Backend address (default `http://localhost:8000`, `/api` in Docker) |

## Test documents

[`sample-documents/`](sample-documents/) has fictional documents in every supported format,
with questions and expected answers in [`TEST_QUESTIONS.md`](sample-documents/TEST_QUESTIONS.md).

## Privacy

With Ask AI, the relevant parts of a document are sent to the LLM provider. Page classification and
the correction memory run on the server and send nothing out. Don't upload real
medical records to a public deployment. This project is a learning project and is not
hardened for sensitive data (no rate limiting, audit logs or data encryption at rest).
