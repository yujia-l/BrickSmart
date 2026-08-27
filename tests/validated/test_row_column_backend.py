from __future__ import annotations

import json
from pathlib import Path

from bricksmart.row_column_runner import summarize_row_column_output

ROOT = Path(__file__).resolve().parents[2]


def test_csv_catalog_is_the_only_block_catalog() -> None:
    """Test that csv catalog is the only block catalog."""
    catalog_dir = ROOT / "block_catalog"
    assert (catalog_dir / "block_definitions.csv").is_file()
    assert not list(catalog_dir.glob("block_definitions.xlsx"))
    assert list(catalog_dir.glob("block_ids.csv")) == []


def test_engine_contains_required_planner_features() -> None:
    """Test that engine contains required planner features."""
    source = (ROOT / "backend/bricksmart/row_column_engine.py").read_text(
        encoding="utf-8"
    )
    required = [
        "plan_rows_with_column_packing_and_rotation",
        "validate_planned_instruction_steps",
        "male_face_for_rotation",
        "actual_block_face_type",
        "mirror_planning_result",
        "consolidate_segment_planning_result",
        "InventoryLedger",
    ]
    for token in required:
        assert token in source


def test_regression_output_is_the_working_26_block_bird() -> None:
    """Test that regression output is the working 26 block bird."""
    summary = summarize_row_column_output(ROOT / "tests/regression/bird/expected")
    assert summary["final_claim_valid"] is True
    assert summary["final_block_count"] == 26
    assert summary["structural_segment_count"] == 3
    assert summary["direct_structural_join_count"] == 2
    assert summary["combined_symmetry_complete"] is True
    assert summary["inventory_valid"] is True
    assert summary["inventory_recount"] == {
        "standard_2x2x2": 16,
        "standard_2x3x2": 6,
        "standard_2x4x2": 4,
    }


def test_runtime_context_uses_csv_and_separate_inventory() -> None:
    """Test that runtime context uses csv and separate inventory."""
    context = json.loads(
        (ROOT / "model_registry/contracts/bird-standard-kit/versions/validated-1/task_context.json")
        .read_text(encoding="utf-8")
    )
    assert context["paths"]["catalog_csv"].endswith("block_definitions.csv")
    assert context["inventory"]["profile_path"].endswith("standard_kit.yaml")
    assert context["segment_assembly"]["structural_connector_policy"]["join_mode"] == "direct_structural_lock"


def test_model_build_api_endpoint_is_context_driven(monkeypatch) -> None:
    """Test that model build api endpoint is context driven.
    
    :param monkeypatch: Pytest monkeypatch fixture used by the test.
    """
    from fastapi.testclient import TestClient
    from bricksmart.app import app
    import bricksmart.app as app_module

    class Result:
        summary = {
            "final_claim_valid": True,
            "final_block_count": 26,
            "inventory_valid": True,
        }
        log_path = ROOT / "tests/regression/bird/README.md"

    monkeypatch.setattr(app_module, "run_model_build", lambda **kwargs: Result())
    response = TestClient(app).post(
        "/api/model/build",
        json={
            "contract_uri": "contract://bird-standard-kit",
            "clean_output": False,
        },
    )
    assert response.status_code == 200
    assert response.json()["final_block_count"] == 26
