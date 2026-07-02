from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from bricksmart.exceptions import InventoryConfigurationError
from bricksmart.inventory.models import InventoryMode, InventoryProfile


def _read_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise InventoryConfigurationError(f"Configuration file not found: {path}")
    with path.open(encoding="utf-8") as fh:
        if path.suffix.lower() == ".json":
            payload = json.load(fh)
        elif path.suffix.lower() in {".yaml", ".yml"}:
            payload = yaml.safe_load(fh)
        else:
            raise InventoryConfigurationError(f"Unsupported configuration format: {path.suffix}")
    if not isinstance(payload, dict):
        raise InventoryConfigurationError(f"Configuration must be a mapping: {path}")
    return payload


def _validate_quantities(raw: Any, *, label: str) -> dict[str, int]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise InventoryConfigurationError(f"{label} must be a mapping")
    result: dict[str, int] = {}
    for raw_key, raw_value in raw.items():
        key = str(raw_key).strip()
        if not key:
            raise InventoryConfigurationError(f"{label} contains an empty block type")
        if isinstance(raw_value, bool) or not isinstance(raw_value, int) or raw_value < 0:
            raise InventoryConfigurationError(
                f"{label}.{key} must be a non-negative integer, got {raw_value!r}"
            )
        result[key] = raw_value
    return result


def load_inventory_profile(path: str | Path) -> InventoryProfile:
    path = Path(path)
    payload = _read_mapping(path)
    try:
        mode = InventoryMode(str(payload.get("inventory_mode", "finite")).lower())
    except ValueError as exc:
        raise InventoryConfigurationError(
            f"inventory_mode must be 'finite' or 'unlimited' in {path}"
        ) from exc
    quantities = _validate_quantities(payload.get("blocks", {}), label="blocks")
    if mode is InventoryMode.FINITE and not quantities:
        raise InventoryConfigurationError("A finite inventory profile must declare blocks")
    return InventoryProfile(
        inventory_id=str(payload.get("inventory_id", path.stem)),
        inventory_name=str(payload.get("inventory_name", path.stem)),
        mode=mode,
        quantities=quantities,
        schema_version=str(payload.get("schema_version", "1.0")),
    )


def load_teacher_budget(path: str | Path | None) -> dict[str, int]:
    if path is None:
        return {}
    payload = _read_mapping(Path(path))
    return _validate_quantities(payload.get("blocks", payload), label="teacher_budget.blocks")
