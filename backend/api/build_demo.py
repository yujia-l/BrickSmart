"""Local end-to-end build demo endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from build3d.jobs import snapshot, start_build_job
from build3d.rodin_client import check_balance

router = APIRouter(prefix="/api/v1/build-demo", tags=["build-demo"])


class BuildDemoRequest(BaseModel):
    story_text: str = Field(..., min_length=50)
    teacher_connection_intent: str = ""


@router.get("/health")
async def build_demo_health():
    return {"rodin": check_balance()}


@router.post("/jobs")
async def create_build_job(body: BuildDemoRequest):
    return start_build_job(body.story_text, body.teacher_connection_intent)


@router.get("/jobs/{job_id}")
async def get_build_job(job_id: str):
    job = snapshot(job_id)
    if not job:
        raise HTTPException(404, "Build job not found")
    return job
