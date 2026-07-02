from __future__ import annotations

import argparse
from pathlib import Path

from bricksmart.catalog import load_catalog_block_ids, validate_inventory_against_catalog
from bricksmart.inventory import (
    InventoryLedger,
    compile_effective_inventory,
    load_inventory_profile,
    load_teacher_budget,
)
from bricksmart.io import load_planning_problem
from bricksmart.outputs.writers import write_run_outputs
from bricksmart.planning import ConstrainedPlanningService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run inventory-constrained BrickSmart planning")
    parser.add_argument("--problem", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--teacher-budget", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    profile = load_inventory_profile(args.inventory)
    catalog_ids = load_catalog_block_ids(args.catalog)
    validate_inventory_against_catalog(profile.quantities, catalog_ids)
    budget = load_teacher_budget(args.teacher_budget)
    effective = compile_effective_inventory(profile, budget)
    ledger = InventoryLedger(effective)
    problem = load_planning_problem(args.problem)
    result = ConstrainedPlanningService(ledger).plan(problem)
    paths = write_run_outputs(args.output, result=result, ledger=ledger)
    print(f"Planning status: {result.status}")
    print(f"Final block count: {len(result.final_parts)}")
    print("Wrote:")
    for path in paths:
        print(f"  {path}")


if __name__ == "__main__":
    main()
