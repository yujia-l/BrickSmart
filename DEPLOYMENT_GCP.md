# KidSpark GCP Deployment

Target project: `kidspark-499901`

The root container runs Streamlit on Cloud Run's public port and FastAPI on
localhost port 8001. Gemini uses Vertex AI. Teacher-turn retrieval connects
directly to Cloud SQL pgvector unless `KIDSPARK_RAG_SERVICE_URL` points at a
separate ingestion/RAG service.

## One-Time Project Setup

```bash
gcloud config set project kidspark-499901
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  apikeys.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com \
  storage.googleapis.com
```

The hosted service uses
`kidspark-runtime@kidspark-499901.iam.gserviceaccount.com`. It needs these
runtime roles:

- Vertex AI User
- Cloud SQL Client
- Storage Object Viewer
- Secret Manager Secret Accessor
- Logs Writer
- Monitoring Metric Writer

Do not upload a service-account JSON key or set
`GOOGLE_APPLICATION_CREDENTIALS` in Cloud Run.

## Secrets

Create or update Secret Manager values without placing them on a command line
or in Git:

```bash
gcloud secrets create kidspark-db-url --replication-policy=automatic
gcloud secrets create hyper3d-api-key --replication-policy=automatic
gcloud secrets create gemini-api-key --replication-policy=automatic
```

`gemini-api-key` contains an authorization key bound to the KidSpark runtime
service account and restricted to `aiplatform.googleapis.com`. The application
uses it when `GEMINI_API_KEY` is present and otherwise falls back to Application
Default Credentials. Keep non-sensitive model names, locations, limits, and
feature flags as Cloud Run environment variables rather than Secret Manager
values.

Cloud Run's database URL uses the Cloud SQL Unix socket:

```text
postgresql+psycopg://USER:PASSWORD@/kidspark?host=/cloudsql/kidspark-499901:us-central1:kidspark-db
```

## Database

Apply:

```text
backend/ingestion/postgres/migrations/2026-07-vertex-rag-v1.sql
```

Load rows first, then perform a resumable Vertex embedding backfill.
Re-embedding is intentional; old OpenAI vectors are not part of the production
contract:

```bash
set PYTHONPATH=backend/ingestion
python -m app.services.ingest --no-embed
python -m app.services.ingest --backfill-only --max-embeddings 100
```

The measured `gemini-embedding-001` online-prediction quota in `us-central1`
is five requests per minute. The checked-in default uses four. A quota increase
is required before the full 24,279-node corpus can be re-embedded in a
reasonable production migration window. Backfill commits each batch, so jobs
can be resumed safely.

The processed bucket currently has no persisted image crops. Reprocess source
PDFs with `SAVE_IMAGE_CROPS=true` to populate selective visual embeddings for
parts diagrams, build steps, example builds, and instructional diagrams.

Required verification:

```sql
SELECT extversion FROM pg_extension WHERE extname = 'vector';
SELECT count(*) FROM document_bundle;
SELECT count(*) FROM pdf_node;
SELECT count(*) FROM pdf_node WHERE embedding IS NOT NULL;
SELECT count(*) FROM standard_rules;
SELECT DISTINCT grade_band FROM pdf_node ORDER BY grade_band;
```

## Deploy

Replace the service name only if the team chooses a different canonical name:

```bash
gcloud run deploy kidspark \
  --source . \
  --project kidspark-499901 \
  --region us-central1 \
  --allow-unauthenticated \
  --service-account kidspark-runtime@kidspark-499901.iam.gserviceaccount.com \
  --port 8080 \
  --memory 4Gi \
  --cpu 2 \
  --timeout 3600 \
  --min-instances 0 \
  --max-instances 4 \
  --add-cloudsql-instances kidspark-499901:us-central1:kidspark-db \
  --set-env-vars GCP_PROJECT_ID=kidspark-499901,VERTEX_GENERATION_LOCATION=global,VERTEX_EMBEDDING_LOCATION=us-central1,GEMINI_PRIMARY_MODEL=gemini-3.6-flash,GEMINI_FALLBACK_MODEL=gemini-3.5-flash,KIDSPARK_RAG_ENABLED=true,KIDSPARK_RAG_TIMEOUT_SECONDS=10,RAG_QUERY_UNDERSTANDING_ENABLED=false,DATABASE_REQUIRED=true,GCS_BUCKET_NAME=kidspark-project-data,GCS_PROCESSED_BUCKET=kidspark-data-processed,EMBED_MODEL=gemini-embedding-001,EMBED_DIM=3072,EMBED_REQUESTS_PER_MINUTE=4 \
  --set-secrets POSTGRESQL_DATABASE_URL=kidspark-db-url:latest,HYPER3D_API_KEY=hyper3d-api-key:latest,GEMINI_API_KEY=gemini-api-key:latest
```

Rodin/Bang/notebook processing can be CPU and memory intensive, which is why
the initial deployment uses 2 CPU, 4 GiB, and a one-hour request timeout.
Resource limits can be tuned after observing real traces.

## Validate

```bash
gcloud run services describe kidspark \
  --project kidspark-499901 \
  --region us-central1 \
  --format="value(status.url)"

gcloud run services logs read kidspark \
  --project kidspark-499901 \
  --region us-central1 \
  --limit 100
```

Check `/health`, `/health/ready`, and `/api/v1/settings/runtime`. The runtime
settings response must report `provider=vertex_ai`, `configured=true`, and the
expected non-sensitive `auth_mode`. Then check `/kidspark`, one teacher planning turn, one
model preview, one validated build, and all three PDF downloads before routing
team demos to the revision.
