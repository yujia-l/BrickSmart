from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from bricksmart.geometry.models import GridCoord, LoadedObjModel, VoxelModel
from bricksmart.planning.models import Placement, PlanningResult


@dataclass(frozen=True)
class VoxelCandidate:
    block_type: str
    origin: GridCoord
    dimensions: GridCoord
    cells: frozenset[GridCoord]
    target_cells: frozenset[GridCoord]
    dominant_segment: str
    segment_purity: float
    packing_priority: int

    @property
    def volume(self) -> int:
        return len(self.cells)

    @property
    def target_overlap(self) -> int:
        return len(self.target_cells)

    @property
    def overhang(self) -> int:
        return self.volume - self.target_overlap


@dataclass(frozen=True)
class SelectedVoxelBlock:
    candidate: VoxelCandidate
    newly_covered: frozenset[GridCoord]
    effective_score: float
    selection_index: int
    component_seed: bool

    def to_placement(self, *, step: int | None = None) -> Placement:
        return Placement(
            part_id=f"part_{self.selection_index:03d}",
            block_type=self.candidate.block_type,
            segment_id=self.candidate.dominant_segment,
            step=step,
            metadata={
                "origin_grid": list(self.candidate.origin),
                "dimensions_grid": list(self.candidate.dimensions),
                "target_overlap": self.candidate.target_overlap,
                "newly_covered": len(self.newly_covered),
                "overhang_voxels": self.candidate.overhang,
                "segment_purity": self.candidate.segment_purity,
                "effective_score": self.effective_score,
                "component_seed": self.component_seed,
            },
        )


@dataclass(frozen=True)
class StructuralPlannerConfig:
    minimum_candidate_fill_ratio: float = 0.20
    coverage_target: float = 0.93
    scarcity_weight: float = 0.25
    overhang_weight: float = 1.20
    new_coverage_weight: float = 10.0
    connectivity_bonus: float = 3.0
    efficiency_bonus: float = 2.0
    segment_purity_bonus: float = 0.5
    allow_new_component_seed: bool = True
    variant_name: str = "balanced"
    block_type_penalties: dict[str, float] = field(default_factory=dict)
    require_segment_representation: bool = False
    symmetry_mode: str = "required"
    minimum_target_symmetry: float = 0.95
    minimum_build_volume_symmetry: float = 0.98
    minimum_exact_block_symmetry: float = 1.0
    symmetry_coverage_reward: float = 100.0
    symmetry_block_count_penalty: float = 0.10
    symmetry_solver_time_limit_seconds: float = 30.0
    symmetry_solver_relative_gap: float = 0.0


@dataclass
class ObjBuildResult:
    status: str
    model: LoadedObjModel
    voxel_model: VoxelModel
    selected_blocks: list[SelectedVoxelBlock]
    placements: list[Placement]
    planning_result: PlanningResult
    geometry_validation: dict[str, Any]
    build_sequence_validation: dict[str, Any]
    planner_summary: dict[str, Any] = field(default_factory=dict)
    segment_sequence_validation: dict[str, Any] = field(default_factory=dict)
    global_plan_alternatives: list[dict[str, Any]] = field(default_factory=list)
    segment_inventory_allocations: list[dict[str, Any]] = field(default_factory=list)
    interface_reservations: list[dict[str, Any]] = field(default_factory=list)
    segment_coverage: list[dict[str, Any]] = field(default_factory=list)
    symmetry_validation: dict[str, Any] = field(default_factory=dict)
    symmetry_segment_pairs: list[dict[str, Any]] = field(default_factory=list)
    symmetry_groups: list[dict[str, Any]] = field(default_factory=list)
    catalog_summary: dict[str, Any] = field(default_factory=dict)
    catalog_colors: dict[str, str] = field(default_factory=dict)

    def to_summary(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "model": self.model.to_summary(),
            "voxelization": self.voxel_model.to_summary(),
            "planner_summary": self.planner_summary,
            "geometry_validation": self.geometry_validation,
            "build_sequence_validation": self.build_sequence_validation,
            "segment_sequence_validation": self.segment_sequence_validation,
            "symmetry_validation": self.symmetry_validation,
            "catalog": self.catalog_summary,
            "part_count": len(self.placements),
            "parts": [part.to_dict() for part in self.placements],
        }
