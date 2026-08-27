"""Symmetry declaration and mirror-planning helpers.

This module interprets contract symmetry data and prepares mirrored structural
or functional planning requirements.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from bricksmart.geometry.models import GridCoord, VoxelModel
from bricksmart.planning.voxel_models import VoxelCandidate


@dataclass(frozen=True)
class SymmetrySpec:
    axis: int
    plane_sum: int
    target_match_count: int
    target_voxel_count: int
    target_symmetry_fraction: float
    segment_pairs: dict[str, str]
    segment_pair_rows: list[dict[str, object]]

    @property
    def axis_name(self) -> str:
        """Return axis name.
        
        :returns: The result produced by the function.
        :rtype: str
        """
        return ("x", "y", "z")[self.axis]

    @property
    def plane_coordinate(self) -> float:
        """Return the plane coordinate value.
        
        :returns: The result produced by the function.
        :rtype: float
        """
        return self.plane_sum / 2.0

    def mirror_cell(self, cell: GridCoord) -> GridCoord:
        """Mirror cell.
        
        :param cell: The cell value.
        :type cell: GridCoord
        :returns: The result produced by the function.
        :rtype: GridCoord
        """
        values = list(cell)
        values[self.axis] = self.plane_sum - values[self.axis]
        return tuple(values)  # type: ignore[return-value]

    def mirror_origin(self, origin: GridCoord, dimensions: GridCoord) -> GridCoord:
        """Mirror origin.
        
        :param origin: The origin value.
        :type origin: GridCoord
        :param dimensions: The dimensions value.
        :type dimensions: GridCoord
        :returns: The result produced by the function.
        :rtype: GridCoord
        """
        values = list(origin)
        values[self.axis] = (
            self.plane_sum - origin[self.axis] - dimensions[self.axis] + 1
        )
        return tuple(values)  # type: ignore[return-value]


def _symmetry_fraction(
    voxels: frozenset[GridCoord], *, axis: int, plane_sum: int
) -> tuple[int, float]:
    """Return symmetry fraction.
    
    :param voxels: The voxels value.
    :type voxels: frozenset[GridCoord]
    :param axis: The axis value.
    :type axis: int
    :param plane_sum: The plane sum value.
    :type plane_sum: int
    :returns: The result produced by the function.
    :rtype: tuple[int, float]
    """
    mirrored = {
        tuple(
            plane_sum - value if index == axis else value
            for index, value in enumerate(cell)
        )
        for cell in voxels
    }
    matches = len(set(voxels) & mirrored)
    return matches, matches / len(voxels) if voxels else 1.0


def _detect_segment_pairs(
    voxel_model: VoxelModel,
    *,
    axis: int,
    plane_sum: int,
) -> tuple[dict[str, str], list[dict[str, object]]]:
    """Detect segment pairs.
    
    :param voxel_model: The voxel model value.
    :type voxel_model: VoxelModel
    :param axis: The axis value.
    :type axis: int
    :param plane_sum: The plane sum value.
    :type plane_sum: int
    :returns: The result produced by the function.
    :rtype: tuple[dict[str, str], list[dict[str, object]]]
    """
    by_segment: dict[str, set[GridCoord]] = defaultdict(set)
    for cell, segment in voxel_model.segment_by_voxel.items():
        by_segment[segment].add(cell)

    overlap: dict[tuple[str, str], int] = {}
    for left, cells in by_segment.items():
        mirrored = {
            tuple(
                plane_sum - value if index == axis else value
                for index, value in enumerate(cell)
            )
            for cell in cells
        }
        for right, right_cells in by_segment.items():
            overlap[(left, right)] = len(mirrored & right_cells)

    unmatched = set(by_segment)
    pairs: dict[str, str] = {}
    rows: list[dict[str, object]] = []

    # Self-symmetric centerline segments are assigned first.
    for segment in sorted(by_segment):
        self_overlap = overlap[(segment, segment)]
        best_other = max(
            (overlap[(segment, other)] for other in by_segment if other != segment),
            default=0,
        )
        if self_overlap >= best_other and self_overlap / len(by_segment[segment]) >= 0.80:
            pairs[segment] = segment
            unmatched.discard(segment)

    while unmatched:
        left = min(unmatched)
        candidates = [right for right in unmatched if right != left]
        if not candidates:
            pairs[left] = left
            unmatched.remove(left)
            continue
        right = max(
            candidates,
            key=lambda candidate: (
                overlap[(left, candidate)] + overlap[(candidate, left)],
                min(
                    overlap[(left, candidate)] / max(1, len(by_segment[left])),
                    overlap[(candidate, left)] / max(1, len(by_segment[candidate])),
                ),
                candidate,
            ),
        )
        pairs[left] = right
        pairs[right] = left
        unmatched.remove(left)
        unmatched.remove(right)

    emitted: set[tuple[str, str]] = set()
    for left in sorted(pairs):
        right = pairs[left]
        key = tuple(sorted((left, right)))
        if key in emitted:
            continue
        emitted.add(key)
        left_size = len(by_segment[left])
        right_size = len(by_segment[right])
        left_to_right = overlap[(left, right)]
        right_to_left = overlap[(right, left)]
        rows.append(
            {
                "left_segment": left,
                "right_segment": right,
                "pair_kind": "centerline" if left == right else "mirrored_pair",
                "left_target_voxels": left_size,
                "right_target_voxels": right_size,
                "left_mirror_overlap": left_to_right,
                "right_mirror_overlap": right_to_left,
                "left_match_fraction": left_to_right / left_size if left_size else 1.0,
                "right_match_fraction": right_to_left / right_size if right_size else 1.0,
            }
        )
    return pairs, rows


def detect_bilateral_symmetry(voxel_model: VoxelModel) -> SymmetrySpec:
    """Detect bilateral symmetry.
    
    :param voxel_model: The voxel model value.
    :type voxel_model: VoxelModel
    :returns: The result produced by the function.
    :rtype: SymmetrySpec
    """
    candidates: list[tuple[float, int, int, int]] = []
    for axis in range(3):
        plane_sum = voxel_model.grid_bounds_min[axis] + voxel_model.grid_bounds_max[axis]
        matches, fraction = _symmetry_fraction(
            voxel_model.target_voxels,
            axis=axis,
            plane_sum=plane_sum,
        )
        candidates.append((fraction, matches, axis, plane_sum))
    fraction, matches, axis, plane_sum = max(candidates)
    segment_pairs, rows = _detect_segment_pairs(
        voxel_model,
        axis=axis,
        plane_sum=plane_sum,
    )
    return SymmetrySpec(
        axis=axis,
        plane_sum=plane_sum,
        target_match_count=matches,
        target_voxel_count=len(voxel_model.target_voxels),
        target_symmetry_fraction=fraction,
        segment_pairs=segment_pairs,
        segment_pair_rows=rows,
    )


def mirror_candidate_key(
    candidate: VoxelCandidate,
    symmetry: SymmetrySpec,
) -> tuple[str, GridCoord, GridCoord]:
    """Mirror candidate key.
    
    :param candidate: The candidate value.
    :type candidate: VoxelCandidate
    :param symmetry: The symmetry value.
    :type symmetry: SymmetrySpec
    :returns: The result produced by the function.
    :rtype: tuple[str, GridCoord, GridCoord]
    """
    return (
        candidate.block_type,
        symmetry.mirror_origin(candidate.origin, candidate.dimensions),
        candidate.dimensions,
    )
