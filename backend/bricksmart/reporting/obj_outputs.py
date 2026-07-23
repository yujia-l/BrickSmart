"""Report writers for direct OBJ pipeline outputs.

This module serializes exploratory OBJ planning results, diagnostics, and
visualization inputs.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from bricksmart.io import dump_json as _write_json
from typing import Iterable

from bricksmart.inventory.ledger import InventoryLedger
from bricksmart.outputs.writers import write_run_outputs
from bricksmart.planning.voxel_models import ObjBuildResult
from bricksmart.reporting.visualization import (
    write_build_preview,
    write_final_catalog_png,
    write_segment_build_player,
    write_symmetry_top_png,
)


def _write_rows(path: Path, rows: Iterable[dict[str, object]]) -> None:
    """Write rows.
    
    :param path: Filesystem path used by the operation.
    :type path: Path
    :param rows: Row records to process.
    :type rows: Iterable[dict[str, object]]
    """
    materialized = list(rows)
    if not materialized:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in materialized:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in materialized:
            cooked = {
                key: json.dumps(value) if isinstance(value, (list, dict, tuple)) else value
                for key, value in row.items()
            }
            writer.writerow(cooked)


def write_obj_build_outputs(
    output_dir: str | Path,
    *,
    result: ObjBuildResult,
    ledger: InventoryLedger,
    include_html: bool = True,
) -> list[Path]:
    """Write obj build outputs.
    
    :param output_dir: Directory where generated artifacts are written.
    :type output_dir: str | Path
    :param result: The result value.
    :type result: ObjBuildResult
    :param ledger: Inventory ledger used by the operation.
    :type ledger: InventoryLedger
    :param include_html: Whether to include html.
    :type include_html: bool
    :returns: The result produced by the function.
    :rtype: list[Path]
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written = write_run_outputs(
        output_dir,
        result=result.planning_result,
        ledger=ledger,
    )

    model_summary = output_dir / "model_summary.json"
    _write_json(model_summary, result.model.to_summary())
    written.append(model_summary)

    catalog_audit = output_dir / "catalog_usage_audit.json"
    used_types = sorted({placement.block_type for placement in result.placements})
    _write_json(
        catalog_audit,
        {
            "catalog": result.catalog_summary,
            "used_block_types": used_types,
            "colors_from_catalog": {
                block_type: result.catalog_colors.get(block_type, "")
                for block_type in used_types
            },
            "shadow_catalog_used": False,
        },
    )
    written.append(catalog_audit)

    segment_path = output_dir / "source_segments.csv"
    with segment_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "segment_id",
            "vertex_count",
            "source_face_count",
            "triangulated_face_count",
            "bounds_min",
            "bounds_max",
            "extents",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for segment in result.model.segments:
            row = segment.to_summary()
            for field in ("bounds_min", "bounds_max", "extents"):
                row[field] = json.dumps(row[field])
            writer.writerow(row)
    written.append(segment_path)

    voxel_summary = output_dir / "voxelization_summary.json"
    _write_json(voxel_summary, result.voxel_model.to_summary())
    written.append(voxel_summary)

    voxels_path = output_dir / "target_voxels.csv"
    with voxels_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["x", "y", "z", "segment_id", "memberships"]
        )
        writer.writeheader()
        for voxel in sorted(result.voxel_model.target_voxels):
            writer.writerow(
                {
                    "x": voxel[0],
                    "y": voxel[1],
                    "z": voxel[2],
                    "segment_id": result.voxel_model.segment_by_voxel[voxel],
                    "memberships": json.dumps(
                        result.voxel_model.memberships_by_voxel[voxel]
                    ),
                }
            )
    written.append(voxels_path)

    detailed_parts = output_dir / "final_parts_detailed.csv"
    with detailed_parts.open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "part_id", "step", "block_type", "segment_id",
            "symmetry_group_id", "mirror_part_id", "symmetry_group_kind",
            "segment_order_index", "segment_step", "segment_phase",
            "origin_x", "origin_y", "origin_z",
            "size_x", "size_y", "size_z",
            "target_overlap", "newly_covered", "overhang_voxels",
            "segment_purity", "effective_score", "component_seed",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        selected_by_id = {
            f"part_{selected.selection_index:03d}": selected
            for selected in result.selected_blocks
        }
        symmetry_by_part: dict[str, dict[str, object]] = {}
        for group in result.symmetry_groups:
            part_ids = list(group.get("part_ids", []))
            for part_id in part_ids:
                peers = [value for value in part_ids if value != part_id]
                symmetry_by_part[str(part_id)] = {
                    "group_id": group.get("group_id", ""),
                    "group_kind": group.get("group_kind", ""),
                    "mirror_part_id": peers[0] if peers else str(part_id),
                }
        for placement in sorted(result.placements, key=lambda part: part.step or 0):
            selected = selected_by_id[placement.part_id]
            candidate = selected.candidate
            writer.writerow(
                {
                    "part_id": placement.part_id,
                    "step": placement.step,
                    "block_type": candidate.block_type,
                    "segment_id": candidate.dominant_segment,
                    "symmetry_group_id": symmetry_by_part.get(placement.part_id, {}).get("group_id", ""),
                    "mirror_part_id": symmetry_by_part.get(placement.part_id, {}).get("mirror_part_id", ""),
                    "symmetry_group_kind": symmetry_by_part.get(placement.part_id, {}).get("group_kind", ""),
                    "segment_order_index": placement.metadata.get("segment_order_index"),
                    "segment_step": placement.metadata.get("segment_step"),
                    "segment_phase": placement.metadata.get("segment_phase"),
                    "origin_x": candidate.origin[0],
                    "origin_y": candidate.origin[1],
                    "origin_z": candidate.origin[2],
                    "size_x": candidate.dimensions[0],
                    "size_y": candidate.dimensions[1],
                    "size_z": candidate.dimensions[2],
                    "target_overlap": candidate.target_overlap,
                    "newly_covered": len(selected.newly_covered),
                    "overhang_voxels": candidate.overhang,
                    "segment_purity": candidate.segment_purity,
                    "effective_score": selected.effective_score,
                    "component_seed": selected.component_seed,
                }
            )
    written.append(detailed_parts)

    geometry_validation = output_dir / "geometry_validation.json"
    _write_json(geometry_validation, result.geometry_validation)
    written.append(geometry_validation)

    build_sequence_validation = output_dir / "build_sequence_validation.json"
    _write_json(build_sequence_validation, result.build_sequence_validation)
    written.append(build_sequence_validation)

    build_steps_path = output_dir / "build_step_validation.csv"
    _write_rows(build_steps_path, result.build_sequence_validation["steps"])
    written.append(build_steps_path)


    symmetry_validation = output_dir / "symmetry_validation.json"
    _write_json(symmetry_validation, result.symmetry_validation)
    written.append(symmetry_validation)

    symmetry_pairs = output_dir / "symmetry_segment_pairs.csv"
    _write_rows(symmetry_pairs, result.symmetry_segment_pairs)
    written.append(symmetry_pairs)

    symmetry_groups = output_dir / "symmetry_groups.csv"
    _write_rows(symmetry_groups, result.symmetry_groups)
    written.append(symmetry_groups)

    segment_validation = output_dir / "segment_sequence_validation.json"
    _write_json(segment_validation, result.segment_sequence_validation)
    written.append(segment_validation)

    segment_steps = output_dir / "segment_build_sequence.csv"
    _write_rows(segment_steps, result.segment_sequence_validation.get("steps", []))
    written.append(segment_steps)

    alternatives = output_dir / "global_plan_alternatives.csv"
    _write_rows(alternatives, result.global_plan_alternatives)
    written.append(alternatives)

    allocations = output_dir / "segment_inventory_allocations.csv"
    _write_rows(allocations, result.segment_inventory_allocations)
    written.append(allocations)

    interfaces = output_dir / "interface_reservations.csv"
    _write_rows(interfaces, result.interface_reservations)
    written.append(interfaces)

    segment_coverage = output_dir / "segment_coverage.csv"
    _write_rows(segment_coverage, result.segment_coverage)
    written.append(segment_coverage)

    global_allocation = output_dir / "global_allocation_summary.json"
    _write_json(global_allocation, result.planner_summary.get("allocation", {}))
    written.append(global_allocation)

    planner_summary = output_dir / "structural_planner_summary.json"
    _write_json(planner_summary, result.planner_summary)
    written.append(planner_summary)

    segment_plan = output_dir / "segment_build_plan.json"
    _write_json(
        segment_plan,
        {
            "policy": "globally_allocate_symmetry_pairs_then_build_by_segment",
            "chosen_global_variant": result.planner_summary.get("chosen_global_variant"),
            "segment_order": result.planner_summary.get("segment_order", []),
            "segment_step_ranges": result.planner_summary.get("segment_step_ranges", {}),
            "join_steps": result.planner_summary.get("join_steps", []),
            "source_segment_coverage": result.planner_summary.get(
                "source_segment_coverage", {}
            ),
        },
    )
    written.append(segment_plan)

    instructions = output_dir / "obj_build_instructions.json"
    phases = []
    placements_by_segment: dict[str, list] = {}
    for placement in sorted(result.placements, key=lambda p: p.step or 0):
        placements_by_segment.setdefault(placement.segment_id or "unassigned", []).append(
            placement.to_dict()
        )
    for segment in result.planner_summary.get("segment_order", []):
        phases.append(
            {
                "segment_id": segment,
                "step_range": result.planner_summary.get("segment_step_ranges", {}).get(
                    segment, {}
                ),
                "placements": placements_by_segment.get(segment, []),
            }
        )
    _write_json(
        instructions,
        {
            "status": result.status,
            "source_obj": str(result.model.source_path),
            "axis_mapping": list(result.model.axis_mapping),
            "pitch": result.voxel_model.pitch,
            "coverage_fraction": result.geometry_validation["coverage_fraction"],
            "planning_policy": "globally_allocate_symmetry_pairs_then_build_by_segment",
            "catalog_source": result.catalog_summary.get("source_path"),
            "catalog_sha256": result.catalog_summary.get("source_sha256"),
            "catalog_format": "csv",
            "shadow_catalog_used": False,
            "segment_order": result.planner_summary.get("segment_order", []),
            "segment_phases": phases,
            "join_steps": result.planner_summary.get("join_steps", []),
            "symmetry": result.planner_summary.get("symmetry", {}),
            "symmetry_validation": result.symmetry_validation,
            "steps": [
                part.to_dict()
                for part in sorted(result.placements, key=lambda p: p.step or 0)
            ],
            "limitations": [
                "This checkpoint performs structural approximation only.",
                "Functional and connector blocks require confirmed segment semantics.",
                "Source object names are preserved but not semantically relabeled.",
                "Bilateral symmetry is detected from geometry rather than semantic labels.",
                "Functional and connector semantics remain a later integration stage.",
            ],
        },
    )
    written.append(instructions)

    preview_names: list[str] = []
    if include_html:
        preview = write_build_preview(output_dir / "build_preview.html", result)
        written.append(preview)
        preview_names.append(preview.name)
        player = write_segment_build_player(
            output_dir / "segment_build_player.html", result
        )
        written.append(player)
        preview_names.append(player.name)

    final_png = write_final_catalog_png(
        output_dir / "final_build_catalog_colored.png", result
    )
    written.append(final_png)
    preview_names.append(final_png.name)

    symmetry_top_png = write_symmetry_top_png(
        output_dir / "final_build_symmetry_top.png", result
    )
    written.append(symmetry_top_png)
    preview_names.append(symmetry_top_png.name)

    manifest = output_dir / "run_manifest.json"
    _write_json(
        manifest,
        {
            "status": result.status,
            "output_files": [path.name for path in written] + [manifest.name],
            "inventory_validation": result.planning_result.inventory_validation["status"],
            "geometry_validation": result.geometry_validation["status"],
            "build_sequence_validation": result.build_sequence_validation["status"],
            "segment_sequence_validation": result.segment_sequence_validation.get("status"),
            "symmetry_validation": result.symmetry_validation.get("status"),
            "planning_policy": "globally_allocate_symmetry_pairs_then_build_by_segment",
            "catalog_source": result.catalog_summary.get("source_path"),
            "catalog_sha256": result.catalog_summary.get("source_sha256"),
            "catalog_format": "csv",
            "shadow_catalog_used": False,
            "preview_files": preview_names,
        },
    )
    written.append(manifest)
    return written
