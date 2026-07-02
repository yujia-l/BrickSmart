"""Instruction planning helpers for physicalized BrickSmart block output."""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from build3d.block_decomposer import BlockInstance, block_inventory_summary


def generate_row_steps(blocks: list[BlockInstance], max_steps: int = 8) -> list[list[BlockInstance]]:
    row_map: dict[int, list[BlockInstance]] = defaultdict(list)
    for block in blocks:
        row_map[block.position[1]].append(block)
    rows = [sorted(row_map[key], key=lambda b: (b.position[2], b.position[0])) for key in sorted(row_map)]
    if len(rows) <= max_steps:
        return rows
    chunk_size = math.ceil(len(rows) / max_steps)
    return [sum(rows[i : i + chunk_size], []) for i in range(0, len(rows), chunk_size)]


def describe_instruction_step(
    step_number: int,
    image_path: Path,
    multiview_path: Path | None,
    step_blocks: list[BlockInstance],
    previous_blocks: list[BlockInstance],
    segment_lookup: dict[int, str],
    artifact_label: str,
    connector_notes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    segment_ids = sorted({block.segment_id for block in step_blocks})
    segment_labels = [segment_lookup.get(segment_id, f"segment {segment_id}") for segment_id in segment_ids]
    label_text = natural_join(segment_labels) if segment_labels else "the next section"
    inventory = block_inventory_summary(step_blocks)
    piece_text = inventory_sentence(inventory)
    new_count = len(step_blocks)
    built_count = len(previous_blocks) + new_count
    connectors = matching_connector_notes(segment_ids, connector_notes or [])
    connector_text = connector_instruction_text(connectors)

    return {
        "step_number": step_number,
        "title": f"Build {label_text}",
        "image_path": str(image_path),
        "multiview_path": str(multiview_path) if multiview_path else None,
        "segments": segment_ids,
        "segment_labels": segment_labels,
        "new_block_count": new_count,
        "cumulative_block_count": built_count,
        "inventory": inventory,
        "connector_notes": connectors,
        "teacher_instruction": (
            f"Add {new_count} block{'s' if new_count != 1 else ''} for {label_text}. "
            f"Use the highlighted blocks to extend the {artifact_label}; the faded blocks show what should already be built. "
            f"{connector_text}"
        ).strip(),
        "student_instruction": (
            f"Find {piece_text}. Put the bright pieces on the model so it matches the picture, "
            "then check that the shape still looks like the target build."
        ),
        "teacher_check": (
            "Confirm the pieces look like physical BrickSmart blocks, connect to the previous step, "
            "and preserve the intended segment shape before moving on."
        ),
    }


def matching_connector_notes(segment_ids: list[int], connector_notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segment_set = set(segment_ids)
    matches = []
    for note in connector_notes:
        values = {int(value) for value in note.get("segments", []) if str(value).isdigit()}
        if segment_set & values:
            matches.append(note)
    return matches


def connector_instruction_text(connector_notes: list[dict[str, Any]]) -> str:
    if not connector_notes:
        return ""
    phrases = []
    for note in connector_notes[:3]:
        part = note.get("part_name", "moving part")
        connector = str(note.get("connector_type", "connector")).replace("_", " ")
        status = "candidate site detected" if note.get("status") == "candidate" else "needs teacher placement review"
        phrases.append(f"For {part}, reserve a {connector} location ({status}).")
    return " ".join(phrases)


def inventory_sentence(inventory: list[dict[str, Any]]) -> str:
    if not inventory:
        return "the next pieces"
    pieces = []
    for item in inventory:
        quantity = int(item["quantity"])
        piece = str(item["piece"])
        color = str(item.get("color") or "").strip()
        if quantity != 1 and piece.endswith("block"):
            piece = f"{piece}s"
        label = f"{color} {piece}".strip()
        pieces.append(f"{quantity} x {label}")
    return natural_join(pieces)


def natural_join(values: list[str]) -> str:
    clean = [value for value in values if value]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} and {clean[1]}"
    return f"{', '.join(clean[:-1])}, and {clean[-1]}"
