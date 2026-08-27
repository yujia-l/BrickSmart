#!/usr/bin/env python3
"""Generate a self-contained BrickSmart build-equivalence HTML report.

This tool compares a reviewed regression baseline with artifacts from a fresh
candidate run. It is intentionally release/test tooling rather than production
planner code.

Typical usage from the repository root::

    PYTHONPATH=backend python tools/verification/generate_build_equivalence_report.py \
        --baseline-dir tests/regression/bird/expected \
        --candidate-dir .test-runs/bird-live-check/artifacts \
        --baseline-player docs/examples/bird_build_instructions.html \
        --candidate-player .test-runs/bird-live-check/artifacts/visualizations/proper_complete_build_steps.html \
        --catalog block_catalog/block_definitions.csv \
        --baseline-label "v1.2.1 accepted baseline" \
        --candidate-label "v1.2.2 refactored build" \
        --model-name "reference bird" \
        --output release/verification/reports/bird_build_equivalence.html

The report is always written. By default, the command exits with status 2 when
an equivalence check fails, which makes it suitable for CI. Pass
``--allow-differences`` to generate an investigative report without failing.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd


CANONICAL_ARTIFACTS: tuple[str, ...] = (
    "complete_build_steps.csv",
    "display_block_family_counts.json",
    "inventory_validation.json",
    "segment_connector_assembly_steps.csv",
    "segment_connector_final_summary.json",
    "segment_connector_functional_final_blocks.csv",
    "segment_subassembly_blocks.csv",
    "structural_assembly_graph.csv",
    "subassembly_build_steps.csv",
    "true_complete_build_steps.csv",
)

FINAL_BLOCKS_FILE = "segment_connector_functional_final_blocks.csv"
TRUE_TIMELINE_FILE = "true_complete_build_steps.csv"
FINAL_SUMMARY_FILE = "segment_connector_final_summary.json"
INVENTORY_FILE = "inventory_validation.json"

PLACEMENT_COLUMNS: tuple[str, ...] = (
    "block_id",
    "block_role",
    "block_family",
    "position",
    "size",
    "rotation",
    "source_segment_id",
    "interface_id",
    "physical_target_id",
)

TIMELINE_COLUMNS: tuple[str, ...] = (
    "global_step",
    "phase",
    "title",
    "instruction",
    "visible_block_ids",
    "final_position_segment_ids",
    "interface_id",
)

# Paths in regression summaries are machine-specific and should not make a
# behavior-preserving refactor look different. Only path-valued fields are
# normalized; all behavioral values remain exact.
PATH_KEYS = {
    "catalog_csv",
    "catalog_path",
    "context_path",
    "input_path",
    "legacy_player_html",
    "output_dir",
    "output_html",
    "source_model",
    "timeline_csv",
}
PATH_MARKERS: tuple[str, ...] = (
    "/block_catalog/",
    "/config/",
    "/model_registry/",
    "/model_store/",
    "/tests/",
    "/examples/",
    "/docs/",
    "/release/",
)

DEFAULT_COLORS: Mapping[str, str] = {
    "standard_2x2x2": "#3678e2",
    "standard_2x3x2": "#1fb556",
    "standard_2x4x2": "#e2b21f",
    "rotation_block": "#8b5cf6",
    "hinge_block": "#ec4899",
    "big_wheel": "#dc2626",
    "small_wheel": "#dc2626",
    "angle_joint": "#ef4444",
    "angle_symmetrical": "#f97316",
    "feature_beam_3x1x1": "#374151",
    "feature_beam_7x1x1": "#374151",
    "feature_beam_curved": "#ef4444",
    "bucket": "#22c55e",
    "bucket_arms": "#ef4444",
}

CSS_COLOR_MAP: Mapping[str, str] = {
    "black": "#111827",
    "blue": "#3678e2",
    "brown": "#92400e",
    "cyan": "#06b6d4",
    "gray": "#6b7280",
    "green": "#1fb556",
    "grey": "#6b7280",
    "orange": "#f97316",
    "pink": "#ec4899",
    "purple": "#8b5cf6",
    "red": "#dc2626",
    "white": "#f8fafc",
    "yellow": "#e2b21f",
}


@dataclass(frozen=True)
class BuildMetrics:
    final_claim_valid: bool
    final_block_count: int
    true_build_step_count: int
    structural_segment_count: int
    direct_structural_join_count: int
    inventory_recount: Mapping[str, int]
    deterministic: bool | None
    runtime_llm_used: bool | None
    symmetry_complete: bool | None
    collision_free: bool | None


@dataclass(frozen=True)
class ArtifactComparison:
    filename: str
    status: str
    equivalent: bool
    baseline_sha256: str | None
    candidate_sha256: str | None
    detail: str


@dataclass(frozen=True)
class ReportResult:
    equivalent: bool
    output_path: Path
    artifact_comparisons: tuple[ArtifactComparison, ...]
    placement_equal: bool
    timeline_equal: bool
    metrics_equal: bool
    player_equal: bool | None


def sha256_file(path: Path) -> str:
    """Compute SHA-256 for file.
    
    :param path: Filesystem path used by the operation.
    :type path: Path
    :returns: The result produced by the function.
    :rtype: str
    """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    """Read json.
    
    :param path: Filesystem path used by the operation.
    :type path: Path
    :returns: The loaded data.
    :rtype: Any
    """
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_path_string(value: str) -> str:
    """Normalize path string.
    
    :param value: Value used by the operation.
    :type value: str
    :returns: The computed result.
    :rtype: str
    """
    normalized = value.replace("\\", "/")
    if normalized.startswith("<project-root>/"):
        return normalized
    for marker in PATH_MARKERS:
        marker_index = normalized.find(marker)
        if marker_index >= 0:
            return "<project-root>" + normalized[marker_index:]
    return normalized


def normalize_json(value: Any, *, key: str | None = None) -> Any:
    """Normalize only machine-specific path values for semantic comparison."""
    if isinstance(value, dict):
        return {
            str(child_key): normalize_json(child_value, key=str(child_key))
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [normalize_json(item, key=key) for item in value]
    if isinstance(value, str) and (key in PATH_KEYS or key and key.endswith("_path")):
        return _normalize_path_string(value)
    return value


def _normalize_scalar(value: Any) -> Any:
    """Normalize scalar.
    
    :param value: Value used by the operation.
    :type value: Any
    :returns: The computed result.
    :rtype: Any
    """
    if pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def canonical_dataframe(path: Path, columns: Sequence[str] | None = None) -> list[dict[str, Any]]:
    """Return canonical dataframe.
    
    :param path: Filesystem path used by the operation.
    :type path: Path
    :param columns: The columns value.
    :type columns: Sequence[str] | None
    :returns: The result produced by the function.
    :rtype: list[dict[str, Any]]
    """
    frame = pd.read_csv(path, keep_default_na=True)
    if columns is not None:
        missing = [column for column in columns if column not in frame.columns]
        if missing:
            raise ValueError(f"{path} is missing required columns: {missing}")
        frame = frame[list(columns)]
    sort_columns = [
        column
        for column in ("block_id", "global_step", "assembly_step", "interface_id")
        if column in frame.columns
    ]
    if sort_columns:
        frame = frame.sort_values(sort_columns, kind="stable", na_position="last")
    records: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        records.append({key: _normalize_scalar(value) for key, value in row.items()})
    return records


def compare_artifact(filename: str, baseline_dir: Path, candidate_dir: Path) -> ArtifactComparison:
    """Compare artifact.
    
    :param filename: The filename value.
    :type filename: str
    :param baseline_dir: Directory for baseline artifacts.
    :type baseline_dir: Path
    :param candidate_dir: Directory for candidate artifacts.
    :type candidate_dir: Path
    :returns: The result produced by the function.
    :rtype: ArtifactComparison
    """
    baseline = baseline_dir / filename
    candidate = candidate_dir / filename
    if not baseline.is_file() or not candidate.is_file():
        missing = []
        if not baseline.is_file():
            missing.append("baseline")
        if not candidate.is_file():
            missing.append("candidate")
        return ArtifactComparison(
            filename=filename,
            status="Missing",
            equivalent=False,
            baseline_sha256=sha256_file(baseline) if baseline.is_file() else None,
            candidate_sha256=sha256_file(candidate) if candidate.is_file() else None,
            detail=f"Missing from {', '.join(missing)} artifact directory",
        )

    baseline_hash = sha256_file(baseline)
    candidate_hash = sha256_file(candidate)
    if baseline_hash == candidate_hash:
        return ArtifactComparison(
            filename=filename,
            status="Exact byte match",
            equivalent=True,
            baseline_sha256=baseline_hash,
            candidate_sha256=candidate_hash,
            detail="Files are byte-for-byte identical",
        )

    suffix = baseline.suffix.lower()
    try:
        if suffix == ".json":
            baseline_json = normalize_json(read_json(baseline))
            candidate_json = normalize_json(read_json(candidate))
            if baseline_json == candidate_json:
                return ArtifactComparison(
                    filename=filename,
                    status="Path-normalized match",
                    equivalent=True,
                    baseline_sha256=baseline_hash,
                    candidate_sha256=candidate_hash,
                    detail="Behavioral JSON matches after normalizing machine-specific paths",
                )
        elif suffix == ".csv":
            if canonical_dataframe(baseline) == canonical_dataframe(candidate):
                return ArtifactComparison(
                    filename=filename,
                    status="Semantic CSV match",
                    equivalent=True,
                    baseline_sha256=baseline_hash,
                    candidate_sha256=candidate_hash,
                    detail="Rows and values match after canonical parsing",
                )
    except (ValueError, TypeError, json.JSONDecodeError, pd.errors.ParserError) as exc:
        return ArtifactComparison(
            filename=filename,
            status="Comparison error",
            equivalent=False,
            baseline_sha256=baseline_hash,
            candidate_sha256=candidate_hash,
            detail=str(exc),
        )

    return ArtifactComparison(
        filename=filename,
        status="Different",
        equivalent=False,
        baseline_sha256=baseline_hash,
        candidate_sha256=candidate_hash,
        detail="Artifact content differs",
    )


def load_metrics(output_dir: Path) -> BuildMetrics:
    """Load metrics.
    
    :param output_dir: Directory where generated artifacts are written.
    :type output_dir: Path
    :returns: The loaded data.
    :rtype: BuildMetrics
    """
    final_blocks_path = output_dir / FINAL_BLOCKS_FILE
    timeline_path = output_dir / TRUE_TIMELINE_FILE
    summary_path = output_dir / FINAL_SUMMARY_FILE
    inventory_path = output_dir / INVENTORY_FILE

    final_blocks = pd.read_csv(final_blocks_path)
    timeline = pd.read_csv(timeline_path)
    summary = read_json(summary_path)
    inventory = read_json(inventory_path)

    segment_count = summary.get("structural_segment_count")
    if segment_count is None:
        segment_count = int(final_blocks["source_segment_id"].dropna().nunique())

    return BuildMetrics(
        final_claim_valid=bool(summary.get("final_claim_valid", False)),
        final_block_count=int(summary.get("final_block_count", len(final_blocks))),
        true_build_step_count=int(len(timeline)),
        structural_segment_count=int(segment_count),
        direct_structural_join_count=int(summary.get("direct_structural_join_count", 0)),
        inventory_recount={
            str(key): int(value)
            for key, value in dict(inventory.get("recount") or {}).items()
        },
        deterministic=_optional_bool(summary, "deterministic_execution"),
        runtime_llm_used=_runtime_llm_used(summary),
        symmetry_complete=_optional_bool(summary, "combined_symmetry_complete"),
        collision_free=_optional_bool(summary, "collision_free"),
    )


def _optional_bool(mapping: Mapping[str, Any], key: str) -> bool | None:
    """Return optional bool.
    
    :param mapping: The mapping value.
    :type mapping: Mapping[str, Any]
    :param key: Key used for lookup or grouping.
    :type key: str
    :returns: The result produced by the function.
    :rtype: bool | None
    """
    value = mapping.get(key)
    return None if value is None else bool(value)


def _runtime_llm_used(summary: Mapping[str, Any]) -> bool | None:
    """Return the runtime llm used.
    
    :param summary: The summary value.
    :type summary: Mapping[str, Any]
    :returns: The result produced by the function.
    :rtype: bool | None
    """
    for key in ("runtime_llm_used", "llm_used", "used_runtime_llm"):
        if key in summary:
            return bool(summary[key])
    execution_mode = str(summary.get("execution_mode") or "").lower()
    if execution_mode:
        return "llm" in execution_mode and "no_llm" not in execution_mode
    return None


def metrics_equivalent(baseline: BuildMetrics, candidate: BuildMetrics) -> bool:
    # Environmental metadata such as whether a diagnostic explicitly recorded
    # deterministic execution may be absent in a compact baseline. Build-facing
    # results are the required equivalence contract.
    """Return whether metrics equivalent.
    
    :param baseline: The baseline value.
    :type baseline: BuildMetrics
    :param candidate: The candidate value.
    :type candidate: BuildMetrics
    :returns: The result produced by the function.
    :rtype: bool
    """
    return (
        baseline.final_claim_valid == candidate.final_claim_valid
        and baseline.final_block_count == candidate.final_block_count
        and baseline.true_build_step_count == candidate.true_build_step_count
        and baseline.structural_segment_count == candidate.structural_segment_count
        and baseline.direct_structural_join_count == candidate.direct_structural_join_count
        and dict(baseline.inventory_recount) == dict(candidate.inventory_recount)
    )


def parse_triplet(value: Any, *, field: str) -> tuple[float, float, float]:
    """Parse triplet.
    
    :param value: Value used by the operation.
    :type value: Any
    :param field: The field value.
    :type field: str
    :returns: The computed result.
    :rtype: tuple[float, float, float]
    """
    if isinstance(value, (list, tuple)):
        parsed = value
    else:
        try:
            parsed = ast.literal_eval(str(value))
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"Cannot parse {field} triplet from {value!r}") from exc
    if not isinstance(parsed, (list, tuple)) or len(parsed) != 3:
        raise ValueError(f"{field} must contain exactly three values: {value!r}")
    return tuple(float(component) for component in parsed)


def load_catalog_colors(catalog_path: Path | None) -> dict[str, str]:
    """Load catalog colors.
    
    :param catalog_path: Catalog file path used by the operation.
    :type catalog_path: Path | None
    :returns: The loaded data.
    :rtype: dict[str, str]
    """
    colors = dict(DEFAULT_COLORS)
    if catalog_path is None or not catalog_path.is_file():
        return colors
    catalog = pd.read_csv(catalog_path)
    if not {"block_family", "color"}.issubset(catalog.columns):
        return colors
    for row in catalog[["block_family", "color"]].dropna().to_dict(orient="records"):
        family = str(row["block_family"]).strip()
        raw_color = str(row["color"]).strip().lower()
        if not family:
            continue
        colors[family] = CSS_COLOR_MAP.get(raw_color, raw_color)
    return colors


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    """Convert hex to to rgb.
    
    :param color: The color value.
    :type color: str
    :returns: The result produced by the function.
    :rtype: tuple[int, int, int]
    """
    value = color.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(character * 2 for character in value)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        return (54, 120, 226)
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def shade(color: str, factor: float) -> str:
    """Compute shade for shade.
    
    :param color: The color value.
    :type color: str
    :param factor: The factor value.
    :type factor: float
    :returns: The result produced by the function.
    :rtype: str
    """
    red, green, blue = _hex_to_rgb(color)
    red = max(0, min(255, round(red * factor)))
    green = max(0, min(255, round(green * factor)))
    blue = max(0, min(255, round(blue * factor)))
    return f"#{red:02x}{green:02x}{blue:02x}"


def _project(point: tuple[float, float, float]) -> tuple[float, float]:
    """Project project.
    
    :param point: The point value.
    :type point: tuple[float, float, float]
    :returns: The result produced by the function.
    :rtype: tuple[float, float]
    """
    x, y, z = point
    return ((x - y) * 1.0, (x + y) * 0.48 - z * 1.0)


def _cuboid_faces(
    position: tuple[float, float, float],
    size: tuple[float, float, float],
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int, int]]]:
    """Return cuboid faces.
    
    :param position: The position value.
    :type position: tuple[float, float, float]
    :param size: The size value.
    :type size: tuple[float, float, float]
    :returns: The result produced by the function.
    :rtype: tuple[list[tuple[float, float, float]], list[tuple[int, int, int, int]]]
    """
    x, y, z = position
    dx, dy, dz = size
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
    # Three visible faces for the chosen camera direction.
    faces = [
        (1, 2, 6, 5),  # +X side
        (2, 3, 7, 6),  # +Y side
        (4, 5, 6, 7),  # top
    ]
    return vertices, faces


def render_isometric_svg(
    final_blocks_path: Path,
    *,
    label: str,
    colors: Mapping[str, str],
    width: int = 504,
    height: int = 343,
) -> str:
    """Render isometric svg.
    
    :param final_blocks_path: Path to the final blocks file.
    :type final_blocks_path: Path
    :param label: The label value.
    :type label: str
    :param colors: The colors value.
    :type colors: Mapping[str, str]
    :param width: The width value.
    :type width: int
    :param height: The height value.
    :type height: int
    :returns: The result produced by the function.
    :rtype: str
    """
    frame = pd.read_csv(final_blocks_path)
    blocks: list[dict[str, Any]] = []
    all_projected: list[tuple[float, float]] = []

    for row in frame.to_dict(orient="records"):
        position = parse_triplet(row["position"], field="position")
        size = parse_triplet(row["size"], field="size")
        vertices, faces = _cuboid_faces(position, size)
        projected = [_project(vertex) for vertex in vertices]
        all_projected.extend(projected)
        blocks.append(
            {
                "block_id": int(row["block_id"]),
                "block_family": str(row["block_family"]),
                "position": position,
                "size": size,
                "vertices": vertices,
                "faces": faces,
                "projected": projected,
                "depth": position[0] + position[1] + position[2] * 0.05,
            }
        )

    if not blocks:
        raise ValueError(f"No final blocks found in {final_blocks_path}")

    min_x = min(point[0] for point in all_projected)
    max_x = max(point[0] for point in all_projected)
    min_y = min(point[1] for point in all_projected)
    max_y = max(point[1] for point in all_projected)
    padding = 32.0
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    scale = min((width - 2 * padding) / span_x, (height - 2 * padding) / span_y)

    def screen(point: tuple[float, float]) -> tuple[float, float]:
        """Project coordinates onto the screen for screen.
        
        :param point: The point value.
        :type point: tuple[float, float]
        :returns: The result produced by the function.
        :rtype: tuple[float, float]
        """
        projected_x, projected_y = point
        x_value = padding + (projected_x - min_x) * scale
        y_value = padding + (projected_y - min_y) * scale
        return (x_value, y_value)

    face_factors = (0.78, 0.9, 1.18)
    polygons: list[str] = []
    for block in sorted(blocks, key=lambda item: (item["depth"], item["block_id"])):
        base_color = colors.get(block["block_family"], "#64748b")
        for face_index, face in enumerate(block["faces"]):
            points = [screen(block["projected"][vertex_index]) for vertex_index in face]
            points_text = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
            title = html.escape(
                f"Block {block['block_id']} — {block['block_family']}", quote=True
            )
            polygons.append(
                f'<polygon points="{points_text}" fill="{shade(base_color, face_factors[face_index])}" '
                f'stroke="#0f172a" stroke-width="1.2"><title>{title}</title></polygon>'
            )

    escaped_label = html.escape(label, quote=True)
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escaped_label} isometric block model" preserveAspectRatio="xMidYMid meet">'
        '<rect x="0" y="0" width="100%" height="100%" rx="14" fill="#f8fafc"/>'
        + "".join(polygons)
        + "</svg>"
    )


def _short_hash(value: str | None) -> str:
    """Return short hash.
    
    :param value: Value used by the operation.
    :type value: str | None
    :returns: The result produced by the function.
    :rtype: str
    """
    return "—" if value is None else value[:16] + "…"


def _yes_no(value: bool | None) -> str:
    """Format yes/no for no.
    
    :param value: Value used by the operation.
    :type value: bool | None
    :returns: The result produced by the function.
    :rtype: str
    """
    if value is None:
        return "not recorded"
    return "yes" if value else "no"


def _inventory_text(recount: Mapping[str, int]) -> str:
    """Return inventory text.
    
    :param recount: The recount value.
    :type recount: Mapping[str, int]
    :returns: The result produced by the function.
    :rtype: str
    """
    if not recount:
        return "No inventory recount recorded"
    return ", ".join(f"{family}: {count}" for family, count in sorted(recount.items()))


def _artifact_table(comparisons: Iterable[ArtifactComparison]) -> str:
    """Return artifact table.
    
    :param comparisons: The comparisons value.
    :type comparisons: Iterable[ArtifactComparison]
    :returns: The result produced by the function.
    :rtype: str
    """
    rows = []
    for comparison in comparisons:
        status_class = "pass" if comparison.equivalent else "fail"
        rows.append(
            "<tr>"
            f"<td><code>{html.escape(comparison.filename)}</code></td>"
            f'<td><span class="status {status_class}" title="{html.escape(comparison.detail, quote=True)}">'
            f"{html.escape(comparison.status)}</span></td>"
            f"<td><code>{_short_hash(comparison.baseline_sha256)}</code></td>"
            f"<td><code>{_short_hash(comparison.candidate_sha256)}</code></td>"
            "</tr>"
        )
    return "".join(rows)


def _extract_body(player_html: str) -> str:
    """Extract body.
    
    :param player_html: The player html value.
    :type player_html: str
    :returns: The result produced by the function.
    :rtype: str
    """
    match = re.search(r"<body[^>]*>(.*)</body>\s*</html>\s*$", player_html, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return player_html


def _extract_head_style(player_html: str) -> str:
    """Extract head style.
    
    :param player_html: The player html value.
    :type player_html: str
    :returns: The result produced by the function.
    :rtype: str
    """
    match = re.search(r"<head[^>]*>(.*?)</head>", player_html, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    head = match.group(1)
    styles = re.findall(r"<style[^>]*>.*?</style>", head, re.IGNORECASE | re.DOTALL)
    return "\n".join(styles)


def build_report_html(
    *,
    baseline_dir: Path,
    candidate_dir: Path,
    baseline_label: str,
    candidate_label: str,
    model_name: str,
    baseline_metrics: BuildMetrics,
    candidate_metrics: BuildMetrics,
    comparisons: Sequence[ArtifactComparison],
    placement_equal: bool,
    timeline_equal: bool,
    metrics_equal: bool,
    player_equal: bool | None,
    baseline_player_hash: str | None,
    candidate_player_hash: str | None,
    baseline_svg: str,
    candidate_svg: str,
    candidate_player_html: str | None,
) -> str:
    """Build report html.
    
    :param baseline_dir: Directory for baseline artifacts.
    :type baseline_dir: Path
    :param candidate_dir: Directory for candidate artifacts.
    :type candidate_dir: Path
    :param baseline_label: The baseline label value.
    :type baseline_label: str
    :param candidate_label: The candidate label value.
    :type candidate_label: str
    :param model_name: The model name value.
    :type model_name: str
    :param baseline_metrics: The baseline metrics value.
    :type baseline_metrics: BuildMetrics
    :param candidate_metrics: The candidate metrics value.
    :type candidate_metrics: BuildMetrics
    :param comparisons: The comparisons value.
    :type comparisons: Sequence[ArtifactComparison]
    :param placement_equal: The placement equal value.
    :type placement_equal: bool
    :param timeline_equal: The timeline equal value.
    :type timeline_equal: bool
    :param metrics_equal: The metrics equal value.
    :type metrics_equal: bool
    :param player_equal: The player equal value.
    :type player_equal: bool | None
    :param baseline_player_hash: The baseline player hash value.
    :type baseline_player_hash: str | None
    :param candidate_player_hash: The candidate player hash value.
    :type candidate_player_hash: str | None
    :param baseline_svg: The baseline svg value.
    :type baseline_svg: str
    :param candidate_svg: The candidate svg value.
    :type candidate_svg: str
    :param candidate_player_html: The candidate player html value.
    :type candidate_player_html: str | None
    :returns: The generated result.
    :rtype: str
    """
    equivalent = (
        all(comparison.equivalent for comparison in comparisons)
        and placement_equal
        and timeline_equal
        and metrics_equal
        and player_equal is not False
    )
    pass_text = "✓ PASS — equivalent build output" if equivalent else "✗ FAIL — build differences detected"
    pass_class = "equiv-pass" if equivalent else "equiv-fail"
    reviewed_player_statement = (
        "The interactive players also have the same complete SHA-256 digest."
        if player_equal is True
        else "No pre-refactor player was supplied, so player-byte identity was not evaluated."
        if player_equal is None
        else "The supplied interactive players have different SHA-256 digests."
    )
    player_hash_text = (
        candidate_player_hash or baseline_player_hash or "No player hash available"
    )

    player_section = ""
    player_styles = ""
    if candidate_player_html:
        player_styles = _extract_head_style(candidate_player_html)
        player_section = (
            '<div class="equiv-divider">Interactive build produced by candidate code</div>'
            "</section>"
            + _extract_body(candidate_player_html)
        )
    else:
        player_section = (
            '<section class="equiv-section"><h2>Interactive player</h2>'
            "<p>No candidate player HTML was supplied. The artifact comparison remains complete, "
            "but this report does not embed the interactive build.</p></section></section>"
        )

    report_css = """
<style id="equivalence-report-style">
  * { box-sizing: border-box; }
  body { margin:0; font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:#f3f4f6; color:#111827; }
  .equiv-wrap { max-width:1220px; margin:0 auto; padding:24px 12px 4px; color:#0f172a; }
  .equiv-hero { background:linear-gradient(135deg,#0f172a,#1e3a8a); color:#fff; border-radius:18px; padding:26px; box-shadow:0 12px 30px rgba(15,23,42,.22); }
  .equiv-kicker { margin:0 0 8px; font-size:.78rem; font-weight:800; letter-spacing:.12em; text-transform:uppercase; color:#bfdbfe; }
  .equiv-title { margin:0; font-size:clamp(1.65rem,4vw,2.65rem); line-height:1.08; }
  .equiv-sub { margin:12px 0 0; max-width:920px; color:#dbeafe; line-height:1.55; }
  .equiv-pass,.equiv-fail { display:inline-flex; align-items:center; gap:8px; margin-top:16px; padding:8px 13px; border-radius:999px; font-weight:900; }
  .equiv-pass { background:#dcfce7; color:#166534; }
  .equiv-fail { background:#fee2e2; color:#991b1b; }
  .equiv-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:16px 0; }
  .equiv-card,.equiv-section { background:#fff; border:1px solid #dbe3ef; border-radius:14px; box-shadow:0 4px 14px rgba(15,23,42,.06); }
  .equiv-card { padding:16px; }
  .equiv-card strong { display:block; font-size:1.7rem; line-height:1; color:#1d4ed8; }
  .equiv-card span { display:block; margin-top:7px; font-size:.83rem; color:#475569; font-weight:750; }
  .equiv-section { margin:16px 0; padding:20px; }
  .equiv-section h2 { margin:0 0 12px; font-size:1.25rem; }
  .equiv-section p { line-height:1.55; color:#334155; }
  .compare-grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  .compare-figure { margin:0; border:1px solid #dbe3ef; border-radius:14px; overflow:hidden; background:#f8fafc; }
  .compare-figure figcaption { padding:12px 14px; font-size:.9rem; font-weight:850; background:#eff6ff; border-bottom:1px solid #dbe3ef; }
  .compare-figure svg { display:block; width:100%; height:330px; }
  .equiv-table-wrap { overflow:auto; }
  .equiv-table { width:100%; border-collapse:collapse; font-size:.86rem; }
  .equiv-table th,.equiv-table td { padding:10px 12px; border-bottom:1px solid #e2e8f0; text-align:left; white-space:nowrap; }
  .equiv-table th { background:#f8fafc; color:#475569; font-size:.74rem; letter-spacing:.05em; text-transform:uppercase; }
  .status { display:inline-block; border-radius:999px; padding:4px 8px; font-size:.76rem; font-weight:850; }
  .status.pass { background:#dcfce7; color:#166534; }
  .status.fail { background:#fee2e2; color:#991b1b; }
  .hash-box { overflow-wrap:anywhere; padding:11px 13px; border-radius:10px; background:#f1f5f9; font:.8rem/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; color:#334155; }
  .equiv-notes { margin:0; padding-left:1.25rem; color:#334155; line-height:1.6; }
  .equiv-divider { display:flex; align-items:center; gap:12px; margin:24px auto 8px; max-width:1220px; padding:0 12px; font-weight:900; color:#1e293b; }
  .equiv-divider::before,.equiv-divider::after { content:""; height:1px; flex:1; background:#cbd5e1; }
  @media (max-width:850px){ .equiv-grid{grid-template-columns:repeat(2,1fr)} .compare-grid{grid-template-columns:1fr} }
  @media (max-width:520px){ .equiv-grid{grid-template-columns:1fr} .equiv-hero{padding:20px} }
  @media (prefers-color-scheme:dark){
    body{background:#111827;color:#f9fafb}.equiv-wrap{color:#f8fafc}.equiv-card,.equiv-section{background:#111827;border-color:#334155}
    .equiv-section p,.equiv-notes{color:#cbd5e1}.equiv-card span{color:#cbd5e1}.equiv-card strong{color:#93c5fd}
    .compare-figure{border-color:#334155;background:#0f172a}.compare-figure figcaption{background:#172554;border-color:#334155}
    .equiv-table th{background:#0f172a;color:#cbd5e1}.equiv-table th,.equiv-table td{border-color:#334155}
    .hash-box{background:#0f172a;color:#cbd5e1}.equiv-divider{color:#e2e8f0}.equiv-divider::before,.equiv-divider::after{background:#475569}
  }
</style>
"""

    artifact_rows = _artifact_table(comparisons)
    title_model = html.escape(model_name)
    baseline_label_html = html.escape(baseline_label)
    candidate_label_html = html.escape(candidate_label)
    metrics_rows = (
        f'<li>Canonical final placement rows: {"exact match" if placement_equal else "different"}</li>'
        f'<li>Canonical true build timeline rows: {"exact match" if timeline_equal else "different"}</li>'
        f'<li>Inventory recount: {html.escape(_inventory_text(candidate_metrics.inventory_recount))}</li>'
        f'<li>Execution deterministic: {_yes_no(candidate_metrics.deterministic)}</li>'
        f'<li>Runtime LLM used: {_yes_no(candidate_metrics.runtime_llm_used)}</li>'
        f'<li>Symmetry complete: {_yes_no(candidate_metrics.symmetry_complete)}</li>'
        f'<li>Collision free: {_yes_no(candidate_metrics.collision_free)}</li>'
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BrickSmart build-equivalence report — {title_model}</title>
{player_styles}
{report_css}
</head>
<body>
<section class="equiv-wrap" aria-labelledby="equivalence-title">
  <header class="equiv-hero">
    <p class="equiv-kicker">BrickSmart refactoring verification</p>
    <h1 class="equiv-title" id="equivalence-title">The {title_model} build {"remained unchanged" if equivalent else "changed"}</h1>
    <p class="equiv-sub">Comparison of {baseline_label_html} with {candidate_label_html}. {html.escape(reviewed_player_statement)}</p>
    <div class="{pass_class}">{pass_text}</div>
  </header>

  <div class="equiv-grid" aria-label="Build comparison metrics">
    <div class="equiv-card"><strong>{baseline_metrics.final_block_count} = {candidate_metrics.final_block_count}</strong><span>Final blocks</span></div>
    <div class="equiv-card"><strong>{baseline_metrics.true_build_step_count} = {candidate_metrics.true_build_step_count}</strong><span>True build steps</span></div>
    <div class="equiv-card"><strong>{baseline_metrics.structural_segment_count} = {candidate_metrics.structural_segment_count}</strong><span>Structural segments</span></div>
    <div class="equiv-card"><strong>{baseline_metrics.direct_structural_join_count} = {candidate_metrics.direct_structural_join_count}</strong><span>Direct structural joins</span></div>
  </div>

  <section class="equiv-section">
    <h2>Visual comparison</h2>
    <p>Both views are rendered independently from each artifact set’s final block-placement CSV. The equivalence gate separately checks block IDs, families, coordinates, dimensions, rotations, and build-step rows.</p>
    <div class="compare-grid">
      <figure class="compare-figure"><figcaption>Before — {baseline_label_html}</figcaption>{baseline_svg}</figure>
      <figure class="compare-figure"><figcaption>After — {candidate_label_html}</figcaption>{candidate_svg}</figure>
    </div>
  </section>

  <section class="equiv-section">
    <h2>Canonical artifact comparison</h2>
    <p>Exact hashes are preferred. JSON files may also pass after normalization of machine-specific absolute paths; CSV files may pass after canonical parsing when only serialization differs.</p>
    <div class="equiv-table-wrap"><table class="equiv-table">
      <thead><tr><th>Artifact</th><th>Result</th><th>Baseline SHA-256</th><th>Candidate SHA-256</th></tr></thead>
      <tbody>{artifact_rows}</tbody>
    </table></div>
  </section>

  <section class="equiv-section">
    <h2>Interactive player identity</h2>
    <p>{html.escape(reviewed_player_statement)}</p>
    <div class="hash-box">{html.escape(player_hash_text)}</div>
    <ul class="equiv-notes">{metrics_rows}</ul>
  </section>

  <section class="equiv-section">
    <h2>Scope of this proof</h2>
    <p>This report verifies the supplied canonical reference build across the selected baseline and candidate artifacts. It does not claim equivalence for models or code paths that were not executed and compared.</p>
  </section>

  {player_section}
</body>
</html>
"""


def generate_report(
    *,
    baseline_dir: Path,
    candidate_dir: Path,
    output_path: Path,
    baseline_label: str,
    candidate_label: str,
    model_name: str,
    catalog_path: Path | None = None,
    baseline_player_path: Path | None = None,
    candidate_player_path: Path | None = None,
    artifact_names: Sequence[str] = CANONICAL_ARTIFACTS,
) -> ReportResult:
    """Generate report.
    
    :param baseline_dir: Directory for baseline artifacts.
    :type baseline_dir: Path
    :param candidate_dir: Directory for candidate artifacts.
    :type candidate_dir: Path
    :param output_path: Path to the output file.
    :type output_path: Path
    :param baseline_label: The baseline label value.
    :type baseline_label: str
    :param candidate_label: The candidate label value.
    :type candidate_label: str
    :param model_name: The model name value.
    :type model_name: str
    :param catalog_path: Catalog file path used by the operation.
    :type catalog_path: Path | None
    :param baseline_player_path: Path to the baseline player file.
    :type baseline_player_path: Path | None
    :param candidate_player_path: Path to the candidate player file.
    :type candidate_player_path: Path | None
    :param artifact_names: The artifact names value.
    :type artifact_names: Sequence[str]
    :returns: The generated result.
    :rtype: ReportResult
    """
    baseline_dir = baseline_dir.resolve()
    candidate_dir = candidate_dir.resolve()
    output_path = output_path.resolve()

    for name, directory in (("baseline", baseline_dir), ("candidate", candidate_dir)):
        if not directory.is_dir():
            raise FileNotFoundError(f"{name.capitalize()} artifact directory does not exist: {directory}")

    comparisons = tuple(
        compare_artifact(filename, baseline_dir, candidate_dir)
        for filename in artifact_names
    )

    baseline_metrics = load_metrics(baseline_dir)
    candidate_metrics = load_metrics(candidate_dir)
    metrics_equal = metrics_equivalent(baseline_metrics, candidate_metrics)

    baseline_placements = canonical_dataframe(
        baseline_dir / FINAL_BLOCKS_FILE, PLACEMENT_COLUMNS
    )
    candidate_placements = canonical_dataframe(
        candidate_dir / FINAL_BLOCKS_FILE, PLACEMENT_COLUMNS
    )
    placement_equal = baseline_placements == candidate_placements

    baseline_timeline = canonical_dataframe(
        baseline_dir / TRUE_TIMELINE_FILE, TIMELINE_COLUMNS
    )
    candidate_timeline = canonical_dataframe(
        candidate_dir / TRUE_TIMELINE_FILE, TIMELINE_COLUMNS
    )
    timeline_equal = baseline_timeline == candidate_timeline

    baseline_player_hash: str | None = None
    candidate_player_hash: str | None = None
    player_equal: bool | None = None
    candidate_player_html: str | None = None

    if baseline_player_path is not None:
        baseline_player_path = baseline_player_path.resolve()
        if not baseline_player_path.is_file():
            raise FileNotFoundError(f"Baseline player does not exist: {baseline_player_path}")
        baseline_player_hash = sha256_file(baseline_player_path)

    if candidate_player_path is not None:
        candidate_player_path = candidate_player_path.resolve()
        if not candidate_player_path.is_file():
            raise FileNotFoundError(f"Candidate player does not exist: {candidate_player_path}")
        candidate_player_hash = sha256_file(candidate_player_path)
        candidate_player_html = candidate_player_path.read_text(encoding="utf-8")

    if baseline_player_hash is not None and candidate_player_hash is not None:
        player_equal = baseline_player_hash == candidate_player_hash

    colors = load_catalog_colors(catalog_path.resolve() if catalog_path else None)
    baseline_svg = render_isometric_svg(
        baseline_dir / FINAL_BLOCKS_FILE,
        label=baseline_label,
        colors=colors,
    )
    candidate_svg = render_isometric_svg(
        candidate_dir / FINAL_BLOCKS_FILE,
        label=candidate_label,
        colors=colors,
    )

    report_html = build_report_html(
        baseline_dir=baseline_dir,
        candidate_dir=candidate_dir,
        baseline_label=baseline_label,
        candidate_label=candidate_label,
        model_name=model_name,
        baseline_metrics=baseline_metrics,
        candidate_metrics=candidate_metrics,
        comparisons=comparisons,
        placement_equal=placement_equal,
        timeline_equal=timeline_equal,
        metrics_equal=metrics_equal,
        player_equal=player_equal,
        baseline_player_hash=baseline_player_hash,
        candidate_player_hash=candidate_player_hash,
        baseline_svg=baseline_svg,
        candidate_svg=candidate_svg,
        candidate_player_html=candidate_player_html,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_html, encoding="utf-8")

    equivalent = (
        all(comparison.equivalent for comparison in comparisons)
        and placement_equal
        and timeline_equal
        and metrics_equal
        and player_equal is not False
    )
    return ReportResult(
        equivalent=equivalent,
        output_path=output_path,
        artifact_comparisons=comparisons,
        placement_equal=placement_equal,
        timeline_equal=timeline_equal,
        metrics_equal=metrics_equal,
        player_equal=player_equal,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build parser.
    
    :returns: The generated result.
    :rtype: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        description="Generate a self-contained BrickSmart build-equivalence HTML report."
    )
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-label", default="accepted regression baseline")
    parser.add_argument("--candidate-label", default="candidate build")
    parser.add_argument("--model-name", default="reference model")
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--baseline-player", type=Path)
    parser.add_argument("--candidate-player", type=Path)
    parser.add_argument(
        "--allow-differences",
        action="store_true",
        help="Write the report but return success even when differences are found.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line entry point.
    
    :param argv: Command-line argument list.
    :type argv: Sequence[str] | None
    :returns: The process exit code, when one is returned.
    :rtype: int
    """
    args = build_parser().parse_args(argv)
    try:
        result = generate_report(
            baseline_dir=args.baseline_dir,
            candidate_dir=args.candidate_dir,
            output_path=args.output,
            baseline_label=args.baseline_label,
            candidate_label=args.candidate_label,
            model_name=args.model_name,
            catalog_path=args.catalog,
            baseline_player_path=args.baseline_player,
            candidate_player_path=args.candidate_player,
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError, pd.errors.ParserError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Report written: {result.output_path}")
    print(f"Equivalent: {'yes' if result.equivalent else 'no'}")
    print(f"Placement rows equal: {'yes' if result.placement_equal else 'no'}")
    print(f"Timeline rows equal: {'yes' if result.timeline_equal else 'no'}")
    print(f"Metrics equal: {'yes' if result.metrics_equal else 'no'}")
    if result.player_equal is not None:
        print(f"Player bytes equal: {'yes' if result.player_equal else 'no'}")
    failed = [item.filename for item in result.artifact_comparisons if not item.equivalent]
    if failed:
        print("Non-equivalent artifacts: " + ", ".join(failed))

    if result.equivalent or args.allow_differences:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
