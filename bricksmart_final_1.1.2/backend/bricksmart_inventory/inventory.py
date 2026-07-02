from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
import json
import uuid

import yaml


class InventoryError(RuntimeError):
    """Base inventory exception."""


class InventoryExhaustedError(InventoryError):
    """Raised when an atomic reservation cannot be satisfied."""


@dataclass(frozen=True)
class InventoryProfile:
    inventory_id: str
    mode: str
    blocks: dict[str, int]
    source_path: str

    @property
    def finite(self) -> bool:
        return self.mode == "finite"


def _normalized_count(value: Any, family: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Inventory count for {family!r} must be an integer, not bool.")
    try:
        count = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Inventory count for {family!r} must be an integer.") from exc
    if count < 0:
        raise ValueError(f"Inventory count for {family!r} cannot be negative.")
    if isinstance(value, float) and value != count:
        raise ValueError(f"Inventory count for {family!r} must be a whole number.")
    return count


def load_inventory_profile(path: str | Path) -> InventoryProfile:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Inventory profile does not exist: {source}")
    payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    mode = str(payload.get("inventory_mode", "finite")).strip().lower()
    if mode not in {"finite", "unlimited"}:
        raise ValueError(f"Unsupported inventory_mode={mode!r} in {source}")
    raw_blocks = payload.get("blocks", {}) or {}
    if not isinstance(raw_blocks, Mapping):
        raise ValueError("Inventory profile blocks must be a mapping.")
    blocks = {
        str(family).strip(): _normalized_count(value, str(family).strip())
        for family, value in raw_blocks.items()
        if str(family).strip()
    }
    return InventoryProfile(
        inventory_id=str(payload.get("inventory_id", source.stem)),
        mode=mode,
        blocks=blocks,
        source_path=str(source),
    )


def validate_inventory_profile(
    profile: InventoryProfile,
    catalog_families: Iterable[str],
) -> dict[str, Any]:
    catalog = {str(value).strip() for value in catalog_families if str(value).strip()}
    unknown_inventory_families = sorted(set(profile.blocks) - catalog)
    if unknown_inventory_families:
        raise KeyError(
            "Inventory profile contains block families absent from block_definitions.xlsx: "
            f"{unknown_inventory_families}"
        )
    return {
        "valid": True,
        "inventory_id": profile.inventory_id,
        "inventory_mode": profile.mode,
        "catalog_family_count": len(catalog),
        "inventory_family_count": len(profile.blocks),
        "unknown_inventory_families": [],
        "catalog_families_without_finite_stock": (
            sorted(catalog - set(profile.blocks)) if profile.finite else []
        ),
    }


def block_family_counts(blocks: Iterable[Any], multiplier: int = 1) -> dict[str, int]:
    multiplier = int(multiplier)
    if multiplier < 1:
        raise ValueError("Inventory multiplier must be at least 1.")
    counts: Counter[str] = Counter()
    for block in blocks:
        if isinstance(block, Mapping):
            family = block.get("block_family")
        else:
            family = getattr(block, "block_family", None)
        if family in {None, ""}:
            raise InventoryError(f"A planned block has no catalog block_family: {block!r}")
        counts[str(family)] += multiplier
    return dict(sorted(counts.items()))


class InventoryLedger:
    """Atomic run-level inventory ledger.

    A finite profile treats catalog families omitted from the profile as zero stock.
    Unlimited mode records usage but never rejects a reservation.
    """

    def __init__(self, profile: InventoryProfile):
        self.profile = profile
        self._reserved: dict[str, dict[str, int]] = {}
        self._reservation_scope: dict[str, str] = {}
        self._committed: Counter[str] = Counter()
        self._events: list[dict[str, Any]] = []
        self._event_index = 0

    @property
    def committed(self) -> dict[str, int]:
        return dict(sorted(self._committed.items()))

    @property
    def reserved_totals(self) -> dict[str, int]:
        totals: Counter[str] = Counter()
        for requirements in self._reserved.values():
            totals.update(requirements)
        return dict(sorted(totals.items()))

    def capacity(self, family: str) -> int | None:
        if not self.profile.finite:
            return None
        return int(self.profile.blocks.get(str(family), 0))

    def available(self, family: str) -> int | None:
        capacity = self.capacity(family)
        if capacity is None:
            return None
        reserved = int(self.reserved_totals.get(str(family), 0))
        committed = int(self._committed.get(str(family), 0))
        return capacity - reserved - committed

    def check(self, requirements: Mapping[str, int]) -> dict[str, Any]:
        normalized = {
            str(family): _normalized_count(count, str(family))
            for family, count in requirements.items()
            if int(count) != 0
        }
        shortages: dict[str, dict[str, int]] = {}
        for family, required in normalized.items():
            available = self.available(family)
            if available is not None and required > available:
                shortages[family] = {
                    "required": required,
                    "available": available,
                    "shortage": required - available,
                    "capacity": int(self.capacity(family) or 0),
                    "committed": int(self._committed.get(family, 0)),
                    "reserved": int(self.reserved_totals.get(family, 0)),
                }
        return {
            "feasible": not shortages,
            "requirements": normalized,
            "shortages": shortages,
        }

    def reserve(self, requirements: Mapping[str, int], scope: str) -> str:
        check = self.check(requirements)
        if not check["feasible"]:
            self._record_event("reserve_rejected", scope, check["requirements"], check["shortages"])
            raise InventoryExhaustedError(
                f"Inventory reservation failed for {scope}: "
                + json.dumps(check["shortages"], sort_keys=True)
            )
        reservation_id = f"inv-{uuid.uuid4().hex[:12]}"
        self._reserved[reservation_id] = dict(check["requirements"])
        self._reservation_scope[reservation_id] = str(scope)
        self._record_event("reserved", scope, check["requirements"], {})
        return reservation_id

    def commit(self, reservation_id: str) -> dict[str, int]:
        if reservation_id not in self._reserved:
            raise KeyError(f"Unknown inventory reservation: {reservation_id}")
        requirements = self._reserved.pop(reservation_id)
        scope = self._reservation_scope.pop(reservation_id)
        self._committed.update(requirements)
        self._record_event("committed", scope, requirements, {})
        return dict(requirements)

    def reserve_and_commit(self, requirements: Mapping[str, int], scope: str) -> str:
        reservation_id = self.reserve(requirements, scope)
        self.commit(reservation_id)
        return reservation_id

    def release(self, reservation_id: str) -> dict[str, int]:
        if reservation_id not in self._reserved:
            raise KeyError(f"Unknown inventory reservation: {reservation_id}")
        requirements = self._reserved.pop(reservation_id)
        scope = self._reservation_scope.pop(reservation_id)
        self._record_event("released", scope, requirements, {})
        return dict(requirements)

    def final_recount(self, blocks: Iterable[Any]) -> dict[str, Any]:
        recount = block_family_counts(blocks)
        all_families = sorted(
            set(self.profile.blocks)
            | set(self._committed)
            | set(recount)
        )
        usage_rows = []
        overages = {}
        ledger_mismatches = {}
        for family in all_families:
            capacity = self.capacity(family)
            used = int(recount.get(family, 0))
            committed = int(self._committed.get(family, 0))
            if capacity is not None and used > capacity:
                overages[family] = {
                    "used": used,
                    "capacity": capacity,
                    "overage": used - capacity,
                }
            if used != committed:
                ledger_mismatches[family] = {
                    "recount": used,
                    "ledger_committed": committed,
                }
            usage_rows.append({
                "block_family": family,
                "capacity": capacity,
                "used": used,
                "ledger_committed": committed,
                "remaining": None if capacity is None else capacity - used,
                "status": "OVER" if family in overages else "PASS",
            })
        return {
            "valid": not overages and not ledger_mismatches and not self._reserved,
            "inventory_id": self.profile.inventory_id,
            "inventory_mode": self.profile.mode,
            "usage_rows": usage_rows,
            "overages": overages,
            "ledger_mismatches": ledger_mismatches,
            "open_reservations": dict(self._reserved),
            "recount": recount,
            "ledger_committed": self.committed,
        }

    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def _record_event(
        self,
        event_type: str,
        scope: str,
        requirements: Mapping[str, int],
        shortages: Mapping[str, Any],
    ) -> None:
        self._event_index += 1
        self._events.append({
            "event_index": self._event_index,
            "event_type": event_type,
            "scope": str(scope),
            "requirements": dict(requirements),
            "shortages": dict(shortages),
            "committed_after": self.committed,
            "reserved_after": self.reserved_totals,
        })
