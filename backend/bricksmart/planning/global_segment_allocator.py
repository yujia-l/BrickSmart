"""Whole-model allocator for segment-level planning.

This module coordinates required segment assemblies and catalog block families
across the entire confirmed model.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Iterable

from bricksmart.catalog.structural import StructuralBlockDefinition
from bricksmart.geometry.models import GridCoord, VoxelModel
from bricksmart.inventory.ledger import InventoryLedger
from bricksmart.inventory.models import EffectiveInventory
from bricksmart.planning.build_order import contact_graph
from bricksmart.planning.models import PlanningResult
from bricksmart.planning.segment_build_order import SegmentBuildOrder, assign_segment_build_steps
from bricksmart.planning.symmetric_voxel_planner import SymmetryConstrainedVoxelPlanner
from bricksmart.planning.symmetry import SymmetrySpec, detect_bilateral_symmetry
from bricksmart.planning.voxel_models import SelectedVoxelBlock, StructuralPlannerConfig
from bricksmart.validation.geometry_validation import validate_voxel_build
from bricksmart.validation.inventory_validation import validate_final_inventory
from bricksmart.validation.segment_sequence_validation import validate_segment_sequence
from bricksmart.validation.symmetry_validation import validate_bilateral_symmetry


@dataclass(frozen=True)
class GlobalPlanAlternative:
    variant_name: str
    status: str
    selected_blocks: list[SelectedVoxelBlock]
    planning_result: PlanningResult
    geometry_validation: dict[str, object]
    symmetry_validation: dict[str, object]
    planner_summary: dict[str, object]
    symmetry_group_rows: list[dict[str, object]]
    segment_coverage: dict[str, dict[str, object]]
    strict_sequence_feasible: bool
    segment_order: list[str]
    total_overhang: int
    rank_key: tuple[object, ...]


@dataclass(frozen=True)
class AllocationCommit:
    ledger: InventoryLedger
    allocation_summary: dict[str, object]
    interface_rows: list[dict[str, object]]
    segment_rows: list[dict[str, object]]
    symmetry_group_rows: list[dict[str, object]]


@dataclass(frozen=True)
class CoordinatedSegmentPlan:
    selected_blocks: list[SelectedVoxelBlock]
    placements: list
    planning_result: PlanningResult
    geometry_validation: dict[str, object]
    symmetry_validation: dict[str, object]
    symmetry: SymmetrySpec
    planner_summary: dict[str, object]
    segment_sequence_validation: dict[str, object]
    segment_build_order: SegmentBuildOrder
    alternatives: list[dict[str, object]]
    segment_coverage_rows: list[dict[str, object]]
    allocation: AllocationCommit


def _variant_configs(base: StructuralPlannerConfig) -> list[StructuralPlannerConfig]:
    """Return the variant configs value.
    
    :param base: The base value.
    :type base: StructuralPlannerConfig
    :returns: The result produced by the function.
    :rtype: list[StructuralPlannerConfig]
    """
    return [
        replace(base, variant_name="symmetric_balanced"),
        replace(
            base,
            variant_name="symmetric_low_overhang",
            overhang_weight=max(base.overhang_weight, 2.0),
        ),
        replace(
            base,
            variant_name="symmetric_fewer_blocks",
            symmetry_block_count_penalty=max(base.symmetry_block_count_penalty, 1.0),
        ),
        replace(
            base,
            variant_name="symmetric_preserve_2x4",
            block_type_penalties={"standard_2x4x2": 8.0},
        ),
        replace(
            base,
            variant_name="symmetric_preserve_2x3",
            block_type_penalties={"standard_2x3x2": 5.0},
        ),
        replace(
            base,
            variant_name="symmetric_preserve_2x2",
            block_type_penalties={"standard_2x2x2": 5.0},
        ),
    ]


def _covered_cells(blocks: Iterable[SelectedVoxelBlock]) -> set[GridCoord]:
    """Return the covered cells value.
    
    :param blocks: Block records used by the operation.
    :type blocks: Iterable[SelectedVoxelBlock]
    :returns: The result produced by the function.
    :rtype: set[GridCoord]
    """
    covered: set[GridCoord] = set()
    for block in blocks:
        covered.update(block.candidate.target_cells)
    return covered


def _segment_coverage(
    voxel_model: VoxelModel,
    blocks: list[SelectedVoxelBlock],
) -> dict[str, dict[str, object]]:
    """Return segment coverage.
    
    :param voxel_model: The voxel model value.
    :type voxel_model: VoxelModel
    :param blocks: Block records used by the operation.
    :type blocks: list[SelectedVoxelBlock]
    :returns: The result produced by the function.
    :rtype: dict[str, dict[str, object]]
    """
    covered = _covered_cells(blocks)
    totals = Counter(voxel_model.segment_by_voxel.values())
    covered_counts = Counter(
        voxel_model.segment_by_voxel[cell]
        for cell in covered
        if cell in voxel_model.segment_by_voxel
    )
    assigned = Counter(block.candidate.dominant_segment for block in blocks)
    return {
        segment: {
            "segment_id": segment,
            "target_voxels": totals[segment],
            "covered_voxels": covered_counts[segment],
            "coverage_fraction": (
                covered_counts[segment] / totals[segment] if totals[segment] else 0.0
            ),
            "assigned_block_count": assigned[segment],
            "represented_by_dominant_block": assigned[segment] > 0,
        }
        for segment in sorted(totals)
    }


def _alternative_rank(
    *,
    status: str,
    sequence_feasible: bool,
    symmetry_validation: dict[str, object],
    coverage: dict[str, dict[str, object]],
    geometry_validation: dict[str, object],
    blocks: list[SelectedVoxelBlock],
    total_overhang: int,
) -> tuple[object, ...]:
    """Return the alternative rank value.
    
    :param status: The status value.
    :type status: str
    :param sequence_feasible: The sequence feasible value.
    :type sequence_feasible: bool
    :param symmetry_validation: The symmetry validation value.
    :type symmetry_validation: dict[str, object]
    :param coverage: The coverage value.
    :type coverage: dict[str, dict[str, object]]
    :param geometry_validation: The geometry validation value.
    :type geometry_validation: dict[str, object]
    :param blocks: Block records used by the operation.
    :type blocks: list[SelectedVoxelBlock]
    :param total_overhang: The total overhang value.
    :type total_overhang: int
    :returns: The result produced by the function.
    :rtype: tuple[object, ...]
    """
    fractions = [float(data["coverage_fraction"]) for data in coverage.values()]
    represented = sum(bool(data["represented_by_dominant_block"]) for data in coverage.values())
    return (
        status == "PASS",
        symmetry_validation.get("status") == "PASS",
        sequence_feasible,
        represented,
        min(fractions) if fractions else 0.0,
        float(geometry_validation.get("coverage_fraction", 0.0)),
        float(symmetry_validation.get("exact_mirrored_block_fraction", 0.0)),
        -total_overhang,
        -len(blocks),
    )


def generate_global_alternatives(
    *,
    voxel_model: VoxelModel,
    definitions: tuple[StructuralBlockDefinition, ...],
    inventory: EffectiveInventory,
    config: StructuralPlannerConfig,
    symmetry: SymmetrySpec,
) -> list[GlobalPlanAlternative]:
    """Generate global alternatives.
    
    :param voxel_model: The voxel model value.
    :type voxel_model: VoxelModel
    :param definitions: The definitions value.
    :type definitions: tuple[StructuralBlockDefinition, ...]
    :param inventory: Inventory data used by the operation.
    :type inventory: EffectiveInventory
    :param config: Configuration values for the operation.
    :type config: StructuralPlannerConfig
    :param symmetry: The symmetry value.
    :type symmetry: SymmetrySpec
    :returns: The generated result.
    :rtype: list[GlobalPlanAlternative]
    """
    alternatives: list[GlobalPlanAlternative] = []
    for variant in _variant_configs(config):
        trial_ledger = InventoryLedger(inventory)
        planner = SymmetryConstrainedVoxelPlanner(
            ledger=trial_ledger,
            definitions=definitions,
            symmetry=symmetry,
            config=variant,
        )
        result = planner.plan(voxel_model)
        sequence_feasible = True
        segment_order: list[str] = []
        try:
            segment_build = assign_segment_build_steps(result.selected_blocks)
            validation = validate_segment_sequence(
                selected_blocks=result.selected_blocks,
                placements=segment_build.placements,
            )
            sequence_feasible = validation["status"] == "PASS"
            segment_order = segment_build.segment_order
        except ValueError:
            sequence_feasible = False
        coverage = _segment_coverage(voxel_model, result.selected_blocks)
        total_overhang = sum(block.candidate.overhang for block in result.selected_blocks)
        alternatives.append(
            GlobalPlanAlternative(
                variant_name=variant.variant_name,
                status=result.planning_result.status,
                selected_blocks=result.selected_blocks,
                planning_result=result.planning_result,
                geometry_validation=result.geometry_validation,
                symmetry_validation=result.symmetry_validation,
                planner_summary=result.planner_summary,
                symmetry_group_rows=result.symmetry_group_rows,
                segment_coverage=coverage,
                strict_sequence_feasible=sequence_feasible,
                segment_order=segment_order,
                total_overhang=total_overhang,
                rank_key=_alternative_rank(
                    status=result.planning_result.status,
                    sequence_feasible=sequence_feasible,
                    symmetry_validation=result.symmetry_validation,
                    coverage=coverage,
                    geometry_validation=result.geometry_validation,
                    blocks=result.selected_blocks,
                    total_overhang=total_overhang,
                ),
            )
        )
    return sorted(alternatives, key=lambda alternative: alternative.rank_key, reverse=True)


def _allocation_groups(
    blocks: list[SelectedVoxelBlock],
) -> tuple[
    dict[tuple[str, tuple[str, ...]], Counter[str]],
    dict[str, Counter[str]],
    set[int],
]:
    """Return the allocation groups value.
    
    :param blocks: Block records used by the operation.
    :type blocks: list[SelectedVoxelBlock]
    :returns: The result produced by the function.
    :rtype: tuple[dict[tuple[str, tuple[str, ...]], Counter[str]], dict[str, Counter[str]], set[int]]
    """
    graph = contact_graph(blocks)
    interface_groups: dict[tuple[str, tuple[str, ...]], Counter[str]] = defaultdict(Counter)
    internal_groups: dict[str, Counter[str]] = defaultdict(Counter)
    interface_indices: set[int] = set()

    for index, block in enumerate(blocks):
        segment = block.candidate.dominant_segment
        neighbor_segments = tuple(
            sorted(
                {
                    blocks[neighbor].candidate.dominant_segment
                    for neighbor in graph[index]
                    if blocks[neighbor].candidate.dominant_segment != segment
                }
            )
        )
        if neighbor_segments:
            interface_indices.add(index)
            interface_groups[(segment, neighbor_segments)][block.candidate.block_type] += 1
        else:
            internal_groups[segment][block.candidate.block_type] += 1
    return interface_groups, internal_groups, interface_indices


def commit_symmetric_allocation(
    *,
    blocks: list[SelectedVoxelBlock],
    symmetry_group_rows: list[dict[str, object]],
    inventory: EffectiveInventory,
) -> AllocationCommit:
    """Return the commit symmetric allocation value.
    
    :param blocks: Block records used by the operation.
    :type blocks: list[SelectedVoxelBlock]
    :param symmetry_group_rows: The symmetry group rows value.
    :type symmetry_group_rows: list[dict[str, object]]
    :param inventory: Inventory data used by the operation.
    :type inventory: EffectiveInventory
    :returns: The result produced by the function.
    :rtype: AllocationCommit
    """
    ledger = InventoryLedger(inventory)
    committed_group_rows: list[dict[str, object]] = []
    for source_row in symmetry_group_rows:
        row = deepcopy(source_row)
        requirements = {
            str(block_type): int(count)
            for block_type, count in dict(row["requirements"]).items()
        }
        reservation_id = ledger.reserve(
            requirements,
            reason=f"atomic_mirrored_placement:{row['group_id']}",
        )
        ledger.commit(reservation_id)
        row["reservation_id"] = reservation_id
        row["status"] = "COMMITTED"
        committed_group_rows.append(row)

    interface_groups, internal_groups, interface_indices = _allocation_groups(blocks)
    interface_rows: list[dict[str, object]] = []
    segment_rows: list[dict[str, object]] = []

    for (segment, neighbors), requirements in sorted(interface_groups.items()):
        for block_type, count in sorted(requirements.items()):
            interface_rows.append(
                {
                    "owner_segment": segment,
                    "neighbor_segments": "+".join(neighbors),
                    "block_type": block_type,
                    "allocated_count": count,
                    "allocation_kind": "interface",
                    "status": "COMMITTED_IN_SYMMETRY_GROUP",
                }
            )
    for segment, requirements in sorted(internal_groups.items()):
        for block_type, count in sorted(requirements.items()):
            segment_rows.append(
                {
                    "segment_id": segment,
                    "allocation_kind": "internal",
                    "block_type": block_type,
                    "allocated_count": count,
                    "status": "COMMITTED_IN_SYMMETRY_GROUP",
                }
            )

    assigned_totals: dict[str, Counter[str]] = defaultdict(Counter)
    for block in blocks:
        assigned_totals[block.candidate.dominant_segment][block.candidate.block_type] += 1
    for segment, counts in sorted(assigned_totals.items()):
        for block_type, count in sorted(counts.items()):
            segment_rows.append(
                {
                    "segment_id": segment,
                    "allocation_kind": "total",
                    "block_type": block_type,
                    "allocated_count": count,
                    "status": "COMMITTED",
                }
            )

    allocation_summary = {
        "status": "PASS",
        "policy": "globally_allocate_symmetry_pairs_then_build_by_segment",
        "atomic_symmetry_group_count": len(committed_group_rows),
        "interface_block_count": len(interface_indices),
        "internal_block_count": len(blocks) - len(interface_indices),
        "segment_count": len(assigned_totals),
        "committed_counts": ledger.committed_counts,
        "remaining_inventory": {
            block_type: values["remaining"]
            for block_type, values in ledger.snapshot().items()
        },
        "reservation_order": [
            f"atomic_mirrored_placement:{row['group_id']}"
            for row in committed_group_rows
        ],
    }
    return AllocationCommit(
        ledger=ledger,
        allocation_summary=allocation_summary,
        interface_rows=interface_rows,
        segment_rows=segment_rows,
        symmetry_group_rows=committed_group_rows,
    )


def coordinate_segment_plan(
    *,
    voxel_model: VoxelModel,
    definitions: tuple[StructuralBlockDefinition, ...],
    inventory: EffectiveInventory,
    config: StructuralPlannerConfig,
) -> CoordinatedSegmentPlan:
    """Return the coordinate segment plan value.
    
    :param voxel_model: The voxel model value.
    :type voxel_model: VoxelModel
    :param definitions: The definitions value.
    :type definitions: tuple[StructuralBlockDefinition, ...]
    :param inventory: Inventory data used by the operation.
    :type inventory: EffectiveInventory
    :param config: Configuration values for the operation.
    :type config: StructuralPlannerConfig
    :returns: The result produced by the function.
    :rtype: CoordinatedSegmentPlan
    """
    if config.symmetry_mode not in {"required", "auto"}:
        raise ValueError(
            "Symmetry mode must be 'required' or 'auto'; asymmetric fallback is diagnostic-only"
        )
    symmetry = detect_bilateral_symmetry(voxel_model)
    if (
        config.symmetry_mode == "auto"
        and symmetry.target_symmetry_fraction < config.minimum_target_symmetry
    ):
        raise ValueError(
            "No sufficiently bilateral symmetry was detected for the symmetry planner"
        )
    alternatives = generate_global_alternatives(
        voxel_model=voxel_model,
        definitions=definitions,
        inventory=inventory,
        config=config,
        symmetry=symmetry,
    )
    chosen: GlobalPlanAlternative | None = None
    allocation: AllocationCommit | None = None
    build_order: SegmentBuildOrder | None = None

    for alternative in alternatives:
        if alternative.status != "PASS":
            continue
        if alternative.symmetry_validation.get("status") != "PASS":
            continue
        if not alternative.strict_sequence_feasible:
            continue
        try:
            trial_allocation = commit_symmetric_allocation(
                blocks=alternative.selected_blocks,
                symmetry_group_rows=alternative.symmetry_group_rows,
                inventory=inventory,
            )
            trial_order = assign_segment_build_steps(alternative.selected_blocks)
        except Exception:
            continue
        chosen = alternative
        allocation = trial_allocation
        build_order = trial_order
        break

    if chosen is None or allocation is None or build_order is None:
        if not alternatives:
            raise ValueError("No global symmetry-aware planning alternatives were generated")
        chosen = alternatives[0]
        allocation = commit_symmetric_allocation(
            blocks=chosen.selected_blocks,
            symmetry_group_rows=chosen.symmetry_group_rows,
            inventory=inventory,
        )
        try:
            build_order = assign_segment_build_steps(chosen.selected_blocks)
        except ValueError:
            build_order = SegmentBuildOrder([], [], {}, [])

    inventory_validation = validate_final_inventory(
        final_parts=build_order.placements,
        inventory=allocation.ledger.inventory,
        ledger_committed=allocation.ledger.committed_counts,
    )
    geometry_validation = validate_voxel_build(
        voxel_model=voxel_model,
        selected_blocks=chosen.selected_blocks,
        coverage_target=config.coverage_target,
    )
    segment_validation = validate_segment_sequence(
        selected_blocks=chosen.selected_blocks,
        placements=build_order.placements,
    )
    symmetry_validation = validate_bilateral_symmetry(
        voxel_model=voxel_model,
        selected_blocks=chosen.selected_blocks,
        symmetry=symmetry,
        minimum_target_symmetry=config.minimum_target_symmetry,
        minimum_build_volume_symmetry=config.minimum_build_volume_symmetry,
        minimum_exact_block_symmetry=config.minimum_exact_block_symmetry,
    )

    status = "PASS"
    for validation in (
        inventory_validation,
        geometry_validation,
        segment_validation,
        symmetry_validation,
    ):
        if validation["status"] != "PASS":
            status = str(validation["status"])
            break

    planning_result = deepcopy(chosen.planning_result)
    planning_result.status = status
    planning_result.final_parts = build_order.placements
    planning_result.inventory_validation = inventory_validation

    alternative_rows: list[dict[str, object]] = []
    for rank, alternative in enumerate(alternatives, start=1):
        fractions = [
            float(data["coverage_fraction"])
            for data in alternative.segment_coverage.values()
        ]
        alternative_rows.append(
            {
                "rank": rank,
                "variant_name": alternative.variant_name,
                "selected": alternative is chosen,
                "planner_status": alternative.status,
                "symmetry_status": alternative.symmetry_validation.get("status"),
                "strict_sequence_feasible": alternative.strict_sequence_feasible,
                "block_count": len(alternative.selected_blocks),
                "coverage_fraction": alternative.geometry_validation.get(
                    "coverage_fraction", 0.0
                ),
                "build_volume_symmetry_fraction": alternative.symmetry_validation.get(
                    "build_volume_symmetry_fraction", 0.0
                ),
                "exact_mirrored_block_fraction": alternative.symmetry_validation.get(
                    "exact_mirrored_block_fraction", 0.0
                ),
                "minimum_segment_coverage_fraction": min(fractions) if fractions else 0.0,
                "represented_segment_count": sum(
                    bool(data["represented_by_dominant_block"])
                    for data in alternative.segment_coverage.values()
                ),
                "total_overhang": alternative.total_overhang,
                "segment_order": "+".join(alternative.segment_order),
                "solver_status": alternative.planner_summary.get("solver", {}).get(
                    "message"
                ),
            }
        )

    planner_summary = deepcopy(chosen.planner_summary)
    planner_summary.update(
        {
            "coordination_policy": "globally_allocate_symmetry_pairs_then_build_by_segment",
            "chosen_global_variant": chosen.variant_name,
            "global_alternative_count": len(alternatives),
            "backtracking_attempts_before_success": next(
                row["rank"] for row in alternative_rows if row["selected"]
            ),
            "segment_order": build_order.segment_order,
            "segment_step_ranges": {
                segment: {"start": values[0], "end": values[1]}
                for segment, values in build_order.step_ranges.items()
            },
            "join_steps": build_order.join_steps,
            "allocation": allocation.allocation_summary,
            "source_segment_coverage": chosen.segment_coverage,
            "symmetry": {
                "axis": symmetry.axis_name,
                "axis_index": symmetry.axis,
                "plane_sum": symmetry.plane_sum,
                "plane_coordinate": symmetry.plane_coordinate,
                "target_symmetry_fraction": symmetry.target_symmetry_fraction,
                "segment_pairs": symmetry.segment_pairs,
            },
        }
    )

    return CoordinatedSegmentPlan(
        selected_blocks=chosen.selected_blocks,
        placements=build_order.placements,
        planning_result=planning_result,
        geometry_validation=geometry_validation,
        symmetry_validation=symmetry_validation,
        symmetry=symmetry,
        planner_summary=planner_summary,
        segment_sequence_validation=segment_validation,
        segment_build_order=build_order,
        alternatives=alternative_rows,
        segment_coverage_rows=list(chosen.segment_coverage.values()),
        allocation=allocation,
    )
