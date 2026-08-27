"""Structural catalog adapters for planner-facing block metadata.

This module converts validated CSV catalog rows into structural placement,
rotation, connector, and support information used by the planner.
"""

from __future__ import annotations

from pathlib import Path

from bricksmart.catalog.loader import load_block_catalog
from bricksmart.catalog.models import CatalogBlockDefinition
from bricksmart.exceptions import CatalogConfigurationError

StructuralBlockDefinition = CatalogBlockDefinition


def load_structural_block_definitions(
    path: str | Path,
) -> tuple[StructuralBlockDefinition, ...]:
    """Load structural block definitions.
    
    :param path: Filesystem path used by the operation.
    :type path: str | Path
    :returns: The loaded data.
    :rtype: tuple[StructuralBlockDefinition, ...]
    """
    catalog = load_block_catalog(path)
    definitions = catalog.structural_definitions
    if not definitions:
        raise CatalogConfigurationError(
            "block_definitions.csv contains no structural-eligible block definitions"
        )
    return definitions
