from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class InventoryMode(str, Enum):
    FINITE = "finite"
    UNLIMITED = "unlimited"


@dataclass(frozen=True)
class InventoryProfile:
    inventory_id: str
    inventory_name: str
    mode: InventoryMode
    quantities: dict[str, int] = field(default_factory=dict)
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mode"] = self.mode.value
        return payload


@dataclass(frozen=True)
class EffectiveInventory:
    inventory_id: str
    mode: InventoryMode
    limits: dict[str, int | None]
    limit_sources: dict[str, str]
    physical_limits: dict[str, int]
    teacher_limits: dict[str, int]

    def limit_for(self, block_type: str) -> int | None:
        if self.mode is InventoryMode.UNLIMITED:
            return None
        return self.limits.get(block_type, 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "inventory_id": self.inventory_id,
            "mode": self.mode.value,
            "limits": self.limits,
            "limit_sources": self.limit_sources,
            "physical_limits": self.physical_limits,
            "teacher_limits": self.teacher_limits,
        }


@dataclass(frozen=True)
class InventoryEvent:
    sequence: int
    action: str
    reservation_id: str
    reason: str
    requirements: dict[str, int]
    snapshot: dict[str, dict[str, int | None]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
