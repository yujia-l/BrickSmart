from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from bricksmart.catalog.structural import StructuralBlockDefinition
from bricksmart.geometry.models import GridCoord, VoxelModel
from bricksmart.inventory.ledger import InventoryLedger
from bricksmart.planning.models import PlanningResult, SelectionDecision
from bricksmart.planning.structural_voxel_planner import generate_structural_candidates
from bricksmart.planning.symmetry import SymmetrySpec, mirror_candidate_key
from bricksmart.planning.voxel_models import (
    SelectedVoxelBlock,
    StructuralPlannerConfig,
    VoxelCandidate,
)
from bricksmart.validation.geometry_validation import validate_voxel_build
from bricksmart.validation.inventory_validation import validate_final_inventory
from bricksmart.validation.symmetry_validation import validate_bilateral_symmetry


@dataclass(frozen=True)
class SymmetricCandidateGroup:
    group_id: str
    candidates: tuple[VoxelCandidate, ...]
    occupied_cells: frozenset[GridCoord]
    target_cells: frozenset[GridCoord]
    requirements: dict[str, int]
    overhang: int

    @property
    def block_count(self) -> int:
        return len(self.candidates)


@dataclass(frozen=True)
class SymmetricPlanResult:
    selected_blocks: list[SelectedVoxelBlock]
    placements: list
    planning_result: PlanningResult
    geometry_validation: dict[str, object]
    symmetry_validation: dict[str, object]
    planner_summary: dict[str, object]
    symmetry_group_rows: list[dict[str, object]]


def generate_symmetric_candidate_groups(
    *,
    voxel_model: VoxelModel,
    definitions: tuple[StructuralBlockDefinition, ...],
    symmetry: SymmetrySpec,
    minimum_fill_ratio: float,
) -> tuple[list[SymmetricCandidateGroup], int]:
    candidates = generate_structural_candidates(
        voxel_model,
        definitions,
        minimum_fill_ratio=minimum_fill_ratio,
    )
    lookup = {
        (candidate.block_type, candidate.origin, candidate.dimensions): candidate
        for candidate in candidates
    }
    groups: list[SymmetricCandidateGroup] = []
    emitted: set[tuple[tuple[str, GridCoord, GridCoord], ...]] = set()

    for candidate in candidates:
        candidate_key = (
            candidate.block_type,
            candidate.origin,
            candidate.dimensions,
        )
        mirror_key = mirror_candidate_key(candidate, symmetry)
        mirror = lookup.get(mirror_key)
        if mirror is None:
            continue

        if candidate_key == mirror_key:
            if symmetry.segment_pairs.get(candidate.dominant_segment) != candidate.dominant_segment:
                continue
            members = (candidate,)
        else:
            if candidate.cells & mirror.cells:
                continue
            if symmetry.segment_pairs.get(candidate.dominant_segment) != mirror.dominant_segment:
                continue
            if symmetry.segment_pairs.get(mirror.dominant_segment) != candidate.dominant_segment:
                continue
            members = tuple(
                sorted(
                    (candidate, mirror),
                    key=lambda value: (value.origin, value.block_type),
                )
            )

        identity = tuple(
            (member.block_type, member.origin, member.dimensions) for member in members
        )
        if identity in emitted:
            continue
        emitted.add(identity)
        occupied = frozenset().union(*(member.cells for member in members))
        target = frozenset().union(*(member.target_cells for member in members))
        requirements = dict(Counter(member.block_type for member in members))
        groups.append(
            SymmetricCandidateGroup(
                group_id=f"symmetry_group_{len(groups) + 1:04d}",
                candidates=members,
                occupied_cells=occupied,
                target_cells=target,
                requirements=requirements,
                overhang=len(occupied - target),
            )
        )
    return groups, len(candidates)


def _solve_groups(
    *,
    voxel_model: VoxelModel,
    groups: list[SymmetricCandidateGroup],
    ledger: InventoryLedger,
    config: StructuralPlannerConfig,
) -> tuple[list[SymmetricCandidateGroup], dict[str, object]]:
    target_cells = sorted(voxel_model.target_voxels)
    group_count = len(groups)
    target_count = len(target_cells)
    target_index = {cell: index for index, cell in enumerate(target_cells)}
    variable_count = group_count + target_count

    objective = np.zeros(variable_count, dtype=float)
    for index, group in enumerate(groups):
        block_penalty = sum(
            config.block_type_penalties.get(candidate.block_type, 0.0)
            for candidate in group.candidates
        )
        objective[index] = (
            group.overhang * config.overhang_weight
            + group.block_count * config.symmetry_block_count_penalty
            + block_penalty
        )
    objective[group_count:] = -config.symmetry_coverage_reward

    row_indices: list[int] = []
    column_indices: list[int] = []
    values: list[float] = []
    lower_bounds: list[float] = []
    upper_bounds: list[float] = []

    def add_constraint(coefficients: dict[int, float], lower: float, upper: float) -> None:
        row = len(lower_bounds)
        for column, value in coefficients.items():
            row_indices.append(row)
            column_indices.append(column)
            values.append(float(value))
        lower_bounds.append(lower)
        upper_bounds.append(upper)

    occupancy_to_groups: dict[GridCoord, list[int]] = defaultdict(list)
    for group_index, group in enumerate(groups):
        for cell in group.occupied_cells:
            occupancy_to_groups[cell].append(group_index)
    for group_indices in occupancy_to_groups.values():
        add_constraint(
            {group_index: 1.0 for group_index in group_indices},
            -np.inf,
            1.0,
        )

    structural_types = sorted(
        {
            candidate.block_type
            for group in groups
            for candidate in group.candidates
        }
    )
    for block_type in structural_types:
        limit = ledger.capacity(block_type)
        if limit is None:
            continue
        coefficients = {
            group_index: float(group.requirements.get(block_type, 0))
            for group_index, group in enumerate(groups)
            if group.requirements.get(block_type, 0)
        }
        add_constraint(coefficients, -np.inf, float(limit))

    groups_by_target: dict[GridCoord, list[int]] = defaultdict(list)
    for group_index, group in enumerate(groups):
        for cell in group.target_cells:
            groups_by_target[cell].append(group_index)
    for cell, voxel_index in target_index.items():
        coefficients = {group_count + voxel_index: 1.0}
        for group_index in groups_by_target.get(cell, []):
            coefficients[group_index] = coefficients.get(group_index, 0.0) - 1.0
        add_constraint(coefficients, -np.inf, 0.0)

    # Every source segment must retain at least one dominant block assignment.
    segments = sorted(set(voxel_model.segment_by_voxel.values()))
    for segment in segments:
        coefficients: dict[int, float] = {}
        for group_index, group in enumerate(groups):
            count = sum(
                candidate.dominant_segment == segment
                for candidate in group.candidates
            )
            if count:
                coefficients[group_index] = float(count)
        add_constraint(coefficients, 1.0, np.inf)

    # The selected plan must meet the requested coarse target coverage, not merely
    # maximize toward it. This makes a short solver result fail explicitly.
    required_coverage = math.ceil(config.coverage_target * target_count)
    add_constraint(
        {
            group_count + voxel_index: 1.0
            for voxel_index in range(target_count)
        },
        float(required_coverage),
        np.inf,
    )

    matrix = coo_matrix(
        (values, (row_indices, column_indices)),
        shape=(len(lower_bounds), variable_count),
    ).tocsr()
    result = milp(
        objective,
        integrality=np.ones(variable_count, dtype=int),
        bounds=Bounds(
            np.zeros(variable_count, dtype=float),
            np.ones(variable_count, dtype=float),
        ),
        constraints=LinearConstraint(
            matrix,
            np.asarray(lower_bounds, dtype=float),
            np.asarray(upper_bounds, dtype=float),
        ),
        options={
            "time_limit": float(config.symmetry_solver_time_limit_seconds),
            "mip_rel_gap": float(config.symmetry_solver_relative_gap),
        },
    )
    selected = [
        group
        for index, group in enumerate(groups)
        if result.x is not None and result.x[index] >= 0.5
    ]
    return selected, {
        "success": bool(result.success),
        "status_code": int(result.status),
        "message": str(result.message),
        "objective_value": float(result.fun) if result.fun is not None else None,
        "candidate_group_count": group_count,
        "constraint_count": len(lower_bounds),
        "required_covered_voxels": required_coverage,
    }


class SymmetryConstrainedVoxelPlanner:
    def __init__(
        self,
        *,
        ledger: InventoryLedger,
        definitions: tuple[StructuralBlockDefinition, ...],
        symmetry: SymmetrySpec,
        config: StructuralPlannerConfig,
    ):
        self.ledger = ledger
        self.definitions = definitions
        self.symmetry = symmetry
        self.config = config

    def plan(self, voxel_model: VoxelModel) -> SymmetricPlanResult:
        groups, raw_candidate_count = generate_symmetric_candidate_groups(
            voxel_model=voxel_model,
            definitions=self.definitions,
            symmetry=self.symmetry,
            minimum_fill_ratio=self.config.minimum_candidate_fill_ratio,
        )
        selected_groups, solver_summary = _solve_groups(
            voxel_model=voxel_model,
            groups=groups,
            ledger=self.ledger,
            config=self.config,
        )

        selected_blocks: list[SelectedVoxelBlock] = []
        decisions: list[SelectionDecision] = []
        covered: set[GridCoord] = set()
        group_rows: list[dict[str, object]] = []

        for group in selected_groups:
            reservation_id = self.ledger.reserve(
                group.requirements,
                reason=f"atomic_mirrored_placement:{group.group_id}",
            )
            self.ledger.commit(reservation_id)
            member_part_ids: list[str] = []
            for candidate in group.candidates:
                newly_covered = frozenset(candidate.target_cells - covered)
                selected = SelectedVoxelBlock(
                    candidate=candidate,
                    newly_covered=newly_covered,
                    effective_score=float(len(newly_covered)),
                    selection_index=len(selected_blocks) + 1,
                    component_seed=False,
                )
                selected_blocks.append(selected)
                covered.update(candidate.target_cells)
                member_part_ids.append(f"part_{selected.selection_index:03d}")
            decisions.append(
                SelectionDecision(
                    group_id=group.group_id,
                    selected_candidate_id="+".join(member_part_ids),
                    status="SELECTED",
                    base_score=float(len(group.target_cells)),
                    scarcity_penalty=0.0,
                    effective_score=float(len(group.target_cells) - group.overhang),
                    requirements=group.requirements,
                    shortages={},
                    selection_kind=(
                        "centerline_symmetric_block"
                        if group.block_count == 1
                        else "atomic_mirrored_pair"
                    ),
                )
            )
            group_rows.append(
                {
                    "group_id": group.group_id,
                    "group_kind": (
                        "centerline" if group.block_count == 1 else "mirrored_pair"
                    ),
                    "part_ids": member_part_ids,
                    "block_count": group.block_count,
                    "block_types": [candidate.block_type for candidate in group.candidates],
                    "segment_ids": [
                        candidate.dominant_segment for candidate in group.candidates
                    ],
                    "origins": [list(candidate.origin) for candidate in group.candidates],
                    "dimensions": [
                        list(candidate.dimensions) for candidate in group.candidates
                    ],
                    "requirements": group.requirements,
                    "target_overlap": len(group.target_cells),
                    "overhang_voxels": group.overhang,
                    "reservation_id": reservation_id,
                    "status": "COMMITTED",
                }
            )

        # Segment-aware ordering is applied by the global coordinator. The temporary
        # placements here are only for inventory recount compatibility.
        placements = [
            block.to_placement(step=index)
            for index, block in enumerate(selected_blocks, start=1)
        ]
        inventory_validation = validate_final_inventory(
            final_parts=placements,
            inventory=self.ledger.inventory,
            ledger_committed=self.ledger.committed_counts,
        )
        geometry_validation = validate_voxel_build(
            voxel_model=voxel_model,
            selected_blocks=selected_blocks,
            coverage_target=self.config.coverage_target,
        )
        symmetry_validation = validate_bilateral_symmetry(
            voxel_model=voxel_model,
            selected_blocks=selected_blocks,
            symmetry=self.symmetry,
            minimum_target_symmetry=self.config.minimum_target_symmetry,
            minimum_build_volume_symmetry=self.config.minimum_build_volume_symmetry,
            minimum_exact_block_symmetry=self.config.minimum_exact_block_symmetry,
        )

        status = "PASS"
        if not solver_summary["success"]:
            status = "FAIL_SYMMETRY_SOLVER"
        for validation in (
            inventory_validation,
            geometry_validation,
            symmetry_validation,
        ):
            if validation["status"] != "PASS":
                status = str(validation["status"])
                break

        planning_result = PlanningResult(
            status=status,
            final_parts=placements,
            decisions=decisions,
            unmet_requirements=[],
            inventory_validation=inventory_validation,
        )
        planner_summary = {
            "planner_kind": "exact_bilateral_symmetry_milp",
            "raw_candidate_count": raw_candidate_count,
            "symmetric_candidate_group_count": len(groups),
            "selected_symmetry_group_count": len(selected_groups),
            "selected_block_count": len(selected_blocks),
            "selected_by_block_type": dict(
                sorted(
                    Counter(
                        block.candidate.block_type for block in selected_blocks
                    ).items()
                )
            ),
            "covered_target_voxels": len(covered),
            "target_voxels": len(voxel_model.target_voxels),
            "coverage_fraction": (
                len(covered) / len(voxel_model.target_voxels)
                if voxel_model.target_voxels
                else 1.0
            ),
            "symmetry": {
                "axis": self.symmetry.axis_name,
                "axis_index": self.symmetry.axis,
                "plane_sum": self.symmetry.plane_sum,
                "plane_coordinate": self.symmetry.plane_coordinate,
                "target_symmetry_fraction": self.symmetry.target_symmetry_fraction,
                "segment_pairs": self.symmetry.segment_pairs,
            },
            "solver": solver_summary,
            "configuration": dict(self.config.__dict__),
        }
        return SymmetricPlanResult(
            selected_blocks=selected_blocks,
            placements=placements,
            planning_result=planning_result,
            geometry_validation=geometry_validation,
            symmetry_validation=symmetry_validation,
            planner_summary=planner_summary,
            symmetry_group_rows=group_rows,
        )
