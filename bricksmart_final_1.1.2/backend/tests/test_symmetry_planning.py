from collections import Counter
from pathlib import Path

import pytest

from bricksmart.model_store import LocalModelStore
from bricksmart.obj_pipeline import run_obj_build
from bricksmart.planning.voxel_models import StructuralPlannerConfig

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def bird_symmetry_build(module_catalog_workbook: Path):
    """Run the expensive deterministic bird planner once for this test module."""
    return run_obj_build(
        obj_path=LocalModelStore(ROOT / "model_store").resolve("bird-base").local_path,
        inventory_path=ROOT / "backend/bricksmart/config/inventory/standard_kit.yaml",
        catalog_path=module_catalog_workbook,
        target_longest_cells=18,
        planner_config=StructuralPlannerConfig(
            coverage_target=0.93,
            symmetry_mode="required",
        ),
    )


def test_detects_bird_bilateral_plane_and_source_symmetry(bird_symmetry_build):
    result, _ = bird_symmetry_build
    symmetry = result.symmetry_validation
    assert symmetry["axis"] == "x"
    assert symmetry["plane_coordinate"] == 10.0
    assert symmetry["target_match_count"] == 209
    assert symmetry["target_voxel_count"] == 212
    assert symmetry["target_symmetry_fraction"] > 0.98


def test_all_selected_blocks_have_exact_mirrors(bird_symmetry_build):
    result, _ = bird_symmetry_build
    blocks = {
        (block.candidate.block_type, block.candidate.origin, block.candidate.dimensions)
        for block in result.selected_blocks
    }
    plane_sum = int(result.symmetry_validation["plane_sum"])
    for block in result.selected_blocks:
        candidate = block.candidate
        mirror_origin = (
            plane_sum - candidate.origin[0] - candidate.dimensions[0] + 1,
            candidate.origin[1],
            candidate.origin[2],
        )
        assert (candidate.block_type, mirror_origin, candidate.dimensions) in blocks
    assert result.symmetry_validation["unmatched_blocks"] == []


def test_mirrored_source_segments_receive_equal_block_counts(bird_symmetry_build):
    result, _ = bird_symmetry_build
    counts = Counter(placement.segment_id for placement in result.placements)
    assert counts["root.1"] == counts["root.2"] == 7
    assert counts["root.3"] == counts["root.4"] == 1
    assert counts["root.5"] == counts["root.6"] == 1


def test_inventory_is_committed_as_atomic_symmetry_groups(bird_symmetry_build):
    result, ledger = bird_symmetry_build
    assert result.symmetry_groups
    assert all(row["status"] == "COMMITTED" for row in result.symmetry_groups)
    mirrored = [row for row in result.symmetry_groups if row["group_kind"] == "mirrored_pair"]
    assert mirrored
    assert all(row["block_count"] == 2 for row in mirrored)
    assert ledger.committed_counts == Counter(
        placement.block_type for placement in result.placements
    )


def test_symmetry_is_a_hard_final_gate(bird_symmetry_build):
    result, _ = bird_symmetry_build
    assert result.status == "PASS"
    assert result.symmetry_validation["status"] == "PASS"
