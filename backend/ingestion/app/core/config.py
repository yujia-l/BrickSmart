"""Application settings (Pydantic BaseSettings).

Environment-driven configuration for the KidSpark RAG backend. Field names are the .env variable
names (UPPERCASE); `get_settings()` selects an env-specific profile via the ENV variable, and the
module-level `settings` singleton is imported everywhere.
"""
import os
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    # --- service metadata ---
    PROJECT_NAME: str = Field("KidSpark RAG Backend", json_schema_extra={"env": "PROJECT_NAME"})
    DESCRIPTION: str = Field(
        "Multimodal, lineage-preserving retrieval backend for the KidSpark STEM curriculum",
        json_schema_extra={"env": "DESCRIPTION"})
    VERSION: str = Field("1.0.0", json_schema_extra={"env": "VERSION"})
    CORS_ORIGINS: List[str] = Field(default=["*"], json_schema_extra={"env": "CORS_ORIGINS"})
    API_V1_STR: str = Field("/api/v1", json_schema_extra={"env": "API_V1_STR"})

    # --- database (Postgres + pgvector) ---
    POSTGRESQL_DATABASE_URL: Optional[str] = Field(
        default=None, json_schema_extra={"env": "POSTGRESQL_DATABASE_URL"})
    POSTGRES_HOST: str = Field("", json_schema_extra={"env": "POSTGRES_HOST"})
    POSTGRES_PORT: str = Field("", json_schema_extra={"env": "POSTGRES_PORT"})
    POSTGRES_DB: str = Field("", json_schema_extra={"env": "POSTGRES_DB"})
    POSTGRES_USER: str = Field("", json_schema_extra={"env": "POSTGRES_USER"})
    POSTGRES_PASSWORD: str = Field("", json_schema_extra={"env": "POSTGRES_PASSWORD"})
    DATABASE_REQUIRED: bool = Field(
        False, json_schema_extra={"env": "DATABASE_REQUIRED"})

    # --- Vertex AI + GCP ---
    GCP_PROJECT_ID: str = Field("kidspark-499901", json_schema_extra={"env": "GCP_PROJECT_ID"})
    VERTEX_GENERATION_LOCATION: str = Field(
        "global", json_schema_extra={"env": "VERTEX_GENERATION_LOCATION"})
    VERTEX_EMBEDDING_LOCATION: str = Field(
        "us-central1", json_schema_extra={"env": "VERTEX_EMBEDDING_LOCATION"})
    GEMINI_PRIMARY_MODEL: str = Field(
        "gemini-3.6-flash", json_schema_extra={"env": "GEMINI_PRIMARY_MODEL"})
    GEMINI_FALLBACK_MODEL: str = Field(
        "gemini-3.5-flash", json_schema_extra={"env": "GEMINI_FALLBACK_MODEL"})

    # --- GCS data layer ---
    GCS_BUCKET_NAME: str = Field("", json_schema_extra={"env": "GCS_BUCKET_NAME"})
    GCS_PREFIX: str = Field("", json_schema_extra={"env": "GCS_PREFIX"})
    GCS_PROCESSED_BUCKET: str = Field("", json_schema_extra={"env": "GCS_PROCESSED_BUCKET"})
    RAW_PREFIX: str = Field("Data", json_schema_extra={"env": "RAW_PREFIX"})
    KNOWLEDGE_PREFIX: str = Field("Knowledge_chunks", json_schema_extra={"env": "KNOWLEDGE_PREFIX"})
    KNOWLEDGE_LOCAL_DIR: str = Field("", json_schema_extra={"env": "KNOWLEDGE_LOCAL_DIR"})

    # --- chunking ---
    CHUNK_MAX_CHARS: int = Field(800, json_schema_extra={"env": "CHUNK_MAX_CHARS"})
    CHUNK_OVERLAP: int = Field(120, json_schema_extra={"env": "CHUNK_OVERLAP"})
    CHUNK_MIN_CHARS: int = Field(15, json_schema_extra={"env": "CHUNK_MIN_CHARS"})

    # --- models ---
    EMBED_MODEL: str = Field("gemini-embedding-001", json_schema_extra={"env": "EMBED_MODEL"})
    EMBED_DIM: int = Field(3072, json_schema_extra={"env": "EMBED_DIM"})
    EMBED_WORKERS: int = Field(2, json_schema_extra={"env": "EMBED_WORKERS"})
    EMBED_REQUESTS_PER_MINUTE: int = Field(
        4, json_schema_extra={"env": "EMBED_REQUESTS_PER_MINUTE"})
    RAG_QUERY_UNDERSTANDING_ENABLED: bool = Field(
        False, json_schema_extra={"env": "RAG_QUERY_UNDERSTANDING_ENABLED"})
    VISION_MODEL: str = Field("gemini-3.6-flash", json_schema_extra={"env": "VISION_MODEL"})
    VISION_FALLBACK_MODEL: str = Field(
        "gemini-3.5-flash", json_schema_extra={"env": "VISION_FALLBACK_MODEL"})
    VISUAL_EMBED_MODEL: str = Field(
        "multimodalembedding@001", json_schema_extra={"env": "VISUAL_EMBED_MODEL"})
    VISUAL_EMBED_DIM: int = Field(1408, json_schema_extra={"env": "VISUAL_EMBED_DIM"})
    VISUAL_EMBED_ROLES: str = Field(
        "parts_diagram,build_step,example_build,diagram",
        json_schema_extra={"env": "VISUAL_EMBED_ROLES"})
    SAVE_IMAGE_CROPS: bool = Field(True, json_schema_extra={"env": "SAVE_IMAGE_CROPS"})

    # --- reranker ---
    RERANKER: str = Field("cross_encoder", json_schema_extra={"env": "RERANKER"})
    RERANK_MODEL: str = Field(
        "cross-encoder/ms-marco-MiniLM-L-6-v2", json_schema_extra={"env": "RERANK_MODEL"})
    RERANK_POOL: int = Field(20, json_schema_extra={"env": "RERANK_POOL"})

    # --- docling ---
    DOCLING_OCR: bool = Field(True, json_schema_extra={"env": "DOCLING_OCR"})
    DOCLING_TABLES: bool = Field(True, json_schema_extra={"env": "DOCLING_TABLES"})
    DOCLING_IMAGE_SCALE: float = Field(2.0, json_schema_extra={"env": "DOCLING_IMAGE_SCALE"})

    # --- pipeline meta ---
    MANIFEST_PATH: str = Field(
        "Data/kidspark_manifest.csv", json_schema_extra={"env": "MANIFEST_PATH"})
    PROC_VERSION: str = Field("2.0-vertex", json_schema_extra={"env": "PROC_VERSION"})

    @model_validator(mode="after")
    def _assemble_db_url(self):
        # Build the SQLAlchemy URL from POSTGRES_* if POSTGRESQL_DATABASE_URL wasn't provided directly.
        # User/password are percent-encoded so special chars (#, @, :, / ...) don't corrupt the URL.
        database_parts = (
            self.POSTGRES_HOST,
            self.POSTGRES_PORT,
            self.POSTGRES_DB,
            self.POSTGRES_USER,
            self.POSTGRES_PASSWORD,
        )
        if not self.POSTGRESQL_DATABASE_URL and all(database_parts):
            from urllib.parse import quote_plus
            self.POSTGRESQL_DATABASE_URL = (
                f"postgresql+psycopg://{quote_plus(self.POSTGRES_USER)}:"
                f"{quote_plus(self.POSTGRES_PASSWORD)}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}")
        elif self.DATABASE_REQUIRED and not self.POSTGRESQL_DATABASE_URL:
            raise ValueError(
                "Database configuration is required. Set POSTGRESQL_DATABASE_URL "
                "or every POSTGRES_* setting."
            )
        return self


class DevelopmentConfig(BaseConfig):
    DEBUG: bool = Field(True, json_schema_extra={"env": "DEBUG"})


class TestingConfig(BaseConfig):
    DEBUG: bool = Field(True, json_schema_extra={"env": "DEBUG"})


class ProductionConfig(BaseConfig):
    DEBUG: bool = Field(False, json_schema_extra={"env": "DEBUG"})


def get_settings():
    env = os.getenv("ENV", "").lower()
    env_mapping = {
        "production": (".env.production", ProductionConfig),
        "testing": (".env.testing", TestingConfig),
        "development": (".env.development", DevelopmentConfig),
    }
    if not env:
        load_dotenv(".env")
        return BaseConfig()
    env_file, config_class = env_mapping.get(env, (".env", BaseConfig))
    if os.path.exists(env_file):
        print(f"Loading {env} configuration from {env_file}")
        load_dotenv(env_file)
    else:
        print(f"Environment file {env_file} does not exist")
    return config_class()


settings = get_settings()
