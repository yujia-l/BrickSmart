"""
KidSpark AI — FastAPI Application Entry Point
Owner: Developer B
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.build_demo import router as build_demo_router
from api.health import router as health_router
from api.sessions import router as sessions_router
from api.settings import router as settings_router

app = FastAPI(
    title="KidSpark AI",
    version="0.1.0",
    description="Backend API for KidSpark AI lesson generation system",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(sessions_router)
app.include_router(build_demo_router)
app.include_router(settings_router)


@app.get("/")
async def root():
    return {
        "service": "KidSpark AI",
        "version": "0.1.0",
        "docs": "/docs",
    }
