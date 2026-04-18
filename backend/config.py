"""
KidSpark AI — Shared Configuration
Owner: SHARED (both developers use this)

This module provides all GCP and service configuration. Both the ingestion
pipeline (Dev A) and the runtime/agent pipeline (Dev B) import from here.

For local development, create a .env file in the backend/ directory with
the values below. In production (Cloud Run), these come from environment
variables and Secret Manager.

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 6, "GCP Infrastructure"
"""

# import os
# from dotenv import load_dotenv
#
# load_dotenv()
#
#
# # --- Database (Cloud SQL + pgvector) ---
# DATABASE_URL = os.getenv(
#     "DATABASE_URL",
#     "postgresql+asyncpg://kidspark:password@localhost:5432/kidspark"
# )
#
# # --- Google Cloud Storage ---
# GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "kidspark-assets")
# GCS_RAW_PREFIX = "raw/"          # uploaded PDFs
# GCS_PAGES_PREFIX = "pages/"      # rendered slide page images
# GCS_GENERATED_PREFIX = "generated/"  # generated lesson assets
#
# # --- OpenAI ---
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# OPENAI_MODEL = "gpt-4o"
# OPENAI_EMBEDDING_MODEL = "text-embedding-3-large"
# EMBEDDING_DIMENSIONS = 3072
#
# # --- GCP Project ---
# GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "your-project-id")
# GCP_REGION = os.getenv("GCP_REGION", "us-central1")
#
# # --- Secret Manager (production only) ---
# # In production, secrets are fetched from Secret Manager instead of env vars.
# # Secret names:
# #   - kidspark-openai-key
# #   - kidspark-db-password
# USE_SECRET_MANAGER = os.getenv("USE_SECRET_MANAGER", "false").lower() == "true"
#
# # --- Application ---
# API_VERSION = "v1"
# MAX_REFINEMENT_ITERATIONS = 3
# LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
