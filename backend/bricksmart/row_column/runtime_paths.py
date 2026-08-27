"""Path and JSON helpers used by the row/column worker."""

from __future__ import annotations

import json
from pathlib import Path


def read_json(path, default=None):
    """Read json.
    
    :param path: Filesystem path used by the operation.
    :param default: Fallback value used when no explicit value is available.
    :returns: The loaded data.
    """
    path = Path(path)
    if not path.is_file():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_path(value, base_dir=None):
    """Resolve path.
    
    :param value: Value used by the operation.
    :param base_dir: Directory for base artifacts.
    :returns: The computed result.
    """
    if value in {None, ""}:
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    candidates = []
    if base_dir is not None:
        candidates.append(Path(base_dir) / path)
    candidates.append(Path.cwd() / path)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()


def resolve_input_with_project_fallback(value, base_dir=None):
    """Resolve a configured input, then search the project by basename."""
    configured = resolve_path(value, base_dir)
    if configured is not None and configured.exists():
        return configured
    if value in {None, ""}:
        return configured

    basename = Path(value).name
    search_roots = []
    if base_dir is not None:
        base_dir = Path(base_dir).resolve()
        search_roots.extend([base_dir, base_dir.parent])
    search_roots.append(Path.cwd().resolve())

    seen = set()
    matches = []
    for root in search_roots:
        if root in seen or not root.exists():
            continue
        seen.add(root)
        try:
            matches.extend(
                path for path in root.rglob(basename)
                if path.is_file()
            )
        except Exception:
            continue

    unique_matches = list(dict.fromkeys(path.resolve() for path in matches))
    if len(unique_matches) == 1:
        return unique_matches[0]
    if unique_matches:
        return max(unique_matches, key=lambda path: path.stat().st_mtime)
    return configured


__all__ = [
    'read_json',
    'resolve_path',
    'resolve_input_with_project_fallback',
]
