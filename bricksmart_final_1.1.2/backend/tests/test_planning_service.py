from bricksmart.inventory import InventoryLedger, compile_effective_inventory
from bricksmart.inventory.models import InventoryMode, InventoryProfile
from bricksmart.planning import (
    CandidateGroup,
    CandidateOption,
    ConstrainedPlanningService,
    Placement,
    PlanningProblem,
)


def option(candidate_id, score, block_type, count):
    return CandidateOption(
        candidate_id=candidate_id,
        score=score,
        placements=tuple(
            Placement(part_id=f"{candidate_id}-{index}", block_type=block_type)
            for index in range(count)
        ),
    )


def test_planner_chooses_feasible_alternative():
    profile = InventoryProfile(
        "kit", "kit", InventoryMode.FINITE,
        {"standard_2x2x2": 4, "standard_2x4x2": 2},
    )
    ledger = InventoryLedger(compile_effective_inventory(profile))
    problem = PlanningProblem(
        groups=(
            CandidateGroup(
                group_id="body",
                alternatives=(
                    option("too_many_small", 10, "standard_2x2x2", 6),
                    option("two_large", 9, "standard_2x4x2", 2),
                ),
            ),
        ),
        scarcity_weight=0,
    )
    result = ConstrainedPlanningService(ledger).plan(problem)
    assert result.status == "PASS"
    assert result.decisions[0].selected_candidate_id == "two_large"
    assert ledger.committed_counts == {"standard_2x4x2": 2}


def test_required_symmetric_pair_fails_as_one_atomic_group():
    profile = InventoryProfile("kit", "kit", InventoryMode.FINITE, {"big_wheel": 1})
    ledger = InventoryLedger(compile_effective_inventory(profile))
    pair = CandidateOption(
        candidate_id="pair",
        score=1,
        placements=(
            Placement("left", "big_wheel"),
            Placement("right", "big_wheel"),
        ),
    )
    result = ConstrainedPlanningService(ledger).plan(
        PlanningProblem(
            groups=(
                CandidateGroup(
                    group_id="wheels",
                    alternatives=(pair,),
                    selection_kind="symmetry_pair",
                ),
            )
        )
    )
    assert result.status == "FAIL_NO_FEASIBLE_BUILD"
    assert result.final_parts == []
    assert ledger.committed_counts == {}


def test_optional_group_is_skipped_without_failing_build():
    profile = InventoryProfile("kit", "kit", InventoryMode.FINITE, {"bucket": 0})
    ledger = InventoryLedger(compile_effective_inventory(profile))
    result = ConstrainedPlanningService(ledger).plan(
        PlanningProblem(
            groups=(
                CandidateGroup(
                    group_id="optional_bucket",
                    required=False,
                    alternatives=(option("bucket", 1, "bucket", 1),),
                ),
            )
        )
    )
    assert result.status == "PASS"
    assert result.decisions[0].status == "SKIPPED"
