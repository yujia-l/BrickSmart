from __future__ import annotations

from collections import Counter
from typing import Iterable

from bricksmart.exceptions import PlanningInputError
from bricksmart.planning.models import CandidateOption, Placement


def count_placements(placements: Iterable[Placement]) -> dict[str, int]:
    return dict(Counter(part.block_type for part in placements))


def requirements_for(candidate: CandidateOption) -> dict[str, int]:
    counted = count_placements(candidate.placements)
    if candidate.requirements and candidate.requirements != counted:
        raise PlanningInputError(
            f"Candidate {candidate.candidate_id} requirements do not match its placements: "
            f"declared={candidate.requirements}, counted={counted}"
        )
    return counted
