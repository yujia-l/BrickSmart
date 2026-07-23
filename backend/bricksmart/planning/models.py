"""Planning-domain data models.

The models describe build requests, planner inputs, allocation results, and
intermediate structures shared across planning modules.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Placement:
    part_id: str
    block_type: str
    segment_id: str | None = None
    step: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert the object to dict.
        
        :returns: The result produced by the function.
        :rtype: dict[str, Any]
        """
        return asdict(self)


@dataclass(frozen=True)
class CandidateOption:
    candidate_id: str
    score: float
    placements: tuple[Placement, ...]
    requirements: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CandidateGroup:
    group_id: str
    alternatives: tuple[CandidateOption, ...]
    required: bool = True
    priority: int = 0
    selection_kind: str = "generic"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanningProblem:
    groups: tuple[CandidateGroup, ...]
    scarcity_weight: float = 0.25
    fail_on_required_group: bool = True


@dataclass(frozen=True)
class SelectionDecision:
    group_id: str
    selected_candidate_id: str | None
    status: str
    base_score: float | None
    scarcity_penalty: float | None
    effective_score: float | None
    requirements: dict[str, int]
    shortages: dict[str, dict[str, int]]
    selection_kind: str

    def to_dict(self) -> dict[str, Any]:
        """Convert the object to dict.
        
        :returns: The result produced by the function.
        :rtype: dict[str, Any]
        """
        return asdict(self)


@dataclass
class PlanningResult:
    status: str
    final_parts: list[Placement]
    decisions: list[SelectionDecision]
    unmet_requirements: list[dict[str, Any]]
    inventory_validation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert the object to dict.
        
        :returns: The result produced by the function.
        :rtype: dict[str, Any]
        """
        return {
            "status": self.status,
            "final_parts": [part.to_dict() for part in self.final_parts],
            "decisions": [decision.to_dict() for decision in self.decisions],
            "unmet_requirements": self.unmet_requirements,
            "inventory_validation": self.inventory_validation,
        }
