# BrickSmart model store

This directory is the local content-addressed model store used by the packaged regression contracts.

- `manifests/` maps stable `model://` IDs to immutable content.
- `objects/sha256/` contains deduplicated OBJ bytes.
- `tmp/` is runtime scratch space and is ignored.

In production, set `BRICKSMART_MODEL_STORE_ROOT` to persistent application storage rather than storing user uploads in the source checkout.
