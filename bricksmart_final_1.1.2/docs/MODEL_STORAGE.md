# Model storage and production loading

## Purpose

Planning code must not know where a user uploaded an OBJ or how production
object storage is arranged. The model-store layer resolves a stable model
reference into a verified, immutable local file before voxelization starts.

The model store owns geometry bytes. The model registry owns reviewed build
contracts. A contract references a model through a URI and optional checksum;
it does not embed or duplicate the OBJ.

## Local storage layout

```text
model_store/
├── manifests/
│   └── <model-id>.json
├── objects/
│   └── sha256/
│       └── <first-two>/
│           └── <sha256>.obj
└── tmp/
```

A model manifest is mutable metadata pointing to an immutable content object.
The object path is derived from SHA-256, so duplicate uploads do not duplicate
bytes.

Temporary upload files belong under `tmp/` and must be removed after a
successful atomic import or a failed request.

## URI schemes

### `model://`

The normal application reference:

```text
model://<model-id>
```

It resolves a logical model ID through a manifest to an immutable SHA-256
object.

### `sha256://`

Direct immutable lookup by digest. This is useful for audit replay and
reproducible jobs that should not depend on a mutable model-ID manifest.

### Local path and `file://`

Supported for development and migration. When a model ID is supplied, the
resolver should import the file into the content-addressed store and return a
`model://` reference.

Production contracts should prefer registered `model://` references rather
than source-tree paths.

### HTTPS

Remote loading is disabled by default.

Enable it with:

```bash
export BRICKSMART_ALLOW_REMOTE_MODELS=1
```

In production, restrict hosts:

```bash
export BRICKSMART_REMOTE_MODEL_HOSTS=models.example.org,assets.example.org
```

Downloads must be streamed, size-limited, validated as supported model content,
hash-checked when an expected digest is supplied, and imported into the local
immutable store before planning.

### S3

Enable remote models and install the S3 optional dependency supported by the
package, for example:

```bash
pip install '.[s3]'
```

An S3 object must be downloaded or cached into the immutable local store before
voxelization. Planning code receives a resolved local immutable path, not an
open network stream.

## Upload and request flow

Recommended API flow:

1. The frontend uploads an OBJ to `POST /api/models/upload`.
2. The server validates the extension and configured size limit while streaming
   to a temporary file.
3. The server calculates SHA-256.
4. The object is atomically installed in the content-addressed store.
5. A model manifest is written or updated.
6. The response returns `model://<model-id>` and the digest.
7. A contract records that URI and may record `expected_sha256`.
8. The build service resolves the URI before voxelization.
9. `run.json` records the immutable URI, digest, source kind, and lineage.

The current planner accepts OBJ geometry. Support for another geometry format
requires an explicit reusable ingestion adapter and validation coverage.

## Integrity

A contract may provide:

```json
{
  "model_source": {
    "uri": "model://registered-model-id",
    "expected_sha256": "lowercase-sha256"
  }
}
```

Resolution must fail before voxelization when:

- the model ID does not exist;
- the immutable object is missing;
- the digest is malformed;
- the bytes do not match `expected_sha256`;
- a remote source violates host, size, or scheme policy;
- the file type is unsupported.

The resolved URI, local path, source kind, byte size, and SHA-256 should be
recorded in contract-validation output and run diagnostics.

## Deployment modes

### Development or single server

Use the repository-local store or set a persistent root:

```bash
export BRICKSMART_MODEL_STORE_ROOT=/data/bricksmart/model_store
```

The storage root must be outside disposable temporary directories.

### Multiple workers

Use one of these patterns:

- a shared persistent volume containing manifests and objects;
- central object storage for authoritative model bytes with a metadata store for
  logical IDs;
- S3 as the authoritative upload destination with checksum-verified worker-local
  caches.

Do not place user-uploaded models inside the source-code image.

### Containers

Mount model, registry, and run data separately:

```text
/data/bricksmart/model_store
/data/bricksmart/model_registry
/data/bricksmart/runs
```

Example:

```bash
export BRICKSMART_MODEL_STORE_ROOT=/data/bricksmart/model_store
export BRICKSMART_MODEL_REGISTRY_ROOT=/data/bricksmart/model_registry
export BRICKSMART_RUNS_ROOT=/data/bricksmart/runs
```

## Security controls

Production loading should enforce:

- supported extension and content checks;
- configurable maximum upload and download size;
- sanitized logical IDs;
- atomic writes;
- optional or policy-required expected SHA-256;
- remote loading disabled by default;
- HTTPS host allowlisting;
- timeout and redirect limits;
- temporary-file cleanup;
- filesystem confinement;
- no contract-selected output paths.

A model URI is resolved through the model-store boundary. It must not be treated
as a raw filesystem path supplied by the API caller.

## Lifecycle and garbage collection

Deleting a model ID removes only its manifest. Content garbage collection is a
separate operation because another model ID, contract revision, run, or
regression fixture may still reference the same SHA-256 object.

Garbage collection must:

1. enumerate references from manifests, retained contracts, retained runs, and
   regression fixtures;
2. identify unreferenced immutable objects;
3. apply an appropriate retention period;
4. delete only after verification or administrative review.

## Storage adapters

The runtime boundary is the model resolver plus model-store interface. A
database-backed manifest service, GCS adapter, Azure Blob adapter, or presigned
upload workflow may be added without changing voxelization or structural
planning code.
