# KidSpark AI — Backend

FastAPI backend for the KidSpark AI lesson generation system. This service runs on GCP Cloud Run and provides:

- **Ingestion Pipeline** (Developer A): Parses Kid Spark lesson PDFs into structured, searchable knowledge nodes with vector embeddings.
- **Agent Pipeline** (Developer B): Multi-stage AI pipeline that guides teachers through lesson creation using a consultation loop, block awareness step, and automated generation.

---

## Backend folder structure and developer branches

This section captures the **planning-stage** layout for Phase 1: how the backend sits next to BrickSmart, how directories split work between two developers, and how Git branches are used. The repo is a **single** repository; `dev/ingestion` and `dev/runtime` are two branches off `deploy`, not separate repos.

### Current state (repo root)

The existing BrickSmart app stays as-is. The KidSpark backend lives entirely under `backend/`:

```
BrickSmart/
  home.py              # Streamlit entry
  streaming.py
  pages/               # step1–3 UI
  utils/
  structured_query/
  database/            # static JSON (e.g. spatial_dim.json)
  .streamlit/
  Dockerfile           # Streamlit container (root)
  requirements.txt     # Streamlit app deps

  # --- KidSpark backend (new) ---
  backend/             # everything below
```

We do **not** change the Streamlit layout for Phase 1; we add and evolve only `backend/`.

### Proposed folder structure (high-level)

```
backend/
  README.md                      # This file — setup + architecture overview
  requirements.txt               # Backend-only Python deps (separate from root requirements.txt)
  Dockerfile                     # FastAPI image for Cloud Run
  alembic.ini                    # Alembic entry config
  config.py                      # Shared GCP config (DB URL, GCS, secrets)

  migrations/
    env.py                         # Alembic environment (wire to SQLAlchemy models)
    versions/                      # Generated migration scripts

  models/                          # SHARED — both developers import
    __init__.py
    schemas.py                     # Pydantic models (API + agents + ingestion DTOs)
    db_models.py                   # SQLAlchemy ORM ↔ Postgres tables

  ingestion/                       # === Developer A ===
    __init__.py
    parser.py                      # Docling / layout-aware PDF parsing
    extractor.py                   # Section extraction + metadata tagging
    captioner.py                     # GPT-4o Vision for slide companions
    embedder.py                    # text-embedding-3-large → pgvector
    linker.py                      # Relations + dedup across bundle
    policy_loader.py               # Standards / framework PDF → policy_rules
    block_catalog_loader.py        # Kid Spark piece catalog → block_catalog
    router.py                      # FastAPI routes for bundle upload / ingest / jobs

  retrieval/                       # === Developer B builds; both pipelines use ===
    __init__.py
    search.py                      # Hybrid vector + metadata search
    expansion.py                   # Bundle expansion (siblings + relations + policy)
    evidence.py                    # Assemble EvidencePack for agents

  agents/                          # === Developer B ===
    __init__.py
    story_analysis.py              # Step A — storybook analysis (post-upload)
    consultation.py                # Multi-turn teacher consultation + KB tools
    block_awareness.py             # Movement + Kid Spark piece mapping
    outline_planner.py             # Step B — LessonSpec
    build_target.py                # Step C — BuildTargetProfile
    teacher_plan.py                # Step D — TeacherLessonPlan
    student_guide.py               # Step E — StudentActivityGuide
    validator.py                   # Step F — ValidationResult
    orchestrator.py                # Phases: consult → block awareness → generate

  api/                             # === Developer B ===
    __init__.py
    main.py                        # FastAPI app, routers, middleware, lifespan
    sessions.py                    # Session lifecycle (upload, message, approve, generate)
    health.py                      # Liveness / readiness for Cloud Run

  tests/
    __init__.py
    test_ingestion/                # Dev A — parser, extractor, captioner, embedder
    test_retrieval/                # Shared — search, expansion, evidence
    test_agents/                   # Dev B — consultation, block awareness, orchestrator
    test_api/                      # Dev B — HTTP session flow
    fixtures/                      # Shared sample inputs (e.g. storybook text)
```

### Design rationale

- **`backend/` is self-contained** — its own `requirements.txt`, `Dockerfile`, and `config.py`. The Streamlit app at the repo root keeps its own Dockerfile and dependencies until you intentionally unify deployment.
- **`models/`** is the **shared contract**: Pydantic schemas and SQLAlchemy tables used by ingestion writes and runtime reads. Keep schema changes reviewable and small.
- **`ingestion/`** is **Developer A’s** surface: parse → extract → caption → embed → link → expose ingest APIs. Developer B does not implement ingestion here.
- **`agents/` and `api/`** are **Developer B’s** surface: consultation, block awareness, generation pipeline, orchestration, and public HTTP API.
- **`retrieval/`** is **implemented by Developer B** (search + expansion + evidence assembly) but **used by both**: ingestion does not need retrieval for writing; agents and consultation tools need it for reads.
- **`migrations/`** is **primarily Developer A** (tables for bundles, nodes, relations, policy, block catalog, sessions). Developer B may add migrations for session or runtime-only columns when agreed.
- **`tests/`** is split by domain so each developer can run focused suites (`test_ingestion`, `test_agents`, etc.) without stepping on the other’s files.

### Conflict avoidance

Only a **narrow** set of paths should see concurrent edits from both developers:

| Area | Risk | Mitigation |
|------|------|------------|
| `models/schemas.py`, `models/db_models.py` | Both need types/tables | Short PRs, announce schema changes in chat, merge to `deploy` quickly |
| `config.py` | Shared env knobs | Rare edits; defaults live here |
| `backend/requirements.txt` | New packages | Add deps in small commits; avoid drive-by upgrades |

Everything else is **directory-scoped**: Dev A owns `ingestion/` and migration authoring; Dev B owns `agents/`, `api/`, and `retrieval/`. That keeps merge conflicts low if people pull `deploy` before starting work.

### Branch strategy

`deploy` is treated as the **integration branch** (mainline for KidSpark backend work). Feature work happens on two long-lived branches:

```
deploy                    ← merge here when ready (treated as “main” for this effort)
  │
  ├── dev/ingestion       ← Developer A: ingestion, migrations, models (as needed)
  │
  └── dev/runtime         ← Developer B: agents, api, retrieval, models (as needed)
```

**Workflow**

1. Branch from `deploy` (or stay on `dev/ingestion` / `dev/runtime` already tracking it).
2. Implement in the directories above; prefer touching only your side plus shared files when necessary.
3. Pull latest `deploy` regularly (`git fetch origin` then `git merge origin/deploy`) to reduce drift.
4. Open PRs (or merge) into `deploy` when a slice is stable; resolve conflicts early on shared files.

Both `dev/ingestion` and `dev/runtime` should **track the same planning baseline** in this README so anyone opening either branch sees the same high-level map.

---

## Setup

```bash
cd backend
pip install -r requirements.txt
```

## Running locally

```bash
uvicorn api.main:app --reload --port 8000
```

(Until `api/main.py` wires routers, this may need a minimal app stub.)

## Environment variables

See [`config.py`](config.py) for intended GCP and OpenAI settings. For local dev, use a `.env` file in `backend/` (values mirror the commented placeholders in `config.py`).

## Reference

See [`KIDSPARK_TECHNICAL_SPEC.md`](../KIDSPARK_TECHNICAL_SPEC.md) in the project root for the full technical specification (APIs, data models, GCP, agent phases).
