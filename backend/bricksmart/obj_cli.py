"""Command-line entry point for greedy OBJ build experiments.

The CLI runs direct OBJ loading and experimental voxel/placement workflows
outside the validated contract-registry execution path.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from bricksmart.obj_pipeline import run_obj_build
from bricksmart.planning.voxel_models import StructuralPlannerConfig
from bricksmart.reporting import write_obj_build_outputs


def build_parser() -> argparse.ArgumentParser:
    """Build parser.
    
    :returns: The generated result.
    :rtype: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        description="Build a coarse inventory-constrained structure directly from a segmented OBJ"
    )
    parser.add_argument("--obj", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--teacher-budget", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--up-axis", choices=["auto", "x", "y", "z"], default="auto")
    parser.add_argument("--target-longest-cells", type=int, default=18)
    parser.add_argument("--minimum-component-voxels", type=int, default=1)
    parser.add_argument("--minimum-candidate-fill-ratio", type=float, default=0.20)
    parser.add_argument("--coverage-target", type=float, default=0.93)
    parser.add_argument("--scarcity-weight", type=float, default=0.25)
    parser.add_argument("--symmetry-mode", choices=["required", "auto"], default="required")
    parser.add_argument("--minimum-target-symmetry", type=float, default=0.95)
    parser.add_argument("--minimum-build-volume-symmetry", type=float, default=0.98)
    parser.add_argument("--symmetry-solver-time-limit", type=float, default=30.0)
    parser.add_argument("--no-html", action="store_true")
    return parser


def main() -> None:
    """Run the command-line entry point."""
    args = build_parser().parse_args()
    config = StructuralPlannerConfig(
        minimum_candidate_fill_ratio=args.minimum_candidate_fill_ratio,
        coverage_target=args.coverage_target,
        scarcity_weight=args.scarcity_weight,
        symmetry_mode=args.symmetry_mode,
        minimum_target_symmetry=args.minimum_target_symmetry,
        minimum_build_volume_symmetry=args.minimum_build_volume_symmetry,
        symmetry_solver_time_limit_seconds=args.symmetry_solver_time_limit,
    )
    result, ledger = run_obj_build(
        obj_path=args.obj,
        inventory_path=args.inventory,
        catalog_path=args.catalog,
        teacher_budget_path=args.teacher_budget,
        up_axis=args.up_axis,
        target_longest_cells=args.target_longest_cells,
        minimum_component_voxels=args.minimum_component_voxels,
        planner_config=config,
    )
    paths = write_obj_build_outputs(
        args.output,
        result=result,
        ledger=ledger,
        include_html=not args.no_html,
    )
    print(f"Build status: {result.status}")
    print(f"Source segments: {len(result.model.segments)}")
    print(f"Target voxels: {len(result.voxel_model.target_voxels)}")
    print(f"Final block count: {len(result.placements)}")
    print(f"Coverage: {result.geometry_validation['coverage_fraction']:.2%}")
    print(f"Symmetry: {result.symmetry_validation.get('exact_mirrored_block_fraction', 0.0):.2%}")
    print("Wrote:")
    for path in paths:
        print(f"  {path}")


if __name__ == "__main__":
    main()
