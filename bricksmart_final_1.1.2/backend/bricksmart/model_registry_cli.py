from __future__ import annotations

import argparse
import json
from pathlib import Path

from bricksmart.model_registry import LocalModelRegistry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage versioned BrickSmart model contracts.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)

    imp = sub.add_parser("import", help="Import a task context and confirmation artifact")
    imp.add_argument("task_context", type=Path)
    imp.add_argument("--confirmations", type=Path)
    imp.add_argument("--contract-id", required=True)
    imp.add_argument("--version-id")

    sub.add_parser("list", help="List current contracts")

    show = sub.add_parser("show", help="Show a contract revision")
    show.add_argument("reference", help="contract://id or contract://id@version")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    registry = LocalModelRegistry.from_environment(args.project_root.resolve())
    if args.command == "import":
        record = registry.register_files(
            task_context_path=args.task_context,
            confirmations_path=args.confirmations,
            contract_id=args.contract_id,
            version_id=args.version_id,
            metadata={"ingest_method": "cli_import"},
        )
        print(json.dumps(record.to_dict(), indent=2))
    elif args.command == "list":
        print(json.dumps([row.to_dict() for row in registry.list_records()], indent=2))
    elif args.command == "show":
        print(json.dumps(registry.resolve(args.reference).to_dict(), indent=2))


if __name__ == "__main__":
    main()
