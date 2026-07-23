"""Regression-baseline support package.

The package contains helpers for loading reviewed fixtures and comparing live
runs against expected outputs.
"""

from .checkpoints import (
    build_checkpoint_manifest,
    compare_checkpoint_manifests,
    write_checkpoint_manifest,
)

__all__ = [
    "build_checkpoint_manifest",
    "compare_checkpoint_manifests",
    "write_checkpoint_manifest",
]
