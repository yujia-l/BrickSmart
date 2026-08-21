"""Pydantic request/response schemas (the API contract — the 'View' data models)."""
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field


class RetrieveRequest(BaseModel):
    grade_band: str = Field(..., description="Grade selected in the UI (authoritative filter)")
    prompt: str = Field(..., description="Teacher's finalized request after the conversation loop")
    filters: Optional[Dict[str, str]] = Field(None, description="Optional lab/unit/lesson overrides")
    k: int = 40
    seed_k: int = 8
    rerank: bool = True


class RetrieveResponse(BaseModel):
    query: str
    understood: Dict[str, Any]
    filters: Dict[str, Any]
    seeds: List[Dict[str, Any]]
    bundles: List[Dict[str, Any]]
    policies: List[Dict[str, Any]]


class PolicyRequest(BaseModel):
    bundle_name: Optional[str] = None
    unit: Optional[str] = None
    policy_scope: Optional[str] = None


class PolicyResponse(BaseModel):
    count: int
    rules: List[Dict[str, Any]]


class IngestRequest(BaseModel):
    embed: bool = Field(True, description="Embed nodes with Vertex AI (False = load rows without vectors)")
    keep_dir: Optional[str] = Field(None, description="Keep the downloaded GCS mirror in this dir")


class IngestResponse(BaseModel):
    status: str
    bundles_loaded: int
    bucket: str
    prefix: str


class WelcomeResponse(BaseModel):
    service: str
    version: str
    message: str


class MetricsResponse(BaseModel):
    status: str
    uptime_seconds: float
    requests_processed: int
