"""Symmetry validation helpers.

This module checks mirror-pair completeness and symmetry expectations declared
by the model contract.
"""

from __future__ import annotations

from collections import Counter

from bricksmart.geometry.models import GridCoord, VoxelModel
from bricksmart.planning.symmetry import SymmetrySpec
from bricksmart.planning.voxel_models import SelectedVoxelBlock


def validate_bilateral_symmetry(
    *,
    voxel_model: VoxelModel,
    selected_blocks: list[SelectedVoxelBlock],
    symmetry: SymmetrySpec,
    minimum_target_symmetry: float = 0.95,
    minimum_build_volume_symmetry: float = 0.98,
    minimum_exact_block_symmetry: float = 1.0,
) -> dict[str, object]:
    """Validate bilateral symmetry.
    
    :param voxel_model: The voxel model value.
    :type voxel_model: VoxelModel
    :param selected_blocks: The selected blocks value.
    :type selected_blocks: list[SelectedVoxelBlock]
    :param symmetry: The symmetry value.
    :type symmetry: SymmetrySpec
    :param minimum_target_symmetry: The minimum target symmetry value.
    :type minimum_target_symmetry: float
    :param minimum_build_volume_symmetry: The minimum build volume symmetry value.
    :type minimum_build_volume_symmetry: float
    :param minimum_exact_block_symmetry: The minimum exact block symmetry value.
    :type minimum_exact_block_symmetry: float
    :returns: The result produced by the function.
    :rtype: dict[str, object]
    """
    occupied: set[GridCoord] = set()
    for block in selected_blocks:
        occupied.update(block.candidate.cells)
    mirrored_occupied = {symmetry.mirror_cell(cell) for cell in occupied}
    volume_matches = len(occupied & mirrored_occupied)
    build_volume_fraction = volume_matches / len(occupied) if occupied else 1.0

    keys = Counter(
        (
            block.candidate.block_type,
            block.candidate.origin,
            block.candidate.dimensions,
        )
        for block in selected_blocks
    )
    exact_matches = 0
    unmatched: list[dict[str, object]] = []
    for block in selected_blocks:
        candidate = block.candidate
        mirror_key = (
            candidate.block_type,
            symmetry.mirror_origin(candidate.origin, candidate.dimensions),
            candidate.dimensions,
        )
        if keys[mirror_key] > 0:
            exact_matches += 1
        else:
            unmatched.append(
                {
                    "part_id": f"part_{block.selection_index:03d}",
                    "block_type": candidate.block_type,
                    "segment_id": candidate.dominant_segment,
                    "origin": list(candidate.origin),
                    "dimensions": list(candidate.dimensions),
                    "expected_mirror_origin": list(mirror_key[1]),
                }
            )
    exact_fraction = exact_matches / len(selected_blocks) if selected_blocks else 1.0

    segment_counts = Counter(
        block.candidate.dominant_segment for block in selected_blocks
    )
    pair_rows: list[dict[str, object]] = []
    checked: set[tuple[str, str]] = set()
    for left, right in sorted(symmetry.segment_pairs.items()):
        key = tuple(sorted((left, right)))
        if key in checked:
            continue
        checked.add(key)
        left_count = segment_counts[left]
        right_count = segment_counts[right]
        pair_rows.append(
            {
                "left_segment": left,
                "right_segment": right,
                "left_block_count": left_count,
                "right_block_count": right_count,
                "count_match": left_count == right_count if left != right else True,
            }
        )

    failures: list[str] = []
    if symmetry.target_symmetry_fraction < minimum_target_symmetry:
        failures.append("source_target_below_minimum_symmetry")
    if build_volume_fraction < minimum_build_volume_symmetry:
        failures.append("build_volume_below_minimum_symmetry")
    if exact_fraction < minimum_exact_block_symmetry:
        failures.append("exact_mirrored_block_fraction_below_minimum")
    if any(not row["count_match"] for row in pair_rows):
        failures.append("mirrored_segment_block_counts_do_not_match")

    return {
        "status": "PASS" if not failures else "FAIL_SYMMETRY",
        "axis": symmetry.axis_name,
        "axis_index": symmetry.axis,
        "plane_sum": symmetry.plane_sum,
        "plane_coordinate": symmetry.plane_coordinate,
        "target_match_count": symmetry.target_match_count,
        "target_voxel_count": symmetry.target_voxel_count,
        "target_symmetry_fraction": symmetry.target_symmetry_fraction,
        "occupied_cell_count": len(occupied),
        "mirrored_occupied_match_count": volume_matches,
        "build_volume_symmetry_fraction": build_volume_fraction,
        "exact_mirrored_block_count": exact_matches,
        "selected_block_count": len(selected_blocks),
        "exact_mirrored_block_fraction": exact_fraction,
        "minimum_target_symmetry": minimum_target_symmetry,
        "minimum_build_volume_symmetry": minimum_build_volume_symmetry,
        "minimum_exact_block_symmetry": minimum_exact_block_symmetry,
        "segment_pair_counts": pair_rows,
        "unmatched_blocks": unmatched,
        "failures": failures,
    }
