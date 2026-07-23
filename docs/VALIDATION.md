# Validation and regression policy

BrickSmart makes a final build claim only after the relevant contract,
geometry, catalog, inventory, connection, and assembly checks pass.

This document describes durable validation policy. Point-in-time test counts,
package versions, commit hashes, and baseline results belong under
`release/verification/` and must be regenerated for each release.

## Validation layers

### 1. Contract preflight

Before voxelization, validate:

- supported contract schema;
- resolvable contract revision;
- resolvable model URI;
- optional expected model checksum;
- authoritative confirmation artifact;
- XLSX catalog availability;
- inventory keys against catalog block identifiers;
- registered functional capability types;
- required anchors, members, and cross-references;
- absence of contract-owned output paths.

### Deterministic execution gate

Validated mode must confirm that runtime LLM use is disabled. A build that uses
exploratory LLM enrichment is marked provisional even when its geometric planner
gates pass.

### 2. Geometry and source lineage

Validate:

- deterministic OBJ ingestion and voxelization;
- coordinate transforms;
- source-segment identity preservation;
- disconnected-component handling;
- structuralized-grid lineage;
- candidate occupancy;
- collision and reserved-occupancy constraints.

### 3. Catalog conformance

Validate that:

- every selected block exists in `block_definitions.xlsx`;
- dimensions and occupancy come from the workbook;
- selected rotations are allowed;
- connector faces match the rotated catalog definition;
- planner priority and functional metadata are catalog-driven;
- no shadow CSV or hard-coded block definition is used.

### 4. Structural planning

Validate:

- source coverage;
- segment-local packing;
- row and column progression;
- block placement uniqueness;
- required locking contacts;
- temporary-root behavior;
- segment-module connectivity;
- symmetry requirements;
- direct structural joins and declared interfaces.

### 5. Functional assemblies

For each declared capability, validate:

- capability type registration;
- anchor and member resolution;
- catalog family requirements;
- collision and clearance;
- contact orientation;
- reserved-face or interface constraints;
- inventory reservation;
- attachment sequencing;
- final connectivity.

### 6. Inventory

Validate:

- initial available quantities;
- reservation accounting;
- committed placements;
- replacements and functional allocations;
- final recount;
- absence of negative inventory;
- declared unlimited-inventory mode when intentionally used.

### 7. Build sequencing

Validate:

- every part appears in the instruction sequence;
- steps reference existing blocks and modules;
- each step's prerequisites are complete;
- staged modules are distinguished from final-position modules;
- module joins use validated interfaces;
- the final state matches the validated final parts.

### 8. Final claim gate

The final claim may be `PASS` only when all contract-required gates pass.
Diagnostic files may still be written after a failure, but generated geometry or
visualizations must not be presented as a validated final build.

## Test locations

```text
backend/tests/      unit and integration tests
tests/regression/   reviewed immutable expected outputs
.test-runs/         generated live end-to-end runs
runs/               generated production or local executions
```

Regression fixtures are not production runs.

## Commands

Run the Python test suite:

```bash
pytest -q
```

Run backend unit and integration tests:

```bash
pytest -q backend/tests
```

Run reviewed baseline comparisons:

```bash
make regression
```

Run live end-to-end builds into `.test-runs/`:

```bash
make regression-bird
make regression-airplane-reference
make regression-airplane-standard-kit
```

## Regression baselines

The reviewed reference fixtures are stored under:

```text
tests/regression/bird/
tests/regression/airplane_reference_unlimited/
tests/regression/airplane_standard_kit/
```

A compact baseline may include only the structured files necessary to verify:

- input contract and confirmation snapshot;
- expected final parts;
- expected block-family counts;
- segment assignments;
- rotations and placements;
- build-step order;
- module and interface summaries;
- inventory results;
- validation summaries;
Generated HTML, large arrays, raw LLM traces, and detailed planner diagnostics do not belong in permanent regression fixtures. Tests verify generation, while live output remains in `.test-runs/`.

## Current reviewed reference baselines

The fixture contents and their manifests are authoritative. The following
values document the reviewed expectations supplied with the current reference
fixtures.

### Bird

| Expectation | Reviewed value |
|---|---:|
| Structural modules | 3 |
| Structural blocks | 26 |
| `standard_2x2x2` | 16 |
| `standard_2x3x2` | 6 |
| `standard_2x4x2` | 4 |
| Direct structural locks | 2 |
| True build steps | 14 |
| Symmetry and inventory recount | Complete |

### Airplane reference — unlimited inventory

| Expectation | Reviewed value |
|---|---:|
| Structural modules | 8 |
| Total blocks | 78 |
| Direct structural joins | 7 |
| `big_wheel` | 2 |
| `rotation_block` | 1 |
| True build steps | 41 |
| Symmetry and inventory recount | Complete |

The airplane reference uses explicitly recorded unlimited inventory for the
full reviewed scale because the standard kit cannot satisfy the complete
structural demand. The separate `airplane_standard_kit` fixture expects `INFEASIBLE_INVENTORY`, no validated final claim, and no build-instructions HTML.

Regression tests compare normalized summaries, block-family counts, placement
and rotation data where configured, source-segment assignments, inventory
results, build order, final claims, and required artifacts. Live checks write to
`.test-runs/` and must not add generated data to production `runs/`.

## Updating a baseline

Do not replace a baseline solely to make a failing test pass.

For an intentional planner change:

1. run the affected unit and integration tests;
2. generate a new live run under `.test-runs/`;
3. compare structured CSV and JSON outputs;
4. inspect inventory, connectivity, contacts, symmetry, and build order;
5. review the interactive player when relevant;
6. document why the output changed;
7. replace the baseline only after explicit review;
8. regenerate release verification.

## Required storage checks

Release validation must confirm:

- packaged OBJ files exist only in approved model-store locations;
- model-specific contracts and confirmations are versioned or captured as
  regression inputs;
- contracts cannot control output locations;
- runtime executions write only under the configured run root;
- compact source-repository regression fixtures live under `tests/regression/`;
- regression fixtures are excluded from production wheel and source distributions;
- the packaged `runs/` directory contains no execution results;
- temporary `pipeline_runtime/` contents are not treated as authoritative.

## Packaging checks

A release check should verify:

- Python sources compile;
- tests pass from the extracted release archive;
- the package version matches release metadata;
- only approved runtime, contract, documentation, and test assets are included;
- no retired R&D-version identifiers remain in active source, configuration,
  documentation, contract IDs, model IDs, or artifact names;
- generated verification files identify the commit and generation time.

## Release evidence

Generated evidence belongs under:

```text
release/verification/
├── MODEL_AGNOSTIC_AUDIT.json
├── PROVENANCE.json
└── VALIDATION_REPORT.md
```

These files describe one repository state. They must not be hand-maintained as
timeless documentation.

## Failure triage

Start with:

```text
runs/<run-id>/run.json
runs/<run-id>/logs/
runs/<run-id>/artifacts/
```

Review the earliest failing gate before interpreting downstream artifacts.
Inventory, collision, connector-contact, connectivity, symmetry, and final-claim
summaries should be treated as linked evidence rather than independent success
claims.
