from __future__ import annotations

from bricksmart.exceptions import InventoryConfigurationError
from bricksmart.inventory.models import EffectiveInventory, InventoryMode, InventoryProfile


def compile_effective_inventory(
    profile: InventoryProfile,
    teacher_budget: dict[str, int] | None = None,
) -> EffectiveInventory:
    """Combine physical kit limits and optional per-run teacher limits."""
    budget = dict(teacher_budget or {})

    if profile.mode is InventoryMode.UNLIMITED:
        if budget:
            limits = dict(budget)
            sources = {block: "teacher_budget" for block in limits}
            return EffectiveInventory(
                inventory_id=f"{profile.inventory_id}+teacher_budget",
                mode=InventoryMode.FINITE,
                limits=limits,
                limit_sources=sources,
                physical_limits={},
                teacher_limits=budget,
            )
        return EffectiveInventory(
            inventory_id=profile.inventory_id,
            mode=InventoryMode.UNLIMITED,
            limits={},
            limit_sources={},
            physical_limits={},
            teacher_limits={},
        )

    unknown_budget = sorted(set(budget) - set(profile.quantities))
    if unknown_budget:
        raise InventoryConfigurationError(
            "Teacher budget references blocks absent from the physical kit: "
            + ", ".join(unknown_budget)
        )

    limits: dict[str, int] = {}
    sources: dict[str, str] = {}
    for block_type, physical_limit in profile.quantities.items():
        if block_type in budget and budget[block_type] < physical_limit:
            limits[block_type] = budget[block_type]
            sources[block_type] = "teacher_budget"
        else:
            limits[block_type] = physical_limit
            sources[block_type] = "physical_inventory"

    return EffectiveInventory(
        inventory_id=(
            f"{profile.inventory_id}+teacher_budget" if budget else profile.inventory_id
        ),
        mode=InventoryMode.FINITE,
        limits=limits,
        limit_sources=sources,
        physical_limits=dict(profile.quantities),
        teacher_limits=budget,
    )
