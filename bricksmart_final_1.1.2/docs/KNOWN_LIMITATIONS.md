# Known limitations

This document lists current limitations of the validated BrickSmart runtime.
Resolved defects and migration-only problems do not belong here.

## Validated structural join mode

**Affected area:** Structural assembly

The row/column structural engine currently validates
`direct_structural_lock` as its production structural join mode.

A new join mode requires a reusable, model-agnostic join-capability handler,
contract schema, validation rules, and tests. It must not be added as a branch
for one object category.

## Functional capability coverage

**Affected area:** Functional assemblies

Built-in capability types cover:

- catalog attachments;
- replacement attachments;
- motion connectors;
- in-between connectors;
- motion-connected structural subassemblies.

A genuinely new physical mechanism requires one reusable capability handler.
Adding a new model name does not.

## Supported structural lattice

**Affected area:** Structural planning

The ported structuralization and row/column packing algorithms are optimized for
the catalog's 2×2 structural lattice.

Contracts may configure preprocessing, transforms, and packing behavior, but
arbitrary non-lattice construction systems are outside the validated engine.

## Required semantic confirmation

**Affected area:** Model contracts

A production contract must provide authoritative segment confirmations unless
the contract explicitly enables the supported object-name confirmation path.

The runtime does not invent model-specific segment meanings when confirmed
semantics are required.

## Workbook formula values

**Affected area:** Block catalog loading

Workbook formulas must have cached values available because the loader reads
stored workbook cell values rather than recalculating formulas.

Before committing workbook changes, open and save the workbook in a compatible
spreadsheet application so formula caches are current.

## OBJ-only geometry ingestion

**Affected area:** Model loading

The current validated ingestion path accepts OBJ geometry. Other geometry
formats require a reusable ingestion adapter, security validation, checksum
handling, and regression coverage.

## Reference-airplane inventory feasibility

**Affected area:** Reference regression model

The complete reviewed airplane exceeds the supplied standard-kit structural
inventory. The reference fixture and HTML therefore use explicitly recorded unlimited
inventory and are labeled as an unlimited reference build.

This is an inventory-feasibility result for that contract and kit, not a
model-specific runtime branch. Finite-kit builds must report the shortage rather
than silently exceed inventory.

## Experimental fallback planner

**Affected area:** Alternative planning

The older greedy cuboid OBJ planner is experimental. It is not equivalent to the
validated row/column planner and must not be used as an automatic success
fallback for production claims.
