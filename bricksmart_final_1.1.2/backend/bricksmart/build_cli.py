from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from bricksmart.row_column_runner import run_model_build


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build any BrickSmart model from a task-context contract and the shared XLSX catalog."
    )
    parser.add_argument("--task-context", "--context", "--contract", dest="task_context", required=True, help="Path or contract:// URI")
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--inventory", type=Path, help="Optional inventory profile override")
    parser.add_argument(
        "--model-uri",
        help="Override the contract model source (for example model://id, https://..., or s3://...).",
    )
    parser.add_argument("--run-id", help="Optional stable run ID; otherwise one is generated")
    parser.add_argument("--clean-output", action="store_true", help="Replace an existing explicit --run-id")
    parser.add_argument("--allow-unverified-contract", action="store_true")
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_model_build(
        task_context_path=args.task_context,
        project_root=args.project_root,
        inventory_profile_path=args.inventory,
        clean_output=args.clean_output,
        check=not args.allow_incomplete,
        allow_unverified_contract=args.allow_unverified_contract,
        model_source_override=args.model_uri,
        run_id=args.run_id,
    )
    print(json.dumps(result.summary, indent=2))
    print(f"Log: {result.log_path}")
    # Large visualization objects created by the post-run HTML writer can make
    # interpreter teardown unbounded in a one-shot CLI process. All run data is
    # already persisted, so flush the user-facing summary and terminate cleanly.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
