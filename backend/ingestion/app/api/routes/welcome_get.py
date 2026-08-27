"""Welcome route — a friendly root endpoint under the API prefix."""
from fastapi import APIRouter

from app.core.config import settings
from app.api.schemas.schema import WelcomeResponse


class WelcomeGetRouter:
    def __init__(self):
        self.router = APIRouter(tags=["welcome"])
        self.router.add_api_route("/", self.welcome, methods=["GET"],
                                  response_model=WelcomeResponse)

    async def welcome(self) -> WelcomeResponse:
        return WelcomeResponse(
            service=settings.PROJECT_NAME,
            version=settings.VERSION,
            message="KidSpark RAG backend is running.")
