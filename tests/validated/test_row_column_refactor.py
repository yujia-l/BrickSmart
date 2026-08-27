from __future__ import annotations

import ast
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from bricksmart.row_column.artifacts import write_step_validation_artifacts
from bricksmart.row_column.assembly import (
    format_block_id_field,
    parse_block_id_field,
)
from bricksmart.row_column.geometry import FaceType
from bricksmart.row_column.validation import contact_status_between_blocks

ROOT = Path(__file__).resolve().parents[2]


EXTRACTED_ENGINE_NAMES = {
    "FaceType",
    "actual_block_face_type",
    "block_family_count_dataframe",
    "build_assembly_oriented_assembly_steps",
    "build_assembly_timeline",
    "catalog_run_audit",
    "compute_contact_surfaces",
    "compute_segment_adjacency",
    "contact_status_between_blocks",
    "coordinate_plan_to_world",
    "figure_layout",
    "format_block_id_field",
    "geometry_contacts",
    "json_safe_value",
    "locking_components_from_edges",
    "mask_iou",
    "parse_block_id_field",
    "read_json",
    "remap_validation_block_ids_to_planning",
    "render_voxel_view",
    "reservation_final_reservation_audit",
    "resolve_path",
    "safe_export_dataframe",
    "structuralization_delta_figure",
    "touching_face_geometry",
    "validate_functional_block",
    "validate_required_embedded_connectors",
}


def test_extracted_names_are_imported_not_redefined_in_engine() -> None:
    """Test that extracted names are imported not redefined in engine."""
    engine_path = ROOT / "backend/bricksmart/row_column_engine.py"
    tree = ast.parse(engine_path.read_text(encoding="utf-8"))
    definitions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    assert EXTRACTED_ENGINE_NAMES.isdisjoint(definitions)

    source = engine_path.read_text(encoding="utf-8")
    assert "from bricksmart.row_column.geometry import (" in source
    assert "from bricksmart.row_column.validation import (" in source
    assert "from bricksmart.row_column.artifacts import (" in source


def test_runtime_and_contract_packages_import_in_fresh_process() -> None:
    """Test that runtime and contract packages import in fresh process."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend")
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import bricksmart.runtime; "
                "from bricksmart.contracts import "
                "ModelContractError, validate_model_contract; "
                "assert ModelContractError and callable(validate_model_contract)"
            ),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_assembly_block_id_helpers_round_trip() -> None:
    """Test that assembly block id helpers round trip."""
    encoded = format_block_id_field([7, 2, 7, 4])
    assert parse_block_id_field(encoded) == [7, 2, 7, 4]


@dataclass
class _Block:
    block_id: int
    position: tuple[int, int, int]
    size: tuple[int, int, int]
    faces: dict[str, list[list[FaceType]]]


def test_extracted_contact_validation_preserves_face_polarity() -> None:
    """Test that extracted contact validation preserves face polarity."""
    male = _Block(
        block_id=1,
        position=(0, 0, 0),
        size=(2, 2, 2),
        faces={"+X": [[FaceType.MALE]]},
    )
    female = _Block(
        block_id=2,
        position=(2, 0, 0),
        size=(2, 2, 2),
        faces={"-X": [[FaceType.FEMALE]]},
    )
    contact = contact_status_between_blocks(male, female)
    assert contact is not None
    assert contact["overlap_area"] == 4
    assert contact["contact_status"] == "male_to_female_lock"


def test_step_validation_writer_uses_explicit_output_context(tmp_path: Path) -> None:
    """Test that step validation writer uses explicit output context.
    
    :param tmp_path: Temporary filesystem path provided by pytest.
    :type tmp_path: Path
    """
    validation = {
        "step_rows": [
            {
                "step": 1,
                "row": 0,
                "step_status": "accepted",
                "num_blocks": 1,
                "num_components": 1,
                "valid_components": 1,
                "invalid_components": 0,
                "locks_to_accepted_prior": 0,
                "lock_area_to_accepted_prior": 0,
                "internal_lock_area": 0,
                "male_male_or_overlap_conflicts": 0,
                "exposed_male_area": 4,
                "accepted_block_ids": "1",
                "rejected_block_ids": "",
            }
        ],
        "block_rows": [
            {
                "step": 1,
                "block_id": 1,
                "block_family": "standard_2x2x2",
                "accepted": True,
                "reason": "root_component",
                "rotation": 0,
                "male_face": "+X",
            }
        ],
        "component_rows": [],
        "contact_rows": [],
        "block_validation": {1: {"accepted": True}},
        "accepted_before_by_step": {1: []},
        "accepted_after_by_step": {1: [1]},
        "num_final_accepted_blocks": 1,
        "num_total_blocks": 1,
        "all_blocks_accepted": True,
    }
    frames = write_step_validation_artifacts(
        validation,
        output_dir=tmp_path,
        show_output_paths=False,
    )
    assert len(frames) == 4
    assert (tmp_path / "build_step_validation.json").is_file()
    assert (tmp_path / "validated_build_instructions.md").is_file()
