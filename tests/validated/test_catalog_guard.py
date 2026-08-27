from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_csv_is_the_only_committed_block_catalog():
    """Test that csv is the only committed block catalog."""
    catalog_dir = ROOT / "block_catalog"
    assert (catalog_dir / "block_definitions.csv").is_file()
    prohibited = [
        path
        for path in catalog_dir.iterdir()
        if path.name.startswith("block_definitions.") and path.suffix.lower() != ".csv"
    ]
    assert prohibited == []


def test_runtime_has_no_hardcoded_block_color_map():
    """Test that runtime has no hardcoded block color map."""
    source = (ROOT / "backend/bricksmart/reporting/visualization.py").read_text(
        encoding="utf-8"
    )
    assert "_BLOCK_COLORS" not in source
    assert '"standard_2x2x2":' not in source
    assert '"standard_2x3x2":' not in source
    assert '"standard_2x4x2":' not in source


def test_runtime_references_csv_not_xlsx():
    """Test that runtime references csv not xlsx."""
    runtime_files = list((ROOT / "backend/bricksmart").rglob("*.py"))
    runtime_text = "\n".join(path.read_text(encoding="utf-8") for path in runtime_files)
    assert "block_definitions.csv" in runtime_text
    assert "block_definitions.xlsx" not in runtime_text
    assert "openpyxl" not in runtime_text
