from pathlib import Path

from bricksmart.inventory import InventoryLedger, compile_effective_inventory
from bricksmart.inventory.models import InventoryMode, InventoryProfile
from bricksmart.outputs.writers import write_run_outputs
from bricksmart.planning import (
    CandidateGroup,
    CandidateOption,
    ConstrainedPlanningService,
    Placement,
    PlanningProblem,
)


def test_required_output_files_are_written(tmp_path: Path):
    """Test that required output files are written.
    
    :param tmp_path: Temporary filesystem path provided by pytest.
    :type tmp_path: Path
    """
    profile = InventoryProfile("kit", "kit", InventoryMode.FINITE, {"big_wheel": 2})
    ledger = InventoryLedger(compile_effective_inventory(profile))
    candidate = CandidateOption(
        candidate_id="wheel_pair",
        score=1.0,
        placements=(Placement("left", "big_wheel"), Placement("right", "big_wheel")),
    )
    result = ConstrainedPlanningService(ledger).plan(
        PlanningProblem(groups=(CandidateGroup("wheels", (candidate,)),))
    )
    paths = write_run_outputs(tmp_path, result=result, ledger=ledger)
    assert {path.name for path in paths} == {
        "effective_inventory.json",
        "inventory_usage.csv",
        "inventory_events.csv",
        "inventory_validation.json",
        "unmet_inventory_requirements.csv",
        "final_parts.csv",
        "build_instructions.json",
        "build_instructions.html",
    }

    html = (tmp_path / "build_instructions.html").read_text(encoding="utf-8")
    assert "BrickSmart build instructions" in html
    assert "big_wheel" in html
    assert "Total blocks" in html
