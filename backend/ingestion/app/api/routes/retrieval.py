"""Retrieval routes — the teacher-facing RAG endpoints (the 'Controller').

  POST /retrieve   {grade_band, prompt, filters?, k?, seed_k?, rerank?} -> lineage-preserving RAG pack
  POST /policies   {bundle_name? | unit? | policy_scope?}               -> unit rules for compliance
"""
from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.core.logging import get_logger
from app.api.models.model_init import DBUtil
from app.api.schemas.schema import (RetrieveRequest, RetrieveResponse,
                                     PolicyRequest, PolicyResponse)
from app.services import retrieval as retrieval_service
from app.services import repository

log = get_logger("routes.retrieval")


class RetrievalRouter:
    def __init__(self):
        self.db = DBUtil(settings)
        self.router = APIRouter(tags=["retrieval"])
        self.router.add_api_route("/retrieve", self.retrieve, methods=["POST"],
                                  response_model=RetrieveResponse)
        self.router.add_api_route("/policies", self.policies, methods=["POST"],
                                  response_model=PolicyResponse)

    async def retrieve(self, req: RetrieveRequest) -> RetrieveResponse:
        """Templated retrieval: grade (from UI) + teacher's final prompt -> optimized RAG pack."""
        try:
            result = retrieval_service.templated_retrieve(
                req.prompt, req.grade_band, filters=req.filters,
                k=req.k, seed_k=req.seed_k, rerank=req.rerank,
                settings=settings, dbu=self.db)
            return RetrieveResponse(**result)
        except Exception as e:
            log.error("retrieve failed: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    async def policies(self, req: PolicyRequest) -> PolicyResponse:
        """Standard rules for a bundle / unit / policy_scope (post-generation compliance check)."""
        try:
            rules = repository.policies_for(bundle_name=req.bundle_name, unit=req.unit,
                                            policy_scope=req.policy_scope, db=self.db)
            return PolicyResponse(count=len(rules), rules=rules)
        except Exception as e:
            log.error("policies failed: %s", e)
            raise HTTPException(status_code=500, detail=str(e))
