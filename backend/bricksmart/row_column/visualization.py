"""Self-contained Plotly visualization builders and view helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go


def infer_connector_render_axis(
    block,
):
    """Return the infer connector render axis value.
    
    :param block: Block record used by the operation.
    :returns: The result produced by the function.
    """
    record = getattr(
        block,
        "catalog_record",
        {},
    ) or {}
    role = str(
        record.get(
            "functional_role",
            "",
        )
    ).lower()
    family = str(
        getattr(
            block,
            "block_family",
            "",
        )
    ).lower()

    if (
        role == "wheel"
        or "wheel" in family
    ):
        return 0

    axis = getattr(
        block,
        "render_axis",
        None,
    )
    if axis is not None:
        return int(
            axis
        )

    explicit_axis = record.get(
        "render_axis"
    )
    if explicit_axis is not None:
        return int(
            explicit_axis
        )

    size = np.asarray(
        block.size,
        dtype=float,
    )
    return int(
        np.argmin(
            size
        )
    )


def figure_layout(title):
    """Return the figure layout value.
    
    :param title: The title value.
    :returns: The result produced by the function.
    """
    return {
        "title": title,
        "scene": {
            "aspectmode": "data",
            "xaxis":{"title":"X","backgroundcolor":"rgb(248,248,248)"},
            "yaxis":{"title":"Y","backgroundcolor":"rgb(248,248,248)"},
            "zaxis":{"title":"Z","backgroundcolor":"rgb(248,248,248)"},
            "camera":{"eye":{"x":1.45,"y":1.45,"z":1.15}},
        },
        "margin":{"l":0,"r":0,"t":55,"b":0},
        "paper_bgcolor":"white",
        "hoverlabel":{"align":"left"},
    }


def reserved_face_interactive_figure(segment_grid, requirements_df):
    """Return the reserved face interactive figure value.
    
    :param segment_grid: The segment grid value.
    :param requirements_df: DataFrame containing requirements records.
    :returns: The result produced by the function.
    """
    figure = go.Figure()
    source_coordinates = np.argwhere(segment_grid > 0)
    if len(source_coordinates):
        figure.add_trace(go.Scatter3d(
            x=source_coordinates[:, 0] + 0.5,
            y=source_coordinates[:, 1] + 0.5,
            z=source_coordinates[:, 2] + 0.5,
            mode="markers",
            marker={"size": 3, "color": "lightgray", "opacity": 0.07, "symbol": "square"},
            name="Source structure",
            hoverinfo="name",
        ))

    color_by_strategy = {
        "hard": "crimson",
        "soft": "goldenrod",
        "none": "gray",
    }
    if requirements_df is not None and not requirements_df.empty:
        for strategy in ("hard", "soft", "none"):
            subset = requirements_df[
                requirements_df.get(
                    "reservation_strategy",
                    pd.Series("hard", index=requirements_df.index),
                ).astype(str).str.lower().eq(strategy)
            ]
            if subset.empty:
                continue
            coordinates = np.asarray(subset["structural_coordinate"].tolist(), dtype=float)
            figure.add_trace(go.Scatter3d(
                x=coordinates[:, 0] + 0.5,
                y=coordinates[:, 1] + 0.5,
                z=coordinates[:, 2] + 0.5,
                mode="markers",
                marker={
                    "size": 9 if strategy == "hard" else 7,
                    "color": color_by_strategy[strategy],
                    "opacity": 0.95 if strategy == "hard" else 0.65,
                    "symbol": "diamond" if strategy == "hard" else "circle-open",
                    "line": {"color": "black", "width": 1},
                },
                text=[
                    (
                        f"Strategy: {strategy}<br>Owner: {getattr(row, 'reservation_owner_id', '')}"
                        f"<br>Segment: {row.segment_id}<br>Face: {row.structural_face}"
                        f"<br>Required role: {row.required_structural_role}"
                    )
                    for row in subset.itertuples(index=False)
                ],
                hoverinfo="text",
                name=f"{strategy.title()} reservation",
            ))

    figure.update_layout(**figure_layout("Reservation Selective Interface Reservations"))
    return figure


def reservation_candidate_reservation_figure(segment_grid, candidate_audit_df, selected_df, title):
    """Return reservation candidate reservation figure.
    
    :param segment_grid: The segment grid value.
    :param candidate_audit_df: DataFrame containing candidate audit records.
    :param selected_df: DataFrame containing selected records.
    :param title: The title value.
    :returns: The result produced by the function.
    """
    figure = go.Figure()
    source_coordinates = np.argwhere(segment_grid > 0)
    if len(source_coordinates):
        figure.add_trace(go.Scatter3d(
            x=source_coordinates[:, 0] + 0.5,
            y=source_coordinates[:, 1] + 0.5,
            z=source_coordinates[:, 2] + 0.5,
            mode="markers",
            marker={"size": 2, "color": "lightgray", "opacity": 0.05, "symbol": "square"},
            name="Source structure",
            hoverinfo="name",
        ))

    selected_ids = set(
        selected_df.get("candidate_id", pd.Series(dtype=object)).dropna().astype(int)
    ) if selected_df is not None and not selected_df.empty else set()

    if candidate_audit_df is not None and not candidate_audit_df.empty:
        for row in candidate_audit_df.itertuples(index=False):
            coordinates = getattr(row, "geometry_coordinates", []) or []
            if not coordinates:
                continue
            candidate_id = int(getattr(row, "candidate_id"))
            selected = candidate_id in selected_ids
            hard_valid = bool(getattr(row, "reservation_hard_valid", True))
            penalty = float(getattr(row, "reservation_soft_penalty", 0.0) or 0.0)
            strategy = str(getattr(row, "reservation_strategy", "soft"))
            if selected:
                color, opacity, name = "green", 0.9, "Selected"
            elif not hard_valid:
                color, opacity, name = "red", 0.55, "Hard rejected"
            elif penalty > 0:
                color, opacity, name = "orange", 0.45, "Soft penalized"
            else:
                color, opacity, name = "gold", 0.28, "Valid alternative"
            array = np.asarray(coordinates, dtype=float)
            figure.add_trace(go.Scatter3d(
                x=array[:, 0] + 0.5,
                y=array[:, 1] + 0.5,
                z=array[:, 2] + 0.5,
                mode="markers",
                marker={"size": 5, "color": color, "opacity": opacity, "symbol": "square"},
                text=(
                    f"Candidate {candidate_id}<br>State: {name}<br>Strategy: {strategy}"
                    f"<br>Adjusted score: {getattr(row, 'reservation_adjusted_score', '')}"
                ),
                hoverinfo="text",
                name=name,
                showlegend=False,
            ))

    figure.update_layout(**figure_layout(title))
    return figure


def reservation_reservation_fulfillment_figure(segment_grid, requirements_df, audit_df):
    """Return reservation reservation fulfillment figure.
    
    :param segment_grid: The segment grid value.
    :param requirements_df: DataFrame containing requirements records.
    :param audit_df: DataFrame containing audit records.
    :returns: The result produced by the function.
    """
    audit_lookup = {
        str(row.requirement_group_id): row._asdict()
        for row in audit_df.itertuples(index=False)
    } if audit_df is not None and not audit_df.empty else {}
    figure = go.Figure()
    source_coordinates = np.argwhere(segment_grid > 0)
    if len(source_coordinates):
        figure.add_trace(go.Scatter3d(
            x=source_coordinates[:, 0] + 0.5,
            y=source_coordinates[:, 1] + 0.5,
            z=source_coordinates[:, 2] + 0.5,
            mode="markers",
            marker={"size": 2, "color": "lightgray", "opacity": 0.05, "symbol": "square"},
            name="Source structure",
            hoverinfo="name",
        ))
    if requirements_df is not None and not requirements_df.empty:
        representatives = requirements_df.sort_values("alternative_rank").drop_duplicates(
            "requirement_group_id",
            keep="first",
        )
        for row in representatives.itertuples(index=False):
            audit = audit_lookup.get(str(row.requirement_group_id), {})
            strategy = str(row.reservation_strategy)
            satisfied = bool(audit.get("satisfied", False))
            color = "green" if satisfied else "red" if strategy == "hard" else "orange"
            coordinate = np.asarray(row.structural_coordinate, dtype=float)
            figure.add_trace(go.Scatter3d(
                x=[coordinate[0] + 0.5],
                y=[coordinate[1] + 0.5],
                z=[coordinate[2] + 0.5],
                mode="markers",
                marker={"size": 11, "color": color, "symbol": "diamond", "line": {"color": "black", "width": 1}},
                text=(
                    f"Group: {row.requirement_group_id}<br>Strategy: {strategy}"
                    f"<br>Status: {audit.get('status', 'not evaluated')}"
                ),
                hoverinfo="text",
                name=f"{strategy}: {'fulfilled' if satisfied else 'unresolved'}",
                showlegend=False,
            ))
    figure.update_layout(**figure_layout("Reservation Reservation Fulfillment"))
    return figure


def progression_camera(
    build_axis,
):
    """Return progression camera.
    
    :param build_axis: The build axis value.
    :returns: The result produced by the function.
    """
    build_axis = str(
        build_axis
    ).upper()
    return {
        "+Y": (
            24,
            -52,
        ),
        "-Y": (
            24,
            128,
        ),
        "+X": (
            24,
            38,
        ),
        "-X": (
            24,
            -142,
        ),
    }.get(
        build_axis,
        (
            24,
            -52,
        ),
    )


def structuralization_delta_figure(
    raw_segment_grid,
    structural_grid,
):
    """Return the structuralization delta figure value.
    
    :param raw_segment_grid: The raw segment grid value.
    :param structural_grid: The structural grid value.
    :returns: The result produced by the function.
    """
    raw_occupied = (
        raw_segment_grid > 0
    )
    structural_occupied = (
        structural_grid > 0
    )
    retained = (
        raw_occupied
        & structural_occupied
    )
    added = (
        structural_occupied
        & ~raw_occupied
    )
    removed = (
        raw_occupied
        & ~structural_occupied
    )

    figure = go.Figure()
    for mask, name, color, opacity in [
        (
            retained,
            "Retained source voxels",
            "royalblue",
            0.35,
        ),
        (
            added,
            "Added lattice voxels",
            "limegreen",
            0.80,
        ),
        (
            removed,
            "Removed source voxels",
            "crimson",
            0.80,
        ),
    ]:
        coordinates = np.argwhere(
            mask
        )
        if len(coordinates) == 0:
            continue
        figure.add_trace(
            go.Scatter3d(
                x=coordinates[:, 0] + 0.5,
                y=coordinates[:, 1] + 0.5,
                z=coordinates[:, 2] + 0.5,
                mode="markers",
                marker={
                    "size": 4,
                    "color": color,
                    "opacity": opacity,
                    "symbol": "square",
                },
                name=name,
                hoverinfo="name",
            )
        )

    figure.update_layout(
        **figure_layout(
            "Raw-to-Structural-Lattice Conversion"
        )
    )
    return figure


def assembly_segment_center(blocks):
    """Return assembly segment center.
    
    :param blocks: Block records used by the operation.
    :returns: The result produced by the function.
    """
    blocks = list(blocks)
    if not blocks:
        return None
    centers = np.asarray([
        [
            float(block.position[axis])
            + float(block.size[axis]) / 2.0
            for axis in range(3)
        ]
        for block in blocks
    ])
    return tuple(
        float(value)
        for value in centers.mean(axis=0)
    )


def assembly_interface_center(
    interface_id,
    interface_payload,
):
    """Return assembly interface center.
    
    :param interface_id: Identifier for the interface.
    :param interface_payload: The interface payload value.
    :returns: The result produced by the function.
    """
    payload = interface_payload.get(
        str(interface_id),
        {},
    )
    coordinates = []
    for key in [
        "a_coordinates",
        "b_coordinates",
    ]:
        coordinates.extend(
            payload.get(key, [])
        )
    if not coordinates:
        return None
    array = np.asarray(
        coordinates,
        dtype=float,
    )
    return tuple(
        float(value)
        for value in (
            array.mean(axis=0) + 0.5
        )
    )


__all__ = [
    'figure_layout',
    'structuralization_delta_figure',
    'reserved_face_interactive_figure',
    'reservation_candidate_reservation_figure',
    'reservation_reservation_fulfillment_figure',
    'progression_camera',
    'infer_connector_render_axis',
    'assembly_segment_center',
    'assembly_interface_center',
]
