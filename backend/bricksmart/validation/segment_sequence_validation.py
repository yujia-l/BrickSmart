"""Segment-sequence validation helpers.

This module verifies that segment assemblies and joins follow the expected
ordering and dependency constraints.
"""

from __future__ import annotations

from collections import defaultdict

from bricksmart.planning.build_order import blocks_face_touch
from bricksmart.planning.models import Placement
from bricksmart.planning.voxel_models import SelectedVoxelBlock


def validate_segment_sequence(
    *,
    selected_blocks: list[SelectedVoxelBlock],
    placements: list[Placement],
) -> dict[str, object]:
    """Validate segment sequence.
    
    :param selected_blocks: The selected blocks value.
    :type selected_blocks: list[SelectedVoxelBlock]
    :param placements: The placements value.
    :type placements: list[Placement]
    :returns: The result produced by the function.
    :rtype: dict[str, object]
    """
    selected_by_id = {
        f"part_{selected.selection_index:03d}": selected for selected in selected_blocks
    }
    ordered = sorted(placements, key=lambda part: part.step or 0)
    failures: list[str] = []
    segment_runs: list[str] = []
    ranges: dict[str, list[int]] = defaultdict(list)
    prior: list[Placement] = []
    rows: list[dict[str, object]] = []

    last_segment: str | None = None
    closed_segments: set[str] = set()
    for placement in ordered:
        segment = placement.segment_id or "unassigned"
        ranges[segment].append(int(placement.step or 0))
        if segment != last_segment:
            if last_segment is not None:
                closed_segments.add(last_segment)
            if segment in closed_segments:
                failures.append(
                    f"Segment {segment!r} appears in more than one build phase"
                )
            segment_runs.append(segment)
            last_segment = segment

        selected = selected_by_id[placement.part_id]
        contacts = [
            earlier.part_id
            for earlier in prior
            if blocks_face_touch(selected, selected_by_id[earlier.part_id])
        ]
        phase_start = len(ranges[segment]) == 1
        valid_contact = not prior or bool(contacts)
        if not valid_contact:
            failures.append(
                f"Step {placement.step} ({placement.part_id}) has no prior face contact"
            )
        if phase_start and prior:
            cross_segment_contacts = [
                earlier.part_id
                for earlier in prior
                if earlier.segment_id != segment
                and blocks_face_touch(selected, selected_by_id[earlier.part_id])
            ]
            if not cross_segment_contacts:
                failures.append(
                    f"Segment {segment!r} begins at step {placement.step} without a join "
                    "to an already completed segment"
                )
        else:
            cross_segment_contacts = []

        rows.append(
            {
                "step": placement.step,
                "part_id": placement.part_id,
                "segment_id": segment,
                "segment_step": placement.metadata.get("segment_step"),
                "phase_start": phase_start,
                "contacts_prior_part_ids": contacts,
                "cross_segment_join_contacts": cross_segment_contacts,
                "status": "PASS" if valid_contact else "FAIL_NO_PRIOR_FACE_CONTACT",
            }
        )
        prior.append(placement)

    step_ranges = {
        segment: {"start_step": min(steps), "end_step": max(steps), "step_count": len(steps)}
        for segment, steps in ranges.items()
    }
    for segment, data in step_ranges.items():
        expected = list(range(data["start_step"], data["end_step"] + 1))
        if ranges[segment] != expected:
            failures.append(f"Segment {segment!r} steps are not contiguous")

    return {
        "status": "PASS" if not failures else "FAIL_SEGMENT_SEQUENCE",
        "segment_order": segment_runs,
        "segment_count": len(segment_runs),
        "step_ranges": step_ranges,
        "steps": rows,
        "failures": failures,
    }
