# BrickSmart architecture

BrickSmart is a model-agnostic, contract-driven planning system. Runtime
behavior is selected from a versioned model contract, the shared XLSX block
catalog, and a run-level inventory profile. An object category such as
`bird`, `airplane`, or `vehicle` must not select a dedicated production-code
branch.

`object_type_hint` may provide descriptive context for frontend or semantic
labeling workflows. It must not select planner algorithms, block families,
output locations, API routes, or visualization implementations.

## Architectural inputs

A build resolves three independent inputs:

1. **Model contract** — model identity, confirmed semantics, preprocessing,
   structural intent, symmetry, interfaces, and reusable functional
   capabilities.
2. **Block catalog** — geometry, rotations, connector faces, priorities,
   colors, and functional metadata loaded directly from
   `block_catalog/block_definitions.xlsx`.
3. **Inventory profile** — the quantities available for this execution.

Inventory configuration contains quantities only. It does not redefine catalog
metadata.

## Deterministic execution boundary

LLM1 and LLM2 may propose semantics or interface intent during contract
authoring. Their reviewed outcomes are stored in an immutable contract revision.
The validated runtime does not call an LLM.

`execution_policy.mode=validated` is the production default and requires
`llm.llm2.enabled=false`. Exploratory runtime enrichment is explicitly
provisional and is never eligible for a validated final claim.

## Runtime flow

```text
Resolve contract URI
        ↓
Resolve immutable model URI and checksum
        ↓
Validate contract, confirmations, catalog, and inventory
        ↓
Load OBJ and apply contract-defined transforms
        ↓
Voxelize and preserve source-segment lineage
        ↓
Apply confirmed segment semantics
        ↓
Detect segment interfaces and declared capabilities
        ↓
Plan structural segment modules
        ↓
Plan functional attachments and reusable assemblies
        ↓
Coordinate inventory globally
        ↓
Sequence module construction and final assembly
        ↓
Validate geometry, contacts, inventory, and connectivity
        ↓
Write isolated run artifacts and build visualizations
```

No stage may infer the output directory from the contract. The run store owns
all output paths.

## Responsibility boundaries

### Runtime code

Runtime code owns reusable mechanics:

- immutable model resolution;
- OBJ ingestion and deterministic voxelization;
- coordinate transforms requested by a contract;
- source-segment lineage preservation and auditing;
- catalog-driven candidate generation and packing;
- allowed-rotation and connector-face validation;
- global inventory reservation and recount;
- generic symmetry planning;
- generic interface handling;
- reusable functional-capability dispatch;
- build sequencing;
- final validation;
- artifact and interactive-player generation.

### Model contract

The contract owns model-specific values:

- model URI and expected checksum;
- preprocessing and voxelization settings;
- confirmation-artifact reference;
- source-segment meanings and display names;
- symmetry declarations;
- interface intent;
- functional targets and assembly instances;
- catalog queries and exact-family requirements;
- teacher-confirmed build intent;
- visualization labels and instruction wording.

A contract provides data. It must not embed executable Python or choose
model-specific runtime modules.

### XLSX catalog

`block_catalog/block_definitions.xlsx` is authoritative for:

- block identifiers and geometry;
- visible and reserved occupancy;
- male and female connector faces;
- allowed rotations;
- packing priorities;
- colors;
- functional roles and other block metadata.

Planner code must not maintain a shadow CSV or hard-coded replacement for these
values.

### Inventory profile

A run-level inventory profile supplies available quantities keyed by workbook
block identifiers. It must not contain geometry, connector definitions,
rotation policy, colors, or planner priorities.

## Capability dispatch

Functional behavior is selected by `assembly_type`, not by object name.
Built-in reusable capability types include:

- `catalog_attachment`
- `replacement_attachment`
- `motion_connector`
- `in_between_connector`
- `motion_connected_structural_subassembly`

A contract may declare multiple instances of the same capability.

A Python change is appropriate only when BrickSmart needs a genuinely new,
reusable physical mechanism that cannot be represented by an existing
capability. Adding a new model instance or object category must not require a
Python change.

## Principal implementation boundaries

The current implementation separates orchestration and storage concerns across
the following modules:

| Module | Responsibility |
|---|---|
| `backend/bricksmart/row_column_runner.py` | Build orchestration |
| `backend/bricksmart/row_column_engine.py` | Catalog-driven structural planning |
| `backend/bricksmart/runtime/contract.py` | Contract validation |
| `backend/bricksmart/runtime/context.py` | Contract and runtime-context loading |
| `backend/bricksmart/model_store/resolver.py` | Model URI resolution |
| `backend/bricksmart/model_store/local.py` | Local immutable model storage |
| `backend/bricksmart/model_registry.py` | Contract revision storage and resolution |
| `backend/bricksmart/run_store.py` | Isolated run allocation and manifests |
| `backend/bricksmart/reporting/true_build_player.py` | Shared build-player generation |

These filenames may be refactored, but their responsibility boundaries should
remain explicit.

## Storage boundaries

```text
model_store/       immutable model geometry
model_registry/    immutable contract revisions and current pointers
runs/              generated execution records
tests/regression/  reviewed expected outputs
pipeline_runtime/  temporary engine workspace only
```

Authoritative data must never be stored only in `pipeline_runtime/`.

## Adding a model

Adding a model requires:

1. importing an OBJ into the model store;
2. producing a task-context JSON;
3. producing and reviewing a segment-confirmation artifact;
4. registering an immutable contract revision;
5. running the generic build entry point;
6. reviewing validation and, when appropriate, adding a regression fixture.

It must not require edits to the runtime, CLI, API, or shared player.

## Adding a reusable capability

A new capability requires:

1. a capability schema and stable `assembly_type`;
2. a generic handler that does not reference object categories;
3. catalog queries rather than hard-coded block families where possible;
4. preflight validation;
5. geometry, inventory, contact, and sequencing tests;
6. at least one representative integration test;
7. documentation in this file and the model-contract schema.

## Prohibited coupling

Production runtime code must not:

- branch on `bird`, `airplane`, or another model category;
- enumerate allowed model profiles;
- select hard-coded block geometry by model name;
- embed inventory quantities;
- read model-specific output paths from a contract;
- require a model-specific player implementation;
- treat regression fixtures as production inputs.

## Architectural conformance

`release/verification/MODEL_AGNOSTIC_AUDIT.json` is a generated release
artifact. It reports conformance for a particular repository state and commit.
It is not a substitute for these architecture rules and must be regenerated
before a release.
