# Model registry

`model_store` and `model_registry` solve different problems:

- `model_store` stores immutable mesh bytes and returns `model://` URIs.
- `model_registry` stores reviewed build contracts and returns `contract://`
  URIs.

Separating geometry from interpretation allows multiple reviewed contracts to
reference the same immutable OBJ without duplicating model bytes.

## Registry layout

```text
model_registry/
└── contracts/
    └── <contract-id>/
        ├── current.json
        └── versions/
            └── <revision-id>/
                ├── task_context.json
                ├── segment_confirmations.csv or .json
                └── manifest.json
```

A revision directory is immutable after registration.

## Contract URIs

A versioned URI resolves one exact revision:

```text
contract://classroom-model-standard-kit@teacher-review-2
```

An unversioned URI resolves through `current.json`:

```text
contract://classroom-model-standard-kit
```

Use a versioned URI for tests, reproducible builds, audits, and release
evidence. Use an unversioned URI only when the caller intentionally wants the
revision currently selected for new builds.

Callers must not assume that revision IDs are sequential or human-readable.
The registry manifest is authoritative.

## Revision contents

### `task_context.json`

The model and build-behavior contract. It references immutable model geometry,
confirmed semantics, preprocessing settings, structural intent, symmetry,
interfaces, and reusable functional capabilities.

### `segment_confirmations.csv` or `.json`

The authoritative teacher-reviewed segment meanings. The registry snapshots the
artifact so later frontend changes cannot alter an earlier revision.

### `manifest.json`

Revision metadata, including contract identity, revision identity, checksums,
source references, creation metadata, and artifact filenames.

### `current.json`

A small mutable pointer selecting the revision returned by an unversioned
contract URI. Updating this pointer does not modify any revision.

## Immutability rules

A new revision is required when any build-affecting value changes, including:

- segment labels or display names;
- confirmation status;
- model checksum or source;
- coordinate transforms;
- voxelization or preprocessing settings;
- instructor intent;
- symmetry declarations;
- interface rules;
- functional targets or assembly declarations;
- catalog requirements.

Existing revision contents must never be edited in place.

## Registration workflow

```bash
bricksmart-contract-registry import ./task_context.json \
  --confirmations ./segment_confirmations.csv \
  --contract-id classroom-model-standard-kit
```

Registration should:

1. validate the task context and confirmation artifact;
2. resolve the referenced model and optional expected checksum;
3. remove or reject contract-owned output paths;
4. compute artifact checksums;
5. allocate an immutable revision ID;
6. write the revision atomically;
7. update `current.json` only after the revision is complete.

A failed import must not leave a partially selected current revision.

## Output-path ownership

Contracts cannot select output locations. Historical `paths.output_dir` values
are removed when a contract is registered and are ignored by the runner.

The run store assigns an isolated output directory for every execution.

## Resolution and run snapshots

At build time the registry resolves the requested URI to an exact revision. The
run store then snapshots the resolved contract, confirmation artifact, and
inventory configuration under:

```text
runs/<run-id>/inputs/
```

`run.json` records the resolved contract URI and revision, not merely the
unversioned alias. This preserves reproducibility even when `current.json`
changes later.

## Failure behavior

Resolution must fail before planning when:

- the contract ID does not exist;
- a requested revision does not exist;
- `current.json` is missing or invalid for an unversioned URI;
- a revision artifact is missing;
- a recorded checksum does not match;
- the referenced model cannot be resolved;
- the contract schema is unsupported.

The runner must not silently fall back to another revision.

## Production persistence

Set a persistent root with:

```bash
export BRICKSMART_MODEL_REGISTRY_ROOT=/data/bricksmart/model_registry
```

The local filesystem implementation is suitable for development and
single-node deployment.

A multi-node deployment should use:

- durable object storage for immutable revision documents;
- a transactional metadata store for revision indexes and current pointers;
- compare-and-swap or equivalent concurrency control when changing
  `current.json`;
- access controls separating contract authors, reviewers, and build workers.

## Retention

Immutable revisions referenced by retained runs or regression fixtures must not
be removed. Retention tooling should operate from manifest and run lineage
rather than deleting revisions based only on age.
