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
        self._handlers: dict[str, AssemblyHandler] = {}

    def register(self, handler: AssemblyHandler) -> None:
        if handler.assembly_type in self._handlers:
            raise ValueError(f"Duplicate functional assembly handler: {handler.assembly_type}")
        self._handlers[handler.assembly_type] = handler

    def validate(self, specs: Iterable[FunctionalAssemblySpec]) -> None:
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
        return tuple(sorted(self._handlers))


def _require_anchor(spec: FunctionalAssemblySpec) -> None:
    if spec.anchor_segment_id is None:
        raise ValueError(f"Assembly {spec.assembly_id!r} requires anchor_segment_id")


def _validate_catalog_attachment(spec: FunctionalAssemblySpec) -> None:
    if not spec.source_segment_ids:
        raise ValueError(f"Assembly {spec.assembly_id!r} requires source_segment_ids")


def _validate_motion_subassembly(spec: FunctionalAssemblySpec) -> None:
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
