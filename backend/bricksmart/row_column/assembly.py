"""Assembly sequencing and report-preparation helpers."""

from __future__ import annotations

import copy
from collections import Counter, defaultdict, deque

import numpy as np
import pandas as pd


def reindex_segment_plan(
    planning_result,
    next_block_id,
    segment_id,
    segment_label,
):
    """Return the reindex segment plan value.
    
    :param planning_result: The planning result value.
    :param next_block_id: Identifier for the next block.
    :param segment_id: Identifier for the segment.
    :param segment_label: The segment label value.
    :returns: The result produced by the function.
    """
    blocks = planning_result["blocks"]
    mapping = {}
    for block in blocks:
        old_id = int(block.block_id)
        mapping[old_id] = int(next_block_id)
        block.block_id = int(next_block_id)
        block.source_segment_id = int(segment_id)
        block.segment_label = str(segment_label)
        block.subassembly_id = f"segment_{int(segment_id)}"
        block.block_role = "segment_structural"
        next_block_id += 1

    return planning_result, next_block_id


def parse_block_id_field(
    value,
):
    """Parse block id field.
    
    :param value: Value used by the operation.
    :returns: The computed result.
    """
    if value is None:
        return []
    if isinstance(
        value,
        (
            list,
            tuple,
            set,
            np.ndarray,
        ),
    ):
        return [
            int(item)
            for item in value
        ]
    if isinstance(
        value,
        (
            float,
            np.floating,
        ),
    ) and np.isnan(
        value
    ):
        return []

    text = str(
        value
    ).strip()
    if not text:
        return []

    return [
        int(token.strip())
        for token in text.split(",")
        if token.strip()
    ]


def remap_validation_block_ids_to_planning(
    validation,
    planning_result,
):
    """
    Align validation IDs with the globally reindexed planning blocks.
    """
    remapped = copy.deepcopy(
        validation
    )
    block_rows = remapped.get(
        "block_rows",
        [],
    )
    instruction_steps = planning_result.get(
        "instruction_steps",
        [],
    )

    mapping = {}
    for step_number, step in enumerate(
        instruction_steps,
        start=1,
    ):
        local_rows = sorted(
            [
                row
                for row in block_rows
                if int(
                    row.get(
                        "step",
                        -1,
                    )
                )
                == step_number
            ],
            key=lambda row: int(
                row.get(
                    "block_id",
                    0,
                )
            ),
        )
        global_blocks = sorted(
            list(
                step.get(
                    "blocks",
                    [],
                )
            ),
            key=lambda block: (
                int(
                    block.position[
                        0
                    ]
                ),
                int(
                    block.position[
                        2
                    ]
                ),
                int(
                    block.size[
                        2
                    ]
                ),
                int(
                    block.block_id
                ),
            ),
        )

        if len(
            local_rows
        ) != len(
            global_blocks
        ):
            raise RuntimeError(
                "Cannot align validation IDs for "
                f"step {step_number}: "
                f"{len(local_rows)} validation rows versus "
                f"{len(global_blocks)} planning blocks."
            )

        for local_row, global_block in zip(
            local_rows,
            global_blocks,
        ):
            mapping[
                int(
                    local_row[
                        "block_id"
                    ]
                )
            ] = int(
                global_block.block_id
            )

    if not mapping:
        return remapped

    def remap_id(
        value,
    ):
        """Return the remap id value.
        
        :param value: Value used by the operation.
        :returns: The result produced by the function.
        """
        return int(
            mapping.get(
                int(
                    value
                ),
                int(
                    value
                ),
            )
        )

    def remap_field(
        value,
    ):
        """Return the remap field value.
        
        :param value: Value used by the operation.
        :returns: The result produced by the function.
        """
        return format_block_id_field(
            [
                remap_id(
                    item
                )
                for item in parse_block_id_field(
                    value
                )
            ]
        )

    for row in remapped.get(
        "block_rows",
        [],
    ):
        row[
            "block_id"
        ] = remap_id(
            row[
                "block_id"
            ]
        )

    block_validation = {}
    for old_key, row in remapped.get(
        "block_validation",
        {},
    ).items():
        new_row = copy.deepcopy(
            row
        )
        new_id = remap_id(
            new_row.get(
                "block_id",
                old_key,
            )
        )
        new_row[
            "block_id"
        ] = new_id
        block_validation[
            str(
                new_id
            )
        ] = new_row
    remapped[
        "block_validation"
    ] = block_validation

    for row in remapped.get(
        "component_rows",
        [],
    ):
        for field in [
            "block_ids",
            "accepted_block_ids",
            "rejected_block_ids",
            "direct_conflict_block_ids",
        ]:
            row[
                field
            ] = remap_field(
                row.get(
                    field
                )
            )

    for row in remapped.get(
        "contact_rows",
        [],
    ):
        row[
            "block_a"
        ] = remap_id(
            row[
                "block_a"
            ]
        )
        row[
            "block_b"
        ] = remap_id(
            row[
                "block_b"
            ]
        )

    for field in [
        "accepted_before_by_step",
        "accepted_after_by_step",
    ]:
        remapped[
            field
        ] = {
            key: [
                remap_id(
                    value
                )
                for value in values
            ]
            for key, values in remapped.get(
                field,
                {},
            ).items()
        }

    for row in remapped.get(
        "step_rows",
        [],
    ):
        row[
            "accepted_block_ids"
        ] = remap_field(
            row.get(
                "accepted_block_ids"
            )
        )
        row[
            "rejected_block_ids"
        ] = remap_field(
            row.get(
                "rejected_block_ids"
            )
        )

    remapped[
        "id_remap"
    ] = {
        str(
            old_id
        ): int(
            new_id
        )
        for old_id, new_id in sorted(
            mapping.items()
        )
    }
    remapped[
        "id_namespace"
    ] = "global_final_block_ids"

    return remapped


def rebuild_instruction_steps_from_blocks(
    blocks,
    row_values=None,
):
    """Return the rebuild instruction steps from blocks value.
    
    :param blocks: Block records used by the operation.
    :param row_values: The row values value.
    :returns: The result produced by the function.
    """
    row_to_blocks = defaultdict(list)
    for block in blocks:
        row_to_blocks[int(block.position[1])].append(block)

    ordered_rows = (
        sorted(int(value) for value in row_values)
        if row_values is not None
        else sorted(row_to_blocks)
    )

    steps = []
    for row_value in ordered_rows:
        local_blocks = sorted(
            row_to_blocks.get(int(row_value), []),
            key=lambda block: (
                int(block.position[0]),
                int(block.position[2]),
                int(block.size[2]),
            ),
        )
        if not local_blocks:
            continue
        steps.append(
            {
                "row": int(row_value),
                "blocks": local_blocks,
            }
        )
    return steps


def connected_segment_graph(
    structural_segment_ids,
    valid_connector_rows,
):
    """Return the connected segment graph value.
    
    :param structural_segment_ids: Identifiers for the structural segment records.
    :param valid_connector_rows: The valid connector rows value.
    :returns: The result produced by the function.
    """
    adjacency = {
        int(segment_id): set()
        for segment_id in structural_segment_ids
    }
    for row in valid_connector_rows:
        if not row["valid"]:
            continue
        segment_a = int(row["segment_a"])
        segment_b = int(row["segment_b"])
        adjacency[segment_a].add(segment_b)
        adjacency[segment_b].add(segment_a)

    if not adjacency:
        return True, []
    start = next(iter(adjacency))
    visited = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for neighbor in adjacency[current]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return visited == set(adjacency), sorted(visited)


def direct_structural_join_tree(
    direct_contact_df,
    structural_segment_ids,
):
    """Return the direct structural join tree value.
    
    :param direct_contact_df: DataFrame containing direct contact records.
    :param structural_segment_ids: Identifiers for the structural segment records.
    :returns: The result produced by the function.
    """
    output_columns = [
        "interface_id",
        "connector_block_id",
        "segment_a",
        "segment_b",
        "locks_to_segment_a",
        "locks_to_segment_b",
        "lock_area_segment_a",
        "lock_area_segment_b",
        "contact_count",
        "join_mode",
        "valid",
    ]

    if direct_contact_df.empty:
        return (
            pd.DataFrame(
                columns=output_columns
            ),
            pd.DataFrame(),
        )

    lock_rows = direct_contact_df.loc[
        direct_contact_df[
            "contact_status"
        ].eq(
            "male_to_female_lock"
        )
    ].copy()

    grouped = {}
    for row in lock_rows.itertuples(
        index=False
    ):
        first, second = sorted(
            (
                int(
                    row.segment_a
                ),
                int(
                    row.segment_b
                ),
            )
        )
        entry = grouped.setdefault(
            (
                first,
                second,
            ),
            {
                "segment_a": first,
                "segment_b": second,
                "contact_count": 0,
                "lock_area": 0,
            },
        )
        entry[
            "contact_count"
        ] += 1
        entry[
            "lock_area"
        ] += int(
            row.overlap_area
        )

    candidate_rows = sorted(
        grouped.values(),
        key=lambda row: (
            -int(
                row[
                    "lock_area"
                ]
            ),
            int(
                row[
                    "segment_a"
                ]
            ),
            int(
                row[
                    "segment_b"
                ]
            ),
        ),
    )

    parent = {
        int(segment_id): int(segment_id)
        for segment_id in structural_segment_ids
    }

    def find(value):
        """Return the find value.
        
        :param value: Value used by the operation.
        :returns: The result produced by the function.
        """
        value = int(value)
        while parent[value] != value:
            parent[value] = parent[
                parent[value]
            ]
            value = parent[value]
        return value

    def union(first, second):
        """Return the union value.
        
        :param first: The first value.
        :param second: The second value.
        :returns: The result produced by the function.
        """
        root_first = find(first)
        root_second = find(second)
        if root_first == root_second:
            return False
        parent[root_second] = root_first
        return True

    selected_rows = []
    audit_rows = []

    for candidate in candidate_rows:
        selected = union(
            candidate[
                "segment_a"
            ],
            candidate[
                "segment_b"
            ],
        )
        audit_rows.append(
            {
                **candidate,
                "selected_for_join_tree": bool(
                    selected
                ),
            }
        )
        if not selected:
            continue

        selected_rows.append(
            {
                "interface_id": (
                    f"DJ_"
                    f"{int(candidate['segment_a']):03d}_"
                    f"{int(candidate['segment_b']):03d}"
                ),
                "connector_block_id": None,
                "segment_a": int(
                    candidate[
                        "segment_a"
                    ]
                ),
                "segment_b": int(
                    candidate[
                        "segment_b"
                    ]
                ),
                "locks_to_segment_a": True,
                "locks_to_segment_b": True,
                "lock_area_segment_a": int(
                    candidate[
                        "lock_area"
                    ]
                ),
                "lock_area_segment_b": int(
                    candidate[
                        "lock_area"
                    ]
                ),
                "contact_count": int(
                    candidate[
                        "contact_count"
                    ]
                ),
                "join_mode": (
                    "direct_structural_lock"
                ),
                "valid": True,
            }
        )

    return (
        pd.DataFrame(
            selected_rows,
            columns=output_columns,
        ),
        pd.DataFrame(
            audit_rows
        ),
    )


def block_family_count_dataframe(
    blocks,
):
    """Return block family count dataframe.
    
    :param blocks: Block records used by the operation.
    :returns: The result produced by the function.
    """
    rows = [
        {
            "block_family": str(
                block.block_family
            ),
            "block_role": str(
                getattr(
                    block,
                    "block_role",
                    getattr(
                        block,
                        "category",
                        "unknown",
                    ),
                )
            ),
        }
        for block in blocks
    ]
    if not rows:
        return pd.DataFrame(
            columns=[
                "block_family",
                "count",
                "block_roles",
            ]
        )

    dataframe = pd.DataFrame(
        rows
    )
    count_rows = []
    for family, group in dataframe.groupby(
        "block_family",
        sort=True,
    ):
        count_rows.append(
            {
                "block_family": str(
                    family
                ),
                "count": int(
                    len(
                        group
                    )
                ),
                "block_roles": ", ".join(
                    sorted(
                        set(
                            group[
                                "block_role"
                            ].astype(
                                str
                            )
                        )
                    )
                ),
            }
        )

    return pd.DataFrame(
        count_rows
    ).sort_values(
        "block_family"
    ).reset_index(
        drop=True
    )


def proper_build_step_labels_for_segment(
    result,
):
    """Return the proper build step labels for segment value.
    
    :param result: The result value.
    :returns: The result produced by the function.
    """
    labels = {
        0: (
            "Target segment geometry — "
            "no blocks placed"
        )
    }
    validation_rows = (
        result.get(
            "validation",
            {},
        ).get(
            "step_rows",
            [],
        )
    )
    steps = (
        result.get(
            "planning_result",
            {},
        ).get(
            "instruction_steps",
            [],
        )
    )
    build_axis = str(
        result.get(
            "selected_build_axis",
            result.get(
                "planning_result",
                {},
            ).get(
                "selected_build_axis",
                "+Y",
            ),
        )
    )

    for step_number, step in enumerate(
        steps,
        start=1,
    ):
        blocks = list(
            step.get(
                "blocks",
                [],
            )
        )
        families = ", ".join(
            str(
                block.block_family
            )
            for block in blocks
        ) or "none"
        block_ids = ", ".join(
            str(
                int(
                    block.block_id
                )
            )
            for block in blocks
        ) or "none"
        validation_row = (
            validation_rows[
                step_number - 1
            ]
            if (
                step_number - 1
                < len(
                    validation_rows
                )
            )
            else {}
        )
        labels[
            step_number
        ] = (
            f"Build axis {build_axis}; "
            f"place block(s) {block_ids}; "
            f"families: {families}; "
            f"status: "
            f"{validation_row.get('step_status', 'unknown')}; "
            f"lock area to accepted structure: "
            f"{validation_row.get('lock_area_to_accepted_prior', 0)}; "
            f"internal lock area: "
            f"{validation_row.get('internal_lock_area', 0)}."
        )
    return labels


def build_assembly_timeline(
    assembly_steps,
    segment_blocks_by_id,
    connector_blocks,
    functional_blocks,
    connector_validation_df,
    structural_ready,
):
    """Build assembly timeline.
    
    :param assembly_steps: The assembly steps value.
    :param segment_blocks_by_id: Identifier for the segment blocks by.
    :param connector_blocks: The connector blocks value.
    :param functional_blocks: The functional blocks value.
    :param connector_validation_df: DataFrame containing connector validation records.
    :param structural_ready: The structural ready value.
    :returns: The generated result.
    """
    connector_by_interface = {
        str(
            block.interface_id
        ): block
        for block in connector_blocks
    }
    valid_rows = (
        connector_validation_df.loc[
            connector_validation_df.get(
                "valid",
                pd.Series(
                    dtype=bool
                ),
            ).astype(
                bool
            )
        ].copy()
        if not connector_validation_df.empty
        else pd.DataFrame()
    )
    valid_interfaces = set(
        valid_rows.get(
            "interface_id",
            pd.Series(
                dtype=str
            ),
        ).astype(
            str
        )
    )
    join_mode_by_interface = {
        str(
            row.interface_id
        ): str(
            getattr(
                row,
                "join_mode",
                "special_connector_block",
            )
        )
        for row in valid_rows.itertuples(
            index=False
        )
    }

    visible_blocks = []
    appearance = {}
    labels = {
        0: "No assembled subassemblies"
    }
    rows = []
    step_number = 0

    if not assembly_steps:
        return (
            visible_blocks,
            appearance,
            labels,
            pd.DataFrame(
                rows,
                columns=[
                    "assembly_visual_step",
                    "action",
                    "segment_id",
                    "interface_id",
                    "block_ids",
                    "status",
                ],
            ),
        )

    root_segment_id = int(
        assembly_steps[
            0
        ][
            "attached_segment_id"
        ]
    )
    root_blocks = list(
        segment_blocks_by_id.get(
            root_segment_id,
            [],
        )
    )
    if root_blocks:
        step_number += 1
        for block in root_blocks:
            appearance[
                int(
                    block.block_id
                )
            ] = step_number
            visible_blocks.append(
                block
            )
        labels[
            step_number
        ] = (
            f"Start with completed segment "
            f"{root_segment_id}"
        )
        rows.append(
            {
                "assembly_visual_step": (
                    step_number
                ),
                "action": (
                    "start_with_segment_subassembly"
                ),
                "segment_id": (
                    root_segment_id
                ),
                "interface_id": None,
                "block_ids": ",".join(
                    str(
                        int(
                            block.block_id
                        )
                    )
                    for block in root_blocks
                ),
                "status": "ready",
            }
        )

    if structural_ready:
        for assembly_step in assembly_steps[
            1:
        ]:
            attached_segment_id = int(
                assembly_step[
                    "attached_segment_id"
                ]
            )
            interface_id = str(
                assembly_step[
                    "interface_id"
                ]
            )
            join_mode = (
                join_mode_by_interface.get(
                    interface_id
                )
            )

            if interface_id not in valid_interfaces:
                rows.append(
                    {
                        "assembly_visual_step": None,
                        "action": (
                            "attach_segment_blocked"
                        ),
                        "segment_id": (
                            attached_segment_id
                        ),
                        "interface_id": (
                            interface_id
                        ),
                        "block_ids": "",
                        "status": (
                            "missing_or_invalid_join"
                        ),
                    }
                )
                continue

            if join_mode != "direct_structural_lock":
                connector = (
                    connector_by_interface.get(
                        interface_id
                    )
                )
                if connector is None:
                    rows.append(
                        {
                            "assembly_visual_step": None,
                            "action": (
                                "attach_segment_blocked"
                            ),
                            "segment_id": (
                                attached_segment_id
                            ),
                            "interface_id": (
                                interface_id
                            ),
                            "block_ids": "",
                            "status": (
                                "missing_special_connector"
                            ),
                        }
                    )
                    continue

                step_number += 1
                appearance[
                    int(
                        connector.block_id
                    )
                ] = step_number
                visible_blocks.append(
                    connector
                )
                labels[
                    step_number
                ] = (
                    f"Place special connector for "
                    f"{interface_id}"
                )
                rows.append(
                    {
                        "assembly_visual_step": (
                            step_number
                        ),
                        "action": (
                            "place_special_connector"
                        ),
                        "segment_id": None,
                        "interface_id": (
                            interface_id
                        ),
                        "block_ids": str(
                            int(
                                connector.block_id
                            )
                        ),
                        "status": "ready",
                    }
                )

            attached_blocks = list(
                segment_blocks_by_id.get(
                    attached_segment_id,
                    [],
                )
            )
            if attached_blocks:
                step_number += 1
                for block in attached_blocks:
                    appearance[
                        int(
                            block.block_id
                        )
                    ] = step_number
                    visible_blocks.append(
                        block
                    )
                labels[
                    step_number
                ] = (
                    f"Attach completed segment "
                    f"{attached_segment_id} by "
                    f"{join_mode or 'validated join'}"
                )
                rows.append(
                    {
                        "assembly_visual_step": (
                            step_number
                        ),
                        "action": (
                            "attach_segment_by_"
                            "direct_structural_lock"
                            if join_mode
                            == "direct_structural_lock"
                            else (
                                "attach_segment_"
                                "through_special_connector"
                            )
                        ),
                        "segment_id": (
                            attached_segment_id
                        ),
                        "interface_id": (
                            interface_id
                        ),
                        "block_ids": ",".join(
                            str(
                                int(
                                    block.block_id
                                )
                            )
                            for block in (
                                attached_blocks
                            )
                        ),
                        "status": "ready",
                    }
                )

        for functional in functional_blocks:
            step_number += 1
            appearance[
                int(
                    functional.block_id
                )
            ] = step_number
            visible_blocks.append(
                functional
            )
            functional_role = str(
                getattr(
                    functional,
                    "block_role",
                    "functional_attachment",
                )
            )
            functional_group_name = str(
                getattr(functional, "connected_group_name", "")
                or getattr(functional, "segment_name", "")
                or getattr(functional, "physical_target_id", "Functional Assembly")
            )
            if functional_role in {"functional_connector", "functional_motion_connector"}:
                labels[step_number] = (
                    f"Attach {functional_group_name} connector to its validated anchor"
                )
            elif functional_role == "functional_subassembly_structural":
                labels[step_number] = (
                    f"Add {functional_group_name} "
                    f"{getattr(functional, 'subassembly_member_role', 'member')} block"
                )
            else:
                labels[
                    step_number
                ] = (
                    f"Attach {functional.block_family} "
                    f"at target "
                    f"{functional.physical_target_id}"
                )
            rows.append(
                {
                    "assembly_visual_step": (
                        step_number
                    ),
                    "action": (
                        "attach_functional_block"
                    ),
                    "segment_id": None,
                    "interface_id": None,
                    "block_ids": str(
                        int(
                            functional.block_id
                        )
                    ),
                    "status": "ready",
                }
            )

    return (
        visible_blocks,
        appearance,
        labels,
        pd.DataFrame(
            rows,
            columns=[
                "assembly_visual_step",
                "action",
                "segment_id",
                "interface_id",
                "block_ids",
                "status",
            ],
        ),
    )


def build_assembly_oriented_assembly_steps(
    root_segment_id,
    required_interfaces_df,
    connector_rule_audit_df,
    selected_connectors_df,
    connector_validation_df,
    structural_segment_ids,
):
    """Build assembly oriented assembly steps.
    
    :param root_segment_id: Identifier for the root segment.
    :param required_interfaces_df: DataFrame containing required interfaces records.
    :param connector_rule_audit_df: DataFrame containing connector rule audit records.
    :param selected_connectors_df: DataFrame containing selected connectors records.
    :param connector_validation_df: DataFrame containing connector validation records.
    :param structural_segment_ids: Identifiers for the structural segment records.
    :returns: The generated result.
    """
    valid_rows = (
        connector_validation_df.loc[
            connector_validation_df.get(
                "valid",
                pd.Series(
                    dtype=bool
                ),
            ).astype(
                bool
            )
        ].copy()
        if not connector_validation_df.empty
        else pd.DataFrame()
    )

    adjacency = defaultdict(
        list
    )
    for row in valid_rows.itertuples(
        index=False
    ):
        adjacency[
            int(
                row.segment_a
            )
        ].append(
            (
                int(
                    row.segment_b
                ),
                str(
                    row.interface_id
                ),
                str(
                    getattr(
                        row,
                        "join_mode",
                        "special_connector_block",
                    )
                ),
            )
        )
        adjacency[
            int(
                row.segment_b
            )
        ].append(
            (
                int(
                    row.segment_a
                ),
                str(
                    row.interface_id
                ),
                str(
                    getattr(
                        row,
                        "join_mode",
                        "special_connector_block",
                    )
                ),
            )
        )

    steps = []
    visited = set()
    roots = (
        [
            int(
                root_segment_id
            )
        ]
        if root_segment_id
        is not None
        else []
    )
    roots += [
        int(
            segment_id
        )
        for segment_id in (
            structural_segment_ids
        )
        if int(
            segment_id
        )
        not in roots
    ]

    for root in roots:
        if root in visited:
            continue

        visited.add(
            root
        )
        steps.append(
            {
                "assembly_step": (
                    len(
                        steps
                    )
                    + 1
                ),
                "action": (
                    "start_segment_subassembly"
                ),
                "root_segment_id": (
                    root
                ),
                "anchor_segment_id": None,
                "attached_segment_id": (
                    root
                ),
                "interface_id": None,
                "connector_decision_valid": None,
                "connector_decision_source": None,
                "connector_selected": None,
                "connector_valid": None,
                "step_status": "ready",
            }
        )

        queue = deque(
            [
                root
            ]
        )
        while queue:
            anchor = queue.popleft()
            for (
                attached,
                interface_id,
                join_mode,
            ) in sorted(
                adjacency[
                    anchor
                ]
            ):
                if attached in visited:
                    continue

                visited.add(
                    attached
                )
                queue.append(
                    attached
                )

                direct_join = bool(
                    join_mode
                    == "direct_structural_lock"
                )
                steps.append(
                    {
                        "assembly_step": (
                            len(
                                steps
                            )
                            + 1
                        ),
                        "action": (
                            "attach_segment_by_"
                            "direct_structural_lock"
                            if direct_join
                            else (
                                "attach_segment_"
                                "through_special_connector"
                            )
                        ),
                        "root_segment_id": (
                            root
                        ),
                        "anchor_segment_id": (
                            anchor
                        ),
                        "attached_segment_id": (
                            attached
                        ),
                        "interface_id": (
                            interface_id
                        ),
                        "connector_decision_valid": (
                            True
                        ),
                        "connector_decision_source": (
                            join_mode
                        ),
                        "connector_selected": (
                            False
                            if direct_join
                            else True
                        ),
                        "connector_valid": True,
                        "step_status": (
                            "ready_to_attach"
                        ),
                    }
                )

    return pd.DataFrame(
        steps,
        columns=[
            "assembly_step",
            "action",
            "root_segment_id",
            "anchor_segment_id",
            "attached_segment_id",
            "interface_id",
            "connector_decision_valid",
            "connector_decision_source",
            "connector_selected",
            "connector_valid",
            "step_status",
        ],
    )


def format_block_id_field(
    values,
):
    """Format block id field.
    
    :param values: The values value.
    :returns: The computed result.
    """
    return ",".join(
        str(
            int(value)
        )
        for value in values
    )


__all__ = [
    'format_block_id_field',
    'parse_block_id_field',
    'reindex_segment_plan',
    'remap_validation_block_ids_to_planning',
    'rebuild_instruction_steps_from_blocks',
    'direct_structural_join_tree',
    'connected_segment_graph',
    'block_family_count_dataframe',
    'proper_build_step_labels_for_segment',
    'build_assembly_timeline',
    'build_assembly_oriented_assembly_steps',
]
