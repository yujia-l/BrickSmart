from __future__ import annotations

import math
from collections import Counter

from bricksmart.catalog.structural import StructuralBlockDefinition
from bricksmart.geometry.models import GridCoord, VoxelModel
from bricksmart.inventory.ledger import InventoryLedger
from bricksmart.inventory.policies import scarcity_penalty
from bricksmart.planning.build_order import assign_build_steps, blocks_face_touch
from bricksmart.planning.models import PlanningResult, SelectionDecision
from bricksmart.planning.voxel_models import (
    SelectedVoxelBlock,
    StructuralPlannerConfig,
    VoxelCandidate,
)
from bricksmart.validation.geometry_validation import validate_voxel_build
from bricksmart.validation.inventory_validation import validate_final_inventory


def _cuboid_cells(origin: GridCoord, dimensions: GridCoord) -> frozenset[GridCoord]:
    return frozenset(
        (x, y, z)
        for x in range(origin[0], origin[0] + dimensions[0])
        for y in range(origin[1], origin[1] + dimensions[1])
        for z in range(origin[2], origin[2] + dimensions[2])
    )


def generate_structural_candidates(
    voxel_model: VoxelModel,
    definitions: tuple[StructuralBlockDefinition, ...],
    *,
    minimum_fill_ratio: float,
) -> list[VoxelCandidate]:
    if not 0 < minimum_fill_ratio <= 1:
        raise ValueError("minimum_fill_ratio must be in (0, 1]")
    target = set(voxel_model.target_voxels)
    lower = voxel_model.grid_bounds_min
    upper = voxel_model.grid_bounds_max
    candidates: list[VoxelCandidate] = []

    for definition in definitions:
        for dimensions in definition.allowed_dimensions:
            volume = math.prod(dimensions)
            minimum_overlap = max(2, math.ceil(volume * minimum_fill_ratio))
            for x in range(lower[0] - dimensions[0] + 1, upper[0] + 1):
                for y in range(lower[1] - dimensions[1] + 1, upper[1] + 1):
                    for z in range(lower[2] - dimensions[2] + 1, upper[2] + 1):
                        origin = (x, y, z)
                        cells = _cuboid_cells(origin, dimensions)
                        target_cells = cells & target
                        if len(target_cells) < minimum_overlap:
                            continue
                        segment_counts = Counter(
                            voxel_model.segment_by_voxel[cell] for cell in target_cells
                        )
                        dominant_segment, dominant_count = segment_counts.most_common(1)[0]
                        candidates.append(
                            VoxelCandidate(
                                block_type=definition.block_type,
                                origin=origin,
                                dimensions=dimensions,
                                cells=cells,
                                target_cells=frozenset(target_cells),
                                dominant_segment=dominant_segment,
                                segment_purity=dominant_count / len(target_cells),
                                packing_priority=definition.packing_priority,
                            )
                        )
    return candidates


class InventoryConstrainedVoxelPlanner:
    def __init__(
        self,
        ledger: InventoryLedger,
        definitions: tuple[StructuralBlockDefinition, ...],
        config: StructuralPlannerConfig | None = None,
    ):
        self.ledger = ledger
        self.definitions = definitions
        self.config = config or StructuralPlannerConfig()

    def plan(self, voxel_model: VoxelModel) -> tuple[
        list[SelectedVoxelBlock], list, PlanningResult, dict[str, object], dict[str, object]
    ]:
        candidates = generate_structural_candidates(
            voxel_model,
            self.definitions,
            minimum_fill_ratio=self.config.minimum_candidate_fill_ratio,
        )
        target = set(voxel_model.target_voxels)
        covered: set[GridCoord] = set()
        occupied: set[GridCoord] = set()
        selected: list[SelectedVoxelBlock] = []
        decisions: list[SelectionDecision] = []
        stop_reason = "coverage_target_reached"

        if self.config.require_segment_representation:
            segment_sizes = Counter(voxel_model.segment_by_voxel.values())
            candidates_by_segment = {
                segment: [
                    candidate
                    for candidate in candidates
                    if candidate.dominant_segment == segment
                ]
                for segment in segment_sizes
            }
            seed_order = sorted(
                segment_sizes,
                key=lambda segment: (
                    len(candidates_by_segment[segment]),
                    segment_sizes[segment],
                    segment,
                ),
            )
            for segment in seed_order:
                ranked_seeds: list[tuple[float, VoxelCandidate]] = []
                for candidate in candidates_by_segment[segment]:
                    if candidate.cells & occupied:
                        continue
                    if not self.ledger.can_reserve({candidate.block_type: 1}):
                        continue
                    segment_overlap = sum(
                        1
                        for cell in candidate.target_cells
                        if voxel_model.segment_by_voxel[cell] == segment
                    )
                    seed_score = (
                        segment_overlap * 15.0
                        + candidate.target_overlap * 2.0
                        + candidate.segment_purity * 8.0
                        - candidate.overhang * 1.5
                        - candidate.volume * 0.1
                        + candidate.packing_priority / 10000.0
                        - self.config.block_type_penalties.get(candidate.block_type, 0.0)
                    )
                    ranked_seeds.append((seed_score, candidate))
                if not ranked_seeds:
                    stop_reason = f"missing_segment_seed:{segment}"
                    break
                seed_score, candidate = max(
                    ranked_seeds,
                    key=lambda row: (
                        row[0],
                        row[1].segment_purity,
                        row[1].target_overlap,
                        -row[1].overhang,
                        row[1].packing_priority,
                    ),
                )
                newly_covered = frozenset(candidate.target_cells - covered)
                reservation_id = self.ledger.reserve(
                    {candidate.block_type: 1},
                    reason=f"segment_seed:{segment}:{candidate.origin}",
                )
                self.ledger.commit(reservation_id)
                selected.append(
                    SelectedVoxelBlock(
                        candidate=candidate,
                        newly_covered=newly_covered,
                        effective_score=seed_score,
                        selection_index=len(selected) + 1,
                        component_seed=bool(selected),
                    )
                )
                occupied.update(candidate.cells)
                covered.update(candidate.target_cells)
                decisions.append(
                    SelectionDecision(
                        group_id=f"segment_seed_{segment}",
                        selected_candidate_id=f"{candidate.block_type}@{candidate.origin}",
                        status="SELECTED",
                        base_score=seed_score,
                        scarcity_penalty=0.0,
                        effective_score=seed_score,
                        requirements={candidate.block_type: 1},
                        shortages={},
                        selection_kind="segment_seed",
                    )
                )

        while target and len(covered) / len(target) < self.config.coverage_target:
            usable: list[tuple[VoxelCandidate, int, bool]] = []
            connected_candidate_exists = False
            for candidate in candidates:
                if candidate.cells & occupied:
                    continue
                if not self.ledger.can_reserve({candidate.block_type: 1}):
                    continue
                new_count = len(candidate.target_cells - covered)
                if new_count <= 0:
                    continue
                connected = not selected or any(
                    blocks_face_touch(
                        SelectedVoxelBlock(candidate, frozenset(), 0.0, 0, False),
                        existing,
                    )
                    for existing in selected
                )
                connected_candidate_exists = connected_candidate_exists or connected
                usable.append((candidate, new_count, connected))

            if not usable:
                stop_reason = "no_feasible_non_overlapping_candidate"
                break

            ranked: list[tuple[float, VoxelCandidate, int, bool]] = []
            for candidate, new_count, connected in usable:
                if connected_candidate_exists and not connected:
                    continue
                if selected and not connected and not self.config.allow_new_component_seed:
                    continue
                penalty = scarcity_penalty(
                    self.ledger,
                    {candidate.block_type: 1},
                    weight=self.config.scarcity_weight,
                )
                efficiency = new_count / candidate.volume
                score = (
                    new_count * self.config.new_coverage_weight
                    - candidate.overhang * self.config.overhang_weight
                    + (self.config.connectivity_bonus if selected and connected else 0.0)
                    + efficiency * self.config.efficiency_bonus
                    + candidate.segment_purity * self.config.segment_purity_bonus
                    + candidate.packing_priority / 10000.0
                    - self.config.block_type_penalties.get(candidate.block_type, 0.0)
                    - penalty
                    - candidate.origin[2] / 10000.0
                )
                ranked.append((score, candidate, new_count, connected))

            if not ranked:
                stop_reason = "connectivity_gate_blocked_remaining_candidates"
                break

            score, candidate, _, connected = max(
                ranked,
                key=lambda row: (
                    row[0],
                    row[2],
                    row[1].packing_priority,
                    row[1].block_type,
                    tuple(-value for value in row[1].origin),
                ),
            )
            newly_covered = frozenset(candidate.target_cells - covered)
            reservation_id = self.ledger.reserve(
                {candidate.block_type: 1},
                reason=(
                    f"structural_voxel:{len(selected) + 1}:"
                    f"{candidate.dominant_segment}:{candidate.origin}"
                ),
            )
            self.ledger.commit(reservation_id)
            item = SelectedVoxelBlock(
                candidate=candidate,
                newly_covered=newly_covered,
                effective_score=score,
                selection_index=len(selected) + 1,
                component_seed=bool(selected and not connected),
            )
            selected.append(item)
            occupied.update(candidate.cells)
            covered.update(candidate.target_cells)
            decisions.append(
                SelectionDecision(
                    group_id=f"structural_voxel_{len(selected):03d}",
                    selected_candidate_id=f"{candidate.block_type}@{candidate.origin}",
                    status="SELECTED",
                    base_score=score,
                    scarcity_penalty=scarcity_penalty(
                        self.ledger,
                        {candidate.block_type: 1},
                        weight=self.config.scarcity_weight,
                    ),
                    effective_score=score,
                    requirements={candidate.block_type: 1},
                    shortages={},
                    selection_kind="structural_voxel",
                )
            )

        placements = assign_build_steps(selected)
        inventory_validation = validate_final_inventory(
            final_parts=placements,
            inventory=self.ledger.inventory,
            ledger_committed=self.ledger.committed_counts,
        )
        geometry_validation = validate_voxel_build(
            voxel_model=voxel_model,
            selected_blocks=selected,
            coverage_target=self.config.coverage_target,
        )
        if inventory_validation["status"] != "PASS":
            status = str(inventory_validation["status"])
        elif geometry_validation["status"] != "PASS":
            status = str(geometry_validation["status"])
        else:
            status = "PASS"

        planning_result = PlanningResult(
            status=status,
            final_parts=placements,
            decisions=decisions,
            unmet_requirements=[],
            inventory_validation=inventory_validation,
        )
        planner_summary = {
            "candidate_count": len(candidates),
            "selected_block_count": len(selected),
            "selected_by_block_type": dict(
                sorted(Counter(item.candidate.block_type for item in selected).items())
            ),
            "covered_target_voxels": len(covered),
            "target_voxels": len(target),
            "coverage_fraction": len(covered) / len(target) if target else 0.0,
            "stop_reason": stop_reason,
            "configuration": {
                key: value for key, value in self.config.__dict__.items()
            },
        }
        return selected, placements, planning_result, geometry_validation, planner_summary
