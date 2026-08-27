from __future__ import annotations

import json
from pathlib import Path

import pytest

from bricksmart.runtime import resolve_execution_policy
from bricksmart.runtime.contract import ModelContractError, validate_model_contract

ROOT = Path(__file__).resolve().parents[2]


def test_validated_mode_is_deterministic_by_default() -> None:
    """Test that validated mode is deterministic by default."""
    policy = resolve_execution_policy({})
    assert policy.mode == "validated"
    assert policy.runtime_llm_effective is False
    assert policy.deterministic_build is True
    assert policy.final_claim_eligible is True


def test_validated_mode_rejects_runtime_llm_request() -> None:
    """Test that validated mode rejects runtime llm request."""
    policy = resolve_execution_policy({
        "execution_policy": {"mode": "validated", "allow_runtime_llm": False},
        "llm": {"llm2": {"enabled": True}},
    })
    assert policy.errors
    assert policy.runtime_llm_effective is False
    assert policy.final_claim_eligible is False


def test_exploratory_llm_mode_is_provisional() -> None:
    """Test that exploratory llm mode is provisional."""
    policy = resolve_execution_policy({
        "execution_policy": {"mode": "exploratory", "allow_runtime_llm": True},
        "llm": {"llm2": {"enabled": True}},
    })
    assert not policy.errors
    assert policy.runtime_llm_effective is True
    assert policy.deterministic_build is False
    assert policy.final_claim_eligible is False


def test_current_packaged_contracts_are_validated_and_llm_free() -> None:
    """Test that current packaged contracts are validated and llm free."""
    contracts = ROOT / "model_registry" / "contracts"
    for current_file in contracts.glob("*/current.json"):
        current = json.loads(current_file.read_text(encoding="utf-8"))
        context_path = current_file.parent / "versions" / current["version_id"] / "task_context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        policy = resolve_execution_policy(context)
        assert policy.mode == "validated"
        assert policy.runtime_llm_requested is False
        assert policy.runtime_llm_effective is False
        assert policy.final_claim_eligible is True


def test_contract_validator_rejects_validated_runtime_llm(tmp_path: Path, catalog_csv: Path) -> None:
    """Test that contract validator rejects validated runtime llm.
    
    :param tmp_path: Temporary filesystem path provided by pytest.
    :type tmp_path: Path
    :param catalog_csv: The catalog csv value.
    :type catalog_csv: Path
    """
    source = tmp_path / "model.obj"
    source.write_text("o x\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    confirmations = tmp_path / "segments.csv"
    confirmations.write_text(
        "segment_id,confirmation_status,confirmed_label\n1,confirmed,body\n",
        encoding="utf-8",
    )
    context = tmp_path / "context.json"
    context.write_text(json.dumps({
        "schema_version": "bricksmart-model-contract-1.0",
        "model_id": "fixture",
        "task_id": "fixture",
        "model_source": {"uri": source.as_uri(), "model_id": "fixture"},
        "paths": {"catalog_csv": str(catalog_csv)},
        "segment_semantics": {"labels_file": confirmations.name},
        "functional_assemblies": [],
        "execution_policy": {"mode": "validated", "allow_runtime_llm": False},
        "llm": {"llm2": {"enabled": True}},
    }), encoding="utf-8")
    with pytest.raises(ModelContractError, match="cannot enable llm.llm2"):
        validate_model_contract(project_root=tmp_path, context_path=context)
