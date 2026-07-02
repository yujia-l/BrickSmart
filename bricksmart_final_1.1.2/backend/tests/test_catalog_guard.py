from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_no_shadow_catalog_files_are_committed():
    catalog_dir = ROOT / "block_catalog"
    prohibited = [
        path for path in catalog_dir.iterdir()
        if path.suffix.lower() in {".csv", ".json", ".yaml", ".yml"}
    ]
    assert prohibited == []


def test_runtime_has_no_hardcoded_block_color_map():
    source = (ROOT / "backend/bricksmart/reporting/visualization.py").read_text(
        encoding="utf-8"
    )
    assert "_BLOCK_COLORS" not in source
    assert '"standard_2x2x2":' not in source
    assert '"standard_2x3x2":' not in source
    assert '"standard_2x4x2":' not in source


def test_runtime_references_xlsx_not_shadow_csv():
    runtime_files = list((ROOT / "backend/bricksmart").rglob("*.py"))
    runtime_text = "\n".join(path.read_text(encoding="utf-8") for path in runtime_files)
    assert "block_definitions.csv" not in runtime_text
    assert "block_ids.csv" not in runtime_text
