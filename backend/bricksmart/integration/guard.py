"""Repository integration guard checks.

This module verifies that model-agnostic boundaries are preserved and that
integration artifacts follow the expected BrickSmart ownership rules.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping, Any

from bricksmart.inventory.ledger import InventoryLedger
from bricksmart.planning.models import Placement
from bricksmart.validation.inventory_validation import validate_final_inventory


class InventoryGuard:
    """Small adapter intended for the existing unconstrained planning code."""

    def __init__(self, ledger: InventoryLedger):
        """Initialize the InventoryGuard instance.
        
        :param ledger: Inventory ledger used by the operation.
        :type ledger: InventoryLedger
        """
        self.ledger = ledger

    def can_place(self, block_types: Iterable[str]) -> bool:
        """Return whether can place.
        
        :param block_types: The block types value.
        :type block_types: Iterable[str]
        :returns: ``True`` when the condition is satisfied; otherwise ``False``.
        :rtype: bool
        """
        return self.ledger.can_reserve(dict(Counter(block_types)))

    def shortages(self, block_types: Iterable[str]) -> dict[str, dict[str, int]]:
        """Return the shortages value.
        
        :param block_types: The block types value.
        :type block_types: Iterable[str]
        :returns: The result produced by the function.
        :rtype: dict[str, dict[str, int]]
        """
        return self.ledger.shortages(dict(Counter(block_types)))

    def reserve_candidate(
        self,
        candidate_parts: Iterable[Mapping[str, Any]],
        *,
        reason: str,
    ) -> str:
        """Return the reserve candidate value.
        
        :param candidate_parts: The candidate parts value.
        :type candidate_parts: Iterable[Mapping[str, Any]]
        :param reason: The reason value.
        :type reason: str
        :returns: The result produced by the function.
        :rtype: str
        """
        requirements = dict(Counter(str(part["block_type"]) for part in candidate_parts))
        return self.ledger.reserve(requirements, reason=reason)

    def commit_candidate(self, reservation_id: str) -> None:
        """Perform the commit candidate operation.
        
        :param reservation_id: Identifier for the reservation.
        :type reservation_id: str
        """
        self.ledger.commit(reservation_id)

    def reject_candidate(self, reservation_id: str) -> None:
        """Perform the reject candidate operation.
        
        :param reservation_id: Identifier for the reservation.
        :type reservation_id: str
        """
        self.ledger.release(reservation_id)

    def validate_final_parts(
        self, final_parts: Iterable[Mapping[str, Any]]
    ) -> dict[str, object]:
        """Validate final parts.
        
        :param final_parts: The final parts value.
        :type final_parts: Iterable[Mapping[str, Any]]
        :returns: The result produced by the function.
        :rtype: dict[str, object]
        """
        placements = [
            Placement(
                part_id=str(part.get("part_id", index)),
                block_type=str(part["block_type"]),
                segment_id=(
                    None if part.get("segment_id") is None else str(part.get("segment_id"))
                ),
                step=(None if part.get("step") is None else int(part.get("step"))),
                metadata={
                    key: value
                    for key, value in part.items()
                    if key not in {"part_id", "block_type", "segment_id", "step"}
                },
            )
            for index, part in enumerate(final_parts)
        ]
        return validate_final_inventory(
            final_parts=placements,
            inventory=self.ledger.inventory,
            ledger_committed=self.ledger.committed_counts,
        )
