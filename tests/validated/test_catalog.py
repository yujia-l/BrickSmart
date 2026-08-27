from pathlib import Path

import pytest

from bricksmart.catalog import (
    load_block_catalog,
    load_catalog_block_ids,
    validate_inventory_against_catalog,
)
from bricksmart.exceptions import CatalogConfigurationError


def test_csv_catalog_contains_all_standard_kit_inventory_ids(catalog_csv: Path):
    """Test that csv catalog contains all standard kit inventory ids.
    
    :param catalog_csv: The catalog csv value.
    :type catalog_csv: Path
    """
    ids = load_catalog_block_ids(catalog_csv)
    assert "standard_2x2x2" in ids
    assert "bucket_arms" in ids


def test_catalog_loader_preserves_color_and_source_lineage(catalog_csv: Path):
    """Test that catalog loader preserves color and source lineage.
    
    :param catalog_csv: The catalog csv value.
    :type catalog_csv: Path
    """
    catalog = load_block_catalog(catalog_csv)
    block = catalog.by_type["standard_2x2x2"]
    source_name = catalog_csv.name
    assert block.display_color == "blue"
    assert block.source_name == source_name
    assert block.source_row > catalog.header_rows[source_name]
    assert catalog.source_sha256


def test_non_csv_catalog_is_rejected(tmp_path: Path):
    """Test that non csv catalog is rejected.
    
    :param tmp_path: Temporary filesystem path provided by pytest.
    :type tmp_path: Path
    """
    xlsx = tmp_path / "block_definitions.xlsx"
    xlsx.write_bytes(b"not-an-xlsx")
    with pytest.raises(CatalogConfigurationError, match="CSV catalog only"):
        load_block_catalog(xlsx)


def test_unknown_inventory_id_fails_validation():
    """Test that unknown inventory id fails validation."""
    with pytest.raises(CatalogConfigurationError):
        validate_inventory_against_catalog(["invented_block"], {"standard_2x2x2"})


def test_rich_catalog_rejects_missing_schema_column(tmp_path: Path):
    """Test that rich catalog rejects missing schema column.
    
    :param tmp_path: Temporary filesystem path provided by pytest.
    :type tmp_path: Path
    """
    import csv

    source = Path(__file__).resolve().parents[2] / "block_catalog/block_definitions.csv"
    with source.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])

    fieldnames.remove("catalog_validation_rule")
    target = tmp_path / "block_definitions.csv"
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(CatalogConfigurationError, match="does not match"):
        load_block_catalog(target)


def test_rich_catalog_rejects_invalid_connector_face(tmp_path: Path):
    """Test that rich catalog rejects invalid connector face.
    
    :param tmp_path: Temporary filesystem path provided by pytest.
    :type tmp_path: Path
    """
    import csv

    source = Path(__file__).resolve().parents[2] / "block_catalog/block_definitions.csv"
    with source.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])

    rows[0]["primary_male_faces"] = "+Q"
    target = tmp_path / "block_definitions.csv"
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(CatalogConfigurationError, match="Invalid connector face"):
        load_block_catalog(target)
