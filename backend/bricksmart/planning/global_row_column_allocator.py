"""Whole-model allocator for row/column structural planning.

This module coordinates block-family allocation across segments so inventory is
reserved globally instead of greedily per local region.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class RowColumnPlanOption:
    """One mechanically valid row/column plan for a segment or atomic pair."""

    option_id: str
    group_id: str
    requirements: dict[str, int]
    block_count: int
    build_axis: str | None = None
    score: float = 0.0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RowColumnPlanGroup:
    """A required selection group.

    A group may represent one segment, a mirrored segment pair, a connector
    module, or a functional attachment. Exactly one option is selected for a
    required group. Optional groups may be skipped.
    """

    group_id: str
    options: tuple[RowColumnPlanOption, ...]
    required: bool = True
    priority: int = 0
    group_kind: str = "segment"


@dataclass(frozen=True)
class GlobalRowColumnAllocation:
    status: str
    selected_options: tuple[RowColumnPlanOption, ...]
    requirements: dict[str, int]
    remaining: dict[str, int | None]
    shortages: dict[str, dict[str, int]]
    explored_states: int
    complete_group_count: int
    required_group_count: int


def _normalize_requirements(requirements: Mapping[str, int]) -> dict[str, int]:
    """Normalize requirements.
    
    :param requirements: The requirements value.
    :type requirements: Mapping[str, int]
    :returns: The computed result.
    :rtype: dict[str, int]
    """
    result: dict[str, int] = {}
    for family, raw_count in requirements.items():
        count = int(raw_count)
        if count < 0:
            raise ValueError(f"Negative requirement for {family}: {count}")
        if count:
            result[str(family)] = result.get(str(family), 0) + count
    return result


def _sum_requirements(options: Iterable[RowColumnPlanOption]) -> dict[str, int]:
    """Return the sum requirements value.
    
    :param options: The options value.
    :type options: Iterable[RowColumnPlanOption]
    :returns: The result produced by the function.
    :rtype: dict[str, int]
    """
    total: Counter[str] = Counter()
    for option in options:
        total.update(_normalize_requirements(option.requirements))
    return dict(sorted(total.items()))


def _fits(
    current: Mapping[str, int],
    addition: Mapping[str, int],
    capacities: Mapping[str, int | None],
) -> bool:
    """Return whether fits.
    
    :param current: The current value.
    :type current: Mapping[str, int]
    :param addition: The addition value.
    :type addition: Mapping[str, int]
    :param capacities: The capacities value.
    :type capacities: Mapping[str, int | None]
    :returns: The result produced by the function.
    :rtype: bool
    """
    for family, count in addition.items():
        capacity = capacities.get(family, 0)
        if capacity is None:
            continue
        if int(current.get(family, 0)) + int(count) > int(capacity):
            return False
    return True


def _shortages(
    requirements: Mapping[str, int], capacities: Mapping[str, int | None]
) -> dict[str, dict[str, int]]:
    """Return the shortages value.
    
    :param requirements: The requirements value.
    :type requirements: Mapping[str, int]
    :param capacities: The capacities value.
    :type capacities: Mapping[str, int | None]
    :returns: The result produced by the function.
    :rtype: dict[str, dict[str, int]]
    """
    result: dict[str, dict[str, int]] = {}
    for family, required in requirements.items():
        capacity = capacities.get(family, 0)
        if capacity is None:
            continue
        if int(required) > int(capacity):
            result[family] = {
                "required": int(required),
                "capacity": int(capacity),
                "shortage": int(required) - int(capacity),
            }
    return result


def _selection_rank(options: Sequence[RowColumnPlanOption]) -> tuple[object, ...]:
    """Higher is better; fewer blocks is preferred before soft score."""

    return (
        -sum(option.block_count for option in options),
        sum(float(option.score) for option in options),
        tuple(option.option_id for option in options),
    )


def allocate_row_column_options(
    groups: Iterable[RowColumnPlanGroup],
    capacities: Mapping[str, int | None],
    *,
    fixed_requirements: Mapping[str, int] | None = None,
    max_states: int = 250_000,
) -> GlobalRowColumnAllocation:
    """Select one mechanically valid option per group under shared inventory.

    This is an exact depth-first branch-and-bound allocator. It does not alter
    geometry or connector validation; it only chooses among plans that have
    already passed the row/column mechanical gates. Groups are ordered by
    scarcity and priority so constrained functional and mirrored modules are
    considered before flexible structural segments.
    """

    capacities = {str(k): (None if v is None else int(v)) for k, v in capacities.items()}
    fixed = _normalize_requirements(fixed_requirements or {})
    ordered = sorted(
        groups,
        key=lambda group: (
            not group.required,
            -int(group.priority),
            len(group.options),
            group.group_id,
        ),
    )
    required_group_count = sum(group.required for group in ordered)
    explored = 0
    best: tuple[RowColumnPlanOption, ...] | None = None
    best_rank: tuple[object, ...] | None = None

    def search(
        index: int,
        usage: Counter[str],
        selected: list[RowColumnPlanOption],
    ) -> None:
        """Search search.
        
        :param index: The index value.
        :type index: int
        :param usage: The usage value.
        :type usage: Counter[str]
        :param selected: The selected value.
        :type selected: list[RowColumnPlanOption]
        """
        nonlocal explored, best, best_rank
        if explored >= max_states:
            return
        explored += 1
        if index == len(ordered):
            rank = _selection_rank(selected)
            if best is None or rank > best_rank:  # type: ignore[operator]
                best = tuple(selected)
                best_rank = rank
            return

        group = ordered[index]
        options = sorted(
            group.options,
            key=lambda option: (
                option.block_count,
                -float(option.score),
                option.option_id,
            ),
        )
        for option in options:
            req = _normalize_requirements(option.requirements)
            if not _fits(usage, req, capacities):
                continue
            usage.update(req)
            selected.append(option)
            search(index + 1, usage, selected)
            selected.pop()
            usage.subtract(req)
            for family in list(usage):
                if usage[family] == 0:
                    del usage[family]

        if not group.required:
            search(index + 1, usage, selected)

    initial = Counter(fixed)
    if _fits({}, initial, capacities):
        search(0, initial, [])

    if best is not None:
        requirements = Counter(fixed)
        requirements.update(_sum_requirements(best))
        remaining = {
            family: None if capacity is None else int(capacity) - int(requirements.get(family, 0))
            for family, capacity in capacities.items()
        }
        return GlobalRowColumnAllocation(
            status="PASS",
            selected_options=best,
            requirements=dict(sorted(requirements.items())),
            remaining=remaining,
            shortages={},
            explored_states=explored,
            complete_group_count=len(best),
            required_group_count=required_group_count,
        )

    # Report a useful lower-bound shortage using the least-block option from
    # each required group. This is diagnostic only; it is not a feasible plan.
    lower_bound_options = [
        min(group.options, key=lambda option: (option.block_count, option.option_id))
        for group in ordered
        if group.required and group.options
    ]
    lower_bound = Counter(fixed)
    lower_bound.update(_sum_requirements(lower_bound_options))
    return GlobalRowColumnAllocation(
        status="FAIL_NO_GLOBAL_INVENTORY_ALLOCATION",
        selected_options=(),
        requirements=dict(sorted(lower_bound.items())),
        remaining={
            family: None if capacity is None else int(capacity) - int(lower_bound.get(family, 0))
            for family, capacity in capacities.items()
        },
        shortages=_shortages(lower_bound, capacities),
        explored_states=explored,
        complete_group_count=0,
        required_group_count=required_group_count,
    )
