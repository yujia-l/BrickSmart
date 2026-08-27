from __future__ import annotations

import csv
from pathlib import Path

import pytest


def _write_catalog_csv(path: Path) -> Path:
    """Write the deterministic CSV integration fixture used by planner tests."""
    headers = [
        "block_type",
        "category",
        "allowed_dimensions",
        "structural_eligible",
        "packing_priority",
        "display_color",
        "allowed_orientations",
        "male_faces",
        "female_faces",
    ]
    rows = [
        ("rotation_block", "functional", "", False, 0, "purple", "", "", ""),
        ("hinge_block", "functional", "", False, 0, "orange", "", "", ""),
        ("big_wheel", "functional", "", False, 0, "black", "", "", ""),
        ("small_wheel", "functional", "", False, 0, "gray", "", "", ""),
        ("standard_2x2x2", "structural", "2x2x2", True, 100, "blue", "X", "+X", "-X"),
        ("standard_2x3x2", "structural", "2x3x2;3x2x2", True, 200, "green", "X,Y,Z", "+X", "-X"),
        ("standard_2x4x2", "structural", "2x4x2;4x2x2", True, 300, "darkgreen", "X,Y,Z", "+X", "-X"),
        ("feature_beam_3x1x1", "feature", "", False, 0, "yellow", "", "", ""),
        ("feature_beam_7x1x1", "feature", "", False, 0, "yellow", "", "", ""),
        ("feature_beam_curved", "feature", "", False, 0, "yellow", "", "", ""),
        ("angle_joint", "connector", "", False, 0, "red", "", "", ""),
        ("angle_symmetrical", "connector", "", False, 0, "red", "", "", ""),
        ("bucket", "functional", "", False, 0, "brown", "", "", ""),
        ("bucket_arms", "functional", "", False, 0, "brown", "", "", ""),
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(headers)
        writer.writerows(rows)
    return path


@pytest.fixture()
def catalog_csv(tmp_path: Path) -> Path:
    """Temporary CSV integration harness; not a replacement for the real catalog."""
    return _write_catalog_csv(tmp_path / "block_definitions.csv")


@pytest.fixture(scope="module")
def module_catalog_csv(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped equivalent for expensive deterministic planner tests."""
    directory = tmp_path_factory.mktemp("module_catalog")
    return _write_catalog_csv(directory / "block_definitions.csv")
