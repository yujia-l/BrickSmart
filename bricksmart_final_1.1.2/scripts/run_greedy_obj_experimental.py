from __future__ import annotations

from pathlib import Path

from bricksmart.obj_pipeline import run_obj_build
from bricksmart.model_store import LocalModelStore
from bricksmart.planning.voxel_models import StructuralPlannerConfig
from bricksmart.reporting import write_obj_build_outputs
from bricksmart.run_store import LocalRunStore

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    result, ledger = run_obj_build(
        obj_path=LocalModelStore(ROOT / "model_store").resolve("bird-base").local_path,
        inventory_path=ROOT / "config/inventory/standard_kit.yaml",
        catalog_path=ROOT / "block_catalog/block_definitions.xlsx",
        up_axis="auto",
        target_longest_cells=18,
        planner_config=StructuralPlannerConfig(
            minimum_candidate_fill_ratio=0.20,
            coverage_target=0.93,
            scarcity_weight=0.25,
            symmetry_mode="required",
        ),
    )
    run = LocalRunStore.from_environment(ROOT).create(
        model_id="bird-base",
        contract_uri="experimental://greedy-obj",
    )
    paths = write_obj_build_outputs(
        run.artifacts_dir,
        result=result,
        ledger=ledger,
    )
    LocalRunStore.update(run, status=result.status, artifact_count=len(paths))
    print(f"status={result.status}")
    print(f"blocks={len(result.placements)}")
    print(f"coverage={result.geometry_validation['coverage_fraction']:.2%}")
    for path in paths:
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
