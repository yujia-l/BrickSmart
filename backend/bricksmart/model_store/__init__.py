"""Model-store package for immutable geometry assets.

The package resolves model references used by contracts and keeps model bytes
separate from generated runs.
"""

from .local import LocalModelStore, safe_model_id
from .resolver import ModelResolver
from .types import ModelRecord, ModelSourceSpec, ResolvedModel

__all__ = [
    "LocalModelStore",
    "ModelResolver",
    "ModelRecord",
    "ModelSourceSpec",
    "ResolvedModel",
    "safe_model_id",
]
