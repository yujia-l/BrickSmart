from pathlib import Path

from bricksmart.catalog import load_block_catalog

ROOT = Path(__file__).resolve().parents[2]


def test_original_workbook_block_definitions_sheet_is_authoritative():
    catalog = load_block_catalog(ROOT / "block_catalog/block_definitions.xlsx")
    assert catalog.sheets_read == ("Block Definitions",)
    assert len(catalog.definitions) == 14
    assert catalog.by_type["standard_2x2x2"].display_color == "blue"
    assert catalog.by_type["standard_2x3x2"].allowed_dimensions == ((2, 3, 2),)
    assert catalog.by_type["standard_2x4x2"].male_faces
