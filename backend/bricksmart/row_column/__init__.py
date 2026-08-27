"""Decomposed row/column engine components.

The legacy worker imports these modules and preserves its public function names
while responsibilities move behind stable module boundaries. Submodules are not
eagerly imported so that worker startup remains lightweight and cycle-free.
"""

__all__ = [
    "artifacts",
    "assembly",
    "geometry",
    "runtime_paths",
    "validation",
    "visualization",
]
