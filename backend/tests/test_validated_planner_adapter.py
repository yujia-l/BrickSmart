import csv
import json

import numpy as np

from build3d.validated_planner_adapter import (
    DEFAULT_ALLOWED_SEGMENT_LABELS,
    ENABLED_SOLVER_FAMILIES,
    _normalize_result,
    _source_segment_groups_from_rows,
    _utf8_obj_copy,
    _write_segment_confirmations,
    _write_task_context,
    apply_catalog_constraints,
    semantic_segment_targets,
)
from build3d.notebook_outputs import coarsen_to_validated_segment_budget
from build3d.pipeline import (
    _automatic_model_recovery_context,
    _distribute_source_segments,
    _rodin_api_prompt,
    _rodin_prompt,
    _validated_planner_blocker,
)


def test_catalog_constraints_default_to_standard_kit_and_supported_families():
    context = {
        "artifact_label": "delivery airplane",
        "artifact_family": "vehicle",
        "parts": [
            {"part_name": "body", "movement": "static"},
            {"part_name": "propeller", "movement": "spinning"},
            {"part_name": "landing gear", "movement": "rolling"},
        ],
    }

    enriched = apply_catalog_constraints(context)

    assert enriched["inventory_mode"] == "standard_kit"
    assert enriched["active_families"]["solver_enabled"] == ENABLED_SOLVER_FAMILIES
    assert enriched["active_families"]["structural"] == [
        "standard_2x2x2",
        "standard_2x3x2",
        "standard_2x4x2",
    ]
    assert "bucket" not in enriched["active_families"]["solver_enabled"]
    assert "angle_joint" not in enriched["active_families"]["solver_enabled"]


def test_movement_parts_generate_metadata_not_final_instructions():
    context = {
        "artifact_label": "delivery airplane",
        "parts": [
            {"part_name": "propeller", "movement": "spinning"},
            {"part_name": "wheels", "movement": "rolling"},
            {"part_name": "door", "movement": "pivoting"},
        ],
    }

    enriched = apply_catalog_constraints(context)

    assert {"rotation_block"} == set(enriched["connector_rules"][0]["allowed_connector_families"])
    assert any(rule["allowed_connector_families"] == ["hinge_block"] for rule in enriched["connector_rules"])
    assert enriched["functional_attachments"][0]["role"] == "wheel"
    assert enriched["functional_attachments"][0]["allowed_families"] == ["big_wheel", "small_wheel"]
    assert set(DEFAULT_ALLOWED_SEGMENT_LABELS).issuperset(
        {"body", "wing_left", "wheel_right", "propeller", "unknown"}
    )


def test_catalog_constraints_include_standard_kit_buildability_budget():
    enriched = apply_catalog_constraints({"artifact_label": "delivery airplane", "parts": []})

    assert enriched["buildability_budget"]["inventory_mode"] == "standard_kit"
    assert enriched["buildability_budget"]["max_validated_blocks"] == 32
    assert enriched["buildability_budget"]["max_semantic_segments"] == 5
    assert enriched["buildability_budget"]["max_moving_parts"] == 1


def test_standard_kit_blocks_unstable_voxelization_before_validated_planner():
    context = apply_catalog_constraints(
        {
            "artifact_label": "delivery airplane",
            "build_constraints": {"inventory_mode": "standard_kit"},
            "parts": [{"part_name": "propeller", "movement": "spinning"}],
        }
    )
    notebook_outputs = {
        "block_count": 18,
        "source_segment_count": 7,
        "surviving_segment_count": 1,
        "segment_preservation_fraction": 0.14,
        "recommended_next_voxel_size": 32,
    }

    blocker = _validated_planner_blocker(context, notebook_outputs)

    assert blocker is not None
    assert blocker["build_status"] == "NEEDS_SIMPLER_MODEL"
    assert blocker["final_claim_valid"] is False
    assert blocker["segment_viability"]["source_segment_count"] == 7


def test_standard_kit_blocks_too_many_confirmed_segments_before_validated_planner():
    context = apply_catalog_constraints(
        {
            "artifact_label": "delivery airplane",
            "build_constraints": {"inventory_mode": "standard_kit"},
            "parts": [{"part_name": "propeller", "movement": "spinning"}],
        }
    )
    notebook_outputs = {
        "block_count": 24,
        "segment_count": 4,
        "surviving_segment_count": 4,
        "segment_preservation_fraction": 1.0,
    }
    segment_rows = [{"segment_id": index, "label": f"part_{index}"} for index in range(1, 11)]

    blocker = _validated_planner_blocker(context, notebook_outputs, segment_rows)

    assert blocker is not None
    assert blocker["build_status"] == "NEEDS_SIMPLER_MODEL"
    assert blocker["segment_viability"]["confirmed_segment_count"] == 10
    assert blocker["segment_viability"]["physical_segment_count"] == 4
    assert "standard-kit validation target is 5 or fewer" in blocker["reason"]


def test_standard_kit_blocks_segment_overage_when_block_budget_fails():
    context = apply_catalog_constraints(
        {
            "artifact_label": "delivery airplane",
            "build_constraints": {"inventory_mode": "standard_kit"},
            "parts": [{"part_name": "propeller", "movement": "spinning"}],
        }
    )
    notebook_outputs = {
        "block_count": 40,
        "segment_count": 8,
        "surviving_segment_count": 8,
        "segment_preservation_fraction": 1.0,
    }
    segment_rows = [{"segment_id": index, "label": f"part_{index}"} for index in range(1, 9)]

    blocker = _validated_planner_blocker(context, notebook_outputs, segment_rows)

    assert blocker is not None
    assert blocker["build_status"] == "NEEDS_SIMPLER_MODEL"
    assert blocker["segment_viability"]["confirmed_segment_count"] == 8
    assert "standard-kit preview budget is 32" in blocker["reason"]
    assert "standard-kit validation target is 5 or fewer" in blocker["reason"]


def test_semantic_preservation_failure_normalizes_to_simpler_model(tmp_path):
    summary = {
        "final_claim_valid": False,
        "final_status": "invalid_inventory_or_build_claim",
        "semantic_target_preservation": {
            "status": "FAIL_REQUIRED_SEMANTIC_TARGETS_LOST",
            "ungrouped_authoritative_source_segment_ids": [1, 2, 3],
            "missing_ungrouped_authoritative_source_segment_ids": [3],
        },
    }

    normalized = _normalize_result(summary, tmp_path)

    assert normalized["build_status"] == "NEEDS_SIMPLER_MODEL"
    assert normalized["final_claim_valid"] is False
    assert normalized["segment_viability"]["missing_segment_ids"] == [3]
    assert "Regenerate a simpler model" in normalized["recommendation"]


def test_planner_timeout_is_reported_before_partial_preservation_artifacts(tmp_path):
    summary = {
        "final_claim_valid": False,
        "timed_out": True,
        "timeout_seconds": 300,
        "semantic_target_preservation": {
            "status": "FAIL_REQUIRED_SEMANTIC_TARGETS_LOST",
        },
    }

    normalized = _normalize_result(summary, tmp_path)

    assert normalized["build_status"] == "PLANNER_TIMEOUT"
    assert "300-second interactive limit" in normalized["reason"]
    assert "could not preserve" not in normalized["reason"]


def test_rodin_api_prompt_is_compacted_under_hyper3d_limit():
    context = {
        "artifact_label": "Flying Delivery Vehicle",
        "parts": [
            {"part_name": "Propeller", "movement": "spinning"},
            {"part_name": "Body", "movement": "static"},
            {"part_name": "Wings", "movement": "static"},
            {"part_name": "Cargo Compartment", "movement": "static"},
            {"part_name": "Tail", "movement": "static"},
        ],
    }
    long_prompt = " ".join(["detailed classroom lesson and model prompt"] * 80)

    prompt = _rodin_api_prompt(context, long_prompt)

    assert len(prompt) <= 1000
    assert "Flying Delivery Vehicle" in prompt
    assert "Propeller spinning" in prompt
    assert "2x2-compatible" in prompt


def test_standard_kit_rodin_prompt_groups_teacher_static_details():
    context = {
        "artifact_label": "Flying Delivery Vehicle",
        "parts": [
            {"part_name": "Propeller", "movement": "spinning"},
            {"part_name": "Body", "movement": "static"},
            {"part_name": "Wings", "movement": "static"},
            {"part_name": "Cargo Compartment", "movement": "static"},
            {"part_name": "Tail", "movement": "static"},
        ],
    }

    targets = semantic_segment_targets(context)
    prompt = _rodin_prompt(context)

    assert len(targets) <= 5
    assert any("moving feature" in target for target in targets)
    assert any("merged" in target for target in targets)
    assert not any("connector" in target.lower() for target in targets)
    assert not any("decoration" in target.lower() for target in targets)
    assert "use only these large semantic regions" in prompt
    assert "Merge cargo, windows, tail" in prompt
    assert "do not create separate connector" in prompt
    assert "clearly separated segments for: Propeller, Body, Wings, Cargo Compartment, Tail" not in prompt


def test_auto_recovery_context_collapses_static_parts_for_second_rodin_attempt():
    context = {
        "artifact_label": "Flying Delivery Vehicle",
        "parts": [
            {"part_name": "Propeller", "movement": "spinning"},
            {"part_name": "Body", "movement": "static"},
            {"part_name": "Wings", "movement": "static"},
            {"part_name": "Cargo Compartment", "movement": "static"},
            {"part_name": "Tail", "movement": "static"},
        ],
        "build_constraints": {
            "inventory_mode": "standard_kit",
            "max_validated_blocks": 32,
            "max_semantic_segments": 5,
        },
    }
    build_plan = {
        "validated_planner": {
            "final_claim_valid": False,
            "build_status": "NEEDS_SIMPLER_MODEL",
            "final_block_count": 20,
            "segment_viability": {
                "source_segment_count": 8,
                "physical_segment_count": 8,
                "max_validated_blocks": 32,
                "max_semantic_segments": 5,
            },
        }
    }

    recovered = _automatic_model_recovery_context(context, build_plan, 1)

    assert recovered["build_constraints"]["max_semantic_segments"] == 4
    assert recovered["build_constraints"]["max_validated_blocks"] == 28
    assert len(recovered["parts"]) <= 4
    assert any(part["part_name"] == "merged body/fuselage" for part in recovered["parts"])
    assert not any(part["part_name"] == "Cargo Compartment" for part in recovered["parts"])
    assert "exactly 4 or fewer large visible regions" in recovered["rodin_prompt"]
    assert "No separate tail, cargo compartment" in recovered["rodin_prompt"]


def test_utf8_obj_copy_replaces_non_utf8_bytes(tmp_path):
    source = tmp_path / "source.obj"
    source.write_bytes(b"o model\nv 0 0 0\n# bad byte: \x97\n")

    sanitized = _utf8_obj_copy(source, tmp_path)

    text = sanitized.read_text(encoding="utf-8")
    assert "o model" in text
    assert "\ufffd" in text


def test_semantic_grouping_maps_every_bang_source_before_voxel_planning():
    voxel_segment = np.array(
        [
            [[1, 2], [3, 4]],
            [[5, 6], [0, 0]],
        ],
        dtype=np.int32,
    )
    rows = [
        {
            "segment_id": 1,
            "semantic_group_id": "moving_propeller",
            "source_segment_grouping": "coarse_validated_region",
            "source_segment_ids": [1, 2],
            "movement": "spinning",
        },
        {
            "segment_id": 2,
            "semantic_group_id": "merged_body",
            "source_segment_grouping": "coarse_validated_region",
            "source_segment_ids": [3, 4, 5, 6],
            "movement": "static",
        },
    ]

    grouped = coarsen_to_validated_segment_budget(voxel_segment, rows, max_segment_count=5)

    assert grouped["strategy"] == "contract_semantic_groups"
    assert grouped["label_mapping_preserved"] is True
    assert grouped["ending_segment_count"] == 2
    assert set(np.unique(grouped["voxel_segment"])) == {0, 1, 2}
    assert np.all(grouped["voxel_segment"][voxel_segment == 1] == 1)
    assert np.all(grouped["voxel_segment"][voxel_segment == 6] == 2)


def test_grouped_voxelization_blocks_when_teacher_semantic_region_is_lost():
    context = apply_catalog_constraints(
        {
            "artifact_label": "delivery airplane",
            "parts": [{"part_name": "propeller", "movement": "spinning"}],
        }
    )
    notebook_outputs = {
        "block_count": 20,
        "source_segment_count": 6,
        "segment_count": 2,
        "surviving_segment_count": 2,
        "segment_preservation_fraction": 2 / 3,
        "semantic_target_survival": {
            "semantic_target_count": 3,
            "surviving_semantic_target_count": 2,
            "preservation_fraction": 2 / 3,
        },
    }
    rows = [
        {
            "segment_id": index,
            "source_segment_grouping": "coarse_validated_region",
            "source_segment_ids": [index],
        }
        for index in range(1, 4)
    ]

    blocker = _validated_planner_blocker(context, notebook_outputs, rows)

    assert blocker is not None
    assert "teacher-approved regions" in blocker["reason"]
    assert blocker["segment_viability"]["semantic_target_count"] == 3


def test_v125_contract_uses_csv_catalog_and_raw_source_groups(tmp_path):
    rows = [
        {
            "segment_id": 1,
            "semantic_group_id": "moving_propeller",
            "function": "propeller",
            "source_name": "propeller",
            "source_segment_grouping": "coarse_validated_region",
            "source_segment_ids": [1, 4],
            "label": "propeller",
        },
        {
            "segment_id": 2,
            "semantic_group_id": "merged_body",
            "function": "merged body",
            "source_name": "body",
            "source_segment_grouping": "coarse_validated_region",
            "source_segment_ids": [2, 3],
            "label": "body",
        },
    ]
    context = apply_catalog_constraints(
        {
            "artifact_label": "delivery airplane",
            "parts": [{"part_name": "propeller", "movement": "spinning"}],
        }
    )
    confirmations_path = _write_segment_confirmations(tmp_path, rows, context)

    with confirmations_path.open(newline="", encoding="utf-8") as handle:
        confirmations = list(csv.DictReader(handle))
    groups = _source_segment_groups_from_rows(rows)

    assert {int(row["segment_id"]) for row in confirmations} == {1, 2, 3, 4}
    assert groups[0]["source_segment_ids"] == [1, 4]

    class ModelRecord:
        model_id = "model-1"
        canonical_uri = "file:///model.obj"
        sha256 = "abc123"

    task_path = _write_task_context(
        planner_dir=tmp_path,
        context=context,
        obj_path=tmp_path / "model.obj",
        model_record=ModelRecord(),
        confirmations_path=confirmations_path,
        coarse_grouped=True,
        segment_rows=rows,
    )
    payload = json.loads(task_path.read_text(encoding="utf-8"))

    assert payload["paths"]["catalog_csv"] == "../block_catalog/block_definitions.csv"
    assert "catalog_xlsx" not in payload["paths"]
    assert payload["segment_semantics"]["source_segment_groups"] == groups


def test_generic_bang_groups_are_collapsed_by_geometry_into_teacher_regions():
    center = (0.0, 0.0, 0.0)
    source_segments = [
        {
            "segment_id": 1,
            "name": "root.0",
            "vertex_count": 800,
            "bbox_volume": 10.0,
            "extents": (2.0, 4.0, 3.0),
            "centroid": center,
            "global_centroid": center,
        },
        {
            "segment_id": 2,
            "name": "root.1",
            "vertex_count": 300,
            "bbox_volume": 3.0,
            "extents": (6.0, 3.0, 0.5),
            "centroid": (-3.0, 0.0, 0.0),
            "global_centroid": center,
        },
        {
            "segment_id": 3,
            "name": "root.2",
            "vertex_count": 310,
            "bbox_volume": 3.0,
            "extents": (6.0, 3.0, 0.5),
            "centroid": (3.0, 0.0, 0.0),
            "global_centroid": center,
        },
        {
            "segment_id": 4,
            "name": "root.3",
            "vertex_count": 120,
            "bbox_volume": 1.0,
            "extents": (2.0, 2.0, 1.0),
            "centroid": (0.0, 0.0, 2.0),
            "global_centroid": center,
        },
        {
            "segment_id": 5,
            "name": "root.4",
            "vertex_count": 60,
            "bbox_volume": 0.5,
            "extents": (1.0, 0.5, 1.0),
            "centroid": (-5.0, 0.0, 0.0),
            "global_centroid": center,
        },
        {
            "segment_id": 6,
            "name": "root.5",
            "vertex_count": 62,
            "bbox_volume": 0.5,
            "extents": (1.0, 0.5, 1.0),
            "centroid": (5.0, 0.0, 0.0),
            "global_centroid": center,
        },
    ]
    targets = [
        "Propeller as the one separated moving feature",
        "single merged body/fuselage",
        "one broad wing or support slab",
    ]

    groups = _distribute_source_segments(source_segments, targets)
    grouped_ids = [{int(source["segment_id"]) for source in group} for group in groups]

    assert grouped_ids[0] == {5, 6}
    assert 1 in grouped_ids[1]
    assert {2, 3}.issubset(grouped_ids[2])
    assert grouped_ids[1] | grouped_ids[2] == {1, 2, 3, 4}
    assert set().union(*grouped_ids) == {1, 2, 3, 4, 5, 6}
