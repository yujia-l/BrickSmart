"""Command-line interface for importing and inspecting stored models.

This module exposes local model-store operations such as import, manifest lookup,
and checksum-backed model reference management.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bricksmart.model_store import LocalModelStore, ModelResolver
from bricksmart.row_column_runner import resolve_project_root


def parser() -> argparse.ArgumentParser:
    """Create the command-line parser.
    
    :returns: The result produced by the function.
    :rtype: argparse.ArgumentParser
    """
    root = argparse.ArgumentParser(description="Manage BrickSmart's content-addressed model store.")
    root.add_argument("--project-root", type=Path)
    sub = root.add_subparsers(dest="command", required=True)

    imp = sub.add_parser("import", help="Import a local OBJ and assign a model:// ID")
    imp.add_argument("path", type=Path)
    imp.add_argument("--model-id", required=True)
    imp.add_argument("--expected-sha256")

    resolve = sub.add_parser("resolve", help="Resolve a model URI to its local immutable object")
    resolve.add_argument("uri")
    resolve.add_argument("--model-id")

    sub.add_parser("list", help="List registered model IDs")
    return root


def main() -> None:
    """Run the command-line entry point."""
    args = parser().parse_args()
    project = resolve_project_root(args.project_root)
    store = LocalModelStore.from_environment(project)
    if args.command == "import":
        record = store.import_file(
            args.path,
            model_id=args.model_id,
            expected_sha256=args.expected_sha256,
        )
        print(json.dumps(record.to_dict(), indent=2))
    elif args.command == "resolve":
        resolved = ModelResolver(project_root=project, store=store).resolve(
            args.uri,
            default_model_id=args.model_id,
        )
        print(json.dumps(resolved.to_dict(), indent=2))
    else:
        print(json.dumps([record.to_dict() for record in store.list_records()], indent=2))


if __name__ == "__main__":
    main()
