"""Regression checkpoint comparison helpers.

This module loads expected artifacts, compares generated outputs, and reports
behavioral differences for reviewed baselines.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from bricksmart.hashing import sha256_file

import numpy as np
import pandas as pd


def _json(path: Path) -> dict[str, Any]:
    """Return the json value.
    
    :param path: Filesystem path used by the operation.
    :type path: Path
    :returns: The result produced by the function.
    :rtype: dict[str, Any]
    """
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _array_summary(path: Path) -> dict[str, Any] | None:
    """Return the array summary value.
    
    :param path: Filesystem path used by the operation.
    :type path: Path
    :returns: The result produced by the function.
    :rtype: dict[str, Any] | None
    """
    if not path.is_file():
        return None
    array = np.load(path, allow_pickle=False)
    return {
        "sha256": sha256_file(path),
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "nonzero_count": int(np.count_nonzero(array)),
        "unique_positive_ids": sorted(int(v) for v in np.unique(array) if int(v) > 0),
    }


def _csv_summary(path: Path, sort_columns: Iterable[str] = ()) -> dict[str, Any] | None:
    """Return the csv summary value.
    
    :param path: Filesystem path used by the operation.
    :type path: Path
    :param sort_columns: The sort columns value.
    :type sort_columns: Iterable[str]
    :returns: The result produced by the function.
    :rtype: dict[str, Any] | None
    """
    if not path.is_file():
        return None
    frame = pd.read_csv(path)
    existing = [column for column in sort_columns if column in frame.columns]
    if existing:
        frame = frame.sort_values(existing, kind="stable").reset_index(drop=True)
    canonical = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return {
        "sha256": hashlib.sha256(canonical).hexdigest(),
        "row_count": int(len(frame)),
        "columns": list(frame.columns),
    }


def build_checkpoint_manifest(
    *,
    project_root: str | Path,
    context_path: str | Path,
    output_dir: str | Path,
    confirmations_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build checkpoint manifest.
    
    :param project_root: The project root value.
    :type project_root: str | Path
    :param context_path: Path to the context file.
    :type context_path: str | Path
    :param output_dir: Directory where generated artifacts are written.
    :type output_dir: str | Path
    :param confirmations_path: Path to the confirmations file.
    :type confirmations_path: str | Path | None
    :returns: The generated result.
    :rtype: dict[str, Any]
    """
    root = Path(project_root).resolve()
    context = Path(context_path).resolve()
    out = Path(output_dir).resolve()
    payload: dict[str, Any] = {
        "schema_version": "bricksmart_model_checkpoint_manifest_v2",
        "context": {
            "path": str(context),
            "sha256": sha256_file(context) if context.is_file() else None,
        },
        "confirmations": None,
        "catalog": None,
        "arrays": {},
        "tables": {},
        "final_summary": _json(out / "segment_connector_final_summary.json"),
        "inventory_validation": _json(out / "inventory_validation.json"),
        "semantic_target_preservation": _json(out / "semantic_target_preservation.json"),
    }
    if confirmations_path:
        confirmations = Path(confirmations_path).resolve()
        payload["confirmations"] = {
            "path": str(confirmations),
            "sha256": sha256_file(confirmations) if confirmations.is_file() else None,
        }
    catalog = root / "block_catalog" / "block_definitions.csv"
    payload["catalog"] = {
        "path": str(catalog),
        "sha256": sha256_file(catalog) if catalog.is_file() else None,
    }
    for name in (
        "voxel_segment_raw.npy",
        "voxel_structure.npy",
        "voxel_segment_preprocessed.npy",
        "voxel_segment_clean.npy",
        "segment_grid_planner_raw.npy",
        "segment_grid_structuralized.npy",
        "segment_grid_planner_combined.npy",
    ):
        summary = _array_summary(out / name)
        if summary:
            payload["arrays"][name] = summary
    table_specs = {
        "segments_labeled_integrated.csv": ("segment_id",),
        "segment_subassembly_blocks.csv": ("source_segment_id", "block_id"),
        "subassembly_build_steps.csv": ("global_step",),
        "segment_connector_assembly_steps.csv": ("assembly_step",),
        "final_parts_detailed.csv": ("block_id",),
        "inventory_usage.csv": ("block_type",),
    }
    for name, sort_columns in table_specs.items():
        summary = _csv_summary(out / name, sort_columns)
        if summary:
            payload["tables"][name] = summary
    return payload


def write_checkpoint_manifest(**kwargs: Any) -> Path:
    """Write checkpoint manifest.
    
    :param kwargs: The kwargs value.
    :type kwargs: Any
    :returns: The result produced by the function.
    :rtype: Path
    """
    out = Path(kwargs["output_dir"]).resolve()
    manifest = build_checkpoint_manifest(**kwargs)
    path = out / "model_checkpoint_manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def compare_checkpoint_manifests(
    expected: dict[str, Any], actual: dict[str, Any]
) -> dict[str, Any]:
    """Compare checkpoint manifests.
    
    :param expected: The expected value.
    :type expected: dict[str, Any]
    :param actual: The actual value.
    :type actual: dict[str, Any]
    :returns: The result produced by the function.
    :rtype: dict[str, Any]
    """
    mismatches: list[dict[str, Any]] = []

    def compare(path: str, left: Any, right: Any) -> None:
        """Compare compare.
        
        :param path: Filesystem path used by the operation.
        :type path: str
        :param left: The left value.
        :type left: Any
        :param right: The right value.
        :type right: Any
        """
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(set(left) | set(right)):
                compare(f"{path}.{key}" if path else key, left.get(key), right.get(key))
        elif left != right:
            mismatches.append({"path": path, "expected": left, "actual": right})

    # Paths are environment-specific and are not parity fields.
    expected_copy = json.loads(json.dumps(expected))
    actual_copy = json.loads(json.dumps(actual))
    for payload in (expected_copy, actual_copy):
        for key in ("context", "confirmations", "catalog"):
            if isinstance(payload.get(key), dict):
                payload[key].pop("path", None)
    compare("", expected_copy, actual_copy)
    return {
        "status": "PASS" if not mismatches else "FAIL",
        "match": not mismatches,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }
