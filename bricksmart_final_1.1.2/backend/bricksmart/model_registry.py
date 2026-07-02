from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Mapping
from urllib.parse import urlparse


def _safe_id(value: str, *, field: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value).strip()).strip("-.")
    if not text or text in {".", ".."}:
        raise ValueError(f"{field} must contain at least one letter or number")
    return text.lower()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _record_from_manifest(path: Path) -> "ContractRecord":
    payload = json.loads(path.read_text(encoding="utf-8"))
    version_dir = path.parent
    for key in ("context_path", "confirmations_path"):
        value = payload.get(key)
        if value and not Path(value).is_absolute():
            payload[key] = str((version_dir / value).resolve())
    return ContractRecord(**payload)


@dataclass(frozen=True)
class ContractRecord:
    contract_id: str
    version_id: str
    canonical_uri: str
    context_path: str
    confirmations_path: str | None
    context_sha256: str
    confirmations_sha256: str | None
    model_id: str
    model_uri: str | None
    created_at: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LocalModelRegistry:
    """Versioned local registry for model-specific build contracts.

    Model meshes live in ``model_store``. This registry stores task contexts,
    confirmation artifacts, and immutable revision metadata. Updating a model
    creates a new revision rather than mutating a prior run's inputs.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.contracts_dir = self.root / "contracts"
        self.contracts_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_environment(cls, project_root: str | Path) -> "LocalModelRegistry":
        configured = os.environ.get("BRICKSMART_MODEL_REGISTRY_ROOT")
        root = Path(configured).expanduser() if configured else Path(project_root) / "model_registry"
        return cls(root)

    def _contract_dir(self, contract_id: str) -> Path:
        return self.contracts_dir / _safe_id(contract_id, field="contract_id")

    def _version_dir(self, contract_id: str, version_id: str) -> Path:
        return self._contract_dir(contract_id) / "versions" / _safe_id(version_id, field="version_id")

    def register_files(
        self,
        *,
        task_context_path: str | Path,
        confirmations_path: str | Path | None = None,
        contract_id: str | None = None,
        version_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        set_current: bool = True,
    ) -> ContractRecord:
        source_context = Path(task_context_path).expanduser().resolve()
        if not source_context.is_file():
            raise FileNotFoundError(f"Task context does not exist: {source_context}")
        payload = json.loads(source_context.read_text(encoding="utf-8"))
        resolved_contract_id = _safe_id(
            contract_id
            or payload.get("contract_id")
            or payload.get("task_id")
            or payload.get("model_id")
            or source_context.stem,
            field="contract_id",
        )
        semantics = payload.setdefault("segment_semantics", {})
        configured_labels = semantics.get("labels_file")
        source_confirmations: Path | None = None
        if confirmations_path is not None:
            source_confirmations = Path(confirmations_path).expanduser().resolve()
        elif configured_labels:
            candidate = (source_context.parent / str(configured_labels)).resolve()
            if candidate.is_file():
                source_confirmations = candidate
        if source_confirmations is not None and not source_confirmations.is_file():
            raise FileNotFoundError(f"Confirmation artifact does not exist: {source_confirmations}")

        # Runtime output paths are execution concerns and do not belong to an
        # immutable model contract. Keep catalog configuration, remove only the
        # historical output location.
        paths = payload.setdefault("paths", {})
        paths.pop("output_dir", None)
        payload["contract_id"] = resolved_contract_id

        confirmations_bytes = source_confirmations.read_bytes() if source_confirmations else b""
        if source_confirmations:
            stored_confirmation_name = "segment_confirmations" + source_confirmations.suffix.lower()
            semantics["labels_file"] = stored_confirmation_name
        else:
            stored_confirmation_name = None

        canonical_context = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        combined = hashlib.sha256(canonical_context + b"\0" + confirmations_bytes).hexdigest()
        resolved_version_id = _safe_id(version_id or combined[:16], field="version_id")
        version_dir = self._version_dir(resolved_contract_id, resolved_version_id)
        version_dir.mkdir(parents=True, exist_ok=True)
        context_target = version_dir / "task_context.json"
        context_target.write_bytes(canonical_context)
        confirmations_target: Path | None = None
        if source_confirmations and stored_confirmation_name:
            confirmations_target = version_dir / stored_confirmation_name
            if not confirmations_target.exists() or confirmations_target.read_bytes() != confirmations_bytes:
                confirmations_target.write_bytes(confirmations_bytes)

        model_source = payload.get("model_source") or {}
        model_uri = model_source.get("uri") if isinstance(model_source, dict) else str(model_source or "")
        model_id = str(
            (model_source.get("model_id") if isinstance(model_source, dict) else None)
            or payload.get("model_id")
            or payload.get("task_id")
            or resolved_contract_id
        )
        record = ContractRecord(
            contract_id=resolved_contract_id,
            version_id=resolved_version_id,
            canonical_uri=f"contract://{resolved_contract_id}@{resolved_version_id}",
            context_path=str(context_target.resolve()),
            confirmations_path=str(confirmations_target.resolve()) if confirmations_target else None,
            context_sha256=_sha256(context_target),
            confirmations_sha256=_sha256(confirmations_target) if confirmations_target else None,
            model_id=model_id,
            model_uri=str(model_uri) if model_uri else None,
            created_at=_utc_now(),
            metadata=dict(metadata or {}),
        )
        manifest_payload = record.to_dict()
        manifest_payload["context_path"] = context_target.name
        manifest_payload["confirmations_path"] = confirmations_target.name if confirmations_target else None
        (version_dir / "manifest.json").write_text(
            json.dumps(manifest_payload, indent=2), encoding="utf-8"
        )
        contract_dir = self._contract_dir(resolved_contract_id)
        contract_dir.mkdir(parents=True, exist_ok=True)
        if set_current:
            (contract_dir / "current.json").write_text(
                json.dumps({"version_id": resolved_version_id, "canonical_uri": record.canonical_uri}, indent=2),
                encoding="utf-8",
            )
        return record

    def register_streams(
        self,
        *,
        task_context: BinaryIO,
        task_context_filename: str,
        confirmations: BinaryIO | None,
        confirmations_filename: str | None,
        contract_id: str,
        version_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ContractRecord:
        tmp = self.root / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        context_tmp = tmp / f"context-{os.getpid()}-{_safe_id(task_context_filename, field='filename')}"
        context_tmp.write_bytes(task_context.read())
        confirmation_tmp: Path | None = None
        try:
            if confirmations is not None:
                confirmation_tmp = tmp / f"confirmations-{os.getpid()}-{_safe_id(confirmations_filename or 'segments.csv', field='filename')}"
                confirmation_tmp.write_bytes(confirmations.read())
            return self.register_files(
                task_context_path=context_tmp,
                confirmations_path=confirmation_tmp,
                contract_id=contract_id,
                version_id=version_id,
                metadata=metadata,
            )
        finally:
            context_tmp.unlink(missing_ok=True)
            if confirmation_tmp:
                confirmation_tmp.unlink(missing_ok=True)

    def resolve(self, reference: str | Path) -> ContractRecord:
        value = str(reference)
        parsed = urlparse(value)
        if parsed.scheme == "contract":
            target = (parsed.netloc + parsed.path).strip("/")
            if "@" in target:
                contract_id, version_id = target.rsplit("@", 1)
            else:
                contract_id, version_id = target, ""
            contract_id = _safe_id(contract_id, field="contract_id")
            if not version_id:
                current = self._contract_dir(contract_id) / "current.json"
                if not current.is_file():
                    raise FileNotFoundError(f"No current contract revision for contract://{contract_id}")
                version_id = json.loads(current.read_text(encoding="utf-8"))["version_id"]
            manifest = self._version_dir(contract_id, version_id) / "manifest.json"
            if not manifest.is_file():
                raise FileNotFoundError(f"Unknown contract revision: contract://{contract_id}@{version_id}")
            return _record_from_manifest(manifest)

        path = Path(reference).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Task context does not exist: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        semantics = payload.get("segment_semantics", {}) or {}
        labels = semantics.get("labels_file")
        confirmations = (path.parent / labels).resolve() if labels else None
        return ContractRecord(
            contract_id=str(payload.get("contract_id") or payload.get("task_id") or path.stem),
            version_id="external",
            canonical_uri=path.as_uri(),
            context_path=str(path),
            confirmations_path=str(confirmations) if confirmations and confirmations.is_file() else None,
            context_sha256=_sha256(path),
            confirmations_sha256=_sha256(confirmations) if confirmations and confirmations.is_file() else None,
            model_id=str(payload.get("model_id") or payload.get("task_id") or path.stem),
            model_uri=((payload.get("model_source") or {}).get("uri") if isinstance(payload.get("model_source"), dict) else None),
            created_at="external",
            metadata={"source_kind": "external_file"},
        )

    def get(self, contract_id: str, version_id: str | None = None) -> ContractRecord:
        suffix = f"@{version_id}" if version_id else ""
        return self.resolve(f"contract://{contract_id}{suffix}")

    def list_records(self, *, current_only: bool = True) -> list[ContractRecord]:
        records: list[ContractRecord] = []
        for contract_dir in sorted(self.contracts_dir.iterdir() if self.contracts_dir.exists() else []):
            if not contract_dir.is_dir():
                continue
            try:
                if current_only:
                    records.append(self.get(contract_dir.name))
                else:
                    for manifest in sorted((contract_dir / "versions").glob("*/manifest.json")):
                        records.append(_record_from_manifest(manifest))
            except (FileNotFoundError, TypeError, json.JSONDecodeError):
                continue
        return records

    def delete_contract(self, contract_id: str) -> None:
        shutil.rmtree(self._contract_dir(contract_id), ignore_errors=True)
