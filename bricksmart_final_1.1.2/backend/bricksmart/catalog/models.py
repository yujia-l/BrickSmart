from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CatalogBlockDefinition:
    block_type: str
    category: str
    allowed_dimensions: tuple[tuple[int, int, int], ...]
    structural_eligible: bool
    packing_priority: int
    display_color: str
    male_faces: tuple[str, ...] = ()
    female_faces: tuple[str, ...] = ()
    allowed_rotations: tuple[str, ...] = ()
    source_sheet: str = ""
    source_row: int = 0
    raw_metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def maximum_volume(self) -> int:
        if not self.allowed_dimensions:
            return 0
        return max(x * y * z for x, y, z in self.allowed_dimensions)

    def to_summary(self) -> dict[str, Any]:
        return {
            "block_type": self.block_type,
            "category": self.category,
            "allowed_dimensions": [list(value) for value in self.allowed_dimensions],
            "structural_eligible": self.structural_eligible,
            "packing_priority": self.packing_priority,
            "display_color": self.display_color,
            "male_faces": list(self.male_faces),
            "female_faces": list(self.female_faces),
            "allowed_rotations": list(self.allowed_rotations),
            "source_sheet": self.source_sheet,
            "source_row": self.source_row,
        }


@dataclass(frozen=True)
class WorkbookCatalog:
    source_path: Path
    source_sha256: str
    definitions: tuple[CatalogBlockDefinition, ...]
    sheets_read: tuple[str, ...]
    header_rows: dict[str, int]

    @property
    def by_type(self) -> dict[str, CatalogBlockDefinition]:
        return {item.block_type: item for item in self.definitions}

    @property
    def block_ids(self) -> set[str]:
        return set(self.by_type)

    @property
    def colors(self) -> dict[str, str]:
        return {
            item.block_type: item.display_color
            for item in self.definitions
            if item.display_color
        }

    @property
    def structural_definitions(self) -> tuple[CatalogBlockDefinition, ...]:
        return tuple(
            sorted(
                (item for item in self.definitions if item.structural_eligible),
                key=lambda item: (-item.packing_priority, item.block_type),
            )
        )

    def to_summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "sheets_read": list(self.sheets_read),
            "header_rows": dict(self.header_rows),
            "block_count": len(self.definitions),
            "structural_block_count": len(self.structural_definitions),
            "block_ids": sorted(self.block_ids),
        }
