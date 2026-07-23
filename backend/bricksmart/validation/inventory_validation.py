"""Inventory validation helpers.

This module recounts final parts and verifies that a completed or attempted
build stays within the selected inventory profile.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from bricksmart.inventory.models import EffectiveInventory, InventoryMode
from bricksmart.planning.models import Placement


def validate_final_inventory(
    *,
    final_parts: Iterable[Placement],
    inventory: EffectiveInventory,
    ledger_committed: dict[str, int],
) -> dict[str, object]:
    """Validate final inventory.
    
    :param final_parts: The final parts value.
    :type final_parts: Iterable[Placement]
    :param inventory: Inventory data used by the operation.
    :type inventory: EffectiveInventory
    :param ledger_committed: The ledger committed value.
    :type ledger_committed: dict[str, int]
    :returns: The result produced by the function.
    :rtype: dict[str, object]
    """
    recount = dict(Counter(part.block_type for part in final_parts))
    exceeded: dict[str, dict[str, int]] = {}

    if inventory.mode is InventoryMode.FINITE:
        for block_type, used in recount.items():
            limit = inventory.limit_for(block_type) or 0
            if used > limit:
                exceeded[block_type] = {
                    "used": used,
                    "limit": limit,
                    "excess": used - limit,
                }

    all_keys = set(recount) | set(ledger_committed)
    mismatches = {
        block_type: {
            "final_recount": recount.get(block_type, 0),
            "ledger_committed": ledger_committed.get(block_type, 0),
        }
        for block_type in sorted(all_keys)
        if recount.get(block_type, 0) != ledger_committed.get(block_type, 0)
    }

    if exceeded:
        status = "FAIL_INVENTORY_EXCEEDED"
    elif mismatches:
        status = "FAIL_INVENTORY_LEDGER_MISMATCH"
    else:
        status = "PASS"

    return {
        "status": status,
        "final_recount": recount,
        "ledger_committed": dict(ledger_committed),
        "exceeded": exceeded,
        "ledger_mismatches": mismatches,
    }
