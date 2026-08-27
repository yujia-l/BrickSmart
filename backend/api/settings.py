"""Read-only runtime settings exposed to the KidSpark UI."""

from __future__ import annotations

from fastapi import APIRouter

from config import (
    GCP_PROJECT_ID,
    GEMINI_FALLBACK_MODEL,
    GEMINI_PRIMARY_MODEL,
    KIDSPARK_OFFLINE_MODE,
    KIDSPARK_RAG_ENABLED,
    KIDSPARK_RAG_SERVICE_URL,
    VERTEX_EMBEDDING_LOCATION,
    VERTEX_GENERATION_LOCATION,
)
from llm.vertex_gemini import auth_mode, provider_configured

router = APIRouter(prefix="/api/v1", tags=["settings"])


@router.get("/settings/runtime")
async def get_runtime_status():
    return {
        "provider": "vertex_ai",
        "auth_mode": auth_mode(),
        "configured": provider_configured(),
        "offline_mode": KIDSPARK_OFFLINE_MODE,
        "project": GCP_PROJECT_ID,
        "generation_location": VERTEX_GENERATION_LOCATION,
        "embedding_location": VERTEX_EMBEDDING_LOCATION,
        "primary_model": GEMINI_PRIMARY_MODEL,
        "fallback_model": GEMINI_FALLBACK_MODEL,
        "rag_enabled": KIDSPARK_RAG_ENABLED,
        "rag_transport": "service" if KIDSPARK_RAG_SERVICE_URL else "direct_pgvector",
    }
