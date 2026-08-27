"""Functional capability registry.

This module maps reusable capability types to planner handlers without branching
on object names such as bird or airplane.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from .specs import FunctionalAssemblySpec


AssemblyValidator = Callable[[FunctionalAssemblySpec], None]


@dataclass(frozen=True)
class AssemblyHandler:
    assembly_type: str
    validator: AssemblyValidator
    description: str


class FunctionalAssemblyRegistry:
    def __init__(self) -> None:
        """Initialize the FunctionalAssemblyRegistry instance."""
        self._handlers: dict[str, AssemblyHandler] = {}

    def register(self, handler: AssemblyHandler) -> None:
        """Perform the register operation.
        
        :param handler: The handler value.
        :type handler: AssemblyHandler
        """
        if handler.assembly_type in self._handlers:
            raise ValueError(f"Duplicate functional assembly handler: {handler.assembly_type}")
        self._handlers[handler.assembly_type] = handler

    def validate(self, specs: Iterable[FunctionalAssemblySpec]) -> None:
        """Perform the validate operation.
        
        :param specs: The specs value.
        :type specs: Iterable[FunctionalAssemblySpec]
        """
        for spec in specs:
            if not spec.enabled:
                continue
            try:
                handler = self._handlers[spec.assembly_type]
            except KeyError as exc:
                raise ValueError(f"No handler registered for assembly type {spec.assembly_type!r}") from exc
            handler.validator(spec)

    @property
    def supported_types(self) -> tuple[str, ...]:
        """Return the supported types value.
        
        :returns: The result produced by the function.
        :rtype: tuple[str, ...]
        """
        return tuple(sorted(self._handlers))


def _require_anchor(spec: FunctionalAssemblySpec) -> None:
    """Perform the require anchor operation.
    
    :param spec: The spec value.
    :type spec: FunctionalAssemblySpec
    """
    if spec.anchor_segment_id is None:
        raise ValueError(f"Assembly {spec.assembly_id!r} requires anchor_segment_id")


def _validate_catalog_attachment(spec: FunctionalAssemblySpec) -> None:
    """Validate catalog attachment.
    
    :param spec: The spec value.
    :type spec: FunctionalAssemblySpec
    """
    if not spec.source_segment_ids:
        raise ValueError(f"Assembly {spec.assembly_id!r} requires source_segment_ids")


def _validate_motion_subassembly(spec: FunctionalAssemblySpec) -> None:
    """Validate motion subassembly.
    
    :param spec: The spec value.
    :type spec: FunctionalAssemblySpec
    """
    _require_anchor(spec)
    members = spec.metadata.get("members", {}) or {}
    templates = members.get("member_templates", []) or []
    count = int(members.get("count", len(templates)) or 0)
    if count <= 0:
        raise ValueError(f"Assembly {spec.assembly_id!r} requires at least one structural member")
    if templates and len(templates) != count:
        raise ValueError(
            f"Assembly {spec.assembly_id!r} declares count={count} but has {len(templates)} member templates"
        )


def default_registry() -> FunctionalAssemblyRegistry:
    """Return the default registry.
    
    :returns: The result produced by the function.
    :rtype: FunctionalAssemblyRegistry
    """
    registry = FunctionalAssemblyRegistry()
    registry.register(AssemblyHandler("catalog_attachment", _validate_catalog_attachment, "Catalog-selected attachment"))
    registry.register(AssemblyHandler("replacement_attachment", _validate_catalog_attachment, "Source replacement attachment"))
    registry.register(AssemblyHandler("motion_connector", _require_anchor, "Single motion connector"))
    registry.register(AssemblyHandler("in_between_connector", _require_anchor, "Connector between modules"))
    registry.register(AssemblyHandler(
        "motion_connected_structural_subassembly",
        _validate_motion_subassembly,
        "Motion connector with a declarative structural member layout",
    ))
    return registry
