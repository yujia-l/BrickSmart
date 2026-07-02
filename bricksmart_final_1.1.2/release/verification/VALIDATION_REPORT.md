# BrickSmart 1.1.2 validation report

## Final architecture

- Production/default execution mode: `validated`
- Runtime LLM calls in validated mode: prohibited
- LLM role: optional contract-authoring assistance only
- Final planner inputs: immutable contract, model checksum, XLSX catalog, and run inventory
- Exploratory runtime LLM mode: explicitly provisional and not final-claim eligible

## Automated tests

- Collected: 96
- Passed: 96
- Failed: 0

Command:

```bash
PYTHONPATH=backend pytest -q
```

## Live bird build

- Contract: `contract://bird-standard-kit@validated-1`
- Execution mode: validated
- Runtime LLM requested/effective: false / false
- Final claim: PASS
- Final blocks: 26
- True build steps: 14
- Inventory recount:
  - `standard_2x2x2`: 16
  - `standard_2x3x2`: 6
  - `standard_2x4x2`: 4
- Canonical HTML: `artifacts/build_instructions.html`

## Live airplane reference build — unlimited inventory

- Contract: `contract://airplane-reference@validated-1`
- Execution mode: validated
- Runtime LLM requested/effective: false / false
- Interface LLM decisions: 0
- Functional-target LLM decisions: 0
- Deterministic interface decisions: 7
- Deterministic functional-target decisions: 3
- Final claim: PASS
- Final blocks: 78
- True build steps: 41
- Inventory recount:
  - `big_wheel`: 2
  - `rotation_block`: 1
  - `standard_2x2x2`: 57
  - `standard_2x3x2`: 12
  - `standard_2x4x2`: 6
- Canonical HTML: `artifacts/build_instructions.html`


## Repository independence verification

- Production source contains no migration-source section markers.
- Production source contains no interactive-shell imports or dependencies.
- Runtime input resolution uses repository paths, registered contracts, immutable model URIs, and run-level configuration only.
- The engine, tests, contracts, and documentation contain no retired R&D-version identifiers.

## HTML generation provenance

- Generator: `backend/bricksmart/reporting/true_build_player.py`
- Invocation: `backend/bricksmart/row_column_runner.py` after a validated final claim
- Canonical artifact: `artifacts/build_instructions.html`
- Inputs: validated run CSV/JSON artifacts and catalog-derived display metadata
- Output: self-contained HTML

## Worker shutdown validation

The row/column engine and one-shot CLI now terminate directly after all
artifacts and the run summary are safely persisted. This avoids unbounded
interpreter teardown caused by large visualization object graphs in headless
build workers.

## Standard-kit airplane feasibility

- Contract: `contract://airplane-standard-kit@validated-1`
- Inventory: `standard_kit` (finite)
- Observed status: `INFEASIBLE_INVENTORY`
- Validated final claim: false
- First shortage: 18 `standard_2x2x2` required for a mirrored pair; 16 available
- Build-instructions HTML generated: false

## Regression and distribution policy

- Permanent fixtures are compact and remain in the source repository.
- Full diagnostics and HTML are generated under `.test-runs/`.
- Regression fixtures are excluded from production distributions.
- User-facing HTML uses block terminology and visibly identifies unlimited reference inventory.

## Distribution verification

- Wheel excludes `tests/regression/`, `.test-runs/`, `runs/`, and `pipeline_runtime/`.
- Source distribution excludes the same repository-only and generated paths.
- Permanent source-repository regression fixtures total less than 200 KiB and contain no HTML, `.npy` arrays, or raw LLM responses.
- Interactive HTML uses user-facing block terminology and identifies unlimited reference inventory visibly.

## Extracted repository verification

The final ZIP was extracted into a clean directory and tested with:

```bash
PYTHONPATH=backend pytest -q
```

Result: **96 passed, 0 failed**.
