"""Segment-aware build-order sequencing helpers.

This module orders model segments, connectors, and subassemblies into a stable
construction sequence.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from bricksmart.planning.build_order import blocks_face_touch, contact_graph
from bricksmart.planning.models import Placement
from bricksmart.planning.voxel_models import SelectedVoxelBlock


@dataclass(frozen=True)
class SegmentBuildOrder:
    placements: list[Placement]
    segment_order: list[str]
    step_ranges: dict[str, tuple[int, int]]
    join_steps: list[dict[str, object]]


def _part_id(block: SelectedVoxelBlock) -> str:
    """Return the part id value.
    
    :param block: Block record used by the operation.
    :type block: SelectedVoxelBlock
    :returns: The result produced by the function.
    :rtype: str
    """
    return f"part_{block.selection_index:03d}"


def _block_sort_key(block: SelectedVoxelBlock) -> tuple[int, int, int, int]:
    """Return block sort key.
    
    :param block: Block record used by the operation.
    :type block: SelectedVoxelBlock
    :returns: The result produced by the function.
    :rtype: tuple[int, int, int, int]
    """
    x, y, z = block.candidate.origin
    return (z, y, x, block.selection_index)


def _group_indices(blocks: list[SelectedVoxelBlock]) -> dict[str, list[int]]:
    """Group indices.
    
    :param blocks: Block records used by the operation.
    :type blocks: list[SelectedVoxelBlock]
    :returns: The result produced by the function.
    :rtype: dict[str, list[int]]
    """
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, block in enumerate(blocks):
        grouped[block.candidate.dominant_segment].append(index)
    return dict(grouped)


def _segment_contact_graph(
    blocks: list[SelectedVoxelBlock],
    graph: dict[int, set[int]],
    grouped: dict[str, list[int]],
) -> dict[str, set[str]]:
    """Return segment contact graph.
    
    :param blocks: Block records used by the operation.
    :type blocks: list[SelectedVoxelBlock]
    :param graph: The graph value.
    :type graph: dict[int, set[int]]
    :param grouped: The grouped value.
    :type grouped: dict[str, list[int]]
    :returns: The result produced by the function.
    :rtype: dict[str, set[str]]
    """
    result = {segment: set() for segment in grouped}
    for left, neighbors in graph.items():
        left_segment = blocks[left].candidate.dominant_segment
        for right in neighbors:
            right_segment = blocks[right].candidate.dominant_segment
            if left_segment != right_segment:
                result[left_segment].add(right_segment)
    return result


def _order_segment_blocks(
    *,
    segment: str,
    indices: list[int],
    blocks: list[SelectedVoxelBlock],
    graph: dict[int, set[int]],
    previously_built: set[int],
) -> list[int]:
    """Return the order segment blocks value.
    
    :param segment: Segment data used by the operation.
    :type segment: str
    :param indices: The indices value.
    :type indices: list[int]
    :param blocks: Block records used by the operation.
    :type blocks: list[SelectedVoxelBlock]
    :param graph: The graph value.
    :type graph: dict[int, set[int]]
    :param previously_built: The previously built value.
    :type previously_built: set[int]
    :returns: The result produced by the function.
    :rtype: list[int]
    """
    unvisited = set(indices)
    ordered: list[int] = []
    locally_built: set[int] = set()

    while unvisited:
        if not ordered and not previously_built:
            root = min(unvisited, key=lambda index: _block_sort_key(blocks[index]))
        else:
            attachable = [
                index
                for index in unvisited
                if graph[index] & (previously_built | locally_built)
            ]
            if not attachable:
                raise ValueError(
                    f"Segment {segment!r} cannot be built contiguously: a local component "
                    "has no face contact with the completed assembly"
                )
            root = min(
                attachable,
                key=lambda index: (
                    -len(graph[index] & previously_built),
                    -len(graph[index] & locally_built),
                    _block_sort_key(blocks[index]),
                ),
            )

        queue = deque([root])
        unvisited.remove(root)
        while queue:
            current = queue.popleft()
            ordered.append(current)
            locally_built.add(current)
            neighbors = sorted(
                graph[current] & unvisited & set(indices),
                key=lambda index: (
                    -len(graph[index] & (previously_built | locally_built)),
                    _block_sort_key(blocks[index]),
                ),
            )
            for neighbor in neighbors:
                unvisited.remove(neighbor)
                queue.append(neighbor)

    return ordered


def assign_segment_build_steps(
    blocks: list[SelectedVoxelBlock],
) -> SegmentBuildOrder:
    """Order blocks in contiguous segment phases while retaining face-contact buildability.

    Planning is global, but construction is local: once a segment begins, all selected
    blocks assigned to that segment are placed before the next segment starts.
    """

    if not blocks:
        return SegmentBuildOrder([], [], {}, [])

    graph = contact_graph(blocks)
    grouped = _group_indices(blocks)
    segment_graph = _segment_contact_graph(blocks, graph, grouped)

    anchor = min(
        grouped,
        key=lambda segment: (
            -len(segment_graph[segment]),
            -sum(
                1
                for index in grouped[segment]
                for neighbor in graph[index]
                if blocks[neighbor].candidate.dominant_segment != segment
            ),
            -len(grouped[segment]),
            min(_block_sort_key(blocks[index]) for index in grouped[segment]),
            segment,
        ),
    )

    remaining_segments = set(grouped)
    segment_order: list[str] = []
    ordered_indices: list[int] = []
    built_indices: set[int] = set()
    join_steps: list[dict[str, object]] = []

    current_segment = anchor
    while remaining_segments:
        if current_segment not in remaining_segments:
            reachable = [
                segment
                for segment in remaining_segments
                if any(neighbor in segment_order for neighbor in segment_graph[segment])
            ]
            if not reachable:
                raise ValueError(
                    "Selected segment modules do not form one connected segment graph"
                )
            current_segment = min(
                reachable,
                key=lambda segment: (
                    -sum(
                        1
                        for index in grouped[segment]
                        for neighbor in graph[index]
                        if neighbor in built_indices
                    ),
                    -len(grouped[segment]),
                    segment,
                ),
            )

        local_order = _order_segment_blocks(
            segment=current_segment,
            indices=grouped[current_segment],
            blocks=blocks,
            graph=graph,
            previously_built=built_indices,
        )

        if segment_order:
            first_index = local_order[0]
            prior_contacts = sorted(graph[first_index] & built_indices)
            join_steps.append(
                {
                    "segment_id": current_segment,
                    "joins_after_segment": blocks[prior_contacts[0]].candidate.dominant_segment,
                    "first_part_id": _part_id(blocks[first_index]),
                    "contact_part_ids": [_part_id(blocks[index]) for index in prior_contacts],
                }
            )

        segment_order.append(current_segment)
        remaining_segments.remove(current_segment)
        ordered_indices.extend(local_order)
        built_indices.update(local_order)
        current_segment = ""

    placements: list[Placement] = []
    step_ranges: dict[str, tuple[int, int]] = {}
    step = 1
    for segment_index, segment in enumerate(segment_order, start=1):
        segment_indices = [
            index
            for index in ordered_indices
            if blocks[index].candidate.dominant_segment == segment
        ]
        start = step
        for segment_step, index in enumerate(segment_indices, start=1):
            base = blocks[index].to_placement(step=step)
            metadata = dict(base.metadata)
            metadata.update(
                {
                    "segment_order_index": segment_index,
                    "segment_step": segment_step,
                    "segment_phase": f"segment_{segment_index:02d}_{segment}",
                }
            )
            placements.append(
                Placement(
                    part_id=base.part_id,
                    block_type=base.block_type,
                    segment_id=base.segment_id,
                    step=base.step,
                    metadata=metadata,
                )
            )
            step += 1
        step_ranges[segment] = (start, step - 1)

    for join in join_steps:
        segment = str(join["segment_id"])
        join["join_step"] = step_ranges[segment][0]

    return SegmentBuildOrder(
        placements=placements,
        segment_order=segment_order,
        step_ranges=step_ranges,
        join_steps=join_steps,
    )
