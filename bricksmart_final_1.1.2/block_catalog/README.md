# Original BrickSmart block catalog

Place the existing workbook here without renaming or converting it:

```text
block_catalog/block_definitions.xlsx
```

This repository intentionally does **not** include a generated CSV, JSON, YAML, or replacement XLSX catalog.

At runtime, the workbook is the single source of truth for block IDs, dimensions, rotation policy, connector-face metadata, packing priority, and visualization color. Inventory quantities remain in `backend/bricksmart/config/inventory/standard_kit.yaml` because availability is a run-level constraint, not a block definition.

Validate the workbook after copying it into this directory:

```bash
bricksmart-catalog-inspect \
  --catalog block_catalog/block_definitions.xlsx \
  --inventory backend/bricksmart/config/inventory/standard_kit.yaml \
  --output outputs/catalog_inspection.json
```
