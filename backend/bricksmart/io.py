"""Shared file-system and serialization helpers.

This module centralizes small JSON, CSV, and path utilities used by BrickSmart
runtime, validation, and reporting code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bricksmart.planning.models import (
    CandidateGroup,
    CandidateOption,
    Placement,
    PlanningProblem,
)


def load_planning_problem(path: str | Path) -> PlanningProblem:
    """Load planning problem.
    
    :param path: Filesystem path used by the operation.
    :type path: str | Path
    :returns: The loaded data.
    :rtype: PlanningProblem
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    groups = []
    for raw_group in payload.get("groups", []):
        alternatives = []
        for raw_candidate in raw_group.get("alternatives", []):
            placements = tuple(
                Placement(
                    part_id=str(raw_part["part_id"]),
                    block_type=str(raw_part["block_type"]),
                    segment_id=(
                        None
                        if raw_part.get("segment_id") is None
                        else str(raw_part.get("segment_id"))
                    ),
                    step=(None if raw_part.get("step") is None else int(raw_part["step"])),
                    metadata=dict(raw_part.get("metadata", {})),
                )
                for raw_part in raw_candidate.get("placements", [])
            )
            alternatives.append(
                CandidateOption(
                    candidate_id=str(raw_candidate["candidate_id"]),
                    score=float(raw_candidate.get("score", 0.0)),
                    placements=placements,
                    requirements=dict(raw_candidate.get("requirements", {})),
                    metadata=dict(raw_candidate.get("metadata", {})),
                )
            )
        groups.append(
            CandidateGroup(
                group_id=str(raw_group["group_id"]),
                alternatives=tuple(alternatives),
                required=bool(raw_group.get("required", True)),
                priority=int(raw_group.get("priority", 0)),
                selection_kind=str(raw_group.get("selection_kind", "generic")),
                metadata=dict(raw_group.get("metadata", {})),
            )
        )
    return PlanningProblem(
        groups=tuple(groups),
        scarcity_weight=float(payload.get("scarcity_weight", 0.25)),
        fail_on_required_group=bool(payload.get("fail_on_required_group", True)),
    )


def dump_json(path: str | Path, payload: Any) -> None:
    """Dump json.
    
    :param path: Filesystem path used by the operation.
    :type path: str | Path
    :param payload: Payload data to process.
    :type payload: Any
    """
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
