from pathlib import Path

from bricksmart.inventory import load_inventory_profile

ROOT = Path(__file__).resolve().parents[2]


def test_standard_kit_counts_are_exact():
    """Test that standard kit counts are exact."""
    profile = load_inventory_profile(
        ROOT / "backend/bricksmart/config/inventory/standard_kit.yaml"
    )
    assert profile.quantities == {
        "rotation_block": 2,
        "hinge_block": 2,
        "big_wheel": 4,
        "small_wheel": 4,
        "standard_2x2x2": 16,
        "standard_2x3x2": 10,
        "standard_2x4x2": 12,
        "feature_beam_3x1x1": 4,
        "feature_beam_7x1x1": 4,
        "feature_beam_curved": 4,
        "angle_joint": 12,
        "angle_symmetrical": 6,
        "bucket": 1,
        "bucket_arms": 1,
    }
