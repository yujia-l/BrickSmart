"""Integration guard package for cross-layer repository checks.

The package contains lightweight checks that keep frontend, contract, catalog,
and runtime boundaries aligned.
"""

from .guard import InventoryGuard

__all__ = ["InventoryGuard"]
