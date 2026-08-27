"""KidSpark RAG backend — FastAPI application factory."""
import time

import uvicorn
from fastapi import FastAPI

from app.core.config import settings
from app.core.logging import configure
from app.core.middleware import register_middlewares
from app.api.models.model_init import create_all_tables
from app.api.routes.server_metrics import ServerMetrics
from app.api.routes.welcome_get import WelcomeGetRouter
from app.api.routes.retrieval import RetrievalRouter
from app.api.routes.ingestion import IngestionRouter


def create_app() -> FastAPI:
    configure(force=True)                       # capture-all, colorized, real-time logging

    app = FastAPI(
        title=settings.PROJECT_NAME,
        description=settings.DESCRIPTION,
        version=settings.VERSION,
    )
    app.state.start_time = time.time()
    app.state.requests_processed = 0

    # Initialize database (pgvector extension + star-schema tables + indexes)
    create_all_tables()

    # Register middleware (CORS + request timing/counter)
    register_middlewares(app)

    welcome_get_router = WelcomeGetRouter().router
    server_metrics_router = ServerMetrics(app).router
    retrieval_router = RetrievalRouter().router
    ingestion_router = IngestionRouter().router

    # Register the routers
    app.include_router(server_metrics_router)
    app.include_router(welcome_get_router, prefix=settings.API_V1_STR)
    app.include_router(retrieval_router, prefix=settings.API_V1_STR)
    app.include_router(ingestion_router, prefix=settings.API_V1_STR)

    return app


app = create_app()


if __name__ == "__main__":
    # log_config=None -> uvicorn logs flow through our capture-all root handler
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=False, log_config=None)  # pragma: no cover
