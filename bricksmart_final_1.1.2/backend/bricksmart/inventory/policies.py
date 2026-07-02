from __future__ import annotations

from bricksmart.inventory.ledger import InventoryLedger


def scarcity_penalty(
    ledger: InventoryLedger,
    requirements: dict[str, int],
    *,
    weight: float,
) -> float:
    """Penalize consuming scarce blocks without converting scarcity into a hard rule."""
    if weight <= 0:
        return 0.0
    penalty = 0.0
    for block_type, required in requirements.items():
        remaining = ledger.remaining(block_type)
        capacity = ledger.capacity(block_type)
        if remaining is None or capacity in (None, 0) or required == 0:
            continue
        post_remaining = remaining - required
        if post_remaining < 0:
            return float("inf")
        scarcity = 1.0 - (post_remaining / capacity)
        penalty += weight * scarcity * required
    return penalty
