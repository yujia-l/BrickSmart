from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from bricksmart.contracts import (
    ModelContractError,
    build_semantic_target_preservation_report,
    validate_model_contract,
)
from bricksmart.functional import FunctionalAssemblySpec, default_registry
from bricksmart.regression import compare_checkpoint_manifests


def write_contract_fixture(
    tmp_path: Path,
    catalog_workbook: Path,
    *,
    provisional: bool = False,
    object_type: str = "bridge",
) -> tuple[Path, Path, Path]:
    source = tmp_path / "model.obj"
    source.write_text("o module\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    confirmations = tmp_path / "segment_confirmations.csv"
    with confirmations.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "segment_id", "confirmed_label", "confirmed_name",
                "confirmation_status", "confirmation_source", "semantic_group_id",
            ],
        )
        writer.writeheader()
        writer.writerow({
            "segment_id": 1,
            "confirmed_label": "main_structure",
            "confirmed_name": "Main Structure",
            "confirmation_status": "confirmed",
            "confirmation_source": "teacher_frontend",
            "semantic_group_id": "main_module",
        })
    context = tmp_path / "model_task_context.json"
    context.write_text(
        json.dumps({
            "schema_version": "diagnostic_only" if provisional else "bricksmart-model-contract-1.0",
            "task_id": "third_model_fixture",
            "model_id": "third_model_fixture",
            "object_type_hint": object_type,
            "model_source": {
                "uri": source.as_uri(),
                "model_id": "third_model_fixture",
                "filename": source.name,
            },
            "paths": {
                "catalog_xlsx": str(catalog_workbook),
            },
            "segment_semantics": {
                "labels_file": confirmations.name,
                "source_segment_groups": [{
                    "target_id": "main_module",
                    "source_segment_ids": [1],
                    "required": True,
                }],
            },
            "functional_attachments": [],
            "functional_assemblies": [],
        }, indent=2),
        encoding="utf-8",
    )
    return context, confirmations, source


def test_generic_contract_accepts_unlisted_object_type(tmp_path: Path, catalog_workbook: Path) -> None:
    context, confirmations, _ = write_contract_fixture(
        tmp_path, catalog_workbook, object_type="excavator_test_rig"
    )
    result = validate_model_contract(project_root=tmp_path, context_path=context)
    assert result.valid
    assert result.object_type_hint == "excavator_test_rig"
    assert result.authoritative_confirmation_count == 1
    assert result.confirmations_path == str(confirmations.resolve())
    assert result.source_model_uri == "model://third_model_fixture"
    assert result.source_model_kind == "model_store"


def test_provisional_contract_is_rejected(tmp_path: Path, catalog_workbook: Path) -> None:
    context, _, _ = write_contract_fixture(tmp_path, catalog_workbook, provisional=True)
    with pytest.raises(ModelContractError, match="provisional|diagnostic"):
        validate_model_contract(project_root=tmp_path, context_path=context)


def test_registry_selects_capability_not_model_name() -> None:
    registry = default_registry()
    spec = FunctionalAssemblySpec.from_mapping({
        "assembly_id": "tool_head",
        "assembly_type": "motion_connected_structural_subassembly",
        "display_name": "Tool Head",
        "anchor_segment_id": 2,
        "source_segment_ids": [5],
        "members": {
            "count": 2,
            "member_templates": [
                {"member_role": "inner", "offset_index": 0},
                {"member_role": "outer", "offset_index": 1},
            ],
        },
    })
    registry.validate([spec])
    assert "motion_connected_structural_subassembly" in registry.supported_types


def test_semantic_group_can_survive_member_merge() -> None:
    context = {
        "segment_semantics": {
            "source_segment_groups": [{
                "target_id": "central_module",
                "source_segment_ids": [1, 4, 7],
                "required": True,
                "preservation_mode": "any_member_or_merged",
            }]
        },
        "functional_attachments": [],
    }
    rows = [
        {"segment_id": str(segment_id), "confirmation_status": "confirmed", "semantic_group_id": "central_module"}
        for segment_id in (1, 4, 7)
    ]
    report = build_semantic_target_preservation_report(
        context=context,
        confirmation_rows=rows,
        raw_counts={1: 10, 4: 50, 7: 8},
        clean_counts={1: 0, 4: 70, 7: 0},
    )
    assert report["status"] == "PASS_SEMANTIC_TARGETS_PRESERVED"
    assert report["group_targets"][0]["preserved"] is True


def test_exact_source_member_group_detects_loss() -> None:
    context = {
        "segment_semantics": {
            "source_segment_groups": [{
                "target_id": "paired_targets",
                "source_segment_ids": [8, 9],
                "required": True,
                "preservation_mode": "all_members",
            }]
        },
        "functional_attachments": [],
    }
    rows = [
        {"segment_id": "8", "confirmation_status": "confirmed", "semantic_group_id": "paired_targets"},
        {"segment_id": "9", "confirmation_status": "confirmed", "semantic_group_id": "paired_targets"},
    ]
    report = build_semantic_target_preservation_report(
        context=context,
        confirmation_rows=rows,
        raw_counts={8: 5, 9: 5},
        clean_counts={8: 5, 9: 0},
    )
    assert report["status"] == "FAIL_REQUIRED_SEMANTIC_TARGETS_LOST"
    assert report["failed_required_target_ids"] == ["paired_targets"]


def test_checkpoint_comparison_ignores_absolute_paths() -> None:
    expected = {
        "context": {"path": "/old/context.json", "sha256": "a"},
        "catalog": {"path": "/old/catalog.xlsx", "sha256": "b"},
        "arrays": {"voxel_segment_clean.npy": {"sha256": "c"}},
    }
    actual = {
        "context": {"path": "/new/context.json", "sha256": "a"},
        "catalog": {"path": "/new/catalog.xlsx", "sha256": "b"},
        "arrays": {"voxel_segment_clean.npy": {"sha256": "c"}},
    }
    comparison = compare_checkpoint_manifests(expected, actual)
    assert comparison["match"] is True


def test_normalized_context_preserves_multiple_motion_subassemblies() -> None:
    from bricksmart.runtime.context import normalize_task_context

    payload = {
        "task_id": "multi_tool_fixture",
        "model_id": "multi_tool_fixture",
        "functional_assemblies": [
            {
                "assembly_id": "tool_a",
                "assembly_type": "motion_connected_structural_subassembly",
                "anchor_segment_id": 1,
                "source_segment_ids": [2],
                "connector": {"required_block_family": "rotation_block"},
                "members": {
                    "count": 1,
                    "required_block_family": "standard_2x2x2",
                    "member_templates": [
                        {"member_role": "tool", "offset_index": 0, "face_roles": {}}
                    ],
                },
            },
            {
                "assembly_id": "tool_b",
                "assembly_type": "motion_connected_structural_subassembly",
                "anchor_segment_id": 1,
                "source_segment_ids": [3],
                "connector": {"required_block_family": "hinge_block"},
                "members": {
                    "count": 1,
                    "required_block_family": "standard_2x2x2",
                    "member_templates": [
                        {"member_role": "tool", "offset_index": 0, "face_roles": {}}
                    ],
                },
            },
        ],
    }
    normalized = normalize_task_context(payload)
    rows = normalized["segment_assembly"]["custom_functional_subassemblies"]
    assert [row["assembly_id"] for row in rows] == ["tool_a", "tool_b"]
    assert "custom_functional_subassembly" not in normalized["segment_assembly"]
