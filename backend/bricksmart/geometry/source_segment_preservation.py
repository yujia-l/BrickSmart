"""Source-segment lineage preservation helpers.

This module tracks source segment IDs through geometry processing so final parts
and validation artifacts remain traceable to confirmed semantics.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np


@dataclass(frozen=True)
class SourceSegmentPreservationReport:
    source_segment_ids: tuple[int, ...]
    surviving_segment_ids: tuple[int, ...]
    missing_segment_ids: tuple[int, ...]
    raw_counts: dict[int, int]
    clean_counts: dict[int, int]
    status: str

    def to_dict(self) -> dict[str, object]:
        """Convert the object to dict.
        
        :returns: The result produced by the function.
        :rtype: dict[str, object]
        """
        return {
            "status": self.status,
            "source_segment_ids": list(self.source_segment_ids),
            "surviving_segment_ids": list(self.surviving_segment_ids),
            "missing_segment_ids": list(self.missing_segment_ids),
            "raw_counts": {str(k): v for k, v in self.raw_counts.items()},
            "clean_counts": {str(k): v for k, v in self.clean_counts.items()},
            "source_segment_count": len(self.source_segment_ids),
            "surviving_segment_count": len(self.surviving_segment_ids),
            "preservation_fraction": (
                len(self.surviving_segment_ids) / len(self.source_segment_ids)
                if self.source_segment_ids
                else 1.0
            ),
        }


def segment_counts(grid: np.ndarray) -> dict[int, int]:
    """Return segment counts.
    
    :param grid: The grid value.
    :type grid: np.ndarray
    :returns: The result produced by the function.
    :rtype: dict[int, int]
    """
    values, counts = np.unique(np.asarray(grid, dtype=int), return_counts=True)
    return {
        int(value): int(count)
        for value, count in zip(values, counts)
        if int(value) > 0
    }


def evaluate_source_segment_preservation(
    *,
    source_segment_ids: list[int] | tuple[int, ...],
    raw_grid: np.ndarray,
    clean_grid: np.ndarray,
    clean_to_source: Mapping[int, int] | None = None,
) -> SourceSegmentPreservationReport:
    """Evaluate source segment preservation.
    
    :param source_segment_ids: Identifiers for the source segment records.
    :type source_segment_ids: list[int] | tuple[int, ...]
    :param raw_grid: The raw grid value.
    :type raw_grid: np.ndarray
    :param clean_grid: The clean grid value.
    :type clean_grid: np.ndarray
    :param clean_to_source: The clean to source value.
    :type clean_to_source: Mapping[int, int] | None
    :returns: The result produced by the function.
    :rtype: SourceSegmentPreservationReport
    """
    source_ids = tuple(sorted({int(value) for value in source_segment_ids}))
    raw = segment_counts(raw_grid)
    raw_by_source = Counter(raw)

    clean = segment_counts(clean_grid)
    clean_by_source: Counter[int] = Counter()
    if clean_to_source:
        for clean_id, count in clean.items():
            clean_by_source[int(clean_to_source.get(clean_id, clean_id))] += count
    else:
        clean_by_source.update(clean)

    surviving = tuple(sorted(set(source_ids) & set(clean_by_source)))
    missing = tuple(sorted(set(source_ids) - set(surviving)))
    return SourceSegmentPreservationReport(
        source_segment_ids=source_ids,
        surviving_segment_ids=surviving,
        missing_segment_ids=missing,
        raw_counts={sid: int(raw_by_source.get(sid, 0)) for sid in source_ids},
        clean_counts={sid: int(clean_by_source.get(sid, 0)) for sid in source_ids},
        status="PASS" if not missing else "FAIL_SOURCE_SEGMENTS_LOST",
    )


def recommend_grid_size(
    *,
    current_grid_size: int,
    report: SourceSegmentPreservationReport,
    maximum_grid_size: int = 48,
) -> int:
    """Recommend a conservative next grid size when source parts disappear.

    This does not claim that resolution alone fixes every loss. It provides a
    deterministic escalation for the next preflight run while preserving the
    original model and preprocessing policy.
    """

    if report.status == "PASS":
        return int(current_grid_size)
    missing_fraction = len(report.missing_segment_ids) / max(1, len(report.source_segment_ids))
    multiplier = 1.5 if missing_fraction <= 0.25 else 2.0
    proposed = int(np.ceil(int(current_grid_size) * multiplier / 2.0) * 2)
    return min(maximum_grid_size, max(int(current_grid_size) + 2, proposed))
