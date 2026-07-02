"""Physical connectivity checks for notebook-derived BrickSmart blocks."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

import numpy as np

from build3d.block_decomposer import BlockInstance, FaceType
from build3d.csp_solver import DIRECTIONS, build_block_grid


def build_connectivity_report(blocks: list[BlockInstance], grid_size: int) -> dict[str, Any]:
    grid = build_block_grid(blocks, grid_size)
    connections = enumerate_block_interfaces(blocks, grid, grid_size)
    graph = graph_from_valid_connections(connections)
    components = connected_components(blocks, graph)
    degrees = {str(block.block_id): len(graph.get(block.block_id, set())) for block in blocks}
    bridge_blocks = articulation_points(blocks, graph)
    invalid_count = sum(1 for row in connections if not row["valid"])
    largest = max((len(component) for component in components), default=0)

    return {
        "is_fully_connected": len(components) <= 1 if blocks else False,
        "component_count": len(components),
        "largest_component_size": largest,
        "disconnected_block_count": max(len(blocks) - largest, 0),
        "invalid_interface_count": invalid_count,
        "bridge_block_count": len(bridge_blocks),
        "bridge_blocks": bridge_blocks,
        "attachment_degrees": degrees,
        "components": components,
        "connections": connections,
    }


def enumerate_block_interfaces(
    blocks: list[BlockInstance],
    grid: np.ndarray,
    grid_size: int,
) -> list[dict[str, Any]]:
    lookup = {block.block_id: block for block in blocks}
    seen: set[tuple[int, int, str]] = set()
    rows: list[dict[str, Any]] = []
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
            key = (min(block.block_id, neighbor_id), max(block.block_id, neighbor_id), face)
            reverse_key = (key[0], key[1], opposite_face)
            if key in seen or reverse_key in seen:
                continue
            seen.add(key)
            neighbor = lookup[neighbor_id]
            face_a = dominant_face_type(block.faces.get(face, []))
            face_b = dominant_face_type(neighbor.faces.get(opposite_face, []))
            classification = classify_interface(face_a, face_b)
            rows.append(
                {
                    "block_a": block.block_id,
                    "block_b": neighbor_id,
                    "segment_a": block.segment_id,
                    "segment_b": neighbor.segment_id,
                    "face_a": face,
                    "face_b": opposite_face,
                    "face_type_a": face_a.name.lower(),
                    "face_type_b": face_b.name.lower(),
                    "valid": classification["valid"],
                    "attachment": classification["attachment"],
                    "reason": classification["reason"],
                }
            )
    return rows


def dominant_face_type(face: list[list[FaceType]]) -> FaceType:
    values = [item for row in face for item in row]
    if not values:
        return FaceType.NONE
    male = values.count(FaceType.MALE)
    female = values.count(FaceType.FEMALE)
    if male > female:
        return FaceType.MALE
    if female > male:
        return FaceType.FEMALE
    return FaceType.NONE


def classify_interface(a: FaceType, b: FaceType) -> dict[str, Any]:
    if (a == FaceType.MALE and b == FaceType.FEMALE) or (a == FaceType.FEMALE and b == FaceType.MALE):
        return {"valid": True, "attachment": "secure", "reason": "male/female attachment"}
    if a == FaceType.MALE and b == FaceType.MALE:
        return {"valid": False, "attachment": "conflict", "reason": "male/male faces conflict"}
    return {
        "valid": True,
        "attachment": "connector_or_flat_contact",
        "reason": "requires connector or flat contact confirmation",
    }


def graph_from_valid_connections(connections: list[dict[str, Any]]) -> dict[int, set[int]]:
    graph: dict[int, set[int]] = defaultdict(set)
    for row in connections:
        if not row.get("valid"):
            continue
        a = int(row["block_a"])
        b = int(row["block_b"])
        graph[a].add(b)
        graph[b].add(a)
    return graph


def connected_components(blocks: list[BlockInstance], graph: dict[int, set[int]]) -> list[list[int]]:
    visited: set[int] = set()
    components: list[list[int]] = []
    for block in blocks:
        if block.block_id in visited:
            continue
        queue = deque([block.block_id])
        visited.add(block.block_id)
        component: list[int] = []
        while queue:
            block_id = queue.popleft()
            component.append(block_id)
            for neighbor in graph.get(block_id, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        components.append(sorted(component))
    return sorted(components, key=len, reverse=True)


def articulation_points(blocks: list[BlockInstance], graph: dict[int, set[int]]) -> list[int]:
    block_ids = {block.block_id for block in blocks}
    bridges: list[int] = []
    base_count = len(connected_components(blocks, graph))
    for removed in block_ids:
        remaining = [block for block in blocks if block.block_id != removed]
        reduced_graph = {
            node: {neighbor for neighbor in neighbors if neighbor != removed}
            for node, neighbors in graph.items()
            if node != removed
        }
        if len(connected_components(remaining, reduced_graph)) > base_count:
            bridges.append(removed)
    return bridges
