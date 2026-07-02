from __future__ import annotations

from collections import Counter, defaultdict, deque

import numpy as np
import trimesh

from bricksmart.geometry.models import GridCoord, LoadedObjModel, VoxelModel


def _component_filter(voxels: set[GridCoord], minimum_size: int) -> set[GridCoord]:
    if minimum_size <= 1:
        return voxels
    remaining = set(voxels)
    kept: set[GridCoord] = set()
    neighbors = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
    while remaining:
        seed = remaining.pop()
        component = {seed}
        queue = deque([seed])
        while queue:
            current = queue.popleft()
            for delta in neighbors:
                candidate = tuple(current[i] + delta[i] for i in range(3))
                if candidate in remaining:
                    remaining.remove(candidate)
                    component.add(candidate)
                    queue.append(candidate)
        if len(component) >= minimum_size:
            kept.update(component)
    return kept


def voxelize_segmented_model(
    model: LoadedObjModel,
    *,
    target_longest_cells: int = 18,
    fill: bool = True,
    minimum_component_voxels: int = 1,
) -> VoxelModel:
    if target_longest_cells < 4:
        raise ValueError("target_longest_cells must be at least 4")
    longest_extent = float(model.planner_extents.max())
    if longest_extent <= 0:
        raise ValueError("OBJ bounds have no positive extent")

    pitch = longest_extent / target_longest_cells
    origin_array = np.floor(model.planner_bounds[0] / pitch) * pitch - pitch
    memberships: dict[GridCoord, set[str]] = defaultdict(set)

    for segment in model.segments:
        mesh = trimesh.Trimesh(
            vertices=segment.vertices,
            faces=segment.faces,
            process=False,
            validate=False,
        )
        voxel_grid = mesh.voxelized(pitch)
        if fill:
            try:
                voxel_grid = voxel_grid.fill()
            except (ValueError, RuntimeError):
                pass
        indices = np.rint((voxel_grid.points - origin_array) / pitch).astype(np.int64)
        for row in indices:
            memberships[(int(row[0]), int(row[1]), int(row[2]))].add(segment.segment_id)

    target = _component_filter(set(memberships), minimum_component_voxels)
    if not target:
        raise ValueError("Voxelization produced no target voxels")

    filtered_memberships = {
        voxel: tuple(sorted(memberships[voxel])) for voxel in target
    }
    segment_by_voxel = {
        voxel: filtered_memberships[voxel][0] for voxel in target
    }
    counts = Counter(segment_by_voxel.values())
    array = np.asarray(sorted(target), dtype=np.int64)

    return VoxelModel(
        target_voxels=frozenset(target),
        segment_by_voxel=segment_by_voxel,
        memberships_by_voxel=filtered_memberships,
        pitch=float(pitch),
        origin=tuple(float(value) for value in origin_array),
        grid_bounds_min=tuple(int(value) for value in array.min(axis=0)),
        grid_bounds_max=tuple(int(value) for value in array.max(axis=0)),
        segment_voxel_counts=dict(counts),
    )
