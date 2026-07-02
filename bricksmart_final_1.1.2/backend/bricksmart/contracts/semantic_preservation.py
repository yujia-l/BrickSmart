from __future__ import annotations

from typing import Any, Mapping

AUTHORITATIVE_CONFIRMATION_STATUSES = {"confirmed", "corrected", "approved", "accepted"}


def _segment_id(row: Mapping[str, Any]) -> int | None:
    for key in ("segment_id", "source_segment_id", "id"):
        value = row.get(key)
        if value not in (None, ""):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return None
    return None


def _status(row: Mapping[str, Any], default: str = "unresolved") -> str:
    return str(row.get("confirmation_status", row.get("status", default)) or default).strip().lower()


def _group_source_ids(
    context: Mapping[str, Any], confirmation_rows: list[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    semantics = context.get("segment_semantics", {}) or {}
    groups: list[dict[str, Any]] = []
    declared = semantics.get("source_segment_groups", semantics.get("semantic_groups", [])) or []
    for index, group in enumerate(declared):
        if not isinstance(group, Mapping):
            continue
        ids = [int(value) for value in group.get("source_segment_ids", [])]
        if ids:
            groups.append({
                "target_id": str(group.get("target_id", group.get("group_id", f"semantic_group_{index+1}"))),
                "target_type": "semantic_group",
                "source_segment_ids": ids,
                "required": bool(group.get("required", True)),
                "preservation_mode": str(group.get("preservation_mode", "any_member_or_merged")),
            })

    for attachment in context.get("functional_attachments", []) or []:
        grouping = attachment.get("physical_target_grouping", {}) or {}
        for index, group in enumerate(grouping.get("manual_groups", []) or []):
            ids = [int(value) for value in group.get("source_segment_ids", [])]
            if ids:
                groups.append({
                    "target_id": str(group.get("physical_target_id", f"{attachment.get('attachment_id','attachment')}_{index+1}")),
                    "target_type": "functional_target",
                    "source_segment_ids": ids,
                    "required": bool(attachment.get("required", False)),
                    "preservation_mode": str(group.get("preservation_mode", "any_member_or_merged")),
                })

    for assembly in context.get("functional_assemblies", []) or []:
        ids = [int(value) for value in assembly.get("source_segment_ids", []) or []]
        if ids:
            groups.append({
                "target_id": str(assembly.get("assembly_id", assembly.get("physical_target_id", "functional_subassembly"))),
                "target_type": "functional_subassembly",
                "source_segment_ids": ids,
                "required": bool(assembly.get("required", assembly.get("enabled", True))),
                "preservation_mode": str(assembly.get("preservation_mode", "any_member_or_merged")),
            })

    grouped: dict[str, list[int]] = {}
    for row in confirmation_rows:
        sid = _segment_id(row)
        group_id = row.get("physical_target_id", row.get("semantic_group_id", row.get("group_id", "")))
        if sid is not None and str(group_id or "").strip():
            grouped.setdefault(str(group_id).strip(), []).append(sid)
    for group_id, ids in sorted(grouped.items()):
        if not any(group["target_id"] == group_id for group in groups):
            groups.append({
                "target_id": group_id,
                "target_type": "confirmation_group",
                "source_segment_ids": sorted(set(ids)),
                "required": True,
                "preservation_mode": "any_member_or_merged",
            })
    return groups


def build_semantic_target_preservation_report(
    *,
    context: Mapping[str, Any],
    confirmation_rows: list[Mapping[str, Any]],
    raw_counts: Mapping[int | str, int],
    clean_counts: Mapping[int | str, int],
) -> dict[str, Any]:
    raw = {int(key): int(value) for key, value in raw_counts.items()}
    clean = {int(key): int(value) for key, value in clean_counts.items()}
    groups = _group_source_ids(context, confirmation_rows)

    group_rows: list[dict[str, Any]] = []
    failed_required: list[str] = []
    covered_source_ids: set[int] = set()
    for group in groups:
        ids = tuple(sorted(set(int(value) for value in group["source_segment_ids"])))
        covered_source_ids.update(ids)
        raw_total = sum(raw.get(sid, 0) for sid in ids)
        clean_total = sum(clean.get(sid, 0) for sid in ids)
        surviving_members = [sid for sid in ids if clean.get(sid, 0) > 0]
        mode = group["preservation_mode"].strip().lower()
        preserved = (
            len(surviving_members) == len(ids)
            if mode in {"all_members", "exact_source_members"}
            else clean_total > 0
        )
        if group["required"] and not preserved:
            failed_required.append(group["target_id"])
        group_rows.append({
            **group,
            "source_segment_ids": list(ids),
            "raw_voxel_count": raw_total,
            "clean_voxel_count": clean_total,
            "surviving_source_segment_ids": surviving_members,
            "preserved": preserved,
        })

    authoritative_ids = {
        sid for row in confirmation_rows
        if _status(row) in AUTHORITATIVE_CONFIRMATION_STATUSES
        and (sid := _segment_id(row)) is not None
    }
    ungrouped_required = sorted(authoritative_ids - covered_source_ids)
    missing_ungrouped = [sid for sid in ungrouped_required if clean.get(sid, 0) <= 0]
    status = (
        "PASS_SEMANTIC_TARGETS_PRESERVED"
        if not failed_required and not missing_ungrouped
        else "FAIL_REQUIRED_SEMANTIC_TARGETS_LOST"
    )
    return {
        "status": status,
        "group_targets": group_rows,
        "failed_required_target_ids": failed_required,
        "ungrouped_authoritative_source_segment_ids": ungrouped_required,
        "missing_ungrouped_authoritative_source_segment_ids": missing_ungrouped,
        "note": (
            "Raw OBJ groups may be merged into a confirmed semantic or functional target; "
            "preservation is evaluated at the contract-declared target level."
        ),
    }
