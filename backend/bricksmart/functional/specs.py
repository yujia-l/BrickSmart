"""Functional assembly specification models.

This module defines reusable capability declarations for wheels, motion blocks,
connectors, replacements, and other non-structural assemblies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class FunctionalAssemblySpec:
    assembly_id: str
    assembly_type: str
    display_name: str
    source_segment_ids: tuple[int, ...] = ()
    anchor_segment_id: int | None = None
    enabled: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "FunctionalAssemblySpec":
        """Create the object from mapping.
        
        :param row: Row record to process.
        :type row: Mapping[str, Any]
        :returns: The result produced by the function.
        :rtype: 'FunctionalAssemblySpec'
        """
        assembly_id = str(row.get("assembly_id") or row.get("physical_target_id") or "").strip()
        if not assembly_id:
            raise ValueError("Functional assembly requires assembly_id or physical_target_id")
        return cls(
            assembly_id=assembly_id,
            assembly_type=str(row.get("assembly_type") or "catalog_attachment").strip().lower(),
            display_name=str(row.get("display_name") or assembly_id.replace("_", " ").title()),
            source_segment_ids=tuple(int(value) for value in row.get("source_segment_ids", []) or []),
            anchor_segment_id=(int(row["anchor_segment_id"]) if row.get("anchor_segment_id") not in (None, "") else None),
            enabled=bool(row.get("enabled", True)),
            metadata=dict(row),
        )
