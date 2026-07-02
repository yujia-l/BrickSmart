from collections import Counter
from pathlib import Path
from bricksmart.model_store import LocalModelStore

from bricksmart.obj_pipeline import run_obj_build
from bricksmart.planning.voxel_models import StructuralPlannerConfig
from bricksmart.reporting import write_obj_build_outputs

ROOT = Path(__file__).resolve().parents[2]


def _run(catalog_workbook: Path):
    return run_obj_build(
        obj_path=LocalModelStore(ROOT / "model_store").resolve("bird-base").local_path,
        inventory_path=ROOT / "backend/bricksmart/config/inventory/standard_kit.yaml",
        catalog_path=catalog_workbook,
        target_longest_cells=18,
        planner_config=StructuralPlannerConfig(coverage_target=0.93),
    )


def test_all_source_segments_receive_a_build_phase(catalog_workbook: Path):
    result, _ = _run(catalog_workbook)
    source_segments = {segment.segment_id for segment in result.model.segments}
    assigned_segments = {placement.segment_id for placement in result.placements}
    assert assigned_segments == source_segments
    assert result.segment_sequence_validation["status"] == "PASS"


def test_each_segment_appears_in_one_contiguous_step_range(catalog_workbook: Path):
    result, _ = _run(catalog_workbook)
    ordered = sorted(result.placements, key=lambda placement: placement.step or 0)
    by_segment: dict[str, list[int]] = {}
    for placement in ordered:
        by_segment.setdefault(placement.segment_id or "", []).append(int(placement.step or 0))
    for steps in by_segment.values():
        assert steps == list(range(min(steps), max(steps) + 1))
    assert len(result.planner_summary["segment_order"]) == 7


def test_global_reservations_match_final_recount(catalog_workbook: Path):
    result, ledger = _run(catalog_workbook)
    recount = Counter(placement.block_type for placement in result.placements)
    assert dict(recount) == ledger.committed_counts
    assert result.planning_result.inventory_validation["status"] == "PASS"
    assert result.interface_reservations
    assert result.segment_inventory_allocations


def test_global_alternatives_enable_limited_backtracking(catalog_workbook: Path):
    result, _ = _run(catalog_workbook)
    assert len(result.global_plan_alternatives) >= 5
    assert sum(bool(row["selected"]) for row in result.global_plan_alternatives) == 1
    assert all(row["represented_segment_count"] == 7 for row in result.global_plan_alternatives)
    assert all(row["exact_mirrored_block_fraction"] == 1.0 for row in result.global_plan_alternatives)


def test_v5_outputs_use_catalog_colors_and_catalog_lineage(
    tmp_path: Path, catalog_workbook: Path
):
    result, ledger = _run(catalog_workbook)
    paths = write_obj_build_outputs(tmp_path, result=result, ledger=ledger)
    names = {path.name for path in paths}
    assert {
        "global_plan_alternatives.csv",
        "segment_inventory_allocations.csv",
        "interface_reservations.csv",
        "segment_coverage.csv",
        "global_allocation_summary.json",
        "segment_build_plan.json",
        "segment_sequence_validation.json",
        "segment_build_sequence.csv",
        "segment_build_player.html",
        "final_build_catalog_colored.png",
        "final_build_symmetry_top.png",
        "catalog_usage_audit.json",
    } <= names
    assert (tmp_path / "segment_build_player.html").stat().st_size > 1000
    assert (tmp_path / "final_build_catalog_colored.png").stat().st_size > 1000
    html = (tmp_path / "segment_build_player.html").read_text(encoding="utf-8")
    assert "block_definitions.xlsx" not in html
    assert "workbook" not in html.lower()
    assert "standard_2x2x2" in html
