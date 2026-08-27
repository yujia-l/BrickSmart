"""Public contract helpers without eager runtime imports.

``runtime.contract`` consumes ``contracts.semantic_preservation``.  Keeping the
runtime symbols lazy prevents a package-initialization cycle when the row/column
worker imports :mod:`bricksmart.runtime` in a fresh Python process.
"""

from __future__ import annotations

from typing import Any

from .semantic_preservation import build_semantic_target_preservation_report

_RUNTIME_EXPORTS = {
    "ModelContractError",
    "ModelContractValidation",
    "validate_model_contract",
}


def __getattr__(name: str) -> Any:
    """Return the getattr value.
    
    :param name: Name used by the operation.
    :type name: str
    :returns: The result produced by the function.
    :rtype: Any
    """
    if name not in _RUNTIME_EXPORTS:
        raise AttributeError(name)
    from bricksmart.runtime import contract as runtime_contract

    return getattr(runtime_contract, name)


__all__ = [
    "ModelContractError",
    "ModelContractValidation",
    "validate_model_contract",
    "build_semantic_target_preservation_report",
]
