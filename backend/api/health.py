"""
KidSpark AI — Health Check Endpoints
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def liveness():
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness():
    checks = {
        "openai_key_configured": bool(__import__("config").OPENAI_API_KEY),
    }
    all_ok = all(checks.values())
    return {
        "status": "ready" if all_ok else "degraded",
        "checks": checks,
    }
