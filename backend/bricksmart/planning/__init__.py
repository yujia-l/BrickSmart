"""Model-agnostic planning package.

The package contains structural, segment, symmetry, and inventory-coordination
planners that consume contracts and catalog metadata.
"""

from .models import CandidateGroup, CandidateOption, Placement, PlanningProblem, PlanningResult
from .service import ConstrainedPlanningService
from .segment_build_order import SegmentBuildOrder, assign_segment_build_steps

__all__ = [
    "CandidateGroup",
    "CandidateOption",
    "ConstrainedPlanningService",
    "Placement",
    "PlanningProblem",
    "PlanningResult",
    "SegmentBuildOrder",
    "assign_segment_build_steps",
]
