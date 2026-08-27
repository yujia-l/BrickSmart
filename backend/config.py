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

# --- Legacy OpenAI compatibility for non-KidSpark modules ---
OPENAI_API_KEY: str = _clean_secret(os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY", ""))
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-large"
EMBEDDING_DIMENSIONS: int = 3072

# --- Vertex AI ---
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "vertex").strip().lower()
GEMINI_API_KEY: str = _clean_secret(os.getenv("GEMINI_API_KEY", ""))
GCP_PROJECT_ID: str = os.getenv(
    "GCP_PROJECT_ID",
    os.getenv("GOOGLE_CLOUD_PROJECT", "kidspark-499901"),
)
VERTEX_GENERATION_LOCATION: str = os.getenv("VERTEX_GENERATION_LOCATION", "global")
VERTEX_EMBEDDING_LOCATION: str = os.getenv("VERTEX_EMBEDDING_LOCATION", "us-central1")
GEMINI_PRIMARY_MODEL: str = os.getenv("GEMINI_PRIMARY_MODEL", "gemini-3.6-flash")
GEMINI_FALLBACK_MODEL: str = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash")
GEMINI_EMBEDDING_MODEL: str = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
GEMINI_VISUAL_EMBEDDING_MODEL: str = os.getenv(
    "GEMINI_VISUAL_EMBEDDING_MODEL",
    "multimodalembedding@001",
)
VISUAL_EMBEDDING_DIMENSIONS: int = int(os.getenv("VISUAL_EMBEDDING_DIMENSIONS", "1408"))
KIDSPARK_OFFLINE_MODE: bool = os.getenv("KIDSPARK_OFFLINE_MODE", "false").lower() == "true"

# --- KidSpark runtime retrieval ---
KIDSPARK_RAG_ENABLED: bool = os.getenv("KIDSPARK_RAG_ENABLED", "true").lower() == "true"
KIDSPARK_RAG_TIMEOUT_SECONDS: float = float(
    os.getenv("KIDSPARK_RAG_TIMEOUT_SECONDS", "10")
)
KIDSPARK_RAG_RESULT_LIMIT: int = int(os.getenv("KIDSPARK_RAG_RESULT_LIMIT", "8"))
KIDSPARK_RAG_CACHE_TTL_SECONDS: int = int(
    os.getenv("KIDSPARK_RAG_CACHE_TTL_SECONDS", "600")
)
KIDSPARK_RAG_SERVICE_URL: str = os.getenv("KIDSPARK_RAG_SERVICE_URL", "").rstrip("/")
DATABASE_REQUIRED: bool = os.getenv("DATABASE_REQUIRED", "false").lower() == "true"

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
GCP_REGION: str = os.getenv("GCP_REGION", "us-central1")

# --- Secret Manager (production only) ---
USE_SECRET_MANAGER: bool = os.getenv("USE_SECRET_MANAGER", "false").lower() == "true"

# --- Application ---
API_VERSION: str = "v1"
MAX_REFINEMENT_ITERATIONS: int = 3
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
