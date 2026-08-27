from __future__ import annotations

import json
from pathlib import Path
import shutil

import pandas as pd

from bricksmart.reporting.true_build_player import (
    DisplayBlock,
    build_true_timeline,
    write_true_build_player,
)


def _blocks() -> list[DisplayBlock]:
    """Return blocks for blocks.
    
    :returns: The result produced by the function.
    :rtype: list[DisplayBlock]
    """
    return [
        DisplayBlock(1, "standard_2x2x2", 1, "Module A", (0, 0, 0), (2, 2, 2), 0, "+X", "blue"),
        DisplayBlock(2, "standard_2x2x2", 3, "Module C", (8, 0, 0), (2, 2, 2), 180, "-X", "blue"),
        DisplayBlock(3, "standard_2x2x2", 2, "Root Module", (4, 0, 0), (2, 2, 2), 0, "+X", "blue"),
    ]


def test_true_timeline_builds_modules_then_uses_declared_root() -> None:
    """Test that true timeline builds modules then uses declared root."""
    subassembly = pd.DataFrame([
        {"global_step": 1, "segment_id": 1, "segment_name": "Module A", "local_step": 1, "row": 1, "new_block_ids": "1"},
        {"global_step": 2, "segment_id": 3, "segment_name": "Module C", "local_step": 1, "row": 1, "new_block_ids": "2"},
        {"global_step": 3, "segment_id": 2, "segment_name": "Root Module", "local_step": 1, "row": 1, "new_block_ids": "3"},
    ])
    assembly = pd.DataFrame([
        {"assembly_step": 1, "action": "start_with_segment_subassembly", "anchor_segment_id": None, "attached_segment_id": 2, "interface_id": None},
        {"assembly_step": 2, "action": "attach_segment_by_direct_structural_lock", "anchor_segment_id": 2, "attached_segment_id": 1, "interface_id": "DJ_001_002"},
        {"assembly_step": 3, "action": "attach_segment_by_direct_structural_lock", "anchor_segment_id": 2, "attached_segment_id": 3, "interface_id": "DJ_002_003"},
    ])
    graph = pd.DataFrame([
        {"segment_a": 1, "segment_b": 2, "contact_area": 6},
        {"segment_a": 2, "segment_b": 3, "contact_area": 6},
    ])

    steps = build_true_timeline(
        blocks=_blocks(),
        subassembly_steps=subassembly,
        assembly_steps=assembly,
        assembly_graph=graph,
    )

    assert [step.phase for step in steps[:3]] == ["Build segment modules"] * 3
    assert steps[3].title == "Place completed Root Module as the assembly root"
    assert steps[3].final_position_segment_ids == (2,)
    assert steps[4].title == "Attach completed Module A to Root Module"
    assert steps[5].title == "Attach completed Module C to Root Module"
    assert steps[-1].title == "Final validated build"


def test_repo_reference_player_retains_fourteen_true_steps(tmp_path: Path) -> None:
    """Test that repo reference player retains fourteen true steps.
    
    :param tmp_path: Temporary filesystem path provided by pytest.
    :type tmp_path: Path
    """
    root = Path(__file__).resolve().parents[2]
    reference_dir = root / "tests" / "regression" / "bird" / "expected"
    if not reference_dir.is_dir():
        return
    output_dir = tmp_path / "artifacts"
    output_dir.mkdir(parents=True)
    for filename in (
        "segment_subassembly_blocks.csv",
        "segment_connector_functional_final_blocks.csv",
        "subassembly_build_steps.csv",
        "segment_connector_assembly_steps.csv",
        "structural_assembly_graph.csv",
        "complete_build_steps.csv",
    ):
        source = reference_dir / filename
        if source.is_file():
            shutil.copy2(source, output_dir / filename)
    html_path = write_true_build_player(
        output_dir=output_dir,
        catalog_path=root / "block_catalog" / "block_definitions.csv",
        context_path=root / "model_registry/contracts/bird-standard-kit/versions/validated-1/task_context.json",
    )
    timeline = pd.read_csv(output_dir / "true_complete_build_steps.csv")
    canonical_html = output_dir / "build_instructions.html"
    legacy_html = output_dir / "visualizations" / "proper_complete_build_steps.html"
    assert html_path.is_file()
    assert canonical_html.is_file()
    assert legacy_html.is_file()
    assert canonical_html.read_bytes() == legacy_html.read_bytes()
    html = canonical_html.read_text(encoding="utf-8")
    assert "Block types" in html
    assert "Block type:" in html
    assert "Workbook block families" not in html
    assert "workbook catalog colors" not in html.lower()
    assert "Inventory basis" in html
    manifest = json.loads(
        (output_dir / "true_build_player_manifest.json").read_text(encoding="utf-8")
    )
    assert Path(manifest["output_html"]) == canonical_html.resolve()
    assert Path(manifest["legacy_player_html"]) == legacy_html.resolve()
    assert len(timeline) == 14


def test_canonical_html_is_written_by_repository_player() -> None:
    """Test that canonical html is written by repository player."""
    root = Path(__file__).resolve().parents[2]
    source = (root / "backend/bricksmart/reporting/true_build_player.py").read_text(encoding="utf-8")
    runner = (root / "backend/bricksmart/row_column_runner.py").read_text(encoding="utf-8")
    assert 'output_dir / "build_instructions.html"' in source
    assert "write_true_build_player(" in runner
