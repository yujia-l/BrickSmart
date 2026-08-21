from pathlib import Path

from bricksmart.catalog import load_catalog_block_ids, load_structural_block_definitions


def test_structural_catalog_preserves_all_inventory_ids(catalog_csv: Path):
    """Test that structural catalog preserves all inventory ids.
    
    :param catalog_csv: The catalog csv value.
    :type catalog_csv: Path
    """
    ids = load_catalog_block_ids(catalog_csv)
    assert len(ids) == 14
    assert {"rotation_block", "standard_2x4x2", "bucket_arms"} <= ids


def test_only_catalog_structural_blocks_are_packing_eligible(catalog_csv: Path):
    """Test that only catalog structural blocks are packing eligible.
    
    :param catalog_csv: The catalog csv value.
    :type catalog_csv: Path
    """
    definitions = load_structural_block_definitions(catalog_csv)
    assert [item.block_type for item in definitions] == [
        "standard_2x4x2",
        "standard_2x3x2",
        "standard_2x2x2",
    ]
    by_type = {item.block_type: item for item in definitions}
    assert by_type["standard_2x4x2"].allowed_dimensions == (
        (2, 4, 2),
        (4, 2, 2),
    )
    assert by_type["standard_2x2x2"].display_color == "blue"
