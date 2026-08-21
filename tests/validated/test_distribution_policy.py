from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_production_distribution_excludes_regression_and_generated_runs() -> None:
    """Test that production distribution excludes regression and generated runs."""
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert "prune tests/regression" in manifest
    assert "prune .test-runs" in manifest
    assert "prune runs" in manifest
    assert "prune pipeline_runtime" in manifest


def test_user_facing_visualization_source_has_no_workbook_language() -> None:
    """Test that user facing visualization source has no workbook language."""
    sources = [
        ROOT / "backend/bricksmart/reporting/true_build_player.py",
        ROOT / "backend/bricksmart/reporting/visualization.py",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    prohibited = [
        "Workbook block families",
        "workbook catalog colors",
        "catalog colors from block_definitions.csv",
        "Colors: original CSV catalog",
    ]
    for phrase in prohibited:
        assert phrase not in text
