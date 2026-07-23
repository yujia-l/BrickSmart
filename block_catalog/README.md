# BrickSmart block catalog

The authoritative catalog is:

```text
block_catalog/block_definitions.csv
```

It is a UTF-8, single-table, model-agnostic catalog using the versioned
`bricksmart-block-catalog-2` schema. It preserves physical geometry and generic
model-building rules while excluding notebook history and object-specific
policy.

## Catalog scope

The catalog records:

- identity, category, display color, and planner eligibility;
- physical, anchor, visible, layered, and reserved-clearance geometry;
- geometry representation and verification status;
- local male/female connector faces and permitted orientations;
- stackability, support quality, stability, and structural packing priority;
- structural fill, interface insertion, attachment, and replacement behavior;
- source-geometry preservation, placement-origin, and prohibited-use rules;
- functional motion, wheel axes, attachment side, clearance, and ground contact.

The catalog must not contain notebook-version references, object-specific roles,
model symmetry/pairing declarations, integration history, or run-level inventory
quantities.

## Production contract

The production file has 63 ordered columns. The shared loader validates the
complete schema and maps its data into typed:

- `CatalogGeometrySpec`;
- `CatalogBuildPolicy`;
- `CatalogMotionSpec`.

The first 36 columns preserve the previous CSV runtime vocabulary. The remaining
columns restore generic model-building information from the original working
catalog that had been removed too aggressively.

## Editing rules

- Keep face values as comma-separated canonical local tokens such as `+Z,-Z`.
- Keep orientation values as `X`, `Y`, or `Z` tokens.
- Use lowercase `true` and `false` for boolean fields.
- Do not supply invented geometry for unresolved parts.
- Do not add object-specific examples to catalog cells.
- Update the schema, tests, and documentation together when adding a field.

Validate after editing:

```bash
bricksmart-catalog-inspect \
  --catalog block_catalog/block_definitions.csv \
  --inventory config/inventory/standard_kit.yaml \
  --output outputs/catalog_inspection.json
```
