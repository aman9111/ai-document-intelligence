# AI Document Intelligence

Upload medical reports, bills and forms (PDF, DOCX, PNG, JPG) and chat with them.
The app reads the document (with OCR for scans and photos), finds the relevant parts,
and an LLM answers your questions with citations, streaming the answer as it writes.

## Features

- Login and register (JWT, Argon2 password hashing)
- Upload PDF, DOCX and images (up to 10 MB)
- Text extraction: digital PDFs, DOCX tables, and OCR for scanned PDFs and photos
- Hybrid search: meaning (embeddings + pgvector) plus exact words (PostgreSQL full-text search)
- Ask AI: RAG answers with citations, streamed word by word, with follow-up questions and saved chats
- Free AI quota shown in the chat

## Tech stack

| Part | Tools |
|---|---|
| Frontend | React 19, TypeScript, Vite |
| Backend | Python, FastAPI, SQLAlchemy |
| Database | PostgreSQL + pgvector |
| OCR | Tesseract, Poppler (pdf2image), pypdf, python-docx |
| Embeddings | fastembed with `BAAI/bge-small-en-v1.5` (runs locally, 384 dimensions) |
| LLM | Any OpenAI-compatible API, set up for Groq `openai/gpt-oss-120b` (free tier) |

## How it works

```
Upload  →  extract text (OCR if needed)  →  split into chunks  →  embeddings  →  pgvector
Question →  hybrid search (meaning + keywords)  →  top 5 chunks  →  LLM  →  streamed answer
```

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
| `VITE_API_URL` | frontend (build time) | Backend address (default `http://localhost:8000`, `/api` in Docker) |

## Test documents

[`sample-documents/`](sample-documents/) has fictional documents in every supported format,
with questions and expected answers in [`TEST_QUESTIONS.md`](sample-documents/TEST_QUESTIONS.md).

## Privacy

With Ask AI, the relevant parts of a document are sent to the LLM provider. Don't upload real
medical records to a public deployment. This project is a learning project and is not
hardened for sensitive data (no rate limiting, audit logs or data encryption at rest).
