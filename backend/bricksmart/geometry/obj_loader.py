"""OBJ loading and mesh extraction helpers.

This module parses segmented OBJ files and exposes mesh, face, vertex, material,
and segment information for voxelization.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np

from bricksmart.geometry.models import LoadedObjModel, ObjSegment

_AXIS_NAMES = ("x", "y", "z")


def _resolve_axis_order(vertices: np.ndarray, up_axis: str) -> tuple[int, int, int]:
    """Resolve axis order.
    
    :param vertices: The vertices value.
    :type vertices: np.ndarray
    :param up_axis: The up axis value.
    :type up_axis: str
    :returns: The computed result.
    :rtype: tuple[int, int, int]
    """
    normalized = up_axis.strip().lower()
    if normalized == "auto":
        extents = np.ptp(vertices, axis=0)
        up_index = int(np.argmin(extents))
        horizontal = [index for index in range(3) if index != up_index]
        first = max(horizontal, key=lambda index: (extents[index], -index))
        second = next(index for index in horizontal if index != first)
        return first, second, up_index
    if normalized not in _AXIS_NAMES:
        raise ValueError("up_axis must be one of: auto, x, y, z")
    up_index = _AXIS_NAMES.index(normalized)
    horizontal = [index for index in range(3) if index != up_index]
    return horizontal[0], horizontal[1], up_index


def _parse_face_index(token: str, vertex_count: int) -> int:
    """Parse face index.
    
    :param token: The token value.
    :type token: str
    :param vertex_count: The vertex count value.
    :type vertex_count: int
    :returns: The computed result.
    :rtype: int
    """
    raw = int(token.split("/")[0])
    if raw == 0:
        raise ValueError("OBJ vertex indices are one-based and cannot be zero")
    return raw - 1 if raw > 0 else vertex_count + raw


def load_segmented_obj(path: str | Path, *, up_axis: str = "auto") -> LoadedObjModel:
    """Load an OBJ while preserving each `o` object as a source segment.

    Polygon faces are triangulated with a deterministic fan. Coordinates are
    permuted so the requested source up axis becomes planner Z.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"OBJ not found: {path}")

    vertices: list[tuple[float, float, float]] = []
    faces_by_segment: dict[str, list[tuple[int, int, int]]] = defaultdict(list)
    source_faces_by_segment: dict[str, int] = defaultdict(int)
    current_segment = "default"

    with path.open(encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line.startswith("o "):
                value = line[2:].strip()
                current_segment = value or f"unnamed_{line_number}"
            elif line.startswith("v "):
                fields = line.split()
                if len(fields) < 4:
                    raise ValueError(f"Invalid vertex at {path}:{line_number}")
                vertices.append((float(fields[1]), float(fields[2]), float(fields[3])))
            elif line.startswith("f "):
                tokens = line.split()[1:]
                if len(tokens) < 3:
                    raise ValueError(f"Invalid face at {path}:{line_number}")
                indices = [_parse_face_index(token, len(vertices)) for token in tokens]
                if any(index < 0 or index >= len(vertices) for index in indices):
                    raise ValueError(f"Face index out of range at {path}:{line_number}")
                source_faces_by_segment[current_segment] += 1
                for offset in range(1, len(indices) - 1):
                    faces_by_segment[current_segment].append(
                        (indices[0], indices[offset], indices[offset + 1])
                    )

    if not vertices or not faces_by_segment:
        raise ValueError(f"OBJ contains no usable mesh geometry: {path}")

    source_vertices = np.asarray(vertices, dtype=float)
    source_bounds = np.vstack((source_vertices.min(axis=0), source_vertices.max(axis=0)))
    order = _resolve_axis_order(source_vertices, up_axis)
    planner_vertices = source_vertices[:, order]
    planner_bounds = np.vstack((planner_vertices.min(axis=0), planner_vertices.max(axis=0)))

    segments: list[ObjSegment] = []
    for segment_id, global_faces_list in faces_by_segment.items():
        global_faces = np.asarray(global_faces_list, dtype=np.int64)
        used = np.unique(global_faces)
        remap = np.full(len(planner_vertices), -1, dtype=np.int64)
        remap[used] = np.arange(len(used), dtype=np.int64)
        local_faces = remap[global_faces]
        segments.append(
            ObjSegment(
                segment_id=segment_id,
                vertices=planner_vertices[used].copy(),
                faces=local_faces,
                source_face_count=source_faces_by_segment[segment_id],
            )
        )

    return LoadedObjModel(
        source_path=path.resolve(),
        segments=tuple(segments),
        source_vertex_count=len(source_vertices),
        source_face_count=sum(source_faces_by_segment.values()),
        axis_mapping=tuple(_AXIS_NAMES[index] for index in order),
        source_bounds=source_bounds,
        planner_bounds=planner_bounds,
    )
