from pathlib import Path
from bricksmart.model_store import LocalModelStore

import yaml

from bricksmart.obj_pipeline import run_obj_build
from bricksmart.planning.voxel_models import StructuralPlannerConfig
from bricksmart.reporting import write_obj_build_outputs

ROOT = Path(__file__).resolve().parents[2]
BASE_OBJ = LocalModelStore(ROOT / "model_store").resolve("bird-base").local_path
INVENTORY = ROOT / "backend/bricksmart/config/inventory/standard_kit.yaml"


def _run(catalog_workbook: Path, teacher_budget=None):
    return run_obj_build(
        obj_path=BASE_OBJ,
        inventory_path=INVENTORY,
        catalog_path=catalog_workbook,
        teacher_budget_path=teacher_budget,
        up_axis="auto",
        target_longest_cells=18,
        planner_config=StructuralPlannerConfig(coverage_target=0.93),
    )


def test_base_obj_integration_harness_passes_with_xlsx_catalog(catalog_workbook: Path):
    result, ledger = _run(catalog_workbook)
    assert result.status == "PASS"
    assert len(result.placements) == 28
    assert result.geometry_validation["coverage_fraction"] >= 0.93
    assert result.geometry_validation["block_contact_component_count"] == 1
    assert result.geometry_validation["overlap_voxel_count"] == 0
    assert result.build_sequence_validation["status"] == "PASS"
    assert result.catalog_summary["source_path"].endswith("block_definitions.xlsx")
    assert result.catalog_colors["standard_2x2x2"] == "blue"
    assert ledger.committed_counts == {
        "standard_2x2x2": 8,
        "standard_2x3x2": 10,
        "standard_2x4x2": 10,
    }
    assert result.symmetry_validation["status"] == "PASS"
    assert result.planning_result.inventory_validation["status"] == "PASS"


def test_zero_structural_budget_fails_without_exceeding_inventory(
    tmp_path: Path, catalog_workbook: Path
):
    budget = tmp_path / "budget.yaml"
    budget.write_text(
        yaml.safe_dump(
            {
                "blocks": {
                    "standard_2x2x2": 0,
                    "standard_2x3x2": 0,
                    "standard_2x4x2": 0,
                }
            }
        ),
        encoding="utf-8",
    )
    result, ledger = _run(catalog_workbook, budget)
    assert result.status == "FAIL_GEOMETRY_VALIDATION"
    assert result.placements == []
    assert ledger.committed_counts == {}
    assert result.planning_result.inventory_validation["status"] == "PASS"
    assert result.geometry_validation["coverage_fraction"] == 0.0


def test_obj_outputs_include_catalog_lineage_and_preview(
    tmp_path: Path, catalog_workbook: Path
):
    result, ledger = _run(catalog_workbook)
    paths = write_obj_build_outputs(tmp_path, result=result, ledger=ledger)
    names = {path.name for path in paths}
    assert {
        "model_summary.json",
        "catalog_usage_audit.json",
        "source_segments.csv",
        "voxelization_summary.json",
        "target_voxels.csv",
        "final_parts_detailed.csv",
        "inventory_validation.json",
        "geometry_validation.json",
        "build_sequence_validation.json",
        "build_step_validation.csv",
        "obj_build_instructions.json",
        "build_instructions.html",
        "build_preview.html",
        "symmetry_validation.json",
        "symmetry_segment_pairs.csv",
        "symmetry_groups.csv",
        "final_build_catalog_colored.png",
        "final_build_symmetry_top.png",
    } <= names
    assert (tmp_path / "build_preview.html").stat().st_size > 1000
    audit = (tmp_path / "catalog_usage_audit.json").read_text(encoding="utf-8")
    assert '"shadow_catalog_used": false' in audit
