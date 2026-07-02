"""BrickSmart block decomposition from segmented voxels.

Ports the canonical notebook path around BlockInstance, face templates,
2x2 columns, staggered block sequencing, and inventory-aware reoptimization.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

BLOCK_HEIGHTS = [4, 3, 2]
BLOCK_TYPE_COLORS = {
    2: "Blue",
    3: "Green",
    4: "Yellow",
}


class FaceType(Enum):
    MALE = 1
    FEMALE = 2
    NONE = 0


BLOCK_FACE_TEMPLATES = {
    (2, 2, 2): {
        "+X": [[FaceType.MALE] * 2 for _ in range(2)],
        "-X": [[FaceType.FEMALE] * 2 for _ in range(2)],
        "+Y": [[FaceType.FEMALE] * 2 for _ in range(2)],
        "-Y": [[FaceType.FEMALE] * 2 for _ in range(2)],
        "+Z": [[FaceType.FEMALE] * 2 for _ in range(2)],
        "-Z": [[FaceType.FEMALE] * 2 for _ in range(2)],
    },
    (2, 2, 3): {
        "+X": [[FaceType.MALE] * 3 for _ in range(2)],
        "-X": [[FaceType.FEMALE] * 3 for _ in range(2)],
        "+Y": [[FaceType.FEMALE] * 3 for _ in range(2)],
        "-Y": [[FaceType.FEMALE] * 3 for _ in range(2)],
        "+Z": [[FaceType.FEMALE] * 2 for _ in range(2)],
        "-Z": [[FaceType.FEMALE] * 2 for _ in range(2)],
    },
    (2, 2, 4): {
        "+X": [[FaceType.MALE] * 4 for _ in range(2)],
        "-X": [[FaceType.FEMALE] * 4 for _ in range(2)],
        "+Y": [[FaceType.FEMALE] * 4 for _ in range(2)],
        "-Y": [[FaceType.FEMALE] * 4 for _ in range(2)],
        "+Z": [[FaceType.FEMALE] * 2 for _ in range(2)],
        "-Z": [[FaceType.FEMALE] * 2 for _ in range(2)],
    },
}


@dataclass
class BlockInstance:
    position: tuple[int, int, int]
    size: tuple[int, int, int]
    segment_id: int
    block_id: int
    rotation: int = 0
    category: str = "structural"
    connector_type: str | None = None
    segment_a: int | None = None
    segment_b: int | None = None
    faces: dict[str, list[list[FaceType]]] = field(init=False)

    def __post_init__(self) -> None:
        faces = BLOCK_FACE_TEMPLATES.get(self.size, {})
        self.faces = self.rotate_faces(faces, self.rotation) if self.rotation else faces

    def rotate_faces(self, faces: dict[str, list[list[FaceType]]], rotation: int) -> dict[str, list[list[FaceType]]]:
        if not faces:
            return {}

        def rotate_matrix(mat: list[list[FaceType]], k: int) -> list[list[FaceType]]:
            return np.rot90(np.asarray(mat, dtype=object), -k, axes=(1, 0)).tolist()

        rotated_faces: dict[str, list[list[FaceType]]] = {}
        k = (rotation // 90) % 4
        face_order = ["+X", "+Y", "-X", "-Y"]
        for i, face in enumerate(face_order):
            rotated_faces[face_order[(i + k) % 4]] = rotate_matrix(faces[face], k)
        rotated_faces["+Z"] = faces["+Z"]
        rotated_faces["-Z"] = faces["-Z"]
        return rotated_faces

    def set_rotation(self, rotation: int) -> None:
        self.rotation = rotation % 360
        self.faces = self.rotate_faces(BLOCK_FACE_TEMPLATES[self.size], self.rotation)


def decompose_voxels_to_blocks(
    voxel_segment: np.ndarray,
    *,
    max_yellow_blocks: int | None = None,
) -> list[BlockInstance]:
    voxel_matrix = (voxel_segment > 0).astype(int)
    columns = voxel_to_2x2_columns(voxel_matrix, voxel_segment)
    if not columns:
        return []
    assigned = assign_sequences_with_stagger(columns)
    optimized = reoptimize_sequences(columns, assigned, max_yellow_blocks=max_yellow_blocks)
    return build_blocks_from_assigned_sequences(columns, optimized)


def voxel_to_2x2_columns(voxel_matrix: np.ndarray, voxel_segment: np.ndarray) -> dict[tuple[int, int, int], dict[str, Any]]:
    sx, sy, _ = voxel_matrix.shape
    columns: dict[tuple[int, int, int], dict[str, Any]] = {}
    for x in range(0, sx - 1, 2):
        for y in range(0, sy - 1, 2):
            sub = voxel_matrix[x : x + 2, y : y + 2, :]
            occupancy = np.sum(sub > 0, axis=(0, 1))
            filled = np.where(occupancy > 0)[0]
            if len(filled) == 0:
                continue
            for z_min, z_max in split_runs(filled):
                height = z_max - z_min + 1
                if height < 2:
                    continue
                segment_vals = voxel_segment[x : x + 2, y : y + 2, z_min : z_max + 1].flatten()
                segment_vals = segment_vals[segment_vals > 0]
                segment_id = int(Counter(segment_vals).most_common(1)[0][0]) if len(segment_vals) else 1
                columns[(x, y, int(z_min))] = {
                    "z_min": int(z_min),
                    "height": int(height),
                    "segment_id": segment_id,
                }
    return columns


def split_runs(values: np.ndarray) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start = prev = int(values[0])
    for value in values[1:]:
        value = int(value)
        if value != prev + 1:
            runs.append((start, prev))
            start = value
        prev = value
    runs.append((start, prev))
    return runs


def generate_sequences_for_height(target_height: int) -> list[list[int]]:
    results: list[list[int]] = []

    def backtrack(remaining: int, seq: list[int]) -> None:
        if remaining == 0:
            results.append(seq.copy())
            return
        for height in BLOCK_HEIGHTS:
            if height <= remaining:
                seq.append(height)
                backtrack(remaining - height, seq)
                seq.pop()

    backtrack(target_height, [])
    return results or [[target_height]]


def assign_sequences_with_stagger(columns: dict[tuple[int, int, int], dict[str, Any]]) -> dict[tuple[int, int], list[int]]:
    max_height = max(c["height"] for c in columns.values())
    sequences_by_height = {h: generate_sequences_for_height(h) for h in range(2, max_height + 1)}
    assigned: dict[tuple[int, int], list[int]] = {}

    for x, y, z_min in sorted(columns.keys(), key=lambda k: (k[1], k[0], k[2])):
        height = columns[(x, y, z_min)]["height"]
        best_seq = sequences_by_height[height][0]
        best_score = -1e9
        neighbors = [assigned[n] for n in [(x - 2, y), (x, y - 2)] if n in assigned]
        for seq in sequences_by_height[height]:
            score = -len(seq) * 0.1
            seams = internal_seams(seq)
            for neighbor in neighbors:
                neighbor_seams = internal_seams(neighbor)
                score -= 20 * len(seams & neighbor_seams)
                score += len(seams - neighbor_seams)
            if score > best_score:
                best_score = score
                best_seq = seq
        assigned[(x, y)] = best_seq
    return assigned


def reoptimize_sequences(
    columns: dict[tuple[int, int, int], dict[str, Any]],
    assigned_sequences: dict[tuple[int, int], list[int]],
    max_yellow_blocks: int | None = None,
) -> dict[tuple[int, int], list[int]]:
    max_height = max(c["height"] for c in columns.values())
    sequences_by_height = {h: generate_sequences_for_height(h) for h in range(2, max_height + 1)}
    optimized: dict[tuple[int, int], list[int]] = {}
    yellow_used = 0

    for x, y in sorted(assigned_sequences.keys(), key=lambda k: (k[1], k[0])):
        height = sum(assigned_sequences[(x, y)])
        neighbors = [
            optimized.get(n, assigned_sequences.get(n))
            for n in [(x - 2, y), (x + 2, y), (x, y - 2), (x, y + 2)]
            if n in assigned_sequences
        ]
        best_seq = assigned_sequences[(x, y)]
        best_score = -1e9
        for seq in sequences_by_height[height]:
            score = -len(seq) * 0.5
            seams = internal_seams(seq)
            for neighbor in neighbors:
                if not neighbor:
                    continue
                neighbor_seams = internal_seams(neighbor)
                score -= 5 * len(seams & neighbor_seams)
                score += len(seams - neighbor_seams)
            for block_height in seq:
                score += {4: 8, 3: 3, 2: -4}.get(block_height, -10)
            if max_yellow_blocks is not None and yellow_used + seq.count(4) > max_yellow_blocks:
                score -= 10000
            if score > best_score:
                best_score = score
                best_seq = seq
        optimized[(x, y)] = best_seq
        yellow_used += best_seq.count(4)
    return optimized


def internal_seams(seq: list[int]) -> set[int]:
    seams = set()
    z = 0
    for height in seq[:-1]:
        z += height
        seams.add(z)
    return seams


def build_blocks_from_assigned_sequences(
    columns: dict[tuple[int, int, int], dict[str, Any]],
    assigned_sequences: dict[tuple[int, int], list[int]],
) -> list[BlockInstance]:
    blocks: list[BlockInstance] = []
    block_id = 1
    for x, y, z in sorted(columns.keys(), key=lambda k: (k[1], k[0], k[2])):
        seq = assigned_sequences.get((x, y))
        if seq is None:
            continue
        current_z = z
        for height in seq:
            block = BlockInstance(
                position=(x, y, current_z),
                size=(2, 2, height),
                segment_id=int(columns[(x, y, z)]["segment_id"]),
                block_id=block_id,
            )
            blocks.append(block)
            block_id += 1
            current_z += height
    return blocks


def block_inventory_summary(blocks: list[BlockInstance]) -> list[dict[str, Any]]:
    counts = Counter(block.size for block in blocks)
    rows = []
    for size, count in sorted(counts.items()):
        rows.append(
            {
                "piece": f"{size[0]}x{size[1]}x{size[2]} block",
                "color": BLOCK_TYPE_COLORS.get(size[2], "Unknown"),
                "quantity": count,
            }
        )
    return rows


def serialize_blocks(blocks: list[BlockInstance]) -> list[dict[str, Any]]:
    return [
        {
            "block_id": block.block_id,
            "position": list(block.position),
            "size": list(block.size),
            "segment_id": block.segment_id,
            "rotation": block.rotation,
            "category": block.category,
            "connector_type": block.connector_type,
        }
        for block in blocks
    ]
