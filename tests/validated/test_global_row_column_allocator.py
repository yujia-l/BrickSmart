from bricksmart.planning.global_row_column_allocator import (
    RowColumnPlanGroup,
    RowColumnPlanOption,
    allocate_row_column_options,
)


def test_global_allocator_avoids_early_segment_starvation():
    """Test that global allocator avoids early segment starvation."""
    groups = [
        RowColumnPlanGroup(
            "body",
            (
                RowColumnPlanOption("body-blue", "body", {"standard_2x2x2": 14}, 14),
                RowColumnPlanOption(
                    "body-large",
                    "body",
                    {"standard_2x2x2": 6, "standard_2x4x2": 4},
                    10,
                ),
            ),
        ),
        RowColumnPlanGroup(
            "wings",
            (
                RowColumnPlanOption("wings", "wings", {"standard_2x2x2": 8}, 8),
            ),
        ),
    ]
    allocation = allocate_row_column_options(
        groups,
        {"standard_2x2x2": 16, "standard_2x4x2": 12},
    )
    assert allocation.status == "PASS"
    assert {option.option_id for option in allocation.selected_options} == {
        "body-large",
        "wings",
    }
    assert allocation.requirements["standard_2x2x2"] == 14


def test_global_allocator_reserves_functional_blocks_before_structural_choice():
    """Test that global allocator reserves functional blocks before structural choice."""
    groups = [
        RowColumnPlanGroup(
            "airframe",
            (
                RowColumnPlanOption("airframe", "airframe", {"standard_2x2x2": 16}, 16),
            ),
        )
    ]
    allocation = allocate_row_column_options(
        groups,
        {"standard_2x2x2": 16, "big_wheel": 4, "rotation_block": 2},
        fixed_requirements={"big_wheel": 2, "rotation_block": 1},
    )
    assert allocation.status == "PASS"
    assert allocation.requirements == {
        "big_wheel": 2,
        "rotation_block": 1,
        "standard_2x2x2": 16,
    }


def test_global_allocator_reports_model_wide_shortage():
    """Test that global allocator reports model wide shortage."""
    groups = [
        RowColumnPlanGroup(
            "body",
            (RowColumnPlanOption("body", "body", {"standard_2x2x2": 14}, 14),),
        ),
        RowColumnPlanGroup(
            "wing",
            (RowColumnPlanOption("wing", "wing", {"standard_2x2x2": 8}, 8),),
        ),
    ]
    allocation = allocate_row_column_options(
        groups,
        {"standard_2x2x2": 16},
    )
    assert allocation.status == "FAIL_NO_GLOBAL_INVENTORY_ALLOCATION"
    assert allocation.shortages["standard_2x2x2"]["shortage"] == 6
