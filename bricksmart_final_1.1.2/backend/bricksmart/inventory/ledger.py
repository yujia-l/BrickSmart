from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from bricksmart.exceptions import InventoryUnavailableError, ReservationNotFoundError
from bricksmart.inventory.models import EffectiveInventory, InventoryEvent, InventoryMode


@dataclass
class _Reservation:
    reservation_id: str
    requirements: dict[str, int]
    reason: str


class InventoryLedger:
    """Transactional inventory ledger shared by all planning passes."""

    def __init__(self, inventory: EffectiveInventory):
        self.inventory = inventory
        self._committed: dict[str, int] = {}
        self._reserved: dict[str, int] = {}
        self._reservations: dict[str, _Reservation] = {}
        self._events: list[InventoryEvent] = []

    @staticmethod
    def _normalize(requirements: dict[str, int]) -> dict[str, int]:
        normalized: dict[str, int] = {}
        for block_type, count in requirements.items():
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError(f"Requirement for {block_type} must be a non-negative integer")
            if count:
                normalized[str(block_type)] = normalized.get(str(block_type), 0) + count
        return normalized

    def capacity(self, block_type: str) -> int | None:
        return self.inventory.limit_for(block_type)

    def committed(self, block_type: str) -> int:
        return self._committed.get(block_type, 0)

    def reserved(self, block_type: str) -> int:
        return self._reserved.get(block_type, 0)

    def remaining(self, block_type: str) -> int | None:
        capacity = self.capacity(block_type)
        if capacity is None:
            return None
        return capacity - self.committed(block_type) - self.reserved(block_type)

    def can_reserve(self, requirements: dict[str, int]) -> bool:
        normalized = self._normalize(requirements)
        if self.inventory.mode is InventoryMode.UNLIMITED:
            return True
        return all(
            (self.remaining(block_type) or 0) >= count
            for block_type, count in normalized.items()
        )

    def shortages(self, requirements: dict[str, int]) -> dict[str, dict[str, int]]:
        normalized = self._normalize(requirements)
        shortages: dict[str, dict[str, int]] = {}
        if self.inventory.mode is InventoryMode.UNLIMITED:
            return shortages
        for block_type, required in normalized.items():
            available = self.remaining(block_type) or 0
            if required > available:
                shortages[block_type] = {
                    "required": required,
                    "available": available,
                    "shortfall": required - available,
                }
        return shortages

    def reserve(self, requirements: dict[str, int], *, reason: str) -> str:
        normalized = self._normalize(requirements)
        shortages = self.shortages(normalized)
        if shortages:
            details = ", ".join(
                f"{block}: need {data['required']}, available {data['available']}"
                for block, data in shortages.items()
            )
            raise InventoryUnavailableError(f"Atomic reservation failed ({reason}): {details}")

        reservation_id = uuid4().hex
        self._reservations[reservation_id] = _Reservation(
            reservation_id=reservation_id,
            requirements=normalized,
            reason=reason,
        )
        for block_type, count in normalized.items():
            self._reserved[block_type] = self.reserved(block_type) + count
        self._record("reserve", reservation_id, reason, normalized)
        return reservation_id

    def commit(self, reservation_id: str) -> None:
        reservation = self._reservations.pop(reservation_id, None)
        if reservation is None:
            raise ReservationNotFoundError(f"Unknown reservation: {reservation_id}")
        for block_type, count in reservation.requirements.items():
            self._reserved[block_type] = self.reserved(block_type) - count
            self._committed[block_type] = self.committed(block_type) + count
        self._record(
            "commit", reservation_id, reservation.reason, reservation.requirements
        )

    def release(self, reservation_id: str) -> None:
        reservation = self._reservations.pop(reservation_id, None)
        if reservation is None:
            raise ReservationNotFoundError(f"Unknown reservation: {reservation_id}")
        for block_type, count in reservation.requirements.items():
            self._reserved[block_type] = self.reserved(block_type) - count
        self._record(
            "release", reservation_id, reservation.reason, reservation.requirements
        )

    def snapshot(self) -> dict[str, dict[str, int | None]]:
        block_types = set(self.inventory.limits) | set(self._committed) | set(self._reserved)
        return {
            block_type: {
                "capacity": self.capacity(block_type),
                "committed": self.committed(block_type),
                "reserved": self.reserved(block_type),
                "remaining": self.remaining(block_type),
            }
            for block_type in sorted(block_types)
        }

    def usage_summary(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for block_type, values in self.snapshot().items():
            capacity = values["capacity"]
            committed = int(values["committed"] or 0)
            utilization = None if capacity is None or capacity == 0 else committed / capacity
            rows.append(
                {
                    "block_type": block_type,
                    **values,
                    "utilization_fraction": utilization,
                    "limit_source": self.inventory.limit_sources.get(
                        block_type,
                        "unlimited" if capacity is None else "implicit_zero",
                    ),
                    "status": (
                        "PASS"
                        if capacity is None or committed <= capacity
                        else "FAIL_INVENTORY_EXCEEDED"
                    ),
                }
            )
        return rows

    @property
    def committed_counts(self) -> dict[str, int]:
        return {key: value for key, value in self._committed.items() if value}

    @property
    def events(self) -> list[InventoryEvent]:
        return list(self._events)

    def _record(
        self,
        action: str,
        reservation_id: str,
        reason: str,
        requirements: dict[str, int],
    ) -> None:
        self._events.append(
            InventoryEvent(
                sequence=len(self._events) + 1,
                action=action,
                reservation_id=reservation_id,
                reason=reason,
                requirements=dict(requirements),
                snapshot=self.snapshot(),
            )
        )
