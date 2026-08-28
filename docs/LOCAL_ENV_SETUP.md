# KidSpark Local Environment Setup

This guide lists the environment variables teammates need to run KidSpark AI locally. It is intentionally safe to commit: every secret below is a placeholder, not a working credential.

> **Never commit a populated `.env`, service-account JSON file, database password, Gemini key, or Hyper3D key.** The repository `.gitignore` already excludes these files. Obtain secrets through the project administrator or Google Secret Manager.

## Quick Start

The main application loads its local environment from `backend/.env`. From the repository root:

```powershell
Copy-Item .env.example backend/.env
```

If you will also run the standalone ingestion commands from the repository root, create a second local copy because that service reads `.env` from its current working directory:

```powershell
Copy-Item .env.example .env
```

Keep the two local files synchronized when changing shared GCP, database, embedding, or storage settings.

## Full Local Application Template

Place this block in `backend/.env`. Replace values enclosed in angle brackets. Values already filled in are non-secret project defaults.

```dotenv
# -----------------------------------------------------------------------------
# KidSpark application
# -----------------------------------------------------------------------------
ENV=development
LOG_LEVEL=INFO
KIDSPARK_BACKEND_URL=http://127.0.0.1:8001
KIDSPARK_OFFLINE_MODE=false

# -----------------------------------------------------------------------------
# Gemini on Vertex AI
# Preferred local authentication is Application Default Credentials (ADC).
# Leave GEMINI_API_KEY blank when using ADC.
# -----------------------------------------------------------------------------
LLM_PROVIDER=vertex
GCP_PROJECT_ID=kidspark-499901
GOOGLE_CLOUD_PROJECT=kidspark-499901
GCP_REGION=us-central1
VERTEX_GENERATION_LOCATION=global
VERTEX_EMBEDDING_LOCATION=us-central1
GEMINI_PRIMARY_MODEL=gemini-3.6-flash
GEMINI_FALLBACK_MODEL=gemini-3.5-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
GEMINI_VISUAL_EMBEDDING_MODEL=multimodalembedding@001
VISUAL_EMBEDDING_DIMENSIONS=1408

# Optional alternative to ADC. Obtain from Secret Manager/project admin.
GEMINI_API_KEY=<GEMINI_VERTEX_API_KEY_OR_LEAVE_BLANK_FOR_ADC>

# Optional alternative to ADC for an approved local service-account file.
# Prefer ADC. Never place the JSON file inside the repository.
GOOGLE_APPLICATION_CREDENTIALS=<ABSOLUTE_PATH_TO_APPROVED_SERVICE_ACCOUNT_JSON_OR_LEAVE_BLANK>

# -----------------------------------------------------------------------------
# Hyper3D Rodin and Bang (required for live 3D generation and segmentation)
# -----------------------------------------------------------------------------
HYPER3D_API_KEY=<HYPER3D_API_KEY>
HYPER3D_BASE_URL=https://api.hyper3d.com/api/v2
RODIN_TIER=Gen-2.5-Low
RODIN_QUALITY=extra-low
RODIN_MESH_MODE=Raw
RODIN_GEOMETRY_FILE_FORMAT=obj
RODIN_MATERIAL=None
BANG_STRENGTH=5
BANG_RESOLUTION=Basic

# -----------------------------------------------------------------------------
# Teacher-planning RAG
# Use either direct Cloud SQL access or KIDSPARK_RAG_SERVICE_URL, not both.
# When the service URL is blank, KidSpark uses POSTGRESQL_DATABASE_URL directly.
# -----------------------------------------------------------------------------
KIDSPARK_RAG_ENABLED=true
KIDSPARK_RAG_TIMEOUT_SECONDS=10
KIDSPARK_RAG_RESULT_LIMIT=8
KIDSPARK_RAG_CACHE_TTL_SECONDS=600
KIDSPARK_RAG_SERVICE_URL=
RAG_QUERY_UNDERSTANDING_ENABLED=false
DATABASE_REQUIRED=false

# Direct local Cloud SQL Auth Proxy connection.
# URL-encode reserved characters in USER and PASSWORD.
POSTGRESQL_DATABASE_URL=postgresql+psycopg://<DB_USER>:<URL_ENCODED_DB_PASSWORD>@127.0.0.1:<PROXY_PORT>/kidspark

# Used by async application modules that consume backend/config.py directly.
DATABASE_URL=postgresql+asyncpg://<DB_USER>:<URL_ENCODED_DB_PASSWORD>@127.0.0.1:<PROXY_PORT>/kidspark

# -----------------------------------------------------------------------------
# Google Cloud Storage
# -----------------------------------------------------------------------------
GCS_BUCKET_NAME=kidspark-project-data
GCS_PROCESSED_BUCKET=kidspark-data-processed
KNOWLEDGE_PREFIX=Knowledge_chunks
GCS_RAW_BUCKET=kidspark-raw-files
GCS_ASSETS_BUCKET=kidspark-assets

# -----------------------------------------------------------------------------
# Embedding and selective visual retrieval
# -----------------------------------------------------------------------------
EMBED_MODEL=gemini-embedding-001
EMBED_DIM=3072
EMBED_WORKERS=2
EMBED_REQUESTS_PER_MINUTE=4
VISION_MODEL=gemini-3.6-flash
VISION_FALLBACK_MODEL=gemini-3.5-flash
VISUAL_EMBED_MODEL=multimodalembedding@001
VISUAL_EMBED_DIM=1408
VISUAL_EMBED_ROLES=parts_diagram,build_step,example_build,diagram
SAVE_IMAGE_CROPS=true

# -----------------------------------------------------------------------------
# Production-only secret loading. Keep false for normal local development.
# -----------------------------------------------------------------------------
USE_SECRET_MANAGER=false

# -----------------------------------------------------------------------------
# Legacy compatibility only. Current KidSpark does not require OpenAI.
# -----------------------------------------------------------------------------
OPENAI_API_KEY=
OPENAI_KEY=
OPENAI_MODEL=gpt-4o
```

### If RAG Is Exposed as a Service

When the retrieval service is already deployed, replace the direct database configuration with its base URL:

```dotenv
KIDSPARK_RAG_SERVICE_URL=https://<RAG_SERVICE_HOST>
POSTGRESQL_DATABASE_URL=
DATABASE_URL=
DATABASE_REQUIRED=false
```

The current retrieval client calls `POST <KIDSPARK_RAG_SERVICE_URL>/api/v1/retrieve`. If the service requires authentication, the current app will also need the agreed authentication adapter; a private URL alone is not sufficient.

## Authentication

### Recommended: Application Default Credentials

Use your Jacobs Institute/project Google identity:

```powershell
gcloud auth login
gcloud auth application-default login
gcloud config set project kidspark-499901
```

Then leave these values empty in `backend/.env`:

```dotenv
GEMINI_API_KEY=
GOOGLE_APPLICATION_CREDENTIALS=
```

ADC requires the signed-in identity to have the relevant project permissions, typically Vertex AI User and access to the required GCS objects. Direct Cloud SQL use also requires Cloud SQL Client access.

### Approved Service-Account File

Use this only when the project administrator has explicitly supplied a local-development credential:

```dotenv
GOOGLE_APPLICATION_CREDENTIALS=C:\Users\<YOU>\secrets\kidspark-local.json
```

Store the file outside the repository. Do not use a service-account JSON file in Cloud Run; the deployed service uses its attached runtime service account.

### Gemini Vertex API Key

The app supports a service-account-bound Vertex authorization key:

```dotenv
GEMINI_API_KEY=<VALUE_FROM_SECRET_MANAGER>
```

If this is set, it takes precedence over ADC for Gemini calls. It does not replace GCP credentials needed for GCS or Cloud SQL.

## Cloud SQL Auth Proxy

For direct local RAG, start the Cloud SQL Auth Proxy before starting KidSpark. The canonical instance is:

```text
kidspark-499901:us-central1:kidspark-db
```

Example:

```powershell
cloud-sql-proxy.exe kidspark-499901:us-central1:kidspark-db --port <PROXY_PORT>
```

Use the same port in `POSTGRESQL_DATABASE_URL` and `DATABASE_URL`. Obtain the database username and password from the project administrator or the approved Secret Manager secrets. Do not paste the password into documentation, issues, chat transcripts, or shell history.

## Optional Ingestion Configuration

These settings are needed only by teammates loading or reprocessing the curriculum corpus. Add them to the repository-root `.env` used by `backend/ingestion`:

```dotenv
# Service metadata
PROJECT_NAME=KidSpark RAG Backend
VERSION=1.0.0
API_V1_STR=/api/v1
CORS_ORIGINS=["*"]
DEBUG=true

# Cloud SQL; either use the complete URL above or every split field below.
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=<PROXY_PORT>
POSTGRES_DB=kidspark
POSTGRES_USER=<DB_USER>
POSTGRES_PASSWORD=<DB_PASSWORD>

# GCS source and processed corpus
GCS_BUCKET_NAME=kidspark-project-data
GCS_PREFIX=
GCS_PROCESSED_BUCKET=kidspark-data-processed
RAW_PREFIX=Data
KNOWLEDGE_PREFIX=Knowledge_chunks
KNOWLEDGE_LOCAL_DIR=

# Text chunking
CHUNK_MAX_CHARS=800
CHUNK_OVERLAP=120
CHUNK_MIN_CHARS=15

# Embeddings and image processing
EMBED_MODEL=gemini-embedding-001
EMBED_DIM=3072
EMBED_WORKERS=2
EMBED_REQUESTS_PER_MINUTE=4
VISION_MODEL=gemini-3.6-flash
VISION_FALLBACK_MODEL=gemini-3.5-flash
VISUAL_EMBED_MODEL=multimodalembedding@001
VISUAL_EMBED_DIM=1408
VISUAL_EMBED_ROLES=parts_diagram,build_step,example_build,diagram
SAVE_IMAGE_CROPS=true

# Retrieval reranking
RERANKER=cross_encoder
RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
RERANK_POOL=20

# PDF extraction
DOCLING_OCR=true
DOCLING_TABLES=true
DOCLING_IMAGE_SCALE=2.0
MANIFEST_PATH=Data/kidspark_manifest.csv
PROC_VERSION=2.0-vertex

# Ingestion logging
KSRAG_LOG_LEVEL=INFO
KSRAG_LOG_FILE=
```

## Offline or Saved-Output Testing

Use this mode when testing the UI, session gates, voxelization, validated planning, or document generation without calling Gemini, Rodin, Bang, or Cloud SQL:

```dotenv
KIDSPARK_OFFLINE_MODE=true
KIDSPARK_RAG_ENABLED=false
DATABASE_REQUIRED=false
GEMINI_API_KEY=
HYPER3D_API_KEY=
POSTGRESQL_DATABASE_URL=
DATABASE_URL=
```

Offline mode is useful for regression testing, but it does not prove that live model, database, GCS, or Hyper3D permissions are working.

## Where Each Secret Comes From

| Secret or credential | Needed for | Obtain from |
|---|---|---|
| Google ADC login | Vertex AI, GCS, and optionally Cloud SQL Proxy | Your authorized Google project identity |
| `GEMINI_API_KEY` | Optional Gemini authentication instead of ADC | `gemini-api-key` in Secret Manager or project administrator |
| `HYPER3D_API_KEY` | Live Rodin generation and Bang segmentation | `hyper3d-api-key` in Secret Manager or project administrator |
| Database username/password or URL | Direct pgvector retrieval and ingestion | `kidspark-db-url` in Secret Manager or database administrator |
| Service-account JSON | Exceptional approved local automation only | Project administrator; store outside the repository |

## Start and Verify

Install dependencies and run the combined local application:

```powershell
python -m pip install -r requirements.txt
python cloudrun_start.py
```

`cloudrun_start.py` starts FastAPI at `http://127.0.0.1:8001` and Streamlit on port `8080` unless `PORT` is overridden. Open:

```text
http://127.0.0.1:8080/kidspark
```

For the familiar Streamlit development port instead:

```powershell
$env:PORT = "8501"
python cloudrun_start.py
```

Verify the backend before beginning a live run:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
Invoke-RestMethod http://127.0.0.1:8001/health/ready
Invoke-RestMethod http://127.0.0.1:8001/api/v1/settings/runtime
```

Expected runtime indicators include:

- `provider` identifies Vertex AI.
- `configured` is true for Gemini.
- The primary and fallback models match the values above.
- Database readiness is healthy when `DATABASE_REQUIRED=true`.
- No secret value is returned by a settings or health endpoint.

## Common Configuration Mistakes

| Symptom | Check |
|---|---|
| Gemini reports missing credentials | Run `gcloud auth application-default login`, or set the approved `GEMINI_API_KEY` |
| Gemini works but RAG falls back to static evidence | Start Cloud SQL Auth Proxy and verify `POSTGRESQL_DATABASE_URL`, or set a reachable `KIDSPARK_RAG_SERVICE_URL` |
| GCS access is denied | Confirm ADC/project identity and bucket access in `kidspark-499901` |
| Rodin or Bang is unavailable | Confirm `HYPER3D_API_KEY` and the Hyper3D account quota |
| App ignores edited values | Confirm the main runtime values are in `backend/.env`, then restart both processes |
| Password breaks the database URL | Percent-encode reserved characters, or use the split `POSTGRES_*` fields for ingestion |
| Ingestion cannot see its settings | Confirm a root `.env` exists when running ingestion from the repository root |

## Final Safety Check

Before committing or sharing changes:

```powershell
git status --short
git check-ignore backend/.env .env
git diff -- . ':!*.env'
```

Both `.env` paths should be reported as ignored. Never use `git add -f` on an environment or credential file.
