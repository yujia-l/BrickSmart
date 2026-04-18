# KidSpark AI — Backend

FastAPI backend for the KidSpark AI lesson generation system. This service runs on GCP Cloud Run and provides:

- **Ingestion Pipeline** (Developer A): Parses Kid Spark lesson PDFs into structured, searchable knowledge nodes with vector embeddings.
- **Agent Pipeline** (Developer B): Multi-stage AI pipeline that guides teachers through lesson creation using a consultation loop, block awareness step, and automated generation.

## Setup

```bash
cd backend
pip install -r requirements.txt
```

## Running Locally

```bash
uvicorn api.main:app --reload --port 8000
```

## Environment Variables

See `config.py` for all required GCP configuration. Copy `.env.example` to `.env` for local development.

## Project Structure

```
backend/
  config.py          # Shared GCP config
  models/            # Pydantic models + SQLAlchemy tables (SHARED)
  ingestion/         # Dev A — document parsing, extraction, embedding
  retrieval/         # Dev B builds, both use — hybrid search + bundle expansion
  agents/            # Dev B — consultation, block awareness, generation pipeline
  api/               # Dev B — FastAPI endpoints
  migrations/        # Alembic DB migrations
  tests/             # Split by domain
```

## Reference

See `KIDSPARK_TECHNICAL_SPEC.md` in the project root for the full technical specification.
