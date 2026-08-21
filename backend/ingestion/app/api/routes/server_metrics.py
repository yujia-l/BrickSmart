"""Server metrics + liveness routes."""
import time

from fastapi import APIRouter

from app.api.schemas.schema import MetricsResponse


class ServerMetrics:
    def __init__(self, app):
        self.app = app
        self.router = APIRouter(tags=["metrics"])
        self.router.add_api_route("/healthz", self.healthz, methods=["GET"])
        self.router.add_api_route("/metrics", self.metrics, methods=["GET"],
                                  response_model=MetricsResponse)

    async def healthz(self):
        return {"status": "ok"}

    async def metrics(self) -> MetricsResponse:
        start = getattr(self.app.state, "start_time", time.time())
        processed = getattr(self.app.state, "requests_processed", 0)
        return MetricsResponse(status="ok",
                               uptime_seconds=round(time.time() - start, 2),
                               requests_processed=processed)
