"""High-level planning service orchestration.

This module coordinates catalog loading, inventory compilation, model geometry,
planning requirements, and validated build outputs.
"""

from __future__ import annotations

from bricksmart.inventory.ledger import InventoryLedger
from bricksmart.inventory.policies import scarcity_penalty
from bricksmart.planning.models import (
    CandidateOption,
    PlanningProblem,
    PlanningResult,
    SelectionDecision,
)
from bricksmart.planning.requirements import requirements_for
from bricksmart.validation.inventory_validation import validate_final_inventory


class ConstrainedPlanningService:
    """Select candidate alternatives while enforcing one shared inventory ledger."""

    def __init__(self, ledger: InventoryLedger):
        """Initialize the ConstrainedPlanningService instance.
        
        :param ledger: Inventory ledger used by the operation.
        :type ledger: InventoryLedger
        """
        self.ledger = ledger

    def plan(self, problem: PlanningProblem) -> PlanningResult:
        """Run the planning endpoint or operation.
        
        :param problem: The problem value.
        :type problem: PlanningProblem
        :returns: The result produced by the function.
        :rtype: PlanningResult
        """
        final_parts = []
        decisions: list[SelectionDecision] = []
        unmet: list[dict[str, object]] = []
        status = "PASS"

        groups = sorted(problem.groups, key=lambda group: (-group.priority, group.group_id))
        for group in groups:
            feasible: list[tuple[float, float, CandidateOption, dict[str, int]]] = []
            candidate_shortages: dict[str, dict[str, dict[str, int]]] = {}

            for candidate in group.alternatives:
                requirements = requirements_for(candidate)
                shortages = self.ledger.shortages(requirements)
                if shortages:
                    candidate_shortages[candidate.candidate_id] = shortages
                    continue
                penalty = scarcity_penalty(
                    self.ledger,
                    requirements,
                    weight=problem.scarcity_weight,
                )
                feasible.append((candidate.score - penalty, penalty, candidate, requirements))

            if not feasible:
                group_status = "FAIL_REQUIRED_BLOCK_UNAVAILABLE" if group.required else "SKIPPED"
                decisions.append(
                    SelectionDecision(
                        group_id=group.group_id,
                        selected_candidate_id=None,
                        status=group_status,
                        base_score=None,
                        scarcity_penalty=None,
                        effective_score=None,
                        requirements={},
                        shortages=_merge_shortages(candidate_shortages),
                        selection_kind=group.selection_kind,
                    )
                )
                unmet.append(
                    {
                        "group_id": group.group_id,
                        "required": group.required,
                        "selection_kind": group.selection_kind,
                        "candidate_shortages": candidate_shortages,
                    }
                )
                if group.required:
                    status = "FAIL_NO_FEASIBLE_BUILD"
                    if problem.fail_on_required_group:
                        break
                continue

            effective_score, penalty, selected, requirements = max(
                feasible,
                key=lambda item: (item[0], item[2].score, item[2].candidate_id),
            )
            reservation_id = self.ledger.reserve(
                requirements,
                reason=f"{group.selection_kind}:{group.group_id}:{selected.candidate_id}",
            )
            self.ledger.commit(reservation_id)
            final_parts.extend(selected.placements)
            decisions.append(
                SelectionDecision(
                    group_id=group.group_id,
                    selected_candidate_id=selected.candidate_id,
                    status="SELECTED",
                    base_score=selected.score,
                    scarcity_penalty=penalty,
                    effective_score=effective_score,
                    requirements=requirements,
                    shortages={},
                    selection_kind=group.selection_kind,
                )
            )

        validation = validate_final_inventory(
            final_parts=final_parts,
            inventory=self.ledger.inventory,
            ledger_committed=self.ledger.committed_counts,
        )
        if validation["status"] != "PASS":
            status = validation["status"]

        return PlanningResult(
            status=status,
            final_parts=final_parts,
            decisions=decisions,
            unmet_requirements=unmet,
            inventory_validation=validation,
        )


def _merge_shortages(
    candidate_shortages: dict[str, dict[str, dict[str, int]]]
) -> dict[str, dict[str, int]]:
    """Merge shortages.
    
    :param candidate_shortages: The candidate shortages value.
    :type candidate_shortages: dict[str, dict[str, dict[str, int]]]
    :returns: The result produced by the function.
    :rtype: dict[str, dict[str, int]]
    """
    merged: dict[str, dict[str, int]] = {}
    for shortages in candidate_shortages.values():
        for block_type, data in shortages.items():
            current = merged.get(block_type)
            if current is None or data["shortfall"] < current["shortfall"]:
                merged[block_type] = dict(data)
    return merged
