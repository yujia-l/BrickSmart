from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bricksmart.contracts import build_semantic_target_preservation_report
from bricksmart.regression import write_checkpoint_manifest
from bricksmart.runtime import load_task_context, resolve_execution_policy, validate_model_contract
from bricksmart.model_registry import LocalModelRegistry
from bricksmart.run_store import LocalRunStore, RunPaths


@dataclass(frozen=True)
class RowColumnRunResult:
    project_root: Path
    context_path: Path
    contract_uri: str
    run_id: str
    run_dir: Path
    output_dir: Path
    returncode: int
    log_path: Path
    summary: dict[str, Any]


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _inventory_infeasibility_from_log(log_text: str) -> dict[str, Any] | None:
    """Extract a structured inventory-shortage outcome from an engine log."""
    pattern = re.compile(r"Inventory reservation failed for (.+?): (\{.*\})")
    for line in reversed(log_text.splitlines()):
        match = pattern.search(line.strip())
        if match is None:
            continue
        try:
            shortages = json.loads(match.group(2))
        except json.JSONDecodeError:
            continue
        return {
            "status": "INFEASIBLE_INVENTORY",
            "failure_scope": match.group(1),
            "shortages": shortages,
        }
    return None


def _write_inventory_infeasibility_artifacts(
    *, output_dir: Path, outcome: dict[str, Any], inventory_profile_path: str | Path | None
) -> None:
    inventory_id = Path(inventory_profile_path).stem if inventory_profile_path else "unknown"
    payload = {
        "schema_version": "bricksmart-inventory-feasibility-1.0",
        **outcome,
        "final_claim_valid": False,
        "inventory_id": inventory_id,
        "inventory_mode": "finite",
        "build_instructions_html_generated": False,
    }
    (output_dir / "inventory_feasibility.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "inventory_validation.json").write_text(
        json.dumps(
            {
                "valid": False,
                "inventory_id": inventory_id,
                "inventory_mode": "finite",
                "status": "INFEASIBLE_INVENTORY",
                "failure_scope": outcome["failure_scope"],
                "shortages": outcome["shortages"],
                "recount": {},
                "ledger_committed": {},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "segment_connector_final_summary.json").write_text(
        json.dumps(
            {
                "final_claim_valid": False,
                "final_status": "INFEASIBLE_INVENTORY",
                "final_block_count": 0,
                "structural_segment_count": 0,
                "direct_structural_join_count": 0,
                "combined_symmetry_complete": False,
                "inventory_valid": False,
                "inventory_profile": inventory_id,
                "inventory_mode": "finite",
                "inventory_enforced": True,
                "inventory_shortages": outcome["shortages"],
                "inventory_failure_scope": outcome["failure_scope"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def resolve_project_root(start: str | Path | None = None) -> Path:
    root = Path(start).expanduser().resolve() if start is not None else Path(__file__).resolve().parents[2]
    required = [root / "backend", root / "block_catalog"]
    if not all(path.exists() for path in required):
        raise FileNotFoundError(
            "Could not resolve BrickSmart project root. Expected backend/ and "
            "block_catalog/ under " + str(root)
        )
    (root / "pipeline_runtime").mkdir(parents=True, exist_ok=True)
    return root


def output_dir_from_context(project_root: Path, context_path: Path) -> Path:
    """Deprecated output-directory helper.

    The runtime no longer trusts model contracts to choose output locations. New runs
    are created by :class:`LocalRunStore` under ``BRICKSMART_RUNS_ROOT``.
    """
    context = _load_json(context_path, {}) or {}
    model_id = str(context.get("model_id") or context.get("task_id") or context_path.stem)
    store = LocalRunStore.from_environment(project_root)
    return store.create(model_id=model_id, contract_uri=context_path.as_uri()).artifacts_dir


def summarize_row_column_output(output_dir: Path) -> dict[str, Any]:
    final_summary = _load_json(output_dir / "segment_connector_final_summary.json", {}) or {}
    inventory = _load_json(output_dir / "inventory_validation.json", {}) or {}
    visualization = _load_json(output_dir / "final_visualization_export_audit.json", {}) or {}
    return {
        "final_claim_valid": bool(final_summary.get("final_claim_valid", False)),
        "final_status": final_summary.get("final_status"),
        "final_block_count": int(final_summary.get("final_block_count", 0) or 0),
        "structural_segment_count": int(final_summary.get("structural_segment_count", 0) or 0),
        "direct_structural_join_count": int(final_summary.get("direct_structural_join_count", 0) or 0),
        "combined_symmetry_complete": bool(final_summary.get("combined_symmetry_complete", False)),
        "inventory_valid": bool(inventory.get("valid", False)),
        "inventory_recount": inventory.get("recount", {}),
        "visualizations_complete": bool(visualization.get("all_expected_files_exist", False)),
        "output_dir": str(output_dir),
    }


def _confirmation_rows(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.is_file():
        return []
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))
    payload = _load_json(path, [])
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("records", "segment_rows", "segments_labeled"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def _write_semantic_preservation(
    *, context_path: Path, output_dir: Path, confirmations_path: Path | None
) -> dict[str, Any]:
    raw_report = _load_json(output_dir / "source_segment_preservation.json", {}) or {}
    context = load_task_context(context_path)
    rows = _confirmation_rows(confirmations_path)
    semantic_counts = None
    semantic_audit = output_dir / "segment_semantic_resolution_audit.csv"
    if semantic_audit.is_file():
        with semantic_audit.open(newline="", encoding="utf-8-sig") as handle:
            semantic_rows = list(csv.DictReader(handle))
        semantic_counts = {
            int(float(row["segment_id"])): int(float(row.get("voxel_count", 0) or 0))
            for row in semantic_rows if row.get("segment_id") not in (None, "")
        }
    report = build_semantic_target_preservation_report(
        context=context,
        confirmation_rows=rows,
        raw_counts=(semantic_counts or raw_report.get("raw_counts", {})),
        clean_counts=(semantic_counts or raw_report.get("clean_counts", {})),
    )
    (output_dir / "semantic_target_preservation.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def run_model_build(
    *,
    task_context_path: str | Path,
    project_root: str | Path | None = None,
    inventory_profile_path: str | Path | None = None,
    clean_output: bool = False,
    check: bool = True,
    allow_unverified_contract: bool = False,
    model_source_override: str | dict[str, Any] | None = None,
    run_id: str | None = None,
) -> RowColumnRunResult:
    root = resolve_project_root(project_root)
    runtime_dir = root / "pipeline_runtime"
    registry = LocalModelRegistry.from_environment(root)
    contract_record = registry.resolve(task_context_path)
    context = Path(contract_record.context_path).expanduser().resolve()
    normalized_context = load_task_context(context)
    execution_policy = resolve_execution_policy(normalized_context)
    contract = validate_model_contract(
        project_root=root,
        context_path=context,
        allow_unverified=allow_unverified_contract,
        model_source_override=model_source_override,
    )
    run_store = LocalRunStore.from_environment(root)
    run_paths = run_store.create(
        model_id=contract.model_id,
        contract_uri=contract_record.canonical_uri,
        run_id=run_id,
        replace=bool(clean_output and run_id),
        metadata={"contract_version": contract_record.version_id},
    )
    output_dir = run_paths.artifacts_dir
    log_path = run_paths.logs_dir / "row_column_pipeline.log"
    shutil.copy2(context, run_paths.inputs_dir / "task_context.json")
    if contract.confirmations_path:
        source_confirmation = Path(contract.confirmations_path)
        shutil.copy2(source_confirmation, run_paths.inputs_dir / source_confirmation.name)
    if inventory_profile_path is not None:
        inventory_snapshot = Path(inventory_profile_path).expanduser().resolve()
        if inventory_snapshot.is_file():
            shutil.copy2(inventory_snapshot, run_paths.inputs_dir / inventory_snapshot.name)
    LocalRunStore.update(
        run_paths,
        status="running",
        contract_validation=contract.to_dict(),
    )

    env = os.environ.copy()
    backend_path = str(root / "backend")
    prior = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = backend_path + (os.pathsep + prior if prior else "")
    env["BRICKSMART_TASK_CONTEXT"] = str(context)
    env["BRICKSMART_PROJECT_ROOT"] = str(root)
    env["BRICKSMART_ALLOW_UNVERIFIED_CONTRACT"] = "1" if allow_unverified_contract else "0"
    env["BRICKSMART_RESOLVED_MODEL_PATH"] = contract.source_model_path
    env["BRICKSMART_RESOLVED_MODEL_URI"] = contract.source_model_uri
    env["BRICKSMART_RESOLVED_MODEL_SHA256"] = contract.source_model_sha256 or ""
    env["BRICKSMART_OUTPUT_DIR"] = str(output_dir)
    env["BRICKSMART_RUN_ID"] = run_paths.run_id
    env["BRICKSMART_EXECUTION_MODE"] = execution_policy.mode
    env["BRICKSMART_RUNTIME_LLM_ALLOWED"] = (
        "1" if execution_policy.runtime_llm_effective else "0"
    )
    if inventory_profile_path is not None:
        env["BRICKSMART_INVENTORY_PROFILE"] = str(Path(inventory_profile_path).expanduser().resolve())
    env.setdefault("MPLBACKEND", "Agg")

    with log_path.open("w", encoding="utf-8") as log:
        completed = subprocess.run(
            [sys.executable, "-m", "bricksmart.row_column_engine"],
            cwd=runtime_dir,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    log_text = log_path.read_text(encoding="utf-8")
    inventory_infeasibility = (
        _inventory_infeasibility_from_log(log_text)
        if completed.returncode != 0
        else None
    )
    if inventory_infeasibility is not None:
        _write_inventory_infeasibility_artifacts(
            output_dir=output_dir,
            outcome=inventory_infeasibility,
            inventory_profile_path=inventory_profile_path,
        )
        LocalRunStore.update(
            run_paths,
            status="infeasible",
            returncode=0,
            engine_returncode=completed.returncode,
            log_path=str(log_path),
        )
    elif completed.returncode != 0:
        LocalRunStore.update(
            run_paths,
            status="failed",
            returncode=completed.returncode,
            log_path=str(log_path),
        )
        if check:
            tail = "\n".join(log_text.splitlines()[-100:])
            raise RuntimeError(
                f"Model build failed with exit code {completed.returncode}.\n{tail}"
            )

    semantic_report = _write_semantic_preservation(
        context_path=context,
        output_dir=output_dir,
        confirmations_path=(Path(contract.confirmations_path) if contract.confirmations_path else None),
    )
    planner_summary = summarize_row_column_output(output_dir)
    planner_final_claim_valid = bool(planner_summary.get("final_claim_valid", False))
    summary = {
        **planner_summary,
        "planner_final_claim_valid": planner_final_claim_valid,
        "execution_policy": execution_policy.to_dict(),
        "run_id": run_paths.run_id,
        "run_dir": str(run_paths.run_dir),
        "artifacts_dir": str(output_dir),
        "contract_uri": contract_record.canonical_uri,
        "model_contract": contract.to_dict(),
        "semantic_target_preservation": semantic_report,
    }

    manifest_path = write_checkpoint_manifest(
        project_root=root,
        context_path=context,
        output_dir=output_dir,
        confirmations_path=contract.confirmations_path,
    )
    summary["model_checkpoint_manifest"] = str(manifest_path)

    if completed.returncode == 0 and planner_final_claim_valid:
        from bricksmart.reporting.true_build_player import write_true_build_player

        write_true_build_player(
            output_dir=output_dir,
            catalog_path=contract.catalog_path,
            context_path=context,
        )
        planner_summary = summarize_row_column_output(output_dir)
        planner_final_claim_valid = bool(planner_summary.get("final_claim_valid", False))
        summary = {
            **planner_summary,
            "planner_final_claim_valid": planner_final_claim_valid,
            "execution_policy": execution_policy.to_dict(),
            "run_id": run_paths.run_id,
            "run_dir": str(run_paths.run_dir),
            "artifacts_dir": str(output_dir),
            "contract_uri": contract_record.canonical_uri,
            "model_contract": contract.to_dict(),
            "semantic_target_preservation": semantic_report,
            "model_checkpoint_manifest": str(manifest_path),
        }

    if not execution_policy.final_claim_eligible:
        summary["final_claim_valid"] = False
        summary["final_status"] = "PROVISIONAL_EXPLORATORY"
        summary["claim_reason"] = (
            "Exploratory execution is not eligible for a validated final claim. "
            "Register the reviewed decisions in a validated contract and rerun."
        )
    else:
        summary["final_claim_valid"] = planner_final_claim_valid

    build_html = output_dir / "build_instructions.html"
    legacy_html = output_dir / "visualizations" / "proper_complete_build_steps.html"
    summary["build_instructions_html"] = str(build_html) if build_html.is_file() else None
    summary["true_build_player_html"] = str(legacy_html) if legacy_html.is_file() else None
    summary["engine_returncode"] = completed.returncode
    timeline = output_dir / "true_complete_build_steps.csv"
    if timeline.is_file():
        with timeline.open(newline="", encoding="utf-8") as handle:
            summary["true_build_step_count"] = sum(1 for _ in csv.DictReader(handle))
    else:
        summary["true_build_step_count"] = 0

    run_status = (
        "succeeded"
        if summary["final_claim_valid"]
        else "infeasible"
        if summary.get("final_status") == "INFEASIBLE_INVENTORY"
        else "provisional"
        if planner_final_claim_valid and not execution_policy.final_claim_eligible
        else "incomplete"
    )
    LocalRunStore.update(
        run_paths,
        status=run_status,
        returncode=(0 if inventory_infeasibility is not None else completed.returncode),
        engine_returncode=completed.returncode,
        summary=summary,
        log_path=str(log_path),
    )
    if (
        check
        and not summary["final_claim_valid"]
        and summary.get("final_status") != "INFEASIBLE_INVENTORY"
    ):
        raise RuntimeError(
            "Model pipeline completed but the final claim gate failed. "
            f"See {run_paths.run_dir}"
        )
    return RowColumnRunResult(
        project_root=root,
        context_path=context,
        contract_uri=contract_record.canonical_uri,
        run_id=run_paths.run_id,
        run_dir=run_paths.run_dir,
        output_dir=output_dir,
        returncode=(0 if inventory_infeasibility is not None else completed.returncode),
        log_path=log_path,
        summary=summary,
    )
