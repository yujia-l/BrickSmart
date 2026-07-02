from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bricksmart.app import MODEL_STORE, app
from bricksmart.model_store import LocalModelStore, ModelResolver


def _obj_bytes(name: str = "part") -> bytes:
    return f"o {name}\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n".encode()


def test_content_addressed_store_deduplicates_bytes(tmp_path: Path) -> None:
    store = LocalModelStore(tmp_path / "store")
    first = tmp_path / "first.obj"
    second = tmp_path / "second.obj"
    first.write_bytes(_obj_bytes())
    second.write_bytes(_obj_bytes())
    a = store.import_file(first, model_id="first-model")
    b = store.import_file(second, model_id="second-model")
    assert a.sha256 == b.sha256
    assert a.object_path == b.object_path
    assert store.resolve("first-model").local_path == store.resolve("second-model").local_path


def test_model_uri_resolves_registered_object(tmp_path: Path) -> None:
    source = tmp_path / "fixture.obj"
    source.write_bytes(_obj_bytes("fixture"))
    store = LocalModelStore(tmp_path / "store")
    record = store.import_file(source, model_id="fixture-model")
    resolved = ModelResolver(project_root=tmp_path, store=store).resolve("model://fixture-model")
    assert resolved.canonical_uri == "model://fixture-model"
    assert resolved.sha256 == record.sha256
    assert resolved.cache_hit is True


def test_model_resolver_rejects_checksum_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "fixture.obj"
    source.write_bytes(_obj_bytes())
    store = LocalModelStore(tmp_path / "store")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        ModelResolver(project_root=tmp_path, store=store).resolve(
            {"uri": str(source), "model_id": "fixture", "expected_sha256": "0" * 64},
            context_path=tmp_path / "context.json",
        )


def test_local_path_is_imported_to_store(tmp_path: Path) -> None:
    source = tmp_path / "local.obj"
    source.write_bytes(_obj_bytes("local"))
    store = LocalModelStore(tmp_path / "store")
    resolved = ModelResolver(project_root=tmp_path, store=store).resolve(
        {"uri": source.name, "model_id": "local-model"},
        context_path=tmp_path / "context.json",
    )
    assert resolved.canonical_uri == "model://local-model"
    assert store.get("local-model").sha256 == hashlib.sha256(source.read_bytes()).hexdigest()


def test_remote_urls_are_disabled_by_default(tmp_path: Path) -> None:
    resolver = ModelResolver(
        project_root=tmp_path,
        store=LocalModelStore(tmp_path / "store"),
        allow_remote=False,
    )
    with pytest.raises(ValueError, match="disabled"):
        resolver.resolve({"uri": "https://example.com/model.obj", "model_id": "remote"})


def test_api_upload_returns_stable_model_uri() -> None:
    client = TestClient(app)
    model_id = "pytest-upload-model"
    response = client.post(
        "/api/models/upload",
        data={"model_id": model_id},
        files={"file": ("upload.obj", _obj_bytes("upload"), "model/obj")},
    )
    try:
        assert response.status_code == 200
        payload = response.json()
        assert payload["canonical_uri"] == f"model://{model_id}"
        assert client.get(f"/api/models/{model_id}").status_code == 200
    finally:
        MODEL_STORE.delete_manifest(model_id)
