# KidSpark Backend

FastAPI orchestration for the six-step teacher flow:

1. Upload Story
2. Plan With KidSpark Coach
3. Review Model Preview
4. Review Segments and Connectors
5. Review Build Plan
6. Review Lesson Bundle

## Architecture

```text
api/               FastAPI routes and readiness
agents/            story analysis, teacher coach, planning state, orchestration
llm/               Vertex Gemini primary/fallback adapter
retrieval/         bounded teacher-turn RAG provider and grade normalization
ingestion/app/     Docling/Gemini/GCS/pgvector ingestion and retrieval service
build3d/           Rodin, Bang, notebook physicalization, validated planner
documents/         lesson plan, activity guide, and slide companion generation
models/            shared Pydantic runtime contracts
```

The combined Cloud Run container starts this API on localhost port 8001 and
Streamlit on the public port. The Streamlit page calls the API through
`KIDSPARK_BACKEND_URL`.

## Models

- Gemini primary: `gemini-3.6-flash` in Vertex `global`
- Gemini fallback: `gemini-3.5-flash` in Vertex `global`
- Text embeddings: `gemini-embedding-001`, 3072 dimensions, `us-central1`
- Selective visual embeddings: `multimodalembedding@001`, 1408 dimensions

Application Default Credentials are used locally by default. Cloud Run can use
its service account directly, or receive a service-account-bound Vertex
authorization key through Secret Manager as `GEMINI_API_KEY`. The KidSpark UI
does not accept, display, or persist model credentials.

## Retrieval

Every story analysis and teacher-planning turn passes through
`retrieval/provider.py`. It normalizes the grade, performs bounded hybrid
retrieval, stores source trace IDs on the session, and falls back to static
reference material when the database is unavailable.

See [retrieval/README.md](retrieval/README.md) for the data contract, migration,
and smoke-test instructions.

## Local Run

From the repository root:

```bash
python -m pip install -r requirements.txt
python cloudrun_start.py
```

Or run the API independently:

```bash
cd backend
uvicorn api.main:app --host 127.0.0.1 --port 8001
```

Copy `.env.example` to `.env` for local settings. Do not commit the populated
file, database passwords, API keys, or service-account JSON.

## Health

```text
GET /health
GET /health/ready
GET /api/v1/settings/runtime
```

Readiness reports the Vertex model contract and pgvector schema/data status.
Set `DATABASE_REQUIRED=true` in Cloud Run so a missing production database is
reported as degraded. Keep it false for offline UI and unit-test work.

## Tests

```bash
pytest backend/tests
pytest tests/validated
```

Default tests use offline/fake model and retrieval providers. Live Vertex,
Cloud SQL, Rodin, and browser validation are explicit release checks because
they use external services and may consume credits.

## Deployment

The canonical GCP project is `kidspark-499901`, with Cloud Run and Cloud SQL in
`us-central1`. See [../DEPLOYMENT_GCP.md](../DEPLOYMENT_GCP.md).
