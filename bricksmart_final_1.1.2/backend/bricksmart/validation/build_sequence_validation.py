from __future__ import annotations

from bricksmart.planning.build_order import blocks_face_touch
from bricksmart.planning.models import Placement
from bricksmart.planning.voxel_models import SelectedVoxelBlock


def validate_build_sequence(
    *,
    selected_blocks: list[SelectedVoxelBlock],
    placements: list[Placement],
) -> dict[str, object]:
    selected_by_id = {
        f"part_{selected.selection_index:03d}": selected for selected in selected_blocks
    }
    prior: list[tuple[str, SelectedVoxelBlock]] = []
    rows: list[dict[str, object]] = []
    failures: list[str] = []

    for placement in sorted(placements, key=lambda part: part.step or 0):
        selected = selected_by_id[placement.part_id]
        contacts = [
            part_id
            for part_id, earlier in prior
            if blocks_face_touch(selected, earlier)
        ]
        valid = not prior or bool(contacts)
        if not valid:
            failures.append(
                f"Step {placement.step} ({placement.part_id}) has no face contact with prior steps"
            )
        rows.append(
            {
                "step": placement.step,
                "part_id": placement.part_id,
                "block_type": placement.block_type,
                "segment_id": placement.segment_id,
                "contacts_prior_count": len(contacts),
                "contacts_prior_part_ids": contacts,
                "status": "PASS" if valid else "FAIL_NO_PRIOR_FACE_CONTACT",
            }
        )
        prior.append((placement.part_id, selected))

    return {
        "status": "PASS" if not failures else "FAIL_BUILD_SEQUENCE",
        "step_count": len(rows),
        "steps": rows,
        "failures": failures,
    }
