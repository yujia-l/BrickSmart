"""Visualization helpers for BrickSmart geometry and build artifacts.

This module prepares rendered block views, Plotly figures, and visual summaries
for reports and interactive build instructions.
"""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go

from bricksmart.exceptions import CatalogConfigurationError
from bricksmart.planning.voxel_models import ObjBuildResult


def _cuboid_mesh(origin: tuple[int, int, int], dimensions: tuple[int, int, int]):
    """Return cuboid mesh.
    
    :param origin: The origin value.
    :type origin: tuple[int, int, int]
    :param dimensions: The dimensions value.
    :type dimensions: tuple[int, int, int]
    :returns: The result produced by the function.
    """
    x, y, z = origin
    dx, dy, dz = dimensions
    vertices = [
        (x, y, z),
        (x + dx, y, z),
        (x + dx, y + dy, z),
        (x, y + dy, z),
        (x, y, z + dz),
        (x + dx, y, z + dz),
        (x + dx, y + dy, z + dz),
        (x, y + dy, z + dz),
    ]
    triangles = [
        (0, 1, 2), (0, 2, 3),
        (4, 6, 5), (4, 7, 6),
        (0, 4, 5), (0, 5, 1),
        (1, 5, 6), (1, 6, 2),
        (2, 6, 7), (2, 7, 3),
        (3, 7, 4), (3, 4, 0),
    ]
    return vertices, triangles


def _catalog_color(result: ObjBuildResult, block_type: str) -> str:
    """Return catalog color.
    
    :param result: The result value.
    :type result: ObjBuildResult
    :param block_type: The block type value.
    :type block_type: str
    :returns: The result produced by the function.
    :rtype: str
    """
    color = str(result.catalog_colors.get(block_type, "")).strip()
    if not color:
        raise CatalogConfigurationError(
            f"No visualization color for {block_type!r} in block_definitions.csv"
        )
    return color


def _add_target_trace(figure: go.Figure, result: ObjBuildResult) -> None:
    """Add target trace.
    
    :param figure: The figure value.
    :type figure: go.Figure
    :param result: The result value.
    :type result: ObjBuildResult
    """
    target = sorted(result.voxel_model.target_voxels)
    figure.add_trace(
        go.Scatter3d(
            x=[value[0] + 0.5 for value in target],
            y=[value[1] + 0.5 for value in target],
            z=[value[2] + 0.5 for value in target],
            mode="markers",
            marker={"size": 2.5, "color": "#777777", "opacity": 0.20},
            name="Target voxels",
            hoverinfo="skip",
        )
    )


def _block_trace(selected, placement, *, color: str, visible: bool = True) -> go.Mesh3d:
    """Return block trace.
    
    :param selected: The selected value.
    :param placement: The placement value.
    :param color: The color value.
    :type color: str
    :param visible: The visible value.
    :type visible: bool
    :returns: The result produced by the function.
    :rtype: go.Mesh3d
    """
    candidate = selected.candidate
    vertices, triangles = _cuboid_mesh(candidate.origin, candidate.dimensions)
    return go.Mesh3d(
        x=[value[0] for value in vertices],
        y=[value[1] for value in vertices],
        z=[value[2] for value in vertices],
        i=[value[0] for value in triangles],
        j=[value[1] for value in triangles],
        k=[value[2] for value in triangles],
        color=color,
        opacity=0.84,
        flatshading=True,
        name=placement.part_id,
        visible=visible,
        hovertemplate=(
            f"step={placement.step}<br>{placement.part_id}<br>{candidate.block_type}"
            f"<br>catalog color={color}"
            f"<br>source segment={candidate.dominant_segment}"
            f"<br>segment step={placement.metadata.get('segment_step')}"
            f"<br>origin={candidate.origin}"
            f"<br>dimensions={candidate.dimensions}"
            "<extra></extra>"
        ),
        showscale=False,
    )


def _base_layout(title: str) -> dict:
    """Return base layout.
    
    :param title: The title value.
    :type title: str
    :returns: The result produced by the function.
    :rtype: dict
    """
    return {
        "title": title,
        "scene": {
            "xaxis_title": "Planner X",
            "yaxis_title": "Planner Y",
            "zaxis_title": "Planner Z (up)",
            "aspectmode": "data",
        },
        "legend": {"itemsizing": "constant"},
        "margin": {"l": 0, "r": 0, "t": 80, "b": 0},
    }


def write_build_preview(path: str | Path, result: ObjBuildResult) -> Path:
    """Write build preview.
    
    :param path: Filesystem path used by the operation.
    :type path: str | Path
    :param result: The result value.
    :type result: ObjBuildResult
    :returns: The result produced by the function.
    :rtype: Path
    """
    path = Path(path)
    figure = go.Figure()
    _add_target_trace(figure, result)
    placements_by_id = {placement.part_id: placement for placement in result.placements}
    for selected in result.selected_blocks:
        placement = placements_by_id[f"part_{selected.selection_index:03d}"]
        figure.add_trace(
            _block_trace(
                selected,
                placement,
                color=_catalog_color(result, selected.candidate.block_type),
            )
        )
    validation = result.geometry_validation
    figure.update_layout(
        **_base_layout(
            f"BrickSmart final build — block colors — "
            f"{len(result.placements)} blocks — "
            f"{validation['coverage_fraction']:.1%} coarse coverage"
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(path, include_plotlyjs=True, full_html=True)
    return path


def write_segment_build_player(path: str | Path, result: ObjBuildResult) -> Path:
    """Write a step player using catalog colors; segment identity remains metadata."""
    path = Path(path)
    figure = go.Figure()
    _add_target_trace(figure, result)
    selected_by_id = {
        f"part_{selected.selection_index:03d}": selected
        for selected in result.selected_blocks
    }
    ordered = sorted(result.placements, key=lambda placement: placement.step or 0)
    for placement in ordered:
        selected = selected_by_id[placement.part_id]
        figure.add_trace(
            _block_trace(
                selected,
                placement,
                color=_catalog_color(result, selected.candidate.block_type),
            )
        )

    total_traces = 1 + len(ordered)
    slider_steps = []
    for step in range(0, len(ordered) + 1):
        visible = [True] + [int(placement.step or 0) <= step for placement in ordered]
        if step == 0:
            label = "Target"
            title = "Target voxels before placement"
        else:
            placement = ordered[step - 1]
            label = str(step)
            title = (
                f"Step {step}: {placement.segment_id} — "
                f"segment step {placement.metadata.get('segment_step')}"
            )
        slider_steps.append(
            {
                "method": "update",
                "args": [{"visible": visible}, {"title": title}],
                "label": label,
            }
        )

    segment_buttons = []
    for segment in result.planner_summary.get("segment_order", []):
        end = int(result.planner_summary["segment_step_ranges"][segment]["end"])
        visible = [True] + [int(placement.step or 0) <= end for placement in ordered]
        segment_buttons.append(
            {
                "label": f"Through {segment}",
                "method": "update",
                "args": [
                    {"visible": visible},
                    {"title": f"Completed segment phase: {segment} (through step {end})"},
                ],
            }
        )
    segment_buttons.append(
        {
            "label": "Final build",
            "method": "update",
            "args": [
                {"visible": [True] * total_traces},
                {"title": "Final build — block colors"},
            ],
        }
    )

    layout = _base_layout(
        "Segment-by-segment build player — block colors"
    )
    layout.update(
        {
            "sliders": [
                {
                    "active": len(ordered),
                    "currentvalue": {"prefix": "Build step: "},
                    "pad": {"t": 45},
                    "steps": slider_steps,
                }
            ],
            "updatemenus": [
                {
                    "type": "dropdown",
                    "direction": "down",
                    "x": 0.0,
                    "y": 1.08,
                    "buttons": segment_buttons,
                    "showactive": True,
                }
            ],
            "annotations": [
                {
                    "text": "Block colors identify block types. Segment details appear in hover labels and the phase selector.",
                    "xref": "paper",
                    "yref": "paper",
                    "x": 1.0,
                    "y": 1.06,
                    "showarrow": False,
                    "xanchor": "right",
                }
            ],
        }
    )
    figure.update_layout(**layout)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(path, include_plotlyjs=True, full_html=True)
    return path


def write_final_catalog_png(path: str | Path, result: ObjBuildResult) -> Path:
    """Write final catalog png.
    
    :param path: Filesystem path used by the operation.
    :type path: str | Path
    :param result: The result value.
    :type result: ObjBuildResult
    :returns: The result produced by the function.
    :rtype: Path
    """
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    path = Path(path)
    selected_by_id = {
        f"part_{selected.selection_index:03d}": selected
        for selected in result.selected_blocks
    }
    figure = plt.figure(figsize=(11, 8))
    axis = figure.add_subplot(111, projection="3d")

    for placement in sorted(result.placements, key=lambda value: value.step or 0):
        candidate = selected_by_id[placement.part_id].candidate
        vertices, _ = _cuboid_mesh(candidate.origin, candidate.dimensions)
        faces = [
            [vertices[index] for index in (0, 1, 2, 3)],
            [vertices[index] for index in (4, 5, 6, 7)],
            [vertices[index] for index in (0, 1, 5, 4)],
            [vertices[index] for index in (1, 2, 6, 5)],
            [vertices[index] for index in (2, 3, 7, 6)],
            [vertices[index] for index in (3, 0, 4, 7)],
        ]
        collection = Poly3DCollection(
            faces,
            alpha=0.86,
            facecolor=_catalog_color(result, candidate.block_type),
            edgecolor="black",
            linewidth=0.45,
        )
        axis.add_collection3d(collection)

    all_cells = [cell for selected in result.selected_blocks for cell in selected.candidate.cells]
    if all_cells:
        axis.set_xlim(min(cell[0] for cell in all_cells), max(cell[0] for cell in all_cells) + 1)
        axis.set_ylim(min(cell[1] for cell in all_cells), max(cell[1] for cell in all_cells) + 1)
        axis.set_zlim(min(cell[2] for cell in all_cells), max(cell[2] for cell in all_cells) + 1)
    axis.set_xlabel("Planner X")
    axis.set_ylabel("Planner Y")
    axis.set_zlabel("Planner Z")
    axis.set_title("BrickSmart build — colors loaded from block_definitions.csv")
    axis.view_init(elev=24, azim=-58)
    try:
        axis.set_box_aspect((1.8, 1.0, 0.8))
    except AttributeError:
        pass
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return path


def write_symmetry_top_png(path: str | Path, result: ObjBuildResult) -> Path:
    """Write symmetry top png.
    
    :param path: Filesystem path used by the operation.
    :type path: str | Path
    :param result: The result value.
    :type result: ObjBuildResult
    :returns: The result produced by the function.
    :rtype: Path
    """
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    path = Path(path)
    selected_by_id = {
        f"part_{selected.selection_index:03d}": selected
        for selected in result.selected_blocks
    }
    figure, axis = plt.subplots(figsize=(12, 8))
    ordered = sorted(
        result.placements,
        key=lambda placement: (
            selected_by_id[placement.part_id].candidate.origin[2],
            placement.step or 0,
        ),
    )
    for placement in ordered:
        candidate = selected_by_id[placement.part_id].candidate
        x, y, _ = candidate.origin
        dx, dy, _ = candidate.dimensions
        axis.add_patch(
            Rectangle(
                (x, y),
                dx,
                dy,
                facecolor=_catalog_color(result, candidate.block_type),
                edgecolor="black",
                linewidth=0.8,
                alpha=0.72,
            )
        )
    symmetry = result.planner_summary.get("symmetry", {})
    if symmetry.get("axis") == "x":
        axis.axvline(
            float(symmetry.get("plane_coordinate", 0.0)) + 0.5,
            linestyle="--",
            linewidth=1.2,
            color="black",
            label="detected symmetry plane",
        )
    all_cells = [cell for selected in result.selected_blocks for cell in selected.candidate.cells]
    if all_cells:
        axis.set_xlim(min(cell[0] for cell in all_cells) - 0.5, max(cell[0] for cell in all_cells) + 1.5)
        axis.set_ylim(min(cell[1] for cell in all_cells) - 0.5, max(cell[1] for cell in all_cells) + 1.5)
    axis.set_aspect("equal", adjustable="box")
    axis.set_xlabel("Planner X (bilateral direction)")
    axis.set_ylabel("Planner Y")
    axis.set_title(
        "Top view — block colors — exact mirrored placement "
        f"({result.symmetry_validation.get('exact_mirrored_block_fraction', 0.0):.0%})"
    )
    axis.legend(loc="upper right")
    axis.grid(True, alpha=0.25)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return path
