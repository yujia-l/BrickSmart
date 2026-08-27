"""Interactive build-step player generation.

This module builds the self-contained HTML and data structures used to review a
validated assembly step by step.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import plotly.graph_objects as go

from bricksmart.catalog import load_block_catalog
from bricksmart.exceptions import CatalogConfigurationError
from bricksmart.runtime import load_task_context, model_identity


@dataclass(frozen=True)
class DisplayBlock:
    block_id: int
    block_family: str
    segment_id: int
    segment_name: str
    position: tuple[float, float, float]
    size: tuple[float, float, float]
    rotation: int
    male_face: str
    color: str
    block_role: str = "segment_structural"
    physical_target_id: str = ""


@dataclass(frozen=True)
class PlayerStep:
    step: int
    phase: str
    title: str
    instruction: str
    visible_block_ids: tuple[int, ...]
    final_position_segment_ids: tuple[int, ...]
    interface_id: str = ""


def _parse_triplet(value: Any, *, field: str) -> tuple[float, float, float]:
    """Parse triplet.
    
    :param value: Value used by the operation.
    :type value: Any
    :param field: The field value.
    :type field: str
    :returns: The computed result.
    :rtype: tuple[float, float, float]
    """
    if isinstance(value, (list, tuple)):
        parsed = value
    else:
        try:
            parsed = ast.literal_eval(str(value))
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"Cannot parse {field}: {value!r}") from exc
    if not isinstance(parsed, (list, tuple)) or len(parsed) != 3:
        raise ValueError(f"Expected three values for {field}, got {value!r}")
    return tuple(float(item) for item in parsed)


def _ids(value: Any) -> tuple[int, ...]:
    """Return IDs for ids.
    
    :param value: Value used by the operation.
    :type value: Any
    :returns: The result produced by the function.
    :rtype: tuple[int, ...]
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ()
    return tuple(
        int(item.strip())
        for item in str(value).split(",")
        if item.strip()
    )


def _hex_color(value: str) -> str:
    """Convert hex to color.
    
    :param value: Value used by the operation.
    :type value: str
    :returns: The result produced by the function.
    :rtype: str
    """
    color = str(value or "").strip()
    if not color:
        raise CatalogConfigurationError("Catalog display color is empty")
    if color.startswith("#"):
        return color
    normalized = color.lower().replace(" ", "")
    named = {
        "blue": "#3977D4",
        "green": "#43A047",
        "yellow": "#F2C94C",
        "red": "#D64545",
        "purple": "#7E57C2",
        "orange": "#F2994A",
        "gray": "#9E9E9E",
        "grey": "#9E9E9E",
        "white": "#F5F5F5",
        "black": "#212121",
    }
    return named.get(normalized, color)


def _catalog_colors(catalog_path: str | Path) -> dict[str, str]:
    """Return catalog colors.
    
    :param catalog_path: Catalog file path used by the operation.
    :type catalog_path: str | Path
    :returns: The result produced by the function.
    :rtype: dict[str, str]
    """
    catalog = load_block_catalog(catalog_path)
    colors = catalog.colors
    if not colors:
        raise CatalogConfigurationError(
            f"No block_family/color rows found in {catalog_path}"
        )
    return colors

def _functional_target_metadata(context: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Return functional target metadata.
    
    :param context: Runtime context for the operation.
    :type context: dict[str, Any] | None
    :returns: The result produced by the function.
    :rtype: dict[str, dict[str, Any]]
    """
    metadata: dict[str, dict[str, Any]] = {}
    if not context:
        return metadata
    confirmed_names = {
        str(key): str(value)
        for key, value in (
            (context.get("segment_semantics", {}) or {}).get(
                "confirmed_segment_names", {}
            )
            or {}
        ).items()
    }
    for declaration in context.get("functional_attachments", []) or []:
        attachment_id = str(declaration.get("attachment_id") or "")
        grouping = declaration.get("physical_target_grouping", {}) or {}
        for group in grouping.get("manual_groups", []) or []:
            target_id = str(group.get("physical_target_id") or "")
            if not target_id:
                continue
            metadata[target_id] = {
                "display_name": str(
                    group.get("physical_group_name")
                    or group.get("display_name")
                    or target_id.replace("_", " ").title()
                ),
                "assembly_type": str(declaration.get("attachment_type") or declaration.get("candidate_strategy") or "catalog_attachment"),
                "instruction_templates": declaration.get("instruction_templates", {}) or {},
                "attachment_id": attachment_id,
            }
    for assembly in context.get("functional_assemblies", []) or []:
        target_id = str(assembly.get("physical_target_id") or assembly.get("assembly_id") or "")
        if not target_id:
            continue
        anchor_segment_id = str(assembly.get("anchor_segment_id") or "").strip()
        metadata[target_id] = {
            "display_name": str(assembly.get("display_name") or target_id.replace("_", " ").title()),
            "assembly_type": str(assembly.get("assembly_type") or "functional_subassembly"),
            "instruction_templates": assembly.get("instruction_templates", {}) or {},
            "attachment_id": target_id,
            "anchor_segment_id": anchor_segment_id,
            "anchor_name": str(
                assembly.get("anchor_display_name")
                or confirmed_names.get(anchor_segment_id)
                or (f"Segment {anchor_segment_id}" if anchor_segment_id else "validated anchor")
            ),
        }
    return metadata


def _functional_target_name(value: str, metadata: dict[str, dict[str, Any]]) -> str:
    """Return functional target name.
    
    :param value: Value used by the operation.
    :type value: str
    :param metadata: The metadata value.
    :type metadata: dict[str, dict[str, Any]]
    :returns: The result produced by the function.
    :rtype: str
    """
    if value in metadata:
        return str(metadata[value].get("display_name") or value)
    return value.replace("_", " ").title() if value else "Functional Assembly"


def load_display_blocks(
    *,
    output_dir: str | Path,
    catalog_path: str | Path,
    context: dict[str, Any] | None = None,
) -> list[DisplayBlock]:
    """Load display blocks.
    
    :param output_dir: Directory where generated artifacts are written.
    :type output_dir: str | Path
    :param catalog_path: Catalog file path used by the operation.
    :type catalog_path: str | Path
    :param context: Runtime context for the operation.
    :type context: dict[str, Any] | None
    :returns: The loaded data.
    :rtype: list[DisplayBlock]
    """
    output_dir = Path(output_dir)
    structural_table = pd.read_csv(output_dir / "segment_subassembly_blocks.csv")
    final_table_path = output_dir / "segment_connector_functional_final_blocks.csv"
    final_table = (
        pd.read_csv(final_table_path)
        if final_table_path.is_file()
        else structural_table.copy()
    )
    colors = _catalog_colors(catalog_path)
    target_metadata = _functional_target_metadata(context)

    structural_by_id = {
        int(row["block_id"]): row
        for row in structural_table.to_dict(orient="records")
    }
    functional_target_ids = sorted(
        {
            str(value)
            for value in final_table.get(
                "physical_target_id", pd.Series(dtype=str)
            ).dropna()
            if str(value).strip()
        }
    )
    functional_group_ids = {
        target_id: -(1000 + index)
        for index, target_id in enumerate(functional_target_ids, start=1)
    }

    blocks: list[DisplayBlock] = []
    for row in final_table.to_dict(orient="records"):
        block_id = int(row["block_id"])
        family = str(row["block_family"])
        if family not in colors:
            raise CatalogConfigurationError(
                f"No display color for used block family {family!r} in {catalog_path}"
            )

        structural_row = structural_by_id.get(block_id)
        physical_target_id = str(row.get("physical_target_id") or "").strip()
        if structural_row is not None:
            segment_id = int(structural_row["source_segment_id"])
            segment_name = str(
                structural_row.get("segment_name")
                or f"Segment {segment_id}"
            )
            male_face = str(structural_row.get("male_face") or "")
        else:
            segment_id = functional_group_ids.get(physical_target_id, -1999)
            segment_name = _functional_target_name(physical_target_id, target_metadata)
            male_face = ""

        blocks.append(
            DisplayBlock(
                block_id=block_id,
                block_family=family,
                segment_id=segment_id,
                segment_name=segment_name,
                position=_parse_triplet(row["position"], field="position"),
                size=_parse_triplet(row["size"], field="size"),
                rotation=int(row.get("rotation") or 0),
                male_face=male_face,
                color=_hex_color(colors[family]),
                block_role=str(row.get("block_role") or ""),
                physical_target_id=physical_target_id,
            )
        )
    return sorted(blocks, key=lambda block: block.block_id)


def _functional_instruction(
    *,
    phase: str,
    blocks: list[DisplayBlock],
    target_metadata: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    """Return functional instruction.
    
    :param phase: The phase value.
    :type phase: str
    :param blocks: Block records used by the operation.
    :type blocks: list[DisplayBlock]
    :param target_metadata: The target metadata value.
    :type target_metadata: dict[str, dict[str, Any]]
    :returns: The result produced by the function.
    :rtype: tuple[str, str]
    """
    names = {block.segment_name for block in blocks}
    target_name = sorted(names)[0] if names else "Functional Assembly"
    target_id = next((block.physical_target_id for block in blocks if block.physical_target_id), "")
    metadata = target_metadata.get(target_id, {})
    templates = metadata.get("instruction_templates", {}) or {}
    families = [block.block_family for block in blocks]
    block_ids = ", ".join(str(block.block_id) for block in blocks)
    role = str(blocks[0].block_role if blocks else "")
    values = {
        "display_name": target_name,
        "target_id": target_id,
        "block_ids": block_ids,
        "block_family": families[0] if families else "",
        "anchor_name": str(metadata.get("anchor_name") or "validated anchor"),
        "anchor_segment_id": str(metadata.get("anchor_segment_id") or ""),
    }
    if role in {"functional_connector", "functional_motion_connector"}:
        template = templates.get("connector")
        return (
            f"Attach {target_name} connector",
            str(template).format_map(type("_SafeValues", (dict,), {"__missing__": lambda self, key: ""})(values)) if template else
            f"Attach connector block {block_ids} ({values['block_family']}) to the validated anchor for {target_name}.",
        )
    if role == "functional_subassembly_structural":
        template = templates.get("member")
        return (
            f"Build {target_name}",
            str(template).format_map(type("_SafeValues", (dict,), {"__missing__": lambda self, key: ""})(values)) if template else
            f"Add block {block_ids} ({values['block_family']}) to the {target_name} subassembly.",
        )
    template = templates.get("attachment")
    return (
        f"Attach {target_name}",
        str(template).format_map(type("_SafeValues", (dict,), {"__missing__": lambda self, key: ""})(values)) if template else
        f"Place block{'s' if len(blocks) != 1 else ''} {block_ids} in the validated final position for {target_name}.",
    )


def build_true_timeline(
    *,
    blocks: Iterable[DisplayBlock],
    subassembly_steps: pd.DataFrame,
    assembly_steps: pd.DataFrame,
    assembly_graph: pd.DataFrame | None = None,
    complete_build_steps: pd.DataFrame | None = None,
    context: dict[str, Any] | None = None,
) -> list[PlayerStep]:
    """Build true timeline.
    
    :param blocks: Block records used by the operation.
    :type blocks: Iterable[DisplayBlock]
    :param subassembly_steps: The subassembly steps value.
    :type subassembly_steps: pd.DataFrame
    :param assembly_steps: The assembly steps value.
    :type assembly_steps: pd.DataFrame
    :param assembly_graph: The assembly graph value.
    :type assembly_graph: pd.DataFrame | None
    :param complete_build_steps: The complete build steps value.
    :type complete_build_steps: pd.DataFrame | None
    :param context: Runtime context for the operation.
    :type context: dict[str, Any] | None
    :returns: The generated result.
    :rtype: list[PlayerStep]
    """
    blocks = list(blocks)
    by_id = {block.block_id: block for block in blocks}
    target_metadata = _functional_target_metadata(context)
    structural_blocks = [
        block for block in blocks
        if block.block_role == "segment_structural"
    ]
    structural_ids = tuple(block.block_id for block in structural_blocks)
    all_ids = tuple(block.block_id for block in blocks)
    segment_names = {
        block.segment_id: block.segment_name
        for block in structural_blocks
    }

    timeline: list[PlayerStep] = []
    visible: list[int] = []

    for row in subassembly_steps.sort_values("global_step").to_dict(orient="records"):
        new_ids = _ids(row.get("new_block_ids"))
        visible.extend(block_id for block_id in new_ids if block_id not in visible)
        segment_id = int(row["segment_id"])
        segment_name = str(row.get("segment_name") or segment_names.get(segment_id, segment_id))
        local_step = int(row.get("local_step") or 0)
        row_number = row.get("row")
        timeline.append(
            PlayerStep(
                step=len(timeline) + 1,
                phase="Build segment modules",
                title=f"Build {segment_name} — local step {local_step}",
                instruction=(
                    f"Add block{'s' if len(new_ids) != 1 else ''} "
                    f"{', '.join(str(value) for value in new_ids)} to the separate "
                    f"{segment_name} module (row {row_number})."
                ),
                visible_block_ids=tuple(visible),
                final_position_segment_ids=(),
            )
        )

    sorted_assembly = assembly_steps.sort_values("assembly_step")
    final_segments: list[int] = []
    if not sorted_assembly.empty:
        root_row = sorted_assembly.iloc[0].to_dict()
        root_segment_id = int(root_row["attached_segment_id"])
        root_name = segment_names.get(root_segment_id, f"Segment {root_segment_id}")
        final_segments = [root_segment_id]
        timeline.append(
            PlayerStep(
                step=len(timeline) + 1,
                phase="Assemble completed modules",
                title=f"Place completed {root_name} as the assembly root",
                instruction=(
                    f"Move the completed {root_name} module from its staging area into its "
                    "final model position. Keep the other completed modules in staging."
                ),
                visible_block_ids=structural_ids,
                final_position_segment_ids=(root_segment_id,),
            )
        )

        graph_by_pair: dict[frozenset[int], dict[str, Any]] = {}
        if assembly_graph is not None and not assembly_graph.empty:
            for row in assembly_graph.to_dict(orient="records"):
                graph_by_pair[frozenset((int(row["segment_a"]), int(row["segment_b"])))] = row

        for row in sorted_assembly.iloc[1:].to_dict(orient="records"):
            attached_segment_id = int(row["attached_segment_id"])
            anchor_segment_id = int(row["anchor_segment_id"])
            attached_name = segment_names.get(attached_segment_id, f"Segment {attached_segment_id}")
            anchor_name = segment_names.get(anchor_segment_id, f"Segment {anchor_segment_id}")
            interface_id = str(row.get("interface_id") or "")
            graph_row = graph_by_pair.get(frozenset((anchor_segment_id, attached_segment_id)), {})
            contact_area = graph_row.get("contact_area")
            contact_note = f" with locking contact area {int(contact_area)}" if pd.notna(contact_area) else ""
            final_segments.append(attached_segment_id)
            timeline.append(
                PlayerStep(
                    step=len(timeline) + 1,
                    phase="Assemble completed modules",
                    title=f"Attach completed {attached_name} to {anchor_name}",
                    instruction=(
                        f"Move the completed {attached_name} module from staging to its final "
                        f"position and engage interface {interface_id} by direct structural lock"
                        f"{contact_note}."
                    ),
                    visible_block_ids=structural_ids,
                    final_position_segment_ids=tuple(final_segments),
                    interface_id=interface_id,
                )
            )

    visible_functional_ids: list[int] = []
    final_functional_groups: list[int] = []
    if complete_build_steps is not None and not complete_build_steps.empty:
        nonstructural_ids = {
            block.block_id for block in blocks
            if block.block_role != "segment_structural"
        }
        functional_mask = complete_build_steps["new_block_ids"].map(
            lambda value: bool(set(_ids(value)) & nonstructural_ids)
        )
        functional_rows = complete_build_steps.loc[functional_mask]
        for row in functional_rows.sort_values("global_step").to_dict(orient="records"):
            new_ids = _ids(row.get("new_block_ids"))
            new_blocks = [by_id[block_id] for block_id in new_ids if block_id in by_id]
            if not new_blocks:
                continue
            visible_functional_ids.extend(
                block_id for block_id in new_ids if block_id not in visible_functional_ids
            )
            group_id = new_blocks[0].segment_id
            if group_id not in final_functional_groups:
                final_functional_groups.append(group_id)
            title, instruction = _functional_instruction(
                phase=str(row.get("phase") or ""),
                blocks=new_blocks,
                target_metadata=target_metadata,
            )
            timeline.append(
                PlayerStep(
                    step=len(timeline) + 1,
                    phase="Attach functional assemblies",
                    title=title,
                    instruction=instruction,
                    visible_block_ids=tuple(structural_ids + tuple(visible_functional_ids)),
                    final_position_segment_ids=tuple(final_segments + final_functional_groups),
                )
            )

    timeline.append(
        PlayerStep(
            step=len(timeline) + 1,
            phase="Final validation",
            title="Final validated build",
            instruction=(
                f"All {len(final_segments)} structural segment modules and "
                f"{len(final_functional_groups)} functional assemblies are in their "
                "validated final positions. All contract-required inventory, locking, "
                "collision, symmetry, and attachment gates have passed."
            ),
            visible_block_ids=all_ids,
            final_position_segment_ids=tuple(
                sorted(set(final_segments + final_functional_groups))
            ),
        )
    )
    return timeline

def _cuboid_vertices(
    origin: tuple[float, float, float],
    size: tuple[float, float, float],
) -> tuple[list[float], list[float], list[float]]:
    """Return cuboid vertices.
    
    :param origin: The origin value.
    :type origin: tuple[float, float, float]
    :param size: The size value.
    :type size: tuple[float, float, float]
    :returns: The result produced by the function.
    :rtype: tuple[list[float], list[float], list[float]]
    """
    x, y, z = origin
    dx, dy, dz = size
    vertices = [
        (x, y, z),
        (x + dx, y, z),
        (x + dx, y + dy, z),
        (x, y + dy, z),
        (x, y, z + dz),
        (x + dx, y, z + dz),
        (x + dx, y + dy, z + dz),
        (x, y + dy, z + dz),
    ]
    return (
        [value[0] for value in vertices],
        [value[1] for value in vertices],
        [value[2] for value in vertices],
    )


def _wireframe_coordinates(
    origin: tuple[float, float, float],
    size: tuple[float, float, float],
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Return the wireframe coordinates value.
    
    :param origin: The origin value.
    :type origin: tuple[float, float, float]
    :param size: The size value.
    :type size: tuple[float, float, float]
    :returns: The result produced by the function.
    :rtype: tuple[list[float | None], list[float | None], list[float | None]]
    """
    x, y, z = _cuboid_vertices(origin, size)
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]
    xs: list[float | None] = []
    ys: list[float | None] = []
    zs: list[float | None] = []
    for start, end in edges:
        xs.extend((x[start], x[end], None))
        ys.extend((y[start], y[end], None))
        zs.extend((z[start], z[end], None))
    return xs, ys, zs


def _stage_offsets(blocks: list[DisplayBlock], root_segment_id: int) -> dict[int, tuple[float, float, float]]:
    """Return the stage offsets value.
    
    :param blocks: Block records used by the operation.
    :type blocks: list[DisplayBlock]
    :param root_segment_id: Identifier for the root segment.
    :type root_segment_id: int
    :returns: The result produced by the function.
    :rtype: dict[int, tuple[float, float, float]]
    """
    min_x = min(block.position[0] for block in blocks)
    min_y = min(block.position[1] for block in blocks)
    max_x = max(block.position[0] + block.size[0] for block in blocks)
    max_y = max(block.position[1] + block.size[1] for block in blocks)
    span_x = max_x - min_x
    span_y = max_y - min_y
    gap = max(5.0, 0.35 * max(span_x, span_y))

    segment_ids = sorted({block.segment_id for block in blocks})
    offsets: dict[int, tuple[float, float, float]] = {
        root_segment_id: (0.0, -(span_y + gap), 0.0)
    }
    non_root = [value for value in segment_ids if value != root_segment_id]
    if len(non_root) == 1:
        offsets[non_root[0]] = (0.0, span_y + gap, 0.0)
    else:
        for index, segment_id in enumerate(non_root):
            x_shift = (index - (len(non_root) - 1) / 2.0) * (0.25 * span_x)
            offsets[segment_id] = (x_shift, span_y + gap, 0.0)
    return offsets


def _translated(origin: tuple[float, float, float], offset: tuple[float, float, float]):
    """Return the translated value.
    
    :param origin: The origin value.
    :type origin: tuple[float, float, float]
    :param offset: The offset value.
    :type offset: tuple[float, float, float]
    :returns: The result produced by the function.
    """
    return tuple(origin[index] + offset[index] for index in range(3))




def write_true_build_player(
    *,
    output_dir: str | Path,
    catalog_path: str | Path,
    context_path: str | Path | None = None,
    html_path: str | Path | None = None,
    build_instructions_html_path: str | Path | None = None,
    timeline_csv_path: str | Path | None = None,
) -> Path:
    """Write true build player.
    
    :param output_dir: Directory where generated artifacts are written.
    :type output_dir: str | Path
    :param catalog_path: Catalog file path used by the operation.
    :type catalog_path: str | Path
    :param context_path: Path to the context file.
    :type context_path: str | Path | None
    :param html_path: Path to the html file.
    :type html_path: str | Path | None
    :param build_instructions_html_path: Path to the build instructions html file.
    :type build_instructions_html_path: str | Path | None
    :param timeline_csv_path: Path to the timeline csv file.
    :type timeline_csv_path: str | Path | None
    :returns: The result produced by the function.
    :rtype: Path
    """
    output_dir = Path(output_dir)
    context = load_task_context(context_path) if context_path else {}
    identity = model_identity(context, context_path=context_path) if context else None
    model_display_name = identity.display_name if identity else "BrickSmart Model"
    inventory_validation_path = output_dir / "inventory_validation.json"
    inventory_validation: dict[str, Any] = {}
    if inventory_validation_path.is_file():
        inventory_validation = json.loads(
            inventory_validation_path.read_text(encoding="utf-8")
        )
    inventory_mode = str(inventory_validation.get("inventory_mode") or "unknown")
    inventory_id = str(inventory_validation.get("inventory_id") or "not recorded")
    inventory_basis = (
        "Unlimited reference inventory"
        if inventory_mode == "unlimited"
        else f"Finite inventory: {inventory_id}"
        if inventory_mode == "finite"
        else "Inventory basis not recorded"
    )
    player_display_name = (
        f"{model_display_name} — unlimited inventory reference"
        if inventory_mode == "unlimited"
        else model_display_name
    )
    html_path = Path(html_path) if html_path else output_dir / "visualizations/proper_complete_build_steps.html"
    build_instructions_html_path = (
        Path(build_instructions_html_path)
        if build_instructions_html_path
        else output_dir / "build_instructions.html"
    )
    timeline_csv_path = (
        Path(timeline_csv_path)
        if timeline_csv_path
        else output_dir / "true_complete_build_steps.csv"
    )

    blocks = load_display_blocks(output_dir=output_dir, catalog_path=catalog_path, context=context)
    subassembly_steps = pd.read_csv(output_dir / "subassembly_build_steps.csv")
    assembly_steps = pd.read_csv(output_dir / "segment_connector_assembly_steps.csv")
    assembly_graph_path = output_dir / "structural_assembly_graph.csv"
    assembly_graph = pd.read_csv(assembly_graph_path) if assembly_graph_path.is_file() else pd.DataFrame()
    complete_steps_path = output_dir / "complete_build_steps.csv"
    complete_build_steps = (
        pd.read_csv(complete_steps_path)
        if complete_steps_path.is_file()
        else pd.DataFrame()
    )
    timeline = build_true_timeline(
        blocks=blocks,
        subassembly_steps=subassembly_steps,
        assembly_steps=assembly_steps,
        assembly_graph=assembly_graph,
        complete_build_steps=complete_build_steps,
        context=context,
    )

    root_segment_id = int(
        assembly_steps.sort_values("assembly_step").iloc[0]["attached_segment_id"]
    )
    stage_offsets = _stage_offsets(blocks, root_segment_id)
    by_id = {block.block_id: block for block in blocks}

    timeline_rows = []
    for step in timeline:
        timeline_rows.append(
            {
                "global_step": step.step,
                "phase": step.phase,
                "title": step.title,
                "instruction": step.instruction,
                "visible_block_ids": ",".join(str(value) for value in step.visible_block_ids),
                "final_position_segment_ids": ",".join(
                    str(value) for value in step.final_position_segment_ids
                ),
                "interface_id": step.interface_id,
            }
        )
    pd.DataFrame(timeline_rows).to_csv(timeline_csv_path, index=False)

    triangles_i = [0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 3, 3]
    triangles_j = [1, 2, 6, 7, 4, 5, 5, 6, 6, 7, 7, 4]
    triangles_k = [2, 3, 5, 6, 5, 1, 6, 2, 7, 3, 4, 0]

    figure = go.Figure()
    trace_indices: dict[int, tuple[int, int]] = {}
    initial_positions: dict[int, tuple[float, float, float] | None] = {
        block.block_id: None for block in blocks
    }
    for block in blocks:
        origin = block.position
        x, y, z = _cuboid_vertices(origin, block.size)
        mesh_index = len(figure.data)
        figure.add_trace(
            go.Mesh3d(
                x=x,
                y=y,
                z=z,
                i=triangles_i,
                j=triangles_j,
                k=triangles_k,
                color=block.color,
                opacity=0.95,
                flatshading=True,
                visible=False,
                name=f"Block {block.block_id}: {block.block_family}",
                hovertemplate=(
                    f"<b>Block {block.block_id}</b><br>Block type: {block.block_family}"
                    f"<br>Module: {block.segment_name}<br>Rotation: {block.rotation}°"
                    f"<br>Role: {block.block_role}<br>Male face: {block.male_face}<extra></extra>"
                ),
                lighting={"ambient": 0.62, "diffuse": 0.75, "specular": 0.12},
                showscale=False,
                legendgroup=block.block_family,
                showlegend=not any(
                    prior.block_family == block.block_family and prior.block_id < block.block_id
                    for prior in blocks
                ),
            )
        )
        edge_x, edge_y, edge_z = _wireframe_coordinates(origin, block.size)
        edge_index = len(figure.data)
        figure.add_trace(
            go.Scatter3d(
                x=edge_x,
                y=edge_y,
                z=edge_z,
                mode="lines",
                line={"color": "#111111", "width": 4},
                visible=False,
                hoverinfo="skip",
                showlegend=False,
                legendgroup=block.block_family,
            )
        )
        trace_indices[block.block_id] = (mesh_index, edge_index)

    frames: list[go.Frame] = []
    frame_positions: list[dict[int, tuple[float, float, float] | None]] = []
    for step in timeline:
        visible_ids = set(step.visible_block_ids)
        final_segments = set(step.final_position_segment_ids)
        positions: dict[int, tuple[float, float, float] | None] = {}
        frame_data: list[Any] = []
        frame_traces: list[int] = []
        for block in blocks:
            visible = block.block_id in visible_ids
            if not visible:
                positions[block.block_id] = None
                origin = block.position
            elif block.segment_id in final_segments:
                positions[block.block_id] = block.position
                origin = block.position
            else:
                origin = _translated(block.position, stage_offsets[block.segment_id])
                positions[block.block_id] = origin

            x, y, z = _cuboid_vertices(origin, block.size)
            edge_x, edge_y, edge_z = _wireframe_coordinates(origin, block.size)
            mesh_index, edge_index = trace_indices[block.block_id]
            frame_data.extend(
                [
                    go.Mesh3d(x=x, y=y, z=z, visible=visible),
                    go.Scatter3d(x=edge_x, y=edge_y, z=edge_z, visible=visible),
                ]
            )
            frame_traces.extend([mesh_index, edge_index])

        frame_positions.append(positions)
        frames.append(
            go.Frame(
                name=str(step.step),
                data=frame_data,
                traces=frame_traces,
                layout=go.Layout(
                    title={
                        "text": f"<b>{player_display_name} — {step.phase}</b>",
                        "x": 0.5,
                    },
                ),
            )
        )

    figure.frames = frames
    first_frame = frames[0]
    for index, update in enumerate(first_frame.data):
        figure.data[first_frame.traces[index]].update(update)

    slider_steps = [
        {
            "args": [
                [str(step.step)],
                {
                    "frame": {"duration": 450, "redraw": True},
                    "mode": "immediate",
                    "transition": {"duration": 250},
                },
            ],
            "label": str(step.step),
            "method": "animate",
        }
        for step in timeline
    ]

    phase_buttons = []
    seen_phase_labels: set[str] = set()
    for step in timeline:
        label = step.phase
        if label in seen_phase_labels:
            continue
        seen_phase_labels.add(label)
        phase_buttons.append(
            {
                "label": label,
                "method": "animate",
                "args": [
                    [str(step.step)],
                    {
                        "frame": {"duration": 0, "redraw": True},
                        "mode": "immediate",
                        "transition": {"duration": 0},
                    },
                ],
            }
        )

    all_origins = []
    for positions in frame_positions:
        for block_id, origin in positions.items():
            if origin is None:
                continue
            block = by_id[block_id]
            all_origins.extend(
                [
                    origin,
                    (
                        origin[0] + block.size[0],
                        origin[1] + block.size[1],
                        origin[2] + block.size[2],
                    ),
                ]
            )
    x_values = [value[0] for value in all_origins]
    y_values = [value[1] for value in all_origins]
    z_values = [value[2] for value in all_origins]
    pad = 3.0

    figure.update_layout(
        title={
            "text": f"<b>{player_display_name} — {timeline[0].phase}</b>",
            "x": 0.5,
        },
        template="plotly_white",
        width=1180,
        height=900,
        margin={"l": 10, "r": 10, "t": 105, "b": 165},
        legend={
            "title": {"text": "Block types"},
            "orientation": "h",
            "x": 0.5,
            "xanchor": "center",
            "y": 1.015,
            "yanchor": "bottom",
            "bgcolor": "rgba(255,255,255,0.0)",
        },
        scene={
            "domain": {"x": [0.0, 1.0], "y": [0.0, 0.88]},
            "xaxis": {"title": "X", "range": [min(x_values) - pad, max(x_values) + pad]},
            "yaxis": {"title": "Y", "range": [min(y_values) - pad, max(y_values) + pad]},
            "zaxis": {"title": "Z (up)", "range": [min(z_values) - 1, max(z_values) + 8]},
            "aspectmode": "data",
            "camera": {"eye": {"x": 1.65, "y": -2.1, "z": 1.35}},
        },
        sliders=[
            {
                "active": 0,
                "currentvalue": {"prefix": "True build step: ", "font": {"size": 15}},
                "pad": {"t": 50},
                "steps": slider_steps,
            }
        ],
        updatemenus=[
            {
                "type": "buttons",
                "direction": "left",
                "x": 0.0,
                "y": -0.02,
                "buttons": [
                    {
                        "label": "▶ Play",
                        "method": "animate",
                        "args": [
                            None,
                            {
                                "frame": {"duration": 950, "redraw": True},
                                "fromcurrent": True,
                                "transition": {"duration": 300},
                            },
                        ],
                    },
                    {
                        "label": "❚❚ Pause",
                        "method": "animate",
                        "args": [
                            [None],
                            {
                                "frame": {"duration": 0, "redraw": False},
                                "mode": "immediate",
                                "transition": {"duration": 0},
                            },
                        ],
                    },
                ],
            },
            {
                "type": "dropdown",
                "direction": "down",
                "x": 0.44,
                "y": -0.02,
                "showactive": True,
                "buttons": phase_buttons,
            },
        ],
    )

    segment_names = {block.segment_id: block.segment_name for block in blocks}
    external_steps: list[dict[str, Any]] = []
    for step in timeline:
        visible_ids = set(step.visible_block_ids)
        visible_segment_ids = sorted(
            {
                block.segment_id
                for block in blocks
                if block.block_id in visible_ids
            }
        )
        final_ids = set(step.final_position_segment_ids)
        external_steps.append(
            {
                "step": int(step.step),
                "phase": step.phase,
                "title": step.title,
                "instruction": step.instruction,
                "interface_id": step.interface_id,
                "final_modules": [
                    segment_names[value]
                    for value in visible_segment_ids
                    if value in final_ids
                ],
                "staged_modules": [
                    segment_names[value]
                    for value in visible_segment_ids
                    if value not in final_ids
                ],
            }
        )

    html_path.parent.mkdir(parents=True, exist_ok=True)
    build_instructions_html_path.parent.mkdir(parents=True, exist_ok=True)
    plot_div_id = "bricksmart-build-player"
    plot_html = figure.to_html(
        include_plotlyjs=True,
        full_html=False,
        config={"displaylogo": False, "responsive": True},
        auto_play=False,
        div_id=plot_div_id,
    )
    steps_json = json.dumps(external_steps, ensure_ascii=False).replace("</", "<\\/")
    page_html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{player_display_name} — BrickSmart build player</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f3f4f6; color: #111827; }}
  .player-shell {{ width: min(1220px, 100%); margin: 0 auto; padding: 12px; }}
  .plot-card {{ background: #fff; border: 1px solid #d1d5db; border-radius: 14px; overflow: hidden; box-shadow: 0 5px 18px rgba(0,0,0,.08); }}
  #{plot_div_id} {{ width: 100%; min-height: 720px; }}
  .step-panel {{ margin-top: 12px; background: #fff; border: 1px solid #d1d5db; border-radius: 14px; padding: 18px 20px; box-shadow: 0 3px 12px rgba(0,0,0,.06); }}
  .step-heading {{ display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; margin-bottom: 10px; }}
  .step-number {{ font-size: 1.1rem; font-weight: 800; }}
  .phase-chip {{ border-radius: 999px; padding: 4px 10px; background: #e5e7eb; font-size: .82rem; font-weight: 700; }}
  .step-title {{ margin: 0 0 8px; font-size: 1.18rem; }}
  .step-instruction {{ margin: 0; line-height: 1.5; }}
  .status-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }}
  .status-card {{ border: 1px solid #e5e7eb; border-radius: 10px; padding: 10px 12px; background: #f9fafb; }}
  .status-label {{ display: block; margin-bottom: 5px; color: #4b5563; font-size: .78rem; font-weight: 800; letter-spacing: .04em; text-transform: uppercase; }}
  .status-value {{ line-height: 1.4; overflow-wrap: anywhere; }}
  @media (max-width: 760px) {{
    .player-shell {{ padding: 6px; }}
    #{plot_div_id} {{ min-height: 610px; }}
    .step-panel {{ padding: 14px; }}
    .status-grid {{ grid-template-columns: 1fr; }}
  }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #111827; color: #f9fafb; }}
    .plot-card, .step-panel {{ background: #1f2937; border-color: #4b5563; }}
    .phase-chip {{ background: #374151; }}
    .status-card {{ background: #111827; border-color: #374151; }}
    .status-label {{ color: #d1d5db; }}
  }}
</style>
</head>
<body>
<main class="player-shell">
  <section class="plot-card" aria-label="Interactive 3D build model">{plot_html}</section>
  <section id="bricksmart-step-panel" class="step-panel" aria-live="polite">
    <div class="step-heading">
      <span id="bricksmart-step-number" class="step-number"></span>
      <span id="bricksmart-step-phase" class="phase-chip"></span>
    </div>
    <h2 id="bricksmart-step-title" class="step-title"></h2>
    <p id="bricksmart-step-instruction" class="step-instruction"></p>
    <div class="status-grid">
      <div class="status-card"><span class="status-label">Modules in final position</span><span id="bricksmart-final-modules" class="status-value"></span></div>
      <div class="status-card"><span class="status-label">Modules in staging area</span><span id="bricksmart-staged-modules" class="status-value"></span></div>
      <div class="status-card"><span class="status-label">Inventory basis</span><span class="status-value">{inventory_basis}</span></div>
    </div>
  </section>
</main>
<script>
(() => {{
  const steps = {steps_json};
  const plot = document.getElementById('{plot_div_id}');
  const byId = (id) => document.getElementById(id);
  const render = (index) => {{
    const bounded = Math.max(0, Math.min(Number(index) || 0, steps.length - 1));
    const step = steps[bounded];
    byId('bricksmart-step-number').textContent = `Step ${{step.step}} of ${{steps.length}}`;
    byId('bricksmart-step-phase').textContent = step.phase;
    byId('bricksmart-step-title').textContent = step.title;
    byId('bricksmart-step-instruction').textContent = step.instruction;
    byId('bricksmart-final-modules').textContent = step.final_modules.length ? step.final_modules.join(', ') : 'None yet';
    byId('bricksmart-staged-modules').textContent = step.staged_modules.length ? step.staged_modules.join(', ') : 'None';
  }};
  const activeSliderIndex = () => {{
    const sliders = plot && plot._fullLayout && plot._fullLayout.sliders;
    return sliders && sliders.length ? sliders[0].active : 0;
  }};
  render(0);
  if (plot && typeof plot.on === 'function') {{
    plot.on('plotly_sliderchange', (event) => {{
      const label = event && event.step ? Number(event.step.label) : NaN;
      render(Number.isFinite(label) ? label - 1 : activeSliderIndex());
    }});
    plot.on('plotly_animated', () => render(activeSliderIndex()));
    plot.on('plotly_buttonclicked', () => window.setTimeout(() => render(activeSliderIndex()), 0));
  }}
  window.addEventListener('resize', () => {{
    if (window.Plotly && plot) window.Plotly.Plots.resize(plot);
  }});
}})();
</script>
</body>
</html>
"""
    html_path.write_text(page_html, encoding="utf-8")
    if build_instructions_html_path.resolve() != html_path.resolve():
        build_instructions_html_path.write_text(page_html, encoding="utf-8")

    metadata = {
        "player": "model_agnostic_segment_module_assembly_player",
        "model_id": identity.model_id if identity else None,
        "model_display_name": model_display_name,
        "player_display_name": player_display_name,
        "inventory_id": inventory_id,
        "inventory_mode": inventory_mode,
        "inventory_basis": inventory_basis,
        "context_path": str(Path(context_path).resolve()) if context_path else None,
        "step_count": len(timeline),
        "fabrication_step_count": len(subassembly_steps),
        "assembly_action_count": len(assembly_steps),
        "root_segment_id": root_segment_id,
        "catalog_path": str(Path(catalog_path).resolve()),
        "output_html": str(build_instructions_html_path.resolve()),
        "legacy_player_html": str(html_path.resolve()),
        "timeline_csv": str(timeline_csv_path.resolve()),
        "behavior": {
            "phase_1": "build completed segment modules in separate staging areas",
            "phase_2": "place the contract-selected root module and attach every structural module",
            "phase_3": "attach every validated functional assembly declared by the task context",
            "catalog_colors": True,
            "black_block_outlines": True,
            "labels_outside_canvas": True,
            "step_instructions_outside_canvas": True,
            "scene_annotations": False,
        },
    }
    (output_dir / "true_build_player_manifest.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return html_path
