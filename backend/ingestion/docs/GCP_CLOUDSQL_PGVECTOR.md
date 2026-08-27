# Create & load Postgres + pgvector on GCP (Cloud SQL) - runbook

Target: **Cloud SQL for PostgreSQL** (managed), pgvector enabled, loaded from
`gs://kidspark-processed/Knowledge_chunks/`. You run the loader from your **local machine** through the
**Cloud SQL Auth Proxy**. The KidSpark app reads `POSTGRESQL_DATABASE_URL` / `POSTGRES_*` from `.env`
(via `app/core/config.py`), so once the proxy is up, `create_all_tables()` + the ingest run unchanged.

Project: `kidsstemproject`. Pick a region close to your GCS bucket, e.g. `us-central1`.

---

## 0. Prerequisites (once)

```bash
# gcloud CLI installed + authenticated
gcloud auth login
gcloud config set project kidsstemproject

# enable the APIs you need
gcloud services enable sqladmin.googleapis.com

# a local psql client (to verify) — Postgres Core distribution, or:
#   macOS:  brew install libpq && brew link --force libpq
#   Ubuntu: sudo apt-get install postgresql-client
```

---

## 1. Create the Cloud SQL instance (PG16 → pgvector 0.8)

```bash
gcloud sql instances create kidspark-pg \
  --database-version=POSTGRES_16 \
  --region=us-central1 \
  --tier=db-custom-2-8192 \          # 2 vCPU / 8 GB - bump for large embed loads
  --storage-size=20GB \
  --storage-auto-increase
```

Set the built-in admin password (the `postgres` user is a Cloud SQL superuser — used to enable the extension):

```bash
gcloud sql users set-password postgres \
  --instance=kidspark-pg \
  --password='CHOOSE_A_STRONG_ADMIN_PASSWORD'
```

---

## 2. Create the app database + user

```bash
gcloud sql databases create kidspark --instance=kidspark-pg

gcloud sql users create kidspark_app \
  --instance=kidspark-pg \
  --password='CHOOSE_A_STRONG_APP_PASSWORD'
```

Note the instance connection name (you need it for the proxy):

```bash
gcloud sql instances describe kidspark-pg --format='value(connectionName)'
# -> kidsstemproject:us-central1:kidspark-pg
```

---

## 3. Start the Cloud SQL Auth Proxy (local tunnel)

```bash
# download the proxy (Linux amd64 shown; pick your OS build from the releases page)
curl -o cloud-sql-proxy \
  https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.23.0/cloud-sql-proxy.linux.amd64
chmod +x cloud-sql-proxy

# open a tunnel: 127.0.0.1:5432 -> your instance  (leave this running in its own terminal)
./cloud-sql-proxy kidsstemproject:us-central1:kidspark-pg --port 5432
```

Now `127.0.0.1:5432` is your Cloud SQL instance.

---

## 4. Enable pgvector (once, as the admin user)

```bash
PGPASSWORD='CHOOSE_A_STRONG_ADMIN_PASSWORD' \
psql -h 127.0.0.1 -p 5432 -U postgres -d kidspark -c "CREATE EXTENSION IF NOT EXISTS vector;"

# confirm version is >= 0.7 (needed for halfvec + the HNSW halfvec index this schema uses)
PGPASSWORD='CHOOSE_A_STRONG_ADMIN_PASSWORD' \
psql -h 127.0.0.1 -p 5432 -U postgres -d kidspark -c "SELECT extversion FROM pg_extension WHERE extname='vector';"
```

(Cloud SQL–created users are members of `cloudsqlsuperuser`, so `kidspark_app` can also create extensions —
but doing it once as `postgres` is cleanest.)

---

## 5. Point `.env` at the proxy

Edit `.env` so the app connects through the tunnel instead of your local Docker DB:

```dotenv
POSTGRES_HOST='127.0.0.1'
POSTGRES_PORT='5432'
POSTGRES_DB='kidspark'
POSTGRES_USER='kidspark_app'
POSTGRES_PASSWORD='<set-via-secret-manager>'
```

`app/core/config.py` builds `POSTGRESQL_DATABASE_URL` from these (the user/password are **percent-encoded**,
so special characters like `#` are safe). Or set one explicit URL, which takes precedence over the pieces:

```dotenv
POSTGRESQL_DATABASE_URL='postgresql+psycopg://kidspark_app:CHOOSE_A_STRONG_APP_PASSWORD@127.0.0.1:5432/kidspark'
```

Also make sure these are set (already in your `.env`):

```dotenv
OPENAI_API_KEY='...'                       # needed to embed nodes + queries
GCP_PROJECT_ID='kidsstemproject'
GCS_PROCESSED_BUCKET='kidspark-processed'
GOOGLE_APPLICATION_CREDENTIALS='...json'   # service account with GCS read for the ingest
```

---

## 6. Create the star schema on Cloud SQL

`create_all_tables()` (in `app/api/models/model_init.py`) runs `CREATE EXTENSION IF NOT EXISTS vector`,
creates `document_bundle` / `pdf_node` / `standard_rules`, and builds the halfvec HNSW + GIN indexes.

```bash
python -c "from app.api.models.model_init import create_all_tables; create_all_tables()"
```

Verify (Windows-friendly helper prints tables, pgvector version, and counts):

```bash
python check_db.py
#   or, with psql:
psql -h 127.0.0.1 -p 5432 -U kidspark_app -d kidspark -c "\dt"
psql -h 127.0.0.1 -p 5432 -U kidspark_app -d kidspark -c "\di"    # halfvec HNSW + GIN indexes
```

Note: starting the API also creates the schema — `create_app()` calls `create_all_tables()` at startup.

---

## 7. Load the processed bundles from GCS → Cloud SQL

Ingestion **streams** each bundle from `gs://kidspark-processed/Knowledge_chunks/bundles/` into the star
schema (artifacts are read into memory — nothing is written to local disk). Each bundle becomes one
`document_bundle` row + its own `pdf_node` rows + its unit `standard_rules`, never concatenated.

**Option A - CLI (headless):**

```bash
python -m app.services.ingest             # stream + embed + load all bundles from GCS
python -m app.services.ingest --no-embed  # load rows without embeddings (schema smoke test)
```

**Option B - API endpoint.** Start the app (now pointed at Cloud SQL via `.env`) and call `/ingest`:

```bash
uvicorn app.main:app --port 8080
curl -X POST http://localhost:8080/api/v1/ingest -H "Content-Type: application/json" -d "{\"embed\": true}"
```

Under the hood both call `repository.load_knowledge_from_gcs()`, which reads each bundle with
`download_as_text()` and commits per bundle, so bundles stay individual and traceable
(`pdf_node.bundle_id → document_bundle.bundle_id`).

---

## 8. Verify the load

```bash
python check_db.py     # counts + embedded-vs-total + distinct grade_band/unit + a sample node
```

Or directly with psql:

```bash
psql -h 127.0.0.1 -p 5432 -U kidspark_app -d kidspark -c "
SELECT
  (SELECT count(*) FROM document_bundle) AS bundles,
  (SELECT count(*) FROM pdf_node)         AS nodes,
  (SELECT count(*) FROM pdf_node WHERE embedding IS NOT NULL) AS embedded,
  (SELECT count(*) FROM standard_rules)   AS rules;"

# no orphan nodes (every node traces to a bundle)
psql -h 127.0.0.1 -p 5432 -U kidspark_app -d kidspark -c "
SELECT count(*) AS orphans FROM pdf_node n
LEFT JOIN document_bundle b ON b.bundle_id = n.bundle_id WHERE b.bundle_id IS NULL;"
```

Run a context-aware retrieval end-to-end (use an exact `grade_band` from `check_db.py`):

```bash
python -c "from app.services import repository; import json; print(json.dumps(repository.retrieve_from_db('build and invent with blocks', filters={'grade_band':'Grades Pre-K - 1st (Early Elementary Program Grades Pre-K - 1st)'}, k=20, seed_k=5, hybrid=True)['seeds'], indent=2)[:800])"
```

Or hit the API: `POST /api/v1/retrieve` with `{ "grade_band": "<exact value>", "prompt": "inventing with blocks" }`.

---

## 9. Production / ongoing notes

- **Running in GCP later:** for Cloud Run / a GCE loader, use the instance's **private IP** (no proxy)
  or the Auth Proxy sidecar, and prefer **IAM database authentication** over a password.
- **Big loads:** embedding every node calls OpenAI per node — expect time + token cost on the first full
  run. Bump the instance tier (CPU/RAM) while loading, then scale down.
- **Index tuning:** after a large load, `ANALYZE pdf_node;`. HNSW build memory scales with rows; raise
  `maintenance_work_mem` on the instance for faster index builds.
- **Backups:** enable automated backups + PITR (`--backup-start-time`, `--enable-point-in-time-recovery`).
- **Security:** never commit `.env`. Store the DB password / OpenAI key in **Secret Manager** and inject
  them as environment variables (Cloud Run supports mounting secrets as env vars, which
  `app/core/config.py` reads directly).
- **Teardown of local Docker:** the local `docker-compose` pgvector is no longer the target once `.env`
  points at Cloud SQL; keep it for offline dev or `docker compose down`.
