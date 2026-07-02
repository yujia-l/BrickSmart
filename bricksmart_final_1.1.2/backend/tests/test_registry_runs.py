from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from bricksmart.app import app
from bricksmart.model_registry import LocalModelRegistry
from bricksmart.run_store import LocalRunStore

ROOT = Path(__file__).resolve().parents[2]


def test_packaged_contracts_live_in_model_registry() -> None:
    contexts = list((ROOT / "model_registry/contracts").glob("*/versions/*/task_context.json"))
    assert len(contexts) >= 3
    assert not (ROOT / "pipeline_runtime/json").exists()
    for path in contexts:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert "output_dir" not in (payload.get("paths", {}) or {})


def test_contract_registry_resolves_current_and_version() -> None:
    registry = LocalModelRegistry(ROOT / "model_registry")
    current = registry.resolve("contract://bird-standard-kit")
    validated = registry.resolve("contract://bird-standard-kit@validated-1")
    baseline = registry.resolve("contract://bird-standard-kit@baseline")
    assert current.context_sha256 == validated.context_sha256
    assert current.canonical_uri.endswith("@validated-1")
    assert current.context_sha256 != baseline.context_sha256
    assert Path(current.context_path).is_file()
    assert Path(current.confirmations_path or "").is_file()


def test_run_store_isolates_inputs_logs_and_artifacts(tmp_path: Path) -> None:
    store = LocalRunStore(tmp_path / "runs")
    first = store.create(model_id="example", contract_uri="contract://example@revision-1")
    second = store.create(model_id="example", contract_uri="contract://example@revision-1")
    assert first.run_id != second.run_id
    assert first.artifacts_dir.parent == first.run_dir
    assert first.logs_dir.parent == first.run_dir
    assert first.inputs_dir.parent == first.run_dir
    assert json.loads(first.manifest_path.read_text())["status"] == "created"


def test_engine_accepts_run_output_override() -> None:
    source = (ROOT / "backend/bricksmart/row_column_engine.py").read_text(encoding="utf-8")
    assert "BRICKSMART_OUTPUT_DIR" in source


def test_api_lists_contracts_and_runs() -> None:
    client = TestClient(app)
    contracts = client.get("/api/contracts")
    runs = client.get("/api/runs")
    assert contracts.status_code == 200
    assert any(row["canonical_uri"].startswith("contract://bird-standard-kit") for row in contracts.json())
    assert runs.status_code == 200
    assert runs.json() == []


def test_contract_upload_creates_versioned_revision(tmp_path: Path, monkeypatch) -> None:
    import bricksmart.app as app_module

    registry = LocalModelRegistry(tmp_path / "registry")
    monkeypatch.setattr(app_module, "MODEL_REGISTRY", registry)
    context = {
        "schema_version": "bricksmart-model-contract-1.0",
        "task_id": "uploaded",
        "model_id": "uploaded-model",
        "model_source": {"uri": "model://bird-base"},
        "paths": {"catalog_xlsx": "block_catalog/block_definitions.xlsx"},
        "segment_semantics": {"labels_file": "labels.csv"},
        "functional_assemblies": [],
    }
    response = TestClient(app_module.app).post(
        "/api/contracts/upload",
        data={"contract_id": "uploaded-contract", "version_id": "teacher-review-1"},
        files={
            "task_context": ("context.json", json.dumps(context), "application/json"),
            "confirmations": ("labels.csv", "segment_id,confirmed_label,confirmation_status\n1,body,confirmed\n", "text/csv"),
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["canonical_uri"] == "contract://uploaded-contract@teacher-review-1"
    stored = Path(payload["context_path"])
    assert stored.is_file()
    assert "output_dir" not in json.loads(stored.read_text()).get("paths", {})
