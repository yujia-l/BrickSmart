from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping, Any

from bricksmart.inventory.ledger import InventoryLedger
from bricksmart.planning.models import Placement
from bricksmart.validation.inventory_validation import validate_final_inventory


class InventoryGuard:
    """Small adapter intended for the existing unconstrained planning code."""

    def __init__(self, ledger: InventoryLedger):
        self.ledger = ledger

    def can_place(self, block_types: Iterable[str]) -> bool:
        return self.ledger.can_reserve(dict(Counter(block_types)))

    def shortages(self, block_types: Iterable[str]) -> dict[str, dict[str, int]]:
        return self.ledger.shortages(dict(Counter(block_types)))

    def reserve_candidate(
        self,
        candidate_parts: Iterable[Mapping[str, Any]],
        *,
        reason: str,
    ) -> str:
        requirements = dict(Counter(str(part["block_type"]) for part in candidate_parts))
        return self.ledger.reserve(requirements, reason=reason)

    def commit_candidate(self, reservation_id: str) -> None:
        self.ledger.commit(reservation_id)

    def reject_candidate(self, reservation_id: str) -> None:
        self.ledger.release(reservation_id)

    def validate_final_parts(
        self, final_parts: Iterable[Mapping[str, Any]]
    ) -> dict[str, object]:
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
