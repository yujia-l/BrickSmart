"""Shared exception types for BrickSmart runtime failures.

This module provides domain-specific errors used by catalog loading, model
resolution, contract validation, inventory handling, and planning services.
"""

class BrickSmartError(Exception):
    """Base exception for the constrained planning package."""


class CatalogConfigurationError(BrickSmartError):
    """Raised when block_definitions.csv cannot be used safely."""


class InventoryConfigurationError(BrickSmartError):
    """Raised when an inventory profile or budget is invalid."""


class InventoryUnavailableError(BrickSmartError):
    """Raised when an atomic reservation cannot be satisfied."""


class ReservationNotFoundError(BrickSmartError):
    """Raised when a reservation ID is unknown."""


class PlanningInputError(BrickSmartError):
    """Raised when a planning problem is internally inconsistent."""
