from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

GridCoord = tuple[int, int, int]


@dataclass(frozen=True)
class ObjSegment:
    segment_id: str
    vertices: np.ndarray
    faces: np.ndarray
    source_face_count: int

    @property
    def bounds(self) -> np.ndarray:
        return np.vstack((self.vertices.min(axis=0), self.vertices.max(axis=0)))

    @property
    def extents(self) -> np.ndarray:
        return self.bounds[1] - self.bounds[0]

    def to_summary(self) -> dict[str, Any]:
        bounds = self.bounds
        return {
            "segment_id": self.segment_id,
            "vertex_count": int(len(self.vertices)),
            "source_face_count": int(self.source_face_count),
            "triangulated_face_count": int(len(self.faces)),
            "bounds_min": [float(v) for v in bounds[0]],
            "bounds_max": [float(v) for v in bounds[1]],
            "extents": [float(v) for v in self.extents],
        }


@dataclass(frozen=True)
class LoadedObjModel:
    source_path: Path
    segments: tuple[ObjSegment, ...]
    source_vertex_count: int
    source_face_count: int
    axis_mapping: tuple[str, str, str]
    source_bounds: np.ndarray
    planner_bounds: np.ndarray

    @property
    def planner_extents(self) -> np.ndarray:
        return self.planner_bounds[1] - self.planner_bounds[0]

    def to_summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "segment_count": len(self.segments),
            "segment_ids": [segment.segment_id for segment in self.segments],
            "source_vertex_count": int(self.source_vertex_count),
            "source_face_count": int(self.source_face_count),
            "axis_mapping": list(self.axis_mapping),
            "source_bounds": self.source_bounds.tolist(),
            "planner_bounds": self.planner_bounds.tolist(),
            "planner_extents": self.planner_extents.tolist(),
        }


@dataclass(frozen=True)
class VoxelModel:
    target_voxels: frozenset[GridCoord]
    segment_by_voxel: dict[GridCoord, str]
    memberships_by_voxel: dict[GridCoord, tuple[str, ...]]
    pitch: float
    origin: tuple[float, float, float]
    grid_bounds_min: GridCoord
    grid_bounds_max: GridCoord
    segment_voxel_counts: dict[str, int] = field(default_factory=dict)

    @property
    def grid_shape(self) -> GridCoord:
        return tuple(
            self.grid_bounds_max[i] - self.grid_bounds_min[i] + 1 for i in range(3)
        )

    def to_summary(self) -> dict[str, Any]:
        return {
            "target_voxel_count": len(self.target_voxels),
            "pitch": self.pitch,
            "origin": list(self.origin),
            "grid_bounds_min": list(self.grid_bounds_min),
            "grid_bounds_max": list(self.grid_bounds_max),
            "grid_shape": list(self.grid_shape),
            "segment_voxel_counts": dict(sorted(self.segment_voxel_counts.items())),
            "overlap_voxel_count": sum(
                1 for memberships in self.memberships_by_voxel.values() if len(memberships) > 1
            ),
        }
