"""Middleware registration (CORS + request timing/counter)."""
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("middleware")


def register_middlewares(app: FastAPI) -> None:
    """Attach all HTTP middleware to the app."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _timing_and_count(request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        elapsed_ms = (time.time() - start) * 1000.0
        try:
            request.app.state.requests_processed += 1
        except Exception:
            pass
        response.headers["X-Process-Time-ms"] = f"{elapsed_ms:.1f}"
        log.info("%s %s -> %s (%.1f ms)",
                 request.method, request.url.path, response.status_code, elapsed_ms)
        return response
