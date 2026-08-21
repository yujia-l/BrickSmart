from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_runtime_has_no_model_profile_enumeration() -> None:
    """Test that runtime has no model profile enumeration."""
    engine = (ROOT / "backend/bricksmart/row_column_engine.py").read_text(encoding="utf-8")
    runner = (ROOT / "backend/bricksmart/row_column_runner.py").read_text(encoding="utf-8")
    cli = (ROOT / "backend/bricksmart/build_cli.py").read_text(encoding="utf-8")
    assert "MODEL_PROFILE" not in engine
    assert "choices=[\"bird\", \"airplane\"]" not in cli
    assert "model_profile ==" not in runner


def test_active_runtime_has_no_named_model_cli() -> None:
    """Test that active runtime has no named model cli."""
    assert not (ROOT / "backend/bricksmart/airplane_cli.py").exists()
    assert not (ROOT / "backend/bricksmart/bird_cli.py").exists()


def test_packaged_contexts_use_generic_functional_assembly_schema() -> None:
    """Test that packaged contexts use generic functional assembly schema."""
    for path in (ROOT / "model_registry/contracts").glob("*/versions/*/task_context.json"):
        context = json.loads(path.read_text(encoding="utf-8"))
        assert context["schema_version"] in {"bricksmart-model-contract-1.0", "bricksmart-model-contract-1.0"}
        assert "model_id" in context
        assert "functional_assemblies" in context
        assert "propeller_assembly" not in (context.get("segment_assembly", {}) or {})


def test_catalog_remains_csv_catalog_single_source() -> None:
    """Test that catalog remains csv catalog single source."""
    catalog_dir = ROOT / "block_catalog"
    assert (catalog_dir / "block_definitions.csv").is_file()
    assert not list(catalog_dir.glob("block_definitions.xlsx"))
    assert not list(catalog_dir.glob("block_ids.csv"))


def test_runtime_supports_multiple_functional_subassembly_instances() -> None:
    """Test that runtime supports multiple functional subassembly instances."""
    engine = (ROOT / "backend/bricksmart/row_column_engine.py").read_text(encoding="utf-8")
    context = (ROOT / "backend/bricksmart/runtime/context.py").read_text(encoding="utf-8")
    assert "CUSTOM_FUNCTIONAL_SUBASSEMBLY_CONFIGS" in engine
    assert "custom_subassembly_instances" in engine
    assert 'segment_assembly["custom_functional_subassembly"]' not in context


def test_packaged_contexts_use_model_store_uris() -> None:
    """Test that packaged contexts use model store uris."""
    for path in (ROOT / "model_registry/contracts").glob("*/versions/*/task_context.json"):
        context = json.loads(path.read_text(encoding="utf-8"))
        assert context["model_source"]["uri"].startswith("model://")
        assert "source_model" not in (context.get("paths", {}) or {})


def test_packaged_obj_files_exist_only_in_model_store() -> None:
    """Test that packaged obj files exist only in model store."""
    obj_paths = [path.relative_to(ROOT) for path in ROOT.rglob("*.obj")]
    assert obj_paths
    assert all(path.parts[0] == "model_store" for path in obj_paths)


def test_validated_runtime_is_guarded_against_llm_network_calls() -> None:
    """Test that validated runtime is guarded against llm network calls."""
    engine = (ROOT / "backend/bricksmart/row_column_engine.py").read_text(encoding="utf-8")
    assert "LLM2_EFFECTIVE_ENABLED" in engine
    assert "BRICKSMART_RUNTIME_LLM_ALLOWED" in engine
    assert 'LLM2_CONFIG["enabled"] = LLM2_EFFECTIVE_ENABLED' in engine


def test_engine_worker_has_explicit_headless_shutdown() -> None:
    """Test that engine worker has explicit headless shutdown."""
    engine = (ROOT / "backend/bricksmart/row_column_engine.py").read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in engine
    assert 'os._exit(0)' in engine


def test_build_cli_has_explicit_success_shutdown() -> None:
    """Test that build cli has explicit success shutdown."""
    cli = (ROOT / "backend/bricksmart/build_cli.py").read_text(encoding="utf-8")
    assert "sys.stdout.flush()" in cli
    assert "os._exit(0)" in cli
