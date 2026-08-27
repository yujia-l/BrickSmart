"""Artifact serialization and row/column output writers."""

from __future__ import annotations

import copy
import json
from collections import defaultdict
from enum import Enum
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd


def json_safe_value(value):
    """Recursively convert nested NumPy/pandas objects to JSON-safe values."""
    if isinstance(value, np.ndarray):
        return [json_safe_value(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return json_safe_value(value.item())
    if isinstance(value, dict):
        return {
            str(key): json_safe_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [json_safe_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return json_safe_value(value.value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if value is pd.NA:
        return None
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def safe_export_dataframe(df, path):
    """Perform the safe export dataframe operation.
    
    :param df: DataFrame containing the records to process.
    :param path: Filesystem path used by the operation.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    export = df.copy()
    for column in export.columns:
        mask = export[column].map(
            lambda value: isinstance(
                value,
                (list, tuple, set, dict, np.ndarray),
            )
        )
        if mask.any():
            export.loc[mask, column] = export.loc[mask, column].map(
                lambda value: json.dumps(
                    json_safe_value(value),
                    ensure_ascii=False,
                    sort_keys=True,
                    allow_nan=False,
                )
            )
    export.to_csv(path, index=False)


def write_planner_outputs(
    planning_result,
    *,
    output_dir,
    catalog_csv_path,
    structural_catalog_records,
    task_context_json_path,
    task_context_packing_priority_overrides,
    manual_packing_priority_overrides,
    male_face_resolver: Callable[[int, tuple[int, int, int]], str],
    show_output_paths: bool = False,
):
    """
    Persist the selected plan without assuming that display step numbers are
    identical to planner-frame row coordinates.
    """
    output_dir = Path(
        output_dir
    )
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    blocks = list(
        planning_result[
            "blocks"
        ]
    )
    steps = list(
        planning_result[
            "instruction_steps"
        ]
    )
    best_state = (
        planning_result[
            "best_state"
        ]
    )
    row_diagnostics = list(
        best_state.get(
            "row_diagnostics",
            [],
        )
    )
    selected_build_axis = str(
        planning_result.get(
            "selected_build_axis",
            "+Y",
        )
    )

    block_rows = []

    for block in blocks:
        block_rows.append(
            {
                "block_id": int(
                    block.block_id
                ),
                "block_family": (
                    block.block_family
                ),
                "catalog_color": (
                    block.catalog_record[
                        "color"
                    ]
                ),
                "default_packing_priority": float(
                    block.catalog_record[
                        "default_packing_priority"
                    ]
                ),
                "effective_packing_priority": float(
                    block.catalog_record[
                        "effective_packing_priority"
                    ]
                ),
                "packing_priority_source": (
                    block.catalog_record[
                        "packing_priority_source"
                    ]
                ),
                "native_geometry_size": (
                    block.catalog_record[
                        "geometry_size"
                    ]
                ),
                "column_world_size": "x".join(
                    str(
                        int(
                            value
                        )
                    )
                    for value in block.size
                ),
                "selected_build_axis": (
                    selected_build_axis
                ),
                "world_row_y": int(
                    block.position[
                        1
                    ]
                ),
                "position_x": int(
                    block.position[
                        0
                    ]
                ),
                "position_y": int(
                    block.position[
                        1
                    ]
                ),
                "position_z": int(
                    block.position[
                        2
                    ]
                ),
                "size_x": int(
                    block.size[
                        0
                    ]
                ),
                "size_y": int(
                    block.size[
                        1
                    ]
                ),
                "size_z": int(
                    block.size[
                        2
                    ]
                ),
                "rotation": int(
                    block.rotation
                ),
                "male_face": (
                    male_face_resolver(
                        block.rotation,
                        block.size,
                    )
                ),
            }
        )

    normalized_diagnostic_rows = []
    for step_index, step in enumerate(
        steps,
        start=1,
    ):
        diagnostic = copy.deepcopy(
            step.get(
                "planning_diagnostic",
                (
                    row_diagnostics[
                        step_index - 1
                    ]
                    if (
                        step_index - 1
                        < len(
                            row_diagnostics
                        )
                    )
                    else {}
                ),
            )
            or {}
        )
        planner_row = int(
            step.get(
                "planner_row",
                diagnostic.get(
                    "row",
                    step.get(
                        "row",
                        step_index,
                    ),
                ),
            )
        )
        display_step = int(
            step.get(
                "row",
                step_index,
            )
        )
        diagnostic[
            "step_number"
        ] = int(
            step_index
        )
        diagnostic[
            "display_step"
        ] = int(
            display_step
        )
        diagnostic[
            "planner_row"
        ] = int(
            planner_row
        )
        diagnostic[
            "world_slice_coordinate"
        ] = step.get(
            "world_slice_coordinate"
        )
        diagnostic[
            "selected_build_axis"
        ] = str(
            step.get(
                "build_axis",
                selected_build_axis,
            )
        )
        normalized_diagnostic_rows.append(
            diagnostic
        )

    block_df = pd.DataFrame(
        block_rows
    )
    row_df = pd.DataFrame(
        normalized_diagnostic_rows
    )

    block_path = (
        output_dir
        / "better_block_plan.csv"
    )
    row_path = (
        output_dir
        / "better_row_planning_summary.csv"
    )
    summary_path = (
        output_dir
        / "better_planner_summary.json"
    )
    instructions_path = (
        output_dir
        / "better_build_instructions.md"
    )

    block_df.to_csv(
        block_path,
        index=False,
    )
    row_df.to_csv(
        row_path,
        index=False,
    )

    summary_payload = {
        "catalog_csv": str(
            catalog_csv_path
        ),
        "selected_build_axis": (
            selected_build_axis
        ),
        "enabled_structural_families": [
            record[
                "block_family"
            ]
            for record in (
                structural_catalog_records
            )
        ],
        "default_packing_priority_by_family": {
            record[
                "block_family"
            ]: float(
                record[
                    "default_packing_priority"
                ]
            )
            for record in (
                structural_catalog_records
            )
        },
        "effective_packing_priority_by_family": {
            record[
                "block_family"
            ]: float(
                record[
                    "effective_packing_priority"
                ]
            )
            for record in (
                structural_catalog_records
            )
        },
        "packing_priority_source_by_family": {
            record[
                "block_family"
            ]: record[
                "packing_priority_source"
            ]
            for record in (
                structural_catalog_records
            )
        },
        "task_context_json": (
            str(
                task_context_json_path
            )
            if task_context_json_path
            is not None
            else None
        ),
        "task_context_family_priority_overrides": (
            task_context_packing_priority_overrides
        ),
        "manual_family_priority_overrides": (
            manual_packing_priority_overrides
        ),
        "config": (
            planning_result[
                "config"
            ]
        ),
        "num_steps": int(
            len(
                steps
            )
        ),
        "num_planner_rows": int(
            len(
                row_diagnostics
            )
        ),
        "num_blocks": int(
            len(
                blocks
            )
        ),
        "theoretical_fixed_column_minimum": (
            planning_result[
                "theoretical_fixed_column_minimum"
            ]
        ),
        "final_exposed_male_area": (
            best_state[
                "final_exposed_male_area"
            ]
        ),
        "total_prior_lock_area": (
            best_state[
                "total_prior_lock_area"
            ]
        ),
        "total_internal_lock_area": (
            best_state[
                "total_internal_lock_area"
            ]
        ),
        "total_aligned_seams": (
            best_state[
                "total_aligned_seams"
            ]
        ),
        "total_staggered_seams": (
            best_state[
                "total_staggered_seams"
            ]
        ),
    }
    summary_path.write_text(
        json.dumps(
            summary_payload,
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = [
        "# Better Row-Aware Build Plan",
        "",
        (
            "Planning follows the selected segment build axis. "
            "Display step numbers are intentionally separate from "
            "planner-frame row coordinates."
        ),
        "",
        f"- Selected build axis: {selected_build_axis}",
        f"- Catalog: {catalog_csv_path}",
        (
            "- Packing priority policy: catalog defaults may be "
            "overridden by the model task context; effective values "
            "are used only as a late tie-breaker."
        ),
        f"- Planned steps: {len(steps)}",
        f"- Planned blocks: {len(blocks)}",
        (
            "- Fixed-column theoretical minimum: "
            f"{planning_result['theoretical_fixed_column_minimum']}"
        ),
        (
            "- Final unreserved exposed male area: "
            f"{best_state['final_exposed_male_area']}"
        ),
        "",
    ]

    for step_index, step in enumerate(
        steps,
        start=1,
    ):
        diagnostic = (
            normalized_diagnostic_rows[
                step_index - 1
            ]
            if (
                step_index - 1
                < len(
                    normalized_diagnostic_rows
                )
            )
            else {}
        )
        planner_row = int(
            diagnostic.get(
                "planner_row",
                step.get(
                    "planner_row",
                    step_index,
                ),
            )
        )
        world_slice = (
            diagnostic.get(
                "world_slice_coordinate"
            )
        )
        step_axis = str(
            diagnostic.get(
                "selected_build_axis",
                selected_build_axis,
            )
        )

        lines.extend(
            [
                (
                    f"## Step {step_index}: "
                    f"build along {step_axis}"
                ),
                "",
                (
                    f"- Planner-frame row: "
                    f"{planner_row}"
                ),
                (
                    f"- World slice coordinate: "
                    f"{world_slice}"
                ),
                (
                    f"- Blocks: "
                    f"{len(step['blocks'])}"
                ),
                (
                    "- Block IDs: "
                    + ",".join(
                        str(
                            int(
                                block.block_id
                            )
                        )
                        for block in (
                            step[
                                "blocks"
                            ]
                        )
                    )
                ),
                (
                    "- Lock area to accepted structure: "
                    f"{diagnostic.get('prior_lock_area', 0)}"
                ),
                (
                    "- Lock area within step: "
                    f"{diagnostic.get('internal_lock_area', 0)}"
                ),
                (
                    "- Forward female receiving area: "
                    f"{diagnostic.get('forward_female_area', 0)}"
                ),
                (
                    "- Exposed male area during planning: "
                    f"{diagnostic.get('row_exposed_male_area', 0)}"
                ),
                "",
            ]
        )

        for block in step[
            "blocks"
        ]:
            lines.append(
                (
                    f"- Place block "
                    f"{int(block.block_id)} "
                    f"({block.block_family}, catalog native "
                    f"{block.catalog_record['geometry_size']}) at "
                    f"{tuple(int(value) for value in block.position)}, "
                    f"world size "
                    f"{tuple(int(value) for value in block.size)}, "
                    f"default priority "
                    f"{float(block.catalog_record['default_packing_priority'])}, "
                    f"effective priority "
                    f"{float(block.catalog_record['effective_packing_priority'])} "
                    f"({block.catalog_record['packing_priority_source']}), "
                    f"rotation {int(block.rotation)}°, "
                    f"male face "
                    f"{male_face_resolver(block.rotation, block.size)}."
                )
            )

        lines.append(
            ""
        )

    instructions_path.write_text(
        "\n".join(
            lines
        ),
        encoding="utf-8",
    )

    if show_output_paths:
        for path in [
            block_path,
            row_path,
            summary_path,
            instructions_path,
        ]:
            print(
                f"[OUTPUT] {path}"
            )

    return (
        block_df,
        row_df,
    )


def write_step_validation_artifacts(
    validation,
    *,
    output_dir,
    show_output_paths: bool = False,
):
    """Write step validation artifacts.
    
    :param validation: The validation value.
    :param output_dir: Directory where generated artifacts are written.
    :param show_output_paths: The show output paths value.
    :type show_output_paths: bool
    :returns: The result produced by the function.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    step_df = pd.DataFrame(validation["step_rows"])
    block_df = pd.DataFrame(validation["block_rows"])
    component_df = pd.DataFrame(
        validation["component_rows"]
    )
    contact_df = pd.DataFrame(validation["contact_rows"])

    step_path = (
        output_dir
        / "build_step_validation_summary.csv"
    )
    block_path = (
        output_dir
        / "build_step_block_validation.csv"
    )
    component_path = (
        output_dir
        / "build_step_component_validation.csv"
    )
    contact_path = (
        output_dir
        / "build_step_contact_validation.csv"
    )
    json_path = (
        output_dir
        / "build_step_validation.json"
    )
    markdown_path = (
        output_dir
        / "validated_build_instructions.md"
    )

    step_df.to_csv(step_path, index=False)
    block_df.to_csv(block_path, index=False)
    component_df.to_csv(component_path, index=False)
    contact_df.to_csv(contact_path, index=False)

    json_payload = {
        "step_rows": validation["step_rows"],
        "block_rows": validation["block_rows"],
        "component_rows": validation[
            "component_rows"
        ],
        "contact_rows": validation["contact_rows"],
        "block_validation": {
            str(key): value
            for key, value in validation[
                "block_validation"
            ].items()
        },
        "accepted_before_by_step": {
            str(key): value
            for key, value in validation[
                "accepted_before_by_step"
            ].items()
        },
        "accepted_after_by_step": {
            str(key): value
            for key, value in validation[
                "accepted_after_by_step"
            ].items()
        },
        "num_final_accepted_blocks": validation[
            "num_final_accepted_blocks"
        ],
        "num_total_blocks": validation[
            "num_total_blocks"
        ],
        "all_blocks_accepted": validation[
            "all_blocks_accepted"
        ],
    }
    json_path.write_text(
        json.dumps(json_payload, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Validated Build Instructions",
        "",
        "Every non-root accepted block must be reachable through "
        "male-to-female locking edges from the previously accepted "
        "structure. Female-to-female contact is allowed but does not "
        "transmit the locking path.",
        "",
        f"- Total blocks: "
        f"{validation['num_total_blocks']}",
        f"- Accepted after final step: "
        f"{validation['num_final_accepted_blocks']}",
        f"- All blocks accepted: "
        f"{validation['all_blocks_accepted']}",
        "",
    ]

    blocks_by_step = defaultdict(list)
    components_by_step = defaultdict(list)

    for row in validation["block_rows"]:
        blocks_by_step[int(row["step"])].append(row)

    for row in validation["component_rows"]:
        components_by_step[int(row["step"])].append(
            row
        )

    for step in validation["step_rows"]:
        step_number = int(step["step"])
        lines.extend([
            f"## Step {step_number}: Build row "
            f"Y={step['row']}",
            "",
            f"- Status: **{step['step_status']}**",
            f"- Blocks: {step['num_blocks']}",
            f"- Locking components: "
            f"{step['num_components']} "
            f"({step['valid_components']} valid, "
            f"{step['invalid_components']} invalid)",
            f"- Locks to accepted prior structure: "
            f"{step['locks_to_accepted_prior']}",
            f"- Lock area to accepted prior structure: "
            f"{step['lock_area_to_accepted_prior']}",
            f"- Internal lock area: "
            f"{step['internal_lock_area']}",
            f"- Conflicts: "
            f"{step['male_male_or_overlap_conflicts']}",
            f"- Exposed male area at this step: "
            f"{step['exposed_male_area']}",
            f"- Accepted block IDs: "
            f"{step['accepted_block_ids'] or 'none'}",
            f"- Rejected block IDs: "
            f"{step['rejected_block_ids'] or 'none'}",
            "",
            "| Block | Catalog family | Result | Reason | Rotation | Male face |",
            "|---:|---|---|---|---:|---|",
        ])

        for row in blocks_by_step[step_number]:
            result = (
                "accepted"
                if row["accepted"]
                else "rejected"
            )
            lines.append(
                f"| {row['block_id']} | "
                f"{row['block_family']} | {result} | "
                f"`{row['reason']}` | "
                f"{row['rotation']}° | "
                f"{row['male_face']} |"
            )

        lines.append("")

    markdown_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    if show_output_paths:
        for path in [
            step_path,
            block_path,
            component_path,
            contact_path,
            json_path,
            markdown_path,
        ]:
            print(
                f"[OUTPUT] {path}"
            )

    return (
        step_df,
        block_df,
        component_df,
        contact_df,
    )


__all__ = [
    'json_safe_value',
    'safe_export_dataframe',
    'write_planner_outputs',
    'write_step_validation_artifacts',
]
