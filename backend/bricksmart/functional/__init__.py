"""Functional-assembly capability package.

The package contains reusable attachment and motion-capability definitions used
by model-agnostic planning.
"""

from .registry import AssemblyHandler, FunctionalAssemblyRegistry, default_registry
from .specs import FunctionalAssemblySpec

__all__ = ["AssemblyHandler", "FunctionalAssemblyRegistry", "FunctionalAssemblySpec", "default_registry"]
