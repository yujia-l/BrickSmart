"""Generic build-order sequencing helpers.

This module orders placed blocks and assemblies into human-reviewable build
steps while preserving connectivity and dependencies.
"""

from __future__ import annotations

from collections import deque

from bricksmart.planning.models import Placement
from bricksmart.planning.voxel_models import SelectedVoxelBlock


def blocks_face_touch(left: SelectedVoxelBlock, right: SelectedVoxelBlock) -> bool:
    """Return whether blocks face touch.
    
    :param left: The left value.
    :type left: SelectedVoxelBlock
    :param right: The right value.
    :type right: SelectedVoxelBlock
    :returns: The result produced by the function.
    :rtype: bool
    """
    a_origin = left.candidate.origin
    a_dims = left.candidate.dimensions
    b_origin = right.candidate.origin
    b_dims = right.candidate.dimensions
    a_end = tuple(a_origin[index] + a_dims[index] for index in range(3))
    b_end = tuple(b_origin[index] + b_dims[index] for index in range(3))
    for axis in range(3):
        if a_end[axis] == b_origin[axis] or b_end[axis] == a_origin[axis]:
            other_axes = [index for index in range(3) if index != axis]
            if all(
                min(a_end[index], b_end[index])
                - max(a_origin[index], b_origin[index])
                > 0
                for index in other_axes
            ):
                return True
    return False


def contact_graph(blocks: list[SelectedVoxelBlock]) -> dict[int, set[int]]:
    """Return the contact graph value.
    
    :param blocks: Block records used by the operation.
    :type blocks: list[SelectedVoxelBlock]
    :returns: The result produced by the function.
    :rtype: dict[int, set[int]]
    """
    graph = {index: set() for index in range(len(blocks))}
    for left in range(len(blocks)):
        for right in range(left):
            if blocks_face_touch(blocks[left], blocks[right]):
                graph[left].add(right)
                graph[right].add(left)
    return graph


def connected_components(graph: dict[int, set[int]]) -> list[list[int]]:
    """Return the connected components value.
    
    :param graph: The graph value.
    :type graph: dict[int, set[int]]
    :returns: The result produced by the function.
    :rtype: list[list[int]]
    """
    remaining = set(graph)
    components: list[list[int]] = []
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        component: list[int] = []
        queue = deque([seed])
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in sorted(graph[current]):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
        components.append(component)
    return components


def assign_build_steps(blocks: list[SelectedVoxelBlock]) -> list[Placement]:
    """Assign build steps.
    
    :param blocks: Block records used by the operation.
    :type blocks: list[SelectedVoxelBlock]
    :returns: The result produced by the function.
    :rtype: list[Placement]
    """
    if not blocks:
        return []
    graph = contact_graph(blocks)
    unvisited = set(graph)
    ordered: list[int] = []

    while unvisited:
        root = min(
            unvisited,
            key=lambda index: (
                blocks[index].candidate.origin[2],
                blocks[index].candidate.origin[1],
                blocks[index].candidate.origin[0],
                blocks[index].selection_index,
            ),
        )
        queue = deque([root])
        unvisited.remove(root)
        while queue:
            current = queue.popleft()
            ordered.append(current)
            neighbors = sorted(
                graph[current] & unvisited,
                key=lambda index: (
                    blocks[index].candidate.origin[2],
                    -len(graph[index]),
                    blocks[index].selection_index,
                ),
            )
            for neighbor in neighbors:
                unvisited.remove(neighbor)
                queue.append(neighbor)

    return [blocks[index].to_placement(step=step) for step, index in enumerate(ordered, start=1)]
