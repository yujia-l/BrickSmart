"""Ingestion route — trigger the GCS -> database load from the API (the 'Controller').

  POST /ingest   {embed?} -> streams processed bundles from GCS into the star schema

Runs as a sync def so FastAPI executes it in a threadpool (the load can take a while: it streams
from GCS and embeds every node with OpenAI), keeping the event loop responsive.
"""
from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.core.logging import get_logger
from app.api.schemas.schema import IngestRequest, IngestResponse
from app.services.ingest import ingest_from_gcs

log = get_logger("routes.ingestion")


class IngestionRouter:
    def __init__(self):
        self.router = APIRouter(tags=["ingestion"])
        self.router.add_api_route("/ingest", self.ingest, methods=["POST"],
                                  response_model=IngestResponse)

    def ingest(self, req: IngestRequest) -> IngestResponse:
        """Load all processed bundles from the GCS bucket into the Postgres + pgvector star schema."""
        try:
            count = ingest_from_gcs(settings, embed=req.embed)
            return IngestResponse(
                status="ok",
                bundles_loaded=count,
                bucket=settings.GCS_PROCESSED_BUCKET or "kidspark-processed",
                prefix=settings.KNOWLEDGE_PREFIX)
        except Exception as e:
            log.error("ingest failed: %s", e)
            raise HTTPException(status_code=500, detail=str(e))
