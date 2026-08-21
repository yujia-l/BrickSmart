from __future__ import annotations

import csv
import re
from pathlib import Path

from bricksmart.catalog import CATALOG_COLUMNS, CATALOG_SCHEMA_VERSION, load_block_catalog

FORBIDDEN_TEXT = re.compile(
    r"\bV\d+[A-Z]*\b|\bv\d+(?:\.\d+)*\b|\bnotebook\b|\bLLM\d?\b|"
    r"\bcurrent pass\b|\bcurrent airplane\b|\bairplane_buildability\b|"
    r"\bairplane\b|\bfuselage\b|\bwing\b|\btail\b|\bpropeller\b|"
    r"\blanding gear\b|\bcockpit\b|\bfrontend\b|\bteacher\b|\bhardcoded\b",
    re.IGNORECASE,
)


def _catalog_path() -> Path:
    """Return catalog path.
    
    :returns: The result produced by the function.
    :rtype: Path
    """
    return Path(__file__).resolve().parents[2] / "block_catalog" / "block_definitions.csv"


def _catalog_rows() -> tuple[list[str], list[dict[str, str]]]:
    """Return catalog rows.
    
    :returns: The result produced by the function.
    :rtype: tuple[list[str], list[dict[str, str]]]
    """
    with _catalog_path().open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    return list(reader.fieldnames or []), rows


def test_production_catalog_has_rich_model_building_schema() -> None:
    """Test that production catalog has rich model building schema."""
    columns, rows = _catalog_rows()

    assert tuple(columns) == CATALOG_COLUMNS
    assert len(rows) == 14
    assert len({row["block_family"] for row in rows}) == 14

    for row in rows:
        for value in row.values():
            assert not FORBIDDEN_TEXT.search(str(value or ""))

    catalog = load_block_catalog(_catalog_path())
    assert catalog.schema_version == CATALOG_SCHEMA_VERSION
    assert catalog.columns == CATALOG_COLUMNS


def test_missing_geometry_is_never_enabled() -> None:
    """Test that missing geometry is never enabled."""
    _, rows = _catalog_rows()

    for row in rows:
        if row["geometry_status"] == "missing":
            assert row["current_solver_enabled"] == "false"
            assert row["geometry_size"] == ""
            assert row["anchor_size"] == ""
            assert row["validate_with_anchor_size"] == "false"


def test_structural_rows_preserve_buildability_rules() -> None:
    """Test that structural rows preserve buildability rules."""
    _, rows = _catalog_rows()
    structural = [row for row in rows if row["category"] == "structural_block"]

    assert {row["block_family"] for row in structural} == {
        "standard_2x2x2",
        "standard_2x3x2",
        "standard_2x4x2",
    }
    for row in structural:
        assert row["geometry_status"] == "verified"
        assert row["counts_as_structural_coverage"] == "true"
        assert row["default_packing_priority"] == "1"
        assert "male_to_female" in row["interface_rule"]
        assert row["source_segment_required"] == "true"
        assert row["validate_with_anchor_size"] == "true"


def test_wheel_rows_preserve_layer_clearance_and_world_mapping_rules() -> None:
    """Test that wheel rows preserve layer clearance and world mapping rules."""
    _, rows = _catalog_rows()
    by_family = {row["block_family"]: row for row in rows}

    for family in ("big_wheel", "small_wheel"):
        row = by_family[family]
        assert row["geometry_representation"] == "layered_wheel"
        assert row["geometry_coordinate_frame"] == "local_wheel_frame"
        assert row["local_axle_axis"] == "N"
        assert row["visible_geometry_size"]
        assert row["anchor_geometry_layer_spec"]
        assert row["clearance_reservation_size"]
        assert row["do_not_resize_to_source_bbox"] == "true"
        assert row["source_segment_required"] == "false"
        assert row["ground_contact_policy"]
