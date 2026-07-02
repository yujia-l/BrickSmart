from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook


def _write_catalog_workbook(path: Path) -> Path:
    """Write the deterministic XLSX integration fixture used by planner tests."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Block Definitions"
    sheet.append(["BrickSmart catalog integration test fixture"])
    sheet.append([])
    sheet.append(
        [
            "block_type",
            "category",
            "allowed_dimensions",
            "structural_eligible",
            "packing_priority",
            "display_color",
            "rotation_policy",
            "male_faces",
            "female_faces",
        ]
    )
    rows = [
        ("rotation_block", "functional", "", False, 0, "purple", "", "", ""),
        ("hinge_block", "functional", "", False, 0, "orange", "", "", ""),
        ("big_wheel", "functional", "", False, 0, "black", "", "", ""),
        ("small_wheel", "functional", "", False, 0, "gray", "", "", ""),
        ("standard_2x2x2", "structural", "2x2x2", True, 100, "blue", "fixed", "+X", "-X"),
        ("standard_2x3x2", "structural", "2x3x2;3x2x2", True, 200, "green", "z", "+X", "-X"),
        ("standard_2x4x2", "structural", "2x4x2;4x2x2", True, 300, "darkgreen", "z", "+X", "-X"),
        ("feature_beam_3x1x1", "feature", "", False, 0, "yellow", "", "", ""),
        ("feature_beam_7x1x1", "feature", "", False, 0, "yellow", "", "", ""),
        ("feature_beam_curved", "feature", "", False, 0, "yellow", "", "", ""),
        ("angle_joint", "connector", "", False, 0, "red", "", "", ""),
        ("angle_symmetrical", "connector", "", False, 0, "red", "", "", ""),
        ("bucket", "functional", "", False, 0, "brown", "", "", ""),
        ("bucket_arms", "functional", "", False, 0, "brown", "", "", ""),
    ]
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    return path


@pytest.fixture()
def catalog_workbook(tmp_path: Path) -> Path:
    """Temporary XLSX integration harness; not a replacement for the real catalog."""
    return _write_catalog_workbook(tmp_path / "block_definitions.xlsx")


@pytest.fixture(scope="module")
def module_catalog_workbook(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped equivalent for expensive deterministic planner tests."""
    directory = tmp_path_factory.mktemp("module_catalog")
    return _write_catalog_workbook(directory / "block_definitions.xlsx")
