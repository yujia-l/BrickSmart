# Model contract schema

The task context is BrickSmart's model and build-behavior contract. Every model
uses the same schema while providing model-specific values.

Start from:

```text
examples/contracts/model_contract_template.json
```

The runtime validator in `backend/bricksmart/runtime/contract.py` and the
committed contract template are authoritative. This document explains the
stable public concepts and constraints.

## Schema version

Current schema identifier:

```text
bricksmart-model-contract-1.0
```

A runtime must reject unsupported major schema versions rather than silently
reinterpret them.

## Top-level structure

| Field | Purpose |
|---|---|
| `schema_version` | Contract schema identifier |
| `model_id` | Stable logical model identifier |
| `task_id` | Build-intent identifier |
| `display_name` | User-facing name |
| `object_type_hint` | Descriptive metadata only |
| `model_source` | Immutable model reference and optional checksum |
| `paths` | Non-output resource paths |
| `segment_semantics` | Authoritative confirmation reference |
| `segment_assembly` | Generic structural-planning configuration |
| `functional_attachments` | Catalog-selected physical targets |
| `functional_assemblies` | Reusable capability instances |

The runtime validator determines which fields are required for a particular
capability. Unknown fields must not be relied upon unless the current schema and
validator explicitly support them.

## Execution policy

```json
{
  "execution_policy": {
    "mode": "validated",
    "allow_runtime_llm": false,
    "final_claim_requires_deterministic_inputs": true
  }
}
```

- `validated` is the default and forbids runtime LLM calls.
- `exploratory` may allow runtime LLM enrichment only when
  `allow_runtime_llm` is true.
- Exploratory runs are provisional and cannot produce a validated final claim.
- LLM model names and prompts used during authoring belong in provenance, not
  deployment endpoint fields inside a validated runtime contract.

## Identity

```json
{
  "schema_version": "bricksmart-model-contract-1.0",
  "model_id": "classroom-model",
  "task_id": "standard-kit-build",
  "display_name": "Classroom model",
  "object_type_hint": "descriptive-only"
}
```

Rules:

- `model_id` identifies the model logically and must remain stable.
- `task_id` distinguishes build intent or configuration.
- `display_name` is presentation metadata.
- `object_type_hint` may support semantic labeling but must not select Python
  branches, planner implementations, or block definitions.

## Model source

```json
{
  "model_source": {
    "uri": "model://registered-model-id",
    "expected_sha256": "optional-lowercase-sha256",
    "filename": "model.obj"
  }
}
```

Supported source classes include:

- `model://` for registered immutable models;
- `sha256://` for direct content-addressed resolution;
- trusted local or file references for development;
- opt-in HTTPS;
- opt-in S3.

Production contracts should prefer `model://` plus `expected_sha256`.

The build must fail before voxelization when the resolved model does not match
`expected_sha256`.

## Resource paths

`paths` contains non-output resources only. Supported concepts include:

- `paths.catalog_xlsx`
- `paths.catalog_sheet`
- `paths.relative_to`

The catalog path must resolve to the authoritative XLSX workbook.

The following is prohibited:

```json
{
  "paths": {
    "output_dir": "some/model-specific/path"
  }
}
```

The registry removes historical `paths.output_dir` values and the runner ignores
them. The run store owns output allocation.

## Segment semantics

`segment_semantics.labels_file` references the authoritative frontend and
teacher-confirmation artifact.

```json
{
  "segment_semantics": {
    "labels_file": "segment_confirmations.csv"
  }
}
```

When confirmations are required, runtime code must not invent model-specific
meanings or silently substitute unconfirmed labels.

The confirmation artifact may be CSV or JSON when supported by the validator.
Its required columns or fields are defined by the committed example artifact
and runtime validation code.

Files named like
`simulated_teacher_segment_confirmations_*.csv` are development stand-ins only.
A registered production revision must reference the actual artifact produced or
updated by the frontend confirmation workflow.

## Structural planning

`segment_assembly.segment_packing` configures generic packing behavior, such as:

- candidate axes;
- row and column progression;
- temporary module roots;
- source-segment preservation;
- symmetry requirements;
- final connectivity requirements.

These values tune reusable algorithms. They must not identify a model-specific
Python function.

## Functional attachments

`functional_attachments` declares catalog-selected physical targets, anchors,
interfaces, and exact-family requirements when applicable.

Block families must resolve through `block_definitions.xlsx`. Geometry and
connector metadata must not be repeated in the contract.

## Functional assemblies

`functional_assemblies` declares reusable capability instances. Dispatch is
selected by `assembly_type`.

Supported built-in capability types include:

- `catalog_attachment`
- `replacement_attachment`
- `motion_connector`
- `in_between_connector`
- `motion_connected_structural_subassembly`

A contract may declare multiple instances of one capability.

Each instance must provide the anchors, members, interface references, and
capability-specific values required by the runtime validator. A new object
category does not justify a new `assembly_type`; a genuinely new reusable
physical mechanism may.

## Inventory

Inventory is not embedded in block definitions or the model contract. It is
supplied separately through the CLI or API:

```bash
bricksmart-build \
  --contract contract://classroom-model-standard-kit \
  --inventory config/inventory/standard_kit.yaml
```

Inventory keys must resolve to block identifiers in the XLSX catalog.

## Minimal contract example

```json
{
  "schema_version": "bricksmart-model-contract-1.0",
  "model_id": "classroom-model",
  "task_id": "standard-kit-build",
  "display_name": "Classroom model",
  "object_type_hint": "descriptive-only",
  "model_source": {
    "uri": "model://classroom-model",
    "expected_sha256": "replace-with-model-sha256",
    "filename": "model.obj"
  },
  "paths": {
    "catalog_xlsx": "block_catalog/block_definitions.xlsx"
  },
  "segment_semantics": {
    "labels_file": "segment_confirmations.csv"
  },
  "segment_assembly": {
    "segment_packing": {}
  },
  "functional_attachments": [],
  "functional_assemblies": []
}
```

The empty `segment_packing` object is illustrative. Use the committed template
for the current supported defaults and fields.

## Preflight validation

Before voxelization, the runtime validates:

- schema version;
- model URI resolution;
- optional model checksum;
- authoritative confirmation records;
- XLSX catalog availability;
- catalog sheet and block identifiers;
- registered functional capability types;
- required anchors and member metadata;
- inventory-to-catalog consistency;
- prohibited output-path ownership;
- required cross-field references.

A preflight failure must stop the build before generated planning artifacts are
treated as valid.

## Registry storage

Active task contexts and confirmation artifacts belong in immutable
`model_registry/` revisions. A build resolves them through a `contract://` URI
and snapshots the resolved inputs under the run directory.

## Schema evolution

Schema changes follow these rules:

1. backward-compatible optional additions may retain the current major version;
2. changed meanings or removed fields require a new major schema version;
3. migrations must be explicit and tested;
4. registry revisions remain immutable and retain their original schema;
5. runs record the exact schema and contract revision they consumed.
