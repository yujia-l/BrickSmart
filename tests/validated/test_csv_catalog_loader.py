from pathlib import Path

from bricksmart.catalog import CATALOG_SCHEMA_VERSION, load_block_catalog

ROOT = Path(__file__).resolve().parents[2]


def test_authoritative_csv_catalog_loads_all_block_definitions():
    """Test that authoritative csv catalog loads all block definitions."""
    path = ROOT / "block_catalog/block_definitions.csv"
    catalog = load_block_catalog(path)
    assert catalog.sources_read == (path.name,)
    assert catalog.schema_version == CATALOG_SCHEMA_VERSION
    assert len(catalog.definitions) == 14
    assert catalog.by_type["standard_2x2x2"].display_color == "blue"
    assert set(catalog.by_type["standard_2x3x2"].allowed_dimensions) == {
        (2, 3, 2),
        (2, 2, 3),
        (3, 2, 2),
    }
    assert catalog.by_type["standard_2x4x2"].male_faces == ("+Z",)


def test_authoritative_catalog_exposes_typed_build_policies():
    """Test that authoritative catalog exposes typed build policies."""
    catalog = load_block_catalog(ROOT / "block_catalog/block_definitions.csv")

    structural = catalog.by_type["standard_2x3x2"]
    assert structural.geometry.status == "verified"
    assert structural.geometry.anchor_dimensions == (2, 3, 1)
    assert structural.build_policy.counts_as_structural_coverage is True
    assert "male_to_female" in structural.build_policy.interface_rule
    assert structural.build_policy.source_segment_required is True

    wheel = catalog.by_type["big_wheel"]
    assert wheel.geometry.representation == "layered_wheel"
    assert wheel.geometry.visible_dimensions == (3, 3, 1)
    assert wheel.geometry.clearance_dimensions == (4, 4, 1)
    assert wheel.motion.local_axle_axis == "N"
    assert wheel.build_policy.do_not_resize_to_source_bbox is True
    assert wheel.build_policy.source_segment_required is False

    bucket = catalog.by_type["bucket"]
    assert bucket.geometry.status == "missing"
    assert bucket.allowed_dimensions == ()
    assert bucket.build_policy.solver_enabled is False
