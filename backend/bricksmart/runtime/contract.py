"""Model-contract validation and normalization.

This module validates contract fields, resolves confirmation artifacts, and
normalizes contract data for runtime planning.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from bricksmart.hashing import sha256_file
from bricksmart.contracts.semantic_preservation import (
    confirmation_status,
    segment_id_from_row,
)

from .context import model_identity, normalize_task_context
from .execution_policy import resolve_execution_policy
from bricksmart.functional import FunctionalAssemblySpec, default_registry
from bricksmart.model_store import ModelResolver, ModelSourceSpec


AUTHORITATIVE_STATUSES = {"confirmed", "corrected", "approved", "accepted"}
PROVISIONAL_MARKERS = {
    "geometry_inferred", "geometry-inferred", "temporary_mapping",
    "temporary-mapping", "diagnostic_only", "diagnostic-only",
}


class ModelContractError(RuntimeError):
    """Raised when a task context cannot safely drive a BrickSmart run."""


@dataclass(frozen=True)
class ModelContractValidation:
    model_id: str
    task_id: str
    object_type_hint: str
    context_path: str
    confirmations_path: str | None
    source_model_path: str
    source_model_uri: str
    source_model_kind: str
    source_model_id: str | None
    source_model_cache_hit: bool
    catalog_path: str
    context_sha256: str
    confirmations_sha256: str | None
    source_model_sha256: str | None
    catalog_sha256: str | None
    authoritative_confirmation_count: int
    confirmed_segment_ids: tuple[int, ...]
    functional_assembly_types: tuple[str, ...]
    execution_mode: str
    runtime_llm_requested: bool
    runtime_llm_allowed: bool
    runtime_llm_effective: bool
    deterministic_build: bool
    final_claim_eligible: bool
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Convert the object to dict.
        
        :returns: The result produced by the function.
        :rtype: dict[str, Any]
        """
        payload = asdict(self)
        payload["confirmed_segment_ids"] = list(self.confirmed_segment_ids)
        payload["functional_assembly_types"] = list(self.functional_assembly_types)
        payload["errors"] = list(self.errors)
        payload["warnings"] = list(self.warnings)
        return payload


def _resolve(value: str | Path, *, context_path: Path, project_root: Path) -> Path:
    """Return the resolve value.
    
    :param value: Value used by the operation.
    :type value: str | Path
    :param context_path: Path to the context file.
    :type context_path: Path
    :param project_root: The project root value.
    :type project_root: Path
    :returns: The result produced by the function.
    :rtype: Path
    """
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    runtime = project_root / "pipeline_runtime"
    candidates = [context_path.parent / candidate, runtime / candidate, project_root / candidate]
    for path in candidates:
        if path.exists():
            return path.resolve()
    return candidates[0].resolve()


def _read_rows(path: Path) -> list[dict[str, Any]]:
    """Read rows.
    
    :param path: Filesystem path used by the operation.
    :type path: Path
    :returns: The loaded data.
    :rtype: list[dict[str, Any]]
    """
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [dict(row) for row in payload]
    if isinstance(payload, dict):
        for key in ("records", "segment_rows", "segments_labeled"):
            if isinstance(payload.get(key), list):
                return [dict(row) for row in payload[key]]
    raise ModelContractError(f"Unsupported confirmation artifact: {path}")


def _provisional_hits(payload: Any, prefix: str = "") -> list[str]:
    """Return the provisional hits value.
    
    :param payload: Payload data to process.
    :type payload: Any
    :param prefix: The prefix value.
    :type prefix: str
    :returns: The result produced by the function.
    :rtype: list[str]
    """
    hits: list[str] = []
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            hits.extend(_provisional_hits(value, path))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            hits.extend(_provisional_hits(value, f"{prefix}[{index}]"))
    elif isinstance(payload, str):
        normalized = payload.lower().replace(" ", "_")
        if any(marker in normalized for marker in PROVISIONAL_MARKERS):
            hits.append(f"{prefix}={payload!r}")
    return hits


def validate_model_contract(
    *,
    project_root: str | Path,
    context_path: str | Path,
    allow_unverified: bool = False,
    model_source_override: str | Mapping[str, Any] | None = None,
    model_resolver: ModelResolver | None = None,
) -> ModelContractValidation:
    """Validate model contract.
    
    :param project_root: The project root value.
    :type project_root: str | Path
    :param context_path: Path to the context file.
    :type context_path: str | Path
    :param allow_unverified: Whether to allow unverified.
    :type allow_unverified: bool
    :param model_source_override: The model source override value.
    :type model_source_override: str | Mapping[str, Any] | None
    :param model_resolver: The model resolver value.
    :type model_resolver: ModelResolver | None
    :returns: The result produced by the function.
    :rtype: ModelContractValidation
    """
    root = Path(project_root).expanduser().resolve()
    context_file = Path(context_path).expanduser().resolve()
    if not context_file.is_file():
        raise ModelContractError(f"Task context does not exist: {context_file}")

    raw = json.loads(context_file.read_text(encoding="utf-8"))
    payload = normalize_task_context(raw)
    identity = model_identity(payload, context_path=context_file)
    errors: list[str] = []
    warnings: list[str] = []

    execution_policy = resolve_execution_policy(payload)
    errors.extend(execution_policy.errors)
    warnings.extend(execution_policy.warnings)

    policy = payload.get("contract_policy", {}) or {}
    reject_provisional = bool(policy.get("reject_provisional_metadata", True))
    hits = _provisional_hits(payload)
    if hits and reject_provisional and not allow_unverified:
        errors.append("Task context contains provisional/diagnostic metadata: " + "; ".join(hits[:8]))

    semantics = payload.get("segment_semantics", {}) or {}
    labels_value = semantics.get("labels_file")
    confirmations: Path | None = None
    rows: list[dict[str, Any]] = []
    if labels_value:
        confirmations = _resolve(labels_value, context_path=context_file, project_root=root)
        if not confirmations.is_file():
            errors.append(f"Configured confirmation artifact is missing: {confirmations}")
        else:
            rows = _read_rows(confirmations)
    elif not semantics.get("auto_confirm_from_obj_object_names", False):
        errors.append(
            "A model contract must provide segment_semantics.labels_file or explicitly enable "
            "auto_confirm_from_obj_object_names."
        )

    authoritative = [row for row in rows if confirmation_status(row) in AUTHORITATIVE_STATUSES]
    ids = tuple(sorted({sid for row in authoritative if (sid := segment_id_from_row(row)) is not None}))
    if rows and not authoritative:
        errors.append("The confirmation artifact has no authoritative segment records.")

    paths = payload.get("paths", {}) or {}
    source_value = model_source_override or payload.get("model_source") or paths.get("source_model") or payload.get("source_model_path")
    resolved_model = None
    if not source_value:
        errors.append("model_source.uri is required.")
        source = root / "MISSING_SOURCE.obj"
        source_uri = "missing://source"
        source_kind = "missing"
        source_model_id = None
        source_cache_hit = False
    else:
        try:
            resolver = model_resolver or ModelResolver(project_root=root)
            spec = source_value if isinstance(source_value, (str, Mapping)) else str(source_value)
            resolved_model = resolver.resolve(
                spec,
                context_path=context_file,
                default_model_id=identity.model_id,
            )
            source = resolved_model.local_path
            source_uri = resolved_model.canonical_uri
            source_kind = resolved_model.source_kind
            source_model_id = resolved_model.model_id
            source_cache_hit = resolved_model.cache_hit
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f"Unable to resolve model source: {exc}")
            source = root / "MISSING_SOURCE.obj"
            source_uri = str(source_value)
            source_kind = "resolution_error"
            source_model_id = None
            source_cache_hit = False

    catalog_value = paths.get("catalog_csv", payload.get("catalog_csv", "../block_catalog/block_definitions.csv"))
    catalog = _resolve(catalog_value, context_path=context_file, project_root=root)
    if not catalog.is_file():
        fallback = root / "block_catalog" / "block_definitions.csv"
        if fallback.is_file():
            catalog = fallback.resolve()
        else:
            errors.append(f"Configured block catalog is missing: {catalog}")
    if catalog.suffix.lower() != ".csv":
        errors.append("The block catalog must be the authoritative CSV file.")

    regression = payload.get("regression", {}) or {}
    source_hash = resolved_model.sha256 if resolved_model is not None else (sha256_file(source) if source.is_file() else None)
    catalog_hash = sha256_file(catalog) if catalog.is_file() else None
    expected_source = str(regression.get("source_model_sha256") or "").lower()
    expected_catalog = str(regression.get("catalog_sha256") or "").lower()
    if expected_source and source_hash != expected_source:
        errors.append(f"Source-model fingerprint mismatch: expected {expected_source}, got {source_hash}.")
    if expected_catalog and catalog_hash != expected_catalog:
        errors.append(f"Catalog fingerprint mismatch: expected {expected_catalog}, got {catalog_hash}.")

    assembly_rows = [
        row
        for row in payload.get("functional_assemblies", []) or []
        if row.get("enabled", True)
    ]
    assembly_specs: list[FunctionalAssemblySpec] = []
    for row in assembly_rows:
        try:
            assembly_specs.append(FunctionalAssemblySpec.from_mapping(row))
        except (TypeError, ValueError) as exc:
            errors.append(str(exc))
    assembly_types = tuple(sorted({spec.assembly_type for spec in assembly_specs}))
    try:
        default_registry().validate(assembly_specs)
    except ValueError as exc:
        errors.append(str(exc))

    result = ModelContractValidation(
        model_id=identity.model_id,
        task_id=identity.task_id,
        object_type_hint=identity.object_type_hint,
        context_path=str(context_file),
        confirmations_path=str(confirmations) if confirmations else None,
        source_model_path=str(source),
        source_model_uri=source_uri,
        source_model_kind=source_kind,
        source_model_id=source_model_id,
        source_model_cache_hit=source_cache_hit,
        catalog_path=str(catalog),
        context_sha256=sha256_file(context_file),
        confirmations_sha256=sha256_file(confirmations) if confirmations and confirmations.is_file() else None,
        source_model_sha256=source_hash,
        catalog_sha256=catalog_hash,
        authoritative_confirmation_count=len(authoritative),
        confirmed_segment_ids=ids,
        functional_assembly_types=assembly_types,
        execution_mode=execution_policy.mode,
        runtime_llm_requested=execution_policy.runtime_llm_requested,
        runtime_llm_allowed=execution_policy.allow_runtime_llm,
        runtime_llm_effective=execution_policy.runtime_llm_effective,
        deterministic_build=execution_policy.deterministic_build,
        final_claim_eligible=execution_policy.final_claim_eligible,
        valid=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
    if errors and not allow_unverified:
        raise ModelContractError("\n".join(errors))
    return result
