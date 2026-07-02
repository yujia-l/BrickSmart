from __future__ import annotations

import argparse
from pathlib import Path

from bricksmart.catalog import load_catalog_block_ids, validate_inventory_against_catalog
from bricksmart.inventory import InventoryLedger, compile_effective_inventory, load_inventory_profile
from bricksmart.io import load_planning_problem
from bricksmart.outputs.writers import write_run_outputs
from bricksmart.planning import ConstrainedPlanningService
from bricksmart.run_store import LocalRunStore

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--catalog",
        type=Path,
        default=ROOT / "block_catalog/block_definitions.xlsx",
    )
    args = parser.parse_args()

    profile = load_inventory_profile(
        ROOT / "config/inventory/standard_kit.yaml"
    )
    catalog_ids = load_catalog_block_ids(args.catalog)
    validate_inventory_against_catalog(profile.quantities, catalog_ids)
    effective = compile_effective_inventory(profile)
    ledger = InventoryLedger(effective)
    problem = load_planning_problem(ROOT / "examples/sample_candidate_problem.json")
    result = ConstrainedPlanningService(ledger).plan(problem)
    run = LocalRunStore.from_environment(ROOT).create(model_id="candidate-demo", contract_uri="demo://candidate-allocation")
    paths = write_run_outputs(run.artifacts_dir, result=result, ledger=ledger)
    LocalRunStore.update(run, status="succeeded", artifact_count=len(paths))

    print(f"Planning status: {result.status}")
    print(f"Final block count: {len(result.final_parts)}")
    for decision in result.decisions:
        print(f"{decision.group_id}: {decision.selected_candidate_id or decision.status}")
    print("Output files:")
    for path in paths:
        print(f"  {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
