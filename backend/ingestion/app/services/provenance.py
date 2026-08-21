"""Traceability. build() stamps every required field so any downstream record — bundle.json,
nodes.json, relations.json, a PostgreSQL row, a pgvector chunk; can be traced back to its exact
source object and its unit-level policy."""
import uuid
from datetime import datetime, timezone

# deterministic namespace so bundle_id / rule_id are stable across re-runs (idempotent)
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "kidspark.knowledge")


def bundle_id(bundle_name: str) -> str:
    return str(uuid.uuid5(_NS, "bundle:" + bundle_name))


def rule_id(policy_scope: str, index: int = 0) -> str:
    return str(uuid.uuid5(_NS, f"rule:{policy_scope}:{index}"))


def build(meta, filename, gcs_object_path, b_name, p_scope, policy_path,
          manifest_path="", r_id=None, processing_version="1.0") -> dict:
    """The canonical provenance block attached to every artifact and every node/chunk."""
    return {
        "grade_band": meta.get("grade_band", ""),
        "lab": meta.get("lab", ""),
        "unit": meta.get("unit", ""),
        "lesson": meta.get("lesson", ""),
        "filename": filename,
        "gcs_object_path": gcs_object_path,
        "bundle_name": b_name,
        "bundle_id": bundle_id(b_name),
        "policy_scope": p_scope,
        "policy_path": policy_path,
        "rule_id": r_id,
        "manifest_path": manifest_path,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "processing_version": processing_version,
    }
