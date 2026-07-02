class BrickSmartError(Exception):
    """Base exception for the constrained planning package."""


class CatalogConfigurationError(BrickSmartError):
    """Raised when the original block_definitions.xlsx cannot be used safely."""


class InventoryConfigurationError(BrickSmartError):
    """Raised when an inventory profile or budget is invalid."""


class InventoryUnavailableError(BrickSmartError):
    """Raised when an atomic reservation cannot be satisfied."""


class ReservationNotFoundError(BrickSmartError):
    """Raised when a reservation ID is unknown."""


class PlanningInputError(BrickSmartError):
    """Raised when a planning problem is internally inconsistent."""
