from pathlib import Path

import pytest

from bricksmart.catalog import (
    load_block_catalog,
    load_catalog_block_ids,
    validate_inventory_against_catalog,
)
from bricksmart.exceptions import CatalogConfigurationError


def test_xlsx_catalog_contains_all_standard_kit_inventory_ids(catalog_workbook: Path):
    ids = load_catalog_block_ids(catalog_workbook)
    assert "standard_2x2x2" in ids
    assert "bucket_arms" in ids


def test_catalog_loader_preserves_color_and_source_lineage(catalog_workbook: Path):
    catalog = load_block_catalog(catalog_workbook)
    block = catalog.by_type["standard_2x2x2"]
    assert block.display_color == "blue"
    assert block.source_sheet == "Block Definitions"
    assert block.source_row > catalog.header_rows["Block Definitions"]
    assert catalog.source_sha256


def test_shadow_csv_catalog_is_rejected(tmp_path: Path):
    shadow = tmp_path / "block_definitions.csv"
    shadow.write_text("block_type,color\nstandard_2x2x2,blue\n", encoding="utf-8")
    with pytest.raises(CatalogConfigurationError, match="shadow CSV"):
        load_block_catalog(shadow)


def test_unknown_inventory_id_fails_validation():
    with pytest.raises(CatalogConfigurationError):
        validate_inventory_against_catalog(["invented_block"], {"standard_2x2x2"})
