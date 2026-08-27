"""Compatibility package for inventory helpers.

This package preserves older import paths while the main BrickSmart runtime owns
inventory compilation and validation.
"""

from .inventory import (
    InventoryError,
    InventoryExhaustedError,
    InventoryLedger,
    InventoryProfile,
    block_family_counts,
    load_inventory_profile,
    validate_inventory_profile,
)

__all__ = [
    "InventoryError",
    "InventoryExhaustedError",
    "InventoryLedger",
    "InventoryProfile",
    "block_family_counts",
    "load_inventory_profile",
    "validate_inventory_profile",
]
