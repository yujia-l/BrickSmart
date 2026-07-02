from __future__ import annotations

import json
from pathlib import Path

from bricksmart.row_column_runner import summarize_row_column_output

ROOT = Path(__file__).resolve().parents[2]


def test_bird_regression_baseline() -> None:
    summary = summarize_row_column_output(ROOT / "tests/regression/bird/expected")
    assert summary["final_claim_valid"] is True
    assert summary["final_block_count"] == 26
    assert summary["structural_segment_count"] == 3
    assert summary["direct_structural_join_count"] == 2
    assert summary["inventory_recount"] == {
        "standard_2x2x2": 16,
        "standard_2x3x2": 6,
        "standard_2x4x2": 4,
    }


def test_unlimited_airplane_reference_baseline_is_explicit() -> None:
    expected = ROOT / "tests/regression/airplane_reference_unlimited/expected"
    summary = summarize_row_column_output(expected)
    inventory = json.loads((expected / "inventory_validation.json").read_text())
    assert summary["final_claim_valid"] is True
    assert summary["final_block_count"] == 78
    assert summary["structural_segment_count"] == 8
    assert summary["direct_structural_join_count"] == 7
    assert inventory["inventory_mode"] == "unlimited"
    assert summary["inventory_recount"] == {
        "big_wheel": 2,
        "rotation_block": 1,
        "standard_2x2x2": 57,
        "standard_2x3x2": 12,
        "standard_2x4x2": 6,
    }


def test_standard_kit_airplane_is_an_expected_infeasibility() -> None:
    path = ROOT / "tests/regression/airplane_standard_kit/expected/inventory_feasibility.json"
    result = json.loads(path.read_text())
    assert result["status"] == "INFEASIBLE_INVENTORY"
    assert result["final_claim_valid"] is False
    assert result["build_instructions_html_generated"] is False
    assert result["shortages"]["standard_2x2x2"] == {
        "available": 16,
        "capacity": 16,
        "committed": 0,
        "required": 18,
        "reserved": 0,
        "shortage": 2,
    }


def test_regression_fixtures_are_compact_and_not_runtime_runs() -> None:
    assert not (ROOT / "runs/baseline-bird").exists()
    assert not (ROOT / "runs/baseline-airplane").exists()
    assert not (ROOT / "tests/regression/airplane").exists()
    assert (ROOT / "tests/regression/bird/expected").is_dir()
    assert (ROOT / "tests/regression/airplane_reference_unlimited/expected").is_dir()
    assert (ROOT / "tests/regression/airplane_standard_kit/expected").is_dir()
    assert list((ROOT / "tests/regression").rglob("*.npy")) == []
    assert list((ROOT / "tests/regression").rglob("*.html")) == []
    assert list((ROOT / "tests/regression").rglob("llm2_raw_responses.json")) == []
