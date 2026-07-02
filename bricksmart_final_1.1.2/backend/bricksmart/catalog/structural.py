from __future__ import annotations

from pathlib import Path

from bricksmart.catalog.loader import load_block_catalog
from bricksmart.catalog.models import CatalogBlockDefinition
from bricksmart.exceptions import CatalogConfigurationError

StructuralBlockDefinition = CatalogBlockDefinition


def load_structural_block_definitions(
    path: str | Path,
) -> tuple[StructuralBlockDefinition, ...]:
    catalog = load_block_catalog(path)
    definitions = catalog.structural_definitions
    if not definitions:
        raise CatalogConfigurationError(
            "block_definitions.xlsx contains no structural-eligible block definitions"
        )
    return definitions
