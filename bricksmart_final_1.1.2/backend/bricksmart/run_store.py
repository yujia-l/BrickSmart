from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _safe(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value).strip()).strip("-.").lower()
    return text or "model"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class RunPaths:
    run_id: str
    run_dir: Path
    artifacts_dir: Path
    logs_dir: Path
    inputs_dir: Path
    manifest_path: Path

    def to_dict(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}


class LocalRunStore:
    """Create isolated, immutable-by-default directories for build executions."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_environment(cls, project_root: str | Path) -> "LocalRunStore":
        configured = os.environ.get("BRICKSMART_RUNS_ROOT")
        root = Path(configured).expanduser() if configured else Path(project_root) / "runs"
        return cls(root)

    def create(
        self,
        *,
        model_id: str,
        contract_uri: str,
        run_id: str | None = None,
        replace: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> RunPaths:
        timestamp = _now().strftime("%Y%m%dT%H%M%SZ")
        resolved_id = _safe(run_id) if run_id else f"{timestamp}-{_safe(model_id)}-{uuid.uuid4().hex[:8]}"
        run_dir = self.root / resolved_id
        if run_dir.exists():
            if not replace:
                raise FileExistsError(f"Run already exists: {run_dir}")
            shutil.rmtree(run_dir)
        artifacts = run_dir / "artifacts"
        logs = run_dir / "logs"
        inputs = run_dir / "inputs"
        for path in (artifacts, logs, inputs):
            path.mkdir(parents=True, exist_ok=True)
        manifest = run_dir / "run.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": "bricksmart-run-v1",
                    "run_id": resolved_id,
                    "status": "created",
                    "created_at": _now().isoformat().replace("+00:00", "Z"),
                    "model_id": model_id,
                    "contract_uri": contract_uri,
                    "artifacts_dir": str(artifacts),
                    "logs_dir": str(logs),
                    "inputs_dir": str(inputs),
                    "metadata": dict(metadata or {}),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return RunPaths(resolved_id, run_dir, artifacts, logs, inputs, manifest)

    @staticmethod
    def update(paths: RunPaths, **values: Any) -> None:
        payload = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
        payload.update(values)
        payload["updated_at"] = _now().isoformat().replace("+00:00", "Z")
        paths.manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list_runs(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for manifest in sorted(self.root.glob("*/run.json"), reverse=True):
            try:
                rows.append(json.loads(manifest.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        return rows

    def get(self, run_id: str) -> dict[str, Any]:
        path = self.root / _safe(run_id) / "run.json"
        if not path.is_file():
            raise FileNotFoundError(f"Unknown run: {run_id}")
        return json.loads(path.read_text(encoding="utf-8"))
