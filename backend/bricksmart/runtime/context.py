"""Runtime context loading for validated build executions.

This module combines contract, inventory, catalog, and run-store inputs into the
structured context consumed by planning services.
"""

from __future__ import annotations

import copy
import json

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class ModelIdentity:
    model_id: str
    task_id: str
    object_type_hint: str
    display_name: str


def model_identity(payload: Mapping[str, Any], *, context_path: str | Path | None = None) -> ModelIdentity:
    """Return the model identity value.
    
    :param payload: Payload data to process.
    :type payload: Mapping[str, Any]
    :param context_path: Path to the context file.
    :type context_path: str | Path | None
    :returns: The result produced by the function.
    :rtype: ModelIdentity
    """
    task_id = str(payload.get("task_id") or "").strip()
    object_type = str(payload.get("object_type_hint") or "").strip()
    explicit = str(payload.get("model_id") or "").strip()
    stem = Path(context_path).stem if context_path else "model"
    model_id = explicit or task_id or object_type or stem
    display_name = str(
        payload.get("display_name")
        or payload.get("object_description")
        or object_type
        or model_id
    ).strip()
    return ModelIdentity(
        model_id=model_id,
        task_id=task_id or model_id,
        object_type_hint=object_type,
        display_name=display_name,
    )


def _default_member_templates(count: int, layout_axis: str) -> list[dict[str, Any]]:
    """Generate the default three-member linear layout when templates are omitted.

    New contracts should provide ``member_templates`` explicitly.
    """
    if count != 3:
        return []
    axis = str(layout_axis or "Z").upper()
    forward = f"+{axis}"
    backward = f"-{axis}"
    common = {
        "+X": "female", "-X": "female",
        "+Y": "female", "-Y": "female",
        "+Z": "female", "-Z": "female",
    }
    lower = dict(common)
    lower[forward] = "male"
    center = dict(common)
    center[forward] = "male"
    upper = dict(common)
    # Historical endpoint orientation is declarative after normalization.
    upper["+X"] = "male"
    return [
        {"member_role": "center", "offset_index": 0, "face_roles": center},
        {"member_role": "lower", "offset_index": -1, "face_roles": lower},
        {"member_role": "upper", "offset_index": 1, "face_roles": upper},
    ]


def _normalize_motion_subassembly(assembly: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize motion subassembly.
    
    :param assembly: The assembly value.
    :type assembly: Mapping[str, Any]
    :returns: The computed result.
    :rtype: dict[str, Any]
    """
    result = copy.deepcopy(dict(assembly))
    result.setdefault("assembly_type", "motion_connected_structural_subassembly")
    result.setdefault("assembly_id", result.get("physical_target_id", "functional_subassembly"))
    result.setdefault("physical_target_id", result["assembly_id"])
    result.setdefault("display_name", str(result["assembly_id"]).replace("_", " ").title())

    connector = copy.deepcopy(result.get("connector") or {})
    connector.setdefault("motion_type", result.get("connector_motion_type", "free_rotation"))
    connector.setdefault("axis", result.get("connector_axis", "Y"))
    connector.setdefault("placement_policy", result.get("placement_policy", "outside_anchor_face_centered_on_symmetry_plane"))
    connector.setdefault("required_block_family", result.get("connector_required_block_family", "rotation_block"))
    result["connector"] = connector

    members = copy.deepcopy(result.get("members") or {})
    members.setdefault("count", int(result.get("structural_block_count", 0) or 0))
    members.setdefault("layout_axis", result.get("layout_axis", "Z"))
    members.setdefault("catalog_query", result.get("structural_block_catalog_query", {}))
    members.setdefault("required_block_family", result.get("required_block_family", ""))
    templates = members.get("member_templates") or result.get("member_templates")
    if not templates:
        templates = _default_member_templates(int(members["count"]), str(members["layout_axis"]))
    members["member_templates"] = list(templates or [])
    result["members"] = members

    result.setdefault("anchor_segment_id", -1)
    result.setdefault("source_segment_ids", [])
    result["validation"] = copy.deepcopy(result.get("validation") or {})
    result.setdefault("enabled", True)
    result.setdefault("instruction_templates", {
        "connector": "Attach {display_name} connector block {block_ids} to {anchor_name}.",
        "member": "Add block {block_ids} to the {display_name} subassembly.",
    })
    return result


def normalize_task_context(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a normalized, model-neutral task context.

    Runtime behavior is selected entirely from contract capabilities and catalog data.
    """
    context = copy.deepcopy(dict(payload))
    identity = model_identity(context)
    context.setdefault("model_id", identity.model_id)
    context.setdefault("display_name", identity.display_name)

    model_source = context.get("model_source")
    if isinstance(model_source, str):
        context["model_source"] = {"uri": model_source, "model_id": identity.model_id}
    elif isinstance(model_source, dict):
        context["model_source"].setdefault("model_id", identity.model_id)

    assemblies = [copy.deepcopy(dict(row)) for row in context.get("functional_assemblies", []) or []]
    normalized: list[dict[str, Any]] = []
    for row in assemblies:
        assembly_type = str(row.get("assembly_type") or "").strip().lower()
        if assembly_type in {"motion_connected_structural_subassembly", "motion_structural_subassembly"}:
            normalized.append(_normalize_motion_subassembly(row))
        else:
            normalized.append(row)
    context["functional_assemblies"] = normalized

    # Capability instances remain a list. The runtime may instantiate any
    # number of motion-connected structural subassemblies declared by a model.
    compatible = [
        row for row in normalized
        if row.get("enabled", True)
        and str(row.get("assembly_type", "")).lower()
        == "motion_connected_structural_subassembly"
    ]
    segment_assembly = context.setdefault("segment_assembly", {})
    segment_assembly["custom_functional_subassemblies"] = compatible
    return context


def load_task_context(path: str | Path) -> dict[str, Any]:
    """Load task context.
    
    :param path: Filesystem path used by the operation.
    :type path: str | Path
    :returns: The loaded data.
    :rtype: dict[str, Any]
    """
    context_path = Path(path).expanduser().resolve()
    payload = json.loads(context_path.read_text(encoding="utf-8"))
    return normalize_task_context(payload)
