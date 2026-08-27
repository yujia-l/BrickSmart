"""OBJ-to-build experimental pipeline helpers.

This module connects OBJ loading, voxelization, simple planning, and reporting
for exploratory geometry workflows that sit beside the validated contract-based
BrickSmart runtime.
"""

from __future__ import annotations

from pathlib import Path

from bricksmart.catalog import (
    load_block_catalog,
    validate_inventory_against_catalog,
    validate_used_block_colors,
)
from bricksmart.geometry import load_segmented_obj, voxelize_segmented_model
from bricksmart.inventory import compile_effective_inventory, load_inventory_profile, load_teacher_budget
from bricksmart.planning.global_segment_allocator import coordinate_segment_plan
from bricksmart.planning.voxel_models import ObjBuildResult, StructuralPlannerConfig
from bricksmart.validation.build_sequence_validation import validate_build_sequence


def run_obj_build(
    *,
    obj_path: str | Path,
    inventory_path: str | Path,
    catalog_path: str | Path,
    teacher_budget_path: str | Path | None = None,
    up_axis: str = "auto",
    target_longest_cells: int = 18,
    minimum_component_voxels: int = 1,
    planner_config: StructuralPlannerConfig | None = None,
) -> tuple[ObjBuildResult, object]:
    """Run obj build.
    
    :param obj_path: OBJ model path used by the operation.
    :type obj_path: str | Path
    :param inventory_path: Path to the inventory file.
    :type inventory_path: str | Path
    :param catalog_path: Catalog file path used by the operation.
    :type catalog_path: str | Path
    :param teacher_budget_path: Path to the teacher budget file.
    :type teacher_budget_path: str | Path | None
    :param up_axis: The up axis value.
    :type up_axis: str
    :param target_longest_cells: The target longest cells value.
    :type target_longest_cells: int
    :param minimum_component_voxels: The minimum component voxels value.
    :type minimum_component_voxels: int
    :param planner_config: The planner config value.
    :type planner_config: StructuralPlannerConfig | None
    :returns: The result produced by the function.
    :rtype: tuple[ObjBuildResult, object]
    """
    profile = load_inventory_profile(inventory_path)
    catalog = load_block_catalog(catalog_path)
    validate_inventory_against_catalog(profile.quantities, catalog.block_ids)
    definitions = catalog.structural_definitions
    teacher_budget = load_teacher_budget(teacher_budget_path)
    effective = compile_effective_inventory(profile, teacher_budget)

    model = load_segmented_obj(obj_path, up_axis=up_axis)
    voxel_model = voxelize_segmented_model(
        model,
        target_longest_cells=target_longest_cells,
        minimum_component_voxels=minimum_component_voxels,
    )
    coordinated = coordinate_segment_plan(
        voxel_model=voxel_model,
        definitions=definitions,
        inventory=effective,
        config=planner_config or StructuralPlannerConfig(),
    )
    used_block_types = [item.candidate.block_type for item in coordinated.selected_blocks]
    validate_used_block_colors(used_block_types, catalog)

    build_sequence_validation = validate_build_sequence(
        selected_blocks=coordinated.selected_blocks,
        placements=coordinated.placements,
    )

    status = coordinated.planning_result.status
    if status == "PASS" and build_sequence_validation["status"] != "PASS":
        status = str(build_sequence_validation["status"])
        coordinated.planning_result.status = status

    result = ObjBuildResult(
        status=status,
        model=model,
        voxel_model=voxel_model,
        selected_blocks=coordinated.selected_blocks,
        placements=coordinated.placements,
        planning_result=coordinated.planning_result,
        geometry_validation=coordinated.geometry_validation,
        build_sequence_validation=build_sequence_validation,
        planner_summary=coordinated.planner_summary,
        segment_sequence_validation=coordinated.segment_sequence_validation,
        global_plan_alternatives=coordinated.alternatives,
        segment_inventory_allocations=coordinated.allocation.segment_rows,
        interface_reservations=coordinated.allocation.interface_rows,
        segment_coverage=coordinated.segment_coverage_rows,
        symmetry_validation=coordinated.symmetry_validation,
        symmetry_segment_pairs=coordinated.symmetry.segment_pair_rows,
        symmetry_groups=coordinated.allocation.symmetry_group_rows,
        catalog_summary=catalog.to_summary(),
        catalog_colors=catalog.colors,
    )
    return result, coordinated.allocation.ledger
