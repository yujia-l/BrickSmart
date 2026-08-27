"""FastAPI application for BrickSmart runtime services.

This module exposes API routes for build planning, catalog access, contract
resolution, inventory handling, and generated artifact retrieval.
"""

from __future__ import annotations

import json
from urllib.parse import urlparse
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from bricksmart.api_models import (
    ModelBuildRequest,
    ModelRegistrationRequest,
    ObjPlanRequest,
    PlanRequest,
)
from bricksmart.exceptions import BrickSmartError
from bricksmart.inventory import (
    InventoryLedger,
    compile_effective_inventory,
    load_inventory_profile,
)
from bricksmart.inventory.models import InventoryMode, InventoryProfile
from bricksmart.obj_pipeline import run_obj_build
from bricksmart.row_column_runner import run_model_build
from bricksmart.model_store import LocalModelStore, ModelResolver
from bricksmart.model_registry import LocalModelRegistry
from bricksmart.run_store import LocalRunStore
from bricksmart.planning.voxel_models import StructuralPlannerConfig
from bricksmart.planning import (
    CandidateGroup,
    CandidateOption,
    ConstrainedPlanningService,
    Placement,
    PlanningProblem,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INVENTORY_PATH = (
    PROJECT_ROOT / "config/inventory/standard_kit.yaml"
)
SAMPLE_PROBLEM_PATH = PROJECT_ROOT / "examples/sample_candidate_problem.json"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

app = FastAPI(title="BrickSmart Inventory-Constrained Planner", version="1.1.0")
MODEL_STORE = LocalModelStore.from_environment(PROJECT_ROOT)
MODEL_REGISTRY = LocalModelRegistry.from_environment(PROJECT_ROOT)
RUN_STORE = LocalRunStore.from_environment(PROJECT_ROOT)


@app.get("/health")
def health() -> dict[str, str]:
    """Return the service health status.
    
    :returns: The result produced by the function.
    :rtype: dict[str, str]
    """
    return {"status": "ok"}


@app.get("/api/inventory/default")
def default_inventory() -> dict[str, object]:
    """Return the default inventory.
    
    :returns: The result produced by the function.
    :rtype: dict[str, object]
    """
    profile = load_inventory_profile(DEFAULT_INVENTORY_PATH)
    return {
        "inventory_id": profile.inventory_id,
        "inventory_name": profile.inventory_name,
        "inventory_mode": profile.mode.value,
        "blocks": profile.quantities,
    }


@app.get("/api/problem/sample")
def sample_problem() -> dict[str, object]:
    """Return the sample problem.
    
    :returns: The result produced by the function.
    :rtype: dict[str, object]
    """
    return json.loads(SAMPLE_PROBLEM_PATH.read_text(encoding="utf-8"))


@app.post("/api/plan")
def plan(request: PlanRequest) -> dict[str, object]:
    """Run the planning endpoint or operation.
    
    :param request: Request object supplied by the caller.
    :type request: PlanRequest
    :returns: The result produced by the function.
    :rtype: dict[str, object]
    """
    try:
        profile = InventoryProfile(
            inventory_id=request.inventory_id,
            inventory_name=request.inventory_id,
            mode=InventoryMode(request.inventory_mode),
            quantities=request.quantities,
        )
        effective = compile_effective_inventory(profile, request.teacher_budget)
        ledger = InventoryLedger(effective)
        groups = tuple(
            CandidateGroup(
                group_id=group.group_id,
                required=group.required,
                priority=group.priority,
                selection_kind=group.selection_kind,
                alternatives=tuple(
                    CandidateOption(
                        candidate_id=candidate.candidate_id,
                        score=candidate.score,
                        placements=tuple(
                            Placement(
                                part_id=part.part_id,
                                block_type=part.block_type,
                                segment_id=part.segment_id,
                                step=part.step,
                                metadata=part.metadata,
                            )
                            for part in candidate.placements
                        ),
                        metadata=candidate.metadata,
                    )
                    for candidate in group.alternatives
                ),
            )
            for group in request.groups
        )
        result = ConstrainedPlanningService(ledger).plan(
            PlanningProblem(
                groups=groups,
                scarcity_weight=request.scarcity_weight,
                fail_on_required_group=request.fail_on_required_group,
            )
        )
        return {**result.to_dict(), "inventory_usage": ledger.usage_summary()}
    except (ValueError, BrickSmartError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _resolve_project_path(value: str | None) -> Path | None:
    """Resolve project path.
    
    :param value: Value used by the operation.
    :type value: str | None
    :returns: The computed result.
    :rtype: Path | None
    """
    if value is None:
        return None
    candidate = Path(value)
    resolved = (candidate if candidate.is_absolute() else PROJECT_ROOT / candidate).resolve()
    try:
        resolved.relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("API paths must remain inside the BrickSmart project root") from exc
    return resolved


@app.post("/api/obj/plan")
def plan_obj(request: ObjPlanRequest) -> dict[str, object]:
    """Plan obj.
    
    :param request: Request object supplied by the caller.
    :type request: ObjPlanRequest
    :returns: The result produced by the function.
    :rtype: dict[str, object]
    """
    try:
        if request.model_uri:
            obj_path = ModelResolver(project_root=PROJECT_ROOT, store=MODEL_STORE).resolve(
                request.model_uri
            ).local_path
        elif request.obj_path:
            obj_path = _resolve_project_path(request.obj_path)
        else:
            raise ValueError("Provide model_uri or obj_path")
        result, ledger = run_obj_build(
            obj_path=obj_path,
            inventory_path=_resolve_project_path(request.inventory_path),
            catalog_path=_resolve_project_path(request.catalog_path),
            teacher_budget_path=_resolve_project_path(request.teacher_budget_path),
            up_axis=request.up_axis,
            target_longest_cells=request.target_longest_cells,
            minimum_component_voxels=request.minimum_component_voxels,
            planner_config=StructuralPlannerConfig(
                minimum_candidate_fill_ratio=request.minimum_candidate_fill_ratio,
                coverage_target=request.coverage_target,
                scarcity_weight=request.scarcity_weight,
            ),
        )
        return {**result.to_summary(), "inventory_usage": ledger.usage_summary()}
    except (ValueError, FileNotFoundError, BrickSmartError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/models")
def list_models() -> list[dict[str, object]]:
    """List models.
    
    :returns: The result produced by the function.
    :rtype: list[dict[str, object]]
    """
    return [record.to_dict() for record in MODEL_STORE.list_records()]


@app.get("/api/models/{model_id}")
def get_model(model_id: str) -> dict[str, object]:
    """Return model.
    
    :param model_id: Identifier for the model.
    :type model_id: str
    :returns: The result produced by the function.
    :rtype: dict[str, object]
    """
    try:
        return MODEL_STORE.get(model_id).to_dict()
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/models/upload")
async def upload_model(
    file: UploadFile = File(...),
    model_id: str = Form(...),
    expected_sha256: str | None = Form(None),
) -> dict[str, object]:
    """Upload model.
    
    :param file: The file value.
    :type file: UploadFile
    :param model_id: Identifier for the model.
    :type model_id: str
    :param expected_sha256: The expected sha256 value.
    :type expected_sha256: str | None
    :returns: The result produced by the function.
    :rtype: dict[str, object]
    """
    try:
        record = MODEL_STORE.import_stream(
            file.file,
            model_id=model_id,
            filename=file.filename or "model.obj",
            expected_sha256=expected_sha256,
            media_type=file.content_type or "model/obj",
            metadata={"ingest_method": "api_upload"},
        )
        return record.to_dict()
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()


@app.post("/api/models/register")
def register_model(request: ModelRegistrationRequest) -> dict[str, object]:
    """Register model.
    
    :param request: Request object supplied by the caller.
    :type request: ModelRegistrationRequest
    :returns: The result produced by the function.
    :rtype: dict[str, object]
    """
    try:
        scheme = urlparse(request.source_uri).scheme.lower()
        if scheme not in {"http", "https", "s3"}:
            raise ValueError(
                "The registration API accepts only https:// or s3:// sources. "
                "Use /api/models/upload for user files or the CLI for trusted local imports."
            )
        resolver = ModelResolver(project_root=PROJECT_ROOT, store=MODEL_STORE)
        resolved = resolver.resolve(
            {
                "uri": request.source_uri,
                "model_id": request.model_id,
                "expected_sha256": request.expected_sha256,
                "filename": request.filename,
            },
            default_model_id=request.model_id,
        )
        return MODEL_STORE.get(resolved.model_id or request.model_id).to_dict()
    except (ValueError, FileNotFoundError, RuntimeError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/contracts")
def list_contracts() -> list[dict[str, object]]:
    """List contracts.
    
    :returns: The result produced by the function.
    :rtype: list[dict[str, object]]
    """
    return [record.to_dict() for record in MODEL_REGISTRY.list_records()]


@app.get("/api/contracts/{contract_id}")
def get_contract(contract_id: str, version_id: str | None = None) -> dict[str, object]:
    """Return contract.
    
    :param contract_id: Identifier for the contract.
    :type contract_id: str
    :param version_id: Identifier for the version.
    :type version_id: str | None
    :returns: The result produced by the function.
    :rtype: dict[str, object]
    """
    try:
        return MODEL_REGISTRY.get(contract_id, version_id).to_dict()
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/contracts/upload")
async def upload_contract(
    task_context: UploadFile = File(...),
    contract_id: str = Form(...),
    confirmations: UploadFile | None = File(None),
    version_id: str | None = Form(None),
) -> dict[str, object]:
    """Upload contract.
    
    :param task_context: The task context value.
    :type task_context: UploadFile
    :param contract_id: Identifier for the contract.
    :type contract_id: str
    :param confirmations: The confirmations value.
    :type confirmations: UploadFile | None
    :param version_id: Identifier for the version.
    :type version_id: str | None
    :returns: The result produced by the function.
    :rtype: dict[str, object]
    """
    try:
        record = MODEL_REGISTRY.register_streams(
            task_context=task_context.file,
            task_context_filename=task_context.filename or "task_context.json",
            confirmations=(confirmations.file if confirmations else None),
            confirmations_filename=(confirmations.filename if confirmations else None),
            contract_id=contract_id,
            version_id=version_id,
            metadata={"ingest_method": "api_upload"},
        )
        return record.to_dict()
    except (ValueError, FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await task_context.close()
        if confirmations:
            await confirmations.close()


@app.get("/api/runs")
def list_runs() -> list[dict[str, object]]:
    """List runs.
    
    :returns: The result produced by the function.
    :rtype: list[dict[str, object]]
    """
    return RUN_STORE.list_runs()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, object]:
    """Return run.
    
    :param run_id: Identifier for the run.
    :type run_id: str
    :returns: The result produced by the function.
    :rtype: dict[str, object]
    """
    try:
        return RUN_STORE.get(run_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/model/build")
def build_model(request: ModelBuildRequest) -> dict[str, object]:
    """Run the model-agnostic row/column pipeline from a task context."""
    try:
        context_reference = request.contract_uri or request.task_context_path
        if not context_reference:
            raise ValueError("Provide contract_uri or task_context_path")
        if str(context_reference).startswith("contract://"):
            context_value = context_reference
        else:
            context_value = _resolve_project_path(context_reference)
        inventory_path = _resolve_project_path(request.inventory_path)
        result = run_model_build(
            project_root=PROJECT_ROOT,
            task_context_path=context_value,
            inventory_profile_path=inventory_path,
            clean_output=request.clean_output,
            check=not request.allow_incomplete,
            allow_unverified_contract=request.allow_unverified_contract,
            model_source_override=request.model_uri,
            run_id=request.run_id,
        )
        return {**result.summary, "log_path": str(result.log_path)}
    except (ValueError, FileNotFoundError, RuntimeError, BrickSmartError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


if FRONTEND_DIR.exists():
    app.mount("/ui", StaticFiles(directory=FRONTEND_DIR, html=True), name="ui")
