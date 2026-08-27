"""Behavior-preserving validation helpers for row/column planning."""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from .geometry import (
    actual_block_face_type,
    block_bounds,
    block_contains_voxel,
    classify_face_types,
    coordinate_is_on_block_face,
    height_is_catalog_representable,
    positive_overlap,
    touching_face_geometry,
)


def locking_components_from_edges(block_ids, edges):
    """Return locking components from edges.
    
    :param block_ids: Identifiers for the block records.
    :param edges: The edges value.
    :returns: The result produced by the function.
    """
    adjacency = {
        int(block_id): set()
        for block_id in block_ids
    }

    for a, b in edges:
        a = int(a)
        b = int(b)

        if a in adjacency and b in adjacency:
            adjacency[a].add(b)
            adjacency[b].add(a)

    components = []
    visited = set()

    for start in sorted(adjacency):
        if start in visited:
            continue

        stack = [start]
        visited.add(start)
        component = []

        while stack:
            current = stack.pop()
            component.append(current)

            for neighbor in sorted(adjacency[current]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)

        components.append(sorted(component))

    return components


def contact_status_between_blocks(block_a, block_b):
    """Return the contact status between blocks value.
    
    :param block_a: The block a value.
    :param block_b: The block b value.
    :returns: The result produced by the function.
    """
    geometry = touching_face_geometry(block_a, block_b)
    if geometry is None:
        return None
    if geometry["geometry_status"] == "geometric_overlap_conflict":
        return {
            **geometry,
            "contact_status": "geometric_overlap_conflict",
        }
    face_type_a = actual_block_face_type(
        block_a,
        geometry["face_a"],
    )
    face_type_b = actual_block_face_type(
        block_b,
        geometry["face_b"],
    )
    return {
        **geometry,
        "face_type_a": face_type_a,
        "face_type_b": face_type_b,
        "contact_status": classify_face_types(
            face_type_a,
            face_type_b,
        ),
    }


def embedded_connector_candidate_validation(
    candidate,
    segment_blocks_by_id,
):
    """Return the embedded connector candidate validation value.
    
    :param candidate: The candidate value.
    :param segment_blocks_by_id: Identifier for the segment blocks by.
    :returns: The result produced by the function.
    """
    cells_a = {
        tuple(
            int(
                value
            )
            for value in coordinate
        )
        for coordinate in candidate.get(
            "embedded_anchor_cells_a",
            [],
        )
    }
    cells_b = {
        tuple(
            int(
                value
            )
            for value in coordinate
        )
        for coordinate in candidate.get(
            "embedded_anchor_cells_b",
            [],
        )
    }
    segment_a = int(
        candidate[
            "segment_a"
        ]
    )
    segment_b = int(
        candidate[
            "segment_b"
        ]
    )

    covered_a = {
        coordinate
        for coordinate in cells_a
        if any(
            block_contains_voxel(
                block,
                coordinate,
            )
            for block in (
                segment_blocks_by_id.get(
                    segment_a,
                    [],
                )
            )
        )
    }
    covered_b = {
        coordinate
        for coordinate in cells_b
        if any(
            block_contains_voxel(
                block,
                coordinate,
            )
            for block in (
                segment_blocks_by_id.get(
                    segment_b,
                    [],
                )
            )
        )
    }

    valid = bool(
        len(
            cells_a
        )
        == 4
        and len(
            cells_b
        )
        == 4
        and covered_a
        == cells_a
        and covered_b
        == cells_b
        and int(
            candidate.get(
                "unrelated_overlap",
                0,
            )
        )
        == 0
    )
    return {
        **candidate,
        "postbuild_locks_to_segment_a": bool(
            valid
        ),
        "postbuild_locks_to_segment_b": bool(
            valid
        ),
        "postbuild_lock_area_segment_a": int(
            len(
                covered_a
            )
        ),
        "postbuild_lock_area_segment_b": int(
            len(
                covered_b
            )
        ),
        "postbuild_overlap_conflict_count": 0,
        "postbuild_overlap_block_ids": "",
        "postbuild_validation_mode": (
            "embedded_anchor_layer"
        ),
        "postbuild_valid": bool(
            valid
        ),
    }


def validate_required_embedded_connectors(
    candidates_df,
    segment_blocks_by_id,
):
    """Validate required embedded connectors.
    
    :param candidates_df: DataFrame containing candidates records.
    :param segment_blocks_by_id: Identifier for the segment blocks by.
    :returns: The result produced by the function.
    """
    return pd.DataFrame(
        [
            embedded_connector_candidate_validation(
                row.to_dict(),
                segment_blocks_by_id,
            )
            for _, row in (
                candidates_df.iterrows()
            )
        ]
    )


def validate_functional_block(
    block,
    segment_blocks_by_id,
):
    """Validate functional block.
    
    :param block: Block record used by the operation.
    :param segment_blocks_by_id: Identifier for the segment blocks by.
    :returns: The result produced by the function.
    """
    anchor_id = int(
        block.anchor_segment_id
    )
    source_overlap = int(
        getattr(
            block,
            "source_overlap_voxels",
            0,
        )
    )
    anchor_contact = int(
        getattr(
            block,
            "anchor_contact_area",
            0,
        )
    )
    if (
        source_overlap > 0
        and anchor_contact > 0
    ):
        return {
            "physical_target_id": (
                block.physical_target_id
            ),
            "functional_block_id": int(
                block.block_id
            ),
            "anchor_segment_id": (
                anchor_id
            ),
            "lock_area": int(
                anchor_contact
            ),
            "valid": True,
        }

    lock_area = 0
    for structural_block in (
        segment_blocks_by_id.get(
            anchor_id,
            [],
        )
    ):
        contact = (
            contact_status_between_blocks(
                block,
                structural_block,
            )
        )
        if (
            contact is not None
            and contact[
                "contact_status"
            ]
            == "male_to_female_lock"
        ):
            lock_area += int(
                contact[
                    "overlap_area"
                ]
            )
    return {
        "physical_target_id": (
            block.physical_target_id
        ),
        "functional_block_id": int(
            block.block_id
        ),
        "anchor_segment_id": (
            anchor_id
        ),
        "lock_area": int(
            lock_area
        ),
        "valid": bool(
            lock_area > 0
        ),
    }


def reservation_normalize_strategy(value, default="soft"):
    """Return reservation normalize strategy.
    
    :param value: Value used by the operation.
    :param default: Fallback value used when no explicit value is available.
    :returns: The result produced by the function.
    """
    text = str(value or default).strip().lower()
    if text not in {"hard", "soft", "none"}:
        raise ValueError(f"Unsupported Reservation reservation strategy: {value}")
    return text


def reservation_final_reservation_audit(segment_results, requirements_df):
    """Return reservation final reservation audit.
    
    :param segment_results: The segment results value.
    :param requirements_df: DataFrame containing requirements records.
    :returns: The result produced by the function.
    """
    if requirements_df is None or requirements_df.empty:
        return pd.DataFrame(columns=[
            "requirement_group_id", "reservation_strategy", "segment_id",
            "reservation_owner_id", "satisfied", "status",
        ])

    evaluation_rows = [
        row
        for result in segment_results
        for row in result.get("connector_face_requirement_audit", [])
    ]
    evaluation_by_group = defaultdict(list)
    for row in evaluation_rows:
        evaluation_by_group[str(row.get("requirement_group_id"))].append(row)

    audit_rows = []
    for group_id, group in requirements_df.groupby("requirement_group_id", sort=True):
        strategy = reservation_normalize_strategy(group.iloc[0].get("reservation_strategy", "hard"))
        evaluated = evaluation_by_group.get(str(group_id), [])
        satisfied = any(
            bool(row.get("group_satisfied", row.get("alternative_satisfied", row.get("satisfied", False))))
            for row in evaluated
        )
        status = (
            "fulfilled" if satisfied
            else "unresolved_required" if strategy == "hard"
            else "needs_review" if strategy == "soft"
            else "not_required"
        )
        audit_rows.append({
            "requirement_group_id": str(group_id),
            "reservation_strategy": strategy,
            "reservation_scope": group.iloc[0].get("reservation_scope"),
            "reservation_owner_id": group.iloc[0].get("reservation_owner_id"),
            "segment_id": int(group.iloc[0]["segment_id"]),
            "alternative_count": int(len(group)),
            "evaluated_alternative_count": int(len(evaluated)),
            "satisfied": bool(satisfied),
            "status": status,
            "strategy_reason_code": group.iloc[0].get("strategy_reason_code"),
        })
    return pd.DataFrame(audit_rows)


def catalog_run_audit(
    mask,
    allowed_heights,
):
    """Return catalog run audit.
    
    :param mask: The mask value.
    :param allowed_heights: The allowed heights value.
    :returns: The result produced by the function.
    """
    invalid_runs = []
    shape = mask.shape

    for x in range(
        0,
        shape[0] - 1,
        2,
    ):
        for y in range(
            0,
            shape[1] - 1,
            2,
        ):
            occupied = [
                bool(mask[x, y, z])
                for z in range(
                    shape[2]
                )
            ]
            start = None
            for z, value in enumerate(
                occupied + [False]
            ):
                if (
                    value
                    and start is None
                ):
                    start = z
                elif (
                    not value
                    and start is not None
                ):
                    height = z - start
                    if not (
                        height_is_catalog_representable(
                            height,
                            allowed_heights,
                        )
                    ):
                        invalid_runs.append({
                            "cell_x": x,
                            "cell_y": y,
                            "z_min": start,
                            "height": height,
                        })
                    start = None

    return invalid_runs


__all__ = [
    'locking_components_from_edges',
    'embedded_connector_candidate_validation',
    'validate_required_embedded_connectors',
    'contact_status_between_blocks',
    'validate_functional_block',
    'reservation_normalize_strategy',
    'reservation_final_reservation_audit',
    'catalog_run_audit',
]
