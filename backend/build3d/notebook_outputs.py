"""Notebook-style BrickSmart renders generated from the current OBJ.

This ports the visual/output side of the exploratory notebook into regular
backend code so the teacher review page shows job-specific artifacts instead
of static images from another project folder.

For a stage-by-stage map back to `my_notebook_25 (CSP).ipynb`, see
`backend/build3d/NOTEBOOK_PORT_NOTES.md`.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from build3d.block_decomposer import (
    block_inventory_summary as physical_block_inventory_summary,
    decompose_voxels_to_blocks,
    serialize_blocks,
)
from build3d.connectivity import build_connectivity_report
from build3d.csp_solver import optimize_block_rotations
from build3d.instructions import (
    describe_instruction_step as describe_physical_instruction_step,
    generate_row_steps as generate_physical_row_steps,
)
from build3d.voxelizer import build_segmented_voxel_grid, compute_contact_surfaces


PALETTE = np.array(
    [
        [220, 55, 75],
        [72, 180, 230],
        [255, 225, 70],
        [75, 220, 140],
        [145, 80, 210],
        [245, 130, 48],
        [70, 240, 240],
        [240, 50, 230],
        [210, 245, 60],
        [250, 190, 190],
    ],
    dtype=np.uint8,
)

TEACHER_VOXEL_SIZE = 16


@dataclass
class ObjSegment:
    segment_id: int
    name: str
    faces: list[list[int]]


@dataclass
class BrickBlock:
    block_id: int
    position: tuple[int, int, int]
    size: tuple[int, int, int]
    segment_id: int


def generate_notebook_outputs(
    obj_path: Path | None,
    job_dir: Path,
    segment_rows: list[dict[str, Any]] | None = None,
    artifact_label: str = "BrickSmart model",
    voxel_size: int = TEACHER_VOXEL_SIZE,
    clean_segments: bool = True,
    movement_intents: list[dict[str, Any]] | None = None,
    teacher_connection_intent: str = "",
    max_semantic_segments: int | None = None,
) -> dict[str, Any]:
    output_dir = job_dir / "notebook_outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not obj_path or not obj_path.exists():
        manifest = {
            "status": "not_available",
            "source_obj": str(obj_path) if obj_path else None,
            "images": [],
            "steps": [],
            "instruction_steps": [],
            "note": "No source OBJ was available for notebook-style rendering.",
        }
        _write_manifest(output_dir, manifest)
        return manifest

    # Notebook stage: load Bang segments, voxelize them, clean the grid, and
    # detect segment adjacency/contact surfaces.
    segment_lookup = segment_label_lookup(segment_rows)
    source_vertices, source_segments = load_obj_segments(obj_path)
    raw_voxel_segment = obj_to_voxel_with_segments(source_vertices, source_segments, voxel_size)
    voxel_build = build_segmented_voxel_grid(obj_path, voxel_size=voxel_size, clean_segments=clean_segments)
    voxel_segment = voxel_build.voxel_segment
    adjacency = voxel_build.adjacency
    contacts = voxel_build.contacts
    cleaned_source_voxel_segment = voxel_segment.copy()
    coarsening = coarsen_to_validated_segment_budget(
        voxel_segment,
        segment_rows,
        max_segment_count=max_semantic_segments,
    )
    if coarsening.get("applied"):
        voxel_segment = coarsening["voxel_segment"]
        adjacency = compute_segment_adjacency(voxel_segment)
        contacts = compute_contact_surfaces(voxel_segment)
        if not coarsening.get("label_mapping_preserved"):
            segment_lookup = remap_coarsened_segment_labels(segment_rows, voxel_segment, movement_intents or [])
    connector_candidates = infer_connector_sites(
        movement_intents or [],
        segment_rows or [],
        segment_lookup,
        contacts,
        teacher_connection_intent,
    )

    # Notebook stage: render source segment diagnostics used by the teacher and
    # the planned LLM segment-labeling loop.
    images: list[str] = []
    segment_visualization = output_dir / "segment_visualization.png"
    render_segment_visualization(voxel_segment, segment_visualization)
    images.append(str(segment_visualization))

    multiview = output_dir / "segment_multiview.png"
    render_segment_multiview(voxel_segment, adjacency, multiview)
    images.append(str(multiview))

    # Notebook stage: decompose voxels into physical blocks, optimize block
    # rotations with CSP scoring, and validate physical connectivity.
    blocks = decompose_voxels_to_blocks(voxel_segment)
    blocks = optimize_block_rotations(blocks, voxel_segment.shape[0])
    connectivity_report = build_connectivity_report(blocks, voxel_segment.shape[0])
    brick_preview = output_dir / "brick_approximation.png"
    render_blocks(blocks, voxel_segment.shape[0], brick_preview, title="BrickSmart Block Plan")
    images.append(str(brick_preview))

    # Notebook stage: create assembly steps. Each step gets a single isometric
    # render plus an 8-view placement sheet for the teacher guide.
    instruction_steps = generate_physical_row_steps(blocks)
    step_paths = []
    step_multiview_paths = []
    step_records = []
    built_so_far = []
    for index, step_blocks in enumerate(instruction_steps, start=1):
        path = output_dir / f"notebook_step_{index:02d}.png"
        multiview_path = output_dir / f"notebook_step_{index:02d}_multiview.png"
        render_instruction_step(built_so_far, step_blocks, voxel_segment.shape[0], path, index)
        render_instruction_multiview(built_so_far, step_blocks, voxel_segment.shape[0], multiview_path, index)
        step_paths.append(str(path))
        step_multiview_paths.append(str(multiview_path))
        images.append(str(path))
        images.append(str(multiview_path))
        step_records.append(
            describe_physical_instruction_step(
                index,
                path,
                multiview_path,
                step_blocks,
                built_so_far,
                segment_lookup,
                artifact_label,
                connector_candidates,
            )
        )
        built_so_far.extend(step_blocks)

    block_inventory = physical_block_inventory_summary(blocks)
    contact_summary = summarize_contacts(contacts)
    segment_survival = summarize_segment_survival(
        raw_voxel_segment,
        cleaned_source_voxel_segment,
        source_segments,
    )
    semantic_survival = summarize_semantic_target_survival(voxel_segment, coarsening)
    validation = {
        "is_fully_connected": connectivity_report.get("is_fully_connected", False),
        "component_count": connectivity_report.get("component_count", 0),
        "invalid_interface_count": connectivity_report.get("invalid_interface_count", 0),
        "bridge_block_count": connectivity_report.get("bridge_block_count", 0),
        "connector_candidate_count": len(connector_candidates),
        "connector_review_required": any(item.get("status") != "candidate" for item in connector_candidates),
        "segment_survival": segment_survival,
    }
    manifest = {
        "status": "generated",
        "physicalization": "notebook_csp_v1",
        "source_obj": str(obj_path),
        "resolution_profile": "teacher_readable_16_grid" if voxel_size == TEACHER_VOXEL_SIZE else "custom_grid",
        "voxel_size": voxel_size,
        "clean_segments": clean_segments,
        "segment_count": int(len([x for x in np.unique(voxel_segment) if x > 0])),
        "source_segment_count": segment_survival["source_segment_count"],
        "surviving_segment_count": semantic_survival.get(
            "surviving_semantic_target_count",
            segment_survival["surviving_segment_count"],
        ),
        "segment_preservation_fraction": semantic_survival.get(
            "preservation_fraction",
            segment_survival["preservation_fraction"],
        ),
        "source_segment_preservation_fraction": segment_survival["preservation_fraction"],
        "semantic_target_survival": semantic_survival,
        "recommended_next_voxel_size": segment_survival["recommended_next_voxel_size"],
        "block_count": len(blocks),
        "block_inventory": block_inventory,
        "blocks": serialize_blocks(blocks),
        "connectivity_report": connectivity_report,
        "contacts": contact_summary,
        "connector_candidates": connector_candidates,
        "validation": validation,
        "segment_coarsening": {key: value for key, value in coarsening.items() if key != "voxel_segment"},
        "final_image": str(brick_preview),
        "segment_visualization_image": str(segment_visualization),
        "segment_multiview_image": str(multiview),
        "images": images,
        "steps": step_paths,
        "step_multiviews": step_multiview_paths,
        "instruction_steps": step_records,
        "note": "Generated from the current Bang OBJ using teacher-readable notebook voxelization, CSP block rotation, and physical connectivity checks.",
    }
    _write_manifest(output_dir, manifest)
    return manifest


def coarsen_to_validated_segment_budget(
    voxel_segment: np.ndarray,
    segment_rows: list[dict[str, Any]] | None,
    *,
    max_segment_count: int | None = None,
) -> dict[str, Any]:
    """Merge small voxel regions until coarse teacher-approved region budgets are met.

    Bang can split one teacher-approved static idea into many disconnected color
    regions. That is useful diagnostically, but it makes the classroom build
    look harder than the validated planning budget allows. When the pipeline has
    already created coarse validated segment rows, merge the smallest regions
    into adjacent larger regions before rendering and decomposing the build.
    """
    rows = segment_rows or []
    coarse = bool(rows) and all(
        str(row.get("source_segment_grouping") or "") == "coarse_validated_region"
        for row in rows
    )
    target_count = len(rows) if coarse else 0
    if max_segment_count is not None and max_segment_count > 0:
        target_count = min(target_count, int(max_segment_count))
    ids = [int(value) for value in np.unique(voxel_segment) if value > 0]
    explicit_groups: list[tuple[int, list[int]]] = []
    for group_id, row in enumerate(rows[:target_count], start=1):
        source_ids = []
        for value in row.get("source_segment_ids", []) or []:
            try:
                source_ids.append(int(value))
            except (TypeError, ValueError):
                continue
        if source_ids:
            explicit_groups.append((group_id, sorted(set(source_ids))))

    if explicit_groups:
        source_to_group = {
            source_id: group_id
            for group_id, source_ids in explicit_groups
            for source_id in source_ids
        }
        static_group_ids = [
            index
            for index, row in enumerate(rows[:target_count], start=1)
            if str(row.get("movement") or "static").lower() == "static"
        ]
        fallback_group = static_group_ids[0] if static_group_ids else 1
        normalized = np.zeros_like(voxel_segment)
        unassigned_source_ids: list[int] = []
        for source_id in ids:
            group_id = source_to_group.get(source_id)
            if group_id is None:
                group_id = fallback_group
                unassigned_source_ids.append(source_id)
            normalized[voxel_segment == source_id] = group_id
        ending_ids = [int(value) for value in np.unique(normalized) if value > 0]
        return {
            "applied": True,
            "strategy": "contract_semantic_groups",
            "label_mapping_preserved": True,
            "target_segment_count": int(target_count),
            "starting_segment_count": int(len(ids)),
            "ending_segment_count": int(len(ending_ids)),
            "source_to_semantic_group": source_to_group,
            "unassigned_source_ids": unassigned_source_ids,
            "voxel_segment": normalized,
        }

    if not target_count or len(ids) <= target_count:
        return {"applied": False, "target_segment_count": target_count, "starting_segment_count": len(ids)}

    coarsened = voxel_segment.copy()
    merges: list[dict[str, int]] = []
    while True:
        ids = [int(value) for value in np.unique(coarsened) if value > 0]
        if len(ids) <= target_count:
            break
        counts = {sid: int(np.count_nonzero(coarsened == sid)) for sid in ids}
        adjacency = compute_segment_adjacency(coarsened)
        source_id = min(ids, key=lambda sid: (counts.get(sid, 0), sid))
        neighbors = [sid for sid in adjacency.get(source_id, []) if sid in counts]
        candidates = neighbors or [sid for sid in ids if sid != source_id]
        if not candidates:
            break
        target_id = max(candidates, key=lambda sid: (counts.get(sid, 0), -sid))
        coarsened[coarsened == source_id] = target_id
        merges.append({"from_segment": int(source_id), "to_segment": int(target_id)})

    id_map = {sid: index for index, sid in enumerate(sorted(int(value) for value in np.unique(coarsened) if value > 0), start=1)}
    normalized = np.zeros_like(coarsened)
    for old_id, new_id in id_map.items():
        normalized[coarsened == old_id] = new_id

    return {
        "applied": True,
        "target_segment_count": int(target_count),
        "starting_segment_count": int(len([value for value in np.unique(voxel_segment) if value > 0])),
        "ending_segment_count": int(len(id_map)),
        "merges": merges,
        "id_normalization": id_map,
        "voxel_segment": normalized,
    }


def summarize_semantic_target_survival(
    voxel_segment: np.ndarray,
    coarsening: dict[str, Any],
) -> dict[str, Any]:
    """Report preservation at the teacher-approved semantic target level."""
    if not coarsening.get("applied") or not coarsening.get("label_mapping_preserved"):
        return {}
    target_count = int(coarsening.get("target_segment_count") or 0)
    surviving = len([value for value in np.unique(voxel_segment) if value > 0])
    fraction = min((surviving / target_count) if target_count else 1.0, 1.0)
    return {
        "status": "pass" if surviving > 0 and fraction >= 0.75 else "review",
        "semantic_target_count": target_count,
        "surviving_semantic_target_count": surviving,
        "preservation_fraction": round(float(fraction), 4),
        "grouping_strategy": coarsening.get("strategy"),
    }


def summarize_segment_survival(
    raw_voxel_segment: np.ndarray,
    cleaned_voxel_segment: np.ndarray,
    source_segments: list[ObjSegment],
) -> dict[str, Any]:
    raw_counts = {
        int(segment_id): int(np.count_nonzero(raw_voxel_segment == segment_id))
        for segment_id in np.unique(raw_voxel_segment)
        if segment_id > 0
    }
    clean_ids = [int(segment_id) for segment_id in np.unique(cleaned_voxel_segment) if segment_id > 0]
    source_count = max(len(source_segments), len(raw_counts))
    surviving_count = len(clean_ids)
    preservation_fraction = min((surviving_count / source_count) if source_count else 1.0, 1.0)
    missing_count = max(source_count - surviving_count, 0)
    status = "pass" if missing_count == 0 or preservation_fraction >= 0.75 else "review"
    return {
        "status": status,
        "source_segment_count": int(source_count),
        "surviving_segment_count": int(surviving_count),
        "preservation_fraction": round(float(preservation_fraction), 4),
        "missing_segment_count": int(missing_count),
        "raw_counts": raw_counts,
        "clean_segment_ids": clean_ids,
        "recommended_next_voxel_size": 32 if cleaned_voxel_segment.shape[0] < 32 and status != "pass" else None,
    }


def load_obj_segments(path: Path) -> tuple[np.ndarray, list[ObjSegment]]:
    vertices: list[list[float]] = []
    segments: list[ObjSegment] = []
    current_name = "segment_1"
    current_faces: list[list[int]] = []

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("o ") or line.startswith("g "):
            if current_faces:
                segments.append(ObjSegment(len(segments) + 1, current_name, current_faces))
                current_faces = []
            current_name = line.split(" ", 1)[1].strip() or f"segment_{len(segments) + 1}"
        elif line.startswith("v "):
            parts = line.split()
            if len(parts) >= 4:
                vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
        elif line.startswith("f "):
            indices = []
            for part in line.split()[1:]:
                try:
                    indices.append(int(part.split("/")[0]) - 1)
                except ValueError:
                    pass
            if len(indices) >= 3:
                for i in range(1, len(indices) - 1):
                    current_faces.append([indices[0], indices[i], indices[i + 1]])

    if current_faces:
        segments.append(ObjSegment(len(segments) + 1, current_name, current_faces))
    if not segments and vertices:
        segments.append(ObjSegment(1, "root", []))
    return np.asarray(vertices, dtype=float), segments


def segment_label_lookup(segment_rows: list[dict[str, Any]] | None) -> dict[int, str]:
    lookup: dict[int, str] = {}
    for row in segment_rows or []:
        try:
            segment_id = int(row.get("segment_id", len(lookup) + 1))
        except (TypeError, ValueError):
            continue
        label = str(row.get("label") or row.get("source_name") or f"segment_{segment_id}")
        lookup[segment_id] = label.replace("_", " ")
    return lookup


def remap_coarsened_segment_labels(
    segment_rows: list[dict[str, Any]] | None,
    voxel_segment: np.ndarray,
    movement_intents: list[dict[str, Any]],
) -> dict[int, str]:
    """Assign teacher-facing labels to the merged voxel regions.

    Coarsening intentionally renumbers Bang regions after merging. The old
    segment IDs no longer describe the physical regions, so reuse the desired
    labels but place them by geometry: the largest region is usually the stable
    body/core, and the smallest visible region is usually the moving feature.
    """
    ids = [int(value) for value in np.unique(voxel_segment) if value > 0]
    if not ids:
        return segment_label_lookup(segment_rows)

    counts = {sid: int(np.count_nonzero(voxel_segment == sid)) for sid in ids}
    available_ids = set(ids)
    labels = [clean_segment_label(row) for row in segment_rows or []]
    labels = [label for label in labels if label]
    if not labels:
        return {sid: f"segment {sid}" for sid in ids}

    assigned: dict[int, str] = {}
    body_label = first_label_matching(labels, ["body", "fuselage", "core", "shell", "frame", "structure"])
    if body_label:
        body_id = max(available_ids, key=lambda sid: (counts[sid], -sid))
        assigned[body_id] = body_label
        available_ids.remove(body_id)

    moving_labels = [str(item.get("part_name") or item.get("label") or "").replace("_", " ").strip() for item in movement_intents]
    moving_label = first_label_matching(labels, significant_words(moving_labels)) or first_label_matching(
        labels,
        ["propeller", "wheel", "axle", "door", "spinner", "rotor", "moving"],
    )
    if moving_label and available_ids:
        moving_id = min(available_ids, key=lambda sid: (counts[sid], sid))
        assigned[moving_id] = moving_label
        available_ids.remove(moving_id)

    remaining_labels = [label for label in labels if label not in assigned.values()]
    for sid, label in zip(sorted(available_ids), remaining_labels):
        assigned[sid] = label

    for sid in ids:
        assigned.setdefault(sid, f"segment {sid}")
    return assigned


def clean_segment_label(row: dict[str, Any]) -> str:
    return str(row.get("label") or row.get("source_name") or "").replace("_", " ").strip()


def significant_words(values: list[str]) -> list[str]:
    words: list[str] = []
    for value in values:
        for token in re_slug(value).split("_"):
            if len(token) > 2:
                words.append(token)
    return words


def first_label_matching(labels: list[str], tokens: list[str]) -> str | None:
    token_set = [token.lower() for token in tokens if token]
    for label in labels:
        haystack = label.lower()
        if any(token in haystack for token in token_set):
            return label
    return None


def infer_connector_sites(
    movement_intents: list[dict[str, Any]],
    segment_rows: list[dict[str, Any]],
    segment_lookup: dict[int, str],
    contacts: dict[tuple[int, int], list[dict[str, Any]]],
    teacher_connection_intent: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for intent in movement_intents:
        movement = str(intent.get("movement", "static")).strip().lower()
        if movement == "static":
            continue
        part_name = str(intent.get("part_name") or intent.get("label") or "moving part").strip()
        matched_segments = match_segments_for_part(part_name, segment_rows, segment_lookup)
        contact = best_contact_for_segments(matched_segments, contacts)
        connector_type = connector_type_for_movement(movement)
        if contact:
            segments = [int(contact["segment_a"]), int(contact["segment_b"])]
            candidates.append(
                {
                    "part_name": part_name,
                    "movement": movement,
                    "connector_type": connector_type,
                    "segments": segments,
                    "status": "candidate",
                    "contact_count": contact["contact_count"],
                    "centroid": contact["centroid"],
                    "normal": contact["normal"],
                    "teacher_intent": teacher_connection_intent,
                    "instruction": connector_instruction(part_name, movement, connector_type, "candidate"),
                }
            )
        else:
            candidates.append(
                {
                    "part_name": part_name,
                    "movement": movement,
                    "connector_type": connector_type,
                    "segments": matched_segments,
                    "status": "needs_teacher_review",
                    "contact_count": 0,
                    "centroid": None,
                    "normal": None,
                    "teacher_intent": teacher_connection_intent,
                    "instruction": connector_instruction(part_name, movement, connector_type, "needs_teacher_review"),
                }
            )
    return candidates


def match_segments_for_part(
    part_name: str,
    segment_rows: list[dict[str, Any]],
    segment_lookup: dict[int, str],
) -> list[int]:
    tokens = significant_tokens(part_name)
    matches: list[int] = []
    for row in segment_rows:
        try:
            segment_id = int(row.get("segment_id"))
        except (TypeError, ValueError):
            continue
        haystack = " ".join(
            [
                str(row.get("label", "")),
                str(row.get("source_name", "")),
                segment_lookup.get(segment_id, ""),
            ]
        ).lower()
        if any(token in haystack for token in tokens):
            matches.append(segment_id)
    return sorted(set(matches))


def significant_tokens(value: str) -> list[str]:
    tokens = [token for token in re_slug(value).split("_") if len(token) > 2]
    return tokens or [value.strip().lower()]


def re_slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def best_contact_for_segments(
    segment_ids: list[int],
    contacts: dict[tuple[int, int], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    if not segment_ids:
        return None
    segment_set = set(segment_ids)
    ranked: list[dict[str, Any]] = []
    for (a, b), rows in contacts.items():
        if a not in segment_set and b not in segment_set:
            continue
        points = [row["voxel_a"] for row in rows] + [row["voxel_b"] for row in rows]
        normals = [row["normal"] for row in rows if row.get("normal") is not None]
        centroid = np.mean(np.asarray(points, dtype=float), axis=0).round(2).tolist() if points else None
        normal = np.mean(np.asarray(normals, dtype=float), axis=0).round(2).tolist() if normals else None
        ranked.append(
            {
                "segment_a": int(a),
                "segment_b": int(b),
                "contact_count": len(rows),
                "centroid": centroid,
                "normal": normal,
            }
        )
    if not ranked:
        return None
    return sorted(ranked, key=lambda row: row["contact_count"], reverse=True)[0]


def connector_type_for_movement(movement: str) -> str:
    if movement == "spinning":
        return "axle_rotation"
    if movement == "rolling":
        return "wheel_axle"
    if movement == "pivoting":
        return "hinge_connector"
    if movement == "sliding":
        return "slider_connector"
    return "static_snap"


def connector_instruction(part_name: str, movement: str, connector_type: str, status: str) -> str:
    connector_label = connector_type.replace("_", " ")
    if status == "candidate":
        return (
            f"Use a {connector_label} at the detected contact surface for {part_name} "
            f"so the part can support {movement} motion."
        )
    return (
        f"Teacher must confirm where the {connector_label} should attach for {part_name}; "
        f"the segmented model did not expose a clear {movement} contact surface."
    )


def summarize_contacts(contacts: dict[tuple[int, int], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    for (a, b), values in sorted(contacts.items()):
        rows.append({"segment_a": int(a), "segment_b": int(b), "contact_count": len(values)})
    return rows


def obj_to_voxel_with_segments(vertices: np.ndarray, segments: list[ObjSegment], voxel_size: int) -> np.ndarray:
    voxel = np.zeros((voxel_size, voxel_size, voxel_size), dtype=np.int16)
    if len(vertices) == 0:
        return voxel

    min_bound = vertices.min(axis=0)
    max_bound = vertices.max(axis=0)
    scale = max(float((max_bound - min_bound).max()), 1e-6)
    normalized = (vertices - min_bound) / scale
    normalized = np.clip(normalized * (voxel_size - 1), 0, voxel_size - 1)

    for segment in segments:
        for face in segment.faces:
            tri = normalized[np.asarray(face)]
            for point in sample_triangle(tri, samples=18):
                idx = np.clip(np.rint(point).astype(int), 0, voxel_size - 1)
                voxel[idx[0], idx[1], idx[2]] = segment.segment_id
    return voxel


def sample_triangle(tri: np.ndarray, samples: int) -> list[np.ndarray]:
    points = [tri[0], tri[1], tri[2], tri.mean(axis=0)]
    grid = max(2, int(math.sqrt(samples)))
    for i in range(grid + 1):
        for j in range(grid + 1 - i):
            a = i / grid
            b = j / grid
            c = 1.0 - a - b
            points.append(a * tri[0] + b * tri[1] + c * tri[2])
    return points


def enforce_2x2_footprint(voxel_matrix: np.ndarray) -> np.ndarray:
    sx, sy, sz = voxel_matrix.shape
    snapped = np.zeros_like(voxel_matrix)
    for x in range(0, sx - 1, 2):
        for y in range(0, sy - 1, 2):
            block = voxel_matrix[x : x + 2, y : y + 2, :]
            mask = np.any(block > 0, axis=(0, 1))
            for z in np.where(mask)[0]:
                vals = block[:, :, z].flatten()
                vals = vals[vals > 0]
                if len(vals):
                    snapped[x : x + 2, y : y + 2, z] = Counter(vals).most_common(1)[0][0]
    return snapped


def clean_vertical_columns(voxel_matrix: np.ndarray) -> np.ndarray:
    cleaned = voxel_matrix.copy()
    sx, sy, _ = cleaned.shape
    for x in range(sx):
        for y in range(sy):
            filled = np.where(cleaned[x, y, :] > 0)[0]
            if len(filled) == 1:
                cleaned[x, y, filled[0]] = 0
    return cleaned


def split_segment_connected_components(voxel_segment: np.ndarray) -> np.ndarray:
    sx, sy, sz = voxel_segment.shape
    new_seg = np.zeros_like(voxel_segment)
    visited = np.zeros_like(voxel_segment, dtype=bool)
    directions = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
    new_id = 1
    for x in range(sx):
        for y in range(sy):
            for z in range(sz):
                if visited[x, y, z] or voxel_segment[x, y, z] <= 0:
                    continue
                source_id = voxel_segment[x, y, z]
                queue = [(x, y, z)]
                visited[x, y, z] = True
                component = []
                while queue:
                    cx, cy, cz = queue.pop()
                    component.append((cx, cy, cz))
                    for dx, dy, dz in directions:
                        nx, ny, nz = cx + dx, cy + dy, cz + dz
                        if 0 <= nx < sx and 0 <= ny < sy and 0 <= nz < sz:
                            if not visited[nx, ny, nz] and voxel_segment[nx, ny, nz] == source_id:
                                visited[nx, ny, nz] = True
                                queue.append((nx, ny, nz))
                for cx, cy, cz in component:
                    new_seg[cx, cy, cz] = new_id
                new_id += 1
    return new_seg


def compute_segment_adjacency(voxel_segment: np.ndarray) -> dict[int, list[int]]:
    adjacency: dict[int, set[int]] = defaultdict(set)
    sx, sy, sz = voxel_segment.shape
    for x in range(sx):
        for y in range(sy):
            for z in range(sz):
                current = int(voxel_segment[x, y, z])
                if current <= 0:
                    continue
                for dx, dy, dz in [(1, 0, 0), (0, 1, 0), (0, 0, 1)]:
                    nx, ny, nz = x + dx, y + dy, z + dz
                    if nx >= sx or ny >= sy or nz >= sz:
                        continue
                    other = int(voxel_segment[nx, ny, nz])
                    if other > 0 and other != current:
                        adjacency[current].add(other)
                        adjacency[other].add(current)
    return {key: sorted(values) for key, values in adjacency.items()}


def render_segment_visualization(voxel_segment: np.ndarray, path: Path) -> None:
    fig = plt.figure(figsize=(7, 7))
    ax = fig.add_subplot(111, projection="3d")
    colors = segment_facecolors(voxel_segment)
    ax.voxels(voxel_segment > 0, facecolors=colors, edgecolor="none", alpha=0.95)
    ax.set_title("Segment Visualization", fontsize=18)
    ax.set_box_aspect([1, 1, 1])
    ax.view_init(elev=25, azim=45)
    _set_bounds(ax, voxel_segment.shape[0])
    fig.savefig(path, bbox_inches="tight", dpi=150)
    plt.close(fig)


def render_segment_multiview(voxel_segment: np.ndarray, adjacency: dict[int, list[int]], path: Path) -> None:
    views = [
        ("front", 0, 90),
        ("back", 0, 270),
        ("left", 0, 180),
        ("right", 0, 0),
        ("top", 90, 0),
        ("bottom", -90, 0),
        ("iso_1", 25, 45),
        ("iso_2", 25, 135),
    ]
    fig = plt.figure(figsize=(16, 9))
    for idx, (title, elev, azim) in enumerate(views, start=1):
        ax = fig.add_subplot(3, 4, idx, projection="3d")
        ax.voxels(voxel_segment > 0, facecolors=segment_facecolors(voxel_segment), edgecolor="none", alpha=1.0)
        ax.set_title(title)
        ax.view_init(elev=elev, azim=azim)
        ax.set_axis_off()
        ax.set_box_aspect([1, 1, 1])
        _set_bounds(ax, voxel_segment.shape[0])
    ax = fig.add_subplot(3, 4, 9)
    ax.axis("off")
    ax.set_title("legend")
    unique = [int(x) for x in np.unique(voxel_segment) if x > 0]
    for i, sid in enumerate(unique[:10]):
        color = PALETTE[(sid - 1) % len(PALETTE)] / 255.0
        ax.add_patch(plt.Rectangle((0.05, 0.9 - i * 0.08), 0.06, 0.04, color=color))
        ax.text(0.14, 0.9 - i * 0.08, f"Segment {sid}", transform=ax.transAxes, fontsize=9)
    fig.savefig(path, bbox_inches="tight", dpi=140)
    plt.close(fig)


def segment_facecolors(voxel_segment: np.ndarray) -> np.ndarray:
    colors = np.zeros(voxel_segment.shape + (4,), dtype=float)
    for sid in [int(x) for x in np.unique(voxel_segment) if x > 0]:
        colors[voxel_segment == sid] = np.append(PALETTE[(sid - 1) % len(PALETTE)] / 255.0, 1.0)
    return colors


def voxel_to_blocks(voxel_segment: np.ndarray) -> list[BrickBlock]:
    blocks: list[BrickBlock] = []
    block_id = 1
    sx, sy, sz = voxel_segment.shape
    for x in range(0, sx - 1, 2):
        for y in range(0, sy - 1, 2):
            filled = np.where(np.any(voxel_segment[x : x + 2, y : y + 2, :] > 0, axis=(0, 1)))[0]
            if len(filled) == 0:
                continue
            runs = split_runs(filled)
            for z0, z1 in runs:
                height = max(2, min(4, z1 - z0 + 1))
                segment_vals = voxel_segment[x : x + 2, y : y + 2, z0 : z0 + height].flatten()
                segment_vals = segment_vals[segment_vals > 0]
                segment_id = int(Counter(segment_vals).most_common(1)[0][0]) if len(segment_vals) else 1
                blocks.append(BrickBlock(block_id, (x, y, int(z0)), (2, 2, height), segment_id))
                block_id += 1
    return blocks


def split_runs(values: np.ndarray) -> list[tuple[int, int]]:
    runs = []
    start = prev = int(values[0])
    for value in values[1:]:
        value = int(value)
        if value != prev + 1:
            runs.append((start, prev))
            start = value
        prev = value
    runs.append((start, prev))
    return runs


def render_blocks(blocks: list[BrickBlock], grid_size: int, path: Path, title: str) -> None:
    fig = plt.figure(figsize=(9, 7))
    ax = fig.add_subplot(111, projection="3d")
    draw_blocks(ax, blocks, alpha=0.75)
    ax.set_title(title, fontsize=16)
    ax.set_box_aspect([1, 1, 0.8])
    ax.view_init(elev=25, azim=45)
    _set_bounds(ax, grid_size)
    fig.savefig(path, bbox_inches="tight", dpi=150)
    plt.close(fig)


def generate_row_steps(blocks: list[BrickBlock], max_steps: int = 8) -> list[list[BrickBlock]]:
    row_map: dict[int, list[BrickBlock]] = defaultdict(list)
    for block in blocks:
        row_map[block.position[1]].append(block)
    rows = [row_map[key] for key in sorted(row_map)]
    if len(rows) <= max_steps:
        return rows
    chunk_size = math.ceil(len(rows) / max_steps)
    return [sum(rows[i : i + chunk_size], []) for i in range(0, len(rows), chunk_size)]


def render_instruction_step(
    previous_blocks: list[BrickBlock],
    step_blocks: list[BrickBlock],
    grid_size: int,
    path: Path,
    step_number: int,
) -> None:
    fig = plt.figure(figsize=(9, 7))
    ax = fig.add_subplot(111, projection="3d")
    draw_blocks(ax, previous_blocks, alpha=0.15)
    draw_blocks(ax, step_blocks, alpha=0.85)
    ax.set_title(f"Notebook Assembly Step {step_number}", fontsize=16)
    ax.set_box_aspect([1, 1, 0.8])
    ax.view_init(elev=25, azim=45)
    _set_bounds(ax, grid_size)
    fig.savefig(path, bbox_inches="tight", dpi=150)
    plt.close(fig)


def render_instruction_multiview(
    previous_blocks: list[BrickBlock],
    step_blocks: list[BrickBlock],
    grid_size: int,
    path: Path,
    step_number: int,
) -> None:
    """Render notebook-style placement views for one assembly step.

    This mirrors the original notebook's front/back/left/right/top/bottom/iso
    diagnostic sheet, but applies it to the current build step: previously
    placed blocks are faded, and the newly added blocks are saturated.
    """

    views = [
        ("front", 0, 90),
        ("back", 0, 270),
        ("left", 0, 180),
        ("right", 0, 0),
        ("top", 90, 0),
        ("bottom", -90, 0),
        ("iso_1", 25, 45),
        ("iso_2", 25, 135),
    ]
    fig = plt.figure(figsize=(16, 9))
    for idx, (title, elev, azim) in enumerate(views, start=1):
        ax = fig.add_subplot(3, 4, idx, projection="3d")
        draw_blocks(ax, previous_blocks, alpha=0.12)
        draw_blocks(ax, step_blocks, alpha=0.92)
        ax.set_title(title)
        ax.view_init(elev=elev, azim=azim)
        ax.set_axis_off()
        ax.set_box_aspect([1, 1, 0.8])
        _set_bounds(ax, grid_size)

    legend = fig.add_subplot(3, 4, 9)
    legend.axis("off")
    legend.set_title(f"step {step_number} pieces")
    step_segments = [block.segment_id for block in step_blocks]
    for i, sid in enumerate(sorted(set(step_segments))[:10]):
        color = PALETTE[(sid - 1) % len(PALETTE)] / 255.0
        count = step_segments.count(sid)
        legend.add_patch(plt.Rectangle((0.05, 0.9 - i * 0.08), 0.06, 0.04, color=color))
        legend.text(0.14, 0.9 - i * 0.08, f"Segment {sid}: {count} block(s)", transform=legend.transAxes, fontsize=9)

    fig.suptitle(f"Notebook Assembly Step {step_number} - Multiview Placement", fontsize=18)
    fig.savefig(path, bbox_inches="tight", dpi=140)
    plt.close(fig)


def describe_instruction_step(
    step_number: int,
    image_path: Path,
    step_blocks: list[BrickBlock],
    previous_blocks: list[BrickBlock],
    segment_lookup: dict[int, str],
    artifact_label: str,
) -> dict[str, Any]:
    segment_ids = sorted({block.segment_id for block in step_blocks})
    segment_labels = [segment_lookup.get(segment_id, f"segment {segment_id}") for segment_id in segment_ids]
    label_text = natural_join(segment_labels) if segment_labels else "the next section"
    inventory = block_inventory_summary(step_blocks)
    piece_text = inventory_sentence(inventory)
    new_count = len(step_blocks)
    built_count = len(previous_blocks) + new_count

    return {
        "step_number": step_number,
        "title": f"Build {label_text}",
        "image_path": str(image_path),
        "segments": segment_ids,
        "segment_labels": segment_labels,
        "new_block_count": new_count,
        "cumulative_block_count": built_count,
        "inventory": inventory,
        "teacher_instruction": (
            f"Add {new_count} block{'s' if new_count != 1 else ''} for {label_text}. "
            f"Use the highlighted blocks to extend the {artifact_label}; the faded blocks show what should already be built."
        ),
        "student_instruction": (
            f"Find {piece_text}. Put the bright pieces on the model so it matches the picture, "
            "then check that the shape still looks like the target build."
        ),
        "teacher_check": (
            "Confirm the pieces look like physical BrickSmart blocks, connect to the previous step, "
            "and preserve the intended segment shape before moving on."
        ),
    }


def draw_blocks(ax: Any, blocks: list[BrickBlock], alpha: float) -> None:
    for block in blocks:
        x, y, z = block.position
        dx, dy, dz = block.size
        color = PALETTE[(block.segment_id - 1) % len(PALETTE)] / 255.0
        ax.bar3d(x, y, z, dx, dy, dz, color=color, edgecolor="black", alpha=alpha, linewidth=0.5)
        add_studs(ax, block, color, alpha)


def add_studs(ax: Any, block: BrickBlock, color: np.ndarray, alpha: float) -> None:
    x, y, z = block.position
    dx, dy, dz = block.size
    stud_z = z + dz + 0.04
    for sx in range(x, x + dx, 1):
        for sy in range(y, y + dy, 1):
            ax.bar3d(sx + 0.25, sy + 0.25, stud_z, 0.5, 0.5, 0.18, color=color, edgecolor="black", alpha=alpha)


def block_inventory_summary(blocks: list[BrickBlock]) -> list[dict[str, Any]]:
    counts = Counter(block.size for block in blocks)
    return [
        {"piece": f"{size[0]}x{size[1]}x{size[2]} block", "quantity": count}
        for size, count in sorted(counts.items())
    ]


def inventory_sentence(inventory: list[dict[str, Any]]) -> str:
    if not inventory:
        return "the next pieces"
    pieces = []
    for item in inventory:
        quantity = int(item["quantity"])
        piece = str(item["piece"])
        if quantity != 1 and piece.endswith("block"):
            piece = f"{piece}s"
        pieces.append(f"{quantity} x {piece}")
    return natural_join(pieces)


def natural_join(values: list[str]) -> str:
    clean = [value for value in values if value]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} and {clean[1]}"
    return f"{', '.join(clean[:-1])}, and {clean[-1]}"


def _set_bounds(ax: Any, grid_size: int) -> None:
    ax.set_xlim(0, grid_size)
    ax.set_ylim(0, grid_size)
    ax.set_zlim(0, grid_size)


def _write_manifest(output_dir: Path, manifest: dict[str, Any]) -> None:
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
