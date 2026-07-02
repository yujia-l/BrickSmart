from bricksmart.inventory.models import EffectiveInventory, InventoryMode
from bricksmart.planning.models import Placement
from bricksmart.validation import validate_final_inventory


def inventory(limit):
    return EffectiveInventory(
        inventory_id="test",
        mode=InventoryMode.FINITE,
        limits={"big_wheel": limit},
        limit_sources={"big_wheel": "physical_inventory"},
        physical_limits={"big_wheel": limit},
        teacher_limits={},
    )


def test_final_recount_detects_exceeded_inventory():
    parts = [Placement("a", "big_wheel"), Placement("b", "big_wheel")]
    result = validate_final_inventory(
        final_parts=parts,
        inventory=inventory(1),
        ledger_committed={"big_wheel": 2},
    )
    assert result["status"] == "FAIL_INVENTORY_EXCEEDED"


def test_final_recount_detects_ledger_mismatch():
    parts = [Placement("a", "big_wheel")]
    result = validate_final_inventory(
        final_parts=parts,
        inventory=inventory(4),
        ledger_committed={"big_wheel": 2},
    )
    assert result["status"] == "FAIL_INVENTORY_LEDGER_MISMATCH"
