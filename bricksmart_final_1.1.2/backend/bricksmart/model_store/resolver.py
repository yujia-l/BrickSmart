from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

import requests

from .local import LocalModelStore
from .types import ModelSourceSpec, ResolvedModel


class ModelResolver:
    """Resolve model references into local immutable files for the planner."""

    def __init__(
        self,
        *,
        project_root: str | Path,
        store: LocalModelStore | None = None,
        allow_remote: bool | None = None,
        remote_host_allowlist: set[str] | None = None,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.store = store or LocalModelStore.from_environment(self.project_root)
        self.allow_remote = (
            bool(allow_remote)
            if allow_remote is not None
            else os.environ.get("BRICKSMART_ALLOW_REMOTE_MODELS", "0") == "1"
        )
        configured_hosts = {
            host.strip().lower()
            for host in os.environ.get("BRICKSMART_REMOTE_MODEL_HOSTS", "").split(",")
            if host.strip()
        }
        self.remote_host_allowlist = remote_host_allowlist if remote_host_allowlist is not None else configured_hosts

    def resolve(
        self,
        source: ModelSourceSpec | str | Mapping[str, Any],
        *,
        context_path: str | Path | None = None,
        default_model_id: str | None = None,
    ) -> ResolvedModel:
        spec = source if isinstance(source, ModelSourceSpec) else ModelSourceSpec.from_mapping(source)
        if _looks_like_windows_absolute_path(spec.uri):
            return self._resolve_local(Path(spec.uri), spec, default_model_id=default_model_id)

        parsed = urlparse(spec.uri)
        scheme = parsed.scheme.lower()
        if scheme == "model":
            model_id = (parsed.netloc + parsed.path).strip("/")
            resolved = self.store.resolve(model_id)
            return self._verify(resolved, spec.expected_sha256)
        if scheme == "sha256":
            digest = (parsed.netloc + parsed.path).strip("/").lower()
            matches = list((self.store.objects_dir / digest[:2]).glob(f"{digest}.*"))
            if len(matches) != 1:
                raise FileNotFoundError(f"No unique stored model object for sha256://{digest}")
            path = matches[0].resolve()
            return self._verify(
                ResolvedModel(
                    requested_uri=spec.uri,
                    canonical_uri=f"sha256://{digest}",
                    local_path=path,
                    sha256=digest,
                    size_bytes=path.stat().st_size,
                    source_kind="content_address",
                    cache_hit=True,
                    original_filename=spec.filename or path.name,
                ),
                spec.expected_sha256,
            )
        if scheme in {"http", "https"}:
            return self._resolve_http(spec, default_model_id=default_model_id)
        if scheme == "s3":
            return self._resolve_s3(spec, default_model_id=default_model_id)
        if scheme == "file":
            path_text = url2pathname(unquote(parsed.path))
            path = Path(f"//{parsed.netloc}{path_text}" if parsed.netloc else path_text)
            return self._resolve_local(path, spec, default_model_id=default_model_id)
        if scheme:
            raise ValueError(f"Unsupported model URI scheme: {scheme}")

        candidate = Path(spec.uri).expanduser()
        if not candidate.is_absolute():
            context_dir = Path(context_path).expanduser().resolve().parent if context_path else self.project_root
            candidates = [
                context_dir / candidate,
                self.project_root / candidate,
                self.project_root / "pipeline_runtime" / candidate,
            ]
            candidate = next((p for p in candidates if p.exists()), candidates[0])
        return self._resolve_local(candidate, spec, default_model_id=default_model_id)

    def _resolve_local(
        self,
        path: Path,
        spec: ModelSourceSpec,
        *,
        default_model_id: str | None,
    ) -> ResolvedModel:
        source = path.expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Configured source model is missing: {source}")
        model_id = spec.model_id or default_model_id
        if model_id:
            record = self.store.import_file(
                source,
                model_id=model_id,
                expected_sha256=spec.expected_sha256,
                original_filename=spec.filename or source.name,
                metadata={"imported_from": str(source), "source_kind": "local_path_import"},
            )
            resolved = self.store.resolve(record.model_id)
            return ResolvedModel(
                **{**resolved.__dict__, "requested_uri": spec.uri, "cache_hit": False}
            )
        digest = self._sha(source)
        return self._verify(
            ResolvedModel(
                requested_uri=spec.uri,
                canonical_uri=source.as_uri(),
                local_path=source,
                sha256=digest,
                size_bytes=source.stat().st_size,
                source_kind="local_file",
                cache_hit=True,
                original_filename=source.name,
            ),
            spec.expected_sha256,
        )

    def _resolve_http(self, spec: ModelSourceSpec, *, default_model_id: str | None) -> ResolvedModel:
        if not self.allow_remote:
            raise ValueError("Remote model URLs are disabled. Set BRICKSMART_ALLOW_REMOTE_MODELS=1 to enable them.")
        parsed = urlparse(spec.uri)
        host = (parsed.hostname or "").lower()
        if self.remote_host_allowlist and host not in self.remote_host_allowlist:
            raise ValueError(f"Remote model host is not allowlisted: {host}")
        filename = spec.filename or Path(parsed.path).name or "model.obj"
        model_id = spec.model_id or default_model_id
        if not model_id:
            raise ValueError("Remote model sources require model_source.model_id or a context model_id")
        with requests.get(spec.uri, stream=True, timeout=(10, 120), allow_redirects=False) as response:
            response.raise_for_status()
            declared = int(response.headers.get("content-length", "0") or 0)
            if declared and declared > self.store.max_bytes:
                raise ValueError(f"Remote model exceeds maximum size of {self.store.max_bytes} bytes")
            response.raw.decode_content = True
            record = self.store.import_stream(
                response.raw,
                model_id=model_id,
                filename=filename,
                expected_sha256=spec.expected_sha256,
                metadata={"source_uri": spec.uri, "source_kind": "https"},
                media_type=spec.media_type or response.headers.get("content-type", "model/obj"),
            )
        resolved = self.store.resolve(record.model_id)
        return ResolvedModel(**{**resolved.__dict__, "requested_uri": spec.uri, "cache_hit": False})

    def _resolve_s3(self, spec: ModelSourceSpec, *, default_model_id: str | None) -> ResolvedModel:
        if not self.allow_remote:
            raise ValueError("Remote model URIs are disabled. Set BRICKSMART_ALLOW_REMOTE_MODELS=1 to enable them.")
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Resolving s3:// models requires the optional 'boto3' dependency") from exc
        parsed = urlparse(spec.uri)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        filename = spec.filename or Path(key).name or "model.obj"
        model_id = spec.model_id or default_model_id
        if not model_id:
            raise ValueError("S3 model sources require model_source.model_id or a context model_id")
        with tempfile.NamedTemporaryFile(dir=self.store.tmp_dir, suffix=Path(filename).suffix or ".obj") as tmp:
            boto3.client("s3").download_fileobj(bucket, key, tmp)
            tmp.flush()
            tmp.seek(0)
            record = self.store.import_stream(
                tmp,
                model_id=model_id,
                filename=filename,
                expected_sha256=spec.expected_sha256,
                metadata={"source_uri": spec.uri, "source_kind": "s3"},
                media_type=spec.media_type or "model/obj",
            )
        resolved = self.store.resolve(record.model_id)
        return ResolvedModel(**{**resolved.__dict__, "requested_uri": spec.uri, "cache_hit": False})

    @staticmethod
    def _sha(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _verify(resolved: ResolvedModel, expected: str | None) -> ResolvedModel:
        expected = str(expected or "").strip().lower()
        if expected and resolved.sha256.lower() != expected:
            raise ValueError(f"Model SHA-256 mismatch: expected {expected}, got {resolved.sha256}")
        return resolved


def _looks_like_windows_absolute_path(value: str) -> bool:
    return len(value) >= 3 and value[1] == ":" and value[2] in {"\\", "/"} and value[0].isalpha()
