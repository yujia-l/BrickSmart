from pathlib import Path
from bricksmart.model_store import LocalModelStore

import numpy as np

from bricksmart.geometry import load_segmented_obj

ROOT = Path(__file__).resolve().parents[2]
BASE_OBJ = LocalModelStore(ROOT / "model_store").resolve("bird-base").local_path


def test_base_obj_preserves_source_object_segments():
    """Test that base obj preserves source object segments."""
    model = load_segmented_obj(BASE_OBJ, up_axis="auto")
    assert model.source_vertex_count == 15929
    assert model.source_face_count == 15927
    assert len(model.segments) == 7
    assert [segment.segment_id for segment in model.segments] == [
        "root.0", "root.1", "root.2", "root.3", "root.4", "root.5", "root.6"
    ]
    assert model.axis_mapping == ("x", "z", "y")
    assert np.all(model.planner_extents > 0)
