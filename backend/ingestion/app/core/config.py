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

    # --- OpenAI + GCP ---
    OPENAI_API_KEY: str = Field("", json_schema_extra={"env": "OPENAI_API_KEY"})
    GCP_PROJECT_ID: str = Field("", json_schema_extra={"env": "GCP_PROJECT_ID"})

    # --- GCS data layer ---
    GCS_BUCKET_NAME: str = Field("", json_schema_extra={"env": "GCS_BUCKET_NAME"})
    GCS_PREFIX: str = Field("", json_schema_extra={"env": "GCS_PREFIX"})
    GCS_PROCESSED_BUCKET: str = Field("", json_schema_extra={"env": "GCS_PROCESSED_BUCKET"})
    RAW_PREFIX: str = Field("", json_schema_extra={"env": "RAW_PREFIX"})
    KNOWLEDGE_PREFIX: str = Field("Knowledge_chunks", json_schema_extra={"env": "KNOWLEDGE_PREFIX"})
    KNOWLEDGE_LOCAL_DIR: str = Field("", json_schema_extra={"env": "KNOWLEDGE_LOCAL_DIR"})

    # --- chunking ---
    CHUNK_MAX_CHARS: int = Field(800, json_schema_extra={"env": "CHUNK_MAX_CHARS"})
    CHUNK_OVERLAP: int = Field(120, json_schema_extra={"env": "CHUNK_OVERLAP"})
    CHUNK_MIN_CHARS: int = Field(15, json_schema_extra={"env": "CHUNK_MIN_CHARS"})

    # --- models ---
    EMBED_MODEL: str = Field("text-embedding-3-large", json_schema_extra={"env": "EMBED_MODEL"})
    EMBED_DIM: int = Field(3072, json_schema_extra={"env": "EMBED_DIM"})
    VISION_MODEL: str = Field("gpt-5.6-luna", json_schema_extra={"env": "VISION_MODEL"})

    # --- vision fallback (local, offline captioning when OpenAI is unavailable or refuses) ---
    CAPTION_FALLBACK: bool = Field(True, json_schema_extra={"env": "CAPTION_FALLBACK"})
    OLLAMA_HOST: str = Field("http://localhost:11434", json_schema_extra={"env": "OLLAMA_HOST"})
    OLLAMA_VISION_MODEL: str = Field("llava", json_schema_extra={"env": "OLLAMA_VISION_MODEL"})

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
    PROC_VERSION: str = Field("1.0", json_schema_extra={"env": "PROC_VERSION"})

    @model_validator(mode="after")
    def _assemble_db_url(self):
        # Build the SQLAlchemy URL from POSTGRES_* if POSTGRESQL_DATABASE_URL wasn't provided directly.
        # User/password are percent-encoded so special chars (#, @, :, / ...) don't corrupt the URL.
        if not self.POSTGRESQL_DATABASE_URL:
            from urllib.parse import quote_plus
            self.POSTGRESQL_DATABASE_URL = (
                f"postgresql+psycopg://{quote_plus(self.POSTGRES_USER)}:"
                f"{quote_plus(self.POSTGRES_PASSWORD)}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}")
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
