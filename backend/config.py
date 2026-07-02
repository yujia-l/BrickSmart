"""
KidSpark AI — Shared Configuration
Owner: SHARED (both developers use this)

For local development, create a .env file in the backend/ directory.
In production (Cloud Run), values come from environment variables and Secret Manager.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)


def _clean_secret(value: str | None) -> str:
    return (value or "").strip().lstrip("\ufeff")

# --- OpenAI ---
# Cloud Run currently exposes the OpenAI Secret Manager value as OPENAI_KEY.
# Local/dev tooling may use OPENAI_API_KEY, so support both names.
OPENAI_API_KEY: str = _clean_secret(os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY", ""))
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-large"
EMBEDDING_DIMENSIONS: int = 3072

# --- Hyper3D / Rodin ---
HYPER3D_API_KEY: str = _clean_secret(os.getenv("HYPER3D_API_KEY", ""))
HYPER3D_BASE_URL: str = _clean_secret(os.getenv("HYPER3D_BASE_URL", "https://api.hyper3d.com/api/v2"))
RODIN_TIER: str = os.getenv("RODIN_TIER", "Gen-2.5-Low")
RODIN_QUALITY: str = os.getenv("RODIN_QUALITY", "extra-low")
RODIN_MESH_MODE: str = os.getenv("RODIN_MESH_MODE", "Raw")
RODIN_GEOMETRY_FILE_FORMAT: str = os.getenv("RODIN_GEOMETRY_FILE_FORMAT", "obj")
RODIN_MATERIAL: str = os.getenv("RODIN_MATERIAL", "None")
BANG_STRENGTH: int = int(os.getenv("BANG_STRENGTH", "5"))
BANG_RESOLUTION: str = os.getenv("BANG_RESOLUTION", "Basic")

# --- Database (Cloud SQL + pgvector) ---
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://kidspark:password@localhost:5432/kidspark",
)

# --- Google Cloud Storage ---
GCS_RAW_BUCKET: str = os.getenv("GCS_RAW_BUCKET", "kidspark-raw-files")
GCS_ASSETS_BUCKET: str = os.getenv("GCS_ASSETS_BUCKET", "kidspark-assets")

# --- GCP Project ---
GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "your-project-id")
GCP_REGION: str = os.getenv("GCP_REGION", "us-central1")

# --- Secret Manager (production only) ---
USE_SECRET_MANAGER: bool = os.getenv("USE_SECRET_MANAGER", "false").lower() == "true"

# --- Application ---
API_VERSION: str = "v1"
MAX_REFINEMENT_ITERATIONS: int = 3
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# --- Local fallback: read from root openai.key file if no env var ---
if not OPENAI_API_KEY:
    _key_file = Path(__file__).parent.parent / "openai.key"
    if _key_file.exists():
        OPENAI_API_KEY = _key_file.read_text().strip()
        os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
