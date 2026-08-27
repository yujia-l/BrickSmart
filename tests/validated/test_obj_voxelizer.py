from pathlib import Path
from bricksmart.model_store import LocalModelStore

from bricksmart.geometry import load_segmented_obj, voxelize_segmented_model

ROOT = Path(__file__).resolve().parents[2]
BASE_OBJ = LocalModelStore(ROOT / "model_store").resolve("bird-base").local_path


def test_base_obj_segment_voxelization_is_deterministic():
    """Test that base obj segment voxelization is deterministic."""
    model = load_segmented_obj(BASE_OBJ, up_axis="auto")
    voxels = voxelize_segmented_model(model, target_longest_cells=18)
    assert len(voxels.target_voxels) == 212
    assert voxels.grid_shape == (19, 13, 8)
    assert voxels.segment_voxel_counts["root.0"] == 94
    assert voxels.segment_voxel_counts["root.1"] == 48
    assert voxels.segment_voxel_counts["root.2"] == 49
