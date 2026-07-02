from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from .types import ModelRecord, ResolvedModel

_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ALLOWED_SUFFIXES = {".obj"}


def sha256_stream(handle: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = handle.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        digest.update(chunk)
    return digest.hexdigest(), size


def safe_model_id(value: str) -> str:
    model_id = str(value or "").strip()
    if not _MODEL_ID_RE.fullmatch(model_id):
        raise ValueError(
            "model_id must start with an alphanumeric character and contain only "
            "letters, numbers, '.', '_', or '-' (maximum 128 characters)"
        )
    return model_id


class LocalModelStore:
    """Content-addressed model store with stable ``model://`` identifiers.

    The object bytes are deduplicated by SHA-256. Model IDs are small manifests
    that can be repointed to a newer immutable object without changing runtime
    code or task-context layout.
    """

    def __init__(self, root: str | Path, *, max_bytes: int = 512 * 1024 * 1024):
        self.root = Path(root).expanduser().resolve()
        self.max_bytes = int(max_bytes)
        self.objects_dir = self.root / "objects" / "sha256"
        self.manifests_dir = self.root / "manifests"
        self.tmp_dir = self.root / "tmp"
        for path in (self.objects_dir, self.manifests_dir, self.tmp_dir):
            path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_environment(cls, project_root: str | Path) -> "LocalModelStore":
        project = Path(project_root).expanduser().resolve()
        root = Path(os.environ.get("BRICKSMART_MODEL_STORE_ROOT", project / "model_store"))
        max_bytes = int(os.environ.get("BRICKSMART_MODEL_MAX_BYTES", str(512 * 1024 * 1024)))
        return cls(root, max_bytes=max_bytes)

    def _object_path(self, digest: str, suffix: str = ".obj") -> Path:
        return self.objects_dir / digest[:2] / f"{digest}{suffix.lower()}"

    def _manifest_path(self, model_id: str) -> Path:
        return self.manifests_dir / f"{safe_model_id(model_id)}.json"

    def import_file(
        self,
        source: str | Path,
        *,
        model_id: str,
        expected_sha256: str | None = None,
        metadata: dict[str, Any] | None = None,
        original_filename: str | None = None,
        media_type: str = "model/obj",
    ) -> ModelRecord:
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        with source_path.open("rb") as handle:
            return self.import_stream(
                handle,
                model_id=model_id,
                filename=original_filename or source_path.name,
                expected_sha256=expected_sha256,
                metadata=metadata,
                media_type=media_type,
            )

    def import_stream(
        self,
        handle: BinaryIO,
        *,
        model_id: str,
        filename: str,
        expected_sha256: str | None = None,
        metadata: dict[str, Any] | None = None,
        media_type: str = "model/obj",
    ) -> ModelRecord:
        model_id = safe_model_id(model_id)
        suffix = Path(filename).suffix.lower()
        if suffix not in _ALLOWED_SUFFIXES:
            raise ValueError(f"Unsupported model file type {suffix!r}; expected one of {sorted(_ALLOWED_SUFFIXES)}")

        with tempfile.NamedTemporaryFile(dir=self.tmp_dir, delete=False, suffix=suffix) as tmp:
            temp_path = Path(tmp.name)
            digest = hashlib.sha256()
            size = 0
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > self.max_bytes:
                    temp_path.unlink(missing_ok=True)
                    raise ValueError(f"Model exceeds maximum size of {self.max_bytes} bytes")
                digest.update(chunk)
                tmp.write(chunk)
        sha = digest.hexdigest()
        expected = str(expected_sha256 or "").strip().lower()
        if expected and sha != expected:
            temp_path.unlink(missing_ok=True)
            raise ValueError(f"Model SHA-256 mismatch: expected {expected}, got {sha}")

        object_path = self._object_path(sha, suffix)
        object_path.parent.mkdir(parents=True, exist_ok=True)
        if object_path.exists():
            temp_path.unlink(missing_ok=True)
        else:
            os.replace(temp_path, object_path)

        record = ModelRecord(
            model_id=model_id,
            canonical_uri=f"model://{model_id}",
            sha256=sha,
            size_bytes=size,
            object_path=str(object_path.relative_to(self.root)),
            original_filename=Path(filename).name,
            media_type=media_type,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata=dict(metadata or {}),
        )
        manifest = self._manifest_path(model_id)
        temp_manifest = manifest.with_suffix(".json.tmp")
        temp_manifest.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")
        os.replace(temp_manifest, manifest)
        return record

    def get(self, model_id: str) -> ModelRecord:
        manifest = self._manifest_path(model_id)
        if not manifest.is_file():
            raise FileNotFoundError(f"Unknown model ID: {model_id}")
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        return ModelRecord(**payload)

    def resolve(self, model_id: str) -> ResolvedModel:
        record = self.get(model_id)
        path = (self.root / record.object_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Stored model object is missing: {path}")
        return ResolvedModel(
            requested_uri=f"model://{record.model_id}",
            canonical_uri=record.canonical_uri,
            local_path=path,
            sha256=record.sha256,
            size_bytes=record.size_bytes,
            source_kind="model_store",
            model_id=record.model_id,
            cache_hit=True,
            original_filename=record.original_filename,
        )

    def list_records(self) -> list[ModelRecord]:
        records: list[ModelRecord] = []
        for path in sorted(self.manifests_dir.glob("*.json")):
            try:
                records.append(ModelRecord(**json.loads(path.read_text(encoding="utf-8"))))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        return records

    def delete_manifest(self, model_id: str) -> None:
        self._manifest_path(model_id).unlink(missing_ok=True)
