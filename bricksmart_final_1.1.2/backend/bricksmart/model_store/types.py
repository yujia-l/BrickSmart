from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class ModelSourceSpec:
    uri: str
    expected_sha256: str | None = None
    model_id: str | None = None
    filename: str | None = None
    media_type: str | None = None

    @classmethod
    def from_mapping(cls, value: str | Mapping[str, Any]) -> "ModelSourceSpec":
        if isinstance(value, str):
            return cls(uri=value)
        uri = str(value.get("uri") or value.get("source_uri") or "").strip()
        if not uri:
            raise ValueError("model_source.uri is required")
        expected = str(
            value.get("expected_sha256")
            or value.get("sha256")
            or ""
        ).strip().lower() or None
        return cls(
            uri=uri,
            expected_sha256=expected,
            model_id=(str(value.get("model_id") or "").strip() or None),
            filename=(str(value.get("filename") or "").strip() or None),
            media_type=(str(value.get("media_type") or "").strip() or None),
        )


@dataclass(frozen=True)
class ModelRecord:
    model_id: str
    canonical_uri: str
    sha256: str
    size_bytes: int
    object_path: str
    original_filename: str
    media_type: str
    created_at: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResolvedModel:
    requested_uri: str
    canonical_uri: str
    local_path: Path
    sha256: str
    size_bytes: int
    source_kind: str
    model_id: str | None = None
    cache_hit: bool = False
    original_filename: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["local_path"] = str(self.local_path)
        return payload
