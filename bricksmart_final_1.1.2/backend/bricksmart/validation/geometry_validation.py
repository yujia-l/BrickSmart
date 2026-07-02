from __future__ import annotations

from collections import Counter

from bricksmart.geometry.models import VoxelModel
from bricksmart.planning.build_order import connected_components, contact_graph
from bricksmart.planning.voxel_models import SelectedVoxelBlock


def validate_voxel_build(
    *,
    voxel_model: VoxelModel,
    selected_blocks: list[SelectedVoxelBlock],
    coverage_target: float,
) -> dict[str, object]:
    target = set(voxel_model.target_voxels)
    occupied: set[tuple[int, int, int]] = set()
    covered: set[tuple[int, int, int]] = set()
    overlap_cells: set[tuple[int, int, int]] = set()

    for selected in selected_blocks:
        cells = set(selected.candidate.cells)
        overlap_cells.update(occupied & cells)
        occupied.update(cells)
        covered.update(cells & target)

    coverage_fraction = len(covered) / len(target) if target else 0.0
    overhang = occupied - target
    graph = contact_graph(selected_blocks)
    components = connected_components(graph) if graph else []

    segment_totals = Counter(voxel_model.segment_by_voxel.values())
    segment_covered = Counter(
        voxel_model.segment_by_voxel[voxel] for voxel in covered
    )
    segment_rows = []
    warnings: list[str] = []
    for segment_id in sorted(segment_totals):
        total = segment_totals[segment_id]
        covered_count = segment_covered[segment_id]
        fraction = covered_count / total if total else 0.0
        segment_rows.append(
            {
                "segment_id": segment_id,
                "target_voxels": total,
                "covered_voxels": covered_count,
                "coverage_fraction": fraction,
            }
        )
        if fraction < 0.75:
            warnings.append(
                f"Segment {segment_id} has low coarse coverage ({fraction:.1%})"
            )

    failures: list[str] = []
    if coverage_fraction < coverage_target:
        failures.append(
            f"Coverage {coverage_fraction:.1%} is below target {coverage_target:.1%}"
        )
    if overlap_cells:
        failures.append(f"{len(overlap_cells)} block-volume cells overlap")
    if len(components) > 1:
        failures.append(f"Block contact graph has {len(components)} components")

    return {
        "status": "PASS" if not failures else "FAIL_GEOMETRY_VALIDATION",
        "coverage_target": coverage_target,
        "target_voxel_count": len(target),
        "covered_target_voxel_count": len(covered),
        "uncovered_target_voxel_count": len(target - covered),
        "coverage_fraction": coverage_fraction,
        "occupied_block_voxel_count": len(occupied),
        "overhang_voxel_count": len(overhang),
        "overlap_voxel_count": len(overlap_cells),
        "block_contact_component_count": len(components),
        "block_contact_component_sizes": sorted(
            (len(component) for component in components), reverse=True
        ),
        "segment_coverage": segment_rows,
        "warnings": warnings,
        "failures": failures,
    }
