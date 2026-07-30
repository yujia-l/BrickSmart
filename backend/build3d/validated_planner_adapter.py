"""Adapter from the KidSpark Bang flow to the validated BrickSmart planner."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from bricksmart.model_registry import LocalModelRegistry
from bricksmart.model_store.local import LocalModelStore
from bricksmart.row_column_runner import run_model_build


ENABLED_SOLVER_FAMILIES = [
    "rotation_block",
    "hinge_block",
    "big_wheel",
    "small_wheel",
    "standard_2x2x2",
    "standard_2x3x2",
    "standard_2x4x2",
]

STRUCTURAL_FAMILIES = [
    "standard_2x2x2",
    "standard_2x3x2",
    "standard_2x4x2",
]

DEFAULT_ALLOWED_SEGMENT_LABELS = [
    "body",
    "fuselage",
    "wing_left",
    "wing_right",
    "left_wing",
    "right_wing",
    "wing",
    "tail_left",
    "tail_right",
    "left_tail",
    "right_tail",
    "tail",
    "wheel_left",
    "wheel_right",
    "left_wheel",
    "right_wheel",
    "wheel",
    "nose",
    "propeller",
    "connector_strut",
    "decorative",
    "unknown",
]

KIDSPARK_VALIDATED_PLANNER_TIMEOUT_SECONDS = 300


def run_validated_planner(
    *,
    context: dict[str, Any],
    obj_path: Path | None,
    segment_rows: list[dict[str, Any]],
    job_dir: Path,
) -> dict[str, Any]:
    """Run the validated BrickSmart planner and return UI-ready metadata.

    The caller may still generate diagnostic notebook images, but this result is
    the authoritative source for inventory, final claim, and build steps.
    """
    if obj_path is None or not obj_path.is_file():
        return _skipped("NO_SOURCE_OBJ", "No segmented OBJ was available for validated planning.")

    project_root = Path(__file__).resolve().parents[2]
    planner_dir = job_dir / "validated_planner"
    planner_dir.mkdir(parents=True, exist_ok=True)
    coarse_grouped = _uses_coarse_segment_rows(segment_rows)

    try:
        planner_obj_path = _utf8_obj_copy(obj_path, planner_dir)
        model_record = _import_model(project_root, planner_obj_path, context)
        confirmations_path = _write_segment_confirmations(planner_dir, segment_rows, context)
        task_context_path = _write_task_context(
            planner_dir=planner_dir,
            context=context,
            obj_path=planner_obj_path,
            model_record=model_record,
            confirmations_path=confirmations_path,
            coarse_grouped=coarse_grouped,
            segment_rows=segment_rows,
        )
        registry = LocalModelRegistry.from_environment(project_root)
        contract_record = registry.register_files(
            task_context_path=task_context_path,
            confirmations_path=confirmations_path,
            contract_id=_safe_id(f"session-{job_dir.name}-{context.get('artifact_label', 'model')}"),
            metadata={"source": "kidspark_bang_adapter", "job_dir": str(job_dir)},
        )
        inventory_profile = _inventory_profile_path(project_root, context)
        result = run_model_build(
            task_context_path=contract_record.canonical_uri,
            project_root=project_root,
            inventory_profile_path=inventory_profile,
            allow_unverified_contract=True,
            check=False,
            run_id=_safe_id(f"{job_dir.name}-{context.get('artifact_label', 'model')}"),
            timeout_seconds=KIDSPARK_VALIDATED_PLANNER_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # The UI should show a useful validation failure.
        return _failed("VALIDATED_PLANNER_ERROR", str(exc))

    return _normalize_result(result.summary, result.output_dir, coarse_grouped=coarse_grouped)


def _utf8_obj_copy(obj_path: Path, planner_dir: Path) -> Path:
    """Return a planner-local OBJ that is always readable as UTF-8 text."""
    raw = obj_path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    sanitized = planner_dir / f"{obj_path.stem}_utf8.obj"
    sanitized.write_text(text, encoding="utf-8")
    return sanitized


def apply_catalog_constraints(context: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a model context enriched with catalog-aware defaults."""
    enriched = dict(context)
    build_constraints = dict(enriched.get("build_constraints") or {})
    explicit_targets = build_constraints.get("semantic_segment_targets")
    if explicit_targets:
        max_segments = int(build_constraints.get("max_semantic_segments") or 5)
        build_constraints["semantic_segment_targets"] = [
            _clean_semantic_target(value)
            for value in explicit_targets
            if _clean_semantic_target(value)
        ][:max_segments]
    else:
        build_constraints["semantic_segment_targets"] = semantic_segment_targets(enriched)
    if str(build_constraints.get("inventory_mode") or "standard_kit") != "unlimited":
        build_constraints["required_visible_parts"] = list(build_constraints["semantic_segment_targets"])
    else:
        build_constraints.setdefault("required_visible_parts", list(build_constraints["semantic_segment_targets"]))
    enriched["build_constraints"] = build_constraints
    object_profile = dict(enriched.get("object_profile") or {})
    object_profile.setdefault("object_type_hint", _object_type_hint(enriched))
    object_profile.setdefault("allowed_segment_labels", DEFAULT_ALLOWED_SEGMENT_LABELS)
    enriched["object_profile"] = object_profile
    enriched.setdefault(
        "coordinate_frame",
        {
            "lateral_axis": 0,
            "depth_axis": 1,
            "vertical_axis": 2,
            "front_direction": "+Y",
            "ground_axis": "Z",
        },
    )
    enriched.setdefault(
        "active_families",
        {
            "solver_enabled": ENABLED_SOLVER_FAMILIES,
            "structural": STRUCTURAL_FAMILIES,
            "functional_attachment": ["big_wheel", "small_wheel"],
            "connector": ["rotation_block", "hinge_block"],
        },
    )
    enriched.setdefault("connector_rules", _connector_rules_from_parts(enriched.get("parts", [])))
    enriched.setdefault("functional_attachments", _functional_attachments_from_parts(enriched.get("parts", [])))
    enriched.setdefault(
        "model_constraints",
        {
            "symmetry": build_constraints.get("symmetry", "auto"),
            "thin_features_policy": "warn_and_simplify",
            "unsupported_detail_policy": "optional_or_report",
        },
    )
    enriched.setdefault("inventory_mode", build_constraints.get("inventory_mode", "standard_kit"))
    enriched.setdefault(
        "buildability_budget",
        {
            "inventory_mode": enriched["inventory_mode"],
            "max_validated_blocks": int(build_constraints.get("max_validated_blocks") or 32),
            "max_semantic_segments": int(build_constraints.get("max_semantic_segments") or 5),
            "max_moving_parts": int(build_constraints.get("max_moving_parts") or 1),
            "min_segment_survival_fraction": float(build_constraints.get("min_segment_survival_fraction") or 0.75),
            "minimum_surviving_segments": int(build_constraints.get("minimum_surviving_segments") or 2),
        },
    )
    enriched["catalog_prompt_constraints"] = {
        "enabled_solver_families": ENABLED_SOLVER_FAMILIES,
        "structural_families": STRUCTURAL_FAMILIES,
        "disabled_families_not_for_validated_builds": [
            "feature_beam_3x1x1",
            "feature_beam_7x1x1",
            "feature_beam_curved",
            "angle_joint",
            "angle_symmetrical",
            "bucket",
            "bucket_arms",
        ],
        "rodin_geometry_guidance": (
            "Use simple chunky block-toy geometry, separated moving parts, broad 2x2-compatible "
            "features, and avoid thin fins, tiny details, smooth tapers, dense curves, or unsupported "
            "decorative parts. Keep standard-kit classroom builds small enough for about 30 blocks, "
            "four to five semantic parts, and one primary moving feature unless the teacher explicitly "
            "chooses an unlimited reference preview."
        ),
    }
    return enriched


def semantic_segment_targets(context: dict[str, Any]) -> list[str]:
    """Return the small set of large regions Rodin should preserve for validation.

    Teacher-facing part names can be more detailed than the physical validated
    model can afford. This helper groups static details into coarse regions so a
    plane can still discuss cargo/tail/body while Rodin/Bang only tries to
    preserve a few classroom-buildable segments.
    """
    constraints = context.get("build_constraints") or {}
    max_segments = int(constraints.get("max_semantic_segments") or 5)
    explicit_targets = constraints.get("semantic_segment_targets") or []
    if explicit_targets:
        return [
            _clean_semantic_target(value)
            for value in explicit_targets
            if _clean_semantic_target(value)
        ][:max_segments]
    max_moving = int(constraints.get("max_moving_parts") or 1)
    parts = context.get("parts") or []
    artifact = str(context.get("artifact_label") or context.get("artifact_family") or "model").lower()

    moving_names: list[str] = []
    static_names: list[str] = []
    for part in parts:
        name = str(part.get("part_name", "")).strip()
        if not name:
            continue
        movement = str(part.get("movement", "static")).lower()
        if movement != "static":
            moving_names.append(name)
        else:
            static_names.append(name)

    targets: list[str] = []
    for name in moving_names[:max_moving]:
        targets.append(f"{name} as the one separated moving feature")

    static_text = " ".join(static_names).lower()
    if any(token in artifact or token in static_text for token in ["plane", "airplane", "vehicle", "car", "truck", "delivery"]):
        targets.extend(
            [
                "single main body/fuselage with cargo nose and tail details merged",
                "one broad left-right wing or support slab",
            ]
        )
        if any(token in static_text for token in ["wheel", "landing"]):
            targets.append("paired wheel or landing anchors")
    elif any(token in artifact or token in static_text for token in ["house", "bakery", "shop", "building", "wall", "roof"]):
        targets.extend(
            [
                "single boxy building shell with walls and roof merged",
                "front opening or counter detail merged into the shell",
            ]
        )
    elif any(token in artifact or token in static_text for token in ["tree", "plant", "garden"]):
        targets.extend(["single trunk/body column", "one broad canopy or platform mass"])
    else:
        targets.extend(["single main body/core", "one broad support/base region"])

    deduped: list[str] = []
    seen: set[str] = set()
    for target in targets:
        key = target.lower()
        if key not in seen:
            deduped.append(target)
            seen.add(key)
    return deduped[:max_segments]


def _clean_semantic_target(value: Any) -> str:
    """Keep semantic targets stable when they round-trip through comma-based UI fields."""
    return " ".join(str(value or "").replace(",", " ").split())


def _import_model(project_root: Path, obj_path: Path, context: dict[str, Any]) -> Any:
    store = LocalModelStore.from_environment(project_root)
    model_id = _safe_id(f"{context.get('artifact_label', 'model')}-{obj_path.stem}")
    return store.import_file(
        obj_path,
        model_id=model_id,
        metadata={"source": "kidspark_bang", "artifact_label": context.get("artifact_label")},
    )


def _write_segment_confirmations(
    planner_dir: Path,
    segment_rows: list[dict[str, Any]],
    context: dict[str, Any],
) -> Path:
    path = planner_dir / "segment_confirmations.csv"
    rows = segment_rows or _fallback_segment_rows(context)
    fieldnames = [
        "segment_id",
        "confirmed_label",
        "confirmed_name",
        "confirmation_status",
        "confirmation_source",
        "semantic_group_id",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index, row in enumerate(rows, start=1):
            label = _catalog_label(row.get("label") or row.get("confirmed_label") or row.get("source_name"))
            source_ids = [
                _int(value, index)
                for value in (row.get("source_segment_ids") or [row.get("segment_id", index)])
            ]
            group_id = str(row.get("semantic_group_id") or f"semantic_region_{index}")
            for segment_id in sorted(set(source_ids)):
                writer.writerow(
                    {
                        "segment_id": segment_id,
                        "confirmed_label": label,
                        "confirmed_name": row.get("confirmed_name") or row.get("source_name") or label.replace("_", " ").title(),
                        "confirmation_status": row.get("confirmation_status") or "confirmed",
                        "confirmation_source": row.get("confirmation_source") or "kidspark_teacher_context",
                        "semantic_group_id": group_id,
                    }
                )
    return path


def _source_segment_groups_from_rows(
    segment_rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Translate KidSpark semantic rows into the v1.2.5 grouping contract."""
    groups: list[dict[str, Any]] = []
    for index, row in enumerate(segment_rows or [], start=1):
        if str(row.get("source_segment_grouping") or "") != "coarse_validated_region":
            continue
        source_ids = []
        for value in row.get("source_segment_ids", []) or []:
            try:
                source_ids.append(int(value))
            except (TypeError, ValueError):
                continue
        if not source_ids:
            continue
        groups.append(
            {
                "target_id": str(row.get("semantic_group_id") or f"semantic_region_{index}"),
                "display_name": str(row.get("function") or row.get("source_name") or f"Semantic region {index}"),
                "source_segment_ids": sorted(set(source_ids)),
                "required": True,
                "preservation_mode": "any_member_or_merged",
            }
        )
    return groups


def _write_task_context(
    *,
    planner_dir: Path,
    context: dict[str, Any],
    obj_path: Path,
    model_record: Any,
    confirmations_path: Path,
    coarse_grouped: bool = False,
    segment_rows: list[dict[str, Any]] | None = None,
) -> Path:
    enriched = apply_catalog_constraints(context)
    inventory_mode = str(enriched.get("inventory_mode") or "standard_kit")
    inventory_file = "unlimited.yaml" if inventory_mode == "unlimited" else "standard_kit.yaml"
    payload = {
        "schema_version": "bricksmart-model-contract-1.0",
        "contract_id": _safe_id(f"kidspark-{planner_dir.parent.name}"),
        "model_id": model_record.model_id,
        "task_id": _safe_id(f"kidspark-{planner_dir.parent.name}"),
        "display_name": enriched.get("artifact_label", "KidSpark BrickSmart model"),
        "object_type_hint": (enriched.get("object_profile") or {}).get("object_type_hint", "kidspark_model"),
        "model_source": {
            "uri": model_record.canonical_uri,
            "model_id": model_record.model_id,
            "filename": obj_path.name,
            "expected_sha256": model_record.sha256,
        },
        "paths": {
            "relative_to": "pipeline_runtime",
            "catalog_csv": "../block_catalog/block_definitions.csv",
        },
        "execution_policy": {
            "mode": "validated",
            "allow_runtime_llm": False,
            "final_claim_requires_deterministic_inputs": True,
        },
        "contract_policy": {"reject_provisional_metadata": False},
        "conversation_contract": {
            "allow_catalog_role_query_without_exact_family": True,
            "model_task_context_scope": "build_intent_catalog_queries_and_model_constraints",
            "segment_confirmation_csv_scope": "source_segment_identity_and_semantics_only",
            "unconfirmed_exact_family_behavior": "needs_instructor_confirmation_do_not_guess",
        },
        "inventory": {
            "enforce": inventory_mode != "unlimited",
            "final_recount_required": True,
            "profile_path": f"../config/inventory/{inventory_file}",
            "violation_policy": "fail",
            "coordination_mode": "global_deferred",
        },
        "segment_semantics": {
            "allowed_labels": (enriched.get("object_profile") or {}).get("allowed_segment_labels", DEFAULT_ALLOWED_SEGMENT_LABELS),
            "labels_file": confirmations_path.name,
            "confirmation_policy": {"labels_file_default_status": "confirmed"},
            "auto_confirm_from_obj_object_names": False,
            "fail_when_all_labels_unknown": False,
            "unknown_label": "unknown",
            "source_segment_groups": _source_segment_groups_from_rows(segment_rows),
        },
        "segment_assembly": {
            "interface_detection": {"minimum_contact_area": 1},
            "segment_packing": {
                "stop_after_first_valid_build_axis": False,
                "candidate_build_axes": ["+Y", "+X", "-Y", "-X"],
            },
            "structural_connector_policy": {
                "join_mode": "direct_structural_lock",
                "required_on_each_assembly_graph_edge": True,
                "rigid_join_confirmation_status": "confirmed",
                "rigid_join_decision_source": "kidspark_context",
                "catalog_selector": "segment_connector",
            },
            "custom_functional_subassemblies": _functional_assemblies_from_segments(enriched, segment_rows),
        },
        "structuralization": {"enabled": True},
        "voxelization": {
            "grid_size": int((enriched.get("voxelization") or {}).get("grid_size", 16)),
            "samples_per_triangle": int((enriched.get("voxelization") or {}).get("samples_per_triangle", 30)),
            "random_seed": int((enriched.get("voxelization") or {}).get("random_seed", 0)),
            "preprocessing": {
                "enforce_2x2_footprint": True,
                "clean_vertical_columns": True,
                "thicken_floor_and_ceiling": True,
                "remap_segments_to_2x2_grid": True,
                "split_disconnected_components": not coarse_grouped,
            },
        },
        "catalog": {
            "selectors": {
                "structural": {
                    "all": [
                        {"field": "current_solver_enabled", "op": "truthy"},
                        {"field": "category", "op": "equals", "value": "structural_block"},
                    ]
                },
                "segment_connector": {
                    "all": [
                        {"field": "current_solver_enabled", "op": "truthy"},
                        {"field": "functional_role", "op": "equals", "value": "connector"},
                    ]
                },
            }
        },
        "functional_attachment_policy": {
            "allow_off_grid_candidate_geometry": True,
            "allow_structural_baseline_when_pending": True,
            "candidate_generation_mode": "interface_driven",
            "enforce_exact_expected_count_after_grouping": True,
            "fail_when_required_candidate_missing": False,
            "fail_when_required_labels_missing": False,
            "max_candidates_per_target": 250,
            "minimum_candidate_source_overlap_ratio": 0.15,
            "minimum_contact_area": 2,
            "required_for_complete_build_claim": True,
            "reservation_mode": "selected_candidate_footprint",
            "reserve_clearance": True,
            "selection_mode": "best_valid_per_physical_target",
            "source_removal_mode": "selected_candidate_overlap_and_clearance",
        },
        "functional_attachments": _functional_attachments_from_parts(
            enriched.get("parts", []),
            segment_rows=segment_rows,
        ),
        "functional_assemblies": _functional_assemblies_from_segments(enriched, segment_rows),
        "visualization": {
            "enabled": False,
            "external_player_generated_by_runner": True,
            "generate_proper_complete_build_step_player": False,
            "save_interactive_html": False,
        },
        "runtime_logging": {
            "show_gate_messages": True,
            "show_planner_summary": True,
            "show_final_summary": True,
        },
        "frontend_metadata": {
            "build_constraints": enriched.get("build_constraints", {}),
            "functional_attachments": enriched.get("functional_attachments", []),
            "connector_rules": enriched.get("connector_rules", []),
            "active_families": enriched.get("active_families", {}),
            "coarse_segment_grouping": coarse_grouped,
        },
    }
    path = planner_dir / "task_context.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _normalize_result(summary: dict[str, Any], output_dir: Path, *, coarse_grouped: bool = False) -> dict[str, Any]:
    inventory_validation = _load_json(output_dir / "inventory_validation.json", {})
    inventory_feasibility = _load_json(output_dir / "inventory_feasibility.json", {})
    global_inventory = _load_json(output_dir / "global_inventory_allocation.json", {})
    source_preservation = _load_json(output_dir / "source_segment_preservation.json", {})
    semantic_preservation = summary.get("semantic_target_preservation") or _load_json(
        output_dir / "semantic_target_preservation.json", {}
    )
    final_parts = _read_csv(output_dir / "final_parts.csv")
    true_steps = _read_csv(output_dir / "true_complete_build_steps.csv")
    final_valid = bool(summary.get("final_claim_valid"))
    final_status = summary.get("final_status") or inventory_feasibility.get("status") or ("PASS" if final_valid else "INCOMPLETE")
    semantic_status = str(semantic_preservation.get("status") or "")
    source_status = str(source_preservation.get("status") or "")
    semantic_failed = semantic_status.startswith("FAIL")
    source_failed = source_status.startswith("FAIL")
    preservation_failed = semantic_failed or (source_failed and not coarse_grouped)
    reason = None
    recommendation = None
    shortages = (
        inventory_feasibility.get("shortages")
        or inventory_validation.get("shortages")
        or global_inventory.get("shortages")
        or {}
    )
    overages = inventory_validation.get("overages") or {}
    if not final_valid and summary.get("timed_out"):
        final_status = "PLANNER_TIMEOUT"
        timeout_seconds = int(summary.get("timeout_seconds") or KIDSPARK_VALIDATED_PLANNER_TIMEOUT_SECONDS)
        reason = (
            f"The strict validated planner reached its {timeout_seconds}-second interactive limit before "
            "it could produce complete standard-kit instructions."
        )
        recommendation = (
            "Use the notebook/CSP plan when its block, segment, connectivity, and connector checks pass; "
            "otherwise regenerate a simpler model."
        )
    elif not final_valid and preservation_failed and final_status != "INFEASIBLE_INVENTORY":
        final_status = "NEEDS_SIMPLER_MODEL"
        missing = semantic_preservation.get("missing_ungrouped_authoritative_source_segment_ids") or source_preservation.get("missing_segment_ids") or []
        reason = (
            "The validated planner could not preserve every teacher-confirmed segment "
            f"after voxelization/physicalization. Missing segment ids: {missing or 'unknown'}."
        )
        recommendation = (
            "Regenerate a simpler model with fewer large parts, clearer separation between moving and static pieces, "
            "and broader 2x2-compatible surfaces before approving the build plan."
        )
    elif not final_valid and (shortages or overages or final_status in {"INFEASIBLE_INVENTORY", "invalid_inventory_or_build_claim", "FAIL_GLOBAL_INVENTORY_ALLOCATION"}):
        final_status = "NEEDS_SIMPLER_MODEL"
        reason = _inventory_failure_reason(shortages=shortages, overages=overages, global_inventory=global_inventory)
        recommendation = (
            "Regenerate a simpler, more compact model with fewer source fragments and broader 2x2-compatible surfaces. "
            "Prefer one merged body, one broad support/wing surface, and one clearly separated moving feature so the "
            "validated planner can use the standard kit instead of many small cube clusters."
        )
    elif not final_valid and final_status == "INCOMPLETE":
        final_status = "NEEDS_SIMPLER_MODEL"
        reason = (
            "The validated planner stopped before it could produce complete standard-kit instructions. "
            "This usually means the segmented regions are still too fragmented, disconnected, or hard to pack into legal BrickSmart rows."
        )
        recommendation = (
            "Regenerate a simpler model with fewer large regions, one compact connected static mass, "
            "one clearly separated moving feature, and strong flat 2x2-compatible contact surfaces."
        )
    payload = {
        "enabled": True,
        "build_status": final_status,
        "final_claim_valid": final_valid,
        "inventory_mode": inventory_validation.get("inventory_mode") or inventory_feasibility.get("inventory_mode"),
        "inventory_feasibility": inventory_feasibility or None,
        "inventory_validation": inventory_validation or None,
        "shortages": shortages,
        "overages": overages,
        "run_id": summary.get("run_id"),
        "run_dir": summary.get("run_dir"),
        "artifacts_dir": str(output_dir),
        "build_instructions_html": summary.get("build_instructions_html"),
        "true_build_player_html": summary.get("true_build_player_html"),
        "true_build_step_count": int(summary.get("true_build_step_count") or len(true_steps)),
        "final_block_count": int(summary.get("final_block_count") or len(final_parts)),
        "inventory_rows": _inventory_rows(inventory_validation, final_parts),
        "instruction_steps": _instruction_steps(true_steps) if final_valid else [],
        "final_parts": final_parts,
        "summary": summary,
    }
    if reason:
        payload["reason"] = reason
    if recommendation:
        payload["recommendation"] = recommendation
    if preservation_failed or (source_failed and coarse_grouped):
        payload["segment_viability"] = {
            "semantic_preservation_status": semantic_status or None,
            "source_preservation_status": source_status or None,
            "source_preservation_ignored_for_coarse_groups": bool(source_failed and coarse_grouped and not semantic_failed),
            "missing_segment_ids": semantic_preservation.get("missing_ungrouped_authoritative_source_segment_ids")
            or source_preservation.get("missing_segment_ids")
            or [],
            "confirmed_segment_count": len(
                semantic_preservation.get("ungrouped_authoritative_source_segment_ids") or []
            )
            or None,
        }
    return payload


def _uses_coarse_segment_rows(segment_rows: list[dict[str, Any]] | None) -> bool:
    return bool(segment_rows) and all(
        str(row.get("source_segment_grouping") or "") == "coarse_validated_region"
        for row in segment_rows
    )


def _inventory_failure_reason(
    *,
    shortages: dict[str, Any],
    overages: dict[str, Any],
    global_inventory: dict[str, Any],
) -> str:
    parts: list[str] = []
    if overages:
        details = ", ".join(f"{family}: {info}" for family, info in sorted(overages.items()))
        parts.append(f"standard-kit inventory was over-used ({details})")
    if shortages:
        details = ", ".join(f"{family}: {info}" for family, info in sorted(shortages.items()))
        parts.append(f"required pieces were short ({details})")
    global_status = global_inventory.get("status")
    if global_status and global_status != "PASS":
        parts.append(f"global inventory allocation returned {global_status}")
    if not parts:
        parts.append("the validated planner could not allocate the standard kit to this shape")
    return "The model is visually plausible, but " + "; ".join(parts) + "."


def _instruction_steps(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    steps = []
    for row in rows:
        number = _int(row.get("global_step"), len(steps) + 1)
        steps.append(
            {
                "step_number": number,
                "title": row.get("title") or f"Validated step {number}",
                "teacher_instruction": row.get("instruction") or "",
                "student_instruction": row.get("instruction") or "",
                "phase": row.get("phase") or "Validated build",
                "segments": _ids(row.get("final_position_segment_ids")),
                "segment_labels": [],
                "inventory": [],
                "image_path": "",
                "multiview_path": "",
                "visible_block_ids": _ids(row.get("visible_block_ids")),
                "interface_id": row.get("interface_id") or "",
            }
        )
    return steps


def _inventory_rows(inventory_validation: dict[str, Any], final_parts: list[dict[str, str]]) -> list[dict[str, Any]]:
    recount = inventory_validation.get("recount") if isinstance(inventory_validation, dict) else None
    if isinstance(recount, dict) and recount:
        return [{"piece": family, "quantity": count} for family, count in sorted(recount.items())]
    counts = Counter(row.get("block_family") or row.get("family") for row in final_parts)
    return [{"piece": family, "quantity": count} for family, count in sorted(counts.items()) if family]


def _inventory_profile_path(project_root: Path, context: dict[str, Any]) -> Path:
    mode = str(context.get("inventory_mode") or (context.get("build_constraints") or {}).get("inventory_mode") or "standard_kit")
    filename = "unlimited.yaml" if mode == "unlimited" else "standard_kit.yaml"
    return project_root / "config" / "inventory" / filename


def _connector_rules_from_parts(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rules = []
    for part in parts:
        movement = str(part.get("movement", "static")).lower()
        if movement == "spinning":
            family = "rotation_block"
        elif movement == "pivoting":
            family = "hinge_block"
        else:
            continue
        rules.append(
            {
                "part_name": part.get("part_name", "moving part"),
                "promote_to_connection_type": movement,
                "allowed_connector_families": [family],
            }
        )
    return rules


def _functional_attachments_from_parts(
    parts: list[dict[str, Any]],
    *,
    segment_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    attachments = []
    segment_lookup = _segment_role_lookup(segment_rows)
    propeller_ids = segment_lookup.get("propeller", [])
    anchor_id = _primary_anchor_segment_id(segment_rows)
    if propeller_ids and anchor_id is not None:
        attachments.append(
            {
                "attachment_id": "propeller",
                "block_family_requirement": {
                    "allow_family_fallback": False,
                    "confirmation_status": "confirmed",
                    "decision_id": "kidspark_propeller_rotation_connector_family",
                    "decision_source": "teacher_planning_state",
                    "mode": "exact",
                    "required_block_family": "rotation_block",
                    "unconfirmed_behavior": "needs_instructor_confirmation",
                },
                "candidate_strategy": "rotation_connector_to_structural_propeller_subassembly",
                "catalog_family_selection_source": "kidspark_build_constraints",
                "catalog_query": {
                    "all": [
                        {"field": "current_solver_enabled", "op": "truthy"},
                        {"field": "functional_role", "op": "equals", "value": "connector"},
                        {"field": "placement_mode", "op": "equals", "value": "in_between"},
                        {"field": "motion_type", "op": "equals", "value": "free_rotation"},
                        {"field": "block_family", "op": "equals", "value": "rotation_block"},
                    ]
                },
                "count_policy": "exact_physical_instances",
                "expected_count": 1,
                "motion_type": "rotation",
                "physical_target_grouping": {
                    "manual_groups": [
                        {
                            "confirmation_source": "kidspark_teacher_context",
                            "physical_group_name": "Propeller Assembly",
                            "physical_target_id": "main_propeller",
                            "side": "center",
                            "source_segment_ids": propeller_ids,
                            "status": "confirmed",
                        }
                    ],
                    "mode": "semantic_and_interface_cluster",
                },
                "required": True,
                "required_block_family": "rotation_block",
                "semantic_confirmation_source": "segment_confirmation_csv",
                "semantic_labels": ["propeller", "propeller_blade"],
                "source_removal_policy": "semantic_replacement_group",
            }
        )
    rolling = [part for part in parts if str(part.get("movement", "")).lower() == "rolling"]
    if rolling:
        attachments.append(
            {
                "role": "wheel",
                "count": max(2, len(rolling)),
                "anchor_connection_type": "rigid",
                "functional_motion": "rotation",
                "placement_mode": "metadata_anchor_or_source_replacement",
                "allowed_families": ["big_wheel", "small_wheel"],
            }
        )
    return attachments


def _functional_assemblies_from_segments(
    context: dict[str, Any],
    segment_rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    segment_lookup = _segment_role_lookup(segment_rows)
    propeller_ids = segment_lookup.get("propeller", [])
    anchor_id = _primary_anchor_segment_id(segment_rows)
    if not propeller_ids or anchor_id is None:
        return []
    return [
        {
            "anchor_segment_id": int(anchor_id),
            "assembly_id": "main_propeller",
            "assembly_type": "motion_connected_structural_subassembly",
            "block_family_requirement": {
                "allow_family_fallback": False,
                "confirmation_status": "confirmed",
                "decision_id": "kidspark_propeller_structural_subassembly",
                "decision_source": "teacher_planning_state",
                "mode": "exact",
                "required_block_family": "standard_2x2x2",
            },
            "build_order": ["rotation_connector", "center_propeller_block", "lower_propeller_block", "upper_propeller_block"],
            "connector": {
                "axis": "Y",
                "motion_type": "free_rotation",
                "placement_policy": "outside_front_face_centered_on_symmetry_plane",
                "required_block_family": "rotation_block",
            },
            "connector_axis": "Y",
            "connector_motion_type": "free_rotation",
            "display_name": "Propeller Assembly",
            "enabled": True,
            "instruction_templates": {
                "connector": "Attach {display_name} connector block {block_ids} to {anchor_name}.",
                "member": "Add block {block_ids} to the {display_name} subassembly.",
            },
            "layout_axis": "Z",
            "members": {
                "block_family_requirement": {
                    "allow_family_fallback": False,
                    "confirmation_status": "confirmed",
                    "decision_id": "kidspark_propeller_structural_subassembly",
                    "decision_source": "teacher_planning_state",
                    "mode": "exact",
                    "required_block_family": "standard_2x2x2",
                },
                "catalog_query": {
                    "all": [
                        {"field": "current_solver_enabled", "op": "truthy"},
                        {"field": "functional_role", "op": "equals", "value": "structural"},
                        {"field": "block_family", "op": "equals", "value": "standard_2x2x2"},
                    ]
                },
                "count": 3,
                "layout_axis": "Z",
                "member_templates": [
                    {"member_role": "center", "offset_index": 0, "face_roles": {"+X": "female", "-X": "female", "+Y": "female", "-Y": "female", "+Z": "male", "-Z": "female"}},
                    {"member_role": "lower", "offset_index": -1, "face_roles": {"+X": "female", "-X": "female", "+Y": "female", "-Y": "female", "+Z": "male", "-Z": "female"}},
                    {"member_role": "upper", "offset_index": 1, "face_roles": {"+X": "male", "-X": "female", "+Y": "female", "-Y": "female", "+Z": "female", "-Z": "female"}},
                ],
                "required_block_family": "standard_2x2x2",
            },
            "migration_source": "kidspark_validated_adapter",
            "physical_target_id": "main_propeller",
            "placement_policy": "outside_front_face_centered_on_symmetry_plane",
            "required_block_family": "standard_2x2x2",
            "source_segment_ids": propeller_ids,
            "structural_block_count": 3,
            "validation": {
                "require_centered_on_symmetry_axis": True,
                "require_connector_to_anchor_lock": True,
                "require_connector_to_subassembly_lock": True,
                "require_internal_propeller_locking": True,
                "require_internal_subassembly_locking": True,
                "require_rotation_to_fuselage_lock": True,
                "require_rotation_to_propeller_lock": True,
                "require_three_structural_propeller_blocks": True,
            },
        }
    ]


def _segment_role_lookup(segment_rows: list[dict[str, Any]] | None) -> dict[str, list[int]]:
    roles: dict[str, list[int]] = {}
    for index, row in enumerate(segment_rows or [], start=1):
        segment_ids = [
            _int(value, index)
            for value in (row.get("source_segment_ids") or [row.get("segment_id", index)])
        ]
        label = _catalog_label(row.get("label") or row.get("confirmed_label") or row.get("source_name"))
        movement = str(row.get("movement", "")).lower()
        text = f"{label} {row.get('function', '')} {row.get('source_name', '')}".lower()
        if label == "propeller" or "propeller" in text or "rotor" in text or movement == "spinning":
            roles.setdefault("propeller", []).extend(segment_ids)
        elif label in {"body", "fuselage"} or any(token in text for token in ("body", "fuselage", "core", "shell")):
            roles.setdefault("body", []).extend(segment_ids)
        elif label in {"wing", "left_wing", "right_wing"} or "wing" in text:
            roles.setdefault("wing", []).extend(segment_ids)
    return {role: sorted(set(segment_ids)) for role, segment_ids in roles.items()}


def _primary_anchor_segment_id(segment_rows: list[dict[str, Any]] | None) -> int | None:
    roles = _segment_role_lookup(segment_rows)
    if roles.get("body"):
        return roles["body"][0]
    for index, row in enumerate(segment_rows or [], start=1):
        movement = str(row.get("movement", "static")).lower()
        label = _catalog_label(row.get("label") or row.get("confirmed_label") or row.get("source_name"))
        if movement == "static" and label != "propeller":
            return _int(row.get("segment_id"), index)
    return None


def _fallback_segment_rows(context: dict[str, Any]) -> list[dict[str, Any]]:
    parts = context.get("parts") or [{"part_name": context.get("artifact_label", "body")}]
    return [
        {
            "segment_id": index,
            "label": _catalog_label(part.get("part_name")),
            "source_name": part.get("part_name") or f"segment_{index}",
        }
        for index, part in enumerate(parts, start=1)
    ]


def _object_type_hint(context: dict[str, Any]) -> str:
    raw = str(context.get("artifact_family") or context.get("artifact_label") or "kidspark_model")
    return _safe_id(raw)


def _catalog_label(value: Any) -> str:
    label = _safe_id(str(value or "unknown")).replace("-", "_")
    aliases = {
        "wings": "wing",
        "left_wing": "left_wing",
        "right_wing": "right_wing",
        "wheels": "wheel",
        "landing_gear": "wheel",
        "body": "body",
        "main_body": "body",
        "body_fuselage": "body",
        "merged_body_fuselage": "body",
        "single_main_body_fuselage_with_cargo_nose_and_tail_details_merged": "body",
        "fuselage": "fuselage",
        "tail": "tail",
        "wing_slab": "wing",
        "support_slab": "wing",
        "broad_wing_slab": "wing",
        "one_broad_left_right_wing_or_support_slab": "wing",
        "propeller_blade": "propeller",
        "rotor": "propeller",
    }
    return aliases.get(label, label if label in DEFAULT_ALLOWED_SEGMENT_LABELS else "unknown")


def _safe_id(value: Any) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip()).strip("-.")
    return (text or "model").lower()


def _int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _ids(value: Any) -> list[int]:
    if value in (None, ""):
        return []
    ids = []
    for item in str(value).split(","):
        item = item.strip()
        if not item:
            continue
        try:
            ids.append(int(float(item)))
        except ValueError:
            continue
    return ids


def _load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _skipped(status: str, reason: str) -> dict[str, Any]:
    return {
        "enabled": False,
        "build_status": status,
        "final_claim_valid": False,
        "reason": reason,
        "instruction_steps": [],
        "inventory_rows": [],
        "shortages": {},
    }


def _failed(status: str, reason: str) -> dict[str, Any]:
    payload = _skipped(status, reason)
    payload["enabled"] = True
    return payload
