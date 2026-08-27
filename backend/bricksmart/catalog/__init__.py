"""Catalog loading and validation package.

The package exposes the authoritative CSV block catalog interface used by
planning, inventory, validation, and reporting code.
"""

from bricksmart.catalog.loader import (
    load_block_catalog,
    load_catalog_block_ids,
    validate_inventory_against_catalog,
    validate_used_block_colors,
)
from bricksmart.catalog.models import (
    BlockCatalog,
    CatalogBlockDefinition,
    CatalogBuildPolicy,
    CatalogGeometrySpec,
    CatalogMotionSpec,
    WorkbookCatalog,
)
from bricksmart.catalog.schema import (
    CATALOG_COLUMNS,
    CATALOG_SCHEMA_VERSION,
    CORE_RUNTIME_COLUMNS,
)
from bricksmart.catalog.structural import (
    StructuralBlockDefinition,
    load_structural_block_definitions,
)

__all__ = [
    "BlockCatalog",
    "CatalogBlockDefinition",
    "CatalogBuildPolicy",
    "CatalogGeometrySpec",
    "CatalogMotionSpec",
    "WorkbookCatalog",
    "CATALOG_COLUMNS",
    "CATALOG_SCHEMA_VERSION",
    "CORE_RUNTIME_COLUMNS",
    "load_block_catalog",
    "load_catalog_block_ids",
    "validate_inventory_against_catalog",
    "validate_used_block_colors",
    "StructuralBlockDefinition",
    "load_structural_block_definitions",
]
