from __future__ import annotations

from pydantic import BaseModel, Field


class PlacementRequest(BaseModel):
    part_id: str
    block_type: str
    segment_id: str | None = None
    step: int | None = None
    metadata: dict = Field(default_factory=dict)


class CandidateRequest(BaseModel):
    candidate_id: str
    score: float = 0.0
    placements: list[PlacementRequest]
    metadata: dict = Field(default_factory=dict)


class GroupRequest(BaseModel):
    group_id: str
    alternatives: list[CandidateRequest]
    required: bool = True
    priority: int = 0
    selection_kind: str = "generic"


class PlanRequest(BaseModel):
    inventory_mode: str = "finite"
    inventory_id: str = "request_inventory"
    quantities: dict[str, int] = Field(default_factory=dict)
    teacher_budget: dict[str, int] = Field(default_factory=dict)
    scarcity_weight: float = 0.25
    fail_on_required_group: bool = True
    groups: list[GroupRequest]


class ObjPlanRequest(BaseModel):
    obj_path: str | None = None
    model_uri: str | None = None
    inventory_path: str = "backend/bricksmart/config/inventory/standard_kit.yaml"
    catalog_path: str = "block_catalog/block_definitions.xlsx"
    teacher_budget_path: str | None = None
    up_axis: str = "auto"
    target_longest_cells: int = Field(default=18, ge=4, le=100)
    minimum_component_voxels: int = Field(default=1, ge=1)
    minimum_candidate_fill_ratio: float = Field(default=0.20, gt=0, le=1)
    coverage_target: float = Field(default=0.93, gt=0, le=1)
    scarcity_weight: float = Field(default=0.25, ge=0)


class ModelBuildRequest(BaseModel):
    task_context_path: str | None = None
    contract_uri: str | None = None
    model_uri: str | None = None
    inventory_path: str | None = None
    clean_output: bool = False
    allow_unverified_contract: bool = False
    allow_incomplete: bool = False
    run_id: str | None = None


class ModelRegistrationRequest(BaseModel):
    model_id: str
    source_uri: str
    expected_sha256: str | None = None
    filename: str | None = None


class ModelRecordResponse(BaseModel):
    model_id: str
    canonical_uri: str
    sha256: str
    size_bytes: int
    original_filename: str
    media_type: str
    created_at: str
    metadata: dict = Field(default_factory=dict)
