"""
KidSpark AI — Health Check Endpoints
"""

from fastapi import APIRouter
from config import DATABASE_REQUIRED, GCP_PROJECT_ID, GEMINI_PRIMARY_MODEL
from llm.vertex_gemini import auth_mode, provider_configured

router = APIRouter(tags=["health"])


@router.get("/health")
async def liveness():
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness():
    rag = {"ok": False, "status": "not_checked"}
    try:
        from retrieval.provider import _ingestion_retriever

        _ingestion_retriever()
        import sys
        from pathlib import Path

        ingestion_root = str(Path(__file__).resolve().parents[1] / "ingestion")
        if ingestion_root not in sys.path:
            sys.path.insert(0, ingestion_root)
        from app.api.models.model_init import DBUtil

        rag = DBUtil().health_report()
    except Exception as exc:
        rag = {"ok": False, "status": "unavailable", "error": str(exc)}
    checks = {
        "vertex_gemini_configured": provider_configured(),
        "rag_database_ready": bool(rag.get("ok") and rag.get("data_ready")),
        "rag_corpus_fully_embedded": bool(rag.get("corpus_fully_embedded")),
    }
    all_ok = checks["vertex_gemini_configured"] and (
        checks["rag_database_ready"] or not DATABASE_REQUIRED
    )
    return {
        "status": "ready" if all_ok else "degraded",
        "checks": checks,
        "models": {
            "project": GCP_PROJECT_ID,
            "primary": GEMINI_PRIMARY_MODEL,
            "auth_mode": auth_mode(),
        },
        "rag": rag,
    }
