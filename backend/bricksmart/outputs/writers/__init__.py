"""Structured output-writer package.

The package groups artifact writers that serialize validation and planning
results into stable run-output files.
"""

from .inventory_outputs import write_run_outputs

__all__ = ["write_run_outputs"]
