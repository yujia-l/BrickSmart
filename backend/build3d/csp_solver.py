"""CSP-style block rotation optimization from the notebook."""

from __future__ import annotations

from collections import defaultdict, deque

import numpy as np

from build3d.block_decomposer import BLOCK_FACE_TEMPLATES, BlockInstance, FaceType

DIRECTIONS = {
    "+X": (1, 0, 0, "-X"),
    "-X": (-1, 0, 0, "+X"),
    "+Y": (0, 1, 0, "-Y"),
    "-Y": (0, -1, 0, "+Y"),
    "+Z": (0, 0, 1, "-Z"),
    "-Z": (0, 0, -1, "+Z"),
}


def build_block_grid(blocks: list[BlockInstance], grid_size: int) -> np.ndarray:
    grid = -np.ones((grid_size, grid_size, grid_size), dtype=int)
    for block in blocks:
        x0, y0, z0 = block.position
        dx, dy, dz = block.size
        grid[x0 : x0 + dx, y0 : y0 + dy, z0 : z0 + dz] = block.block_id
    return grid


def score_block_rotation(block: BlockInstance, blocks: list[BlockInstance], grid: np.ndarray, grid_size: int, rotation: int) -> int:
    faces = block.faces
    if rotation != block.rotation:
        faces = block.rotate_faces(BLOCK_FACE_TEMPLATES[block.size], rotation)
    lookup = {b.block_id: b for b in blocks}
    score = 0
    x0, y0, z0 = block.position
    dx, dy, dz = block.size

    for face, (dx_off, dy_off, dz_off, opposite_face) in DIRECTIONS.items():
        nx = x0 + (dx_off > 0) * dx + (dx_off < 0) * -1
        ny = y0 + (dy_off > 0) * dy + (dy_off < 0) * -1
        nz = z0 + (dz_off > 0) * dz + (dz_off < 0) * -1
        if not (0 <= nx < grid_size and 0 <= ny < grid_size and 0 <= nz < grid_size):
            continue
        neighbor_id = int(grid[nx, ny, nz])
        if neighbor_id == -1 or neighbor_id == block.block_id:
            continue
        neighbor = lookup[neighbor_id]
        face_block = np.asarray(faces[face], dtype=object)
        face_neighbor = np.asarray(neighbor.faces[opposite_face], dtype=object)
        if FaceType.MALE in face_block and FaceType.FEMALE in face_neighbor:
            score += 10
        elif FaceType.FEMALE in face_block and FaceType.MALE in face_neighbor:
            score += 10
        elif FaceType.MALE in face_block and FaceType.MALE in face_neighbor:
            score -= 1000
        elif FaceType.FEMALE in face_block and FaceType.FEMALE in face_neighbor:
            score -= 100
    return score


def build_block_graph(blocks: list[BlockInstance], grid: np.ndarray, grid_size: int) -> dict[int, set[int]]:
    graph: dict[int, set[int]] = defaultdict(set)
    lookup = {b.block_id: b for b in blocks}
    for block in blocks:
        x0, y0, z0 = block.position
        dx, dy, dz = block.size
        for face, (dx_off, dy_off, dz_off, opposite_face) in DIRECTIONS.items():
            nx = x0 + (dx_off > 0) * dx + (dx_off < 0) * -1
            ny = y0 + (dy_off > 0) * dy + (dy_off < 0) * -1
            nz = z0 + (dz_off > 0) * dz + (dz_off < 0) * -1
            if not (0 <= nx < grid_size and 0 <= ny < grid_size and 0 <= nz < grid_size):
                continue
            neighbor_id = int(grid[nx, ny, nz])
            if neighbor_id == -1 or neighbor_id == block.block_id:
                continue
            neighbor = lookup[neighbor_id]
            face_a = np.asarray(block.faces[face], dtype=object)[0, 0]
            face_b = np.asarray(neighbor.faces[opposite_face], dtype=object)[0, 0]
            attached = (face_a == FaceType.MALE and face_b == FaceType.FEMALE) or (
                face_a == FaceType.FEMALE and face_b == FaceType.MALE
            )
            if attached:
                graph[block.block_id].add(neighbor_id)
                graph[neighbor_id].add(block.block_id)
    return graph


def compute_connected_components(blocks: list[BlockInstance], grid: np.ndarray, grid_size: int) -> list[list[int]]:
    graph = build_block_graph(blocks, grid, grid_size)
    visited = set()
    components: list[list[int]] = []
    for block in blocks:
        if block.block_id in visited:
            continue
        queue = deque([block.block_id])
        visited.add(block.block_id)
        component = []
        while queue:
            block_id = queue.popleft()
            component.append(block_id)
            for neighbor_id in graph.get(block_id, set()):
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append(neighbor_id)
        components.append(component)
    return components


def connectivity_energy(blocks: list[BlockInstance], grid: np.ndarray, grid_size: int) -> int:
    components = compute_connected_components(blocks, grid, grid_size)
    if len(components) <= 1:
        return 0
    sizes = sorted([len(comp) for comp in components], reverse=True)
    disconnected = sum(sizes[1:])
    return disconnected * disconnected + 10 * (len(components) - 1)


def score_block_rotation_csp(block: BlockInstance, blocks: list[BlockInstance], grid: np.ndarray, grid_size: int, rotation: int) -> int:
    original_rotation = block.rotation
    original_faces = block.faces
    block.set_rotation(rotation)
    local_score = score_block_rotation(block, blocks, grid, grid_size, rotation)
    energy = connectivity_energy(blocks, grid, grid_size)
    block.rotation = original_rotation
    block.faces = original_faces
    return local_score - energy


def optimize_block_rotations(blocks: list[BlockInstance], grid_size: int, max_iters: int = 10) -> list[BlockInstance]:
    if not blocks:
        return blocks
    grid = build_block_grid(blocks, grid_size)
    for _ in range(max_iters):
        changes = 0
        updates: dict[int, int] = {}
        for block in blocks:
            scores = {
                rotation: score_block_rotation_csp(block, blocks, grid, grid_size, rotation)
                for rotation in (0, 90, 180, 270)
            }
            best_rotation = max(scores, key=scores.get)
            if best_rotation != block.rotation:
                updates[block.block_id] = best_rotation
        for block in blocks:
            if block.block_id in updates:
                block.set_rotation(updates[block.block_id])
                changes += 1
        if changes == 0:
            break
        grid = build_block_grid(blocks, grid_size)
    return blocks
