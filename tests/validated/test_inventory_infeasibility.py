from __future__ import annotations

import json
from pathlib import Path

from bricksmart.row_column_runner import (
    _inventory_infeasibility_from_log,
    _write_inventory_infeasibility_artifacts,
    summarize_row_column_output,
)


def test_inventory_exhaustion_log_is_structured() -> None:
    """Test that inventory exhaustion log is structured."""
    log = (
        'bricksmart_inventory.inventory.InventoryExhaustedError: '
        'Inventory reservation failed for symmetry_pair:SP_001_010: '
        '{"standard_2x2x2": {"available": 16, "capacity": 16, '
        '"committed": 0, "required": 18, "reserved": 0, "shortage": 2}}'
    )
    result = _inventory_infeasibility_from_log(log)
    assert result is not None
    assert result["status"] == "INFEASIBLE_INVENTORY"
    assert result["failure_scope"] == "symmetry_pair:SP_001_010"
    assert result["shortages"]["standard_2x2x2"]["shortage"] == 2


def test_inventory_infeasibility_writes_normalized_artifacts(tmp_path: Path) -> None:
    """Test that inventory infeasibility writes normalized artifacts.
    
    :param tmp_path: Temporary filesystem path provided by pytest.
    :type tmp_path: Path
    """
    outcome = {
        "status": "INFEASIBLE_INVENTORY",
        "failure_scope": "symmetry_pair:SP_001_010",
        "shortages": {
            "standard_2x2x2": {
                "available": 16,
                "capacity": 16,
                "committed": 0,
                "required": 18,
                "reserved": 0,
                "shortage": 2,
            }
        },
    }
    _write_inventory_infeasibility_artifacts(
        output_dir=tmp_path,
        outcome=outcome,
        inventory_profile_path="config/inventory/standard_kit.yaml",
    )
    feasibility = json.loads((tmp_path / "inventory_feasibility.json").read_text())
    assert feasibility["status"] == "INFEASIBLE_INVENTORY"
    assert feasibility["build_instructions_html_generated"] is False
    summary = summarize_row_column_output(tmp_path)
    assert summary["final_claim_valid"] is False
    assert summary["final_status"] == "INFEASIBLE_INVENTORY"
    assert not (tmp_path / "build_instructions.html").exists()
