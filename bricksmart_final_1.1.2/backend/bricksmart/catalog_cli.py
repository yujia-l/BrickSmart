from __future__ import annotations

import argparse
import json
from pathlib import Path

from bricksmart.catalog import load_block_catalog, validate_inventory_against_catalog
from bricksmart.inventory import load_inventory_profile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect the original BrickSmart block_definitions.xlsx workbook"
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("block_catalog/block_definitions.xlsx"),
    )
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    catalog = load_block_catalog(args.catalog)
    payload = {
        **catalog.to_summary(),
        "blocks": [item.to_summary() for item in catalog.definitions],
    }
    if args.inventory:
        profile = load_inventory_profile(args.inventory)
        validate_inventory_against_catalog(profile.quantities, catalog.block_ids)
        payload["inventory_validation"] = {
            "status": "PASS",
            "inventory_id": profile.inventory_id,
            "inventory_block_count": len(profile.quantities),
        }
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(args.output)
    else:
        print(text)


if __name__ == "__main__":
    main()
