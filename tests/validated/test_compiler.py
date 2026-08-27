import pytest

from bricksmart.exceptions import InventoryConfigurationError
from bricksmart.inventory import compile_effective_inventory
from bricksmart.inventory.models import InventoryMode, InventoryProfile


def test_teacher_budget_reduces_but_never_increases_physical_limit():
    """Test that teacher budget reduces but never increases physical limit."""
    profile = InventoryProfile(
        "kit", "kit", InventoryMode.FINITE, {"standard_2x2x2": 16, "big_wheel": 4}
    )
    effective = compile_effective_inventory(
        profile, {"standard_2x2x2": 12, "big_wheel": 10}
    )
    assert effective.limit_for("standard_2x2x2") == 12
    assert effective.limit_for("big_wheel") == 4
    assert effective.limit_sources["standard_2x2x2"] == "teacher_budget"
    assert effective.limit_sources["big_wheel"] == "physical_inventory"


def test_teacher_budget_cannot_add_unknown_physical_block():
    """Test that teacher budget cannot add unknown physical block."""
    profile = InventoryProfile("kit", "kit", InventoryMode.FINITE, {"big_wheel": 4})
    with pytest.raises(InventoryConfigurationError):
        compile_effective_inventory(profile, {"small_wheel": 2})


def test_teacher_budget_can_constrain_unlimited_regression_profile():
    """Test that teacher budget can constrain unlimited regression profile."""
    profile = InventoryProfile("unlimited", "unlimited", InventoryMode.UNLIMITED, {})
    effective = compile_effective_inventory(profile, {"big_wheel": 2})
    assert effective.mode is InventoryMode.FINITE
    assert effective.limit_for("big_wheel") == 2
