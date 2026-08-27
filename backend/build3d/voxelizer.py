"""Segmented OBJ voxelization utilities.

This is the production-oriented extraction of the early notebook stages:
OBJ segment loading, segmented voxelization, cleanup, connected-component
splitting, and segment adjacency/contact geometry.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class ObjSegment:
    segment_id: int
    name: str
    faces: list[list[int]]


@dataclass
class VoxelBuild:
    voxel_segment: np.ndarray
    adjacency: dict[int, list[int]]
    contacts: dict[tuple[int, int], list[dict[str, Any]]]


def build_segmented_voxel_grid(
    obj_path: Path,
    voxel_size: int = 32,
    samples_per_triangle: int = 18,
    clean_segments: bool = True,
) -> VoxelBuild:
    vertices, segments = load_obj_segments(obj_path)
    voxel_segment = obj_to_voxel_with_segments(vertices, segments, voxel_size, samples_per_triangle)
    if clean_segments:
        voxel_segment = enforce_2x2_footprint(voxel_segment)
        voxel_segment = clean_vertical_columns(voxel_segment)
        voxel_segment = split_segment_connected_components(voxel_segment)
    adjacency = compute_segment_adjacency(voxel_segment)
    contacts = compute_contact_surfaces(voxel_segment)
    return VoxelBuild(voxel_segment=voxel_segment, adjacency=adjacency, contacts=contacts)


def load_obj_segments(path: Path) -> tuple[np.ndarray, list[ObjSegment]]:
    vertices: list[list[float]] = []
    segments: list[ObjSegment] = []
    current_name = "segment_1"
    current_faces: list[list[int]] = []

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("o ") or line.startswith("g "):
            if current_faces:
                segments.append(ObjSegment(len(segments) + 1, current_name, current_faces))
                current_faces = []
            current_name = line.split(" ", 1)[1].strip() or f"segment_{len(segments) + 1}"
        elif line.startswith("v "):
            parts = line.split()
            if len(parts) >= 4:
                vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
        elif line.startswith("f "):
            indices = []
            for part in line.split()[1:]:
                try:
                    indices.append(int(part.split("/")[0]) - 1)
                except ValueError:
                    pass
            if len(indices) >= 3:
                for i in range(1, len(indices) - 1):
                    current_faces.append([indices[0], indices[i], indices[i + 1]])

    if current_faces:
        segments.append(ObjSegment(len(segments) + 1, current_name, current_faces))
    if not segments and vertices:
        segments.append(ObjSegment(1, "root", []))
    return np.asarray(vertices, dtype=float), segments


def obj_to_voxel_with_segments(
    vertices: np.ndarray,
    segments: list[ObjSegment],
    voxel_size: int,
    samples_per_triangle: int,
) -> np.ndarray:
    voxel = np.zeros((voxel_size, voxel_size, voxel_size), dtype=np.int16)
    if len(vertices) == 0:
        return voxel

    min_bound = vertices.min(axis=0)
    max_bound = vertices.max(axis=0)
    scale = max(float((max_bound - min_bound).max()), 1e-6)
    normalized = (vertices - min_bound) / scale
    normalized = np.clip(normalized * (voxel_size - 1), 0, voxel_size - 1)

    for segment in segments:
        for face in segment.faces:
            tri = normalized[np.asarray(face)]
            for point in sample_triangle(tri, samples_per_triangle):
                idx = np.clip(np.rint(point).astype(int), 0, voxel_size - 1)
                voxel[idx[0], idx[1], idx[2]] = segment.segment_id
    return voxel


def sample_triangle(tri: np.ndarray, samples: int) -> list[np.ndarray]:
    points = [tri[0], tri[1], tri[2], tri.mean(axis=0)]
    grid = max(2, int(math.sqrt(samples)))
    for i in range(grid + 1):
        for j in range(grid + 1 - i):
            a = i / grid
            b = j / grid
            c = 1.0 - a - b
            points.append(a * tri[0] + b * tri[1] + c * tri[2])
    return points


def enforce_2x2_footprint(voxel_matrix: np.ndarray) -> np.ndarray:
    sx, sy, _ = voxel_matrix.shape
    snapped = np.zeros_like(voxel_matrix)
    for x in range(0, sx - 1, 2):
        for y in range(0, sy - 1, 2):
            block = voxel_matrix[x : x + 2, y : y + 2, :]
            mask = np.any(block > 0, axis=(0, 1))
            for z in np.where(mask)[0]:
                vals = block[:, :, z].flatten()
                vals = vals[vals > 0]
                if len(vals):
                    snapped[x : x + 2, y : y + 2, z] = Counter(vals).most_common(1)[0][0]
    return snapped


def clean_vertical_columns(voxel_matrix: np.ndarray) -> np.ndarray:
    cleaned = voxel_matrix.copy()
    sx, sy, _ = cleaned.shape
    for x in range(sx):
        for y in range(sy):
            filled = np.where(cleaned[x, y, :] > 0)[0]
            if len(filled) == 1:
                cleaned[x, y, filled[0]] = 0
    return cleaned


def split_segment_connected_components(voxel_segment: np.ndarray) -> np.ndarray:
    sx, sy, sz = voxel_segment.shape
    new_seg = np.zeros_like(voxel_segment)
    visited = np.zeros_like(voxel_segment, dtype=bool)
    directions = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
    new_id = 1
    for x in range(sx):
        for y in range(sy):
            for z in range(sz):
                if visited[x, y, z] or voxel_segment[x, y, z] <= 0:
                    continue
                source_id = voxel_segment[x, y, z]
                queue = [(x, y, z)]
                visited[x, y, z] = True
                component = []
                while queue:
                    cx, cy, cz = queue.pop()
                    component.append((cx, cy, cz))
                    for dx, dy, dz in directions:
                        nx, ny, nz = cx + dx, cy + dy, cz + dz
                        if 0 <= nx < sx and 0 <= ny < sy and 0 <= nz < sz:
                            if not visited[nx, ny, nz] and voxel_segment[nx, ny, nz] == source_id:
                                visited[nx, ny, nz] = True
                                queue.append((nx, ny, nz))
                for cx, cy, cz in component:
                    new_seg[cx, cy, cz] = new_id
                new_id += 1
    return new_seg


def compute_segment_adjacency(voxel_segment: np.ndarray) -> dict[int, list[int]]:
    adjacency: dict[int, set[int]] = defaultdict(set)
    sx, sy, sz = voxel_segment.shape
    for x in range(sx):
        for y in range(sy):
            for z in range(sz):
                current = int(voxel_segment[x, y, z])
                if current <= 0:
                    continue
                for dx, dy, dz in [(1, 0, 0), (0, 1, 0), (0, 0, 1)]:
                    nx, ny, nz = x + dx, y + dy, z + dz
                    if nx >= sx or ny >= sy or nz >= sz:
                        continue
                    other = int(voxel_segment[nx, ny, nz])
                    if other > 0 and other != current:
                        adjacency[current].add(other)
                        adjacency[other].add(current)
    return {key: sorted(values) for key, values in adjacency.items()}


def compute_contact_surfaces(voxel_segment: np.ndarray) -> dict[tuple[int, int], list[dict[str, Any]]]:
    contacts: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    sx, sy, sz = voxel_segment.shape
    directions = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
    for x in range(sx):
        for y in range(sy):
            for z in range(sz):
                current = int(voxel_segment[x, y, z])
                if current <= 0:
                    continue
                for dx, dy, dz in directions:
                    nx, ny, nz = x + dx, y + dy, z + dz
                    if nx >= sx or ny >= sy or nz >= sz:
                        continue
                    other = int(voxel_segment[nx, ny, nz])
                    if other <= 0 or other == current:
                        continue
                    key = tuple(sorted((current, other)))
                    normal = (dx, dy, dz) if current < other else (-dx, -dy, -dz)
                    contacts[key].append(
                        {
                            "a": current,
                            "b": other,
                            "voxel_a": (x, y, z),
                            "voxel_b": (nx, ny, nz),
                            "normal": normal,
                        }
                    )
    return dict(contacts)
