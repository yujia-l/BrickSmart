"""Catalog-driven row/column structural planning engine."""

from pathlib import Path
import sys
import os

# The engine is selected only by a task-context path. Model names are data,
# not runtime branches. The generic runner always sets this environment value.
_context_value = str(os.environ.get("BRICKSMART_TASK_CONTEXT", "")).strip()
if not _context_value:
    raise RuntimeError(
        "BRICKSMART_TASK_CONTEXT is required. Run bricksmart-build --task-context <file>."
    )
MODEL_TASK_CONTEXT_JSON = Path(_context_value)

print("Selected task context:", MODEL_TASK_CONTEXT_JSON)



import base64
import copy
import io
import json
import math
import os
import posixpath
import re
import time
import traceback
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from enum import Enum
from itertools import permutations, product
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio


def emit_diagnostic(value):
    """Write diagnostic values to the worker log without UI dependencies."""
    if isinstance(value, pd.DataFrame):
        if value.empty:
            print("<empty dataframe>")
        else:
            print(value.to_string(index=False))
        return
    if isinstance(value, pd.Series):
        print(value.to_string())
        return
    if isinstance(value, str) and value.lstrip().startswith("<"):
        return
    print(value)
import requests
import trimesh
from matplotlib.colors import to_rgb
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from PIL import Image, ImageDraw, ImageFont



# Runtime task-context paths may be resolved relative to the dedicated pipeline workspace.
RUNTIME_WORKING_DIR = Path.cwd().resolve()
PROJECT_ROOT = Path(
    os.environ.get("BRICKSMART_PROJECT_ROOT", RUNTIME_WORKING_DIR.parent)
).expanduser().resolve()


def configured_path_base(paths_config, context_dir):
    mode = str(
        paths_config.get(
            "relative_to",
            "task_context_directory",
        )
    ).strip().lower()
    if mode in {
        "runtime_working_directory",
        "working_directory",
        "cwd",
        "runtime_root",
    }:
        return RUNTIME_WORKING_DIR, mode
    if mode in {
        "task_context_directory",
        "context_directory",
        "context",
    }:
        return Path(context_dir).resolve(), mode
    if mode in {"project_root", "repository_root", "repo_root"}:
        return PROJECT_ROOT, mode
    if mode in {"pipeline_runtime", "runtime_directory", "runtime"}:
        return PROJECT_ROOT / "pipeline_runtime", mode
    raise ValueError(
        "Unsupported paths.relative_to value: "
        f"{mode!r}. Expected project_root, pipeline_runtime, "
        "runtime_working_directory, or task_context_directory."
    )


def resolve_catalog_with_sibling_fallback(value, path_base):
    """
    Resolve the configured catalog without using an embedded catalog.

    Resolution order:
      1. configured path relative to the active path base;
      2. the block_catalog directory next to the runtime workspace;
      3. a unique block_definitions*.xlsx file in that sibling directory.

    If several fallback workbooks exist, fail rather than guessing.
    """
    configured = resolve_path(value, path_base)
    if configured is not None and configured.is_file():
        return configured.resolve()

    sibling_catalog_dir = (
        RUNTIME_WORKING_DIR.parent
        / "block_catalog"
    ).resolve()

    configured_basename = (
        Path(value).name
        if value not in {None, ""}
        else "block_definitions.xlsx"
    )
    explicit_candidates = [
        sibling_catalog_dir / configured_basename,
        sibling_catalog_dir / "block_definitions.xlsx",
    ]
    for candidate in explicit_candidates:
        if candidate.is_file():
            return candidate.resolve()

    fallback_matches = sorted(
        path.resolve()
        for path in sibling_catalog_dir.glob(
            "block_definitions*.xlsx"
        )
        if path.is_file()
    )
    if len(fallback_matches) == 1:
        return fallback_matches[0]
    if len(fallback_matches) > 1:
        raise FileNotFoundError(
            "The configured block catalog was not found, and multiple "
            "block_definitions*.xlsx files exist in the sibling catalog "
            "directory. Set paths.catalog_xlsx to the exact filename. "
            f"Configured: {configured}; candidates: "
            f"{[str(path) for path in fallback_matches]}"
        )
    return configured


def runtime_path_layout_summary(
    *,
    path_base,
    path_base_mode,
    context_dir,
    source_model,
    output_dir,
    catalog,
):
    return {
        "runtime_working_directory": str(
            RUNTIME_WORKING_DIR
        ),
        "task_context_directory": str(
            Path(context_dir).resolve()
        ),
        "paths_relative_to": path_base_mode,
        "active_path_base": str(
            Path(path_base).resolve()
        ),
        "expected_sibling_catalog_directory": str(
            (
                RUNTIME_WORKING_DIR.parent
                / "block_catalog"
            ).resolve()
        ),
        "resolved_source_model": str(source_model),
        "resolved_output_directory": str(output_dir),
        "resolved_catalog": str(catalog),
    }


def read_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_path(value, base_dir=None):
    if value in {None, ""}:
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    candidates = []
    if base_dir is not None:
        candidates.append(Path(base_dir) / path)
    candidates.append(Path.cwd() / path)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()


def resolve_input_with_project_fallback(value, base_dir=None):
    """Resolve a configured input, then search the project by basename."""
    configured = resolve_path(value, base_dir)
    if configured is not None and configured.exists():
        return configured
    if value in {None, ""}:
        return configured

    basename = Path(value).name
    search_roots = []
    if base_dir is not None:
        base_dir = Path(base_dir).resolve()
        search_roots.extend([base_dir, base_dir.parent])
    search_roots.append(Path.cwd().resolve())

    seen = set()
    matches = []
    for root in search_roots:
        if root in seen or not root.exists():
            continue
        seen.add(root)
        try:
            matches.extend(
                path for path in root.rglob(basename)
                if path.is_file()
            )
        except Exception:
            continue

    unique_matches = list(dict.fromkeys(path.resolve() for path in matches))
    if len(unique_matches) == 1:
        return unique_matches[0]
    if unique_matches:
        return max(unique_matches, key=lambda path: path.stat().st_mtime)
    return configured


MODEL_TASK_CONTEXT_JSON = resolve_path(MODEL_TASK_CONTEXT_JSON)
from bricksmart.runtime import (
    model_identity, normalize_task_context, resolve_execution_policy,
    validate_model_contract,
)

TASK_CONTEXT = normalize_task_context(read_json(MODEL_TASK_CONTEXT_JSON, {}))
EXECUTION_POLICY = resolve_execution_policy(TASK_CONTEXT)
if not TASK_CONTEXT:
    raise FileNotFoundError(
        f"Could not load model task context: {MODEL_TASK_CONTEXT_JSON}"
    )
MODEL_IDENTITY = model_identity(TASK_CONTEXT, context_path=MODEL_TASK_CONTEXT_JSON)
MODEL_ID = MODEL_IDENTITY.model_id
ALLOW_UNVERIFIED_CONTRACT = str(
    os.environ.get("BRICKSMART_ALLOW_UNVERIFIED_CONTRACT", "0")
).strip().lower() in {"1", "true", "yes", "on"}
MODEL_CONTRACT_VALIDATION = validate_model_contract(
    project_root=RUNTIME_WORKING_DIR.parent,
    context_path=MODEL_TASK_CONTEXT_JSON,
    allow_unverified=ALLOW_UNVERIFIED_CONTRACT,
)


# ============================================================
# Active task-context and confirmation safeguard
# ============================================================
ACTIVE_CONTEXT_NAME = MODEL_TASK_CONTEXT_JSON.name
ACTIVE_SEMANTICS = TASK_CONTEXT.get("segment_semantics", {})
ACTIVE_LABELS_FILE = ACTIVE_SEMANTICS.get("labels_file")
ACTIVE_LABELS_PATH = (
    (MODEL_TASK_CONTEXT_JSON.parent / ACTIVE_LABELS_FILE).resolve()
    if ACTIVE_LABELS_FILE
    else None
)

print("Active model id:", MODEL_ID)
print("Active task context:", MODEL_TASK_CONTEXT_JSON)
print("Configured labels file:", ACTIVE_LABELS_FILE)
print("Resolved labels path:", ACTIVE_LABELS_PATH)
print(
    "Labels file exists:",
    bool(ACTIVE_LABELS_PATH and ACTIVE_LABELS_PATH.is_file()),
)

if (
    ACTIVE_LABELS_FILE
    and (ACTIVE_LABELS_PATH is None or not ACTIVE_LABELS_PATH.is_file())
):
    raise FileNotFoundError(
        "The task context confirmation artifact is missing: "
        f"{ACTIVE_LABELS_PATH}."
    )


RUNTIME_LOGGING_CONFIG = {
    "show_environment": False,
    "show_catalog_details": False,
    "show_planner_configuration": False,
    "show_planner_rows": False,
    "show_planner_parents": False,
    "show_planner_summary": True,
    "show_output_paths": False,
    "show_visualization_paths": False,
    "show_inline_render_messages": False,
    "show_intermediate_tables": False,
    "show_assembly_step_table": False,
    "show_gate_messages": True,
    "show_final_summary": True,
    "show_debug_settings": False,
    **TASK_CONTEXT.get(
        "runtime_logging",
        {},
    ),
}


def log_enabled(
    key,
    default=False,
):
    return bool(
        RUNTIME_LOGGING_CONFIG.get(
            key,
            default,
        )
    )


def pipeline_log(
    key,
    *values,
    default=False,
    **kwargs,
):
    if log_enabled(
        key,
        default,
    ):
        print(
            *values,
            **kwargs,
        )


CONTEXT_DIR = MODEL_TASK_CONTEXT_JSON.parent
PATHS = TASK_CONTEXT.get("paths", {})
PATH_BASE_DIR, PATH_BASE_MODE = configured_path_base(
    PATHS,
    CONTEXT_DIR,
)

_RESOLVED_MODEL_OVERRIDE = os.environ.get("BRICKSMART_RESOLVED_MODEL_PATH", "").strip()
SOURCE_MODEL_PATH = (
    Path(_RESOLVED_MODEL_OVERRIDE).expanduser().resolve()
    if _RESOLVED_MODEL_OVERRIDE
    else resolve_input_with_project_fallback(
        (TASK_CONTEXT.get("model_source") or {}).get("uri")
        if isinstance(TASK_CONTEXT.get("model_source"), dict)
        and not str((TASK_CONTEXT.get("model_source") or {}).get("uri", "")).startswith(("model://", "sha256://", "http://", "https://", "s3://"))
        else PATHS.get(
            "source_model",
            TASK_CONTEXT.get("source_model_path"),
        ),
        PATH_BASE_DIR,
    )
)
SOURCE_MODEL_URI = os.environ.get(
    "BRICKSMART_RESOLVED_MODEL_URI",
    str((TASK_CONTEXT.get("model_source") or {}).get("uri", SOURCE_MODEL_PATH))
    if isinstance(TASK_CONTEXT.get("model_source"), dict)
    else str(SOURCE_MODEL_PATH),
)
SOURCE_MODEL_SHA256 = os.environ.get("BRICKSMART_RESOLVED_MODEL_SHA256", "")
_OUTPUT_OVERRIDE = str(os.environ.get("BRICKSMART_OUTPUT_DIR", "")).strip()
if not _OUTPUT_OVERRIDE:
    raise RuntimeError(
        "BRICKSMART_OUTPUT_DIR is required. Run the engine through bricksmart-build "
        "so outputs are isolated under the configured runs root."
    )
OUTPUT_DIR = Path(_OUTPUT_OVERRIDE).expanduser().resolve()
CATALOG_XLSX_CONFIG_PATH = (
    resolve_catalog_with_sibling_fallback(
        PATHS.get(
            "catalog_xlsx",
            TASK_CONTEXT.get("catalog_xlsx"),
        ),
        PATH_BASE_DIR,
    )
)
CATALOG_SHEET_CONFIG_NAME = PATHS.get(
    "catalog_sheet",
    TASK_CONTEXT.get("catalog_sheet", "Block Definitions"),
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

INPUT_DIAGNOSTICS_PATH = OUTPUT_DIR / "input_diagnostics.json"
INPUT_DIAGNOSTICS_PATH = OUTPUT_DIR / "reservation_input_diagnostics.json"  # secondary diagnostics output
INPUT_DIAGNOSTICS = {
    "schema_version": "bricksmart-runtime-1.0",
    "stage": "task_context_and_paths_resolved",
    "prototype_dependency": "none",
    "model_id": MODEL_ID,
    "task_context": str(MODEL_TASK_CONTEXT_JSON),
    "object_type_hint": MODEL_IDENTITY.object_type_hint,
    "active_context_name": ACTIVE_CONTEXT_NAME,
    "configured_labels_file": ACTIVE_LABELS_FILE,
    "resolved_labels_path": (
        str(ACTIVE_LABELS_PATH)
        if ACTIVE_LABELS_PATH is not None
        else None
    ),
    "labels_file_exists": bool(
        ACTIVE_LABELS_PATH
        and ACTIVE_LABELS_PATH.is_file()
    ),
    "source_model": str(SOURCE_MODEL_PATH),
    "source_model_uri": SOURCE_MODEL_URI,
    "source_model_sha256": SOURCE_MODEL_SHA256 or None,
    "source_model_exists": bool(SOURCE_MODEL_PATH and SOURCE_MODEL_PATH.is_file()),
    "catalog": str(CATALOG_XLSX_CONFIG_PATH),
    "catalog_exists": bool(CATALOG_XLSX_CONFIG_PATH and CATALOG_XLSX_CONFIG_PATH.is_file()),
    "output_directory": str(OUTPUT_DIR),
    "current_working_directory": str(Path.cwd().resolve()),
    "path_layout": runtime_path_layout_summary(
        path_base=PATH_BASE_DIR,
        path_base_mode=PATH_BASE_MODE,
        context_dir=CONTEXT_DIR,
        source_model=SOURCE_MODEL_PATH,
        output_dir=OUTPUT_DIR,
        catalog=CATALOG_XLSX_CONFIG_PATH,
    ),
}
INPUT_DIAGNOSTICS_PATH.write_text(
    json.dumps(INPUT_DIAGNOSTICS, indent=2),
    encoding="utf-8",
)

if SOURCE_MODEL_PATH is None or not SOURCE_MODEL_PATH.is_file():
    raise FileNotFoundError(
        "The resolved task-context model source is missing or invalid: "
        f"{SOURCE_MODEL_PATH}"
    )
if CATALOG_XLSX_CONFIG_PATH is None or not CATALOG_XLSX_CONFIG_PATH.is_file():
    sibling_catalog_dir = (
        RUNTIME_WORKING_DIR.parent
        / "block_catalog"
    ).resolve()
    raise FileNotFoundError(
        "The task context paths.catalog_xlsx is missing or invalid. "
        f"Resolved path: {CATALOG_XLSX_CONFIG_PATH}. "
        "The runtime expects the shared catalog at: "
        f"{sibling_catalog_dir / 'block_definitions.xlsx'}"
    )


if log_enabled(
    "show_environment"
):
    print("Python executable:", sys.executable)
    print("Task context:", MODEL_TASK_CONTEXT_JSON)
    print("Source model:", SOURCE_MODEL_PATH)
    print("Catalog:", CATALOG_XLSX_CONFIG_PATH)
    print("Output directory:", OUTPUT_DIR)



STRUCTURAL_CONNECTOR_POLICY = (
    TASK_CONTEXT.get("segment_assembly", {})
    .get("structural_connector_policy", {})
)
STRUCTURAL_JOIN_MODE = str(
    STRUCTURAL_CONNECTOR_POLICY.get(
        "join_mode",
        "direct_structural_lock",
    )
).strip().lower()
SUPPORTED_STRUCTURAL_JOIN_MODES = {"direct_structural_lock"}

if STRUCTURAL_JOIN_MODE not in SUPPORTED_STRUCTURAL_JOIN_MODES:
    raise NotImplementedError(
        "This planner currently validates direct male-to-female structural joins. "
        f"The active context requested join_mode={STRUCTURAL_JOIN_MODE!r}."
    )

CUSTOM_FUNCTIONAL_SUBASSEMBLY_CONFIGS = [
    dict(row)
    for row in (
        TASK_CONTEXT.get("segment_assembly", {})
        .get("custom_functional_subassemblies", [])
        or []
    )
    if bool(row.get("enabled", True))
]
CUSTOM_FUNCTIONAL_SUBASSEMBLIES_BY_TARGET = {
    str(row.get("physical_target_id") or row.get("assembly_id") or ""): row
    for row in CUSTOM_FUNCTIONAL_SUBASSEMBLY_CONFIGS
    if str(row.get("physical_target_id") or row.get("assembly_id") or "")
}
CUSTOM_FUNCTIONAL_SUBASSEMBLY_ENABLED = bool(
    CUSTOM_FUNCTIONAL_SUBASSEMBLY_CONFIGS
)

ATTACHMENT_DECLARATIONS_BY_ID = {
    str(row.get("attachment_id")): row
    for row in TASK_CONTEXT.get("functional_attachments", [])
    if row.get("attachment_id") not in {None, ""}
}

def _attachment_has_role(row, role):
    role = str(role).strip().lower()
    values = {
        str(row.get("motion_type", "")).strip().lower(),
        str(row.get("functional_role", "")).strip().lower(),
        str(row.get("attachment_type", "")).strip().lower(),
    }
    labels = {str(value).strip().lower() for value in row.get("semantic_labels", [])}
    return role in values or role in labels

WHEEL_ATTACHMENT_DECLARATIONS = [
    row for row in ATTACHMENT_DECLARATIONS_BY_ID.values()
    if _attachment_has_role(row, "wheel")
]
WHEEL_ATTACHMENT_IDS = tuple(
    str(row.get("attachment_id")) for row in WHEEL_ATTACHMENT_DECLARATIONS
)
PRIMARY_WHEEL_ATTACHMENT_ID = WHEEL_ATTACHMENT_IDS[0] if WHEEL_ATTACHMENT_IDS else ""
wheel_declaration = WHEEL_ATTACHMENT_DECLARATIONS[0] if WHEEL_ATTACHMENT_DECLARATIONS else {}
wheel_required_family = str(
    wheel_declaration.get("required_block_family", "")
).strip() or None

semantic_config = TASK_CONTEXT.get("segment_semantics", {})
auto_obj_name_semantics = bool(
    semantic_config.get("auto_confirm_from_obj_object_names", False)
)

MODEL_COMPATIBILITY_PREFLIGHT = {
    "schema_version": "bricksmart-model-preflight-1.0",
    "valid": True,
    "model_id": MODEL_ID,
    "object_type_hint": TASK_CONTEXT.get("object_type_hint"),
    "task_id": TASK_CONTEXT.get("task_id"),
    "source_model": str(SOURCE_MODEL_PATH),
    "structural_join_mode": STRUCTURAL_JOIN_MODE,
    "supported_structural_join_modes": sorted(SUPPORTED_STRUCTURAL_JOIN_MODES),
    "custom_functional_subassembly_enabled": CUSTOM_FUNCTIONAL_SUBASSEMBLY_ENABLED,
    "custom_functional_subassembly_ids": [
        str(row.get("assembly_id") or row.get("physical_target_id") or "")
        for row in CUSTOM_FUNCTIONAL_SUBASSEMBLY_CONFIGS
    ],
    "functional_assembly_types": sorted({
        str(row.get("assembly_type", "catalog_attachment"))
        for row in TASK_CONTEXT.get("functional_assemblies", [])
        if row.get("enabled", True)
    }),
    "wheel_attachment_ids": [str(row.get("attachment_id")) for row in WHEEL_ATTACHMENT_DECLARATIONS],
    "auto_confirm_from_obj_object_names": auto_obj_name_semantics,
    "functional_attachment_ids": sorted(ATTACHMENT_DECLARATIONS_BY_ID),
    "notes": [
        "Object type is descriptive data and does not select a Python branch.",
        "Functional behavior is selected by assembly_type, motion_type, catalog queries, and placement policies.",
        "The catalog is resolved from the shared XLSX workbook; inventory remains a separate run constraint.",
    ],
}

(OUTPUT_DIR / "model_compatibility_preflight.json").write_text(
    json.dumps(MODEL_COMPATIBILITY_PREFLIGHT, indent=2),
    encoding="utf-8",
)

print("Model compatibility preflight:", OUTPUT_DIR / "model_compatibility_preflight.json")
print(json.dumps(MODEL_COMPATIBILITY_PREFLIGHT, indent=2))


OBJ_SEGMENT_NAME_BY_ID = {}


def load_obj_segments_manual(file_path):
    global OBJ_SEGMENT_NAME_BY_ID
    OBJ_SEGMENT_NAME_BY_ID = {}
    vertices = []
    current_faces = []
    segments = []
    current_name = None

    with open(file_path, 'r') as f:
        for line in f:
            if line.startswith(('o ', 'g ')):
                # Save the previous OBJ object/group as one source segment.
                if current_faces:
                    segments.append((current_name, current_faces))
                    current_faces = []

                current_name = line.strip().split(' ', 1)[1]

            elif line.startswith('v '):
                parts = line.strip().split()
                vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])

            # Previously (before Rodin/Bang!)
            # elif line.startswith('f '):
            #     parts = line.strip().split()[1:]
            #     face = [int(p.split('/')[0]) - 1 for p in parts]
            #     current_faces.append(face)

            # To support Rodin/Bang! (convert to triangulation)
            elif line.startswith('f '):

                parts = line.strip().split()[1:]

                # OBJ supports:
                # v
                # v/vt
                # v//vn
                # v/vt/vn

                face = [int(p.split('/')[0]) - 1 for p in parts]

                # already triangle
                if len(face) == 3:
                    current_faces.append(face)

                # triangulate quads/ngons
                elif len(face) > 3:

                    # fan triangulation
                    for i in range(1, len(face) - 1):
                        tri = [face[0], face[i], face[i + 1]]
                        current_faces.append(tri)

    # Add last segment
    if current_faces:
        segments.append((current_name, current_faces))

    vertices = np.array(vertices)

    # Convert to trimesh objects
    segmented_meshes = []
    for i, (name, faces) in enumerate(segments):
        segment_id = i + 1
        mesh = trimesh.Trimesh(vertices=vertices, faces=np.array(faces), process=False)
        segmented_meshes.append((segment_id, mesh))
        OBJ_SEGMENT_NAME_BY_ID[segment_id] = str(name or f"segment_{segment_id}")

    print(f"[INFO] Loaded {len(segmented_meshes)} segments from OBJ (manual)")
    return segmented_meshes

def normalize_meshes(segmented_meshes):
    # Compute global bounds
    all_vertices = np.vstack([m.vertices for _, m in segmented_meshes])

    min_bound = all_vertices.min(axis=0)
    max_bound = all_vertices.max(axis=0)

    scale = (max_bound - min_bound).max()

    normalized = []
    for sid, mesh in segmented_meshes:
        m = mesh.copy()
        m.apply_translation(-min_bound)
        m.apply_scale(1.0 / scale)
        normalized.append((sid, m))

    return normalized

def obj_to_voxel_with_segments(file_path, voxel_size=16, samples_per_triangle=30):
    segmented_meshes = load_obj_segments_manual(file_path)

    segmented_meshes = normalize_meshes(segmented_meshes)

    voxel_segment = np.zeros((voxel_size, voxel_size, voxel_size), dtype=int)

    for segment_id, mesh in segmented_meshes:
        triangles = mesh.triangles

        for tri in triangles:
            for _ in range(samples_per_triangle):
                r1, r2 = np.random.rand(2)
                sqrt_r1 = np.sqrt(r1)

                u = 1 - sqrt_r1
                v = sqrt_r1 * (1 - r2)
                w = sqrt_r1 * r2

                point = u * tri[0] + v * tri[1] + w * tri[2]

                idx = np.clip((point * voxel_size).astype(int), 0, voxel_size - 1)

                voxel_segment[idx[0], idx[1], idx[2]] = segment_id

    # print("[DEBUG] Unique segments in voxel grid:", np.unique(voxel_segment))
    # print("[DEBUG] Filled voxels:", np.sum(voxel_segment > 0))

    return voxel_segment

def enforce_2x2_footprint(voxel_matrix):
    sx, sy, sz = voxel_matrix.shape
    snapped = np.zeros_like(voxel_matrix)

    for x in range(0, sx-1, 2):
        for y in range(0, sy-1, 2):
            block = voxel_matrix[x:x+2, y:y+2, :]

            # If ANY voxel exists in this 2x2 column → fill footprint
            mask = np.any(block > 0, axis=(0,1))
            for z in np.where(mask)[0]:
                color = np.bincount(block[:,:,z].flatten()[block[:,:,z].flatten()>0]).argmax()
                snapped[x:x+2, y:y+2, z] = color

    return snapped

def clean_vertical_columns(voxel_matrix):
    cleaned = voxel_matrix.copy()
    sx, sy, sz = voxel_matrix.shape

    for x in range(sx):
        for y in range(sy):
            column = voxel_matrix[x, y, :]
            filled = np.where(column > 0)[0]

            if len(filled) == 0:
                continue

            z_min = filled.min()
            z_max = filled.max()
            height = z_max - z_min + 1

            if height < 2:
                cleaned[x, y, :] = 0
                continue

            remaining = height
            valid_height = 0

            for block in [4, 3, 2]:
                count = remaining // block
                valid_height += count * block
                remaining -= count * block

            if valid_height < height:
                cleaned[x, y, z_min + valid_height : z_max + 1] = 0

    return cleaned

def thicken_floor_and_ceiling_per_column(voxel_matrix):
    """
    For each 2x2 column:
    - If the floor is 1 voxel thick, add 1 voxel below (toward interior)
    - If the ceiling is 1 voxel thick, add 1 voxel above (toward interior)
    Assumes the surface shell is already voxelized.
    """
    sx, sy, sz = voxel_matrix.shape
    new_voxel = voxel_matrix.copy()

    # Loop over all 2x2 footprints
    for x in range(0, sx - 1):
        for y in range(0, sy - 1):

            # Extract the vertical column
            column = new_voxel[x:x+2, y:y+2, :]
            filled = np.where(np.any(column > 0, axis=(0,1)))[0]

            if len(filled) == 0:
                continue

            # Floor: z_min
            z_min = filled.min()
            if z_min + 1 <= sz - 1:
                # Check if floor is only 1 voxel thick
                if np.all(column[:, :, z_min+1] == 0):
                    column[:, :, z_min+1] = column[:, :, z_min]

            # Ceiling: z_max
            z_max = filled.max()
            if z_max - 1 >= 0:
                # Check if ceiling is only 1 voxel thick
                if np.all(column[:, :, z_max-1] == 0):
                    column[:, :, z_max-1] = column[:, :, z_max]

            # Write back
            new_voxel[x:x+2, y:y+2, :] = column

    return new_voxel

@dataclass
class SegmentedVoxelBuild:
    raw_segment_grid: np.ndarray
    raw_structure_grid: np.ndarray
    preprocessed_segment_grid: np.ndarray
    clean_segment_grid: np.ndarray


def build_segmented_voxel_grids(file_path, voxel_config):
    """
    Context-driven segmented voxelization entry point.

      Execution order:
      1. sample OBJ objects/groups into a raw segmented grid;
      2. preserve the raw structure snapshot for remapping/diagnostics;
      3. apply each preprocessing operation only when enabled by context;
      4. remap processed voxels back to source segments when configured;
      5. split disconnected components when configured.

    Downstream cells still receive the same variable names assigned in
    Section 2: voxel_segment_raw, voxel_structure, voxel_segment, and
    voxel_segment_clean.
    """

    voxel_config = voxel_config or {}
    preprocessing = voxel_config.get("preprocessing", {}) or {}

    grid_size = int(voxel_config.get("grid_size", 16))

    # Sample obj into raw segmented grid
    samples_per_triangle = int(
        voxel_config.get("samples_per_triangle", 30)
    )
    random_seed = int(voxel_config.get("random_seed", 0))

    # Deterministic sampling
    np.random.seed(random_seed)

    raw_segment_grid = obj_to_voxel_with_segments(
        file_path,
        voxel_size=grid_size,
        samples_per_triangle=samples_per_triangle,
    )

    # Preserve the raw structure snapshot for remapping/diagnostics
    raw_structure_grid = raw_segment_grid.copy()
    processed_grid = raw_segment_grid.copy()

    # Apply each preprocessing operation only when enabled by context
    if preprocessing.get("enforce_2x2_footprint", True):
        processed_grid = enforce_2x2_footprint(processed_grid)

    if preprocessing.get("clean_vertical_columns", True):
        processed_grid = clean_vertical_columns(processed_grid)

    if preprocessing.get("thicken_floor_and_ceiling", True):
        processed_grid = thicken_floor_and_ceiling_per_column(
            processed_grid
        )

    preprocessed_segment_grid = processed_grid.copy()
    clean_segment_grid = processed_grid.copy()

    # Remap processed voxels back to source segments when configured
    if preprocessing.get("remap_segments_to_2x2_grid", True):
        clean_segment_grid = remap_segments_to_2x2_grid(
            clean_segment_grid,
            raw_structure_grid,
        )

    # Split disconnected components if configured
    if preprocessing.get("split_disconnected_components", True):
        clean_segment_grid = split_segment_connected_components(
            clean_segment_grid
        )

    return SegmentedVoxelBuild(
        raw_segment_grid=raw_segment_grid,
        raw_structure_grid=raw_structure_grid,
        preprocessed_segment_grid=preprocessed_segment_grid,
        clean_segment_grid=clean_segment_grid,
    )

def remap_segments_to_2x2_grid(voxel_segment, voxel_structure):
    """
    Reassign segment IDs based on 2x2 structural footprint.
    """

    x_size, y_size, z_size = voxel_segment.shape
    new_seg = np.zeros_like(voxel_segment)

    for x in range(0, x_size, 2):
        for y in range(0, y_size, 2):

            # collect all segments in this 2x2 column
            segment_votes = []

            for dx in range(2):
                for dy in range(2):

                    xx = x + dx
                    yy = y + dy

                    if xx >= x_size or yy >= y_size:
                        continue

                    for z in range(z_size):
                        if voxel_structure[xx, yy, z] > 0:
                            segment_votes.append(voxel_segment[xx, yy, z])

            if len(segment_votes) == 0:
                continue

            # majority vote (dominant segment wins)
            dominant_segment = Counter(segment_votes).most_common(1)[0][0]

            # assign to full 2x2 column
            for dx in range(2):
                for dy in range(2):
                    xx = x + dx
                    yy = y + dy

                    if xx >= x_size or yy >= y_size:
                        continue

                    for z in range(z_size):
                        if voxel_structure[xx, yy, z] > 0:
                            new_seg[xx, yy, z] = dominant_segment

    return new_seg

COMPONENT_SOURCE_SEGMENT_BY_ID = {}
COMPONENT_SOURCE_NAME_BY_ID = {}


def split_segment_connected_components(voxel_segment):
    '''
    If one segment contains two physically separate voxel clusters, preprocessing can split them into separate segment IDs.
    Suppose segment ID 4 appears in two separate places:

    Cluster 1                    Cluster 2

    [4][4]                       [4][4]
    [4][4]                       [4][4]

    There is empty space between them. The code:

    Finds the first unvisited voxel labeled 4.
    Starts a breadth-first search, or BFS.
    Collects every face-connected voxel also labeled 4.
    Assigns that entire cluster a new segment ID.
    Later encounters the second group of 4 voxels.
    Since it cannot reach the first group through face-connected 4 voxels, it assigns the second cluster another new ID.

    For example:

    Original grid:

    Cluster A = segment 4
    Cluster B = segment 4

    After splitting:

    Cluster A = new segment 1
    Cluster B = new segment 2
    '''
    global COMPONENT_SOURCE_SEGMENT_BY_ID, COMPONENT_SOURCE_NAME_BY_ID
    COMPONENT_SOURCE_SEGMENT_BY_ID = {}
    COMPONENT_SOURCE_NAME_BY_ID = {}
    sx, sy, sz = voxel_segment.shape

    new_seg = np.zeros_like(voxel_segment)
    visited = np.zeros_like(voxel_segment, dtype=bool)

    directions = [(1,0,0), (-1,0,0),
                  (0,1,0), (0,-1,0),
                  (0,0,1), (0,0,-1)]

    new_id = 1

    for x in range(sx):
        for y in range(sy):
            for z in range(sz):

                if visited[x,y,z]:
                    continue

                sid = voxel_segment[x,y,z]
                if sid == 0:
                    continue

                # BFS for connected component
                queue = deque()
                queue.append((x,y,z))
                visited[x,y,z] = True

                component = []

                while queue:
                    cx, cy, cz = queue.popleft()
                    component.append((cx,cy,cz))

                    for dx,dy,dz in directions:
                        nx, ny, nz = cx+dx, cy+dy, cz+dz

                        if (0 <= nx < sx and
                            0 <= ny < sy and
                            0 <= nz < sz):

                            if not visited[nx,ny,nz] and voxel_segment[nx,ny,nz] == sid:
                                visited[nx,ny,nz] = True
                                queue.append((nx,ny,nz))

                # assign new segment id and preserve source-object lineage
                for (cx,cy,cz) in component:
                    new_seg[cx,cy,cz] = new_id

                COMPONENT_SOURCE_SEGMENT_BY_ID[new_id] = int(sid)
                COMPONENT_SOURCE_NAME_BY_ID[new_id] = str(
                    OBJ_SEGMENT_NAME_BY_ID.get(int(sid), f"segment_{int(sid)}")
                )
                new_id += 1

    return new_seg

def compute_segment_adjacency(voxel_segment):
    sx, sy, sz = voxel_segment.shape
    adjacency = set()

    directions = [(1,0,0), (0,1,0), (0,0,1)]

    for x in range(sx):
        for y in range(sy):
            for z in range(sz):
                s1 = voxel_segment[x,y,z]
                if s1 == 0: continue

                for dx,dy,dz in directions:
                    nx, ny, nz = x+dx, y+dy, z+dz
                    if nx>=sx or ny>=sy or nz>=sz: continue

                    s2 = voxel_segment[nx,ny,nz]
                    if s2 != 0 and s2 != s1:
                        adjacency.add(tuple(sorted((s1, s2))))

    return list(adjacency)

def adjacency_to_dict(adjacency_pairs):
    adj_dict = defaultdict(set)

    for a, b in adjacency_pairs:
        a = int(a)
        b = int(b)

        adj_dict[a].add(b)
        adj_dict[b].add(a)

    # Convert sets → sorted lists (clean output)
    return {k: sorted(list(v)) for k, v in adj_dict.items()}

def compute_contact_surfaces(voxel_segment):
    sx, sy, sz = voxel_segment.shape

    directions = [
        (1,0,0), (-1,0,0),
        (0,1,0), (0,-1,0),
        (0,0,1), (0,0,-1)
    ]

    contacts = defaultdict(list)

    for x in range(sx):
        for y in range(sy):
            for z in range(sz):

                s1 = voxel_segment[x, y, z]
                if s1 == 0:
                    continue

                for dx, dy, dz in directions:
                    nx, ny, nz = x + dx, y + dy, z + dz

                    if (
                        0 <= nx < sx and
                        0 <= ny < sy and
                        0 <= nz < sz
                    ):
                        s2 = voxel_segment[nx, ny, nz]

                        if s2 != 0 and s2 != s1:
                            key = (min(s1, s2), max(s1, s2))

                            contacts[key].append({
                                "pos": (x, y, z),
                                "normal": (dx, dy, dz)
                            })

    return contacts

def compute_interface_centroid(contact_list):

    if len(contact_list) == 0:
        return None

    # -------------------------------------------------
    # Contact voxel positions
    # -------------------------------------------------

    points = np.array([
        c["pos"]
        for c in contact_list
    ])

    center = np.round(
        points.mean(axis=0)
    ).astype(int)

    # -------------------------------------------------
    # Interface directions
    # -------------------------------------------------

    normals = np.array([
        c["normal"]
        for c in contact_list
    ])

    # -------------------------------------------------
    # Count dominant AXIS
    # -------------------------------------------------

    axis_strength = np.sum(
        np.abs(normals),
        axis=0
    )

    dominant_axis = int(
        np.argmax(axis_strength)
    )

    # -------------------------------------------------
    # Determine sign along dominant axis
    # -------------------------------------------------

    signed_strength = np.sum(
        normals[:, dominant_axis]
    )

    sign = 1 if signed_strength >= 0 else -1

    normal = [0, 0, 0]
    normal[dominant_axis] = sign

    return {

        "center":
            tuple(center.tolist()),

        "normal":
            tuple(normal),

        "num_contacts":
            int(len(contact_list))
    }

def normalize_voxel_axes(voxel_segment):
    # OBJ/trimesh fix: swap Y and Z into visualization convention
    return np.transpose(voxel_segment, (0, 2, 1))

PALETTE = [
    (230, 25, 75),   (60, 180, 75),   (255, 225, 25),
    (0, 130, 200),   (245, 130, 48),  (145, 30, 180),
    (70, 240, 240),  (240, 50, 230),  (210, 245, 60),
    (250, 190, 190), (0, 128, 128),   (230, 190, 255),
    (170, 110, 40),  (255, 250, 200), (128, 0, 0),
    (170, 255, 195), (128, 128, 0),   (255, 215, 180),
    (0, 0, 128),     (128, 128, 128), (255, 105, 180),
    (0, 255, 127),   (138, 43, 226),  (255, 140, 0),
    (220, 20, 60),   (50, 205, 50),   (70, 130, 180),
    (255, 69, 0),    (154, 205, 50),  (75, 0, 130),
    (240, 230, 140), (0, 191, 255),   (199, 21, 133),
    (124, 252, 0),   (255, 20, 147),  (0, 250, 154),
]

def color_distance(c1, c2):
    return sum((a - b) ** 2 for a, b in zip(c1, c2))

def generate_segment_colors(voxel_segment, adjacency_dict):
    segment_ids = sorted(np.unique(voxel_segment))
    segment_ids = [s for s in segment_ids if s != 0]

    colors = {}
    used_colors = set()

    for sid in segment_ids:
        best_color = None
        best_score = -1e9

        for i, color in enumerate(PALETTE):

            # 1. adjacency penalty
            adj_penalty = 0
            for n in adjacency_dict.get(sid, []):
                if n in colors:
                    adj_penalty += color_distance(color, colors[n])

            # 2. global reuse penalty
            reuse_penalty = 0
            if color in used_colors:
                reuse_penalty += 1e6  # strong discouragement

            # 3. deterministic tie-breaker (palette order bias)
            tie_breaker = -i * 0.01

            score = adj_penalty - reuse_penalty + tie_breaker

            if score > best_score:
                best_score = score
                best_color = color

        colors[sid] = best_color
        used_colors.add(best_color)

    return colors

def visualize_segments(voxel_segment, adjacency_dict, elev=20, azim=45):

    # Swap Y and Z in visualization
    voxel_vis = normalize_voxel_axes(voxel_segment)

    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')

    filled = voxel_vis > 0

    # IMPORTANT: proper float buffer
    colors = np.zeros(voxel_vis.shape + (3,), dtype=np.float32)

    # adjacency-aware color generation
    segment_colors = generate_segment_colors(voxel_vis, adjacency_dict)

    for sid, color in segment_colors.items():
        mask = voxel_vis == sid

        # normalize RGB -> [0,1] for matplotlib
        colors[mask] = np.array(color) / 255.0

    ax.voxels(filled, facecolors=colors, edgecolor='none', alpha=1.0)

    ax.set_xlim(0, voxel_vis.shape[0])
    ax.set_ylim(0, voxel_vis.shape[1])
    ax.set_zlim(0, voxel_vis.shape[2])

    ax.view_init(elev=elev, azim=azim)

    ax.set_box_aspect(voxel_vis.shape)

    plt.title("Segment Visualization")
    plt.show()

def render_voxel_view(voxel_segment, elev, azim, segment_colors):

    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')

    filled = voxel_segment > 0
    colors = np.zeros(voxel_segment.shape + (3,), dtype=np.float32)

    for sid, color in segment_colors.items():
        mask = voxel_segment == sid
        colors[mask] = np.array(color) / 255.0

    ax.voxels(filled, facecolors=colors, edgecolor='none', alpha=1.0)

    ax.set_xlim(0, voxel_segment.shape[0])
    ax.set_ylim(0, voxel_segment.shape[1])
    ax.set_zlim(0, voxel_segment.shape[2])

    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=150)
    plt.close(fig)

    buf.seek(0)
    return Image.open(buf)

VIEWS = [
    ("front", 0, -90),
    ("back", 0, 90),
    ("left", 0, 180),
    ("right", 0, 0),
    ("top", 90, 0),
    ("bottom", -90, 0),
    ("iso_1", 30, 45),
    ("iso_2", 30, -45),
]

def create_segment_legend(
    segment_colors,
    segment_names=None,
    swatch_size=40,
    padding=10,
):
    segment_ids = sorted(int(value) for value in segment_colors)
    segment_names = {
        int(key): str(value)
        for key, value in (segment_names or {}).items()
    }
    longest = max([
        len(f"Segment {sid} — {segment_names.get(sid, '')}")
        for sid in segment_ids
    ] or [20])
    width = max(300, min(760, 140 + longest * 8))
    height = len(segment_ids) * (swatch_size + padding) + padding
    image = Image.new('RGB', (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype('arial.ttf', 16)
    except Exception:
        font = ImageFont.load_default()

    for index, sid in enumerate(segment_ids):
        y = padding + index * (swatch_size + padding)
        color = tuple(map(int, segment_colors[sid]))
        draw.rectangle(
            [padding, y, padding + swatch_size, y + swatch_size],
            fill=color,
        )
        display_name = segment_names.get(sid, '').strip()
        text = f'Segment {sid}'
        if display_name and display_name != text:
            text += f' — {display_name}'
        draw.text(
            (padding + swatch_size + 10, y + swatch_size // 4),
            text,
            fill=(0, 0, 0),
            font=font,
        )
    return image

def generate_multiview(voxel_segment, adjacency_dict):

    # Swap Y and Z in visualization
    voxel_vis = normalize_voxel_axes(voxel_segment)

    outputs = []

    segment_colors = generate_segment_colors(voxel_vis, adjacency_dict)

    for name, elev, azim in VIEWS:
        img = render_voxel_view(voxel_vis, elev, azim, segment_colors)
        outputs.append({
            "view": name,
            "elev": elev,
            "azim": azim,
            "image": img
        })

    legend_img = create_segment_legend(segment_colors)

    outputs.append({
        "view": "legend",
        "image": legend_img
    })

    return outputs, segment_colors

def display_multiview(views):
    n = len(views)
    cols = 4
    rows = (n + cols - 1) // cols

    figure_size = tuple(
        TASK_CONTEXT.get(
            "visualization",
            {},
        ).get(
            "reference_segment_panel_figsize",
            [12.0, 7.5],
        )
    )
    plt.figure(figsize=figure_size)

    for i, v in enumerate(views):
        plt.subplot(rows, cols, i + 1)
        plt.imshow(v["image"])
        plt.title(v["view"])
        plt.axis("off")

    plt.tight_layout()
    plt.show()


VOXEL_CONFIG = TASK_CONTEXT.get("voxelization", {})
PREPROCESSING_CONFIG = VOXEL_CONFIG.get("preprocessing", {})

grid_size = int(VOXEL_CONFIG.get("grid_size", 16))
samples_per_triangle = int(
    VOXEL_CONFIG.get("samples_per_triangle", 30)
)
random_seed = int(VOXEL_CONFIG.get("random_seed", 0))

voxel_build = build_segmented_voxel_grids(
    SOURCE_MODEL_PATH,
    VOXEL_CONFIG,
)

# Preserve variable names expected by downstream downstream planner stages.
voxel_segment_raw = voxel_build.raw_segment_grid
voxel_structure = voxel_build.raw_structure_grid
voxel_segment = voxel_build.preprocessed_segment_grid
voxel_segment_clean = voxel_build.clean_segment_grid

print("Voxelization and preprocessing complete")
print("Raw grid shape:", voxel_segment_raw.shape)
print(
    "Raw occupied voxels:",
    int(np.count_nonzero(voxel_segment_raw)),
)
print(
    "Clean occupied voxels:",
    int(np.count_nonzero(voxel_segment_clean)),
)
print(
    "Clean segment IDs:",
    sorted(
        int(value)
        for value in np.unique(voxel_segment_clean)
        if int(value) != 0
    ),
)

adjacency_pairs = compute_segment_adjacency(voxel_segment_clean)
adjacency_dict = adjacency_to_dict(adjacency_pairs)
raw_contacts = compute_contact_surfaces(voxel_segment_clean)
segment_colors = generate_segment_colors(
    voxel_segment_clean,
    adjacency_dict,
)

np.save(OUTPUT_DIR / "voxel_segment_clean.npy", voxel_segment_clean)

from bricksmart.geometry.source_segment_preservation import (
    evaluate_source_segment_preservation,
    recommend_grid_size as recommend_source_preserving_grid_size,
)
_source_segment_report = evaluate_source_segment_preservation(
    source_segment_ids=sorted(OBJ_SEGMENT_NAME_BY_ID),
    raw_grid=voxel_segment_raw,
    clean_grid=voxel_segment_clean,
    clean_to_source=(COMPONENT_SOURCE_SEGMENT_BY_ID or None),
)
_source_segment_payload = _source_segment_report.to_dict()
_source_segment_payload["current_grid_size"] = int(grid_size)
_source_segment_payload["recommended_next_grid_size"] = int(
    recommend_source_preserving_grid_size(
        current_grid_size=grid_size,
        report=_source_segment_report,
    )
)
_source_segment_payload["policy"] = str(
    VOXEL_CONFIG.get("source_segment_preservation_policy", "report")
)
(OUTPUT_DIR / "source_segment_preservation.json").write_text(
    json.dumps(_source_segment_payload, indent=2),
    encoding="utf-8",
)
if (
    _source_segment_report.status != "PASS"
    and str(VOXEL_CONFIG.get("source_segment_preservation_policy", "report")).lower()
    == "fail"
):
    raise RuntimeError(
        "Source segment preservation failed; missing source segment IDs: "
        f"{list(_source_segment_report.missing_segment_ids)}. "
        "See source_segment_preservation.json."
    )

(OUTPUT_DIR / "obj_segment_name_lineage.json").write_text(
    json.dumps(
        {
            "obj_segment_name_by_id": {
                str(key): value for key, value in OBJ_SEGMENT_NAME_BY_ID.items()
            },
            "component_source_segment_by_id": {
                str(key): int(value) for key, value in COMPONENT_SOURCE_SEGMENT_BY_ID.items()
            },
            "component_source_name_by_id": {
                str(key): value for key, value in COMPONENT_SOURCE_NAME_BY_ID.items()
            },
        },
        indent=2,
    ),
    encoding="utf-8",
)
if log_enabled(
    "show_environment"
):
    print(
        "Occupied voxels:",
        int(
            (
                voxel_segment_clean
                > 0
            ).sum()
        ),
    )
    print(
        "Clean segment IDs:",
        sorted(
            int(value)
            for value in np.unique(
                voxel_segment_clean
            )
            if value > 0
        ),
    )

visualize_segments(
    voxel_segment_clean,
    adjacency_dict,
    elev=20,
    azim=45,
)

if TASK_CONTEXT.get(
    "visualization",
    {},
).get(
    "show_reference_segment_panel",
    True,
):
    reference_segment_views, reference_segment_colors = (
        generate_multiview(
            voxel_segment_clean,
            adjacency_dict,
        )
    )
    pipeline_log(
        "show_visualization_paths",
        "Reference segment views generated.",
    )



def load_label_records(path):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)

    payload = read_json(path, {})
    if isinstance(payload, list):
        return pd.DataFrame(payload)
    if isinstance(payload, dict):
        if isinstance(payload.get("segments"), dict):
            return pd.DataFrame(
                [
                    {
                        "segment_id": int(segment_id),
                        "segment_label": label,
                    }
                    for segment_id, label in payload["segments"].items()
                ]
            )
        for key in [
            "segment_rows",
            "segments_labeled",
            "records",
        ]:
            if isinstance(payload.get(key), list):
                return pd.DataFrame(payload[key])
    return pd.DataFrame()


def normalize_segment_label_table(
    voxel_grid,
    task_context,
):
    """
    Build the initial segment-label table from the front-end confirmation file.

    Accepted teacher/front-end columns include:
      - confirmed_label / confirmed_name
      - confirmation_status / confirmation_source

    Aliases are normalized to the canonical catalog schema.
    """
    segment_ids, voxel_counts = np.unique(
        voxel_grid[voxel_grid > 0],
        return_counts=True,
    )
    result = pd.DataFrame(
        {
            "segment_id": segment_ids.astype(int),
            "voxel_count": voxel_counts.astype(int),
        }
    )

    semantics = task_context.get(
        "segment_semantics",
        {},
    )
    unknown_label = str(
        semantics.get(
            "unknown_label",
            "unknown",
        )
    )

    result["segment_label"] = unknown_label
    result["label_source"] = "unlabeled"
    result["confirmed_name_from_file"] = ""
    result["confirmation_status_from_file"] = "unresolved"

    labels_file = semantics.get(
        "labels_file"
    )
    if labels_file:
        labels_path = resolve_path(
            labels_file,
            CONTEXT_DIR,
        )
        if not labels_path.is_file():
            raise FileNotFoundError(
                "segment_semantics.labels_file not found: "
                f"{labels_path}"
            )

        labels_df = load_label_records(
            labels_path
        ).copy()

        id_col = next(
            (
                column
                for column in [
                    "segment_id",
                    "source_segment_id",
                    "id",
                ]
                if column in labels_df.columns
            ),
            None,
        )
        label_col = next(
            (
                column
                for column in [
                    "confirmed_label",
                    "segment_label",
                    "final_label",
                    "semantic_label",
                    "label",
                ]
                if column in labels_df.columns
            ),
            None,
        )
        name_col = next(
            (
                column
                for column in [
                    "confirmed_name",
                    "segment_display_name",
                    "segment_name",
                    "display_name",
                ]
                if column in labels_df.columns
            ),
            None,
        )
        status_col = next(
            (
                column
                for column in [
                    "confirmation_status",
                    "status",
                ]
                if column in labels_df.columns
            ),
            None,
        )
        source_col = next(
            (
                column
                for column in [
                    "confirmation_source",
                    "label_source",
                    "source",
                    "decision_source",
                ]
                if column in labels_df.columns
            ),
            None,
        )

        if id_col is None or label_col is None:
            raise ValueError(
                "The labels file must contain a segment ID column and "
                "one confirmed-label column. Accepted label columns are: "
                "confirmed_label, segment_label, final_label, "
                "semantic_label, or label. "
                f"Observed columns: {list(labels_df.columns)}"
            )

        labels_df["segment_id"] = pd.to_numeric(
            labels_df[id_col],
            errors="coerce",
        ).astype("Int64")
        labels_df = labels_df.dropna(
            subset=["segment_id"]
        )
        labels_df["segment_id"] = (
            labels_df["segment_id"].astype(int)
        )

        default_status = str(
            semantics.get(
                "confirmation_policy",
                {},
            ).get(
                "labels_file_default_status",
                "confirmed",
            )
        ).lower()

        labels_df[
            "confirmation_status_from_file"
        ] = (
            labels_df[status_col]
            .fillna(default_status)
            .astype(str)
            .str.strip()
            .str.lower()
            if status_col
            else default_status
        )

        authoritative_statuses = {
            str(value).strip().lower()
            for value in (
                semantics.get(
                    "labels_file_schema",
                    {},
                ).get(
                    "authoritative_statuses",
                    [
                        "confirmed",
                        "corrected",
                        "approved",
                        "accepted",
                    ],
                )
            )
        }

        labels_df["segment_label_from_file"] = (
            labels_df[label_col]
            .fillna("")
            .astype(str)
            .str.strip()
        )
        labels_df["confirmed_name_from_file"] = (
            labels_df[name_col]
            .fillna("")
            .astype(str)
            .str.strip()
            if name_col
            else ""
        )
        labels_df["label_source_from_file"] = (
            labels_df[source_col]
            .fillna("labels_file")
            .astype(str)
            .str.strip()
            if source_col
            else "labels_file"
        )

        # Only confirmed/corrected/approved/accepted rows may drive backend
        # semantics. Proposed or unresolved rows remain unknown.
        authoritative_mask = labels_df[
            "confirmation_status_from_file"
        ].isin(
            authoritative_statuses
        )
        labels_df.loc[
            ~authoritative_mask,
            "segment_label_from_file",
        ] = ""

        labels_for_merge = labels_df[
            [
                "segment_id",
                "segment_label_from_file",
                "confirmed_name_from_file",
                "confirmation_status_from_file",
                "label_source_from_file",
            ]
        ].drop_duplicates(
            "segment_id",
            keep="last",
        )

        result = result.merge(
            labels_for_merge,
            on="segment_id",
            how="left",
            suffixes=("", "_merged"),
        )

        file_mask = (
            result["segment_label_from_file"]
            .fillna("")
            .astype(str)
            .str.strip()
            .ne("")
        )
        result.loc[
            file_mask,
            "segment_label",
        ] = result.loc[
            file_mask,
            "segment_label_from_file",
        ]
        result.loc[
            file_mask,
            "label_source",
        ] = result.loc[
            file_mask,
            "label_source_from_file",
        ]

        result[
            "confirmed_name_from_file"
        ] = result[
            "confirmed_name_from_file_merged"
        ].fillna(
            result[
                "confirmed_name_from_file"
            ]
        )
        result[
            "confirmation_status_from_file"
        ] = result[
            "confirmation_status_from_file_merged"
        ].fillna(
            result[
                "confirmation_status_from_file"
            ]
        )

        result = result.drop(
            columns=[
                "segment_label_from_file",
                "label_source_from_file",
                "confirmed_name_from_file_merged",
                "confirmation_status_from_file_merged",
            ]
        )

    manual_labels = {}
    manual_labels.update(
        {
            str(key): value
            for key, value in task_context.get(
                "manual_segment_labels",
                {},
            ).items()
        }
    )
    manual_labels.update(
        {
            str(key): value
            for key, value in semantics.get(
                "manual_segment_labels",
                {},
            ).items()
        }
    )

    for segment_id_text, label in (
        manual_labels.items()
    ):
        segment_id = int(
            segment_id_text
        )
        mask = (
            result["segment_id"]
            == segment_id
        )
        if mask.any():
            result.loc[
                mask,
                "segment_label",
            ] = str(label)
            result.loc[
                mask,
                "label_source",
            ] = "confirmed_override"
            result.loc[
                mask,
                "confirmation_status_from_file",
            ] = "confirmed"

    allowed_labels = {
        str(value)
        for value in semantics.get(
            "allowed_labels",
            [],
        )
    }
    if allowed_labels:
        invalid = ~result[
            "segment_label"
        ].isin(
            allowed_labels
        )
        if invalid.any():
            invalid_rows = result.loc[
                invalid,
                [
                    "segment_id",
                    "segment_label",
                ],
            ].to_dict(
                orient="records"
            )
            raise ValueError(
                "Segment labels are outside the task-context contract: "
                f"{invalid_rows}"
            )

    return result


segments_labeled_df = normalize_segment_label_table(
    voxel_segment_clean,
    TASK_CONTEXT,
)
segments_labeled_df.to_csv(
    OUTPUT_DIR / "segments_labeled_initial.csv",
    index=False,
)

object_type = TASK_CONTEXT.get(
    "object_type_hint",
    "unknown",
)
segment_labels_dict = dict(
    zip(
        segments_labeled_df["segment_id"].astype(int),
        segments_labeled_df["segment_label"].astype(str),
    )
)
final_output_dict = {
    "object_type": object_type,
    "segments": segment_labels_dict,
}

unknown_count = int(
    (
        segments_labeled_df["segment_label"]
        == TASK_CONTEXT.get(
            "segment_semantics",
            {},
        ).get("unknown_label", "unknown")
    ).sum()
)
print("Object type:", object_type)
print("Unknown segment labels:", unknown_count)
emit_diagnostic(segments_labeled_df)

# Runtime: do not fail here. OBJ object-name aliases, the optional labels
# file, manual overrides, and teacher confirmations are applied in the next
# semantic-confirmation stage.
if unknown_count == len(segments_labeled_df):
    print(
        "All labels are initially unknown; deferring the required-label gate "
        "until after OBJ-name and teacher-confirmation resolution."
    )


# ============================================================
# Teacher/front-end segment confirmation and display names
# ============================================================

semantics = TASK_CONTEXT.get('segment_semantics', {})
confirmation_policy = semantics.get('confirmation_policy', {})
unknown_label = str(semantics.get('unknown_label', 'unknown'))

segments_labeled_df = segments_labeled_df.copy()
for column, default in {
    'proposed_label': unknown_label,
    'confirmed_label': '',
    'confirmed_name': '',
    'confirmation_status': 'unresolved',
    'confirmation_source': '',
}.items():
    if column not in segments_labeled_df.columns:
        segments_labeled_df[column] = default

# Preserve any confirmed display name/status already read by the initial
# schema-compatible normalizer.
if 'confirmed_name_from_file' in segments_labeled_df.columns:
    file_name_mask = (
        segments_labeled_df['confirmed_name_from_file']
        .fillna('')
        .astype(str)
        .str.strip()
        .ne('')
    )
    segments_labeled_df.loc[
        file_name_mask,
        'confirmed_name',
    ] = segments_labeled_df.loc[
        file_name_mask,
        'confirmed_name_from_file',
    ]

if 'confirmation_status_from_file' in segments_labeled_df.columns:
    file_status_mask = (
        segments_labeled_df['confirmation_status_from_file']
        .fillna('')
        .astype(str)
        .str.strip()
        .ne('')
    )
    segments_labeled_df.loc[
        file_status_mask,
        'confirmation_status',
    ] = segments_labeled_df.loc[
        file_status_mask,
        'confirmation_status_from_file',
    ]

confirmed_from_initial_mask = (
    segments_labeled_df['segment_label']
    .astype(str)
    .ne(unknown_label)
)
segments_labeled_df.loc[
    confirmed_from_initial_mask,
    'confirmed_label',
] = segments_labeled_df.loc[
    confirmed_from_initial_mask,
    'segment_label',
]
segments_labeled_df.loc[
    confirmed_from_initial_mask,
    'confirmation_source',
] = segments_labeled_df.loc[
    confirmed_from_initial_mask,
    'label_source',
]


def _useful_segment_text(value):
    text = str(value or '').strip()
    return '' if text.lower() in {'', 'none', 'nan', 'unknown', 'unlabeled'} else text


def _apply_segment_confirmation(record, default_source='teacher_frontend'):
    id_value = record.get('segment_id', record.get('source_segment_id', record.get('id')))
    if id_value in {None, ''}:
        return
    try:
        segment_id = int(id_value)
    except (TypeError, ValueError):
        return
    mask = segments_labeled_df['segment_id'].astype(int) == segment_id
    if not mask.any():
        return

    proposed = _useful_segment_text(record.get(
        'proposed_label',
        record.get('segment_label', record.get('label', record.get('semantic_label', ''))),
    ))
    confirmed_label = _useful_segment_text(record.get('confirmed_label', record.get('final_label', '')))
    confirmed_name = _useful_segment_text(record.get(
        'confirmed_name',
        record.get('segment_name', record.get('display_name', '')),
    ))
    status = _useful_segment_text(record.get(
        'confirmation_status',
        record.get('status', confirmation_policy.get('labels_file_default_status', 'proposed')),
    )).lower() or 'proposed'
    source = _useful_segment_text(record.get(
        'confirmation_source',
        record.get('label_source', record.get('source', default_source)),
    )) or default_source

    if proposed:
        segments_labeled_df.loc[mask, 'proposed_label'] = proposed
    if status in {'confirmed', 'corrected'}:
        canonical = confirmed_label or proposed
        if canonical:
            segments_labeled_df.loc[mask, 'confirmed_label'] = canonical
            segments_labeled_df.loc[mask, 'segment_label'] = canonical
            segments_labeled_df.loc[mask, 'label_source'] = 'confirmed_override'
        if confirmed_name:
            segments_labeled_df.loc[mask, 'confirmed_name'] = confirmed_name
    elif confirmation_policy.get('unconfirmed_labels_may_affect_backend', False) and proposed:
        segments_labeled_df.loc[mask, 'segment_label'] = proposed

    segments_labeled_df.loc[mask, 'confirmation_status'] = status
    segments_labeled_df.loc[mask, 'confirmation_source'] = source


# Treat labels from the optional labels file according to their confirmation status.
labels_file = semantics.get('labels_file')
if labels_file:
    labels_path = resolve_path(labels_file, CONTEXT_DIR)
    if labels_path.is_file():
        labels_confirmation_df = load_label_records(labels_path)
        for record in labels_confirmation_df.to_dict(orient='records'):
            _apply_segment_confirmation(record, 'labels_file')

allowed_labels = set(str(value) for value in semantics.get('allowed_labels', []))


# Optional model-profile semantic bridge. This is enabled only by the task
# context and only exact mapped OBJ object names become authoritative labels.
def _normalized_obj_semantic_name(value):
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return text

if semantics.get("auto_confirm_from_obj_object_names", False):
    aliases = {
        _normalized_obj_semantic_name(key): str(value)
        for key, value in semantics.get("obj_object_name_aliases", {}).items()
    }
    source_names = (
        COMPONENT_SOURCE_NAME_BY_ID
        if COMPONENT_SOURCE_NAME_BY_ID
        else OBJ_SEGMENT_NAME_BY_ID
    )
    auto_rows = []
    for segment_id, object_name in source_names.items():
        normalized_name = _normalized_obj_semantic_name(object_name)
        canonical_label = aliases.get(normalized_name, normalized_name)
        if allowed_labels and canonical_label not in allowed_labels:
            continue
        _apply_segment_confirmation({
            "segment_id": int(segment_id),
            "confirmed_label": canonical_label,
            "confirmed_name": str(object_name),
            "confirmation_status": "confirmed",
            "confirmation_source": "task_context_obj_name_alias",
        }, "task_context_obj_name_alias")
        auto_rows.append({
            "segment_id": int(segment_id),
            "obj_object_name": str(object_name),
            "normalized_name": normalized_name,
            "confirmed_label": canonical_label,
        })
    safe_auto_path = OUTPUT_DIR / "obj_name_semantic_confirmation_audit.csv"
    pd.DataFrame(auto_rows).to_csv(safe_auto_path, index=False)

# Provisional labels remain suggestions and do not become authoritative backend labels.
for segment_id, label in semantics.get('provisional_segment_labels', {}).items():
    _apply_segment_confirmation({
        'segment_id': segment_id,
        'proposed_label': label,
        'confirmation_status': 'proposed',
        'confirmation_source': 'task_context_provisional',
    }, 'task_context_provisional')

# Manual labels and front-end confirmation records are authoritative.
for segment_id, label in semantics.get('manual_segment_labels', {}).items():
    _apply_segment_confirmation({
        'segment_id': segment_id,
        'confirmed_label': label,
        'confirmation_status': 'confirmed',
        'confirmation_source': 'teacher_manual_override',
    }, 'teacher_manual_override')

for record in semantics.get('segment_confirmation_records', []):
    _apply_segment_confirmation(record, 'teacher_frontend')

for segment_id, name in semantics.get('confirmed_segment_names', {}).items():
    mask = segments_labeled_df['segment_id'].astype(int) == int(segment_id)
    if mask.any() and str(name).strip():
        segments_labeled_df.loc[mask, 'confirmed_name'] = str(name).strip()
        status = segments_labeled_df.loc[mask, 'confirmation_status'].astype(str).str.lower()
        if not status.isin({'confirmed', 'corrected'}).all():
            segments_labeled_df.loc[mask, 'confirmation_status'] = 'confirmed'
        source = segments_labeled_df.loc[mask, 'confirmation_source'].astype(str).str.strip()
        if source.eq('').all():
            segments_labeled_df.loc[mask, 'confirmation_source'] = 'teacher_frontend'

# Enforce the policy: unconfirmed labels do not drive backend semantics.
if not confirmation_policy.get('unconfirmed_labels_may_affect_backend', False):
    confirmed_mask = segments_labeled_df['confirmation_status'].astype(str).str.lower().isin({'confirmed', 'corrected'})
    segments_labeled_df.loc[~confirmed_mask, 'segment_label'] = unknown_label

allowed_labels = set(str(value) for value in semantics.get('allowed_labels', []))
if allowed_labels:
    invalid = ~segments_labeled_df['segment_label'].astype(str).isin(allowed_labels)
    if invalid.any():
        raise ValueError(
            'Confirmed segment labels are outside the task-context contract: '
            + str(segments_labeled_df.loc[invalid, ['segment_id', 'segment_label']].to_dict(orient='records'))
        )


def _segment_display_name(row):
    confirmed_name = _useful_segment_text(row.confirmed_name)
    if confirmed_name:
        return confirmed_name
    confirmed_label = _useful_segment_text(row.confirmed_label)
    if confirmed_label:
        return confirmed_label.replace('_', ' ').title()
    proposed = _useful_segment_text(row.proposed_label)
    if proposed:
        return proposed.replace('_', ' ').title()
    return f'Segment {int(row.segment_id)}'

segments_labeled_df['segment_display_name'] = [
    _segment_display_name(row)
    for row in segments_labeled_df.itertuples(index=False)
]
segments_labeled_df['segment_name'] = segments_labeled_df['segment_display_name']

segment_labels_dict = dict(zip(
    segments_labeled_df['segment_id'].astype(int),
    segments_labeled_df['segment_label'].astype(str),
))
segment_display_name_by_id = dict(zip(
    segments_labeled_df['segment_id'].astype(int),
    segments_labeled_df['segment_display_name'].astype(str),
))
segment_confirmation_status_by_id = dict(zip(
    segments_labeled_df['segment_id'].astype(int),
    segments_labeled_df['confirmation_status'].astype(str),
))


def optional_value_is_missing(value):
    """Return True for None, NaN, pandas NA, and blank strings."""
    if value is None:
        return True

    if isinstance(value, str):
        return value.strip().lower() in {
            "",
            "none",
            "nan",
            "null",
            "<na>",
        }

    try:
        missing = pd.isna(value)
    except Exception:
        return False

    if isinstance(
        missing,
        (bool, np.bool_),
    ):
        return bool(missing)

    return False


def normalized_optional_segment_id(value):
    """Normalize integer-like segment IDs while allowing missing values."""
    if optional_value_is_missing(value):
        return None

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            "Segment ID must be integer-like or missing; "
            f"received {value!r}."
        )

    if not numeric_value.is_integer():
        raise ValueError(
            "Segment ID must be an integer value; "
            f"received {value!r}."
        )

    return int(numeric_value)


def segment_display_text(
    segment_id,
    include_id=True,
    missing_text="not applicable",
):
    """
    Format a semantic segment name and stable ID.

    Root assembly steps have no anchor segment, so missing values return
    `missing_text` rather than raising TypeError.
    """
    normalized_id = normalized_optional_segment_id(
        segment_id
    )
    if normalized_id is None:
        return str(missing_text)

    name = segment_display_name_by_id.get(
        normalized_id,
        f"Segment {normalized_id}",
    )
    if include_id:
        return (
            f"{name} "
            f"(segment {normalized_id})"
        )
    return str(name)

final_output_dict = {
    'object_type': object_type,
    'segment_labels': segment_labels_dict,
    'segment_display_names': segment_display_name_by_id,
    'segment_confirmation_status': segment_confirmation_status_by_id,
}
segments_labeled_df.to_csv(OUTPUT_DIR / 'segments_labeled_initial.csv', index=False)

print('Teacher-confirmed segment semantics:')
emit_diagnostic(segments_labeled_df[[
    'segment_id',
    'segment_display_name',
    'proposed_label',
    'confirmed_label',
    'segment_label',
    'confirmation_status',
    'confirmation_source',
    'voxel_count',
]].sort_values('segment_id'))


# ============================================================
# Final semantic audit and deferred all-unknown gate
# ============================================================

def _source_name_for_segment(segment_id):
    source_names = (
        COMPONENT_SOURCE_NAME_BY_ID
        if globals().get("COMPONENT_SOURCE_NAME_BY_ID")
        else globals().get("OBJ_SEGMENT_NAME_BY_ID", {})
    )
    return str(source_names.get(int(segment_id), ""))


semantic_resolution_audit_df = segments_labeled_df.copy()
semantic_resolution_audit_df["obj_object_name"] = (
    semantic_resolution_audit_df["segment_id"]
    .astype(int)
    .map(_source_name_for_segment)
)

semantic_resolution_audit_columns = [
    "segment_id",
    "obj_object_name",
    "segment_display_name",
    "proposed_label",
    "confirmed_label",
    "segment_label",
    "confirmation_status",
    "confirmation_source",
    "voxel_count",
]
semantic_resolution_audit_df[
    semantic_resolution_audit_columns
].sort_values("segment_id").to_csv(
    OUTPUT_DIR / "segment_semantic_resolution_audit.csv",
    index=False,
)

final_unknown_mask = (
    segments_labeled_df["segment_label"]
    .astype(str)
    .eq(unknown_label)
)
final_unknown_count = int(final_unknown_mask.sum())
final_confirmed_count = int(
    len(segments_labeled_df) - final_unknown_count
)

confirmation_template_df = pd.DataFrame({
    "segment_id": segments_labeled_df["segment_id"].astype(int),
    "confirmed_label": [
        "" if label == unknown_label else str(label)
        for label in segments_labeled_df["segment_label"].astype(str)
    ],
    "confirmed_name": (
        segments_labeled_df["segment_display_name"].astype(str)
    ),
    "confirmation_status": [
        "unresolved" if label == unknown_label else "confirmed"
        for label in segments_labeled_df["segment_label"].astype(str)
    ],
    "confirmation_source": [
        (
            "teacher_review_required"
            if label == unknown_label
            else str(source)
        )
        for label, source in zip(
            segments_labeled_df["segment_label"].astype(str),
            segments_labeled_df["confirmation_source"].astype(str),
        )
    ],
    "obj_object_name": (
        segments_labeled_df["segment_id"]
        .astype(int)
        .map(_source_name_for_segment)
    ),
    "voxel_count": segments_labeled_df["voxel_count"].astype(int),
})

confirmation_template_path = (
    OUTPUT_DIR / "segment_confirmations_required.csv"
)
confirmation_template_df.to_csv(
    confirmation_template_path,
    index=False,
)

semantic_gate_summary = {
    "schema_version": "bricksmart-semantic-gate-1.0",
    "object_type": object_type,
    "segment_count": int(len(segments_labeled_df)),
    "confirmed_or_resolved_count": final_confirmed_count,
    "unknown_count": final_unknown_count,
    "all_unknown": bool(
        len(segments_labeled_df) > 0
        and final_unknown_count == len(segments_labeled_df)
    ),
    "auto_confirm_from_obj_object_names": bool(
        semantics.get(
            "auto_confirm_from_obj_object_names",
            False,
        )
    ),
    "configured_labels_file": semantics.get("labels_file"),
    "manual_label_count": int(
        len(semantics.get("manual_segment_labels", {}))
    ),
    "confirmation_record_count": int(
        len(
            semantics.get(
                "segment_confirmation_records",
                [],
            )
        )
    ),
    "semantic_resolution_audit": str(
        OUTPUT_DIR / "segment_semantic_resolution_audit.csv"
    ),
    "confirmation_template": str(
        confirmation_template_path
    ),
}
(
    OUTPUT_DIR / "segment_semantic_gate_summary.json"
).write_text(
    json.dumps(semantic_gate_summary, indent=2),
    encoding="utf-8",
)

print(
    "Final semantic labels:",
    final_confirmed_count,
    "resolved and",
    final_unknown_count,
    "unknown.",
)
print(
    "Semantic audit:",
    OUTPUT_DIR / "segment_semantic_resolution_audit.csv",
)
print(
    "Confirmation template:",
    confirmation_template_path,
)

if (
    semantics.get(
        "fail_when_all_labels_unknown",
        False,
    )
    and len(segments_labeled_df) > 0
    and final_unknown_count == len(segments_labeled_df)
):
    raise RuntimeError(
        "All segments remain unknown after applying OBJ-name aliases, "
        "the optional labels file, manual labels, and teacher confirmation "
        "records. The runtime wrote a populated confirmation file here: "
        f"{confirmation_template_path}. Fill its confirmed_label column, "
        "set confirmation_status to confirmed, then set "
        "segment_semantics.labels_file in the active task context to "
        "that artifact path and rerun the model."
    )


if (
    'reference_segment_views' in globals()
    and 'reference_segment_colors' in globals()
    and TASK_CONTEXT.get('visualization', {}).get('show_reference_segment_panel', True)
):
    named_legend = create_segment_legend(reference_segment_colors, segment_display_name_by_id)
    for item in reference_segment_views:
        if item.get('view') == 'legend':
            item['image'] = named_legend
    display_multiview(reference_segment_views)


def truthy_catalog_value(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {
        "1", "true", "yes", "y", "enabled",
    }


def catalog_tokens(value):
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = re.split(r"[,;|/]+", str(value))
    return {
        str(item).strip().lower()
        for item in values
        if str(item).strip()
    }


def catalog_clause_matches(record, clause):
    field = clause.get("field")
    operation = clause.get("op", "equals")
    value = record.get(field)

    if operation == "truthy":
        return truthy_catalog_value(value)
    if operation == "equals":
        return str(value).strip().lower() == str(
            clause.get("value", "")
        ).strip().lower()
    if operation == "in":
        allowed = {
            str(item).strip().lower()
            for item in clause.get("values", [])
        }
        return str(value).strip().lower() in allowed
    if operation == "token_any":
        requested = {
            str(item).strip().lower()
            for item in clause.get("values", [])
        }
        return bool(catalog_tokens(value) & requested)
    if operation == "not_in":
        disallowed = {
            str(item).strip().lower()
            for item in clause.get("values", [])
        }
        return str(value).strip().lower() not in disallowed
    raise ValueError(f"Unsupported catalog query operation: {operation}")


def catalog_record_matches(record, query):
    clauses = query.get("all", [])
    return all(
        catalog_clause_matches(record, clause)
        for clause in clauses
    )



# The model task context identifies the exact catalog and its selectors.
CATALOG_SHEET_NAME = CATALOG_SHEET_CONFIG_NAME
MANUAL_PACKING_PRIORITY_OVERRIDES = {}
TASK_CONTEXT_JSON_PATH = MODEL_TASK_CONTEXT_JSON

TASK_CONTEXT_PACKING_PRIORITY_OVERRIDES = {
    str(family): float(value)
    for family, value in TASK_CONTEXT.get(
        "packing_policy",
        {},
    ).get("family_priority_overrides", {}).items()
}

STRUCTURAL_CATALOG_QUERY = TASK_CONTEXT.get(
    "catalog",
    {},
).get(
    "selectors",
    {},
).get(
    "structural",
    {
        "all": [
            {
                "field": "current_solver_enabled",
                "op": "truthy",
            },
            {
                "field": "category",
                "op": "equals",
                "value": "structural_block",
            },
        ]
    },
)


def resolve_block_catalog_path():
    return CATALOG_XLSX_CONFIG_PATH


def xlsx_column_index(cell_reference):
    match = re.match(r"([A-Z]+)", str(cell_reference))
    if match is None:
        raise ValueError(f"Invalid XLSX cell reference: {cell_reference}")

    index = 0
    for character in match.group(1):
        index = index * 26 + ord(character) - 64
    return index - 1


def read_xlsx_sheet_records(path, sheet_name):
    # Read the workbook directly from its ZIP/XML representation so
    # the engine does not require openpyxl for this operation.
    path = Path(path)
    main_namespace = (
        "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    )
    office_relationship_namespace = (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    )
    package_relationship_namespace = (
        "http://schemas.openxmlformats.org/package/2006/relationships"
    )

    with zipfile.ZipFile(path) as archive:
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ET.fromstring(
                archive.read("xl/sharedStrings.xml")
            )
            for string_item in shared_root.findall(
                f"{{{main_namespace}}}si"
            ):
                shared_strings.append(
                    "".join(
                        node.text or ""
                        for node in string_item.iter(
                            f"{{{main_namespace}}}t"
                        )
                    )
                )

        workbook_root = ET.fromstring(
            archive.read("xl/workbook.xml")
        )
        relationship_root = ET.fromstring(
            archive.read("xl/_rels/workbook.xml.rels")
        )
        relationship_targets = {
            relationship.attrib["Id"]: relationship.attrib["Target"]
            for relationship in relationship_root.findall(
                f"{{{package_relationship_namespace}}}Relationship"
            )
        }

        worksheet_path = None
        sheets_node = workbook_root.find(
            f"{{{main_namespace}}}sheets"
        )
        for sheet in sheets_node:
            if sheet.attrib.get("name") != sheet_name:
                continue

            relationship_id = sheet.attrib[
                f"{{{office_relationship_namespace}}}id"
            ]
            target = relationship_targets[relationship_id].lstrip("/")
            worksheet_path = (
                posixpath.normpath(target)
                if target.startswith("xl/")
                else posixpath.normpath(
                    posixpath.join("xl", target)
                )
            )
            break

        if worksheet_path is None:
            raise KeyError(
                f"Worksheet {sheet_name!r} was not found in {path}."
            )

        worksheet_root = ET.fromstring(
            archive.read(worksheet_path)
        )
        row_maps = []
        maximum_column = -1

        for row in worksheet_root.iter(
            f"{{{main_namespace}}}row"
        ):
            values_by_column = {}

            for cell in row.findall(
                f"{{{main_namespace}}}c"
            ):
                reference = cell.attrib.get("r", "")
                column_index = xlsx_column_index(reference)
                maximum_column = max(
                    maximum_column,
                    column_index,
                )

                cell_type = cell.attrib.get("t")
                value_node = cell.find(
                    f"{{{main_namespace}}}v"
                )
                inline_node = cell.find(
                    f"{{{main_namespace}}}is"
                )

                if (
                    cell_type == "inlineStr"
                    and inline_node is not None
                ):
                    value = "".join(
                        node.text or ""
                        for node in inline_node.iter(
                            f"{{{main_namespace}}}t"
                        )
                    )
                elif value_node is None:
                    value = None
                else:
                    raw_value = value_node.text or ""

                    if cell_type == "s":
                        value = shared_strings[int(raw_value)]
                    elif cell_type == "b":
                        value = raw_value == "1"
                    elif cell_type in {"str", "e"}:
                        value = raw_value
                    else:
                        try:
                            number = float(raw_value)
                            value = (
                                int(number)
                                if number.is_integer()
                                else number
                            )
                        except ValueError:
                            value = raw_value

                values_by_column[column_index] = value

            if values_by_column:
                row_maps.append(values_by_column)

    if not row_maps:
        return []

    matrix = [
        [
            row_map.get(column_index)
            for column_index in range(maximum_column + 1)
        ]
        for row_map in row_maps
    ]
    headers = [
        str(value).strip() if value is not None else ""
        for value in matrix[0]
    ]

    records = []
    for values in matrix[1:]:
        record = {
            headers[index]: values[index]
            for index in range(len(headers))
            if headers[index]
        }
        if any(
            value not in {None, ""}
            for value in record.values()
        ):
            records.append(record)

    return records


def catalog_boolean(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, np.integer, np.floating)):
        return bool(value)
    return str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
    }


def catalog_number(value, default=0.0):
    if value in {None, ""}:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def parse_catalog_size(value):
    dimensions = tuple(
        int(number)
        for number in re.findall(r"\d+", str(value))
    )
    if len(dimensions) != 3:
        raise ValueError(
            f"Expected a three-dimensional catalog size, got {value!r}."
        )
    return dimensions


def parse_catalog_faces(value):
    return tuple(
        dict.fromkeys(
            re.findall(r"[+-][XYZ]", str(value or ""))
        )
    )


def catalog_rgb(value):
    try:
        return np.rint(
            np.asarray(to_rgb(str(value).strip())) * 255
        ).astype(int)
    except ValueError as exc:
        raise ValueError(
            f"Unsupported catalog color {value!r}."
        ) from exc


# Face polarity values stored in each catalog-derived face grid.
class FaceType(Enum):
    MALE = 1
    FEMALE = 2
    NONE = 0


# Map catalog-local faces into the world orientation used when a
# native 2×N×2 structural block is stood vertically as 2×2×N.
LOCAL_TO_COLUMN_WORLD_FACE = {
    "+X": "+Y",
    "-X": "-Y",
    "+Y": "+Z",
    "-Y": "-Z",
    "+Z": "+X",
    "-Z": "-X",
}


def face_grid_shape(world_size, face):
    size_x, size_y, size_z = (
        int(value) for value in world_size
    )

    if face in {"+X", "-X"}:
        return size_y, size_z
    if face in {"+Y", "-Y"}:
        return size_x, size_z
    if face in {"+Z", "-Z"}:
        return size_x, size_y
    raise KeyError(face)


def make_catalog_face_template(
    world_size,
    male_faces,
    female_faces,
):
    template = {}

    for face in ["+X", "-X", "+Y", "-Y", "+Z", "-Z"]:
        rows, columns = face_grid_shape(world_size, face)

        if face in male_faces:
            face_type = FaceType.MALE
        elif face in female_faces:
            face_type = FaceType.FEMALE
        else:
            face_type = FaceType.NONE

        template[face] = [
            [face_type for _ in range(columns)]
            for _ in range(rows)
        ]

    return template


# Load all catalog rows, then prepare only enabled structural rows
# that can be used by the current 2×2 vertical-column packer.
CATALOG_XLSX_PATH = resolve_block_catalog_path()
BLOCK_CATALOG_RECORDS = read_xlsx_sheet_records(
    CATALOG_XLSX_PATH,
    CATALOG_SHEET_NAME,
)
BLOCK_CATALOG_BY_FAMILY = {
    str(record["block_family"]).strip(): dict(record)
    for record in BLOCK_CATALOG_RECORDS
    if record.get("block_family")
}

def catalog_priority_missing(
    value,
):
    if value is None:
        return True
    if isinstance(
        value,
        str,
    ):
        return not value.strip()
    if isinstance(
        value,
        (
            float,
            np.floating,
        ),
    ):
        return bool(
            np.isnan(
                value
            )
        )
    return False


def catalog_priority_as_float(
    block_family,
    value,
):
    if catalog_priority_missing(
        value
    ):
        raise ValueError(
            f"{block_family} is enabled for structural packing but "
            "has no numeric default_packing_priority in "
            f"{CATALOG_XLSX_PATH}. Replace the local workbook with "
            "the block_definitions.xlsx supplied in the original workbook."
        )
    try:
        return float(
            value
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            f"{block_family} has non-numeric "
            "default_packing_priority={value!r} in "
            f"{CATALOG_XLSX_PATH}."
        ) from exc


catalog_structural_priority_preflight_rows = []
for preflight_record in BLOCK_CATALOG_RECORDS:
    if not catalog_record_matches(
        preflight_record,
        STRUCTURAL_CATALOG_QUERY,
    ):
        continue

    preflight_family = str(
        preflight_record.get(
            "block_family",
            "",
        )
    ).strip()
    preflight_raw_priority = (
        preflight_record.get(
            "default_packing_priority"
        )
    )
    preflight_numeric_priority = None
    preflight_valid = True
    preflight_reason = "numeric_catalog_value"

    try:
        preflight_numeric_priority = (
            catalog_priority_as_float(
                preflight_family,
                preflight_raw_priority,
            )
        )
    except ValueError as exc:
        preflight_valid = False
        preflight_reason = str(
            exc
        )

    catalog_structural_priority_preflight_rows.append(
        {
            "block_family": preflight_family,
            "raw_default_packing_priority": (
                preflight_raw_priority
            ),
            "numeric_default_packing_priority": (
                preflight_numeric_priority
            ),
            "valid": bool(
                preflight_valid
            ),
            "reason": preflight_reason,
            "catalog_path": str(
                CATALOG_XLSX_PATH
            ),
        }
    )

catalog_structural_priority_preflight_df = pd.DataFrame(
    catalog_structural_priority_preflight_rows
)
catalog_structural_priority_preflight_df.to_csv(
    OUTPUT_DIR
    / "catalog_structural_priority_preflight.csv",
    index=False,
)

invalid_catalog_priority_rows = (
    catalog_structural_priority_preflight_df.loc[
        ~catalog_structural_priority_preflight_df[
            "valid"
        ].astype(
            bool
        )
    ]
)

if not invalid_catalog_priority_rows.empty:
    invalid_families = (
        invalid_catalog_priority_rows[
            "block_family"
        ]
        .astype(
            str
        )
        .tolist()
    )
    raise ValueError(
        "Invalid structural catalog priorities for "
        f"{invalid_families}. Replace "
        f"{CATALOG_XLSX_PATH} with the corrected "
        "block_definitions.xlsx supplied in the original workbook."
    )

STRUCTURAL_CATALOG_RECORDS = []

for catalog_record in BLOCK_CATALOG_RECORDS:
    if not catalog_record_matches(
        catalog_record,
        STRUCTURAL_CATALOG_QUERY,
    ):
        continue

    native_size = parse_catalog_size(
        catalog_record["geometry_size"]
    )
    world_size = (
        int(native_size[2]),
        int(native_size[0]),
        int(native_size[1]),
    )

    if world_size[0:2] != (2, 2):
        raise ValueError(
            "The current column packer requires catalog blocks that "
            f"map to a 2×2 world footprint. "
            f"{catalog_record['block_family']} maps to {world_size}."
        )

    local_male_faces = parse_catalog_faces(
        catalog_record.get("primary_male_faces")
    )
    local_female_faces = parse_catalog_faces(
        catalog_record.get("primary_female_faces")
    )

    if len(local_male_faces) != 1:
        raise ValueError(
            f"{catalog_record['block_family']} must define exactly one "
            f"local male face for this structural planner; found "
            f"{local_male_faces}."
        )

    world_male_faces = tuple(
        LOCAL_TO_COLUMN_WORLD_FACE[face]
        for face in local_male_faces
    )
    world_female_faces = tuple(
        LOCAL_TO_COLUMN_WORLD_FACE[face]
        for face in local_female_faces
    )

    if world_male_faces[0] not in {
        "+X",
        "-X",
        "+Y",
        "-Y",
    }:
        raise ValueError(
            f"{catalog_record['block_family']} does not place its male "
            "face on a horizontal side in the selected column orientation."
        )

    block_family = str(
        catalog_record["block_family"]
    ).strip()
    default_priority_value = catalog_record.get(
        "default_packing_priority"
    )
    default_packing_priority = (
        catalog_priority_as_float(
            block_family,
            default_priority_value,
        )
    )

    if block_family in MANUAL_PACKING_PRIORITY_OVERRIDES:
        effective_packing_priority = (
            MANUAL_PACKING_PRIORITY_OVERRIDES[
                block_family
            ]
        )
        packing_priority_source = "manual_override"
    elif block_family in TASK_CONTEXT_PACKING_PRIORITY_OVERRIDES:
        effective_packing_priority = (
            TASK_CONTEXT_PACKING_PRIORITY_OVERRIDES[
                block_family
            ]
        )
        packing_priority_source = "task_context_override"
    else:
        effective_packing_priority = (
            default_packing_priority
        )
        packing_priority_source = "catalog_default"

    prepared_record = dict(catalog_record)
    prepared_record.update({
        "native_size": native_size,
        "column_world_size": world_size,
        "column_height": int(world_size[2]),
        "column_world_male_faces": world_male_faces,
        "column_world_female_faces": world_female_faces,
        "color_rgb": catalog_rgb(catalog_record["color"]),
        "default_packing_priority": default_packing_priority,
        "effective_packing_priority": effective_packing_priority,
        "packing_priority_source": packing_priority_source,
    })
    STRUCTURAL_CATALOG_RECORDS.append(prepared_record)

if not STRUCTURAL_CATALOG_RECORDS:
    raise RuntimeError(
        "No enabled structural_block rows were found in "
        f"{CATALOG_XLSX_PATH}."
    )

enabled_structural_families = {
    record["block_family"]
    for record in STRUCTURAL_CATALOG_RECORDS
}
override_families = (
    set(TASK_CONTEXT_PACKING_PRIORITY_OVERRIDES)
    | set(MANUAL_PACKING_PRIORITY_OVERRIDES)
)
unknown_override_families = sorted(
    override_families - enabled_structural_families
)
if unknown_override_families:
    raise KeyError(
        "Packing-priority overrides reference families that are not "
        "enabled structural catalog families: "
        f"{unknown_override_families}"
    )

# Build lookup tables used by packing, rotation, visualization, and
# output generation. One enabled structural family is expected for
# each supported column height.
STRUCTURAL_CATALOG_BY_FAMILY = {
    record["block_family"]: record
    for record in STRUCTURAL_CATALOG_RECORDS
}
STRUCTURAL_CATALOG_BY_HEIGHT = {}
STRUCTURAL_CATALOG_BY_WORLD_SIZE = {}

for record in STRUCTURAL_CATALOG_RECORDS:
    height = int(record["column_height"])
    world_size = tuple(record["column_world_size"])

    if height in STRUCTURAL_CATALOG_BY_HEIGHT:
        raise ValueError(
            "The current height-based column planner requires one "
            f"enabled structural catalog family per column height. "
            f"Height {height} is duplicated."
        )

    if world_size in STRUCTURAL_CATALOG_BY_WORLD_SIZE:
        raise ValueError(
            f"World size {world_size} is duplicated in the enabled "
            "structural catalog."
        )

    STRUCTURAL_CATALOG_BY_HEIGHT[height] = record
    STRUCTURAL_CATALOG_BY_WORLD_SIZE[world_size] = record

BLOCK_HEIGHTS = sorted(
    STRUCTURAL_CATALOG_BY_HEIGHT,
    reverse=True,
)
BLOCK_FAMILY_BY_HEIGHT = {
    height: record["block_family"]
    for height, record in STRUCTURAL_CATALOG_BY_HEIGHT.items()
}
BLOCK_TYPE_COLORS = {
    height: np.asarray(record["color_rgb"], dtype=int)
    for height, record in STRUCTURAL_CATALOG_BY_HEIGHT.items()
}
EFFECTIVE_PACKING_PRIORITY_BY_HEIGHT = {
    height: float(record["effective_packing_priority"])
    for height, record in STRUCTURAL_CATALOG_BY_HEIGHT.items()
}
COLUMN_BASE_MALE_FACE_BY_SIZE = {
    tuple(record["column_world_size"]): record[
        "column_world_male_faces"
    ][0]
    for record in STRUCTURAL_CATALOG_RECORDS
}
BLOCK_FACE_TEMPLATES = {
    tuple(record["column_world_size"]): make_catalog_face_template(
        record["column_world_size"],
        record["column_world_male_faces"],
        record["column_world_female_faces"],
    )
    for record in STRUCTURAL_CATALOG_RECORDS
}

# Connector and functional families are selected by catalog
# metadata queries from the task context. No family aliases are
# hard-coded in the earlier prototype.
CONNECTOR_FAMILY_ALIASES = {}
CONNECTOR_COLORS = {}

if log_enabled(
    "show_catalog_details"
):
    print(f"Loaded block catalog: {CATALOG_XLSX_PATH}")
    print("Enabled structural column blocks:")
    for record in sorted(
        STRUCTURAL_CATALOG_RECORDS,
        key=lambda item: item["column_height"],
    ):
        print(
            f"- {record['block_family']}: native "
            f"{record['native_size']} -> world "
            f"{record['column_world_size']}; "
            f"male {record['column_world_male_faces'][0]}; "
            f"color {record['color']}; "
            f"default priority "
            f"{record['default_packing_priority']}; "
            f"effective priority "
            f"{record['effective_packing_priority']} "
            f"({record['packing_priority_source']})"
        )

    print(
        "Task context for packing-priority overrides:",
        TASK_CONTEXT_JSON_PATH or "none",
    )


CATALOG_CONFIG = TASK_CONTEXT.get("catalog", {})
CATALOG_REQUIRED_COLUMNS = CATALOG_CONFIG.get(
    "required_columns",
    [],
)
catalog_columns = {
    str(key)
    for record in BLOCK_CATALOG_RECORDS
    for key in record
}
missing_catalog_columns = sorted(
    set(CATALOG_REQUIRED_COLUMNS) - catalog_columns
)

catalog_preflight = {
    "catalog_xlsx": str(CATALOG_XLSX_PATH),
    "catalog_sheet": CATALOG_SHEET_NAME,
    "row_count": len(BLOCK_CATALOG_RECORDS),
    "missing_required_columns": missing_catalog_columns,
    "structural_family_count": len(STRUCTURAL_CATALOG_RECORDS),
}
(OUTPUT_DIR / "catalog_preflight.json").write_text(
    json.dumps(catalog_preflight, indent=2),
    encoding="utf-8",
)

if missing_catalog_columns:
    raise ValueError(
        "The catalog is missing segment-assembly metadata columns: "
        f"{missing_catalog_columns}. "
        "Add the columns to the catalog rather than hard-coding "
        "block families in the runtime."
    )

emit_diagnostic(pd.DataFrame(STRUCTURAL_CATALOG_RECORDS))


# ============================================================
# Finite-inventory coordination layer
# ============================================================
PROJECT_ROOT = RUNTIME_WORKING_DIR.parent.resolve()
PROJECT_SRC = PROJECT_ROOT / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from bricksmart_inventory.inventory import (
    InventoryError,
    InventoryExhaustedError,
    InventoryLedger,
    block_family_counts,
    load_inventory_profile,
    validate_inventory_profile,
)

INVENTORY_CONFIG = TASK_CONTEXT.get("inventory", {})
INVENTORY_ENFORCED = bool(INVENTORY_CONFIG.get("enforce", True))
INVENTORY_PROFILE_PATH = resolve_path(
    os.environ.get("BRICKSMART_INVENTORY_PROFILE")
    or INVENTORY_CONFIG.get(
        "profile_path",
        "../config/inventory/standard_kit.yaml",
    ),
    RUNTIME_WORKING_DIR,
)
INVENTORY_PROFILE = load_inventory_profile(INVENTORY_PROFILE_PATH)
INVENTORY_CATALOG_PREFLIGHT = validate_inventory_profile(
    INVENTORY_PROFILE,
    BLOCK_CATALOG_BY_FAMILY,
)
INVENTORY_LEDGER = InventoryLedger(INVENTORY_PROFILE)
INVENTORY_COORDINATION_MODE = str(
    INVENTORY_CONFIG.get("coordination_mode", "sequential_commit")
).strip().lower()
GLOBAL_DEFERRED_INVENTORY = INVENTORY_COORDINATION_MODE in {
    "global_deferred", "global_allocate_then_commit"
}
PENDING_INVENTORY_REQUIREMENTS = []

(OUTPUT_DIR / "inventory_catalog_preflight.json").write_text(
    json.dumps(
        {
            **INVENTORY_CATALOG_PREFLIGHT,
            "inventory_profile_path": str(INVENTORY_PROFILE_PATH),
            "catalog_path": str(CATALOG_XLSX_PATH),
            "enforced": INVENTORY_ENFORCED,
        },
        indent=2,
    ),
    encoding="utf-8",
)
(OUTPUT_DIR / "effective_inventory.json").write_text(
    json.dumps(
        {
            "inventory_id": INVENTORY_PROFILE.inventory_id,
            "inventory_mode": INVENTORY_PROFILE.mode,
            "blocks": INVENTORY_PROFILE.blocks,
            "enforced": INVENTORY_ENFORCED,
        },
        indent=2,
    ),
    encoding="utf-8",
)


def inventory_check_blocks(blocks, multiplier=1):
    requirements = block_family_counts(
        blocks,
        multiplier=int(multiplier),
    )
    # In global-deferred mode every mechanically valid candidate is checked
    # against the full kit capacity, not against inventory consumed by an
    # earlier segment. The model-wide allocator commits only after all
    # segment candidates have been generated.
    check_ledger = (
        InventoryLedger(INVENTORY_PROFILE)
        if GLOBAL_DEFERRED_INVENTORY
        else INVENTORY_LEDGER
    )
    check = check_ledger.check(requirements)
    if not INVENTORY_ENFORCED:
        check = {
            **check,
            "feasible": True,
            "shortages": {},
        }
    return requirements, check


def inventory_requirements_from_results(results):
    blocks = []
    for result in results:
        if result and result.get("valid", False):
            blocks.extend(
                result.get("planning_result", {}).get("blocks", [])
            )
    return block_family_counts(blocks)


def inventory_commit_results_atomic(results, scope):
    requirements = inventory_requirements_from_results(results)
    if not requirements:
        return None, requirements
    if GLOBAL_DEFERRED_INVENTORY:
        PENDING_INVENTORY_REQUIREMENTS.append({
            "scope": str(scope),
            "requirements": dict(requirements),
        })
        return f"deferred:{scope}", requirements
    reservation_id = INVENTORY_LEDGER.reserve_and_commit(
        requirements,
        scope,
    )
    return reservation_id, requirements

print(
    "Inventory profile:",
    INVENTORY_PROFILE.inventory_id,
    "mode=",
    INVENTORY_PROFILE.mode,
    "enforced=",
    INVENTORY_ENFORCED,
    "coordination=",
    INVENTORY_COORDINATION_MODE,
)



class BlockInstance:
    def __init__(
        self,
        position,
        size,
        base_color,
        block_id,
        rotation=0,
        category="structural",
        connector_type=None,
        segment_a=None,
        segment_b=None,
        block_family=None,
    ):
        self.position = tuple(int(value) for value in position)
        self.size = tuple(int(value) for value in size)
        self.block_id = int(block_id)
        self.rotation = int(rotation) % 360
        self.category = category
        self.connector_type = connector_type
        self.segment_a = segment_a
        self.segment_b = segment_b

        catalog_record = None

        if category == "structural":
            if block_family is None:
                catalog_record = (
                    STRUCTURAL_CATALOG_BY_WORLD_SIZE.get(
                        self.size
                    )
                )
                if catalog_record is None:
                    raise KeyError(
                        "No enabled structural catalog row maps to "
                        f"world size {self.size}."
                    )
                block_family = catalog_record["block_family"]
            else:
                catalog_record = STRUCTURAL_CATALOG_BY_FAMILY.get(
                    block_family
                )
        elif block_family is None and connector_type is not None:
            raise ValueError(
                "Connector block_family must come from a catalog query; "
                "connector aliases are not used."
            )
        elif block_family is not None:
            catalog_record = BLOCK_CATALOG_BY_FAMILY.get(
                block_family
            )

        self.block_family = block_family
        self.catalog_record = catalog_record
        self.catalog_category = (
            catalog_record.get("category")
            if catalog_record is not None
            else None
        )
        self.native_size = (
            tuple(catalog_record["native_size"])
            if catalog_record is not None
            and "native_size" in catalog_record
            else None
        )
        self.base_color = (
            np.asarray(
                catalog_record["color_rgb"],
                dtype=int,
            )
            if category == "structural"
            and catalog_record is not None
            else base_color
        )

        face_template = BLOCK_FACE_TEMPLATES.get(
            self.size
        )
        self.faces = (
            copy.deepcopy(face_template)
            if face_template is not None
            else None
        )

        if self.faces is not None and self.rotation != 0:
            self.faces = self.rotate_faces(
                self.faces,
                self.rotation,
            )

    def rotate_faces(self, faces, rotation):
        rotation = int(rotation) % 360
        if rotation % 90 != 0:
            raise ValueError(
                "Structural rotations must be multiples of 90 degrees."
            )

        def rotate_matrix(matrix, quarter_turns):
            return np.rot90(
                matrix,
                -quarter_turns,
                axes=(1, 0),
            ).tolist()

        rotated_faces = {}
        quarter_turns = rotation // 90
        face_order = ["+X", "+Y", "-X", "-Y"]

        for index, face in enumerate(face_order):
            rotated_faces[
                face_order[(index + quarter_turns) % 4]
            ] = rotate_matrix(
                faces[face],
                quarter_turns,
            )

        rotated_faces["+Z"] = copy.deepcopy(faces["+Z"])
        rotated_faces["-Z"] = copy.deepcopy(faces["-Z"])
        return rotated_faces


def coords_to_voxel_grid(coords, grid_size=None):
    import numpy as np

    if grid_size is None:
        max_x = max(c[0] for c in coords) + 1
        max_y = max(c[1] for c in coords) + 1
        max_z = max(c[2] for c in coords) + 1
    else:
        max_x, max_y, max_z = grid_size, grid_size, grid_size

    grid = np.zeros((max_x, max_y, max_z), dtype=int)

    for x, y, z in coords:
        grid[x, y, z] = 1

    return grid

def voxel_to_2x2_columns(voxel_matrix):
    sx, sy, sz = voxel_matrix.shape
    columns = {}
    for x in range(0, sx-1, 2):
        for y in range(0, sy-1, 2):
            sub = voxel_matrix[x:x+2, y:y+2, :]
            occupancy = np.sum((sub > 0), axis=(0,1))
            mask = occupancy > 0
            filled = np.where(mask)[0]
            if len(filled) == 0: continue
            # split contiguous
            start = prev = filled[0]
            segments = []
            for i in filled[1:]:
                if i == prev+1:
                    prev = i
                else:
                    segments.append((start, prev))
                    start = prev = i
            segments.append((start, prev))
            for z_min, z_max in segments:
                height = z_max - z_min + 1
                if height < 2: continue
                color = int(np.bincount(sub[:,:,z_min].flatten()[sub[:,:,z_min].flatten()>0]).argmax())
                columns[(x, y, z_min)] = {"z_min": z_min, "height": height, "color": color}
    return columns

def build_block_grid(blocks, grid_size):

    grid = np.full(
        (grid_size, grid_size, grid_size),
        fill_value=-1
    )

    for block in blocks:

        x, y, z = block.position
        dx, dy, dz = block.size

        # connectors do NOT overwrite structure
        if getattr(block, "category", None) == "connector":

            continue

        grid[
            x:x+dx,
            y:y+dy,
            z:z+dz
        ] = block.block_id

    return grid

def build_neighbor_map(blocks, grid_size):
    """
    Creates a robust connection map for assembly instructions.

    Each block records:
      - 'support': blocks directly beneath it (Z- direction)
      - 'side': blocks adjacent in X/Y directions (optional for stability)

    This version ignores strict male/female matching to ensure no missing connections.
    """
    # Create a 3D lookup grid of block IDs
    grid = np.full((grid_size, grid_size, grid_size), fill_value=-1)
    for block in blocks:
        x, y, z = block.position
        dx, dy, dz = block.size
        grid[x:x+dx, y:y+dy, z:z+dz] = block.block_id

    connection_map = {}

    for block in blocks:
        support_neighbors = set()
        side_neighbors = set()
        x0, y0, z0 = block.position
        dx, dy, dz = block.size

        # Check all 6 directions for adjacent blocks
        directions = {
            "+X": (1,0,0), "-X": (-1,0,0),
            "+Y": (0,1,0), "-Y": (0,-1,0),
            "+Z": (0,0,1), "-Z": (0,0,-1)
        }

        for face, (dx_off, dy_off, dz_off) in directions.items():
            # Determine search region
            nx_start = max(0, x0 + (dx_off>0)*dx + (dx_off<0)*-1)
            ny_start = max(0, y0 + (dy_off>0)*dy + (dy_off<0)*-1)
            nz_start = max(0, z0 + (dz_off>0)*dz + (dz_off<0)*-1)

            nx_end = min(grid_size, nx_start + dx)
            ny_end = min(grid_size, ny_start + dy)
            nz_end = min(grid_size, nz_start + dz)

            region = grid[nx_start:nx_end, ny_start:ny_end, nz_start:nz_end]
            for nid in set(region.flatten()):
                if nid == -1 or nid == block.block_id:
                    continue
                # Assign vertical support vs side adjacency
                if dz_off == -1:  # block below
                    support_neighbors.add(nid)
                elif dz_off == 0:  # side neighbors
                    side_neighbors.add(nid)

        connection_map[block.block_id] = {
            "support": list(support_neighbors),
            "side": list(side_neighbors)
        }

    return connection_map


def get_block_color(block):
    catalog_record = getattr(
        block,
        "catalog_record",
        None,
    )

    if catalog_record is not None:
        if "color_rgb" in catalog_record:
            return np.asarray(
                catalog_record["color_rgb"],
                dtype=int,
            )
        if catalog_record.get("color"):
            return catalog_rgb(catalog_record["color"])

    if getattr(block, "category", None) == "connector":
        return CONNECTOR_COLORS.get(
            block.connector_type,
            np.array([255, 255, 255]),
        )

    if isinstance(block.base_color, np.ndarray):
        return block.base_color

    if isinstance(
        block.base_color,
        (int, float, np.integer, np.floating),
    ):
        if block.base_color == 99:
            return np.array([180, 180, 180])

        return BLOCK_TYPE_COLORS.get(
            int(block.size[2]),
            np.array([200, 200, 200]),
        )

    return np.array([200, 200, 200])


def to_visual_coords(x, y, z):
    # For visualizations, swapping y and z
    return x, z, y


def visualize_blocks_by_type(
    blocks,
    grid_size,
    elev=30,
    azim=45,
):
    """Model-neutral full-color static block view."""
    return visualize_blocks_static(
        blocks,
        grid_size=grid_size,
        elev=elev,
        azim=azim,
        show_faces=False,
        title="Catalog-Colored Block Plan",
    )



def visualize_blocks_with_faces(
    blocks,
    neighbor_map,
    grid_size,
    elev=25,
    azim=45,
):
    """Model-neutral full-color face-audit view."""
    return visualize_blocks_static(
        blocks,
        grid_size=grid_size,
        elev=elev,
        azim=azim,
        show_faces=True,
        title="Block Plan with Male/Female Faces",
    )



from dataclasses import dataclass, asdict
from collections import defaultdict
from itertools import product
from pathlib import Path
import copy
import json
import math
import time
import numpy as np
import pandas as pd


BETTER_PLANNER_OUTPUT_DIR = OUTPUT_DIR / "_planner_shared"
BETTER_PLANNER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class BetterPlannerConfig:
    """Search limits and ordered planning preferences."""


    # Column decomposition search.

    per_column_sequence_limit: int = 12
    max_extra_blocks_per_column: int = 1
    row_packing_beam_width: int = 12


    # Rotation search.

    exact_rotation_search_limit: int = 6
    rotation_beam_width: int = 1024
    rotation_solutions_per_row: int = 3


    # Cumulative row-state search.

    plan_beam_width: int = 6


    prefer_effective_packing_priority: bool = True
    # Secondary objectives after buildability.

    minimize_exposed_male_area: bool = True
    prefer_forward_female_frontier: bool = True


    # Build order.

    build_axis: str = "+Y"


    # Diagnostics.

    fail_when_no_valid_row_state: bool = True


# Balanced fast mode.
#
# The original broad settings can evaluate tens or hundreds of thousands of
# complete rotation assignments per row. These settings preserve row-aware
# packing, locking-path validation, next-row lookahead, and exposed-male-face
# scoring while reducing the candidate set substantially.

BETTER_PLANNER_CONFIG = BetterPlannerConfig(
    per_column_sequence_limit=4,
    max_extra_blocks_per_column=0,
    row_packing_beam_width=4,
    exact_rotation_search_limit=4,
    rotation_beam_width=128,
    rotation_solutions_per_row=2,
    plan_beam_width=3,
)


HORIZONTAL_FACES = ("+X", "+Y", "-X", "-Y")
ALL_FACES = ("+X", "-X", "+Y", "-Y", "+Z", "-Z")
OPPOSITE_FACE = {
    "+X": "-X",
    "-X": "+X",
    "+Y": "-Y",
    "-Y": "+Y",
    "+Z": "-Z",
    "-Z": "+Z",
}


def normalized_rotation(rotation):
    return (int(rotation) // 90 % 4) * 90


def rotate_horizontal_face(face, rotation):
    if face not in HORIZONTAL_FACES:
        return face

    quarter_turns = normalized_rotation(rotation) // 90
    start_index = HORIZONTAL_FACES.index(face)
    return HORIZONTAL_FACES[
        (start_index + quarter_turns) % 4
    ]


def male_face_for_rotation(rotation, block_size=None):
    if block_size is None:
        base_male_face = "+X"
    else:
        block_size = tuple(int(value) for value in block_size)
        base_male_face = COLUMN_BASE_MALE_FACE_BY_SIZE[
            block_size
        ]

    return rotate_horizontal_face(
        base_male_face,
        rotation,
    )


def face_type_for_rotation(face, rotation, block_size):
    return (
        "male"
        if face == male_face_for_rotation(
            rotation,
            block_size,
        )
        else "female"
    )


def apply_structural_rotation(block, rotation):
    """Apply a 0/90/180/270-degree Z rotation to one structural block."""
    rotation = normalized_rotation(rotation)
    template = BLOCK_FACE_TEMPLATES.get(tuple(block.size))

    if template is None:
        raise KeyError(
            f"No structural face template for block size {tuple(block.size)}"
        )

    block.rotation = rotation
    block.faces = block.rotate_faces(template, rotation)
    return block


def block_bounds(block):
    x0, y0, z0 = (int(v) for v in block.position)
    dx, dy, dz = (int(v) for v in block.size)
    return x0, x0 + dx, y0, y0 + dy, z0, z0 + dz


def positive_overlap(a0, a1, b0, b1):
    return max(0, min(a1, b1) - max(a0, b0))


def face_area(block, face):
    dx, dy, dz = (int(v) for v in block.size)

    if face in {"+X", "-X"}:
        return dy * dz
    if face in {"+Y", "-Y"}:
        return dx * dz
    if face in {"+Z", "-Z"}:
        return dx * dy

    raise KeyError(face)


def touching_face_geometry(block_a, block_b):
    """
    Return exact shared faces and overlap area for axis-aligned blocks.

    This is geometry-only. Face polarity is evaluated separately for each
    candidate rotation assignment.
    """
    ax0, ax1, ay0, ay1, az0, az1 = block_bounds(block_a)
    bx0, bx1, by0, by1, bz0, bz1 = block_bounds(block_b)

    ox = positive_overlap(ax0, ax1, bx0, bx1)
    oy = positive_overlap(ay0, ay1, by0, by1)
    oz = positive_overlap(az0, az1, bz0, bz1)


    # Positive-volume overlap is an invalid placement.

    if ox > 0 and oy > 0 and oz > 0:
        return {
            "block_a": int(block_a.block_id),
            "block_b": int(block_b.block_id),
            "face_a": None,
            "face_b": None,
            "overlap_area": None,
            "geometry_status": "geometric_overlap_conflict",
        }

    if ax1 == bx0 and oy > 0 and oz > 0:
        return {
            "block_a": int(block_a.block_id),
            "block_b": int(block_b.block_id),
            "face_a": "+X",
            "face_b": "-X",
            "overlap_area": int(oy * oz),
            "geometry_status": "face_contact",
        }

    if bx1 == ax0 and oy > 0 and oz > 0:
        return {
            "block_a": int(block_a.block_id),
            "block_b": int(block_b.block_id),
            "face_a": "-X",
            "face_b": "+X",
            "overlap_area": int(oy * oz),
            "geometry_status": "face_contact",
        }

    if ay1 == by0 and ox > 0 and oz > 0:
        return {
            "block_a": int(block_a.block_id),
            "block_b": int(block_b.block_id),
            "face_a": "+Y",
            "face_b": "-Y",
            "overlap_area": int(ox * oz),
            "geometry_status": "face_contact",
        }

    if by1 == ay0 and ox > 0 and oz > 0:
        return {
            "block_a": int(block_a.block_id),
            "block_b": int(block_b.block_id),
            "face_a": "-Y",
            "face_b": "+Y",
            "overlap_area": int(ox * oz),
            "geometry_status": "face_contact",
        }

    if az1 == bz0 and ox > 0 and oy > 0:
        return {
            "block_a": int(block_a.block_id),
            "block_b": int(block_b.block_id),
            "face_a": "+Z",
            "face_b": "-Z",
            "overlap_area": int(ox * oy),
            "geometry_status": "face_contact",
        }

    if bz1 == az0 and ox > 0 and oy > 0:
        return {
            "block_a": int(block_a.block_id),
            "block_b": int(block_b.block_id),
            "face_a": "-Z",
            "face_b": "+Z",
            "overlap_area": int(ox * oy),
            "geometry_status": "face_contact",
        }

    return None


def geometry_contacts(blocks_a, blocks_b=None):
    rows = []

    if blocks_b is None:
        for i in range(len(blocks_a)):
            for j in range(i + 1, len(blocks_a)):
                row = touching_face_geometry(blocks_a[i], blocks_a[j])
                if row is not None:
                    rows.append(row)
        return rows

    for block_a in blocks_a:
        for block_b in blocks_b:
            if int(block_a.block_id) == int(block_b.block_id):
                continue

            row = touching_face_geometry(block_a, block_b)
            if row is not None:
                rows.append(row)

    return rows


def classify_face_types(type_a, type_b):
    if {type_a, type_b} == {"male", "female"}:
        return "male_to_female_lock"
    if type_a == "male" and type_b == "male":
        return "male_to_male_conflict"
    if type_a == "female" and type_b == "female":
        return "female_to_female_nonlocking"
    return "unresolved_or_none"


def actual_block_face_type(block, face):
    template = None if block.faces is None else block.faces.get(face)

    if template is None:
        return "none"

    values = list(np.asarray(template, dtype=object).ravel())
    has_male = any(v == FaceType.MALE for v in values)
    has_female = any(v == FaceType.FEMALE for v in values)

    if has_male and has_female:
        return "mixed"
    if has_male:
        return "male"
    if has_female:
        return "female"
    return "none"


def contact_with_assignment(
    geometry_row,
    current_ids,
    assignment,
    block_lookup,
):
    """Add polarity and status to one geometry-only contact record."""
    row = dict(geometry_row)

    if row["geometry_status"] == "geometric_overlap_conflict":
        row.update({
            "face_type_a": "overlap",
            "face_type_b": "overlap",
            "contact_status": "geometric_overlap_conflict",
        })
        return row

    a = int(row["block_a"])
    b = int(row["block_b"])

    if a in current_ids:
        type_a = face_type_for_rotation(
            row["face_a"],
            assignment[a],
            block_lookup[a].size,
        )
    else:
        type_a = actual_block_face_type(
            block_lookup[a],
            row["face_a"],
        )

    if b in current_ids:
        type_b = face_type_for_rotation(
            row["face_b"],
            assignment[b],
            block_lookup[b].size,
        )
    else:
        type_b = actual_block_face_type(
            block_lookup[b],
            row["face_b"],
        )

    row.update({
        "face_type_a": type_a,
        "face_type_b": type_b,
        "contact_status": classify_face_types(type_a, type_b),
    })
    return row


def sequence_internal_seams(column_key, sequence):
    """Absolute Z seam locations, excluding the top of the column."""
    _, _, z_min = column_key
    seams = set()
    z = int(z_min)

    for height in sequence[:-1]:
        z += int(height)
        seams.add(z)

    return seams

PACKING_POLICY_CONFIG = (
    TASK_CONTEXT.get("packing_policy", {})
    if isinstance(TASK_CONTEXT, dict)
    else {}
)
PREFER_LARGER_BLOCKS_ON_TIES = bool(
    PACKING_POLICY_CONFIG.get(
        "prefer_larger_blocks_on_ties",
        False,
    )
)
ENABLE_SEGMENT_LOCAL_CONSOLIDATION = bool(
    PACKING_POLICY_CONFIG.get(
        "enable_segment_local_consolidation",
        False,
    )
)


def larger_block_tie_break_key(sequence):
    sequence = tuple(int(height) for height in sequence)
    if not PREFER_LARGER_BLOCKS_ON_TIES:
        return tuple()
    ordered_heights = sorted(
        {int(height) for height in BLOCK_HEIGHTS},
        reverse=True,
    )
    counts = tuple(
        -sum(
            1
            for value in sequence
            if int(value) == int(height)
        )
        for height in ordered_heights
    )
    return counts + (
        -sum(int(value) ** 2 for value in sequence),
    ) + tuple(-int(value) for value in sequence)



def all_unique_sequences_for_height(height):
    """Generate ordered 2/3/4-height decompositions without duplicates."""
    height = int(height)
    results = set()

    def visit(remaining, path):
        if remaining == 0:
            results.add(tuple(path))
            return
        if remaining < 0:
            return

        for block_height in BLOCK_HEIGHTS:
            visit(
                remaining - int(block_height),
                path + [int(block_height)],
            )

    visit(height, [])
    return sorted(
        results,
        key=lambda sequence: (
            len(sequence),
            -sum(
                EFFECTIVE_PACKING_PRIORITY_BY_HEIGHT[
                    int(item_height)
                ]
                for item_height in sequence
            ),
            larger_block_tie_break_key(sequence),
            sequence,
        ),
    )


def sequence_options_for_column(height, config):
    all_sequences = all_unique_sequences_for_height(height)

    if not all_sequences:
        return []

    minimum_count = min(len(seq) for seq in all_sequences)
    maximum_count = (
        minimum_count
        + max(0, int(config.max_extra_blocks_per_column))
    )

    filtered = [
        seq
        for seq in all_sequences
        if len(seq) <= maximum_count
    ]

    return filtered[: max(1, int(config.per_column_sequence_limit))]


def fixed_column_minimum_block_count(columns):
    total = 0
    per_column = {}

    for key, data in columns.items():
        options = all_unique_sequences_for_height(data["height"])

        if not options:
            raise ValueError(
                f"Column {key} with height {data['height']} cannot be "
                f"filled exactly using catalog heights {BLOCK_HEIGHTS}."
            )

        minimum = min(len(seq) for seq in options)
        per_column[key] = minimum
        total += minimum

    return total, per_column


def group_columns_by_row(columns):
    grouped = defaultdict(dict)

    for key, data in columns.items():
        x, y, z_min = key
        grouped[int(y)][(int(x), int(y), int(z_min))] = dict(data)

    return {
        row: grouped[row]
        for row in sorted(grouped)
    }


def count_aligned_seams(
    column_key,
    sequence,
    current_assignment,
    previous_row_assignment,
):
    candidate_seams = sequence_internal_seams(
        column_key,
        sequence,
    )
    x, y, _ = column_key

    aligned = 0
    staggered = 0


    # Compare against already assigned X-adjacent columns in this row.

    for other_key, other_sequence in current_assignment.items():
        ox, oy, _ = other_key
        if oy == y and abs(ox - x) == 2:
            other_seams = sequence_internal_seams(
                other_key,
                other_sequence,
            )
            aligned += len(candidate_seams & other_seams)
            staggered += len(candidate_seams ^ other_seams)


    # Compare against columns at the same X in the previously planned row.

    for other_key, other_sequence in previous_row_assignment.items():
        ox, _, _ = other_key
        if ox == x:
            other_seams = sequence_internal_seams(
                other_key,
                other_sequence,
            )
            aligned += len(candidate_seams & other_seams)
            staggered += len(candidate_seams ^ other_seams)

    return aligned, staggered


def generate_row_packing_variants(
    row_columns,
    previous_row_assignment,
    config,
):
    """
    Beam-search column decompositions inside one Y row.

    The search keeps the lowest block-count variants while retaining a few
    seam alternatives for downstream buildability.
    """
    ordered_keys = sorted(
        row_columns,
        key=lambda key: (key[0], key[2]),
    )

    beam = [{
        "assignment": {},
        "block_count": 0,
        "aligned_seams": 0,
        "staggered_seams": 0,
        "catalog_preference_score": 0,
    }]

    for column_key in ordered_keys:
        options = sequence_options_for_column(
            row_columns[column_key]["height"],
            config,
        )

        if not options:
            raise ValueError(
                f"No legal block sequence for column {column_key}."
            )

        expanded = []

        for state in beam:
            for sequence in options:
                assignment = dict(state["assignment"])
                assignment[column_key] = tuple(sequence)

                aligned, staggered = count_aligned_seams(
                    column_key,
                    sequence,
                    state["assignment"],
                    previous_row_assignment,
                )

                sequence_preference = (
                    sum(
                        EFFECTIVE_PACKING_PRIORITY_BY_HEIGHT[
                            int(height)
                        ]
                        for height in sequence
                    )
                    if config.prefer_effective_packing_priority
                    else 0.0
                )

                expanded.append({
                    "assignment": assignment,
                    "block_count": (
                        state["block_count"] + len(sequence)
                    ),
                    "aligned_seams": (
                        state["aligned_seams"] + aligned
                    ),
                    "staggered_seams": (
                        state["staggered_seams"] + staggered
                    ),
                    "catalog_preference_score": (
                        state["catalog_preference_score"]
                        + sequence_preference
                    ),
                })

        expanded.sort(
            key=lambda item: (
                item["block_count"],
                item["aligned_seams"],
                -item["staggered_seams"],
                -item["catalog_preference_score"],
                tuple(
                    (
                        key,
                        item["assignment"][key],
                    )
                    for key in sorted(item["assignment"])
                ),
            )
        )

        beam = expanded[
            : max(1, int(config.row_packing_beam_width))
        ]

    return beam


def build_row_blocks_from_assignment(
    row_columns,
    assignment,
    next_block_id,
):
    row_blocks = []
    block_id = int(next_block_id)

    for column_key in sorted(
        assignment,
        key=lambda key: (key[0], key[2]),
    ):
        x, y, z_min = column_key
        column_data = row_columns[column_key]
        current_z = int(z_min)

        for height in assignment[column_key]:
            catalog_record = STRUCTURAL_CATALOG_BY_HEIGHT[
                int(height)
            ]
            block = BlockInstance(
                position=(int(x), int(y), int(current_z)),
                size=tuple(
                    catalog_record["column_world_size"]
                ),
                base_color=catalog_record["color_rgb"],
                block_id=block_id,
                rotation=0,
                block_family=catalog_record["block_family"],
            )
            row_blocks.append(block)
            block_id += 1
            current_z += int(height)

    return row_blocks, block_id


def locking_reachable_ids(
    current_ids,
    internal_lock_edges,
    seed_ids,
):
    adjacency = {
        int(block_id): set()
        for block_id in current_ids
    }

    for a, b in internal_lock_edges:
        a = int(a)
        b = int(b)
        adjacency[a].add(b)
        adjacency[b].add(a)

    reachable = set(int(v) for v in seed_ids)
    stack = list(sorted(reachable))

    while stack:
        current = stack.pop()

        for neighbor in sorted(adjacency.get(current, ())):
            if neighbor not in reachable:
                reachable.add(neighbor)
                stack.append(neighbor)

    return reachable


def best_root_reachable_ids(
    current_ids,
    internal_lock_edges,
):
    """
    The first row gets one exempt root block.

    Select the root whose male-to-female locking component contains the
    greatest number of current-row blocks.
    """
    best_root = None
    best_reachable = set()

    for root_id in sorted(current_ids):
        reachable = locking_reachable_ids(
            current_ids,
            internal_lock_edges,
            {root_id},
        )

        if (
            len(reachable) > len(best_reachable)
            or (
                len(reachable) == len(best_reachable)
                and (
                    best_root is None
                    or int(root_id) < int(best_root)
                )
            )
        ):
            best_root = int(root_id)
            best_reachable = reachable

    return best_root, best_reachable

def allow_multiple_root_components():
    return bool(
        TASK_CONTEXT.get(
            "segment_assembly",
            {},
        )
        .get(
            "segment_packing",
            {},
        )
        .get(
            "allow_multiple_root_components",
            True,
        )
    )


def locking_component_summary(
    block_ids,
    lock_edges,
):
    block_ids = {
        int(value)
        for value in block_ids
    }
    adjacency = {
        block_id: set()
        for block_id in block_ids
    }

    for first, second in lock_edges:
        first = int(first)
        second = int(second)
        if (
            first in adjacency
            and second in adjacency
        ):
            adjacency[first].add(
                second
            )
            adjacency[second].add(
                first
            )

    components = []
    visited = set()

    for start in sorted(
        block_ids
    ):
        if start in visited:
            continue
        stack = [
            start
        ]
        visited.add(
            start
        )
        component = []

        while stack:
            current = stack.pop()
            component.append(
                current
            )
            for neighbor in sorted(
                adjacency[
                    current
                ]
            ):
                if neighbor in visited:
                    continue
                visited.add(
                    neighbor
                )
                stack.append(
                    neighbor
                )

        components.append(
            sorted(
                component
            )
        )

    return {
        "component_count": int(
            len(
                components
            )
        ),
        "components": (
            components
        ),
        "connected": bool(
            len(
                components
            )
            <= 1
        ),
    }


def final_block_locking_graph_summary(
    blocks,
):
    blocks = list(
        blocks
    )
    block_ids = {
        int(
            block.block_id
        )
        for block in blocks
    }
    if not block_ids:
        return {
            "component_count": 0,
            "components": [],
            "connected": True,
            "lock_area": 0,
            "lock_edge_count": 0,
        }

    assignment = {
        int(
            block.block_id
        ): int(
            block.rotation
        )
        for block in blocks
    }
    block_lookup = {
        int(
            block.block_id
        ): block
        for block in blocks
    }

    lock_edges = []
    lock_area = 0

    for geometry_row in geometry_contacts(
        blocks
    ):
        contact = contact_with_assignment(
            geometry_row,
            block_ids,
            assignment,
            block_lookup,
        )
        if (
            contact[
                "contact_status"
            ]
            == "male_to_female_lock"
        ):
            lock_edges.append(
                (
                    int(
                        contact[
                            "block_a"
                        ]
                    ),
                    int(
                        contact[
                            "block_b"
                        ]
                    ),
                )
            )
            lock_area += int(
                contact[
                    "overlap_area"
                ]
            )

    summary = locking_component_summary(
        block_ids,
        lock_edges,
    )
    summary.update(
        {
            "lock_area": int(
                lock_area
            ),
            "lock_edge_count": int(
                len(
                    lock_edges
                )
            ),
        }
    )
    return summary

def final_block_supported_graph_summary(
    blocks,
):
    """
    Final segment support graph.

    Male-to-female contacts are locking edges. Female-to-female face contacts
    are nonlocking support edges. Conflicts are never support edges.
    """
    blocks = list(
        blocks
    )
    block_ids = {
        int(
            block.block_id
        )
        for block in blocks
    }
    if not block_ids:
        return {
            "component_count": 0,
            "components": [],
            "connected": True,
            "lock_edge_count": 0,
            "support_edge_count": 0,
            "lock_area": 0,
            "support_area": 0,
            "conflict_count": 0,
        }

    assignment = {
        int(
            block.block_id
        ): int(
            block.rotation
        )
        for block in blocks
    }
    block_lookup = {
        int(
            block.block_id
        ): block
        for block in blocks
    }

    supported_edges = []
    lock_edge_count = 0
    support_edge_count = 0
    lock_area = 0
    support_area = 0
    conflict_count = 0

    for geometry_row in geometry_contacts(
        blocks
    ):
        contact = contact_with_assignment(
            geometry_row,
            block_ids,
            assignment,
            block_lookup,
        )
        status = contact[
            "contact_status"
        ]
        if status == "male_to_female_lock":
            supported_edges.append(
                (
                    int(
                        contact[
                            "block_a"
                        ]
                    ),
                    int(
                        contact[
                            "block_b"
                        ]
                    ),
                )
            )
            lock_edge_count += 1
            lock_area += int(
                contact[
                    "overlap_area"
                ]
            )
        elif status == "female_to_female_nonlocking":
            supported_edges.append(
                (
                    int(
                        contact[
                            "block_a"
                        ]
                    ),
                    int(
                        contact[
                            "block_b"
                        ]
                    ),
                )
            )
            support_edge_count += 1
            support_area += int(
                contact[
                    "overlap_area"
                ]
            )
        elif status in {
            "male_to_male_conflict",
            "geometric_overlap_conflict",
        }:
            conflict_count += 1

    summary = locking_component_summary(
        block_ids,
        supported_edges,
    )
    summary.update(
        {
            "lock_edge_count": int(
                lock_edge_count
            ),
            "support_edge_count": int(
                support_edge_count
            ),
            "lock_area": int(
                lock_area
            ),
            "support_area": int(
                support_area
            ),
            "conflict_count": int(
                conflict_count
            ),
        }
    )
    return summary




def next_row_frontier_overlap_area(
    block,
    next_row_columns,
):
    """
    Geometric overlap area between block +Y and the next row's -Y boundary.

    The next row does not need to be packed yet because its column occupancy
    already defines the possible X/Z interface area.
    """
    if not next_row_columns:
        return 0

    bx0, bx1, by0, by1, bz0, bz1 = block_bounds(block)
    total = 0

    for (x, y, z_min), data in next_row_columns.items():
        nx0 = int(x)
        nx1 = nx0 + 2
        ny0 = int(y)
        nz0 = int(z_min)
        nz1 = nz0 + int(data["height"])

        if by1 != ny0:
            continue

        ox = positive_overlap(bx0, bx1, nx0, nx1)
        oz = positive_overlap(bz0, bz1, nz0, nz1)

        if ox > 0 and oz > 0:
            total += ox * oz

    return int(total)


def assignment_face_coverage(
    current_blocks,
    prior_blocks,
    assignment,
):
    """
    Covered area on every current-block face.

    Coverage is geometric; it is independent of whether the contact is
    locking or non-locking.
    """
    current_ids = {
        int(block.block_id)
        for block in current_blocks
    }
    coverage = {
        (int(block.block_id), face): 0
        for block in current_blocks
        for face in ALL_FACES
    }

    internal_geometry = geometry_contacts(current_blocks)
    prior_geometry = geometry_contacts(
        current_blocks,
        prior_blocks,
    )

    for row in internal_geometry + prior_geometry:
        if row["geometry_status"] != "face_contact":
            continue

        a = int(row["block_a"])
        b = int(row["block_b"])
        area = int(row["overlap_area"])

        if a in current_ids:
            coverage[(a, row["face_a"])] += area
        if b in current_ids:
            coverage[(b, row["face_b"])] += area

    return coverage


def current_row_exposed_male_area(
    current_blocks,
    prior_blocks,
    assignment,
    *,
    is_terminal_row,
):
    """
    Count uncovered male-face area.

    For a nonterminal row, an uncovered +Y male face is treated as an open
    frontier opportunity rather than final exterior exposure. Once the next
    row is placed, the previous frontier is re-evaluated in the cumulative
    state score.
    """
    coverage = assignment_face_coverage(
        current_blocks,
        prior_blocks,
        assignment,
    )

    total = 0

    for block in current_blocks:
        block_id = int(block.block_id)
        male_face = male_face_for_rotation(
            assignment[block_id],
            block.size,
        )

        if not is_terminal_row and male_face == "+Y":
            continue

        area = face_area(block, male_face)
        covered = min(
            area,
            coverage[(block_id, male_face)],
        )
        total += max(0, area - covered)

    return int(total)


def cumulative_exposed_male_area(
    blocks,
    *,
    frontier_row=None,
):
    """
    Exposed male area in a cumulative state.

    When frontier_row is supplied, an exposed +Y face in that newest row is
    kept open for the next row and is not yet counted as final exposure.
    """
    lookup = {
        int(block.block_id): block
        for block in blocks
    }
    coverage = {
        (int(block.block_id), face): 0
        for block in blocks
        for face in ALL_FACES
    }

    for row in geometry_contacts(blocks):
        if row["geometry_status"] != "face_contact":
            continue

        a = int(row["block_a"])
        b = int(row["block_b"])
        area = int(row["overlap_area"])

        coverage[(a, row["face_a"])] += area
        coverage[(b, row["face_b"])] += area

    exposed = 0

    for block in blocks:
        block_id = int(block.block_id)
        male_face = male_face_for_rotation(
            block.rotation,
            block.size,
        )

        if (
            frontier_row is not None
            and int(block.position[1]) == int(frontier_row)
            and male_face == "+Y"
        ):
            continue

        area = face_area(block, male_face)
        covered = min(
            area,
            coverage[(block_id, male_face)],
        )
        exposed += max(0, area - covered)

    return int(exposed)


def evaluate_rotation_assignment(
    current_blocks,
    prior_blocks,
    assignment,
    *,
    is_root_row,
    is_terminal_row,
    next_row_columns=None,
    connector_face_requirements=None,
):
    """
    Evaluate one joint rotation assignment for the current row.

    Mechanical reachability uses only male-to-female edges. Female-to-female
    contacts remain allowed geometry but do not transmit the locking path.
    """
    current_ids = {
        int(block.block_id)
        for block in current_blocks
    }
    block_lookup = {
        int(block.block_id): block
        for block in prior_blocks + current_blocks
    }

    internal_geometry = geometry_contacts(current_blocks)
    prior_geometry = geometry_contacts(
        current_blocks,
        prior_blocks,
    )

    internal_contacts = [
        contact_with_assignment(
            row,
            current_ids,
            assignment,
            block_lookup,
        )
        for row in internal_geometry
    ]
    prior_contacts = [
        contact_with_assignment(
            row,
            current_ids,
            assignment,
            block_lookup,
        )
        for row in prior_geometry
    ]

    conflict_rows = [
        row
        for row in internal_contacts + prior_contacts
        if row["contact_status"] in {
            "male_to_male_conflict",
            "geometric_overlap_conflict",
        }
    ]
    direct_conflict_ids = set()

    for row in conflict_rows:
        a = int(row["block_a"])
        b = int(row["block_b"])

        if a in current_ids:
            direct_conflict_ids.add(a)
        if b in current_ids:
            direct_conflict_ids.add(b)

    internal_lock_edges = []
    internal_lock_area = 0
    internal_nonlocking_area = 0

    for row in internal_contacts:
        if row["contact_status"] == "male_to_female_lock":
            internal_lock_edges.append(
                (
                    int(row["block_a"]),
                    int(row["block_b"]),
                )
            )
            internal_lock_area += int(row["overlap_area"])
        elif row["contact_status"] == "female_to_female_nonlocking":
            internal_nonlocking_area += int(row["overlap_area"])

    prior_seed_ids = set()
    prior_lock_area = 0
    prior_nonlocking_area = 0

    for row in prior_contacts:
        if row["contact_status"] == "male_to_female_lock":
            prior_seed_ids.add(int(row["block_a"]))
            prior_lock_area += int(row["overlap_area"])
        elif row["contact_status"] == "female_to_female_nonlocking":
            prior_nonlocking_area += int(row["overlap_area"])

    root_component_summary = (
        locking_component_summary(
            current_ids,
            internal_lock_edges,
        )
    )

    if is_root_row:
        root_id, best_root_reachable = (
            best_root_reachable_ids(
                current_ids,
                internal_lock_edges,
            )
        )
        if allow_multiple_root_components():
            reachable_ids = set(
                current_ids
            )
        else:
            reachable_ids = set(
                best_root_reachable
            )
    else:
        root_id = None
        reachable_ids = locking_reachable_ids(
            current_ids,
            internal_lock_edges,
            prior_seed_ids,
        )

    accepted_ids = set(reachable_ids) - direct_conflict_ids
    all_reachable = (
        accepted_ids == current_ids
        and not direct_conflict_ids
    )

    exposed_male_area = current_row_exposed_male_area(
        current_blocks,
        prior_blocks,
        assignment,
        is_terminal_row=is_terminal_row,
    )

    forward_female_area = 0
    forward_male_area = 0

    for block in current_blocks:
        overlap_area = next_row_frontier_overlap_area(
            block,
            next_row_columns,
        )

        if overlap_area <= 0:
            continue

        block_id = int(block.block_id)
        forward_type = face_type_for_rotation(
            "+Y",
            assignment[block_id],
            block.size,
        )

        if forward_type == "female":
            forward_female_area += overlap_area
        elif forward_type == "male":
            forward_male_area += overlap_area

    connector_face_evaluation = (
        evaluate_assigned_connector_face_requirements(
            current_blocks,
            assignment,
            connector_face_requirements or [],
        )
    )

    rotation_change_quarters = sum(
        min(
            normalized_rotation(assignment[int(block.block_id)]) // 90,
            4 - normalized_rotation(assignment[int(block.block_id)]) // 90,
        )
        for block in current_blocks
    )

    return {
        "valid": bool(
            all_reachable
            and connector_face_evaluation["valid"]
        ),
        "current_ids": sorted(current_ids),
        "accepted_ids": sorted(accepted_ids),
        "rejected_ids": sorted(current_ids - accepted_ids),
        "root_block_id": root_id,
        "root_component_count": int(
            root_component_summary[
                "component_count"
            ]
        ),
        "temporary_multi_root_accepted": bool(
            is_root_row
            and allow_multiple_root_components()
            and root_component_summary[
                "component_count"
            ]
            > 1
        ),
        "reachable_count": len(accepted_ids),
        "direct_conflict_ids": sorted(direct_conflict_ids),
        "conflict_count": len(conflict_rows),
        "prior_lock_area": int(prior_lock_area),
        "internal_lock_area": int(internal_lock_area),
        "prior_nonlocking_area": int(prior_nonlocking_area),
        "internal_nonlocking_area": int(internal_nonlocking_area),
        "exposed_male_area": int(exposed_male_area),
        "forward_female_area": int(forward_female_area),
        "forward_male_area": int(forward_male_area),
        "rotation_change_quarters": int(rotation_change_quarters),
        "internal_contacts": internal_contacts,
        "prior_contacts": prior_contacts,
        "internal_lock_edges": internal_lock_edges,
        "prior_seed_ids": sorted(prior_seed_ids),
        "connector_face_constraints_valid": (
            connector_face_evaluation["valid"]
        ),
        "connector_face_constraints_evaluated": (
            connector_face_evaluation[
                "evaluated_count"
            ]
        ),
        "connector_face_constraints_satisfied": (
            connector_face_evaluation[
                "satisfied_count"
            ]
        ),
        "connector_face_hard_total": int(
            connector_face_evaluation.get("hard_group_count", 0)
        ),
        "connector_face_hard_satisfied": int(
            connector_face_evaluation.get("hard_satisfied_count", 0)
        ),
        "connector_face_soft_total": int(
            connector_face_evaluation.get("soft_group_count", 0)
        ),
        "connector_face_soft_satisfied": int(
            connector_face_evaluation.get("soft_satisfied_count", 0)
        ),
        "connector_face_constraint_rows": (
            connector_face_evaluation["rows"]
        ),
    }

PLANNER_DIAGNOSTIC_CONFIG = TASK_CONTEXT.get(
    "planner_diagnostics",
    {},
)


def planner_diagnostic_attempt_limit():
    return max(
        1,
        int(
            PLANNER_DIAGNOSTIC_CONFIG.get(
                "top_attempts_per_packing_variant",
                8,
            )
        ),
    )


def planner_failure_reasons(
    evaluation,
    *,
    is_root_row,
):
    """
    Return deterministic reasons explaining why an evaluated row state failed.
    """
    if not evaluation:
        return [
            "no_full_rotation_assignment_evaluated"
        ]

    reasons = []

    if int(
        evaluation.get(
            "conflict_count",
            0,
        )
    ) > 0:
        reasons.append(
            "male_to_male_or_geometry_conflict"
        )

    connector_constraints_valid = bool(
        evaluation.get(
            "connector_face_constraints_valid",
            True,
        )
    )
    if not connector_constraints_valid:
        reasons.append(
            "reserved_connector_face_constraint_failed"
        )

    current_ids = set(
        int(value)
        for value in evaluation.get(
            "current_ids",
            [],
        )
    )
    accepted_ids = set(
        int(value)
        for value in evaluation.get(
            "accepted_ids",
            [],
        )
    )

    if accepted_ids != current_ids:
        prior_seed_ids = set(
            int(value)
            for value in evaluation.get(
                "prior_seed_ids",
                [],
            )
        )
        internal_lock_area = int(
            evaluation.get(
                "internal_lock_area",
                0,
            )
        )

        if is_root_row:
            if internal_lock_area <= 0:
                reasons.append(
                    "root_row_has_no_internal_male_to_female_lock"
                )
            else:
                reasons.append(
                    "root_row_locking_graph_is_disconnected"
                )
        else:
            if not prior_seed_ids:
                reasons.append(
                    "no_male_to_female_lock_to_accepted_prior_structure"
                )
            if internal_lock_area <= 0:
                reasons.append(
                    "current_row_has_no_internal_male_to_female_lock"
                )
            elif accepted_ids:
                reasons.append(
                    "current_row_locking_graph_is_partially_disconnected"
                )
            else:
                reasons.append(
                    "current_row_has_no_reachable_locking_component"
                )

    if (
        int(
            evaluation.get(
                "prior_nonlocking_area",
                0,
            )
        )
        > 0
        and int(
            evaluation.get(
                "prior_lock_area",
                0,
            )
        )
        == 0
        and not is_root_row
    ):
        reasons.append(
            "prior_contact_exists_but_is_female_to_female_nonlocking"
        )

    if (
        int(
            evaluation.get(
                "internal_nonlocking_area",
                0,
            )
        )
        > 0
        and int(
            evaluation.get(
                "internal_lock_area",
                0,
            )
        )
        == 0
    ):
        reasons.append(
            "internal_contact_exists_but_is_female_to_female_nonlocking"
        )

    if not reasons and not bool(
        evaluation.get(
            "valid",
            False,
        )
    ):
        reasons.append(
            "failed_unspecified_mechanical_gate"
        )

    return list(
        dict.fromkeys(reasons)
    )


def planner_attempt_diagnostic_row(
    *,
    segment_id,
    segment_label,
    failed_row,
    row_index,
    parent_state_index,
    packing_index,
    packing,
    row_blocks,
    attempt_rank,
    attempt,
    is_root_row,
    is_terminal_row,
):
    evaluation = (
        attempt.get(
            "evaluation",
            {},
        )
        if attempt
        else {}
    )
    reasons = planner_failure_reasons(
        evaluation,
        is_root_row=is_root_row,
    )
    assignment = (
        attempt.get(
            "assignment",
            {},
        )
        if attempt
        else {}
    )

    internal_contacts = evaluation.get(
        "internal_contacts",
        [],
    )
    prior_contacts = evaluation.get(
        "prior_contacts",
        [],
    )

    def count_status(rows, status):
        return sum(
            1
            for row in rows
            if row.get(
                "contact_status"
            )
            == status
        )

    return {
        "segment_id": (
            int(segment_id)
            if segment_id is not None
            else None
        ),
        "segment_label": str(
            segment_label
            if segment_label is not None
            else "unknown"
        ),
        "planner_failure_row": int(
            failed_row
        ),
        "row": int(
            failed_row
        ),
        "row_index": int(
            row_index
        ),
        "is_root_row": bool(
            is_root_row
        ),
        "is_terminal_row": bool(
            is_terminal_row
        ),
        "parent_state": int(
            parent_state_index
        ),
        "packing_variant": int(
            packing_index
        ),
        "attempt_rank": int(
            attempt_rank
        ),
        "failure_stage": (
            "full_rotation_evaluation"
            if attempt
            else "rotation_search_pruned"
        ),
        "rejection_reason": "|".join(
            reasons
        ),
        "block_count": int(
            packing.get(
                "block_count",
                len(row_blocks),
            )
        ),
        "row_block_count": int(
            len(row_blocks)
        ),
        "row_block_ids": ",".join(
            str(
                int(block.block_id)
            )
            for block in row_blocks
        ),
        "row_block_families": ",".join(
            str(
                block.block_family
            )
            for block in row_blocks
        ),
        "reachable_count": int(
            evaluation.get(
                "reachable_count",
                0,
            )
        ),
        "accepted_ids": ",".join(
            str(value)
            for value in evaluation.get(
                "accepted_ids",
                [],
            )
        ),
        "rejected_ids": ",".join(
            str(value)
            for value in evaluation.get(
                "rejected_ids",
                [],
            )
        ),
        "direct_conflict_ids": ",".join(
            str(value)
            for value in evaluation.get(
                "direct_conflict_ids",
                [],
            )
        ),
        "conflict_count": int(
            evaluation.get(
                "conflict_count",
                0,
            )
        ),
        "prior_seed_ids": ",".join(
            str(value)
            for value in evaluation.get(
                "prior_seed_ids",
                [],
            )
        ),
        "locks_to_prior_structure": bool(
            evaluation.get(
                "prior_seed_ids",
                [],
            )
        ),
        "prior_lock_area": int(
            evaluation.get(
                "prior_lock_area",
                0,
            )
        ),
        "internal_lock_area": int(
            evaluation.get(
                "internal_lock_area",
                0,
            )
        ),
        "prior_nonlocking_area": int(
            evaluation.get(
                "prior_nonlocking_area",
                0,
            )
        ),
        "internal_nonlocking_area": int(
            evaluation.get(
                "internal_nonlocking_area",
                0,
            )
        ),
        "prior_male_to_female_contact_count": (
            count_status(
                prior_contacts,
                "male_to_female_lock",
            )
        ),
        "internal_male_to_female_contact_count": (
            count_status(
                internal_contacts,
                "male_to_female_lock",
            )
        ),
        "prior_female_to_female_contact_count": (
            count_status(
                prior_contacts,
                "female_to_female_nonlocking",
            )
        ),
        "internal_female_to_female_contact_count": (
            count_status(
                internal_contacts,
                "female_to_female_nonlocking",
            )
        ),
        "forward_female_area": int(
            evaluation.get(
                "forward_female_area",
                0,
            )
        ),
        "forward_male_area": int(
            evaluation.get(
                "forward_male_area",
                0,
            )
        ),
        "exposed_male_area": int(
            evaluation.get(
                "exposed_male_area",
                0,
            )
        ),
        "connector_face_constraints_valid": bool(
            evaluation.get(
                "connector_face_constraints_valid",
                True,
            )
        ),
        "connector_face_constraints_evaluated": int(
            evaluation.get(
                "connector_face_constraints_evaluated",
                0,
            )
        ),
        "connector_face_constraints_satisfied": int(
            evaluation.get(
                "connector_face_constraints_satisfied",
                0,
            )
        ),
        "rotation_assignment": json.dumps(
            {
                str(key): int(value)
                for key, value in assignment.items()
            },
            sort_keys=True,
        ),
        "objective": json.dumps(
            attempt.get(
                "objective"
            )
            if attempt
            else None
        ),
    }


def planner_attempt_contact_rows(
    attempt_row,
    attempt,
):
    if not attempt:
        return []

    evaluation = attempt.get(
        "evaluation",
        {},
    )
    rows = []

    for scope, contacts in [
        (
            "prior",
            evaluation.get(
                "prior_contacts",
                [],
            ),
        ),
        (
            "internal",
            evaluation.get(
                "internal_contacts",
                [],
            ),
        ),
    ]:
        for contact_index, contact in enumerate(
            contacts,
            start=1,
        ):
            rows.append(
                {
                    "segment_id": (
                        attempt_row[
                            "segment_id"
                        ]
                    ),
                    "segment_label": (
                        attempt_row[
                            "segment_label"
                        ]
                    ),
                    "planner_failure_row": (
                        attempt_row[
                            "planner_failure_row"
                        ]
                    ),
                    "parent_state": (
                        attempt_row[
                            "parent_state"
                        ]
                    ),
                    "packing_variant": (
                        attempt_row[
                            "packing_variant"
                        ]
                    ),
                    "attempt_rank": (
                        attempt_row[
                            "attempt_rank"
                        ]
                    ),
                    "contact_scope": scope,
                    "contact_index": int(
                        contact_index
                    ),
                    "block_a": contact.get(
                        "block_a"
                    ),
                    "block_b": contact.get(
                        "block_b"
                    ),
                    "face_a": contact.get(
                        "face_a"
                    ),
                    "face_b": contact.get(
                        "face_b"
                    ),
                    "face_type_a": contact.get(
                        "face_type_a"
                    ),
                    "face_type_b": contact.get(
                        "face_type_b"
                    ),
                    "geometry_status": contact.get(
                        "geometry_status"
                    ),
                    "contact_status": contact.get(
                        "contact_status"
                    ),
                    "overlap_area": contact.get(
                        "overlap_area"
                    ),
                }
            )

    return rows


def planner_failure_recommendation(
    attempt_rows,
):
    reason_tokens = [
        token
        for row in attempt_rows
        for token in str(
            row.get(
                "rejection_reason",
                "",
            )
        ).split("|")
        if token
    ]
    reason_set = set(
        reason_tokens
    )

    if (
        "reserved_connector_face_constraint_failed"
        in reason_set
    ):
        return (
            "Inspect reserved connector receiving-face requirements and "
            "whether any catalog-driven block rotation can expose the "
            "required complementary face."
        )

    if any(
        "no_male_to_female_lock_to_accepted_prior_structure"
        in reason
        for reason in reason_set
    ):
        return (
            "Inspect the current-row to prior-row interface. Geometry is "
            "present, but the evaluated rotations do not create a locking "
            "male-to-female path to the accepted structure."
        )

    if any(
        "female_to_female_nonlocking"
        in reason
        for reason in reason_set
    ):
        return (
            "Inspect face orientation at the recorded contacts. The geometry "
            "touches, but the contact is female-to-female and cannot transmit "
            "the locking path."
        )

    if any(
        "locking_graph_is_disconnected"
        in reason
        or "partially_disconnected"
        in reason
        or "no_reachable_locking_component"
        in reason
        for reason in reason_set
    ):
        return (
            "Inspect internal row connectivity. At least one block or locking "
            "component is disconnected from the root/prior locking component."
        )

    if (
        "male_to_male_or_geometry_conflict"
        in reason_set
    ):
        return (
            "Inspect the recorded conflict block IDs and contact rows for "
            "male-to-male contact or overlapping geometry."
        )

    only_pruning = bool(
        reason_set
    ) and reason_set <= {
        "no_full_rotation_assignment_evaluated"
    }
    if only_pruning:
        return (
            "All candidate rotations were pruned before full evaluation. "
            "This is the one case where increasing rotation_beam_width or "
            "relaxing partial-search pruning is supported by the evidence."
        )

    return (
        "Inspect the per-attempt and contact diagnostics before changing "
        "beam widths or block-count limits."
    )


def write_segment_planner_failure_diagnostics(
    *,
    segment_id,
    segment_label,
    failed_row,
    attempt_rows,
    contact_rows,
    output_dir,
):
    output_dir = Path(
        output_dir
    )
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    attempt_df = pd.DataFrame(
        attempt_rows
    )
    contact_df = pd.DataFrame(
        contact_rows
    )

    attempt_path = (
        output_dir
        / "row_planning_failure_diagnostics.csv"
    )
    contact_path = (
        output_dir
        / "row_planning_failure_contacts.csv"
    )
    reason_path = (
        output_dir
        / "row_planning_failure_reason_summary.csv"
    )
    summary_path = (
        output_dir
        / "row_planning_failure_summary.json"
    )

    attempt_df.to_csv(
        attempt_path,
        index=False,
    )
    contact_df.to_csv(
        contact_path,
        index=False,
    )

    reason_rows = []
    for reason, count in (
        attempt_df[
            "rejection_reason"
        ]
        .fillna("")
        .str.split("|")
        .explode()
        .loc[
            lambda series: series.ne("")
        ]
        .value_counts()
        .items()
    ):
        reason_rows.append(
            {
                "segment_id": (
                    int(segment_id)
                    if segment_id is not None
                    else None
                ),
                "segment_label": str(
                    segment_label
                    if segment_label is not None
                    else "unknown"
                ),
                "planner_failure_row": int(
                    failed_row
                ),
                "rejection_reason": str(
                    reason
                ),
                "attempt_count": int(
                    count
                ),
            }
        )

    reason_df = pd.DataFrame(
        reason_rows
    )
    reason_df.to_csv(
        reason_path,
        index=False,
    )

    recommendation = (
        planner_failure_recommendation(
            attempt_rows
        )
    )
    summary = {
        "segment_id": (
            int(segment_id)
            if segment_id is not None
            else None
        ),
        "segment_label": str(
            segment_label
            if segment_label is not None
            else "unknown"
        ),
        "failed_row": int(
            failed_row
        ),
        "attempt_count": int(
            len(attempt_rows)
        ),
        "contact_row_count": int(
            len(contact_rows)
        ),
        "reason_counts": {
            str(row[
                "rejection_reason"
            ]): int(
                row["attempt_count"]
            )
            for row in reason_rows
        },
        "beam_increase_supported_by_evidence": bool(
            reason_rows
            and {
                row[
                    "rejection_reason"
                ]
                for row in reason_rows
            }
            <= {
                "no_full_rotation_assignment_evaluated"
            }
        ),
        "recommendation": recommendation,
        "files": {
            "attempts": str(
                attempt_path
            ),
            "contacts": str(
                contact_path
            ),
            "reason_summary": str(
                reason_path
            ),
        },
    }
    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        ),
        encoding="utf-8",
    )

    if PLANNER_DIAGNOSTIC_CONFIG.get(
        "write_shared_rollup",
        True,
    ):
        shared_path = (
            BETTER_PLANNER_OUTPUT_DIR
            / "row_planning_failure_diagnostics.csv"
        )
        if shared_path.is_file():
            try:
                shared_df = pd.read_csv(
                    shared_path
                )
            except Exception:
                shared_df = pd.DataFrame()
        else:
            shared_df = pd.DataFrame()

        if (
            not shared_df.empty
            and "segment_id"
            in shared_df.columns
            and segment_id is not None
            and PLANNER_DIAGNOSTIC_CONFIG.get(
                "replace_segment_rows_in_shared_rollup",
                True,
            )
        ):
            shared_df = shared_df.loc[
                pd.to_numeric(
                    shared_df[
                        "segment_id"
                    ],
                    errors="coerce",
                )
                != int(segment_id)
            ].copy()

        combined = pd.concat(
            [
                shared_df,
                attempt_df,
            ],
            ignore_index=True,
            sort=False,
        )
        combined.to_csv(
            shared_path,
            index=False,
        )

    return {
        "attempt_path": attempt_path,
        "contact_path": contact_path,
        "reason_path": reason_path,
        "summary_path": summary_path,
        "summary": summary,
    }



def final_rotation_objective(evaluation, next_row_is_terminal):
    """
    Higher tuple is better.

    Feasibility dominates all appearance and strength preferences.
    """
    terminal_frontier_weight = (
        3 if next_row_is_terminal else 1
    )

    return (
        int(evaluation["valid"]),
        evaluation["reachable_count"],
        -evaluation["conflict_count"],
        -len(evaluation["direct_conflict_ids"]),
        evaluation["prior_lock_area"],
        evaluation["internal_lock_area"],
        int(evaluation.get("connector_face_soft_satisfied", 0)),
        (
            terminal_frontier_weight
            * evaluation["forward_female_area"]
        ),
        -evaluation["exposed_male_area"],
        -evaluation["prior_nonlocking_area"],
        -evaluation["internal_nonlocking_area"],
        -evaluation["rotation_change_quarters"],
    )


def partial_rotation_score(
    assignment,
    current_blocks,
    prior_blocks,
    current_internal_geometry,
    current_prior_geometry,
    next_row_columns,
    is_terminal_row,
    next_row_is_terminal,
    connector_face_requirements=None,
):
    """
    Cheap score used only to prune the rotation beam.

    Hard male-to-male conflicts are rejected immediately.
    """
    assigned_ids = set(assignment)
    current_ids = {
        int(block.block_id)
        for block in current_blocks
    }
    lookup = {
        int(block.block_id): block
        for block in prior_blocks + current_blocks
    }

    prior_lock_area = 0
    internal_lock_area = 0
    nonlocking_area = 0
    exposed_area = 0
    forward_female_area = 0

    for row in current_prior_geometry:
        a = int(row["block_a"])

        if a not in assigned_ids:
            continue

        contact = contact_with_assignment(
            row,
            current_ids,
            assignment,
            lookup,
        )

        if contact["contact_status"] in {
            "male_to_male_conflict",
            "geometric_overlap_conflict",
        }:
            return None

        if contact["contact_status"] == "male_to_female_lock":
            prior_lock_area += int(contact["overlap_area"])
        elif contact["contact_status"] == "female_to_female_nonlocking":
            nonlocking_area += int(contact["overlap_area"])

    for row in current_internal_geometry:
        a = int(row["block_a"])
        b = int(row["block_b"])

        if a not in assigned_ids or b not in assigned_ids:
            continue

        contact = contact_with_assignment(
            row,
            current_ids,
            assignment,
            lookup,
        )

        if contact["contact_status"] in {
            "male_to_male_conflict",
            "geometric_overlap_conflict",
        }:
            return None

        if contact["contact_status"] == "male_to_female_lock":
            internal_lock_area += int(contact["overlap_area"])
        elif contact["contact_status"] == "female_to_female_nonlocking":
            nonlocking_area += int(contact["overlap_area"])

    geometry_by_block_face = defaultdict(int)

    for row in current_internal_geometry + current_prior_geometry:
        if row["geometry_status"] != "face_contact":
            continue

        a = int(row["block_a"])
        b = int(row["block_b"])
        area = int(row["overlap_area"])

        if a in assigned_ids:
            geometry_by_block_face[(a, row["face_a"])] += area
        if b in assigned_ids:
            geometry_by_block_face[(b, row["face_b"])] += area

    for block in current_blocks:
        block_id = int(block.block_id)

        if block_id not in assigned_ids:
            continue

        male_face = male_face_for_rotation(
            assignment[block_id],
            block.size,
        )
        area = face_area(block, male_face)
        covered = min(
            area,
            geometry_by_block_face[(block_id, male_face)],
        )

        if not (
            not is_terminal_row
            and male_face == "+Y"
        ):
            exposed_area += max(0, area - covered)

        overlap = next_row_frontier_overlap_area(
            block,
            next_row_columns,
        )

        if (
            overlap > 0
            and face_type_for_rotation(
                "+Y",
                assignment[block_id],
                block.size,
            ) == "female"
        ):
            forward_female_area += overlap

    assigned_requirement_evaluation = (
        evaluate_assigned_connector_face_requirements(
            [
                block
                for block in current_blocks
                if int(block.block_id) in assigned_ids
            ],
            assignment,
            connector_face_requirements or [],
        )
    )
    if not assigned_requirement_evaluation["valid"]:
        return None

    terminal_weight = 3 if next_row_is_terminal else 1

    return (
        prior_lock_area,
        internal_lock_area,
        int(assigned_requirement_evaluation.get("soft_satisfied_count", 0)),
        terminal_weight * forward_female_area,
        -exposed_area,
        -nonlocking_area,
        -sum(
            normalized_rotation(value) // 90
            for value in assignment.values()
        ),
    )


def enumerate_rotation_assignments(
    current_blocks,
    prior_blocks,
    *,
    is_root_row,
    is_terminal_row,
    next_row_columns,
    next_row_is_terminal,
    config,
    connector_face_requirements=None,
):
    """
    Exact search for small rows and deterministic beam search for larger rows.

    The second return value contains several top evaluated attempts so failure
    diagnostics can distinguish locking, conflict, reachability, and reserved
    connector-face failures.
    """
    current_ids = [
        int(
            block.block_id
        )
        for block in current_blocks
    ]

    internal_geometry = geometry_contacts(
        current_blocks
    )
    prior_geometry = geometry_contacts(
        current_blocks,
        prior_blocks,
    )

    contact_degree = defaultdict(
        int
    )

    for row in (
        internal_geometry
        + prior_geometry
    ):
        contact_degree[
            int(
                row[
                    "block_a"
                ]
            )
        ] += 1
        contact_degree[
            int(
                row[
                    "block_b"
                ]
            )
        ] += 1

    ordered_ids = sorted(
        current_ids,
        key=lambda block_id: (
            -contact_degree[
                block_id
            ],
            block_id,
        ),
    )

    candidate_assignments = []

    if (
        len(ordered_ids)
        <= int(
            config.exact_rotation_search_limit
        )
    ):
        for rotations in product(
            (
                0,
                90,
                180,
                270,
            ),
            repeat=len(
                ordered_ids
            ),
        ):
            candidate_assignments.append(
                dict(
                    zip(
                        ordered_ids,
                        rotations,
                    )
                )
            )
    else:
        beam = [
            (
                {},
                (
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                ),
            )
        ]

        for block_id in ordered_ids:
            expanded = []

            for assignment, _ in beam:
                for rotation in (
                    0,
                    90,
                    180,
                    270,
                ):
                    candidate = dict(
                        assignment
                    )
                    candidate[
                        block_id
                    ] = rotation

                    score = partial_rotation_score(
                        candidate,
                        current_blocks,
                        prior_blocks,
                        internal_geometry,
                        prior_geometry,
                        next_row_columns,
                        is_terminal_row,
                        next_row_is_terminal,
                        connector_face_requirements,
                    )

                    if score is None:
                        continue

                    expanded.append(
                        (
                            candidate,
                            score,
                        )
                    )

            expanded.sort(
                key=lambda item: (
                    item[1],
                    tuple(
                        item[0][
                            candidate_block_id
                        ]
                        for candidate_block_id
                        in sorted(
                            item[0]
                        )
                    ),
                ),
                reverse=True,
            )

            beam = expanded[
                : max(
                    1,
                    int(
                        config.rotation_beam_width
                    ),
                )
            ]

            if not beam:
                break

        candidate_assignments = [
            assignment
            for assignment, _ in beam
        ]

    evaluated = []

    for assignment in (
        candidate_assignments
    ):
        evaluation = (
            evaluate_rotation_assignment(
                current_blocks,
                prior_blocks,
                assignment,
                is_root_row=(
                    is_root_row
                ),
                is_terminal_row=(
                    is_terminal_row
                ),
                next_row_columns=(
                    next_row_columns
                ),
                connector_face_requirements=(
                    connector_face_requirements
                ),
            )
        )
        objective = (
            final_rotation_objective(
                evaluation,
                next_row_is_terminal,
            )
        )
        evaluated.append(
            {
                "assignment": assignment,
                "evaluation": evaluation,
                "objective": objective,
            }
        )

    evaluated.sort(
        key=lambda item: (
            item["objective"],
            tuple(
                item[
                    "assignment"
                ][block_id]
                for block_id in sorted(
                    item[
                        "assignment"
                    ]
                )
            ),
        ),
        reverse=True,
    )

    valid = [
        item
        for item in evaluated
        if item[
            "evaluation"
        ][
            "valid"
        ]
    ]

    return (
        valid[
            : max(
                1,
                int(
                    config.rotation_solutions_per_row
                ),
            )
        ],
        evaluated[
            : planner_diagnostic_attempt_limit()
        ],
    )


def apply_rotation_assignment(
    blocks,
    assignment,
):
    for block in blocks:
        apply_structural_rotation(
            block,
            assignment[int(block.block_id)],
        )

    return blocks


def row_state_sort_key(state, is_terminal_row):
    """
    Lower tuple is better.

    Block count is the first optimization objective after every row has
    already passed the hard buildability gate.
    """
    terminal_exposed = (
        state["final_exposed_male_area"]
        if is_terminal_row
        else state["closed_exposed_male_area"]
    )

    return (
        int(state["total_block_count"]),
        int(terminal_exposed),
        int(state["total_aligned_seams"]),
        -int(state["total_prior_lock_area"]),
        -int(state["total_internal_lock_area"]),
        -int(state["last_forward_female_area"]),
        tuple(
            (
                step["row"],
                tuple(
                    (
                        int(block.block_id),
                        int(block.rotation),
                    )
                    for block in step["blocks"]
                ),
            )
            for step in state["steps"]
        ),
    )


def planning_state_signature(state):
    return tuple(
        (
            int(step["row"]),
            tuple(
                (
                    tuple(block.position),
                    tuple(block.size),
                    int(block.rotation),
                )
                for block in sorted(
                    step["blocks"],
                    key=lambda block: int(block.block_id),
                )
            ),
        )
        for step in state["steps"]
    )


def plan_rows_with_column_packing_and_rotation(
    columns,
    config=BETTER_PLANNER_CONFIG,
    connector_face_requirements=None,
    *,
    segment_id=None,
    segment_label=None,
    diagnostic_output_dir=None,
):
    """
    Plan the complete build with a beam of cumulative row states.

    Failure diagnostics are written to the current segment directory before
    the planner raises, so one segment cannot overwrite another segment's
    evidence.
    """
    planner_start_time = (
        time.perf_counter()
    )

    rows = group_columns_by_row(
        columns
    )
    row_values = sorted(
        rows
    )

    if not row_values:
        raise ValueError(
            "No 2×2 structural columns were found."
        )

    theoretical_minimum, minimum_by_column = (
        fixed_column_minimum_block_count(
            columns
        )
    )

    states = [
        {
            "blocks": [],
            "steps": [],
            "row_assignments": {},
            "next_block_id": 1,
            "total_block_count": 0,
            "total_aligned_seams": 0,
            "total_staggered_seams": 0,
            "total_prior_lock_area": 0,
            "total_internal_lock_area": 0,
            "last_forward_female_area": 0,
            "closed_exposed_male_area": 0,
            "final_exposed_male_area": 0,
            "row_diagnostics": [],
        }
    ]

    failure_diagnostics = []
    failure_contact_rows = []

    for row_index, row_value in enumerate(
        row_values
    ):
        row_start_time = (
            time.perf_counter()
        )

        pipeline_log(
            "show_planner_rows",
            (
                f"[ROW {row_index + 1}/"
                f"{len(row_values)}] "
                f"Y={row_value}; "
                f"columns={len(rows[row_value])}; "
                f"incoming states={len(states)}"
            ),
            flush=True,
        )

        is_root_row = (
            row_index == 0
        )
        is_terminal_row = (
            row_index
            == len(row_values) - 1
        )
        next_row_value = (
            row_values[
                row_index + 1
            ]
            if not is_terminal_row
            else None
        )
        next_row_columns = (
            rows[
                next_row_value
            ]
            if next_row_value
            is not None
            else {}
        )
        next_row_is_terminal = (
            row_index + 1
            == len(row_values) - 1
        )

        expanded_states = []

        for (
            parent_state_index,
            parent_state,
        ) in enumerate(
            states
        ):
            previous_assignment = (
                parent_state[
                    "row_assignments"
                ].get(
                    row_values[
                        row_index - 1
                    ],
                    {},
                )
                if row_index > 0
                else {}
            )

            packing_variants = (
                generate_row_packing_variants(
                    rows[
                        row_value
                    ],
                    previous_assignment,
                    config,
                )
            )

            pipeline_log(
                "show_planner_parents",
                (
                    f"  Parent "
                    f"{parent_state_index + 1}/"
                    f"{len(states)}; "
                    f"packing variants="
                    f"{len(packing_variants)}"
                ),
                flush=True,
            )

            for (
                packing_index,
                packing,
            ) in enumerate(
                packing_variants
            ):
                (
                    row_blocks,
                    next_block_id,
                ) = (
                    build_row_blocks_from_assignment(
                        rows[
                            row_value
                        ],
                        packing[
                            "assignment"
                        ],
                        parent_state[
                            "next_block_id"
                        ],
                    )
                )

                (
                    valid_rotation_states,
                    diagnostic_attempts,
                ) = (
                    enumerate_rotation_assignments(
                        row_blocks,
                        parent_state[
                            "blocks"
                        ],
                        is_root_row=(
                            is_root_row
                        ),
                        is_terminal_row=(
                            is_terminal_row
                        ),
                        next_row_columns=(
                            next_row_columns
                        ),
                        next_row_is_terminal=(
                            next_row_is_terminal
                        ),
                        config=config,
                        connector_face_requirements=(
                            connector_face_requirements
                        ),
                    )
                )

                if (
                    not valid_rotation_states
                ):
                    attempts_to_record = (
                        diagnostic_attempts
                        if diagnostic_attempts
                        else [None]
                    )

                    for (
                        attempt_rank,
                        attempt,
                    ) in enumerate(
                        attempts_to_record,
                        start=1,
                    ):
                        attempt_row = (
                            planner_attempt_diagnostic_row(
                                segment_id=(
                                    segment_id
                                ),
                                segment_label=(
                                    segment_label
                                ),
                                failed_row=(
                                    row_value
                                ),
                                row_index=(
                                    row_index
                                ),
                                parent_state_index=(
                                    parent_state_index
                                ),
                                packing_index=(
                                    packing_index
                                ),
                                packing=packing,
                                row_blocks=(
                                    row_blocks
                                ),
                                attempt_rank=(
                                    attempt_rank
                                ),
                                attempt=attempt,
                                is_root_row=(
                                    is_root_row
                                ),
                                is_terminal_row=(
                                    is_terminal_row
                                ),
                            )
                        )
                        failure_diagnostics.append(
                            attempt_row
                        )
                        failure_contact_rows.extend(
                            planner_attempt_contact_rows(
                                attempt_row,
                                attempt,
                            )
                        )
                    continue

                for rotation_state in (
                    valid_rotation_states
                ):
                    chosen_row_blocks = (
                        copy.deepcopy(
                            row_blocks
                        )
                    )
                    apply_rotation_assignment(
                        chosen_row_blocks,
                        rotation_state[
                            "assignment"
                        ],
                    )

                    all_blocks = (
                        list(
                            parent_state[
                                "blocks"
                            ]
                        )
                        + chosen_row_blocks
                    )
                    steps = list(
                        parent_state[
                            "steps"
                        ]
                    ) + [
                        {
                            "row": int(
                                row_value
                            ),
                            "blocks": (
                                chosen_row_blocks
                            ),
                            "packing_assignment": (
                                copy.deepcopy(
                                    packing[
                                        "assignment"
                                    ]
                                )
                            ),
                            "rotation_assignment": dict(
                                rotation_state[
                                    "assignment"
                                ]
                            ),
                            "planning_evaluation": (
                                copy.deepcopy(
                                    rotation_state[
                                        "evaluation"
                                    ]
                                )
                            ),
                        }
                    ]
                    row_assignments = dict(
                        parent_state[
                            "row_assignments"
                        ]
                    )
                    row_assignments[
                        int(
                            row_value
                        )
                    ] = copy.deepcopy(
                        packing[
                            "assignment"
                        ]
                    )

                    frontier_row = (
                        None
                        if is_terminal_row
                        else int(
                            row_value
                        )
                    )
                    exposed = (
                        cumulative_exposed_male_area(
                            all_blocks,
                            frontier_row=(
                                frontier_row
                            ),
                        )
                    )
                    final_exposed = (
                        cumulative_exposed_male_area(
                            all_blocks,
                            frontier_row=None,
                        )
                    )

                    expanded_states.append(
                        {
                            "blocks": all_blocks,
                            "steps": steps,
                            "row_assignments": (
                                row_assignments
                            ),
                            "next_block_id": (
                                next_block_id
                            ),
                            "total_block_count": (
                                parent_state[
                                    "total_block_count"
                                ]
                                + packing[
                                    "block_count"
                                ]
                            ),
                            "total_aligned_seams": (
                                parent_state[
                                    "total_aligned_seams"
                                ]
                                + packing[
                                    "aligned_seams"
                                ]
                            ),
                            "total_staggered_seams": (
                                parent_state[
                                    "total_staggered_seams"
                                ]
                                + packing[
                                    "staggered_seams"
                                ]
                            ),
                            "total_prior_lock_area": (
                                parent_state[
                                    "total_prior_lock_area"
                                ]
                                + rotation_state[
                                    "evaluation"
                                ][
                                    "prior_lock_area"
                                ]
                            ),
                            "total_internal_lock_area": (
                                parent_state[
                                    "total_internal_lock_area"
                                ]
                                + rotation_state[
                                    "evaluation"
                                ][
                                    "internal_lock_area"
                                ]
                            ),
                            "last_forward_female_area": (
                                rotation_state[
                                    "evaluation"
                                ][
                                    "forward_female_area"
                                ]
                            ),
                            "closed_exposed_male_area": (
                                exposed
                            ),
                            "final_exposed_male_area": (
                                final_exposed
                            ),
                            "row_diagnostics": (
                                list(
                                    parent_state[
                                        "row_diagnostics"
                                    ]
                                )
                                + [
                                    {
                                        "row": int(
                                            row_value
                                        ),
                                        "packing_block_count": int(
                                            packing[
                                                "block_count"
                                            ]
                                        ),
                                        "aligned_seams": int(
                                            packing[
                                                "aligned_seams"
                                            ]
                                        ),
                                        "staggered_seams": int(
                                            packing[
                                                "staggered_seams"
                                            ]
                                        ),
                                        "prior_lock_area": int(
                                            rotation_state[
                                                "evaluation"
                                            ][
                                                "prior_lock_area"
                                            ]
                                        ),
                                        "internal_lock_area": int(
                                            rotation_state[
                                                "evaluation"
                                            ][
                                                "internal_lock_area"
                                            ]
                                        ),
                                        "forward_female_area": int(
                                            rotation_state[
                                                "evaluation"
                                            ][
                                                "forward_female_area"
                                            ]
                                        ),
                                        "row_exposed_male_area": int(
                                            rotation_state[
                                                "evaluation"
                                            ][
                                                "exposed_male_area"
                                            ]
                                        ),
                                        "row_block_ids": ",".join(
                                            str(
                                                int(
                                                    block.block_id
                                                )
                                            )
                                            for block
                                            in chosen_row_blocks
                                        ),
                                    }
                                ]
                            ),
                        }
                    )

        if not expanded_states:
            diagnostic_directory = (
                Path(
                    diagnostic_output_dir
                )
                if diagnostic_output_dir
                is not None
                else (
                    BETTER_PLANNER_OUTPUT_DIR
                    / (
                        f"segment_"
                        f"{int(segment_id):03d}"
                        if segment_id
                        is not None
                        else "unknown_segment"
                    )
                )
            )

            diagnostic_bundle = (
                write_segment_planner_failure_diagnostics(
                    segment_id=(
                        segment_id
                    ),
                    segment_label=(
                        segment_label
                    ),
                    failed_row=(
                        row_value
                    ),
                    attempt_rows=(
                        failure_diagnostics
                    ),
                    contact_rows=(
                        failure_contact_rows
                    ),
                    output_dir=(
                        diagnostic_directory
                    ),
                )
            )

            message = (
                "No mechanically valid state was found "
                f"for segment {segment_id}, "
                f"row Y={row_value}. "
                "Detailed diagnostics were written to "
                f"{diagnostic_bundle['attempt_path']} "
                "and "
                f"{diagnostic_bundle['summary_path']}. "
                f"Recommendation: "
                f"{diagnostic_bundle['summary']['recommendation']}"
            )

            if (
                config.fail_when_no_valid_row_state
            ):
                raise RuntimeError(
                    message
                )

            print(
                "[WARNING]",
                message,
            )
            break

        deduplicated = {}

        for state in expanded_states:
            signature = (
                planning_state_signature(
                    state
                )
            )
            previous = (
                deduplicated.get(
                    signature
                )
            )

            if previous is None:
                deduplicated[
                    signature
                ] = state
                continue

            if (
                row_state_sort_key(
                    state,
                    is_terminal_row,
                )
                < row_state_sort_key(
                    previous,
                    is_terminal_row,
                )
            ):
                deduplicated[
                    signature
                ] = state

        ranked_states = sorted(
            deduplicated.values(),
            key=lambda state: (
                row_state_sort_key(
                    state,
                    is_terminal_row,
                )
            ),
        )

        states = ranked_states[
            : max(
                1,
                int(
                    config.plan_beam_width
                ),
            )
        ]

        row_elapsed = (
            time.perf_counter()
            - row_start_time
        )

        pipeline_log(
            "show_planner_rows",
            (
                f"[ROW COMPLETE "
                f"{row_index + 1}/"
                f"{len(row_values)}] "
                f"retained={len(states)}; "
                f"blocks="
                f"{states[0]['total_block_count']}; "
                f"elapsed={row_elapsed:.1f}s"
            ),
            flush=True,
        )

    final_supported_states = []
    for state in states:
        locking_summary = (
            final_block_locking_graph_summary(
                state[
                    "blocks"
                ]
            )
        )
        supported_summary = (
            final_block_supported_graph_summary(
                state[
                    "blocks"
                ]
            )
        )
        state[
            "final_locking_graph_summary"
        ] = locking_summary
        state[
            "final_supported_graph_summary"
        ] = supported_summary
        if (
            supported_summary[
                "connected"
            ]
            and supported_summary[
                "conflict_count"
            ]
            == 0
        ):
            final_supported_states.append(
                state
            )

    if not final_supported_states:
        component_counts = sorted(
            {
                int(
                    state.get(
                        "final_supported_graph_summary",
                        {},
                    ).get(
                        "component_count",
                        0,
                    )
                )
                for state in states
            }
        )
        raise RuntimeError(
            "All rows were packable, but no retained final state "
            "formed one conflict-free supported face-contact component. "
            f"Final supported component counts: {component_counts}."
        )

    best_state = min(
        final_supported_states,
        key=lambda state: (
            row_state_sort_key(
                state,
                True,
            )
        ),
    )

    planner_elapsed = (
        time.perf_counter()
        - planner_start_time
    )
    pipeline_log(
        "show_planner_summary",
        (
            f"Segment "
            f"{segment_id if segment_id is not None else '?'} "
            f"planned: {len(best_state['blocks'])} blocks, "
            f"{len(row_values)} steps, "
            f"{planner_elapsed:.1f}s"
        ),
        flush=True,
    )

    return {
        "blocks": (
            best_state[
                "blocks"
            ]
        ),
        "instruction_steps": (
            best_state[
                "steps"
            ]
        ),
        "best_state": best_state,
        "retained_final_states": (
            states
        ),
        "row_values": (
            row_values
        ),
        "theoretical_fixed_column_minimum": int(
            theoretical_minimum
        ),
        "minimum_by_column": (
            minimum_by_column
        ),
        "config": asdict(
            config
        ),
        "failure_diagnostics": (
            failure_diagnostics
        ),
        "failure_contact_rows": (
            failure_contact_rows
        ),
        "final_locking_graph_summary": (
            best_state[
                "final_locking_graph_summary"
            ]
        ),
        "final_supported_graph_summary": (
            best_state[
                "final_supported_graph_summary"
            ]
        ),
    }


def write_better_planner_outputs(
    planning_result,
    output_dir=BETTER_PLANNER_OUTPUT_DIR,
):
    """
    Persist the selected plan without assuming that display step numbers are
    identical to planner-frame row coordinates.
    """
    output_dir = Path(
        output_dir
    )
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    blocks = list(
        planning_result[
            "blocks"
        ]
    )
    steps = list(
        planning_result[
            "instruction_steps"
        ]
    )
    best_state = (
        planning_result[
            "best_state"
        ]
    )
    row_diagnostics = list(
        best_state.get(
            "row_diagnostics",
            [],
        )
    )
    selected_build_axis = str(
        planning_result.get(
            "selected_build_axis",
            "+Y",
        )
    )

    block_rows = []

    for block in blocks:
        block_rows.append(
            {
                "block_id": int(
                    block.block_id
                ),
                "block_family": (
                    block.block_family
                ),
                "catalog_color": (
                    block.catalog_record[
                        "color"
                    ]
                ),
                "default_packing_priority": float(
                    block.catalog_record[
                        "default_packing_priority"
                    ]
                ),
                "effective_packing_priority": float(
                    block.catalog_record[
                        "effective_packing_priority"
                    ]
                ),
                "packing_priority_source": (
                    block.catalog_record[
                        "packing_priority_source"
                    ]
                ),
                "native_geometry_size": (
                    block.catalog_record[
                        "geometry_size"
                    ]
                ),
                "column_world_size": "x".join(
                    str(
                        int(
                            value
                        )
                    )
                    for value in block.size
                ),
                "selected_build_axis": (
                    selected_build_axis
                ),
                "world_row_y": int(
                    block.position[
                        1
                    ]
                ),
                "position_x": int(
                    block.position[
                        0
                    ]
                ),
                "position_y": int(
                    block.position[
                        1
                    ]
                ),
                "position_z": int(
                    block.position[
                        2
                    ]
                ),
                "size_x": int(
                    block.size[
                        0
                    ]
                ),
                "size_y": int(
                    block.size[
                        1
                    ]
                ),
                "size_z": int(
                    block.size[
                        2
                    ]
                ),
                "rotation": int(
                    block.rotation
                ),
                "male_face": (
                    male_face_for_rotation(
                        block.rotation,
                        block.size,
                    )
                ),
            }
        )

    normalized_diagnostic_rows = []
    for step_index, step in enumerate(
        steps,
        start=1,
    ):
        diagnostic = copy.deepcopy(
            step.get(
                "planning_diagnostic",
                (
                    row_diagnostics[
                        step_index - 1
                    ]
                    if (
                        step_index - 1
                        < len(
                            row_diagnostics
                        )
                    )
                    else {}
                ),
            )
            or {}
        )
        planner_row = int(
            step.get(
                "planner_row",
                diagnostic.get(
                    "row",
                    step.get(
                        "row",
                        step_index,
                    ),
                ),
            )
        )
        display_step = int(
            step.get(
                "row",
                step_index,
            )
        )
        diagnostic[
            "step_number"
        ] = int(
            step_index
        )
        diagnostic[
            "display_step"
        ] = int(
            display_step
        )
        diagnostic[
            "planner_row"
        ] = int(
            planner_row
        )
        diagnostic[
            "world_slice_coordinate"
        ] = step.get(
            "world_slice_coordinate"
        )
        diagnostic[
            "selected_build_axis"
        ] = str(
            step.get(
                "build_axis",
                selected_build_axis,
            )
        )
        normalized_diagnostic_rows.append(
            diagnostic
        )

    block_df = pd.DataFrame(
        block_rows
    )
    row_df = pd.DataFrame(
        normalized_diagnostic_rows
    )

    block_path = (
        output_dir
        / "better_block_plan.csv"
    )
    row_path = (
        output_dir
        / "better_row_planning_summary.csv"
    )
    summary_path = (
        output_dir
        / "better_planner_summary.json"
    )
    instructions_path = (
        output_dir
        / "better_build_instructions.md"
    )

    block_df.to_csv(
        block_path,
        index=False,
    )
    row_df.to_csv(
        row_path,
        index=False,
    )

    summary_payload = {
        "catalog_xlsx": str(
            CATALOG_XLSX_PATH
        ),
        "catalog_sheet": (
            CATALOG_SHEET_NAME
        ),
        "selected_build_axis": (
            selected_build_axis
        ),
        "enabled_structural_families": [
            record[
                "block_family"
            ]
            for record in (
                STRUCTURAL_CATALOG_RECORDS
            )
        ],
        "default_packing_priority_by_family": {
            record[
                "block_family"
            ]: float(
                record[
                    "default_packing_priority"
                ]
            )
            for record in (
                STRUCTURAL_CATALOG_RECORDS
            )
        },
        "effective_packing_priority_by_family": {
            record[
                "block_family"
            ]: float(
                record[
                    "effective_packing_priority"
                ]
            )
            for record in (
                STRUCTURAL_CATALOG_RECORDS
            )
        },
        "packing_priority_source_by_family": {
            record[
                "block_family"
            ]: record[
                "packing_priority_source"
            ]
            for record in (
                STRUCTURAL_CATALOG_RECORDS
            )
        },
        "task_context_json": (
            str(
                TASK_CONTEXT_JSON_PATH
            )
            if TASK_CONTEXT_JSON_PATH
            is not None
            else None
        ),
        "task_context_family_priority_overrides": (
            TASK_CONTEXT_PACKING_PRIORITY_OVERRIDES
        ),
        "manual_family_priority_overrides": (
            MANUAL_PACKING_PRIORITY_OVERRIDES
        ),
        "config": (
            planning_result[
                "config"
            ]
        ),
        "num_steps": int(
            len(
                steps
            )
        ),
        "num_planner_rows": int(
            len(
                row_diagnostics
            )
        ),
        "num_blocks": int(
            len(
                blocks
            )
        ),
        "theoretical_fixed_column_minimum": (
            planning_result[
                "theoretical_fixed_column_minimum"
            ]
        ),
        "final_exposed_male_area": (
            best_state[
                "final_exposed_male_area"
            ]
        ),
        "total_prior_lock_area": (
            best_state[
                "total_prior_lock_area"
            ]
        ),
        "total_internal_lock_area": (
            best_state[
                "total_internal_lock_area"
            ]
        ),
        "total_aligned_seams": (
            best_state[
                "total_aligned_seams"
            ]
        ),
        "total_staggered_seams": (
            best_state[
                "total_staggered_seams"
            ]
        ),
    }
    summary_path.write_text(
        json.dumps(
            summary_payload,
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = [
        "# Better Row-Aware Build Plan",
        "",
        (
            "Planning follows the selected segment build axis. "
            "Display step numbers are intentionally separate from "
            "planner-frame row coordinates."
        ),
        "",
        f"- Selected build axis: {selected_build_axis}",
        f"- Catalog: {CATALOG_XLSX_PATH}",
        (
            "- Packing priority policy: catalog defaults may be "
            "overridden by the model task context; effective values "
            "are used only as a late tie-breaker."
        ),
        f"- Planned steps: {len(steps)}",
        f"- Planned blocks: {len(blocks)}",
        (
            "- Fixed-column theoretical minimum: "
            f"{planning_result['theoretical_fixed_column_minimum']}"
        ),
        (
            "- Final unreserved exposed male area: "
            f"{best_state['final_exposed_male_area']}"
        ),
        "",
    ]

    for step_index, step in enumerate(
        steps,
        start=1,
    ):
        diagnostic = (
            normalized_diagnostic_rows[
                step_index - 1
            ]
            if (
                step_index - 1
                < len(
                    normalized_diagnostic_rows
                )
            )
            else {}
        )
        planner_row = int(
            diagnostic.get(
                "planner_row",
                step.get(
                    "planner_row",
                    step_index,
                ),
            )
        )
        world_slice = (
            diagnostic.get(
                "world_slice_coordinate"
            )
        )
        step_axis = str(
            diagnostic.get(
                "selected_build_axis",
                selected_build_axis,
            )
        )

        lines.extend(
            [
                (
                    f"## Step {step_index}: "
                    f"build along {step_axis}"
                ),
                "",
                (
                    f"- Planner-frame row: "
                    f"{planner_row}"
                ),
                (
                    f"- World slice coordinate: "
                    f"{world_slice}"
                ),
                (
                    f"- Blocks: "
                    f"{len(step['blocks'])}"
                ),
                (
                    "- Block IDs: "
                    + ",".join(
                        str(
                            int(
                                block.block_id
                            )
                        )
                        for block in (
                            step[
                                "blocks"
                            ]
                        )
                    )
                ),
                (
                    "- Lock area to accepted structure: "
                    f"{diagnostic.get('prior_lock_area', 0)}"
                ),
                (
                    "- Lock area within step: "
                    f"{diagnostic.get('internal_lock_area', 0)}"
                ),
                (
                    "- Forward female receiving area: "
                    f"{diagnostic.get('forward_female_area', 0)}"
                ),
                (
                    "- Exposed male area during planning: "
                    f"{diagnostic.get('row_exposed_male_area', 0)}"
                ),
                "",
            ]
        )

        for block in step[
            "blocks"
        ]:
            lines.append(
                (
                    f"- Place block "
                    f"{int(block.block_id)} "
                    f"({block.block_family}, catalog native "
                    f"{block.catalog_record['geometry_size']}) at "
                    f"{tuple(int(value) for value in block.position)}, "
                    f"world size "
                    f"{tuple(int(value) for value in block.size)}, "
                    f"default priority "
                    f"{float(block.catalog_record['default_packing_priority'])}, "
                    f"effective priority "
                    f"{float(block.catalog_record['effective_packing_priority'])} "
                    f"({block.catalog_record['packing_priority_source']}), "
                    f"rotation {int(block.rotation)}°, "
                    f"male face "
                    f"{male_face_for_rotation(block.rotation, block.size)}."
                )
            )

        lines.append(
            ""
        )

    instructions_path.write_text(
        "\n".join(
            lines
        ),
        encoding="utf-8",
    )

    if log_enabled(
        "show_output_paths"
    ):
        for path in [
            block_path,
            row_path,
            summary_path,
            instructions_path,
        ]:
            print(
                f"[OUTPUT] {path}"
            )

    return (
        block_df,
        row_df,
    )


planner_config_payload = (
    TASK_CONTEXT.get("segment_assembly", {})
    .get("segment_packing", {})
    .get("planner_config", {})
)
valid_config_fields = set(
    BetterPlannerConfig.__dataclass_fields__
)
unknown_config_fields = sorted(
    set(planner_config_payload) - valid_config_fields
)
if unknown_config_fields:
    raise KeyError(
        "Unknown planner configuration fields: "
        f"{unknown_config_fields}"
    )
BETTER_PLANNER_CONFIG = BetterPlannerConfig(
    **planner_config_payload
)
if log_enabled(
    "show_planner_configuration"
):
    print("Planner configuration:")
    print(
        asdict(
            BETTER_PLANNER_CONFIG
        )
    )



STEP_VALIDATION_OUTPUT_DIR = BETTER_PLANNER_OUTPUT_DIR
STEP_VALIDATION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def locking_components_from_edges(block_ids, edges):
    adjacency = {
        int(block_id): set()
        for block_id in block_ids
    }

    for a, b in edges:
        a = int(a)
        b = int(b)

        if a in adjacency and b in adjacency:
            adjacency[a].add(b)
            adjacency[b].add(a)

    components = []
    visited = set()

    for start in sorted(adjacency):
        if start in visited:
            continue

        stack = [start]
        visited.add(start)
        component = []

        while stack:
            current = stack.pop()
            component.append(current)

            for neighbor in sorted(adjacency[current]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)

        components.append(sorted(component))

    return components


def validate_planned_instruction_steps(
    blocks,
    instruction_steps,
    connector_face_requirements=None,
):
    block_lookup = {
        int(block.block_id): block
        for block in blocks
    }

    accepted_ids = set()
    step_rows = []
    block_rows = []
    component_rows = []
    contact_rows = []
    block_validation = {}
    accepted_before_by_step = {}
    accepted_after_by_step = {}

    for step_idx, step in enumerate(instruction_steps):
        step_number = step_idx + 1
        row_value = int(step["row"])
        current_blocks = list(step["blocks"])
        current_ids = {
            int(block.block_id)
            for block in current_blocks
        }
        prior_blocks = [
            block_lookup[block_id]
            for block_id in sorted(accepted_ids)
        ]

        accepted_before_by_step[step_idx] = sorted(
            accepted_ids
        )

        assignment = {
            int(block.block_id): int(block.rotation)
            for block in current_blocks
        }

        evaluation = evaluate_rotation_assignment(
            current_blocks,
            prior_blocks,
            assignment,
            is_root_row=(step_idx == 0),
            is_terminal_row=(
                step_idx == len(instruction_steps) - 1
            ),
            next_row_columns=None,
            connector_face_requirements=(
                connector_face_requirements
            ),
        )

        accepted_new_ids = set(
            evaluation["accepted_ids"]
        )
        rejected_new_ids = current_ids - accepted_new_ids
        direct_conflict_ids = set(
            evaluation["direct_conflict_ids"]
        )


        # The final audit never lets rejected blocks become future supports.

        accepted_ids.update(accepted_new_ids)
        accepted_after_by_step[step_idx] = sorted(
            accepted_ids
        )

        if not rejected_new_ids:
            if (
                step_idx == 0
                and evaluation.get(
                    "temporary_multi_root_accepted",
                    False,
                )
            ):
                step_status = (
                    "valid_temporary_multi_root"
                )
            else:
                step_status = "valid"
        elif accepted_new_ids:
            step_status = "partial"
        else:
            step_status = "invalid"

        for row in evaluation["prior_contacts"]:
            record = dict(row)
            record.update({
                "step": step_number,
                "row": row_value,
                "scope": "new_to_prior",
                "prior_block_accepted": True,
            })
            contact_rows.append(record)

        for row in evaluation["internal_contacts"]:
            record = dict(row)
            record.update({
                "step": step_number,
                "row": row_value,
                "scope": "within_new_component",
                "prior_block_accepted": None,
            })
            contact_rows.append(record)

        locking_components = locking_components_from_edges(
            current_ids,
            evaluation["internal_lock_edges"],
        )

        valid_component_count = 0
        invalid_component_count = 0

        for component_number, component_ids in enumerate(
            locking_components,
            start=1,
        ):
            component_set = set(component_ids)
            component_conflicts = sorted(
                component_set & direct_conflict_ids
            )
            component_accepted = sorted(
                component_set & accepted_new_ids
            )
            component_rejected = sorted(
                component_set - accepted_new_ids
            )
            component_valid = not component_rejected

            if component_valid:
                valid_component_count += 1
            else:
                invalid_component_count += 1

            if component_conflicts:
                reason = "male_male_or_overlap_conflict"
            elif component_valid:
                reason = (
                    "root_locking_component"
                    if step_idx == 0
                    and evaluation["root_block_id"]
                    in component_set
                    else "locking_path_to_accepted_structure"
                )
            else:
                reason = "no_locking_path_to_accepted_structure"

            component_rows.append({
                "step": step_number,
                "row": row_value,
                "component": component_number,
                "component_valid": bool(component_valid),
                "reason": reason,
                "num_blocks": len(component_ids),
                "block_ids": ",".join(
                    str(v) for v in component_ids
                ),
                "accepted_block_ids": ",".join(
                    str(v) for v in component_accepted
                ),
                "rejected_block_ids": ",".join(
                    str(v) for v in component_rejected
                ),
                "direct_conflict_block_ids": ",".join(
                    str(v) for v in component_conflicts
                ),
            })

        for block in current_blocks:
            block_id = int(block.block_id)

            if block_id in direct_conflict_ids:
                reason = "direct_male_male_or_overlap_conflict"
            elif block_id in accepted_new_ids:
                if (
                    step_idx == 0
                    and block_id
                    == evaluation["root_block_id"]
                ):
                    reason = "root_block_exempt"
                else:
                    reason = "male_female_locking_path"
            else:
                reason = "no_locking_path_to_accepted_structure"

            row = {
                "step": step_number,
                "row": row_value,
                "block_id": block_id,
                "block_family": block.block_family,
                "valid": block_id in accepted_new_ids,
                "accepted": block_id in accepted_new_ids,
                "reason": reason,
                "direct_conflict": (
                    block_id in direct_conflict_ids
                ),
                "rotation": int(block.rotation),
                "male_face": male_face_for_rotation(
                    block.rotation,
                    block.size,
                ),
            }
            block_rows.append(row)
            block_validation[block_id] = dict(row)

        prior_lock_contacts = [
            row
            for row in evaluation["prior_contacts"]
            if row["contact_status"]
            == "male_to_female_lock"
        ]
        prior_nonlocking_contacts = [
            row
            for row in evaluation["prior_contacts"]
            if row["contact_status"]
            == "female_to_female_nonlocking"
        ]
        conflict_contacts = [
            row
            for row in (
                evaluation["prior_contacts"]
                + evaluation["internal_contacts"]
            )
            if row["contact_status"] in {
                "male_to_male_conflict",
                "geometric_overlap_conflict",
            }
        ]

        step_rows.append({
            "step": step_number,
            "row": row_value,
            "step_status": step_status,
            "num_blocks": len(current_blocks),
            "num_components": len(locking_components),
            "valid_components": valid_component_count,
            "invalid_components": invalid_component_count,
            "accepted_new_blocks": len(accepted_new_ids),
            "rejected_new_blocks": len(rejected_new_ids),
            "accepted_total_after_step": len(accepted_ids),
            "locks_to_accepted_prior": len(
                prior_lock_contacts
            ),
            "lock_area_to_accepted_prior": int(
                evaluation["prior_lock_area"]
            ),
            "internal_lock_area": int(
                evaluation["internal_lock_area"]
            ),
            "nonlocking_contacts_to_accepted_prior": len(
                prior_nonlocking_contacts
            ),
            "male_male_or_overlap_conflicts": len(
                conflict_contacts
            ),
            "exposed_male_area": int(
                evaluation["exposed_male_area"]
            ),
            "accepted_block_ids": ",".join(
                str(v)
                for v in sorted(accepted_new_ids)
            ),
            "rejected_block_ids": ",".join(
                str(v)
                for v in sorted(rejected_new_ids)
            ),
        })

    accepted_final_blocks = [
        block_lookup[
            block_id
        ]
        for block_id in sorted(
            accepted_ids
        )
    ]
    final_locking_graph_summary = (
        final_block_locking_graph_summary(
            accepted_final_blocks
        )
    )
    final_supported_graph_summary = (
        final_block_supported_graph_summary(
            accepted_final_blocks
        )
    )

    return {
        "step_rows": step_rows,
        "block_rows": block_rows,
        "component_rows": component_rows,
        "contact_rows": contact_rows,
        "block_validation": block_validation,
        "accepted_before_by_step": accepted_before_by_step,
        "accepted_after_by_step": accepted_after_by_step,
        "num_final_accepted_blocks": len(accepted_ids),
        "num_total_blocks": len(blocks),
        "all_blocks_accepted": (
            len(accepted_ids) == len(blocks)
        ),
        "final_locking_graph_summary": (
            final_locking_graph_summary
        ),
        "final_locking_graph_connected": bool(
            final_locking_graph_summary[
                "connected"
            ]
        ),
        "all_blocks_accepted_and_connected": bool(
            len(
                accepted_ids
            )
            == len(
                blocks
            )
            and final_locking_graph_summary[
                "connected"
            ]
        ),
        "final_supported_graph_summary": (
            final_supported_graph_summary
        ),
        "final_supported_graph_connected": bool(
            final_supported_graph_summary[
                "connected"
            ]
            and final_supported_graph_summary[
                "conflict_count"
            ]
            == 0
        ),
        "all_blocks_accepted_and_supported": bool(
            len(
                accepted_ids
            )
            == len(
                blocks
            )
            and final_supported_graph_summary[
                "connected"
            ]
            and final_supported_graph_summary[
                "conflict_count"
            ]
            == 0
        ),
    }


def write_step_validation_outputs(
    validation,
    output_dir=STEP_VALIDATION_OUTPUT_DIR,
):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    step_df = pd.DataFrame(validation["step_rows"])
    block_df = pd.DataFrame(validation["block_rows"])
    component_df = pd.DataFrame(
        validation["component_rows"]
    )
    contact_df = pd.DataFrame(validation["contact_rows"])

    step_path = (
        output_dir
        / "build_step_validation_summary.csv"
    )
    block_path = (
        output_dir
        / "build_step_block_validation.csv"
    )
    component_path = (
        output_dir
        / "build_step_component_validation.csv"
    )
    contact_path = (
        output_dir
        / "build_step_contact_validation.csv"
    )
    json_path = (
        output_dir
        / "build_step_validation.json"
    )
    markdown_path = (
        output_dir
        / "validated_build_instructions.md"
    )

    step_df.to_csv(step_path, index=False)
    block_df.to_csv(block_path, index=False)
    component_df.to_csv(component_path, index=False)
    contact_df.to_csv(contact_path, index=False)

    json_payload = {
        "step_rows": validation["step_rows"],
        "block_rows": validation["block_rows"],
        "component_rows": validation[
            "component_rows"
        ],
        "contact_rows": validation["contact_rows"],
        "block_validation": {
            str(key): value
            for key, value in validation[
                "block_validation"
            ].items()
        },
        "accepted_before_by_step": {
            str(key): value
            for key, value in validation[
                "accepted_before_by_step"
            ].items()
        },
        "accepted_after_by_step": {
            str(key): value
            for key, value in validation[
                "accepted_after_by_step"
            ].items()
        },
        "num_final_accepted_blocks": validation[
            "num_final_accepted_blocks"
        ],
        "num_total_blocks": validation[
            "num_total_blocks"
        ],
        "all_blocks_accepted": validation[
            "all_blocks_accepted"
        ],
    }
    json_path.write_text(
        json.dumps(json_payload, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Validated Build Instructions",
        "",
        "Every non-root accepted block must be reachable through "
        "male-to-female locking edges from the previously accepted "
        "structure. Female-to-female contact is allowed but does not "
        "transmit the locking path.",
        "",
        f"- Total blocks: "
        f"{validation['num_total_blocks']}",
        f"- Accepted after final step: "
        f"{validation['num_final_accepted_blocks']}",
        f"- All blocks accepted: "
        f"{validation['all_blocks_accepted']}",
        "",
    ]

    blocks_by_step = defaultdict(list)
    components_by_step = defaultdict(list)

    for row in validation["block_rows"]:
        blocks_by_step[int(row["step"])].append(row)

    for row in validation["component_rows"]:
        components_by_step[int(row["step"])].append(
            row
        )

    for step in validation["step_rows"]:
        step_number = int(step["step"])
        lines.extend([
            f"## Step {step_number}: Build row "
            f"Y={step['row']}",
            "",
            f"- Status: **{step['step_status']}**",
            f"- Blocks: {step['num_blocks']}",
            f"- Locking components: "
            f"{step['num_components']} "
            f"({step['valid_components']} valid, "
            f"{step['invalid_components']} invalid)",
            f"- Locks to accepted prior structure: "
            f"{step['locks_to_accepted_prior']}",
            f"- Lock area to accepted prior structure: "
            f"{step['lock_area_to_accepted_prior']}",
            f"- Internal lock area: "
            f"{step['internal_lock_area']}",
            f"- Conflicts: "
            f"{step['male_male_or_overlap_conflicts']}",
            f"- Exposed male area at this step: "
            f"{step['exposed_male_area']}",
            f"- Accepted block IDs: "
            f"{step['accepted_block_ids'] or 'none'}",
            f"- Rejected block IDs: "
            f"{step['rejected_block_ids'] or 'none'}",
            "",
            "| Block | Catalog family | Result | Reason | Rotation | Male face |",
            "|---:|---|---|---|---:|---|",
        ])

        for row in blocks_by_step[step_number]:
            result = (
                "accepted"
                if row["accepted"]
                else "rejected"
            )
            lines.append(
                f"| {row['block_id']} | "
                f"{row['block_family']} | {result} | "
                f"`{row['reason']}` | "
                f"{row['rotation']}° | "
                f"{row['male_face']} |"
            )

        lines.append("")

    markdown_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    if log_enabled(
        "show_output_paths"
    ):
        for path in [
            step_path,
            block_path,
            component_path,
            contact_path,
            json_path,
            markdown_path,
        ]:
            print(
                f"[OUTPUT] {path}"
            )

    return (
        step_df,
        block_df,
        component_df,
        contact_df,
    )




FACE_TO_VECTOR = {
    "+X": np.array([1, 0, 0], dtype=int),
    "-X": np.array([-1, 0, 0], dtype=int),
    "+Y": np.array([0, 1, 0], dtype=int),
    "-Y": np.array([0, -1, 0], dtype=int),
    "+Z": np.array([0, 0, 1], dtype=int),
    "-Z": np.array([0, 0, -1], dtype=int),
}
VECTOR_TO_FACE = {
    tuple(vector.tolist()): face
    for face, vector in FACE_TO_VECTOR.items()
}
FACE_AXIS_SIGN = {
    "+X": (0, 1), "-X": (0, -1),
    "+Y": (1, 1), "-Y": (1, -1),
    "+Z": (2, 1), "-Z": (2, -1),
}


def select_catalog_records(query):
    return [
        dict(record)
        for record in BLOCK_CATALOG_RECORDS
        if catalog_record_matches(record, query)
    ]

def merge_catalog_queries(*queries):
    clauses = []
    for query in queries:
        if isinstance(query, dict):
            clauses.extend(
                copy.deepcopy(
                    query.get(
                        "all",
                        [],
                    )
                )
            )
    return {
        "all": clauses
    }


def connection_type_catalog_constraint(
    connection_type,
):
    return (
        TASK_CONTEXT.get(
            "segment_assembly",
            {},
        )
        .get(
            "structural_connector_policy",
            {},
        )
        .get(
            "connection_type_catalog_constraints",
            {},
        )
        .get(
            str(connection_type).strip().lower(),
            {"all": []},
        )
    )


def apply_connection_type_catalog_constraint(
    connection_type,
    base_query,
):
    constraint = (
        connection_type_catalog_constraint(
            connection_type
        )
    )
    constrained_query = merge_catalog_queries(
        base_query,
        constraint,
    )
    matches = select_catalog_records(
        constrained_query
    )
    return (
        constrained_query,
        matches,
        constraint,
    )


LLM_CONFIG = TASK_CONTEXT.get(
    "llm",
    {},
)
LLM2_CONFIG = dict(LLM_CONFIG.get(
    "llm2",
    {},
) or {})
LLM2_REQUESTED_ENABLED = bool(LLM2_CONFIG.get("enabled", False))
RUNTIME_LLM_ALLOWED_BY_RUNNER = str(
    os.environ.get("BRICKSMART_RUNTIME_LLM_ALLOWED", "0")
).strip().lower() in {"1", "true", "yes", "on"}
LLM2_EFFECTIVE_ENABLED = bool(
    EXECUTION_POLICY.runtime_llm_effective
    and RUNTIME_LLM_ALLOWED_BY_RUNNER
)
# All downstream decision functions use the effective value. In validated mode
# this is always false, even when an old context still requests an LLM.
LLM2_CONFIG["enabled"] = LLM2_EFFECTIVE_ENABLED
LLM2_INTERFACE_DECISION_ROWS = []
LLM2_FUNCTIONAL_DECISION_ROWS = []
LLM2_RAW_RESPONSE_ROWS = []


def llm2_text_value(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def llm2_json_safe(value):
    if isinstance(value, dict):
        return {
            str(key): llm2_json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [
            llm2_json_safe(item)
            for item in value
        ]
    if isinstance(value, np.generic):
        return value.item()
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def llm2_extract_json_object(text):
    text = str(text or "").strip()
    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        value = json.loads(
            text[start : end + 1]
        )
        if isinstance(value, dict):
            return value

    raise ValueError(
        "The LLM response did not contain one valid JSON object."
    )


def llm2_catalog_capability_rows():
    fields = [
        "block_family",
        "category",
        "functional_role",
        "placement_mode",
        "motion_type",
        "functional_attachment_enabled",
        "attachment_candidate_rule",
        "visual_shape",
        "geometry_size",
    ]
    rows = []
    seen = set()

    for record in BLOCK_CATALOG_RECORDS:
        enabled = catalog_clause_matches(
            record,
            {
                "field": "current_solver_enabled",
                "op": "truthy",
            },
        )
        if not enabled:
            continue

        row = {
            field: llm2_text_value(
                record.get(field)
            )
            for field in fields
        }
        signature = tuple(
            row[field]
            for field in fields
        )
        if signature in seen:
            continue
        seen.add(signature)
        rows.append(row)

    rows.sort(
        key=lambda row: (
            row.get("functional_role", ""),
            row.get("motion_type", ""),
            row.get("block_family", ""),
        )
    )
    maximum = int(
        LLM2_CONFIG.get(
            "maximum_catalog_capability_rows_in_prompt",
            40,
        )
    )
    return rows[: max(1, maximum)]


def llm2_catalog_allowed_values():
    fields = LLM2_CONFIG.get(
        "catalog_requirement_fields",
        [],
    )
    allowed = {
        str(field): {}
        for field in fields
    }

    for record in BLOCK_CATALOG_RECORDS:
        if not catalog_clause_matches(
            record,
            {
                "field": "current_solver_enabled",
                "op": "truthy",
            },
        ):
            continue

        for field in allowed:
            value = record.get(field)
            text = llm2_text_value(value)
            if not text:
                continue
            allowed[field][
                text.lower()
            ] = value

    return allowed


def llm2_validate_catalog_requirements(
    requirements,
):
    if not isinstance(requirements, dict):
        raise ValueError(
            "catalog_requirements must be a JSON object."
        )

    allowed_by_field = (
        llm2_catalog_allowed_values()
    )
    validated = {}
    clauses = [
        {
            "field": "current_solver_enabled",
            "op": "truthy",
        }
    ]

    for field, requested_value in (
        requirements.items()
    ):
        field = str(field)
        if field not in allowed_by_field:
            raise ValueError(
                f"LLM2 returned unsupported catalog field {field!r}."
            )

        if requested_value in {
            None,
            "",
            "any",
            "ANY",
        }:
            continue

        if isinstance(requested_value, bool):
            if requested_value:
                clauses.append(
                    {
                        "field": field,
                        "op": "truthy",
                    }
                )
                validated[field] = True
            continue

        requested_text = llm2_text_value(
            requested_value
        ).lower()
        actual_value = allowed_by_field[
            field
        ].get(requested_text)

        if actual_value is None:
            raise ValueError(
                f"Catalog field {field!r} has no enabled value "
                f"matching {requested_value!r}."
            )

        clauses.append(
            {
                "field": field,
                "op": "equals",
                "value": actual_value,
            }
        )
        validated[field] = actual_value

    if not validated:
        raise ValueError(
            "LLM2 did not provide any usable catalog requirement."
        )

    query = {
        "all": clauses
    }
    matches = select_catalog_records(
        query
    )
    if (
        LLM2_CONFIG.get(
            "require_catalog_match",
            True,
        )
        and not matches
    ):
        raise ValueError(
            "The validated LLM2 requirements match no enabled catalog row."
        )

    return validated, query, matches


def llm2_ollama_chat_json(
    system_prompt,
    user_payload,
):
    endpoint = LLM_CONFIG.get(
        "endpoint",
        "http://127.0.0.1:11434/api/chat",
    )
    primary_model = LLM2_CONFIG.get(
        "model",
        "qwen2.5:14b",
    )
    models = [
        primary_model,
        *LLM2_CONFIG.get(
            "fallback_models",
            [],
        ),
    ]
    models = list(
        dict.fromkeys(
            str(model)
            for model in models
            if str(model).strip()
        )
    )

    timeout_seconds = float(
        LLM2_CONFIG.get(
            "timeout_seconds",
            120,
        )
    )
    retries = max(
        1,
        int(
            LLM2_CONFIG.get(
                "maximum_retries_per_model",
                1,
            )
        ),
    )

    errors = []
    for model in models:
        for attempt in range(
            1,
            retries + 1,
        ):
            try:
                response = requests.post(
                    endpoint,
                    json={
                        "model": model,
                        "stream": False,
                        "format": "json",
                        "messages": [
                            {
                                "role": "system",
                                "content": system_prompt,
                            },
                            {
                                "role": "user",
                                "content": json.dumps(
                                    llm2_json_safe(
                                        user_payload
                                    ),
                                    indent=2,
                                ),
                            },
                        ],
                        "options": {
                            "temperature": float(
                                LLM2_CONFIG.get(
                                    "temperature",
                                    0.0,
                                )
                            )
                        },
                    },
                    timeout=timeout_seconds,
                )
                response.raise_for_status()
                body = response.json()
                content = (
                    body.get(
                        "message",
                        {},
                    ).get(
                        "content",
                        "",
                    )
                )
                parsed = llm2_extract_json_object(
                    content
                )
                LLM2_RAW_RESPONSE_ROWS.append(
                    {
                        "model": model,
                        "attempt": attempt,
                        "success": True,
                        "raw_content": content,
                    }
                )
                return parsed, model
            except Exception as error:
                errors.append(
                    f"{model} attempt {attempt}: "
                    f"{type(error).__name__}: {error}"
                )
                LLM2_RAW_RESPONSE_ROWS.append(
                    {
                        "model": model,
                        "attempt": attempt,
                        "success": False,
                        "raw_content": "",
                        "error": errors[-1],
                    }
                )

    raise RuntimeError(
        "Ollama LLM2 failed for all configured models. "
        + " | ".join(errors)
    )


def llm2_interface_fallback_query(
    declared_rule=None,
):
    if isinstance(declared_rule, dict):
        rule_query = declared_rule.get(
            "catalog_query"
        )
        if isinstance(rule_query, dict):
            return rule_query, (
                "task_context_connector_rule"
            )

    selector_name = (
        TASK_CONTEXT.get(
            "segment_assembly",
            {},
        )
        .get(
            "structural_connector_policy",
            {},
        )
        .get(
            "catalog_selector",
            "segment_connector",
        )
    )
    selector = (
        TASK_CONTEXT.get(
            "catalog",
            {},
        )
        .get(
            "selectors",
            {},
        )
        .get(
            selector_name,
            {"all": []},
        )
    )
    return selector, (
        f"catalog_selector:{selector_name}"
    )


def llm2_resolve_interface_decision(
    interface_row,
    declared_rule=None,
):
    interface_id = str(
        interface_row.interface_id
    )
    hard_required = bool(
        TASK_CONTEXT.get(
            "segment_assembly",
            {},
        )
        .get(
            "structural_connector_policy",
            {},
        )
        .get(
            "required_on_each_assembly_graph_edge",
            True,
        )
    )

    (
        fallback_query,
        fallback_source,
    ) = llm2_interface_fallback_query(
        declared_rule
    )
    (
        fallback_query,
        fallback_matches,
        fallback_constraint,
    ) = (
        apply_connection_type_catalog_constraint(
            "structural_connector",
            fallback_query,
        )
    )

    base_row = {
        "scope": "structural_interface",
        "interface_id": interface_id,
        "segment_a": int(
            interface_row.segment_a
        ),
        "segment_b": int(
            interface_row.segment_b
        ),
        "segment_a_name": (
            segment_display_name_by_id.get(
                int(
                    interface_row.segment_a
                ),
                (
                    f"Segment "
                    f"{int(interface_row.segment_a)}"
                ),
            )
        ),
        "segment_b_name": (
            segment_display_name_by_id.get(
                int(
                    interface_row.segment_b
                ),
                (
                    f"Segment "
                    f"{int(interface_row.segment_b)}"
                ),
            )
        ),
        "segment_a_label": str(
            interface_row.segment_a_label
        ),
        "segment_b_label": str(
            interface_row.segment_b_label
        ),
        "normal_a_to_b": str(
            getattr(
                interface_row,
                "normal_a_to_b",
                "",
            )
        ),
        "contact_area": int(
            getattr(
                interface_row,
                "contact_area",
                0,
            )
        ),
        "connector_required_by_policy": (
            hard_required
        ),
    }

    if (
        not bool(
            LLM2_CONFIG.get(
                "enabled",
                True,
            )
        )
        or not bool(
            LLM2_CONFIG.get(
                "classify_structural_interfaces",
                True,
            )
        )
    ):
        return {
            **base_row,
            "decision_source": (
                fallback_source
            ),
            "model": None,
            "connection_type": (
                "structural_connector"
            ),
            "requires_connector": (
                hard_required
            ),
            "catalog_requirements": {},
            "catalog_query": (
                fallback_query
            ),
            "catalog_constraint_policy": (
                fallback_constraint
            ),
            "matched_block_families": [
                row.get(
                    "block_family"
                )
                for row in fallback_matches
            ],
            "valid": bool(
                fallback_matches
            ),
            "reason": (
                "Runtime LLM disabled by execution policy; deterministic "
                "contract/catalog decision used."
            ),
        }

    system_prompt = (
        "You are LLM2 in a catalog-driven construction pipeline. "
        "Teacher-confirmed segment labels are authoritative and must not "
        "be renamed. Classify the mechanical connection requirement for "
        "one required structural assembly-graph interface. Do not name or "
        "invent a block family. Return exactly one JSON object with keys: "
        "connection_type, requires_connector, catalog_requirements, "
        "confidence, reason. connection_type must be one of the supplied "
        "allowed values. catalog_requirements may use only supplied catalog "
        "fields and values. Omit uncertain fields. A required graph edge "
        "cannot be classified as none when connector_required_by_policy is "
        "true."
    )
    user_payload = {
        "object_type": TASK_CONTEXT.get(
            "object_type_hint",
            "unknown",
        ),
        "interface": base_row,
        "allowed_connection_types": (
            LLM2_CONFIG.get(
                "allowed_connection_types",
                [],
            )
        ),
        "allowed_catalog_requirement_fields": (
            LLM2_CONFIG.get(
                "catalog_requirement_fields",
                [],
            )
        ),
        "enabled_catalog_capabilities": (
            llm2_catalog_capability_rows()
        ),
        "output_example": {
            "connection_type": (
                "structural_connector"
            ),
            "requires_connector": True,
            "catalog_requirements": {
                "functional_role": (
                    "connector"
                ),
                "placement_mode": (
                    "in_between"
                ),
            },
            "confidence": 0.9,
            "reason": (
                "The independently built structural "
                "segments need an in-between connector."
            ),
        },
    }

    try:
        (
            raw_decision,
            model,
        ) = llm2_ollama_chat_json(
            system_prompt,
            user_payload,
        )
        connection_type = str(
            raw_decision.get(
                "connection_type",
                "",
            )
        ).strip().lower()
        allowed_types = {
            str(
                value
            ).lower()
            for value in (
                LLM2_CONFIG.get(
                    "allowed_connection_types",
                    [],
                )
            )
        }
        if (
            connection_type
            not in allowed_types
        ):
            raise ValueError(
                "Unsupported connection_type "
                f"{connection_type!r}."
            )

        requires_connector = bool(
            raw_decision.get(
                "requires_connector",
                hard_required,
            )
        )
        if hard_required and (
            not requires_connector
            or connection_type == "none"
        ):
            raise ValueError(
                "LLM2 attempted to bypass a "
                "required assembly-graph connector."
            )

        (
            validated_requirements,
            query,
            _,
        ) = (
            llm2_validate_catalog_requirements(
                raw_decision.get(
                    "catalog_requirements",
                    {},
                )
            )
        )
        (
            query,
            matches,
            connection_constraint,
        ) = (
            apply_connection_type_catalog_constraint(
                connection_type,
                query,
            )
        )
        if not matches:
            raise ValueError(
                "The LLM2 requirements plus the "
                "connection-type catalog policy "
                "matched no enabled catalog rows."
            )

        return {
            **base_row,
            "decision_source": (
                "ollama_llm2"
            ),
            "model": model,
            "connection_type": (
                connection_type
            ),
            "requires_connector": (
                requires_connector
            ),
            "catalog_requirements": (
                validated_requirements
            ),
            "catalog_query": query,
            "catalog_constraint_policy": (
                connection_constraint
            ),
            "matched_block_families": [
                row.get(
                    "block_family"
                )
                for row in matches
            ],
            "valid": True,
            "confidence": (
                raw_decision.get(
                    "confidence"
                )
            ),
            "reason": (
                raw_decision.get(
                    "reason",
                    "",
                )
            ),
        }

    except Exception as error:
        if not bool(
            LLM2_CONFIG.get(
                "fallback_on_error",
                True,
            )
        ):
            raise

        return {
            **base_row,
            "decision_source": (
                fallback_source
            ),
            "model": None,
            "connection_type": (
                "structural_connector"
            ),
            "requires_connector": (
                hard_required
            ),
            "catalog_requirements": {},
            "catalog_query": (
                fallback_query
            ),
            "catalog_constraint_policy": (
                fallback_constraint
            ),
            "matched_block_families": [
                row.get(
                    "block_family"
                )
                for row in fallback_matches
            ],
            "valid": bool(
                fallback_matches
            ),
            "confidence": None,
            "reason": (
                "LLM2 fallback used after: "
                f"{type(error).__name__}: "
                f"{error}"
            ),
        }


def llm2_functional_fallback_query(
    declaration,
):
    return declaration.get(
        "catalog_query",
        {"all": []},
    ), "task_context_functional_attachment_query"


CONFIRMED_BUILD_INTENT_STATUSES = {
    "confirmed",
    "approved",
    "accepted",
    "corrected",
}


def confirmed_exact_block_family_requirement(
    declaration,
):
    required_family = str(
        declaration.get(
            "required_block_family",
            "",
        )
    ).strip()

    if not required_family:
        return ""

    requirement = declaration.get(
        "block_family_requirement",
        {},
    )
    if not isinstance(
        requirement,
        dict,
    ):
        raise ValueError(
            "An exact required_block_family must include a "
            "block_family_requirement object with confirmation provenance."
        )

    requirement_family = str(
        requirement.get(
            "required_block_family",
            "",
        )
    ).strip()
    status = str(
        requirement.get(
            "confirmation_status",
            "",
        )
    ).strip().lower()
    source = str(
        requirement.get(
            "decision_source",
            "",
        )
    ).strip()
    mode = str(
        requirement.get(
            "mode",
            "",
        )
    ).strip().lower()

    if requirement_family != required_family:
        raise ValueError(
            "required_block_family does not match the confirmed "
            "block_family_requirement."
        )
    if mode != "exact":
        raise ValueError(
            f"{required_family} is declared as an exact family but "
            f"block_family_requirement.mode={mode!r}."
        )
    if status not in CONFIRMED_BUILD_INTENT_STATUSES:
        raise ValueError(
            f"Exact family {required_family!r} is not instructor-confirmed. "
            "The front end must elicit and record the instructor decision "
            "instead of allowing the backend to guess."
        )
    if not source:
        raise ValueError(
            f"Exact family {required_family!r} has no decision_source."
        )

    return required_family


def validate_instructor_build_intent_contract(
    task_context,
):
    rows = []

    conversation_contract = task_context.get(
        "conversation_contract",
        {},
    )
    if (
        conversation_contract.get(
            "segment_confirmation_csv_scope"
        )
        != "source_segment_identity_and_semantics_only"
    ):
        raise ValueError(
            "The segment-confirmation CSV must remain limited to source "
            "segment identity and semantics."
        )

    allow_role_query = bool(
        conversation_contract.get(
            "allow_catalog_role_query_without_exact_family",
            True,
        )
    )

    for declaration in task_context.get(
        "functional_attachments",
        [],
    ):
        attachment_id = str(declaration.get("attachment_id", ""))
        required_family = str(
            declaration.get("required_block_family", "")
        ).strip()

        if required_family:
            confirmed_family = confirmed_exact_block_family_requirement(declaration)
            requirement = declaration["block_family_requirement"]
            rows.append({
                "scope": "functional_attachment",
                "attachment_id": attachment_id,
                "requirement_mode": "exact_family",
                "required_block_family": confirmed_family,
                "confirmation_status": str(requirement.get("confirmation_status", "")),
                "decision_source": str(requirement.get("decision_source", "")),
                "decision_id": str(requirement.get("decision_id", "")),
                "valid": True,
            })
            continue

        catalog_query = declaration.get("catalog_query")
        if catalog_query and allow_role_query:
            rows.append({
                "scope": "functional_attachment",
                "attachment_id": attachment_id,
                "requirement_mode": "catalog_role_query",
                "required_block_family": "",
                "confirmation_status": str(
                    declaration.get("confirmation_status", "confirmed_by_task_context")
                ),
                "decision_source": str(
                    declaration.get("decision_source", "model_task_context")
                ),
                "decision_id": str(
                    declaration.get("decision_id", attachment_id)
                ),
                "valid": True,
            })

    for assembly in task_context.get("functional_assemblies", []) or []:
        if not bool(assembly.get("enabled", True)):
            continue
        assembly_id = str(
            assembly.get("assembly_id", assembly.get("physical_target_id", "functional_subassembly"))
        )
        members = assembly.get("members", {}) or {}
        required_family = str(
            members.get("required_block_family", assembly.get("required_block_family", ""))
        ).strip()
        requirement = (
            members.get("block_family_requirement")
            or assembly.get("block_family_requirement")
            or {}
        )
        if required_family and requirement:
            confirmed_family = confirmed_exact_block_family_requirement({
                **assembly,
                "required_block_family": required_family,
                "block_family_requirement": requirement,
            })
            rows.append({
                "scope": "custom_functional_subassembly",
                "attachment_id": assembly_id,
                "requirement_mode": "exact_family",
                "required_block_family": confirmed_family,
                "confirmation_status": str(requirement.get("confirmation_status", "")),
                "decision_source": str(requirement.get("decision_source", "")),
                "decision_id": str(requirement.get("decision_id", assembly_id)),
                "valid": True,
            })
        elif members.get("catalog_query") and allow_role_query:
            rows.append({
                "scope": "custom_functional_subassembly",
                "attachment_id": assembly_id,
                "requirement_mode": "catalog_role_query",
                "required_block_family": "",
                "confirmation_status": "confirmed_by_task_context",
                "decision_source": "model_task_context",
                "decision_id": f"{assembly_id}_catalog_query",
                "valid": True,
            })

    connector_policy = (
        task_context.get("segment_assembly", {})
        .get("structural_connector_policy", {})
    )
    rows.append({
        "scope": "structural_join_policy",
        "attachment_id": "",
        "requirement_mode": str(connector_policy.get("join_mode", "direct_structural_lock")),
        "required_block_family": "",
        "confirmation_status": str(connector_policy.get("rigid_join_confirmation_status", "confirmed")),
        "decision_source": str(connector_policy.get("rigid_join_decision_source", "model_task_context")),
        "decision_id": "structural_join_policy",
        "valid": True,
    })

    if not rows:
        rows.append({
            "scope": "pipeline_policy",
            "attachment_id": "",
            "requirement_mode": "catalog_driven_without_exact_family",
            "required_block_family": "",
            "confirmation_status": "confirmed_by_task_context",
            "decision_source": "model_task_context",
            "decision_id": "catalog_driven_pipeline_policy",
            "valid": True,
        })

    return rows


INSTRUCTOR_BUILD_INTENT_PREFLIGHT_ROWS = (
    validate_instructor_build_intent_contract(
        TASK_CONTEXT
    )
)
INSTRUCTOR_BUILD_INTENT_PREFLIGHT = {
    "valid": True,
    "segment_confirmation_csv_scope": (
        TASK_CONTEXT[
            "conversation_contract"
        ][
            "segment_confirmation_csv_scope"
        ]
    ),
    "model_task_context_scope": (
        TASK_CONTEXT[
            "conversation_contract"
        ][
            "model_task_context_scope"
        ]
    ),
    "requirements": (
        INSTRUCTOR_BUILD_INTENT_PREFLIGHT_ROWS
    ),
}
(
    OUTPUT_DIR
    / "instructor_build_intent_preflight.json"
).write_text(
    json.dumps(
        INSTRUCTOR_BUILD_INTENT_PREFLIGHT,
        indent=2,
    ),
    encoding="utf-8",
)

def llm2_resolve_functional_decision(
    target,
    declaration,
    anchor,
):
    fallback_query, fallback_source = (
        llm2_functional_fallback_query(
            declaration
        )
    )
    fallback_matches = (
        select_catalog_records(
            fallback_query
        )
    )

    source_segment_ids = [
        int(value)
        for value in target.source_segment_ids
    ]
    source_names = [
        segment_display_name_by_id.get(
            segment_id,
            f"Segment {segment_id}",
        )
        for segment_id in source_segment_ids
    ]
    source_labels = [
        segment_labels_dict.get(
            segment_id,
            "unknown",
        )
        for segment_id in source_segment_ids
    ]
    anchor_segment_id = int(
        anchor["anchor_segment_id"]
    )

    base_row = {
        "scope": "functional_target",
        "attachment_id": str(
            target.attachment_id
        ),
        "physical_target_id": str(
            target.physical_target_id
        ),
        "side": str(
            target.side
        ),
        "source_segment_ids": (
            source_segment_ids
        ),
        "source_segment_names": (
            source_names
        ),
        "source_segment_labels": (
            source_labels
        ),
        "anchor_segment_id": (
            anchor_segment_id
        ),
        "anchor_segment_name": (
            segment_display_name_by_id.get(
                anchor_segment_id,
                f"Segment {anchor_segment_id}",
            )
        ),
        "anchor_segment_label": (
            segment_labels_dict.get(
                anchor_segment_id,
                "unknown",
            )
        ),
        "declared_motion_type": (
            declaration.get(
                "motion_type"
            )
        ),
        "candidate_strategy": (
            declaration.get(
                "candidate_strategy"
            )
        ),
    }

    if (
        not bool(
            LLM2_CONFIG.get(
                "enabled",
                True,
            )
        )
        or not bool(
            LLM2_CONFIG.get(
                "classify_functional_targets",
                True,
            )
        )
    ):
        return {
            **base_row,
            "decision_source": fallback_source,
            "model": None,
            "connection_type": ({
                "wheel": "wheel_replacement",
                "free_rotation": "rotation",
                "rotation": "rotation",
                "hinge": "hinge",
            }.get(str(declaration.get("motion_type", "")).strip().lower(), "functional_attachment")),
            "catalog_requirements": {},
            "catalog_query": fallback_query,
            "matched_block_families": [
                row.get("block_family")
                for row in fallback_matches
            ],
            "valid": bool(
                fallback_matches
            ),
            "reason": "Runtime LLM disabled by execution policy; deterministic contract/catalog decision used.",
        }

    system_prompt = (
        "You are LLM2 in a catalog-driven construction pipeline. "
        "Teacher-confirmed segment labels are authoritative and must not "
        "be changed. Determine the functional connection requirement for "
        "one confirmed functional target and its structural anchor. Do not "
        "name or invent a block family. Return exactly one JSON object with "
        "keys: connection_type, catalog_requirements, confidence, reason. "
        "Use only supplied connection types, catalog fields, and catalog "
        "values. Use the declared motion_type, candidate_strategy, and catalog "
        "query as hard context; do not infer behavior from an object name. "
        "The backend will physically validate all candidates."
    )
    user_payload = {
        "object_type": TASK_CONTEXT.get(
            "object_type_hint",
            "unknown",
        ),
        "functional_target": base_row,
        "semantic_labels_declared_for_attachment": (
            declaration.get(
                "semantic_labels",
                [],
            )
        ),
        "allowed_connection_types": (
            LLM2_CONFIG.get(
                "allowed_connection_types",
                [],
            )
        ),
        "allowed_catalog_requirement_fields": (
            LLM2_CONFIG.get(
                "catalog_requirement_fields",
                [],
            )
        ),
        "enabled_catalog_capabilities": (
            llm2_catalog_capability_rows()
        ),
        "declared_motion_type": declaration.get("motion_type"),
        "declared_candidate_strategy": declaration.get("candidate_strategy"),
        "declared_catalog_query": declaration.get("catalog_query", {}),
    }

    try:
        raw_decision, model = (
            llm2_ollama_chat_json(
                system_prompt,
                user_payload,
            )
        )
        connection_type = str(
            raw_decision.get(
                "connection_type",
                "",
            )
        ).strip().lower()
        allowed_types = {
            str(value).lower()
            for value in LLM2_CONFIG.get(
                "allowed_connection_types",
                [],
            )
        }
        if connection_type not in allowed_types:
            raise ValueError(
                f"Unsupported connection_type {connection_type!r}."
            )
        if connection_type == "none":
            raise ValueError(
                "A confirmed functional target cannot use connection_type none."
            )

        (
            validated_requirements,
            query,
            matches,
        ) = llm2_validate_catalog_requirements(
            raw_decision.get(
                "catalog_requirements",
                {},
            )
        )

        # LLM2 may generalize the wheel requirement to functional_role=wheel.
        # Teacher/task catalog constraints remain authoritative, including the
        # context-declared exact-family requirement for this functional pair.
        query = merge_catalog_queries(
            query,
            declaration.get(
                "catalog_query",
                {"all": []},
            ),
        )
        matches = select_catalog_records(
            query
        )
        if not matches:
            raise ValueError(
                "The LLM2 requirements and task-declared catalog constraints "
                "have no common catalog family."
            )

        return {
            **base_row,
            "decision_source": "ollama_llm2",
            "model": model,
            "connection_type": connection_type,
            "catalog_requirements": (
                validated_requirements
            ),
            "catalog_query": query,
            "matched_block_families": [
                row.get("block_family")
                for row in matches
            ],
            "valid": True,
            "confidence": raw_decision.get(
                "confidence"
            ),
            "reason": raw_decision.get(
                "reason",
                "",
            ),
        }

    except Exception as error:
        if not bool(
            LLM2_CONFIG.get(
                "fallback_on_error",
                True,
            )
        ):
            raise

        return {
            **base_row,
            "decision_source": fallback_source,
            "model": None,
            "connection_type": ({
                "wheel": "wheel_replacement",
                "free_rotation": "rotation",
                "rotation": "rotation",
                "hinge": "hinge",
            }.get(str(declaration.get("motion_type", "")).strip().lower(), "functional_attachment")),
            "catalog_requirements": {},
            "catalog_query": fallback_query,
            "matched_block_families": [
                row.get("block_family")
                for row in fallback_matches
            ],
            "valid": bool(
                fallback_matches
            ),
            "confidence": None,
            "reason": (
                "LLM2 fallback used after: "
                f"{type(error).__name__}: {error}"
            ),
        }



def prepare_general_catalog_record(
    record,
):
    """
    Return one consistently enriched catalog record for connectors,
    replacements, and other nonstructural blocks.

    The function is intentionally idempotent so callers may safely normalize
    either a raw workbook row or an already prepared record.
    """
    prepared = dict(
        record
    )

    geometry_size_value = prepared.get(
        "geometry_size"
    )
    if prepared.get(
        "native_size"
    ) is None:
        if geometry_size_value is None:
            raise KeyError(
                "Catalog record is missing both "
                "'native_size' and 'geometry_size'."
            )
        prepared[
            "native_size"
        ] = parse_catalog_size(
            geometry_size_value
        )
    else:
        prepared[
            "native_size"
        ] = tuple(
            int(
                value
            )
            for value in (
                prepared[
                    "native_size"
                ]
            )
        )

    if "male_faces" not in prepared:
        prepared[
            "male_faces"
        ] = parse_catalog_faces(
            prepared.get(
                "primary_male_faces"
            )
        )
    else:
        prepared[
            "male_faces"
        ] = tuple(
            prepared.get(
                "male_faces"
            )
            or ()
        )

    if "female_faces" not in prepared:
        prepared[
            "female_faces"
        ] = parse_catalog_faces(
            prepared.get(
                "primary_female_faces"
            )
        )
    else:
        prepared[
            "female_faces"
        ] = tuple(
            prepared.get(
                "female_faces"
            )
            or ()
        )

    if "color_rgb" not in prepared:
        color_value = prepared.get(
            "color"
        )
        if color_value is None:
            prepared[
                "color_rgb"
            ] = np.asarray(
                [
                    160,
                    160,
                    160,
                ],
                dtype=int,
            )
            prepared[
                "color_normalization_source"
            ] = (
                "neutral_fallback_missing_catalog_color"
            )
        else:
            prepared[
                "color_rgb"
            ] = catalog_rgb(
                color_value
            )
            prepared[
                "color_normalization_source"
            ] = "catalog_color"
    else:
        prepared[
            "color_rgb"
        ] = np.asarray(
            prepared[
                "color_rgb"
            ],
            dtype=int,
        )
        prepared[
            "color_normalization_source"
        ] = prepared.get(
            "color_normalization_source",
            "precomputed_color_rgb",
        )

    return prepared


def rotation_matrices_24():
    matrices = []
    basis = np.eye(3, dtype=int)
    for permutation in permutations(range(3)):
        permutation_matrix = basis[:, permutation]
        for signs in product([-1, 1], repeat=3):
            matrix = permutation_matrix @ np.diag(signs)
            determinant = round(np.linalg.det(matrix))
            if determinant == 1:
                matrices.append(matrix)
    unique = {}
    for matrix in matrices:
        unique[tuple(matrix.ravel().tolist())] = matrix
    return list(unique.values())


ROTATION_MATRICES_24 = rotation_matrices_24()


def oriented_catalog_variants(record):
    prepared = prepare_general_catalog_record(record)
    local_size = np.asarray(prepared["native_size"], dtype=int)
    variants = {}
    for matrix in ROTATION_MATRICES_24:
        world_size = tuple(
            (np.abs(matrix) @ local_size).astype(int).tolist()
        )
        face_roles = {face: "none" for face in ALL_FACES}
        for face in prepared["male_faces"]:
            world_vector = matrix @ FACE_TO_VECTOR[face]
            face_roles[VECTOR_TO_FACE[tuple(world_vector.tolist())]] = "male"
        for face in prepared["female_faces"]:
            world_vector = matrix @ FACE_TO_VECTOR[face]
            world_face = VECTOR_TO_FACE[tuple(world_vector.tolist())]
            if face_roles[world_face] == "none":
                face_roles[world_face] = "female"
        signature = (
            world_size,
            tuple(sorted(
                face
                for face, role in face_roles.items()
                if role == "male"
            )),
            tuple(sorted(
                face
                for face, role in face_roles.items()
                if role == "female"
            )),
        )
        variants[signature] = {
            "block_family": str(record["block_family"]),
            "catalog_record": prepared,
            "size": world_size,
            "face_roles": face_roles,
            "rotation_matrix": matrix.astype(int).tolist(),
        }
    return list(variants.values())


def full_face_template(size, face_roles):
    template = {}
    for face in ALL_FACES:
        rows, columns = face_grid_shape(size, face)
        role = face_roles.get(face, "none")
        face_type = {
            "male": FaceType.MALE,
            "female": FaceType.FEMALE,
        }.get(role, FaceType.NONE)
        template[face] = [
            [face_type for _ in range(columns)]
            for _ in range(rows)
        ]
    return template


def candidate_optional_value(
    candidate,
    key,
    default=None,
):
    """
    Read an optional candidate field without leaking pandas NaN values.

    DataFrames create NaN for columns that apply only to some candidate
    families, such as wheel_axle_axis_index on wheel rows but not rotation
    connector rows.
    """
    value = candidate.get(
        key,
        default,
    )

    if value is None:
        return default

    if isinstance(
        value,
        (
            float,
            np.floating,
        ),
    ) and np.isnan(
        value
    ):
        return default

    try:
        missing = pd.isna(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return value

    if isinstance(
        missing,
        (
            bool,
            np.bool_,
        ),
    ) and bool(
        missing
    ):
        return default

    return value

def make_nonstructural_block(
    candidate,
    block_id,
    category,
):
    raw_record = candidate[
        "catalog_record"
    ]
    record = (
        prepare_general_catalog_record(
            raw_record
        )
    )

    color_rgb = np.asarray(
        record.get(
            "color_rgb",
            [
                160,
                160,
                160,
            ],
        ),
        dtype=int,
    )

    candidate_size = candidate_optional_value(
        candidate,
        "size",
    )
    if candidate_size is None:
        candidate_size = record[
            "native_size"
        ]
    candidate_size = tuple(
        int(
            value
        )
        for value in candidate_size
    )

    face_roles = candidate_optional_value(
        candidate,
        "face_roles",
    )
    if (
        not isinstance(
            face_roles,
            dict,
        )
        or not face_roles
    ):
        face_roles = {
            face: "none"
            for face in (
                "+X",
                "-X",
                "+Y",
                "-Y",
                "+Z",
                "-Z",
            )
        }
        for face in record.get(
            "female_faces",
            (),
        ):
            face_roles[
                face
            ] = "female"
        for face in record.get(
            "male_faces",
            (),
        ):
            face_roles[
                face
            ] = "male"

    block = BlockInstance(
        position=tuple(
            int(
                value
            )
            for value in candidate[
                "origin"
            ]
        ),
        size=candidate_size,
        base_color=color_rgb,
        block_id=block_id,
        rotation=0,
        category=category,
        block_family=candidate[
            "block_family"
        ],
        segment_a=candidate_optional_value(
            candidate,
            "segment_a",
        ),
        segment_b=candidate_optional_value(
            candidate,
            "segment_b",
        ),
    )
    block.catalog_record = (
        record
    )
    block.catalog_category = (
        record.get(
            "category"
        )
    )
    block.base_color = color_rgb
    block.faces = full_face_template(
        candidate_size,
        face_roles,
    )
    block.block_role = candidate_optional_value(
        candidate,
        "block_role",
        category,
    )
    block.interface_id = candidate_optional_value(
        candidate,
        "interface_id",
    )
    block.physical_target_id = candidate_optional_value(
        candidate,
        "physical_target_id",
    )
    block.anchor_segment_id = candidate_optional_value(
        candidate,
        "anchor_segment_id",
    )
    block.rotation_matrix = candidate_optional_value(
        candidate,
        "rotation_matrix",
    )
    block.face_roles = face_roles
    block.validation_mode = candidate_optional_value(
        candidate,
        "validation_mode",
    )
    block.geometry_coordinates = candidate_optional_value(
        candidate,
        "geometry_coordinates",
        [],
    )
    block.embedded_anchor_cells_a = candidate_optional_value(
        candidate,
        "embedded_anchor_cells_a",
        [],
    )
    block.embedded_anchor_cells_b = candidate_optional_value(
        candidate,
        "embedded_anchor_cells_b",
        [],
    )
    block.source_overlap_voxels = candidate_optional_value(
        candidate,
        "source_overlap_voxels",
        0,
    )
    block.source_overlap_ratio = candidate_optional_value(
        candidate,
        "source_overlap_ratio",
        0.0,
    )
    block.anchor_contact_area = candidate_optional_value(
        candidate,
        "anchor_contact_area",
        0,
    )
    block.postbuild_lock_area_segment_a = (
        candidate_optional_value(
            candidate,
            "postbuild_lock_area_segment_a",
            candidate_optional_value(
                candidate,
                "overlap_a",
                0,
            ),
        )
    )
    block.postbuild_lock_area_segment_b = (
        candidate_optional_value(
            candidate,
            "postbuild_lock_area_segment_b",
            candidate_optional_value(
                candidate,
                "overlap_b",
                0,
            ),
        )
    )

    block.wheel_axle_axis = candidate_optional_value(
        candidate,
        "wheel_axle_axis",
    )
    block.wheel_disc_plane = candidate_optional_value(
        candidate,
        "wheel_disc_plane",
    )
    block.wheel_vertical_axis = candidate_optional_value(
        candidate,
        "wheel_vertical_axis",
    )

    wheel_axis_index = candidate_optional_value(
        candidate,
        "wheel_axle_axis_index",
    )
    if wheel_axis_index is not None:
        block.render_axis = int(
            wheel_axis_index
        )

    return block


def planner_segment_grid(voxel_grid):
    axis_order = tuple(
        int(value)
        for value in TASK_CONTEXT.get(
            "coordinate_system",
            {},
        ).get("planner_axis_order", [0, 2, 1])
    )
    result = np.transpose(voxel_grid, axis_order)
    axis_flips = TASK_CONTEXT.get(
        "coordinate_system",
        {},
    ).get("planner_axis_flips", [False, False, False])
    for axis, flip in enumerate(axis_flips):
        if flip:
            result = np.flip(result, axis=axis)
    return result


segment_grid_planner_raw = planner_segment_grid(
    voxel_segment_clean
)
segment_grid_planner = segment_grid_planner_raw.copy()
planner_segment_labels = dict(segment_labels_dict)


def detect_segment_interfaces(segment_grid, included_segment_ids=None):
    included = (
        None
        if included_segment_ids is None
        else {int(value) for value in included_segment_ids}
    )
    buckets = defaultdict(
        lambda: {
            "contact_area": 0,
            "a_coordinates": [],
            "b_coordinates": [],
        }
    )
    shape = segment_grid.shape

    for axis in range(3):
        left_slices = [slice(None)] * 3
        right_slices = [slice(None)] * 3
        left_slices[axis] = slice(0, shape[axis] - 1)
        right_slices[axis] = slice(1, shape[axis])

        left = segment_grid[tuple(left_slices)]
        right = segment_grid[tuple(right_slices)]
        contact_mask = (
            (left > 0)
            & (right > 0)
            & (left != right)
        )

        for local_coordinate in np.argwhere(contact_mask):
            coordinate_a = local_coordinate.astype(int)
            coordinate_b = local_coordinate.astype(int)
            coordinate_b[axis] += 1
            segment_a = int(segment_grid[tuple(coordinate_a)])
            segment_b = int(segment_grid[tuple(coordinate_b)])

            if included is not None and (
                segment_a not in included
                or segment_b not in included
            ):
                continue

            if segment_a < segment_b:
                key = (
                    segment_a,
                    segment_b,
                    ALL_FACES[axis * 2],
                )
                stored_a = coordinate_a
                stored_b = coordinate_b
            else:
                key = (
                    segment_b,
                    segment_a,
                    ALL_FACES[axis * 2 + 1],
                )
                stored_a = coordinate_b
                stored_b = coordinate_a

            buckets[key]["contact_area"] += 1
            buckets[key]["a_coordinates"].append(
                stored_a.tolist()
            )
            buckets[key]["b_coordinates"].append(
                stored_b.tolist()
            )

    rows = []
    payload = {}
    minimum_area = int(
        TASK_CONTEXT.get("segment_assembly", {})
        .get("interface_detection", {})
        .get("minimum_contact_area", 1)
    )
    for index, (
        (segment_a, segment_b, normal),
        data,
    ) in enumerate(sorted(buckets.items()), start=1):
        if data["contact_area"] < minimum_area:
            continue
        interface_id = (
            f"SI_{segment_a:03d}_{segment_b:03d}_{index:03d}"
        )
        rows.append({
            "interface_id": interface_id,
            "segment_a": segment_a,
            "segment_b": segment_b,
            "segment_a_label": planner_segment_labels.get(
                segment_a,
                "unknown",
            ),
            "segment_b_label": planner_segment_labels.get(
                segment_b,
                "unknown",
            ),
            "normal_a_to_b": normal,
            "contact_area": int(data["contact_area"]),
        })
        payload[interface_id] = data

    return pd.DataFrame(rows), payload



def semantic_preflight_axis_index():
    axis_name = str(
        TASK_CONTEXT.get(
            "symmetry",
            {},
        ).get("axis", "X")
    ).upper()
    return {"X": 0, "Y": 1, "Z": 2}[axis_name]


def semantic_preflight_mirror_index(
    index,
    center_plane,
):
    mirrored = (
        2.0 * float(center_plane)
        - (float(index) + 0.5)
    )
    return int(round(mirrored - 0.5))


def semantic_preflight_mirror_mask(
    mask,
    axis,
    center_plane,
):
    mask = np.asarray(mask, dtype=bool)
    mirrored = np.zeros_like(mask)
    for coordinate in np.argwhere(mask):
        reflected = coordinate.astype(int).copy()
        reflected[axis] = (
            semantic_preflight_mirror_index(
                reflected[axis],
                center_plane,
            )
        )
        if all(
            0
            <= reflected[current_axis]
            < mask.shape[current_axis]
            for current_axis in range(3)
        ):
            mirrored[tuple(reflected)] = True
    return mirrored


def semantic_preflight_mask_iou(
    mask_a,
    mask_b,
):
    mask_a = np.asarray(mask_a, dtype=bool)
    mask_b = np.asarray(mask_b, dtype=bool)
    union = int((mask_a | mask_b).sum())
    if union == 0:
        return 1.0
    return float(
        (mask_a & mask_b).sum() / union
    )


def semantic_preflight_center_plane(
    occupied_mask,
    axis,
):
    coordinates = np.argwhere(occupied_mask)
    if len(coordinates) == 0:
        return occupied_mask.shape[axis] / 2.0

    minimum = int(
        coordinates[:, axis].min()
    )
    maximum = int(
        coordinates[:, axis].max()
    )
    bbox_center = (
        minimum + maximum + 1
    ) / 2.0

    configured = (
        TASK_CONTEXT.get("symmetry", {})
        .get("center_plane")
    )
    if configured is not None:
        candidates = [float(configured)]
    else:
        candidates = list(
            np.arange(
                float(minimum),
                float(maximum + 1) + 0.25,
                0.5,
            )
        )
        candidates.append(float(bbox_center))

    scored = []
    for center_plane in sorted(set(candidates)):
        mirrored = (
            semantic_preflight_mirror_mask(
                occupied_mask,
                axis,
                center_plane,
            )
        )
        score = semantic_preflight_mask_iou(
            occupied_mask,
            mirrored,
        )
        scored.append((
            score,
            -abs(
                float(center_plane)
                - float(bbox_center)
            ),
            float(center_plane),
        ))

    return max(scored)[2]


def physical_target_mask(
    target_row,
    segment_grid,
):
    return np.isin(
        segment_grid,
        [
            int(value)
            for value in target_row[
                "source_segment_ids"
            ]
        ],
    )


def run_functional_semantic_preflight(
    segment_table,
    provisional_targets,
    segment_grid,
):
    config = TASK_CONTEXT.get(
        "semantic_preflight",
        {},
    )
    effective = segment_table.copy()
    effective[
        "original_segment_label"
    ] = effective["segment_label"]
    effective[
        "semantic_preflight_status"
    ] = "not_evaluated"
    effective[
        "semantic_preflight_reason"
    ] = None

    audit_rows = []
    suggestion_rows = []
    quarantine_ids = set()
    required_gate_values = []

    if not config.get("enabled", True):
        return {
            "effective_segment_table": effective,
            "audit_df": pd.DataFrame(),
            "suggestions_df": pd.DataFrame(),
            "quarantined_segment_ids": [],
            "gate_valid": True,
            "center_plane": None,
        }

    axis = semantic_preflight_axis_index()
    center_plane = (
        semantic_preflight_center_plane(
            segment_grid > 0,
            axis,
        )
    )
    minimum_voxels = int(
        config.get(
            "minimum_target_voxels",
            4,
        )
    )
    maximum_ratio = float(
        config.get(
            "maximum_pair_voxel_ratio",
            3.0,
        )
    )
    minimum_iou = float(
        config.get(
            "minimum_pair_mirror_iou",
            0.50,
        )
    )

    for declaration in attachment_declarations():
        attachment_id = declaration[
            "attachment_id"
        ]
        required = bool(
            declaration.get("required", False)
        )
        targets = provisional_targets[
            provisional_targets[
                "attachment_id"
            ].astype(str)
            == str(attachment_id)
        ].copy()

        left_rows = targets[
            targets["side"].astype(str).str.lower()
            == "left"
        ]
        right_rows = targets[
            targets["side"].astype(str).str.lower()
            == "right"
        ]

        pair_evaluated = bool(
            config.get(
                "evaluate_required_left_right_pairs",
                True,
            )
            and int(
                declaration.get(
                    "expected_count",
                    0,
                )
            ) == 2
        )

        if not pair_evaluated:
            audit_rows.append({
                "attachment_id": attachment_id,
                "required": required,
                "status": "not_pair_evaluated",
                "left_target_count": len(left_rows),
                "right_target_count": len(right_rows),
                "gate_valid": True,
                "center_plane": center_plane,
            })
            if required:
                required_gate_values.append(True)
            continue

        if (
            len(left_rows) != 1
            or len(right_rows) != 1
        ):
            pair_valid = False
            reason = (
                "expected_exactly_one_left_and_one_right_target"
            )
            left_mask = np.zeros_like(
                segment_grid,
                dtype=bool,
            )
            right_mask = np.zeros_like(
                segment_grid,
                dtype=bool,
            )
            left_ids = [
                int(value)
                for values in left_rows[
                    "source_segment_ids"
                ].tolist()
                for value in values
            ]
            right_ids = [
                int(value)
                for values in right_rows[
                    "source_segment_ids"
                ].tolist()
                for value in values
            ]
        else:
            left_row = left_rows.iloc[0]
            right_row = right_rows.iloc[0]
            left_ids = [
                int(value)
                for value in left_row[
                    "source_segment_ids"
                ]
            ]
            right_ids = [
                int(value)
                for value in right_row[
                    "source_segment_ids"
                ]
            ]
            left_mask = physical_target_mask(
                left_row,
                segment_grid,
            )
            right_mask = physical_target_mask(
                right_row,
                segment_grid,
            )

            left_count = int(
                left_mask.sum()
            )
            right_count = int(
                right_mask.sum()
            )
            maximum_count = max(
                left_count,
                right_count,
                1,
            )
            minimum_count = min(
                left_count,
                right_count,
            )
            voxel_ratio = (
                maximum_count
                / max(minimum_count, 1)
            )
            mirror_iou = (
                semantic_preflight_mask_iou(
                    semantic_preflight_mirror_mask(
                        left_mask,
                        axis,
                        center_plane,
                    ),
                    right_mask,
                )
            )

            reasons = []
            if minimum_count < minimum_voxels:
                reasons.append(
                    "target_below_minimum_voxel_count"
                )
            if voxel_ratio > maximum_ratio:
                reasons.append(
                    "left_right_voxel_ratio_too_large"
                )
            if mirror_iou < minimum_iou:
                reasons.append(
                    "left_right_mirror_iou_too_low"
                )

            pair_valid = not reasons
            reason = (
                "valid_pair"
                if pair_valid
                else ";".join(reasons)
            )

        left_count = int(
            left_mask.sum()
        )
        right_count = int(
            right_mask.sum()
        )
        maximum_count = max(
            left_count,
            right_count,
            1,
        )
        minimum_count = min(
            left_count,
            right_count,
        )
        voxel_ratio = (
            maximum_count
            / max(minimum_count, 1)
        )
        mirror_iou = (
            semantic_preflight_mask_iou(
                semantic_preflight_mirror_mask(
                    left_mask,
                    axis,
                    center_plane,
                ),
                right_mask,
            )
            if (
                left_mask.any()
                and right_mask.any()
            )
            else 0.0
        )

        audit_rows.append({
            "attachment_id": attachment_id,
            "required": required,
            "status": (
                "valid_pair"
                if pair_valid
                else "quarantined_invalid_pair"
            ),
            "left_segment_ids": left_ids,
            "right_segment_ids": right_ids,
            "left_voxel_count": left_count,
            "right_voxel_count": right_count,
            "voxel_count_ratio": float(
                voxel_ratio
            ),
            "mirror_iou": float(mirror_iou),
            "minimum_target_voxels": (
                minimum_voxels
            ),
            "maximum_pair_voxel_ratio": (
                maximum_ratio
            ),
            "minimum_pair_mirror_iou": (
                minimum_iou
            ),
            "reason": reason,
            "gate_valid": bool(pair_valid),
            "center_plane": center_plane,
        })

        if required:
            required_gate_values.append(
                bool(pair_valid)
            )

        if (
            not pair_valid
            and config.get(
                "quarantine_invalid_functional_pairs",
                True,
            )
        ):
            quarantine_ids.update(
                left_ids + right_ids
            )

            if config.get(
                "suggest_alternative_mirror_partners",
                True,
            ):
                for side_name, source_ids, source_mask in [
                    (
                        "left",
                        left_ids,
                        left_mask,
                    ),
                    (
                        "right",
                        right_ids,
                        right_mask,
                    ),
                ]:
                    if not source_mask.any():
                        continue
                    mirrored_source = (
                        semantic_preflight_mirror_mask(
                            source_mask,
                            axis,
                            center_plane,
                        )
                    )
                    candidates = []
                    for candidate_id in sorted(
                        int(value)
                        for value in np.unique(
                            segment_grid
                        )
                        if int(value) > 0
                        and int(value)
                        not in set(source_ids)
                    ):
                        candidate_mask = (
                            segment_grid
                            == candidate_id
                        )
                        candidate_count = int(
                            candidate_mask.sum()
                        )
                        source_count = int(
                            source_mask.sum()
                        )
                        ratio = (
                            max(
                                source_count,
                                candidate_count,
                            )
                            / max(
                                min(
                                    source_count,
                                    candidate_count,
                                ),
                                1,
                            )
                        )
                        iou = (
                            semantic_preflight_mask_iou(
                                mirrored_source,
                                candidate_mask,
                            )
                        )
                        candidates.append((
                            iou,
                            -abs(ratio - 1.0),
                            candidate_id,
                            candidate_count,
                            ratio,
                        ))

                    maximum_suggestions = int(
                        config.get(
                            "maximum_suggestions_per_target",
                            5,
                        )
                    )
                    for rank, candidate in enumerate(
                        sorted(
                            candidates,
                            reverse=True,
                        )[
                            :maximum_suggestions
                        ],
                        start=1,
                    ):
                        (
                            iou,
                            _,
                            candidate_id,
                            candidate_count,
                            ratio,
                        ) = candidate
                        suggestion_rows.append({
                            "attachment_id": (
                                attachment_id
                            ),
                            "quarantined_side": (
                                side_name
                            ),
                            "quarantined_source_segment_ids": (
                                source_ids
                            ),
                            "candidate_rank": rank,
                            "candidate_segment_id": (
                                candidate_id
                            ),
                            "candidate_voxel_count": (
                                candidate_count
                            ),
                            "voxel_count_ratio": (
                                float(ratio)
                            ),
                            "mirror_iou": float(iou),
                            "center_plane": (
                                center_plane
                            ),
                            "applied": False,
                        })

    if quarantine_ids:
        quarantine_mask = effective[
            "segment_id"
        ].astype(int).isin(
            sorted(quarantine_ids)
        )
        effective.loc[
            quarantine_mask,
            "segment_label",
        ] = str(
            config.get(
                "quarantined_label",
                "unknown",
            )
        )
        effective.loc[
            quarantine_mask,
            "label_source",
        ] = (
            "semantic_preflight_quarantine"
        )
        effective.loc[
            quarantine_mask,
            "semantic_preflight_status",
        ] = "quarantined"
        effective.loc[
            quarantine_mask,
            "semantic_preflight_reason",
        ] = (
            "required_functional_pair_failed_geometry_checks"
        )

    effective.loc[
        ~effective["segment_id"].astype(int).isin(
            sorted(quarantine_ids)
        ),
        "semantic_preflight_status",
    ] = "retained"

    gate_valid = bool(
        all(required_gate_values)
        if required_gate_values
        else True
    )

    return {
        "effective_segment_table": effective,
        "audit_df": pd.DataFrame(
            audit_rows
        ),
        "suggestions_df": pd.DataFrame(
            suggestion_rows
        ),
        "quarantined_segment_ids": sorted(
            quarantine_ids
        ),
        "gate_valid": gate_valid,
        "center_plane": float(
            center_plane
        ),
    }

def attachment_declarations():
    return TASK_CONTEXT.get(
        "functional_attachments",
        TASK_CONTEXT.get("functional_attachments_declared", []),
    )


def group_physical_targets(segment_table):
    rows = []
    target_segment_ids = set()

    for declaration in attachment_declarations():
        attachment_id = declaration["attachment_id"]
        labels = {
            str(value).lower()
            for value in declaration.get("semantic_labels", [])
        }
        matching = segment_table[
            segment_table["segment_label"]
            .astype(str)
            .str.lower()
            .isin(labels)
        ].copy()

        grouping = declaration.get(
            "physical_target_grouping",
            {},
        )
        assigned = set()
        for group in grouping.get("manual_groups", []):
            requested_ids = {
                int(value)
                for value in group.get("source_segment_ids", [])
            }
            present_ids = sorted(
                requested_ids
                & set(matching["segment_id"].astype(int))
            )
            if not present_ids:
                continue
            rows.append({
                "attachment_id": attachment_id,
                "physical_target_id": group.get(
                    "physical_target_id",
                    f"{attachment_id}_manual_{len(rows) + 1}",
                ),
                "side": group.get("side", "unspecified"),
                "source_segment_ids": present_ids,
                "group_source": "manual_context",
            })
            assigned.update(present_ids)
            target_segment_ids.update(present_ids)

        remaining = matching[
            ~matching["segment_id"].isin(assigned)
        ].copy()
        remaining["side"] = remaining["segment_label"].map(
            lambda label: (
                "left"
                if "left" in str(label).lower()
                else (
                    "right"
                    if "right" in str(label).lower()
                    else "unspecified"
                )
            )
        )

        for side, side_rows in remaining.groupby("side"):
            ids = sorted(
                side_rows["segment_id"].astype(int).tolist()
            )
            groups = (
                [ids]
                if side in {"left", "right"}
                else [[segment_id] for segment_id in ids]
            )
            for group_number, source_ids in enumerate(
                groups,
                start=1,
            ):
                rows.append({
                    "attachment_id": attachment_id,
                    "physical_target_id": (
                        f"{attachment_id}_{side}_{group_number}"
                    ),
                    "side": side,
                    "source_segment_ids": source_ids,
                    "group_source": "semantic_side_group",
                })
                target_segment_ids.update(source_ids)

    return pd.DataFrame(
        rows,
        columns=[
            "attachment_id",
            "physical_target_id",
            "side",
            "source_segment_ids",
            "group_source",
        ],
    ), target_segment_ids


segments_labeled_initial_df = (
    segments_labeled_df.copy()
)
(
    provisional_physical_targets_df,
    provisional_functional_target_segment_ids,
) = group_physical_targets(
    segments_labeled_initial_df
)
semantic_preflight_result = (
    run_functional_semantic_preflight(
        segments_labeled_initial_df,
        provisional_physical_targets_df,
        segment_grid_planner_raw,
    )
)
segments_labeled_df = (
    semantic_preflight_result[
        "effective_segment_table"
    ]
)
segments_labeled_df.to_csv(
    OUTPUT_DIR
    / "segments_labeled_integrated.csv",
    index=False,
)
semantic_functional_preflight_audit_df = (
    semantic_preflight_result[
        "audit_df"
    ]
)
semantic_functional_preflight_audit_df.to_csv(
    OUTPUT_DIR
    / "semantic_functional_preflight_audit.csv",
    index=False,
)
semantic_functional_pair_suggestions_df = (
    semantic_preflight_result[
        "suggestions_df"
    ]
)
semantic_functional_pair_suggestions_df.to_csv(
    OUTPUT_DIR
    / "semantic_functional_pair_suggestions.csv",
    index=False,
)
semantic_preflight_quarantined_segment_ids = (
    semantic_preflight_result[
        "quarantined_segment_ids"
    ]
)
semantic_preflight_gate_valid = bool(
    semantic_preflight_result[
        "gate_valid"
    ]
)

segment_labels_dict = dict(
    zip(
        segments_labeled_df[
            "segment_id"
        ].astype(int),
        segments_labeled_df[
            "segment_label"
        ].astype(str),
    )
)
planner_segment_labels = dict(
    segment_labels_dict
)
physical_targets_df, functional_target_segment_ids = (
    group_physical_targets(
        segments_labeled_df
    )
)

print(
    "Semantic preflight gate valid:",
    semantic_preflight_gate_valid,
)
print(
    "Quarantined functional-label segments:",
    semantic_preflight_quarantined_segment_ids,
)
emit_diagnostic(
    semantic_functional_preflight_audit_df
)
if not semantic_functional_pair_suggestions_df.empty:
    emit_diagnostic(
        semantic_functional_pair_suggestions_df
    )


def choose_root_segment(structural_segment_ids):
    labels = dict(
        zip(
            segments_labeled_df["segment_id"].astype(int),
            segments_labeled_df["segment_label"].astype(str),
        )
    )
    counts = dict(
        zip(
            segments_labeled_df["segment_id"].astype(int),
            segments_labeled_df["voxel_count"].astype(int),
        )
    )
    preferred = (
        TASK_CONTEXT.get("segment_assembly", {})
        .get("assembly_graph", {})
        .get("preferred_root_labels", [])
    )
    for label in preferred:
        matches = [
            segment_id
            for segment_id in structural_segment_ids
            if labels.get(segment_id, "").lower()
            == str(label).lower()
        ]
        if matches:
            return max(matches, key=lambda value: counts.get(value, 0))
    return max(
        structural_segment_ids,
        key=lambda value: counts.get(value, 0),
    )


class DisjointSet:
    def __init__(self, values):
        self.parent = {value: value for value in values}

    def find(self, value):
        while self.parent[value] != value:
            self.parent[value] = self.parent[
                self.parent[value]
            ]
            value = self.parent[value]
        return value

    def union(self, value_a, value_b):
        root_a = self.find(value_a)
        root_b = self.find(value_b)
        if root_a == root_b:
            return False
        self.parent[root_b] = root_a
        return True


def required_assembly_interfaces(
    interfaces_df,
    structural_segment_ids,
):
    disjoint_set = DisjointSet(structural_segment_ids)
    required = set()
    for row in interfaces_df.sort_values(
        ["contact_area", "interface_id"],
        ascending=[False, True],
    ).itertuples(index=False):
        if disjoint_set.union(
            int(row.segment_a),
            int(row.segment_b),
        ):
            required.add(row.interface_id)
    result = interfaces_df.copy()
    result["assembly_edge_role"] = np.where(
        result["interface_id"].isin(required),
        "required_spanning_forest",
        "optional_non_tree",
    )
    return result, required


def box_coordinates(origin, size):
    x0, y0, z0 = (int(value) for value in origin)
    dx, dy, dz = (int(value) for value in size)
    return [
        (x, y, z)
        for x in range(x0, x0 + dx)
        for y in range(y0, y0 + dy)
        for z in range(z0, z0 + dz)
    ]


def box_mask(shape, origin, size):
    mask = np.zeros(shape, dtype=bool)
    x0, y0, z0 = (int(value) for value in origin)
    dx, dy, dz = (int(value) for value in size)
    if (
        x0 < 0 or y0 < 0 or z0 < 0
        or x0 + dx > shape[0]
        or y0 + dy > shape[1]
        or z0 + dz > shape[2]
    ):
        return None
    mask[
        x0:x0 + dx,
        y0:y0 + dy,
        z0:z0 + dz,
    ] = True
    return mask


NEIGHBOR_OFFSETS = [
    (1, 0, 0), (-1, 0, 0),
    (0, 1, 0), (0, -1, 0),
    (0, 0, 1), (0, 0, -1),
]


def boundary_contact_area(box, target_mask):
    coordinates = set(map(tuple, np.argwhere(box)))
    target_coordinates = set(
        map(tuple, np.argwhere(target_mask))
    )
    contacts = set()
    for coordinate in coordinates:
        for offset in NEIGHBOR_OFFSETS:
            neighbor = tuple(
                coordinate[axis] + offset[axis]
                for axis in range(3)
            )
            if neighbor in target_coordinates:
                contacts.add((coordinate, neighbor))
    return len(contacts)


def exact_2x2_footprint_mask(mask):
    sx, sy, _ = mask.shape
    for x in range(0, sx - 1, 2):
        for y in range(0, sy - 1, 2):
            counts = mask[x:x + 2, y:y + 2, :].sum(
                axis=(0, 1)
            )
            if np.any((counts > 0) & (counts < 4)):
                return False
    return True


def candidate_origins_near_interface(
    size,
    normal_face,
    coordinate_pairs,
    shape,
):
    axis, sign = FACE_AXIS_SIGN[normal_face]
    pairs = [
        (
            np.asarray(a, dtype=int),
            np.asarray(b, dtype=int),
        )
        for a, b in coordinate_pairs
    ]
    center = np.mean(
        [0.5 * (a + b) for a, b in pairs],
        axis=0,
    )
    plane = int(
        round(
            np.mean(
                [
                    max(a[axis], b[axis])
                    for a, b in pairs
                ]
            )
        )
    )

    origins_by_axis = []
    for current_axis in range(3):
        dimension = int(size[current_axis])
        maximum_origin = shape[current_axis] - dimension
        if maximum_origin < 0:
            return []

        if current_axis == axis:
            values = range(
                plane - dimension + 1,
                plane,
            )
        else:
            central = int(math.floor(center[current_axis]))
            values = range(
                central - dimension + 1,
                central + 1,
            )
        origins_by_axis.append(
            sorted(
                {
                    min(max(int(value), 0), maximum_origin)
                    for value in values
                }
            )
        )

    return list(product(*origins_by_axis))


def generate_structural_connector_candidates(
    required_interfaces_df,
    interface_payload,
    structural_segment_ids,
    interface_catalog_queries=None,
):
    selector_name = (
        TASK_CONTEXT.get(
            "segment_assembly",
            {},
        )
        .get(
            "structural_connector_policy",
            {},
        )
        .get(
            "catalog_selector",
            "segment_connector",
        )
    )
    default_selector = (
        TASK_CONTEXT.get(
            "catalog",
            {},
        )
        .get(
            "selectors",
            {},
        )
        .get(
            selector_name,
            {"all": []},
        )
    )
    interface_catalog_queries = (
        interface_catalog_queries
        or {}
    )

    policy = (
        TASK_CONTEXT.get(
            "segment_assembly",
            {},
        )
        .get(
            "structural_connector_policy",
            {},
        )
    )
    minimum_overlap = int(
        policy.get(
            "minimum_source_overlap_voxels_per_segment",
            1,
        )
    )
    minimum_contact = int(
        policy.get(
            "minimum_retained_contact_area_per_segment",
            1,
        )
    )
    maximum_candidates = int(
        policy.get(
            "maximum_candidates_per_interface",
            500,
        )
    )
    all_structural_mask = np.isin(
        segment_grid_planner,
        list(structural_segment_ids),
    )

    query_cache = {}
    catalog_record_union = {}
    candidates = []
    candidate_number = 1

    for interface in (
        required_interfaces_df.itertuples(
            index=False
        )
    ):
        interface_id = str(
            interface.interface_id
        )
        query = (
            interface_catalog_queries.get(
                interface_id
            )
            or interface_catalog_queries.get(
                interface.interface_id
            )
            or default_selector
        )
        query_key = json.dumps(
            llm2_json_safe(query),
            sort_keys=True,
        )

        if query_key not in query_cache:
            catalog_records = (
                select_catalog_records(
                    query
                )
            )
            prepared_variants = [
                variant
                for record in catalog_records
                for variant in (
                    oriented_catalog_variants(
                        record
                    )
                )
            ]
            query_cache[query_key] = (
                catalog_records,
                prepared_variants,
            )

            for record in catalog_records:
                family = str(
                    record.get(
                        "block_family",
                        "",
                    )
                )
                catalog_record_union[
                    family
                ] = dict(record)

        (
            catalog_records,
            prepared_variants,
        ) = query_cache[query_key]

        segment_a = int(
            interface.segment_a
        )
        segment_b = int(
            interface.segment_b
        )
        mask_a = (
            segment_grid_planner
            == segment_a
        )
        mask_b = (
            segment_grid_planner
            == segment_b
        )
        unrelated = (
            all_structural_mask
            & ~mask_a
            & ~mask_b
        )
        coordinates = interface_payload[
            interface.interface_id
        ]
        coordinate_pairs = list(
            zip(
                coordinates[
                    "a_coordinates"
                ],
                coordinates[
                    "b_coordinates"
                ],
            )
        )
        interface_candidates = []

        for variant in prepared_variants:
            normal_role = (
                variant[
                    "face_roles"
                ].get(
                    interface.normal_a_to_b,
                    "none",
                )
            )
            opposite_role = (
                variant[
                    "face_roles"
                ].get(
                    OPPOSITE_FACE[
                        interface.normal_a_to_b
                    ],
                    "none",
                )
            )
            if (
                normal_role == "none"
                or opposite_role == "none"
            ):
                continue

            for origin in (
                candidate_origins_near_interface(
                    variant["size"],
                    interface.normal_a_to_b,
                    coordinate_pairs,
                    segment_grid_planner.shape,
                )
            ):
                geometry = box_mask(
                    segment_grid_planner.shape,
                    origin,
                    variant["size"],
                )
                if geometry is None:
                    continue

                overlap_a = int(
                    (
                        geometry
                        & mask_a
                    ).sum()
                )
                overlap_b = int(
                    (
                        geometry
                        & mask_b
                    ).sum()
                )
                unrelated_overlap = int(
                    (
                        geometry
                        & unrelated
                    ).sum()
                )
                if (
                    overlap_a
                    < minimum_overlap
                    or overlap_b
                    < minimum_overlap
                    or unrelated_overlap > 0
                ):
                    continue

                retained_a = (
                    mask_a
                    & ~geometry
                )
                retained_b = (
                    mask_b
                    & ~geometry
                )
                if (
                    not retained_a.any()
                    or not retained_b.any()
                    or not exact_2x2_footprint_mask(
                        retained_a
                    )
                    or not exact_2x2_footprint_mask(
                        retained_b
                    )
                ):
                    continue

                contact_a = (
                    boundary_contact_area(
                        geometry,
                        retained_a,
                    )
                )
                contact_b = (
                    boundary_contact_area(
                        geometry,
                        retained_b,
                    )
                )
                if (
                    contact_a
                    < minimum_contact
                    or contact_b
                    < minimum_contact
                ):
                    continue

                empty_volume = int(
                    geometry.sum()
                    - overlap_a
                    - overlap_b
                )
                score = (
                    min(
                        contact_a,
                        contact_b,
                    )
                    * 1000
                    + contact_a
                    + contact_b
                    + min(
                        overlap_a,
                        overlap_b,
                    )
                    * 10
                    - empty_volume
                )
                interface_candidates.append(
                    {
                        "candidate_id": (
                            candidate_number
                        ),
                        "interface_id": (
                            interface.interface_id
                        ),
                        "segment_a": segment_a,
                        "segment_b": segment_b,
                        "block_role": (
                            "structural_"
                            "segment_connector"
                        ),
                        "block_family": (
                            variant[
                                "block_family"
                            ]
                        ),
                        "catalog_record": (
                            variant[
                                "catalog_record"
                            ]
                        ),
                        "catalog_query_source": (
                            "llm2_or_fallback"
                        ),
                        "origin": tuple(
                            int(value)
                            for value in origin
                        ),
                        "size": tuple(
                            int(value)
                            for value in (
                                variant["size"]
                            )
                        ),
                        "face_roles": (
                            variant[
                                "face_roles"
                            ]
                        ),
                        "rotation_matrix": (
                            variant[
                                "rotation_matrix"
                            ]
                        ),
                        "overlap_a": overlap_a,
                        "overlap_b": overlap_b,
                        "retained_contact_a": (
                            contact_a
                        ),
                        "retained_contact_b": (
                            contact_b
                        ),
                        "unrelated_overlap": (
                            unrelated_overlap
                        ),
                        "score": score,
                        "geometry_coordinates": (
                            box_coordinates(
                                origin,
                                variant["size"],
                            )
                        ),
                    }
                )
                candidate_number += 1

        interface_candidates.sort(
            key=lambda row: (
                -row["score"],
                row["block_family"],
                row["origin"],
            )
        )
        candidates.extend(
            interface_candidates[
                :maximum_candidates
            ]
        )

    return (
        pd.DataFrame(candidates),
        list(
            catalog_record_union.values()
        ),
    )


def select_nonoverlapping_candidates(
    candidates_df,
    group_column,
    initial_reserved_coordinates=None,
):
    if candidates_df.empty:
        return pd.DataFrame()

    reserved = set(initial_reserved_coordinates or [])
    selected = []
    for group_value, group in candidates_df.groupby(
        group_column,
        sort=True,
    ):
        group = group.sort_values(
            ["score", "candidate_id"],
            ascending=[False, True],
        )
        chosen = None
        for _, row in group.iterrows():
            coordinates = {
                tuple(value)
                for value in row["geometry_coordinates"]
            }
            if coordinates & reserved:
                continue
            chosen = row.to_dict()
            reserved.update(coordinates)
            break
        if chosen is not None:
            selected.append(chosen)
    return pd.DataFrame(selected)


def iter_segment_contact_records(contact_data):
    """Normalize mapping, DataFrame, dictionary, and tuple contact formats."""
    if contact_data is None:
        return
    if isinstance(contact_data, pd.DataFrame):
        yield from contact_data.to_dict(orient="records")
        return
    if isinstance(contact_data, dict):
        for key, value in contact_data.items():
            if isinstance(key, (tuple, list)) and len(key) >= 2:
                entries = value if isinstance(value, (list, tuple)) else []
                yield {
                    "segment_a": int(key[0]),
                    "segment_b": int(key[1]),
                    "area": int(len(entries)),
                    "contacts": entries,
                }
            elif isinstance(value, dict):
                yield value
        return
    for contact in contact_data:
        if isinstance(contact, dict):
            yield contact
        elif (
            isinstance(contact, (tuple, list))
            and len(contact) == 2
            and isinstance(contact[0], (tuple, list))
            and len(contact[0]) >= 2
        ):
            key, value = contact
            entries = value if isinstance(value, (list, tuple)) else []
            yield {
                "segment_a": int(key[0]),
                "segment_b": int(key[1]),
                "area": int(len(entries)),
                "contacts": entries,
            }


def find_anchor_for_target(source_segment_ids, structural_ids):
    best = None
    source_ids = {int(value) for value in source_segment_ids}
    structural_ids = {int(value) for value in structural_ids}
    for contact in iter_segment_contact_records(raw_contacts):
        segment_a = int(contact["segment_a"])
        segment_b = int(contact["segment_b"])
        if segment_a in source_ids and segment_b in structural_ids:
            target_id, anchor_id = segment_a, segment_b
        elif segment_b in source_ids and segment_a in structural_ids:
            target_id, anchor_id = segment_b, segment_a
        else:
            continue
        area = int(
            contact.get("area", len(contact.get("contacts", [])))
        )
        if best is None or area > best["area"]:
            best = {
                "target_segment_id": target_id,
                "anchor_segment_id": anchor_id,
                "area": area,
            }
    return best


def target_candidate_origins(target_mask, size):
    coordinates = np.argwhere(target_mask)
    if len(coordinates) == 0:
        return []
    minimum = coordinates.min(axis=0)
    maximum = coordinates.max(axis=0)
    ranges = []
    for axis in range(3):
        dimension = int(size[axis])
        low = max(0, int(minimum[axis]) - dimension + 1)
        high = min(
            int(maximum[axis]),
            target_mask.shape[axis] - dimension,
        )
        if high < low:
            return []
        ranges.append(range(low, high + 1))

    centroid = coordinates.mean(axis=0)
    origins = list(product(*ranges))
    origins.sort(
        key=lambda origin: sum(
            abs(
                origin[axis]
                + 0.5 * size[axis]
                - centroid[axis]
            )
            for axis in range(3)
        )
    )
    return origins[:1000]


def wheel_axle_axis_index():
    axis_name = str(
        TASK_CONTEXT.get(
            "segment_assembly",
            {},
        )
        .get(
            "functional_attachment_policy",
            {},
        )
        .get(
            "wheel_axle_axis",
            "X",
        )
    ).upper()

    return {
        "X": 0,
        "Y": 1,
        "Z": 2,
    }[
        axis_name
    ]


def is_wheel_catalog_record(
    record,
    block_family=None,
):
    role = str(
        record.get(
            "functional_role",
            "",
        )
    ).lower()
    family = str(
        block_family
        or record.get(
            "block_family",
            "",
        )
    ).lower()

    return bool(
        role == "wheel"
        or "wheel" in family
    )


def wheel_variant_stands_on_z(
    size,
):
    """
    A standing wheel has its axle along X and its disc in the YZ plane.
    """
    size = tuple(
        int(
            value
        )
        for value in size
    )
    axle_axis = (
        wheel_axle_axis_index()
    )
    if axle_axis != 0:
        return False

    depth = int(
        size[
            axle_axis
        ]
    )
    return bool(
        depth
        == min(
            size
        )
        and int(
            size[
                1
            ]
        )
        > depth
        and int(
            size[
                2
            ]
        )
        > depth
    )


def validate_selected_wheel_orientations(
    selected_functional_df,
):
    if selected_functional_df.empty:
        return (
            selected_functional_df.copy(),
            pd.DataFrame(),
        )

    selected = (
        selected_functional_df.copy()
    )
    audit_rows = []

    for row_index, row in (
        selected.iterrows()
    ):
        record = (
            row.get(
                "catalog_record",
                {},
            )
            or {}
        )
        family = str(
            row.get(
                "block_family",
                "",
            )
        )
        if not is_wheel_catalog_record(
            record,
            family,
        ):
            continue

        size = tuple(
            int(
                value
            )
            for value in row[
                "size"
            ]
        )
        valid = (
            wheel_variant_stands_on_z(
                size
            )
        )

        if not valid:
            raise RuntimeError(
                "Selected wheel is flat. "
                f"Target={row.get('physical_target_id')}; "
                f"origin={row.get('origin')}; size={size}. "
                "Expected size with the thin dimension on X "
                "and wheel diameter along Y and Z."
            )

        selected.at[
            row_index,
            "wheel_axle_axis_index",
        ] = 0
        selected.at[
            row_index,
            "wheel_axle_axis",
        ] = "X"
        selected.at[
            row_index,
            "wheel_disc_plane",
        ] = "YZ"
        selected.at[
            row_index,
            "wheel_vertical_axis",
        ] = "Z"
        selected.at[
            row_index,
            "wheel_orientation_valid",
        ] = True

        audit_rows.append(
            {
                "physical_target_id": str(
                    row.get(
                        "physical_target_id"
                    )
                ),
                "block_family": (
                    family
                ),
                "origin": tuple(
                    int(
                        value
                    )
                    for value in row[
                        "origin"
                    ]
                ),
                "size": (
                    size
                ),
                "axle_axis": "X",
                "disc_plane": "YZ",
                "vertical_axis": "Z",
                "thickness_x": int(
                    size[
                        0
                    ]
                ),
                "diameter_y": int(
                    size[
                        1
                    ]
                ),
                "diameter_z": int(
                    size[
                        2
                    ]
                ),
                "valid": True,
            }
        )

    return (
        selected,
        pd.DataFrame(
            audit_rows
        ),
    )

def functional_record_family(
    record,
):
    return str(
        record.get(
            "block_family",
            "",
        )
    ).strip()


def big_wheel_visible_variant(
    record,
    target,
):
    """
    Use the catalog visible disc as the rendered/collision geometry.

    The catalog's second depth layer is the hidden 2x2 attachment layer. It is
    validated through anchor_contact_area rather than rendered as a full 3x3
    rectangular layer.
    """
    prepared = (
        prepare_general_catalog_record(
            record
        )
    )
    side = str(
        getattr(
            target,
            "side",
            "",
        )
    ).lower()

    face_roles = {
        face: "none"
        for face in ALL_FACES
    }
    if side == "left":
        face_roles[
            "+X"
        ] = "male"
    elif side == "right":
        face_roles[
            "-X"
        ] = "male"
    else:
        face_roles[
            "+X"
        ] = "male"

    prepared = dict(
        prepared
    )
    prepared[
        "candidate_geometry_mode"
    ] = (
        "visible_disc_with_hidden_catalog_anchor"
    )
    prepared[
        "visible_geometry_size_world"
    ] = (
        1,
        3,
        3,
    )

    return {
        "block_family": "big_wheel",
        "catalog_record": prepared,
        "size": (
            1,
            3,
            3,
        ),
        "face_roles": face_roles,
        "rotation_matrix": [
            [
                1,
                0,
                0,
            ],
            [
                0,
                1,
                0,
            ],
            [
                0,
                0,
                1,
            ],
        ],
        "candidate_geometry_mode": (
            "visible_disc_with_hidden_catalog_anchor"
        ),
    }


def functional_variants_for_target(
    record,
    target,
):
    if functional_record_family(
        record
    ) == "big_wheel":
        return [
            big_wheel_visible_variant(
                record,
                target,
            )
        ]
    return oriented_catalog_variants(
        record
    )


def big_wheel_candidate_origins(
    target_mask,
    size,
):
    coordinates = np.argwhere(
        target_mask
    )
    if len(
        coordinates
    ) == 0:
        return []

    minimum = coordinates.min(
        axis=0
    )
    maximum = coordinates.max(
        axis=0
    )
    center = (
        minimum.astype(
            float
        )
        + maximum.astype(
            float
        )
    ) / 2.0

    origin = [
        int(
            minimum[
                0
            ]
        ),
        int(
            math.floor(
                center[
                    1
                ]
                - (
                    int(
                        size[
                            1
                        ]
                    )
                    - 1
                )
                / 2.0
            )
        ),
        int(
            math.floor(
                center[
                    2
                ]
                - (
                    int(
                        size[
                            2
                        ]
                    )
                    - 1
                )
                / 2.0
            )
        ),
    ]

    # Big wheels may extend below the voxel grid, but not beyond X/Y bounds.
    if (
        origin[
            0
        ]
        < 0
        or origin[
            0
        ]
        + int(
            size[
                0
            ]
        )
        > target_mask.shape[
            0
        ]
        or origin[
            1
        ]
        < 0
        or origin[
            1
        ]
        + int(
            size[
                1
            ]
        )
        > target_mask.shape[
            1
        ]
    ):
        return []

    if (
        origin[
            2
        ]
        + int(
            size[
                2
            ]
        )
        <= 0
        or origin[
            2
        ]
        >= target_mask.shape[
            2
        ]
    ):
        return []

    return [
        tuple(
            origin
        )
    ]


def clipped_box_mask(
    shape,
    origin,
    size,
):
    starts = [
        max(
            0,
            int(
                origin[
                    axis
                ]
            ),
        )
        for axis in range(
            3
        )
    ]
    ends = [
        min(
            int(
                shape[
                    axis
                ]
            ),
            int(
                origin[
                    axis
                ]
            )
            + int(
                size[
                    axis
                ]
            ),
        )
        for axis in range(
            3
        )
    ]
    if any(
        starts[
            axis
        ]
        >= ends[
            axis
        ]
        for axis in range(
            3
        )
    ):
        return None

    mask = np.zeros(
        shape,
        dtype=bool,
    )
    mask[
        starts[
            0
        ]:
        ends[
            0
        ],
        starts[
            1
        ]:
        ends[
            1
        ],
        starts[
            2
        ]:
        ends[
            2
        ],
    ] = True
    return mask


def mask_coordinate_list(
    mask,
):
    return [
        tuple(
            int(
                value
            )
            for value in coordinate
        )
        for coordinate in np.argwhere(
            mask
        )
    ]


def functional_candidate_origins(
    target_mask,
    variant,
):
    if str(
        variant.get(
            "block_family",
            "",
        )
    ) == "big_wheel":
        return big_wheel_candidate_origins(
            target_mask,
            variant[
                "size"
            ],
        )
    return target_candidate_origins(
        target_mask,
        variant[
            "size"
        ],
    )


def functional_candidate_geometry_mask(
    shape,
    origin,
    variant,
):
    if str(
        variant.get(
            "block_family",
            "",
        )
    ) == "big_wheel":
        return clipped_box_mask(
            shape,
            origin,
            variant[
                "size"
            ],
        )
    return box_mask(
        shape,
        origin,
        variant[
            "size"
        ],
    )


def functional_anchor_contact_area(
    record,
    block_family,
    raw_contact_area,
):
    if str(
        block_family
    ) != "big_wheel":
        return int(
            raw_contact_area
        )

    anchor_size = parse_catalog_size(
        record.get(
            "anchor_size",
            "2x2x1",
        )
    )
    anchor_area_limit = int(
        np.prod(
            anchor_size
        )
    )
    return int(
        min(
            int(
                raw_contact_area
            ),
            anchor_area_limit,
        )
    )

def generate_functional_candidates(
    physical_targets,
    structural_segment_ids,
):
    rows = []
    candidate_number = 1
    declaration_by_id = {
        declaration[
            "attachment_id"
        ]: declaration
        for declaration in (
            attachment_declarations()
        )
    }
    minimum_ratio = float(
        TASK_CONTEXT.get(
            "functional_attachment_policy",
            {},
        ).get(
            "minimum_candidate_source_overlap_ratio",
            0.15,
        )
    )

    for target in physical_targets.itertuples(
        index=False
    ):
        declaration = (
            declaration_by_id[
                target.attachment_id
            ]
        )
        target_mask = np.isin(
            segment_grid_planner,
            [
                int(value)
                for value in (
                    target.source_segment_ids
                )
            ],
        )
        anchor = find_anchor_for_target(
            target.source_segment_ids,
            set(structural_segment_ids),
        )
        if anchor is None:
            LLM2_FUNCTIONAL_DECISION_ROWS.append(
                {
                    "scope": "functional_target",
                    "attachment_id": str(
                        target.attachment_id
                    ),
                    "physical_target_id": str(
                        target.physical_target_id
                    ),
                    "valid": False,
                    "decision_source": (
                        "no_anchor"
                    ),
                    "reason": (
                        "No structural anchor "
                        "was found."
                    ),
                }
            )
            continue

        decision = (
            llm2_resolve_functional_decision(
                target,
                declaration,
                anchor,
            )
        )
        LLM2_FUNCTIONAL_DECISION_ROWS.append(
            decision
        )
        catalog_records = (
            select_catalog_records(
                decision[
                    "catalog_query"
                ]
            )
            if decision.get(
                "valid",
                False,
            )
            else []
        )
        required_block_family = (
            confirmed_exact_block_family_requirement(
                declaration
            )
        )
        if required_block_family:
            catalog_records = [
                record
                for record in catalog_records
                if str(
                    record.get(
                        "block_family",
                        "",
                    )
                )
                == required_block_family
            ]
            decision[
                "task_required_block_family"
            ] = required_block_family
            decision[
                "matched_block_families"
            ] = [
                record.get(
                    "block_family"
                )
                for record in catalog_records
            ]

        target_mask = np.isin(
            segment_grid_planner,
            [
                int(value)
                for value in (
                    target.source_segment_ids
                )
            ],
        )
        anchor_mask = (
            segment_grid_planner
            == int(
                anchor[
                    "anchor_segment_id"
                ]
            )
        )
        other_mask = (
            (
                segment_grid_planner
                > 0
            )
            & ~target_mask
            & ~anchor_mask
        )
        target_voxels = max(
            1,
            int(
                target_mask.sum()
            ),
        )

        for record in catalog_records:
            for variant in (
                functional_variants_for_target(
                    record,
                    target,
                )
            ):
                if (
                    is_wheel_catalog_record(
                        record,
                        variant.get(
                            "block_family"
                        ),
                    )
                    and not wheel_variant_stands_on_z(
                        variant[
                            "size"
                        ]
                    )
                ):
                    continue

                for origin in (
                    functional_candidate_origins(
                        target_mask,
                        variant,
                    )
                ):
                    geometry = (
                        functional_candidate_geometry_mask(
                            segment_grid_planner.shape,
                            origin,
                            variant,
                        )
                    )
                    if geometry is None:
                        continue

                    overlap = int(
                        (
                            geometry
                            & target_mask
                        ).sum()
                    )
                    overlap_ratio = (
                        overlap
                        / target_voxels
                    )
                    if (
                        overlap_ratio
                        < minimum_ratio
                    ):
                        continue

                    anchor_overlap = int(
                        (
                            geometry
                            & anchor_mask
                        ).sum()
                    )
                    other_overlap = int(
                        (
                            geometry
                            & other_mask
                        ).sum()
                    )
                    if (
                        anchor_overlap > 0
                        or other_overlap > 0
                    ):
                        continue

                    raw_contact_area = (
                        boundary_contact_area(
                            geometry,
                            anchor_mask,
                        )
                    )
                    contact_area = (
                        functional_anchor_contact_area(
                            record,
                            variant[
                                "block_family"
                            ],
                            raw_contact_area,
                        )
                    )
                    if contact_area <= 0:
                        continue

                    empty_volume = int(
                        geometry.sum()
                        - overlap
                    )
                    score = (
                        int(
                            round(
                                overlap_ratio
                                * 10000
                            )
                        )
                        + contact_area
                        * 100
                        - empty_volume
                    )
                    rows.append(
                        {
                            "candidate_id": (
                                candidate_number
                            ),
                            "attachment_id": (
                                target.attachment_id
                            ),
                            "physical_target_id": (
                                target.physical_target_id
                            ),
                            "source_segment_ids": (
                                target.source_segment_ids
                            ),
                            "anchor_segment_id": int(
                                anchor[
                                    "anchor_segment_id"
                                ]
                            ),
                            "block_role": (
                                "functional_"
                                "attachment"
                            ),
                            "block_family": (
                                variant[
                                    "block_family"
                                ]
                            ),
                            "catalog_record": (
                                variant[
                                    "catalog_record"
                                ]
                            ),
                            "llm2_connection_type": (
                                decision.get(
                                    "connection_type"
                                )
                            ),
                            "llm2_decision_source": (
                                decision.get(
                                    "decision_source"
                                )
                            ),
                            "origin": tuple(
                                int(value)
                                for value in origin
                            ),
                            "size": tuple(
                                int(value)
                                for value in (
                                    variant[
                                        "size"
                                    ]
                                )
                            ),
                            "face_roles": (
                                variant[
                                    "face_roles"
                                ]
                            ),
                            "rotation_matrix": (
                                variant[
                                    "rotation_matrix"
                                ]
                            ),
                            "source_overlap_voxels": (
                                overlap
                            ),
                            "source_overlap_ratio": (
                                overlap_ratio
                            ),
                            "anchor_contact_area": (
                                contact_area
                            ),
                            "score": score,
                            "geometry_coordinates": (
                                mask_coordinate_list(
                                    geometry
                                )
                            ),
                            "full_geometry_coordinates": (
                                box_coordinates(
                                    origin,
                                    variant[
                                        "size"
                                    ],
                                )
                            ),
                            "off_grid_voxel_count": int(
                                np.prod(
                                    variant[
                                        "size"
                                    ]
                                )
                                - int(
                                    geometry.sum()
                                )
                            ),
                            "candidate_geometry_mode": (
                                variant.get(
                                    "candidate_geometry_mode",
                                    "full_axis_aligned_box",
                                )
                            ),
                            "wheel_axle_axis_index": (
                                0
                                if is_wheel_catalog_record(
                                    record,
                                    variant.get(
                                        "block_family"
                                    ),
                                )
                                else None
                            ),
                            "wheel_axle_axis": (
                                "X"
                                if is_wheel_catalog_record(
                                    record,
                                    variant.get(
                                        "block_family"
                                    ),
                                )
                                else None
                            ),
                            "wheel_disc_plane": (
                                "YZ"
                                if is_wheel_catalog_record(
                                    record,
                                    variant.get(
                                        "block_family"
                                    ),
                                )
                                else None
                            ),
                            "wheel_vertical_axis": (
                                "Z"
                                if is_wheel_catalog_record(
                                    record,
                                    variant.get(
                                        "block_family"
                                    ),
                                )
                                else None
                            ),
                        }
                    )
                    candidate_number += 1

    return pd.DataFrame(rows)


def mask_from_selected_candidates(shape, selected_df):
    mask = np.zeros(shape, dtype=bool)
    if selected_df.empty:
        return mask
    for coordinates in selected_df["geometry_coordinates"]:
        for coordinate in coordinates:
            mask[tuple(int(value) for value in coordinate)] = True
    return mask


def rasterize_blocks(blocks, shape):
    mask = np.zeros(shape, dtype=bool)
    for block in blocks:
        x, y, z = block.position
        dx, dy, dz = block.size
        mask[x:x + dx, y:y + dy, z:z + dz] = True
    return mask


def reindex_segment_plan(
    planning_result,
    next_block_id,
    segment_id,
    segment_label,
):
    blocks = planning_result["blocks"]
    mapping = {}
    for block in blocks:
        old_id = int(block.block_id)
        mapping[old_id] = int(next_block_id)
        block.block_id = int(next_block_id)
        block.source_segment_id = int(segment_id)
        block.segment_label = str(segment_label)
        block.subassembly_id = f"segment_{int(segment_id)}"
        block.block_role = "segment_structural"
        next_block_id += 1

    return planning_result, next_block_id

def parse_block_id_field(
    value,
):
    if value is None:
        return []
    if isinstance(
        value,
        (
            list,
            tuple,
            set,
            np.ndarray,
        ),
    ):
        return [
            int(item)
            for item in value
        ]
    if isinstance(
        value,
        (
            float,
            np.floating,
        ),
    ) and np.isnan(
        value
    ):
        return []

    text = str(
        value
    ).strip()
    if not text:
        return []

    return [
        int(token.strip())
        for token in text.split(",")
        if token.strip()
    ]


def format_block_id_field(
    values,
):
    return ",".join(
        str(
            int(value)
        )
        for value in values
    )


def remap_validation_block_ids_to_planning(
    validation,
    planning_result,
):
    """
    Align validation IDs with the globally reindexed planning blocks.
    """
    remapped = copy.deepcopy(
        validation
    )
    block_rows = remapped.get(
        "block_rows",
        [],
    )
    instruction_steps = planning_result.get(
        "instruction_steps",
        [],
    )

    mapping = {}
    for step_number, step in enumerate(
        instruction_steps,
        start=1,
    ):
        local_rows = sorted(
            [
                row
                for row in block_rows
                if int(
                    row.get(
                        "step",
                        -1,
                    )
                )
                == step_number
            ],
            key=lambda row: int(
                row.get(
                    "block_id",
                    0,
                )
            ),
        )
        global_blocks = sorted(
            list(
                step.get(
                    "blocks",
                    [],
                )
            ),
            key=lambda block: (
                int(
                    block.position[
                        0
                    ]
                ),
                int(
                    block.position[
                        2
                    ]
                ),
                int(
                    block.size[
                        2
                    ]
                ),
                int(
                    block.block_id
                ),
            ),
        )

        if len(
            local_rows
        ) != len(
            global_blocks
        ):
            raise RuntimeError(
                "Cannot align validation IDs for "
                f"step {step_number}: "
                f"{len(local_rows)} validation rows versus "
                f"{len(global_blocks)} planning blocks."
            )

        for local_row, global_block in zip(
            local_rows,
            global_blocks,
        ):
            mapping[
                int(
                    local_row[
                        "block_id"
                    ]
                )
            ] = int(
                global_block.block_id
            )

    if not mapping:
        return remapped

    def remap_id(
        value,
    ):
        return int(
            mapping.get(
                int(
                    value
                ),
                int(
                    value
                ),
            )
        )

    def remap_field(
        value,
    ):
        return format_block_id_field(
            [
                remap_id(
                    item
                )
                for item in parse_block_id_field(
                    value
                )
            ]
        )

    for row in remapped.get(
        "block_rows",
        [],
    ):
        row[
            "block_id"
        ] = remap_id(
            row[
                "block_id"
            ]
        )

    block_validation = {}
    for old_key, row in remapped.get(
        "block_validation",
        {},
    ).items():
        new_row = copy.deepcopy(
            row
        )
        new_id = remap_id(
            new_row.get(
                "block_id",
                old_key,
            )
        )
        new_row[
            "block_id"
        ] = new_id
        block_validation[
            str(
                new_id
            )
        ] = new_row
    remapped[
        "block_validation"
    ] = block_validation

    for row in remapped.get(
        "component_rows",
        [],
    ):
        for field in [
            "block_ids",
            "accepted_block_ids",
            "rejected_block_ids",
            "direct_conflict_block_ids",
        ]:
            row[
                field
            ] = remap_field(
                row.get(
                    field
                )
            )

    for row in remapped.get(
        "contact_rows",
        [],
    ):
        row[
            "block_a"
        ] = remap_id(
            row[
                "block_a"
            ]
        )
        row[
            "block_b"
        ] = remap_id(
            row[
                "block_b"
            ]
        )

    for field in [
        "accepted_before_by_step",
        "accepted_after_by_step",
    ]:
        remapped[
            field
        ] = {
            key: [
                remap_id(
                    value
                )
                for value in values
            ]
            for key, values in remapped.get(
                field,
                {},
            ).items()
        }

    for row in remapped.get(
        "step_rows",
        [],
    ):
        row[
            "accepted_block_ids"
        ] = remap_field(
            row.get(
                "accepted_block_ids"
            )
        )
        row[
            "rejected_block_ids"
        ] = remap_field(
            row.get(
                "rejected_block_ids"
            )
        )

    remapped[
        "id_remap"
    ] = {
        str(
            old_id
        ): int(
            new_id
        )
        for old_id, new_id in sorted(
            mapping.items()
        )
    }
    remapped[
        "id_namespace"
    ] = "global_final_block_ids"

    return remapped

def consolidation_sequence_key(sequence):
    sequence = tuple(int(value) for value in sequence)
    return (
        len(sequence),
        -sum(
            EFFECTIVE_PACKING_PRIORITY_BY_HEIGHT[
                int(height)
            ]
            for height in sequence
        ),
        larger_block_tie_break_key(sequence),
        sequence,
    )


def rebuild_instruction_steps_from_blocks(
    blocks,
    row_values=None,
):
    row_to_blocks = defaultdict(list)
    for block in blocks:
        row_to_blocks[int(block.position[1])].append(block)

    ordered_rows = (
        sorted(int(value) for value in row_values)
        if row_values is not None
        else sorted(row_to_blocks)
    )

    steps = []
    for row_value in ordered_rows:
        local_blocks = sorted(
            row_to_blocks.get(int(row_value), []),
            key=lambda block: (
                int(block.position[0]),
                int(block.position[2]),
                int(block.size[2]),
            ),
        )
        if not local_blocks:
            continue
        steps.append(
            {
                "row": int(row_value),
                "blocks": local_blocks,
            }
        )
    return steps


def build_consolidated_structural_block(
    x,
    y,
    z,
    height,
):
    record = STRUCTURAL_CATALOG_BY_HEIGHT[
        int(height)
    ]
    block = BlockInstance(
        position=(int(x), int(y), int(z)),
        size=tuple(
            int(value)
            for value in record[
                "column_world_size"
            ]
        ),
        base_color=record["color_rgb"],
        block_id=0,
        rotation=0,
        category="structural",
        block_family=record["block_family"],
    )
    block.catalog_record = dict(record)
    return block


def consolidate_segment_planning_result(
    planning_result,
    segment_id,
    segment_label,
    segment_mask=None,
    connector_face_requirements=None,
):
    """
    Safely test segment-local vertical consolidation.

    The original validated planner result remains authoritative unless a
    candidate changes the block-family/count composition and independently
    passes exact-coverage, locking-path, and receiving-face validation.
    Pure reorderings such as [2, 3] -> [3, 2] are never applied.
    """
    if not ENABLE_SEGMENT_LOCAL_CONSOLIDATION:
        return planning_result, {
            "enabled": False,
            "applied": False,
            "candidate_generated": False,
            "rolled_back": False,
            "reason": "disabled_by_task_context",
        }

    original_result = copy.deepcopy(
        planning_result
    )
    original_blocks = list(
        original_result["blocks"]
    )

    columns = defaultdict(list)
    for block in original_blocks:
        key = (
            int(block.position[0]),
            int(block.position[1]),
        )
        columns[key].append(block)

    candidate_blocks = []
    changed_columns = []
    rejected_reorder_columns = []
    unchanged_columns = 0

    for (x, y), column_blocks in sorted(
        columns.items(),
        key=lambda item: (
            item[0][1],
            item[0][0],
        ),
    ):
        ordered = sorted(
            column_blocks,
            key=lambda block: int(
                block.position[2]
            ),
        )
        z_start = int(
            ordered[0].position[2]
        )
        current_z = z_start
        contiguous = True
        old_sequence = []

        for block in ordered:
            if int(block.position[2]) != current_z:
                contiguous = False
                break
            height = int(block.size[2])
            old_sequence.append(height)
            current_z += height

        old_sequence = tuple(
            old_sequence
        )
        if not contiguous:
            candidate_blocks.extend(
                copy.deepcopy(ordered)
            )
            unchanged_columns += 1
            continue

        candidate_sequences = [
            tuple(
                int(value)
                for value in sequence
            )
            for sequence in (
                all_unique_sequences_for_height(
                    sum(old_sequence)
                )
            )
            if len(sequence) <= len(
                old_sequence
            )
        ]
        if not candidate_sequences:
            candidate_blocks.extend(
                copy.deepcopy(ordered)
            )
            unchanged_columns += 1
            continue

        best_sequence = min(
            candidate_sequences,
            key=consolidation_sequence_key,
        )

        old_multiset = tuple(
            sorted(old_sequence)
        )
        new_multiset = tuple(
            sorted(best_sequence)
        )

        pure_reorder = bool(
            old_multiset == new_multiset
            and old_sequence
            != best_sequence
        )
        block_count_reduced = bool(
            len(best_sequence)
            < len(old_sequence)
        )
        family_composition_changed = bool(
            old_multiset
            != new_multiset
        )
        larger_tie_improved = bool(
            len(best_sequence)
            == len(old_sequence)
            and family_composition_changed
            and larger_block_tie_break_key(
                best_sequence
            )
            < larger_block_tie_break_key(
                old_sequence
            )
        )
        meaningful_change = bool(
            block_count_reduced
            or larger_tie_improved
        )

        if pure_reorder:
            rejected_reorder_columns.append(
                {
                    "column_xy": [
                        int(x),
                        int(y),
                    ],
                    "old_sequence": list(
                        old_sequence
                    ),
                    "rejected_sequence": list(
                        best_sequence
                    ),
                    "reason": (
                        "same_family_multiset_"
                        "reordering_not_consolidation"
                    ),
                }
            )
            candidate_blocks.extend(
                copy.deepcopy(ordered)
            )
            unchanged_columns += 1
            continue

        if not meaningful_change:
            candidate_blocks.extend(
                copy.deepcopy(ordered)
            )
            unchanged_columns += 1
            continue

        changed_columns.append(
            {
                "column_xy": [
                    int(x),
                    int(y),
                ],
                "old_sequence": list(
                    old_sequence
                ),
                "new_sequence": list(
                    best_sequence
                ),
                "old_block_families": [
                    str(block.block_family)
                    for block in ordered
                ],
                "new_block_families": [
                    STRUCTURAL_CATALOG_BY_HEIGHT[
                        int(height)
                    ]["block_family"]
                    for height in best_sequence
                ],
                "block_count_reduced": (
                    block_count_reduced
                ),
                "larger_tie_improved": (
                    larger_tie_improved
                ),
            }
        )

        current_z = z_start
        for height in best_sequence:
            new_block = (
                build_consolidated_structural_block(
                    x,
                    y,
                    current_z,
                    int(height),
                )
            )
            candidate_blocks.append(
                new_block
            )
            current_z += int(height)

    before_counts = defaultdict(int)
    for block in original_blocks:
        before_counts[
            str(block.block_family)
        ] += 1

    candidate_counts = defaultdict(int)
    for block in candidate_blocks:
        candidate_counts[
            str(block.block_family)
        ] += 1

    base_audit = {
        "enabled": True,
        "mode": (
            "meaningful_family_change_"
            "then_full_revalidation"
        ),
        "segment_id": int(segment_id),
        "segment_label": str(
            segment_label
        ),
        "candidate_generated": bool(
            changed_columns
        ),
        "changed_column_count": int(
            len(changed_columns)
        ),
        "rejected_pure_reorder_count": int(
            len(rejected_reorder_columns)
        ),
        "unchanged_column_count": int(
            unchanged_columns
        ),
        "before_block_count": int(
            len(original_blocks)
        ),
        "candidate_block_count": int(
            len(candidate_blocks)
        ),
        "before_family_counts": {
            key: int(value)
            for key, value in (
                before_counts.items()
            )
        },
        "candidate_family_counts": {
            key: int(value)
            for key, value in (
                candidate_counts.items()
            )
        },
        "changed_columns": (
            changed_columns
        ),
        "rejected_reorder_columns": (
            rejected_reorder_columns
        ),
    }

    if not changed_columns:
        audit = {
            **base_audit,
            "applied": False,
            "rolled_back": False,
            "validation_passed": True,
            "reason": (
                "no_meaningful_consolidation_"
                "candidate"
            ),
            "after_block_count": int(
                len(original_blocks)
            ),
            "after_family_counts": {
                key: int(value)
                for key, value in (
                    before_counts.items()
                )
            },
        }
        original_result[
            "consolidation_audit"
        ] = audit
        return original_result, audit

    # Temporary local IDs are required for locking-path validation.
    for temporary_id, block in enumerate(
        candidate_blocks,
        start=1,
    ):
        block.block_id = int(
            temporary_id
        )

    candidate_result = copy.deepcopy(
        original_result
    )
    candidate_result["blocks"] = (
        candidate_blocks
    )
    candidate_result[
        "instruction_steps"
    ] = rebuild_instruction_steps_from_blocks(
        candidate_blocks,
        original_result.get(
            "row_values"
        ),
    )

    if isinstance(
        candidate_result.get(
            "best_state"
        ),
        dict,
    ):
        candidate_result[
            "best_state"
        ] = copy.deepcopy(
            candidate_result[
                "best_state"
            ]
        )
        candidate_result[
            "best_state"
        ]["blocks"] = candidate_blocks
        candidate_result[
            "best_state"
        ]["steps"] = candidate_result[
            "instruction_steps"
        ]

    coverage_exact = None
    if segment_mask is not None:
        covered = rasterize_blocks(
            candidate_blocks,
            segment_mask.shape,
        )
        coverage_exact = bool(
            np.array_equal(
                covered,
                segment_mask,
            )
        )

    candidate_validation = (
        validate_planned_instruction_steps(
            candidate_blocks,
            candidate_result[
                "instruction_steps"
            ],
            connector_face_requirements=(
                connector_face_requirements
            ),
        )
    )
    receiving_validation = (
        validate_connector_face_requirements_on_blocks(
            candidate_blocks,
            connector_face_requirements
            or [],
        )
    )

    validation_passed = bool(
        (
            True
            if coverage_exact is None
            else coverage_exact
        )
        and candidate_validation[
            "all_blocks_accepted"
        ]
        and receiving_validation[
            "valid"
        ]
    )

    if not validation_passed:
        rollback_reasons = []
        if coverage_exact is False:
            rollback_reasons.append(
                "coverage_not_exact"
            )
        if not candidate_validation[
            "all_blocks_accepted"
        ]:
            rollback_reasons.append(
                "locking_path_validation_failed"
            )
        if not receiving_validation[
            "valid"
        ]:
            rollback_reasons.append(
                "connector_receiving_faces_failed"
            )

        audit = {
            **base_audit,
            "applied": False,
            "rolled_back": True,
            "validation_passed": False,
            "candidate_exact_coverage": (
                coverage_exact
            ),
            "candidate_all_blocks_accepted": bool(
                candidate_validation[
                    "all_blocks_accepted"
                ]
            ),
            "candidate_receiving_faces_valid": bool(
                receiving_validation[
                    "valid"
                ]
            ),
            "rollback_reason": ",".join(
                rollback_reasons
            )
            or "candidate_validation_failed",
            "after_block_count": int(
                len(original_blocks)
            ),
            "after_family_counts": {
                key: int(value)
                for key, value in (
                    before_counts.items()
                )
            },
        }
        original_result[
            "consolidation_audit"
        ] = audit
        return original_result, audit

    audit = {
        **base_audit,
        "applied": True,
        "rolled_back": False,
        "validation_passed": True,
        "candidate_exact_coverage": (
            coverage_exact
        ),
        "candidate_all_blocks_accepted": True,
        "candidate_receiving_faces_valid": True,
        "after_block_count": int(
            len(candidate_blocks)
        ),
        "after_family_counts": {
            key: int(value)
            for key, value in (
                candidate_counts.items()
            )
        },
    }
    candidate_result[
        "consolidation_audit"
    ] = audit
    return candidate_result, audit



def plan_one_segment(
    segment_id,
    segment_label,
    segment_mask,
    next_block_id,
    connector_face_requirements=None,
    inventory_multiplier=1,
    inventory_scope=None,
):
    segment_id = int(
        segment_id
    )
    segment_label = str(
        segment_label
    )
    segment_directory = (
        OUTPUT_DIR
        / "segments"
        / f"segment_{segment_id:03d}"
    )
    segment_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not segment_mask.any():
        raise ValueError(
            f"Segment {segment_id} "
            "has no packable voxels."
        )

    build_axes = (
        candidate_segment_build_axes()
    )
    stop_after_first_valid = bool(
        TASK_CONTEXT.get(
            "segment_assembly",
            {},
        )
        .get(
            "segment_packing",
            {},
        )
        .get(
            "stop_after_first_valid_build_axis",
            True,
        )
    )

    axis_audit_rows = []
    valid_candidates = []

    for (
        axis_priority,
        build_axis,
    ) in enumerate(
        build_axes
    ):
        quarter_turns = (
            BUILD_AXIS_TO_QUARTER_TURNS[
                build_axis
            ]
        )
        axis_directory = (
            segment_directory
            / (
                "planner_"
                + build_axis_token(
                    build_axis
                )
            )
        )
        axis_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            plan_mask = np.rot90(
                segment_mask,
                k=quarter_turns,
                axes=(
                    0,
                    1,
                ),
            ).copy()
            if not exact_2x2_footprint_mask(
                plan_mask
            ):
                raise ValueError(
                    "The transformed segment has a "
                    "partial 2x2 footprint."
                )

            # Connector receiving faces are selected after structural
            # blocks exist. They do not constrain segment packing.
            plan_requirements = []
            columns = voxel_to_2x2_columns(
                plan_mask.astype(
                    int
                )
            )
            planning_result = (
                plan_rows_with_column_packing_and_rotation(
                    columns,
                    config=BETTER_PLANNER_CONFIG,
                    connector_face_requirements=(
                        plan_requirements
                    ),
                    segment_id=(
                        segment_id
                    ),
                    segment_label=(
                        segment_label
                    ),
                    diagnostic_output_dir=(
                        axis_directory
                    ),
                )
            )
            planning_result = (
                restore_planning_result_to_world(
                    planning_result,
                    segment_mask.shape,
                    quarter_turns,
                    build_axis,
                )
            )
            (
                planning_result,
                consolidation_audit,
            ) = (
                consolidate_segment_planning_result(
                    planning_result,
                    segment_id,
                    segment_label,
                    segment_mask=(
                        segment_mask
                    ),
                    connector_face_requirements=[],
                )
            )

            covered = rasterize_blocks(
                planning_result[
                    "blocks"
                ],
                segment_mask.shape,
            )
            exact_coverage = bool(
                np.array_equal(
                    covered,
                    segment_mask,
                )
            )
            validation = (
                validate_planned_instruction_steps(
                    planning_result[
                        "blocks"
                    ],
                    planning_result[
                        "instruction_steps"
                    ],
                    connector_face_requirements=[],
                )
            )
            receiving_face_validation = {
                "rows": [],
                "groups": [],
                "total": 0,
                "alternative_total": 0,
                "satisfied_count": 0,
                "satisfaction_ratio": 1.0,
                "valid": True,
                "deferred": True,
                "deferred_requirement_count": int(
                    len(
                        connector_face_requirements
                        or []
                    )
                ),
            }
            inventory_requirements, inventory_check = (
                inventory_check_blocks(
                    planning_result["blocks"],
                    multiplier=inventory_multiplier,
                )
            )
            valid = bool(
                exact_coverage
                and validation[
                    "all_blocks_accepted_and_supported"
                ]
                and inventory_check["feasible"]
            )

            axis_audit_rows.append(
                {
                    "segment_id": segment_id,
                    "segment_label": (
                        segment_label
                    ),
                    "build_axis": (
                        build_axis
                    ),
                    "axis_priority": int(
                        axis_priority
                    ),
                    "planner_completed": True,
                    "exact_coverage": bool(
                        exact_coverage
                    ),
                    "all_blocks_accepted": bool(
                        validation[
                            "all_blocks_accepted"
                        ]
                    ),
                    "final_locking_graph_connected": bool(
                        validation[
                            "final_locking_graph_connected"
                        ]
                    ),
                    "final_supported_graph_connected": bool(
                        validation[
                            "final_supported_graph_connected"
                        ]
                    ),
                    "receiving_faces_valid": bool(
                        receiving_face_validation[
                            "valid"
                        ]
                    ),
                    "valid": bool(
                        valid
                    ),
                    "inventory_feasible": bool(
                        inventory_check["feasible"]
                    ),
                    "inventory_multiplier": int(
                        inventory_multiplier
                    ),
                    "inventory_requirements": json.dumps(
                        inventory_requirements,
                        sort_keys=True,
                    ),
                    "inventory_shortages": json.dumps(
                        inventory_check["shortages"],
                        sort_keys=True,
                    ),
                    "block_count": int(
                        len(
                            planning_result[
                                "blocks"
                            ]
                        )
                    ),
                    "final_exposed_male_area": int(
                        planning_result.get(
                            "best_state",
                            {},
                        ).get(
                            "final_exposed_male_area",
                            0,
                        )
                    ),
                    "error": (
                        None
                        if inventory_check["feasible"]
                        else "inventory_shortage: "
                        + json.dumps(
                            inventory_check["shortages"],
                            sort_keys=True,
                        )
                    ),
                }
            )

            candidate = {
                "build_axis": (
                    build_axis
                ),
                "planning_result": (
                    planning_result
                ),
                "consolidation_audit": (
                    consolidation_audit
                ),
                "covered": covered,
                "exact_coverage": (
                    exact_coverage
                ),
                "validation": validation,
                "receiving_face_validation": (
                    receiving_face_validation
                ),
                "valid": valid,
                "axis_priority": (
                    axis_priority
                ),
                "inventory_requirements": (
                    inventory_requirements
                ),
                "inventory_check": (
                    inventory_check
                ),
                "inventory_multiplier": int(
                    inventory_multiplier
                ),
                "inventory_scope": (
                    inventory_scope
                    or f"segment:{segment_id}"
                ),
            }
            if valid:
                valid_candidates.append(
                    candidate
                )
                if stop_after_first_valid:
                    break

        except Exception as error:
            axis_audit_rows.append(
                {
                    "segment_id": segment_id,
                    "segment_label": (
                        segment_label
                    ),
                    "build_axis": (
                        build_axis
                    ),
                    "axis_priority": int(
                        axis_priority
                    ),
                    "planner_completed": False,
                    "exact_coverage": False,
                    "all_blocks_accepted": False,
                    "receiving_faces_valid": False,
                    "valid": False,
                    "block_count": 0,
                    "final_exposed_male_area": None,
                    "error": (
                        f"{type(error).__name__}: "
                        f"{error}"
                    ),
                }
            )

    axis_audit_df = pd.DataFrame(
        axis_audit_rows
    )
    axis_audit_path = (
        segment_directory
        / "segment_build_axis_audit.csv"
    )
    axis_audit_df.to_csv(
        axis_audit_path,
        index=False,
    )

    if not valid_candidates:
        failure_text = "; ".join(
            (
                f"{row['build_axis']}: "
                f"{row['error'] or 'mechanical_validation_failed'}"
            )
            for row in (
                axis_audit_rows
            )
        )
        raise RuntimeError(
            "No valid build axis was found "
            f"for segment {segment_id}. "
            f"See {axis_audit_path}. "
            f"Attempts: {failure_text}"
        )

    chosen = min(
        valid_candidates,
        key=lambda candidate: (
            segment_axis_candidate_sort_key(
                candidate,
                candidate[
                    "axis_priority"
                ],
            )
        ),
    )
    planning_result = (
        chosen[
            "planning_result"
        ]
    )
    (
        planning_result,
        next_block_id,
    ) = reindex_segment_plan(
        planning_result,
        next_block_id,
        segment_id,
        segment_label,
    )
    covered = chosen[
        "covered"
    ]
    validation = (
        remap_validation_block_ids_to_planning(
            chosen[
                "validation"
            ],
            planning_result,
        )
    )
    receiving_face_validation = (
        chosen[
            "receiving_face_validation"
        ]
    )
    selected_build_axis = str(
        chosen[
            "build_axis"
        ]
    )

    return {
        "segment_id": (
            segment_id
        ),
        "segment_label": (
            segment_label
        ),
        "selected_build_axis": (
            selected_build_axis
        ),
        "build_axis_audit_path": str(
            axis_audit_path
        ),
        "build_axis_audit": (
            axis_audit_rows
        ),
        "planning_result": (
            planning_result
        ),
        "validation": (
            validation
        ),
        "consolidation_audit": (
            chosen[
                "consolidation_audit"
            ]
        ),
        "exact_coverage": bool(
            chosen[
                "exact_coverage"
            ]
        ),
        "valid": True,
        "inventory_feasible": bool(
            chosen["inventory_check"]["feasible"]
        ),
        "inventory_requirements": dict(
            chosen["inventory_requirements"]
        ),
        "inventory_multiplier": int(
            chosen["inventory_multiplier"]
        ),
        "inventory_scope": str(
            chosen["inventory_scope"]
        ),
        "packable_voxels": int(
            segment_mask.sum()
        ),
        "covered_voxels": int(
            (
                covered
                & segment_mask
            ).sum()
        ),
        "extra_voxels": int(
            (
                covered
                & ~segment_mask
            ).sum()
        ),
        "missing_voxels": int(
            (
                segment_mask
                & ~covered
            ).sum()
        ),
        "connector_face_enforcement_stage": (
            "postbuild_connector_selection"
        ),
        "deferred_connector_face_requirement_count": int(
            len(
                connector_face_requirements
                or []
            )
        ),
        "connector_face_requirement_count": (
            receiving_face_validation[
                "total"
            ]
        ),
        "connector_face_requirement_alternative_count": (
            receiving_face_validation[
                "alternative_total"
            ]
        ),
        "connector_face_requirement_satisfied_count": (
            receiving_face_validation[
                "satisfied_count"
            ]
        ),
        "connector_face_requirement_satisfaction_ratio": (
            receiving_face_validation[
                "satisfaction_ratio"
            ]
        ),
        "connector_face_requirements_valid": (
            receiving_face_validation[
                "valid"
            ]
        ),
        "connector_face_requirement_audit": (
            receiving_face_validation[
                "rows"
            ]
        ),
    }, next_block_id


def contact_status_between_blocks(block_a, block_b):
    geometry = touching_face_geometry(block_a, block_b)
    if geometry is None:
        return None
    if geometry["geometry_status"] == "geometric_overlap_conflict":
        return {
            **geometry,
            "contact_status": "geometric_overlap_conflict",
        }
    face_type_a = actual_block_face_type(
        block_a,
        geometry["face_a"],
    )
    face_type_b = actual_block_face_type(
        block_b,
        geometry["face_b"],
    )
    return {
        **geometry,
        "face_type_a": face_type_a,
        "face_type_b": face_type_b,
        "contact_status": classify_face_types(
            face_type_a,
            face_type_b,
        ),
    }


def validate_connector_to_segments(
    connector,
    segment_blocks_by_id,
):
    if str(
        getattr(
            connector,
            "validation_mode",
            "",
        )
    ) == "embedded_anchor_layer":
        lock_area_a = int(
            getattr(
                connector,
                "postbuild_lock_area_segment_a",
                0,
            )
        )
        lock_area_b = int(
            getattr(
                connector,
                "postbuild_lock_area_segment_b",
                0,
            )
        )
        return {
            "interface_id": (
                connector.interface_id
            ),
            "connector_block_id": int(
                connector.block_id
            ),
            "segment_a": int(
                connector.segment_a
            ),
            "segment_b": int(
                connector.segment_b
            ),
            "locks_to_segment_a": bool(
                lock_area_a >= 4
            ),
            "locks_to_segment_b": bool(
                lock_area_b >= 4
            ),
            "lock_area_segment_a": (
                lock_area_a
            ),
            "lock_area_segment_b": (
                lock_area_b
            ),
            "valid": bool(
                lock_area_a >= 4
                and lock_area_b >= 4
            ),
        }

    result = {
        "interface_id": connector.interface_id,
        "connector_block_id": int(connector.block_id),
        "segment_a": int(connector.segment_a),
        "segment_b": int(connector.segment_b),
        "locks_to_segment_a": False,
        "locks_to_segment_b": False,
        "lock_area_segment_a": 0,
        "lock_area_segment_b": 0,
    }
    for side_name, segment_id in [
        ("segment_a", int(connector.segment_a)),
        ("segment_b", int(connector.segment_b)),
    ]:
        for block in segment_blocks_by_id.get(
            segment_id,
            [],
        ):
            contact = contact_status_between_blocks(
                connector,
                block,
            )
            if contact is None:
                continue
            if (
                contact[
                    "contact_status"
                ]
                == "male_to_female_lock"
            ):
                result[
                    f"locks_to_{side_name}"
                ] = True
                result[
                    f"lock_area_{side_name}"
                ] += int(
                    contact[
                        "overlap_area"
                    ]
                )
    result["valid"] = bool(
        result["locks_to_segment_a"]
        and result["locks_to_segment_b"]
    )
    return result

def postbuild_validate_connector_candidates(
    candidates_df,
    segment_blocks_by_id,
):
    rows = []

    for _, candidate_row in (
        candidates_df.iterrows()
    ):
        candidate = candidate_row.to_dict()
        temporary_block_id = (
            900000
            + int(
                candidate[
                    "candidate_id"
                ]
            )
        )
        connector = make_nonstructural_block(
            candidate,
            temporary_block_id,
            category=(
                "postbuild_connector_candidate"
            ),
        )
        lock_result = (
            validate_connector_to_segments(
                connector,
                segment_blocks_by_id,
            )
        )

        overlap_conflicts = []
        for segment_blocks in (
            segment_blocks_by_id.values()
        ):
            for block in segment_blocks:
                contact = (
                    contact_status_between_blocks(
                        connector,
                        block,
                    )
                )
                if (
                    contact is not None
                    and contact[
                        "contact_status"
                    ]
                    == "geometric_overlap_conflict"
                ):
                    overlap_conflicts.append(
                        int(
                            block.block_id
                        )
                    )

        rows.append(
            {
                **candidate,
                "postbuild_locks_to_segment_a": bool(
                    lock_result[
                        "locks_to_segment_a"
                    ]
                ),
                "postbuild_locks_to_segment_b": bool(
                    lock_result[
                        "locks_to_segment_b"
                    ]
                ),
                "postbuild_lock_area_segment_a": int(
                    lock_result[
                        "lock_area_segment_a"
                    ]
                ),
                "postbuild_lock_area_segment_b": int(
                    lock_result[
                        "lock_area_segment_b"
                    ]
                ),
                "postbuild_overlap_conflict_count": int(
                    len(
                        overlap_conflicts
                    )
                ),
                "postbuild_overlap_block_ids": ",".join(
                    str(
                        value
                    )
                    for value in sorted(
                        set(
                            overlap_conflicts
                        )
                    )
                ),
                "postbuild_valid": bool(
                    lock_result[
                        "locks_to_segment_a"
                    ]
                    and lock_result[
                        "locks_to_segment_b"
                    ]
                    and not overlap_conflicts
                ),
            }
        )

    return pd.DataFrame(
        rows
    )

FACE_TO_AXIS_SIGN = {
    "+X": (
        0,
        1,
    ),
    "-X": (
        0,
        -1,
    ),
    "+Y": (
        1,
        1,
    ),
    "-Y": (
        1,
        -1,
    ),
    "+Z": (
        2,
        1,
    ),
    "-Z": (
        2,
        -1,
    ),
}


def interface_patch_options(
    interface_payload,
    normal_a_to_b,
):
    axis, sign = (
        FACE_TO_AXIS_SIGN[
            str(
                normal_a_to_b
            )
        ]
    )
    perpendicular_axes = [
        index
        for index in range(
            3
        )
        if index != axis
    ]
    vector = [
        0,
        0,
        0,
    ]
    vector[
        axis
    ] = int(
        sign
    )

    a_set = {
        tuple(
            int(
                value
            )
            for value in coordinate
        )
        for coordinate in interface_payload.get(
            "a_coordinates",
            [],
        )
    }
    b_set = {
        tuple(
            int(
                value
            )
            for value in coordinate
        )
        for coordinate in interface_payload.get(
            "b_coordinates",
            [],
        )
    }

    options = []
    for coordinate in sorted(
        a_set
    ):
        base = list(
            coordinate
        )
        cells_a = []
        for first_offset in (
            0,
            1,
        ):
            for second_offset in (
                0,
                1,
            ):
                candidate = list(
                    base
                )
                candidate[
                    perpendicular_axes[
                        0
                    ]
                ] += first_offset
                candidate[
                    perpendicular_axes[
                        1
                    ]
                ] += second_offset
                cells_a.append(
                    tuple(
                        candidate
                    )
                )

        if not set(
            cells_a
        ) <= a_set:
            continue

        cells_b = [
            tuple(
                cell[
                    index
                ]
                + vector[
                    index
                ]
                for index in range(
                    3
                )
            )
            for cell in cells_a
        ]
        if not set(
            cells_b
        ) <= b_set:
            continue

        geometry = sorted(
            set(
                cells_a
            )
            | set(
                cells_b
            )
        )
        origin = tuple(
            min(
                point[
                    index
                ]
                for point in geometry
            )
            for index in range(
                3
            )
        )
        size = tuple(
            max(
                point[
                    index
                ]
                for point in geometry
            )
            - origin[
                index
            ]
            + 1
            for index in range(
                3
            )
        )
        if tuple(
            size
        ) != (
            2,
            2,
            2,
        ):
            continue

        options.append(
            {
                "origin": (
                    origin
                ),
                "size": (
                    size
                ),
                "geometry_coordinates": (
                    geometry
                ),
                "anchor_cells_a": sorted(
                    cells_a
                ),
                "anchor_cells_b": sorted(
                    cells_b
                ),
            }
        )

    options.sort(
        key=lambda row: (
            row[
                "origin"
            ],
        )
    )
    return options


def connector_record_for_interface(
    interface_id,
    interface_catalog_queries,
):
    query = (
        interface_catalog_queries.get(
            str(
                interface_id
            ),
            {
                "all": [
                    {
                        "field": (
                            "current_solver_enabled"
                        ),
                        "op": "truthy",
                    },
                    {
                        "field": (
                            "functional_role"
                        ),
                        "op": "equals",
                        "value": (
                            "connector"
                        ),
                    },
                ]
            },
        )
    )
    raw_records = select_catalog_records(
        query
    )
    records = [
        prepare_general_catalog_record(
            record
        )
        for record in raw_records
    ]

    exact_records = [
        record
        for record in records
        if tuple(
            int(
                value
            )
            for value in record.get(
                "native_size",
                (),
            )
        )
        == (
            2,
            2,
            2,
        )
    ]

    if exact_records:
        return (
            exact_records[
                0
            ],
            query,
        )
    if records:
        return (
            records[
                0
            ],
            query,
        )

    raise RuntimeError(
        "No enabled catalog connector record "
        f"matched interface {interface_id}."
    )


def generate_required_embedded_connector_candidates(
    required_interfaces_df,
    interface_payload_by_id,
    interface_catalog_queries,
):
    rows = []
    occupied = set()

    for candidate_id, interface_row in enumerate(
        required_interfaces_df.sort_values(
            [
                "interface_id"
            ]
        ).itertuples(
            index=False
        ),
        start=1,
    ):
        interface_id = str(
            interface_row.interface_id
        )
        payload = (
            interface_payload_by_id[
                interface_id
            ]
        )
        options = interface_patch_options(
            payload,
            interface_row.normal_a_to_b,
        )
        if not options:
            raise RuntimeError(
                "No 2x2 embedded anchor patch "
                f"was found for {interface_id}."
            )

        nonoverlapping_options = [
            option
            for option in options
            if not (
                set(
                    option[
                        "geometry_coordinates"
                    ]
                )
                & occupied
            )
        ]
        chosen = (
            nonoverlapping_options[
                0
            ]
            if nonoverlapping_options
            else options[
                0
            ]
        )
        occupied.update(
            chosen[
                "geometry_coordinates"
            ]
        )

        record, query = (
            connector_record_for_interface(
                interface_id,
                interface_catalog_queries,
            )
        )
        axis, _ = FACE_TO_AXIS_SIGN[
            str(
                interface_row.normal_a_to_b
            )
        ]
        axis_letter = [
            "X",
            "Y",
            "Z",
        ][
            axis
        ]
        face_roles = {
            face: "female"
            for face in (
                "+X",
                "-X",
                "+Y",
                "-Y",
                "+Z",
                "-Z",
            )
        }
        face_roles[
            f"+{axis_letter}"
        ] = "male"
        face_roles[
            f"-{axis_letter}"
        ] = "male"

        rows.append(
            {
                "candidate_id": int(
                    candidate_id
                ),
                "interface_id": (
                    interface_id
                ),
                "segment_a": int(
                    interface_row.segment_a
                ),
                "segment_b": int(
                    interface_row.segment_b
                ),
                "block_role": (
                    "structural_segment_connector"
                ),
                "block_family": str(
                    record[
                        "block_family"
                    ]
                ),
                "catalog_record": (
                    record
                ),
                "catalog_query": (
                    query
                ),
                "catalog_query_source": (
                    "llm2_required_interface_"
                    "embedded_anchor"
                ),
                "origin": tuple(
                    int(
                        value
                    )
                    for value in (
                        chosen[
                            "origin"
                        ]
                    )
                ),
                "size": (
                    2,
                    2,
                    2,
                ),
                "face_roles": (
                    face_roles
                ),
                "rotation_matrix": [
                    [
                        1,
                        0,
                        0,
                    ],
                    [
                        0,
                        1,
                        0,
                    ],
                    [
                        0,
                        0,
                        1,
                    ],
                ],
                "normal_a_to_b": str(
                    interface_row.normal_a_to_b
                ),
                "geometry_coordinates": (
                    chosen[
                        "geometry_coordinates"
                    ]
                ),
                "embedded_anchor_cells_a": (
                    chosen[
                        "anchor_cells_a"
                    ]
                ),
                "embedded_anchor_cells_b": (
                    chosen[
                        "anchor_cells_b"
                    ]
                ),
                "overlap_a": int(
                    len(
                        chosen[
                            "anchor_cells_a"
                        ]
                    )
                ),
                "overlap_b": int(
                    len(
                        chosen[
                            "anchor_cells_b"
                        ]
                    )
                ),
                "unrelated_overlap": 0,
                "validation_mode": (
                    "embedded_anchor_layer"
                ),
                "score": int(
                    100000
                    + int(
                        interface_row.contact_area
                    )
                ),
            }
        )

    return pd.DataFrame(
        rows
    )


def embedded_connector_candidate_validation(
    candidate,
    segment_blocks_by_id,
):
    cells_a = {
        tuple(
            int(
                value
            )
            for value in coordinate
        )
        for coordinate in candidate.get(
            "embedded_anchor_cells_a",
            [],
        )
    }
    cells_b = {
        tuple(
            int(
                value
            )
            for value in coordinate
        )
        for coordinate in candidate.get(
            "embedded_anchor_cells_b",
            [],
        )
    }
    segment_a = int(
        candidate[
            "segment_a"
        ]
    )
    segment_b = int(
        candidate[
            "segment_b"
        ]
    )

    covered_a = {
        coordinate
        for coordinate in cells_a
        if any(
            block_contains_voxel(
                block,
                coordinate,
            )
            for block in (
                segment_blocks_by_id.get(
                    segment_a,
                    [],
                )
            )
        )
    }
    covered_b = {
        coordinate
        for coordinate in cells_b
        if any(
            block_contains_voxel(
                block,
                coordinate,
            )
            for block in (
                segment_blocks_by_id.get(
                    segment_b,
                    [],
                )
            )
        )
    }

    valid = bool(
        len(
            cells_a
        )
        == 4
        and len(
            cells_b
        )
        == 4
        and covered_a
        == cells_a
        and covered_b
        == cells_b
        and int(
            candidate.get(
                "unrelated_overlap",
                0,
            )
        )
        == 0
    )
    return {
        **candidate,
        "postbuild_locks_to_segment_a": bool(
            valid
        ),
        "postbuild_locks_to_segment_b": bool(
            valid
        ),
        "postbuild_lock_area_segment_a": int(
            len(
                covered_a
            )
        ),
        "postbuild_lock_area_segment_b": int(
            len(
                covered_b
            )
        ),
        "postbuild_overlap_conflict_count": 0,
        "postbuild_overlap_block_ids": "",
        "postbuild_validation_mode": (
            "embedded_anchor_layer"
        ),
        "postbuild_valid": bool(
            valid
        ),
    }


def validate_required_embedded_connectors(
    candidates_df,
    segment_blocks_by_id,
):
    return pd.DataFrame(
        [
            embedded_connector_candidate_validation(
                row.to_dict(),
                segment_blocks_by_id,
            )
            for _, row in (
                candidates_df.iterrows()
            )
        ]
    )


def intended_embedded_anchor_overlap(
    block_a,
    block_b,
):
    for connector, structural in (
        (
            block_a,
            block_b,
        ),
        (
            block_b,
            block_a,
        ),
    ):
        if str(
            getattr(
                connector,
                "validation_mode",
                "",
            )
        ) != "embedded_anchor_layer":
            continue
        structural_segment_id = getattr(
            structural,
            "source_segment_id",
            None,
        )
        if structural_segment_id is None:
            continue
        if int(
            structural_segment_id
        ) in {
            int(
                connector.segment_a
            ),
            int(
                connector.segment_b
            ),
        }:
            return True
    return False




def validate_functional_block(
    block,
    segment_blocks_by_id,
):
    anchor_id = int(
        block.anchor_segment_id
    )
    source_overlap = int(
        getattr(
            block,
            "source_overlap_voxels",
            0,
        )
    )
    anchor_contact = int(
        getattr(
            block,
            "anchor_contact_area",
            0,
        )
    )
    if (
        source_overlap > 0
        and anchor_contact > 0
    ):
        return {
            "physical_target_id": (
                block.physical_target_id
            ),
            "functional_block_id": int(
                block.block_id
            ),
            "anchor_segment_id": (
                anchor_id
            ),
            "lock_area": int(
                anchor_contact
            ),
            "valid": True,
        }

    lock_area = 0
    for structural_block in (
        segment_blocks_by_id.get(
            anchor_id,
            [],
        )
    ):
        contact = (
            contact_status_between_blocks(
                block,
                structural_block,
            )
        )
        if (
            contact is not None
            and contact[
                "contact_status"
            ]
            == "male_to_female_lock"
        ):
            lock_area += int(
                contact[
                    "overlap_area"
                ]
            )
    return {
        "physical_target_id": (
            block.physical_target_id
        ),
        "functional_block_id": int(
            block.block_id
        ),
        "anchor_segment_id": (
            anchor_id
        ),
        "lock_area": int(
            lock_area
        ),
        "valid": bool(
            lock_area > 0
        ),
    }


def connected_segment_graph(
    structural_segment_ids,
    valid_connector_rows,
):
    adjacency = {
        int(segment_id): set()
        for segment_id in structural_segment_ids
    }
    for row in valid_connector_rows:
        if not row["valid"]:
            continue
        segment_a = int(row["segment_a"])
        segment_b = int(row["segment_b"])
        adjacency[segment_a].add(segment_b)
        adjacency[segment_b].add(segment_a)

    if not adjacency:
        return True, []
    start = next(iter(adjacency))
    visited = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for neighbor in adjacency[current]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return visited == set(adjacency), sorted(visited)


def rotation_candidate_requires_symmetry_centering(row):
    explicit = row.get("center_on_symmetry_axis")
    if explicit not in {None, "", "nan"}:
        return bool(explicit)

    declaration = functional_attachment_declaration(
        row.get("attachment_id")
    )
    if "center_on_symmetry_axis" in declaration:
        return bool(declaration.get("center_on_symmetry_axis"))

    target_id = str(row.get("physical_target_id", ""))
    config = custom_functional_subassembly_config_for_target(target_id)
    if config:
        validation = config.get("validation", {}) or {}
        return bool(validation.get("require_centered_on_symmetry_axis", False))

    return False

def center_selected_rotation_candidates(
    selected_functional_df,
):
    if selected_functional_df.empty:
        return (
            selected_functional_df.copy(),
            pd.DataFrame(),
        )

    centered = selected_functional_df.copy()
    audit_rows = []

    for row_index, row in centered.iterrows():
        connection_type = str(
            row.get(
                "llm2_connection_type",
                "",
            )
        ).lower()
        family = str(
            row.get(
                "block_family",
                "",
            )
        )
        if (
            connection_type != "rotation"
            and family != "rotation_block"
        ):
            continue

        if not rotation_candidate_requires_symmetry_centering(row):
            audit_rows.append({
                "physical_target_id": str(row.get("physical_target_id", "")),
                "block_family": family,
                "original_origin": tuple(int(value) for value in row["origin"]),
                "centered_origin": tuple(int(value) for value in row["origin"]),
                "symmetry_axis_index": int(SYMMETRY_AXIS_INDEX),
                "symmetry_center_plane": float(SYMMETRY_CENTER_PLANE),
                "source_overlap_voxels": int(row.get("source_overlap_voxels", 0)),
                "source_overlap_ratio": float(row.get("source_overlap_ratio", 0.0)),
                "anchor_contact_area": int(row.get("anchor_contact_area", 0)),
                "unrelated_overlap": int(row.get("unrelated_overlap", 0)),
                "centering_required": False,
                "centering_status": "not_requested_by_task_context",
                "valid": True,
            })
            continue

        size = tuple(
            int(value)
            for value in row["size"]
        )
        original_origin = tuple(
            int(value)
            for value in row["origin"]
        )
        centered_origin = list(
            original_origin
        )
        centered_origin[
            SYMMETRY_AXIS_INDEX
        ] = int(
            round(
                float(
                    SYMMETRY_CENTER_PLANE
                )
                - size[
                    SYMMETRY_AXIS_INDEX
                ]
                / 2.0
            )
        )
        centered_origin[
            SYMMETRY_AXIS_INDEX
        ] = max(
            0,
            min(
                centered_origin[
                    SYMMETRY_AXIS_INDEX
                ],
                int(
                    segment_grid_planner.shape[
                        SYMMETRY_AXIS_INDEX
                    ]
                    - size[
                        SYMMETRY_AXIS_INDEX
                    ]
                ),
            ),
        )
        centered_origin = tuple(
            int(value)
            for value in centered_origin
        )

        geometry = box_mask(
            segment_grid_planner.shape,
            centered_origin,
            size,
        )
        if geometry is None:
            raise RuntimeError(
                "Centered rotation block is outside the planning grid."
            )

        source_segment_ids = [
            int(value)
            for value in row.get(
                "source_segment_ids",
                [],
            )
        ]
        target_mask = np.isin(
            segment_grid_planner,
            source_segment_ids,
        )
        anchor_segment_id = int(
            row[
                "anchor_segment_id"
            ]
        )
        anchor_mask = (
            segment_grid_planner
            == anchor_segment_id
        )
        other_mask = (
            (
                segment_grid_planner
                > 0
            )
            & ~target_mask
            & ~anchor_mask
        )

        target_voxels = max(
            1,
            int(
                target_mask.sum()
            ),
        )
        source_overlap = int(
            (
                geometry
                & target_mask
            ).sum()
        )
        source_overlap_ratio = (
            source_overlap
            / target_voxels
        )
        anchor_overlap = int(
            (
                geometry
                & anchor_mask
            ).sum()
        )
        unrelated_overlap = int(
            (
                geometry
                & other_mask
            ).sum()
        )
        anchor_contact_area = int(
            boundary_contact_area(
                geometry,
                anchor_mask,
            )
        )

        valid = bool(
            source_overlap > 0
            and anchor_overlap == 0
            and unrelated_overlap == 0
            and anchor_contact_area > 0
        )
        if not valid:
            raise RuntimeError(
                "The required rotation attachment cannot be centered "
                "without losing target overlap or anchor contact."
            )

        empty_volume = int(
            geometry.sum()
            - source_overlap
        )
        score = (
            int(
                round(
                    source_overlap_ratio
                    * 10000
                )
            )
            + anchor_contact_area
            * 100
            - empty_volume
        )

        centered.at[
            row_index,
            "origin",
        ] = centered_origin
        centered.at[
            row_index,
            "geometry_coordinates",
        ] = box_coordinates(
            centered_origin,
            size,
        )
        centered.at[
            row_index,
            "source_overlap_voxels",
        ] = source_overlap
        centered.at[
            row_index,
            "source_overlap_ratio",
        ] = source_overlap_ratio
        centered.at[
            row_index,
            "anchor_contact_area",
        ] = anchor_contact_area
        centered.at[
            row_index,
            "score",
        ] = score
        centered.at[
            row_index,
            "centered_on_symmetry_axis",
        ] = True

        audit_rows.append(
            {
                "physical_target_id": str(
                    row.get(
                        "physical_target_id"
                    )
                ),
                "block_family": family,
                "original_origin": original_origin,
                "centered_origin": centered_origin,
                "symmetry_axis_index": int(
                    SYMMETRY_AXIS_INDEX
                ),
                "symmetry_center_plane": float(
                    SYMMETRY_CENTER_PLANE
                ),
                "source_overlap_voxels": int(
                    source_overlap
                ),
                "source_overlap_ratio": float(
                    source_overlap_ratio
                ),
                "anchor_contact_area": int(
                    anchor_contact_area
                ),
                "unrelated_overlap": int(
                    unrelated_overlap
                ),
                "centering_required": True,
                "centering_status": "centered_and_valid",
                "valid": bool(
                    valid
                ),
            }
        )

    return (
        centered,
        pd.DataFrame(
            audit_rows
        ),
    )


def direct_structural_join_tree(
    direct_contact_df,
    structural_segment_ids,
):
    output_columns = [
        "interface_id",
        "connector_block_id",
        "segment_a",
        "segment_b",
        "locks_to_segment_a",
        "locks_to_segment_b",
        "lock_area_segment_a",
        "lock_area_segment_b",
        "contact_count",
        "join_mode",
        "valid",
    ]

    if direct_contact_df.empty:
        return (
            pd.DataFrame(
                columns=output_columns
            ),
            pd.DataFrame(),
        )

    lock_rows = direct_contact_df.loc[
        direct_contact_df[
            "contact_status"
        ].eq(
            "male_to_female_lock"
        )
    ].copy()

    grouped = {}
    for row in lock_rows.itertuples(
        index=False
    ):
        first, second = sorted(
            (
                int(
                    row.segment_a
                ),
                int(
                    row.segment_b
                ),
            )
        )
        entry = grouped.setdefault(
            (
                first,
                second,
            ),
            {
                "segment_a": first,
                "segment_b": second,
                "contact_count": 0,
                "lock_area": 0,
            },
        )
        entry[
            "contact_count"
        ] += 1
        entry[
            "lock_area"
        ] += int(
            row.overlap_area
        )

    candidate_rows = sorted(
        grouped.values(),
        key=lambda row: (
            -int(
                row[
                    "lock_area"
                ]
            ),
            int(
                row[
                    "segment_a"
                ]
            ),
            int(
                row[
                    "segment_b"
                ]
            ),
        ),
    )

    parent = {
        int(segment_id): int(segment_id)
        for segment_id in structural_segment_ids
    }

    def find(value):
        value = int(value)
        while parent[value] != value:
            parent[value] = parent[
                parent[value]
            ]
            value = parent[value]
        return value

    def union(first, second):
        root_first = find(first)
        root_second = find(second)
        if root_first == root_second:
            return False
        parent[root_second] = root_first
        return True

    selected_rows = []
    audit_rows = []

    for candidate in candidate_rows:
        selected = union(
            candidate[
                "segment_a"
            ],
            candidate[
                "segment_b"
            ],
        )
        audit_rows.append(
            {
                **candidate,
                "selected_for_join_tree": bool(
                    selected
                ),
            }
        )
        if not selected:
            continue

        selected_rows.append(
            {
                "interface_id": (
                    f"DJ_"
                    f"{int(candidate['segment_a']):03d}_"
                    f"{int(candidate['segment_b']):03d}"
                ),
                "connector_block_id": None,
                "segment_a": int(
                    candidate[
                        "segment_a"
                    ]
                ),
                "segment_b": int(
                    candidate[
                        "segment_b"
                    ]
                ),
                "locks_to_segment_a": True,
                "locks_to_segment_b": True,
                "lock_area_segment_a": int(
                    candidate[
                        "lock_area"
                    ]
                ),
                "lock_area_segment_b": int(
                    candidate[
                        "lock_area"
                    ]
                ),
                "contact_count": int(
                    candidate[
                        "contact_count"
                    ]
                ),
                "join_mode": (
                    "direct_structural_lock"
                ),
                "valid": True,
            }
        )

    return (
        pd.DataFrame(
            selected_rows,
            columns=output_columns,
        ),
        pd.DataFrame(
            audit_rows
        ),
    )


def block_family_count_dataframe(
    blocks,
):
    rows = [
        {
            "block_family": str(
                block.block_family
            ),
            "block_role": str(
                getattr(
                    block,
                    "block_role",
                    getattr(
                        block,
                        "category",
                        "unknown",
                    ),
                )
            ),
        }
        for block in blocks
    ]
    if not rows:
        return pd.DataFrame(
            columns=[
                "block_family",
                "count",
                "block_roles",
            ]
        )

    dataframe = pd.DataFrame(
        rows
    )
    count_rows = []
    for family, group in dataframe.groupby(
        "block_family",
        sort=True,
    ):
        count_rows.append(
            {
                "block_family": str(
                    family
                ),
                "count": int(
                    len(
                        group
                    )
                ),
                "block_roles": ", ".join(
                    sorted(
                        set(
                            group[
                                "block_role"
                            ].astype(
                                str
                            )
                        )
                    )
                ),
            }
        )

    return pd.DataFrame(
        count_rows
    ).sort_values(
        "block_family"
    ).reset_index(
        drop=True
    )




def functional_attachment_declaration(attachment_id):
    attachment_id = str(attachment_id or "")
    for declaration in TASK_CONTEXT.get("functional_attachments", []):
        if str(declaration.get("attachment_id", "")) == attachment_id:
            return declaration
    return {}


def required_family_for_attachment(attachment_id):
    return str(
        functional_attachment_declaration(attachment_id).get(
            "required_block_family",
            "",
        )
    ).strip()


def custom_functional_subassembly_configs():
    return list(CUSTOM_FUNCTIONAL_SUBASSEMBLY_CONFIGS)


def custom_functional_subassembly_config_for_target(physical_target_id):
    return CUSTOM_FUNCTIONAL_SUBASSEMBLIES_BY_TARGET.get(
        str(physical_target_id or ""),
        {},
    )


def custom_functional_subassembly_enabled(physical_target_id=None):
    if physical_target_id is None:
        return bool(CUSTOM_FUNCTIONAL_SUBASSEMBLY_CONFIGS)
    return bool(custom_functional_subassembly_config_for_target(physical_target_id))


def catalog_record_for_query(
    query,
    *,
    preferred_size=None,
):
    records = [
        prepare_general_catalog_record(record)
        for record in select_catalog_records(query)
    ]
    if preferred_size is not None:
        preferred_size = tuple(int(value) for value in preferred_size)
        exact = [
            record
            for record in records
            if tuple(int(value) for value in record.get("native_size", ()))
            == preferred_size
        ]
        if exact:
            return exact[0]
    if records:
        return records[0]
    raise RuntimeError(
        "No enabled catalog record matched the custom functional subassembly query."
    )


def _axis_index_from_name(value):
    token = str(value or "Z").strip().upper().replace("+", "").replace("-", "")
    return {"X": 0, "Y": 1, "Z": 2}.get(token, 2)


def _default_connector_face_roles(axis="Y"):
    axis = str(axis or "Y").strip().upper().replace("+", "").replace("-", "")
    roles = {
        "+X": "female", "-X": "female",
        "+Y": "female", "-Y": "female",
        "+Z": "female", "-Z": "female",
    }
    roles[f"+{axis}"] = "male"
    roles[f"-{axis}"] = "male"
    return roles


def _custom_subassembly_member_templates(config):
    members = config.get("members", {}) or {}
    templates = list(members.get("member_templates", []) or [])
    if templates:
        return templates
    count = int(members.get("count", 0) or 0)
    if count <= 0:
        return []
    center = (count - 1) / 2.0
    return [
        {
            "member_role": f"member_{index + 1}",
            "offset_index": index - center,
            "face_roles": {},
        }
        for index in range(count)
    ]


def create_motion_connected_structural_subassembly(
    config,
    selected_connector_candidate,
    next_block_id,
):
    if not config or not bool(config.get("enabled", True)):
        raise RuntimeError(
            "No enabled motion-connected structural subassembly configuration was provided."
        )
    physical_target_id = str(
        config.get("physical_target_id", config.get("assembly_id", "functional_subassembly"))
    )
    group_name = str(
        config.get("display_name", physical_target_id.replace("_", " ").title())
    )
    source_segment_ids = [int(value) for value in config.get("source_segment_ids", [])]
    anchor_segment_id = int(config.get("anchor_segment_id", -1))
    connector_config = config.get("connector", {}) or {}
    members_config = config.get("members", {}) or {}
    templates = _custom_subassembly_member_templates(config)
    expected_count = int(members_config.get("count", len(templates)) or len(templates))
    if not templates or len(templates) != expected_count:
        raise RuntimeError(
            f"Functional subassembly {physical_target_id!r} requires {expected_count} "
            f"member templates; received {len(templates)}."
        )

    anchor_coordinates = np.argwhere(segment_grid_planner == anchor_segment_id)
    if len(anchor_coordinates) == 0:
        raise RuntimeError(
            f"Anchor segment {anchor_segment_id} for {group_name!r} is missing from the planning grid."
        )

    placement_policy = str(
        connector_config.get(
            "placement_policy",
            config.get("placement_policy", "outside_anchor_face_centered_on_symmetry_plane"),
        )
    ).strip().lower()
    if placement_policy == "outside_front_face_centered_on_symmetry_plane":
        placement_policy = "outside_anchor_face_centered_on_symmetry_plane"
    if placement_policy != "outside_anchor_face_centered_on_symmetry_plane":
        raise NotImplementedError(
            f"Unsupported custom subassembly placement policy: {placement_policy!r}."
        )

    anchor_face = str(connector_config.get("anchor_face", "-Y")).strip().upper()
    if anchor_face not in {"-Y", "+Y"}:
        raise NotImplementedError(
            "The current row/column engine supports outside-anchor placement on ±Y faces."
        )
    face_coordinate = (
        int(anchor_coordinates[:, 1].min())
        if anchor_face == "-Y"
        else int(anchor_coordinates[:, 1].max()) + 1
    )
    face_coordinates = anchor_coordinates[
        anchor_coordinates[:, 1]
        == (face_coordinate if anchor_face == "-Y" else face_coordinate - 1)
    ]
    z_center = float((face_coordinates[:, 2].min() + face_coordinates[:, 2].max() + 1) / 2.0)

    raw_candidate = dict(selected_connector_candidate)
    candidate_size = tuple(int(value) for value in raw_candidate.get("size", (2, 2, 2)))
    if len(candidate_size) != 3:
        candidate_size = (2, 2, 2)
    x_origin = int(round(float(SYMMETRY_CENTER_PLANE) - candidate_size[0] / 2.0))
    z_origin = int(round(z_center - candidate_size[2] / 2.0))
    z_origin = max(int(config.get("minimum_z_origin", 2)), z_origin)
    direction = -1 if anchor_face == "-Y" else 1
    connector_y = face_coordinate - candidate_size[1] if direction < 0 else face_coordinate
    connector_origin = (x_origin, connector_y, z_origin)

    raw_member_size = members_config.get("member_size")
    structural_query = members_config.get("catalog_query", {})
    structural_record = catalog_record_for_query(
        structural_query,
        preferred_size=tuple(raw_member_size) if raw_member_size else (2, 2, 2),
    )
    member_size = tuple(
        int(value) for value in (
            raw_member_size or structural_record.get("native_size", (2, 2, 2))
        )
    )
    member_plane_y = connector_y + direction * member_size[1]

    rotation_candidate = {
        **raw_candidate,
        "physical_target_id": physical_target_id,
        "source_segment_ids": source_segment_ids,
        "anchor_segment_id": anchor_segment_id,
        "block_role": "functional_motion_connector",
        "origin": connector_origin,
        "size": candidate_size,
        "face_roles": connector_config.get(
            "face_roles", _default_connector_face_roles(connector_config.get("axis", "Y"))
        ),
        "validation_mode": "motion_subassembly_connector",
        "source_overlap_voxels": 0,
        "source_overlap_ratio": 0.0,
        "anchor_contact_area": int(candidate_size[0] * candidate_size[2]),
        "centered_on_symmetry_axis": True,
    }
    connector_block = make_nonstructural_block(
        rotation_candidate,
        next_block_id,
        category="functional_connector",
    )
    next_block_id += 1
    connector_block.segment_name = f"{group_name} Connector"
    connector_block.segment_display_name = f"{group_name} Connector"
    connector_block.segment_label = str(connector_config.get("semantic_label", "motion_connector"))
    connector_block.source_segment_ids = source_segment_ids
    connector_block.connected_group_name = group_name
    connector_block.connected_group_id = physical_target_id

    layout_axis = _axis_index_from_name(members_config.get("layout_axis", "Z"))
    member_blocks = []
    for member_index, template in enumerate(templates, start=1):
        offset_index = float(template.get("offset_index", member_index - 1))
        origin = [x_origin, member_plane_y, z_origin]
        origin[layout_axis] += int(round(offset_index * member_size[layout_axis]))
        candidate = {
            "catalog_record": structural_record,
            "block_family": str(structural_record["block_family"]),
            "origin": tuple(origin),
            "size": member_size,
            "face_roles": template.get("face_roles", {}),
            "block_role": "functional_subassembly_structural",
            "physical_target_id": physical_target_id,
            "anchor_segment_id": anchor_segment_id,
            "validation_mode": "functional_subassembly_member",
        }
        block = make_nonstructural_block(
            candidate,
            next_block_id,
            category="functional_subassembly",
        )
        next_block_id += 1
        block.segment_name = group_name
        block.segment_display_name = group_name
        block.segment_label = str(config.get("semantic_label", "functional_subassembly"))
        block.source_segment_ids = source_segment_ids
        block.subassembly_member_role = str(template.get("member_role", f"member_{member_index}"))
        block.subassembly_member_index = member_index
        block.subassembly_offset_index = offset_index
        member_blocks.append(block)

    audit = {
        "assembly_id": physical_target_id,
        "assembly_type": str(config.get("assembly_type", "motion_connected_structural_subassembly")),
        "display_name": group_name,
        "source_segment_ids": source_segment_ids,
        "anchor_segment_id": anchor_segment_id,
        "connector_block_id": int(connector_block.block_id),
        "connector_origin": tuple(int(value) for value in connector_block.position),
        "member_block_ids": [int(block.block_id) for block in member_blocks],
        "member_block_origins": [tuple(int(value) for value in block.position) for block in member_blocks],
        "centered_on_symmetry_axis": bool(
            abs((connector_block.position[0] + connector_block.size[0] / 2.0) - float(SYMMETRY_CENTER_PLANE)) < 1e-9
        ),
    }
    return connector_block, member_blocks, audit, next_block_id


def validate_motion_connected_structural_subassembly(
    config,
    connector_block,
    member_blocks,
    segment_blocks_by_id,
):
    anchor_segment_id = int(config.get("anchor_segment_id", -1))
    physical_target_id = str(config.get("physical_target_id", config.get("assembly_id", "")))
    members_config = config.get("members", {}) or {}
    expected_count = int(members_config.get("count", len(member_blocks)) or len(member_blocks))

    anchor_lock_area = 0
    for structural_block in segment_blocks_by_id.get(anchor_segment_id, []):
        contact = contact_status_between_blocks(connector_block, structural_block)
        if contact and contact.get("contact_status") == "male_to_female_lock":
            anchor_lock_area += int(contact.get("overlap_area", 0))

    ordered = sorted(
        member_blocks,
        key=lambda block: float(getattr(block, "subassembly_offset_index", 0)),
    )
    center = min(
        ordered,
        key=lambda block: abs(float(getattr(block, "subassembly_offset_index", 0))),
    ) if ordered else None
    connector_contact = (
        contact_status_between_blocks(connector_block, center)
        if center is not None else None
    )
    connector_member_lock_area = int(
        (connector_contact or {}).get("overlap_area", 0)
        if (connector_contact or {}).get("contact_status") == "male_to_female_lock"
        else 0
    )
    internal_lock_area = 0
    internal_lock_count = 0
    for left, right in zip(ordered, ordered[1:]):
        contact = contact_status_between_blocks(left, right)
        if contact and contact.get("contact_status") == "male_to_female_lock":
            internal_lock_area += int(contact.get("overlap_area", 0))
            internal_lock_count += 1

    centered = bool(
        abs((connector_block.position[0] + connector_block.size[0] / 2.0) - float(SYMMETRY_CENTER_PLANE)) < 1e-9
    )
    validation = config.get("validation", {}) or {}
    require_centered = bool(validation.get("require_centered_on_symmetry_axis", True))
    require_anchor = bool(validation.get("require_connector_to_anchor_lock", True))
    require_connector_member = bool(validation.get("require_connector_to_subassembly_lock", True))
    require_internal = bool(validation.get("require_internal_subassembly_locking", True))
    valid = bool(
        len(member_blocks) == expected_count
        and (not require_anchor or anchor_lock_area > 0)
        and (not require_connector_member or connector_member_lock_area > 0)
        and (not require_internal or internal_lock_count >= max(0, expected_count - 1))
        and (not require_centered or centered)
    )
    return {
        "assembly_id": physical_target_id,
        "physical_target_id": physical_target_id,
        "functional_block_id": int(connector_block.block_id),
        "anchor_segment_id": anchor_segment_id,
        "lock_area": int(anchor_lock_area + connector_member_lock_area + internal_lock_area),
        "anchor_lock_area": int(anchor_lock_area),
        "connector_to_subassembly_lock_area": int(connector_member_lock_area),
        "subassembly_internal_lock_area": int(internal_lock_area),
        "subassembly_structural_block_count": int(len(member_blocks)),
        "source_segment_ids": list(getattr(connector_block, "source_segment_ids", [])),
        "centered_on_symmetry_axis": centered,
        "valid": valid,
    }


def functional_segment_group_table(segments_labeled_df):
    rows = []
    for config in custom_functional_subassembly_configs():
        group_id = str(config.get("physical_target_id", config.get("assembly_id", "")))
        group_name = str(config.get("display_name", group_id.replace("_", " ").title()))
        source_segment_ids = [int(value) for value in config.get("source_segment_ids", [])]
        for segment_id in source_segment_ids:
            match = segments_labeled_df.loc[
                segments_labeled_df["segment_id"].astype(int) == int(segment_id)
            ]
            rows.append({
                "physical_group_id": group_id,
                "physical_group_name": group_name,
                "segment_id": int(segment_id),
                "segment_display_name": (
                    str(match.iloc[0].get("segment_display_name", f"Segment {segment_id}"))
                    if not match.empty else f"Segment {segment_id}"
                ),
                "segment_label": (
                    str(match.iloc[0].get("segment_label", "functional_member"))
                    if not match.empty else "functional_member"
                ),
                "group_role": "functional_subassembly_member",
                "anchor_segment_id": int(config.get("anchor_segment_id", -1)),
            })
    return pd.DataFrame(rows, columns=[
        "physical_group_id", "physical_group_name", "segment_id",
        "segment_display_name", "segment_label", "group_role", "anchor_segment_id",
    ])

def json_safe_value(value):
    """Recursively convert nested NumPy/pandas objects to JSON-safe values."""
    if isinstance(value, np.ndarray):
        return [json_safe_value(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return json_safe_value(value.item())
    if isinstance(value, dict):
        return {
            str(key): json_safe_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [json_safe_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return json_safe_value(value.value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if value is pd.NA:
        return None
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def safe_export_dataframe(df, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    export = df.copy()
    for column in export.columns:
        mask = export[column].map(
            lambda value: isinstance(
                value,
                (list, tuple, set, dict, np.ndarray),
            )
        )
        if mask.any():
            export.loc[mask, column] = export.loc[mask, column].map(
                lambda value: json.dumps(
                    json_safe_value(value),
                    ensure_ascii=False,
                    sort_keys=True,
                    allow_nan=False,
                )
            )
    export.to_csv(path, index=False)

BUILD_AXIS_TO_QUARTER_TURNS = {
    "+Y": 0,
    "+X": 1,
    "-Y": 2,
    "-X": 3,
}


def candidate_segment_build_axes():
    configured = (
        TASK_CONTEXT.get(
            "segment_assembly",
            {},
        )
        .get(
            "segment_packing",
            {},
        )
        .get(
            "candidate_build_axes",
            ["+Y"],
        )
    )
    axes = []
    for value in configured:
        axis = str(
            value
        ).strip().upper()
        if (
            axis
            in BUILD_AXIS_TO_QUARTER_TURNS
            and axis
            not in axes
        ):
            axes.append(
                axis
            )
    return (
        axes
        or ["+Y"]
    )


def build_axis_token(axis):
    return (
        str(axis)
        .replace(
            "+",
            "plus_",
        )
        .replace(
            "-",
            "minus_",
        )
        .lower()
    )


def coordinate_world_to_plan(
    coordinate,
    world_shape,
    quarter_turns,
):
    x, y, z = (
        int(
            coordinate[
                index
            ]
        )
        for index in range(
            3
        )
    )
    nx = int(
        world_shape[
            0
        ]
    )
    ny = int(
        world_shape[
            1
        ]
    )
    k = int(
        quarter_turns
    ) % 4

    if k == 0:
        return (
            x,
            y,
            z,
        )
    if k == 1:
        return (
            ny - 1 - y,
            x,
            z,
        )
    if k == 2:
        return (
            nx - 1 - x,
            ny - 1 - y,
            z,
        )
    return (
        y,
        nx - 1 - x,
        z,
    )


def coordinate_plan_to_world(
    coordinate,
    world_shape,
    quarter_turns,
):
    px, py, z = (
        int(
            coordinate[
                index
            ]
        )
        for index in range(
            3
        )
    )
    nx = int(
        world_shape[
            0
        ]
    )
    ny = int(
        world_shape[
            1
        ]
    )
    k = int(
        quarter_turns
    ) % 4

    if k == 0:
        return (
            px,
            py,
            z,
        )
    if k == 1:
        return (
            py,
            ny - 1 - px,
            z,
        )
    if k == 2:
        return (
            nx - 1 - px,
            ny - 1 - py,
            z,
        )
    return (
        nx - 1 - py,
        px,
        z,
    )


def face_world_to_plan(
    face,
    quarter_turns,
):
    if face in HORIZONTAL_FACES:
        return rotate_horizontal_face(
            face,
            90
            * (
                int(
                    quarter_turns
                )
                % 4
            ),
        )
    return face


def transform_requirement_to_plan(
    requirement,
    world_shape,
    quarter_turns,
):
    transformed = copy.deepcopy(
        requirement
    )
    for key in [
        "structural_coordinate",
        "connector_coordinate",
    ]:
        if key in transformed:
            transformed[
                key
            ] = coordinate_world_to_plan(
                transformed[
                    key
                ],
                world_shape,
                quarter_turns,
            )
    for key in [
        "structural_face",
        "connector_face",
    ]:
        if key in transformed:
            transformed[
                key
            ] = face_world_to_plan(
                transformed[
                    key
                ],
                quarter_turns,
            )
    transformed[
        "planning_quarter_turns"
    ] = int(
        quarter_turns
    )
    return transformed


def transform_requirements_to_plan(
    requirements,
    world_shape,
    quarter_turns,
):
    return [
        transform_requirement_to_plan(
            requirement,
            world_shape,
            quarter_turns,
        )
        for requirement in (
            requirements
            or []
        )
    ]


def restore_block_from_plan_to_world(
    block,
    world_shape,
    quarter_turns,
    build_axis,
):
    px, py, pz = (
        int(
            value
        )
        for value in (
            block.position
        )
    )
    sx, sy, sz = (
        int(
            value
        )
        for value in (
            block.size
        )
    )

    world_footprint = [
        coordinate_plan_to_world(
            (
                x,
                y,
                pz,
            ),
            world_shape,
            quarter_turns,
        )
        for x in range(
            px,
            px + sx,
        )
        for y in range(
            py,
            py + sy,
        )
    ]
    world_x = [
        coordinate[
            0
        ]
        for coordinate
        in world_footprint
    ]
    world_y = [
        coordinate[
            1
        ]
        for coordinate
        in world_footprint
    ]

    block.position = (
        min(
            world_x
        ),
        min(
            world_y
        ),
        pz,
    )
    world_size = (
        max(
            world_x
        )
        - min(
            world_x
        )
        + 1,
        max(
            world_y
        )
        - min(
            world_y
        )
        + 1,
        sz,
    )
    block.size = tuple(
        int(
            value
        )
        for value in (
            world_size
        )
    )
    world_rotation = (
        int(
            block.rotation
        )
        - 90
        * (
            int(
                quarter_turns
            )
            % 4
        )
    ) % 360
    apply_structural_rotation(
        block,
        world_rotation,
    )
    block.selected_build_axis = str(
        build_axis
    )
    return block


def restore_planning_result_to_world(
    planning_result,
    world_shape,
    quarter_turns,
    build_axis,
):
    block_by_id = {}

    for block in (
        planning_result[
            "blocks"
        ]
    ):
        restore_block_from_plan_to_world(
            block,
            world_shape,
            quarter_turns,
            build_axis,
        )
        block_by_id[
            int(
                block.block_id
            )
        ] = block

    planner_row_diagnostics = list(
        planning_result.get(
            "best_state",
            {},
        ).get(
            "row_diagnostics",
            [],
        )
    )

    for step_index, step in enumerate(
        planning_result[
            "instruction_steps"
        ],
        start=1,
    ):
        step[
            "blocks"
        ] = [
            block_by_id[
                int(
                    block.block_id
                )
            ]
            for block in (
                step[
                    "blocks"
                ]
            )
        ]
        step[
            "planner_row"
        ] = int(
            step.get(
                "row",
                step_index,
            )
        )
        step[
            "planning_diagnostic"
        ] = copy.deepcopy(
            planner_row_diagnostics[
                step_index - 1
            ]
            if (
                step_index - 1
                < len(
                    planner_row_diagnostics
                )
            )
            else {}
        )
        step[
            "row"
        ] = int(
            step_index
        )
        step[
            "build_axis"
        ] = str(
            build_axis
        )
        step[
            "world_slice_coordinate"
        ] = (
            min(
                (
                    block.position[
                        0
                    ]
                    if "X"
                    in build_axis
                    else block.position[
                        1
                    ]
                )
                for block in (
                    step[
                        "blocks"
                    ]
                )
            )
            if step[
                "blocks"
            ]
            else None
        )
        step[
            "rotation_assignment"
        ] = {
            int(
                block.block_id
            ): int(
                block.rotation
            )
            for block in (
                step[
                    "blocks"
                ]
            )
        }

    planning_result[
        "selected_build_axis"
    ] = str(
        build_axis
    )
    planning_result[
        "planning_quarter_turns"
    ] = int(
        quarter_turns
    )
    planning_result[
        "best_state"
    ][
        "blocks"
    ] = planning_result[
        "blocks"
    ]
    planning_result[
        "best_state"
    ][
        "steps"
    ] = planning_result[
        "instruction_steps"
    ]
    return planning_result


def segment_axis_candidate_sort_key(
    candidate,
    axis_priority,
):
    planning_result = (
        candidate[
            "planning_result"
        ]
    )
    best_state = (
        planning_result.get(
            "best_state",
            {},
        )
    )
    return (
        len(
            planning_result.get(
                "blocks",
                [],
            )
        ),
        int(
            best_state.get(
                "final_exposed_male_area",
                0,
            )
        ),
        -int(
            best_state.get(
                "total_prior_lock_area",
                0,
            )
        ),
        -int(
            best_state.get(
                "total_internal_lock_area",
                0,
            )
        ),
        int(
            axis_priority
        ),
    )


def mirrored_build_axis(
    axis,
    symmetry_axis_index,
):
    axis = str(
        axis
    )
    if (
        int(
            symmetry_axis_index
        )
        == 0
    ):
        return {
            "+X": "-X",
            "-X": "+X",
            "+Y": "+Y",
            "-Y": "-Y",
        }.get(
            axis,
            axis,
        )
    if (
        int(
            symmetry_axis_index
        )
        == 1
    ):
        return {
            "+X": "+X",
            "-X": "-X",
            "+Y": "-Y",
            "-Y": "+Y",
        }.get(
            axis,
            axis,
        )
    return axis


VISUALIZATION_CONFIG = {
    "enabled": True,
    "interactive": True,
    "show_inline_segmented": True,
    "show_inline_planning_layers": False,
    "show_inline_segment_sequences": False,
    "show_inline_final": True,
    "show_inline_assembly_sequence": True,
    "save_static_segment_plan_png": True,
    "save_static_final_png": True,
    "interactive_include_plotlyjs": "cdn",
    "candidate_preview_limit_per_group": 30,
    "marker_size": 5,
    "block_opacity": 0.96,
    "context_opacity": 0.10,
    **TASK_CONTEXT.get("visualization", {}),
}
VISUALIZATION_DIR = OUTPUT_DIR / "visualizations"
VISUALIZATION_DIR.mkdir(parents=True, exist_ok=True)
VISUALIZATION_MANIFEST = []


def register_visualization(path, stage, description, interactive=False):
    path = Path(path)
    VISUALIZATION_MANIFEST.append({
        "stage": stage,
        "description": description,
        "interactive": bool(interactive),
        "path": str(path),
        "exists": path.exists(),
    })


def block_rgb(block):
    return np.clip(
        np.asarray(get_block_color(block), dtype=float),
        0,
        255,
    ).astype(int)


def block_is_blue_or_green(block):
    red, green, blue = (
        block_rgb(block).astype(float)
        / 255.0
    )
    blue_dominant = bool(
        blue >= green * 0.88
        and blue > red + 0.10
    )
    green_dominant = bool(
        green >= blue * 0.72
        and green > red + 0.10
    )
    return bool(
        blue_dominant
        or green_dominant
    )


def interactive_effective_block_opacity(
    block,
    requested_opacity,
    *,
    preview=False,
):
    opacity = float(requested_opacity)
    if not block_is_blue_or_green(block):
        return opacity

    setting_name = (
        "interactive_blue_green_preview_min_opacity"
        if preview
        else "interactive_blue_green_min_opacity"
    )
    default_value = (
        0.34
        if preview
        else 0.99
    )
    return max(
        opacity,
        float(
            VISUALIZATION_CONFIG.get(
                setting_name,
                default_value,
            )
        ),
    )


def block_color_css(block):
    red, green, blue = block_rgb(block)
    return f"rgb({red},{green},{blue})"


def block_visual_role(block):
    record = getattr(block, "catalog_record", {}) or {}
    role = str(record.get("functional_role", "")).lower()
    block_role = str(
        getattr(block, "block_role", "")
        or getattr(block, "category", "")
    ).lower()
    if role == "wheel" or "functional" in block_role:
        return "functional"
    if role == "connector" or "connector" in block_role:
        return "connector"
    return "structural"


def hover_value_is_present(
    value,
):
    if value is None:
        return False
    if isinstance(
        value,
        str,
    ):
        return value.strip() not in {
            "",
            "None",
        }
    return True


def hover_value_text(
    value,
):
    if isinstance(
        value,
        np.ndarray,
    ):
        value = value.tolist()
    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return ", ".join(
            str(item)
            for item in value
        )
    if isinstance(
        value,
        dict,
    ):
        return json.dumps(
            value,
            sort_keys=True,
            default=str,
        )
    return str(
        value
    )


def block_hover(
    block,
):
    record = getattr(
        block,
        "catalog_record",
        {},
    ) or {}
    segment_id = getattr(
        block,
        "source_segment_id",
        None,
    )
    segment_name = getattr(
        block,
        "segment_name",
        getattr(
            block,
            "segment_display_name",
            None,
        ),
    )
    if (
        not segment_name
        and segment_id is not None
        and "segment_display_name_by_id"
        in globals()
    ):
        segment_name = (
            segment_display_name_by_id.get(
                int(
                    segment_id
                )
            )
        )

    rows = [
        (
            "Block ID",
            getattr(
                block,
                "block_id",
                None,
            ),
        ),
        (
            "Family",
            getattr(
                block,
                "block_family",
                None,
            ),
        ),
        (
            "Role",
            block_visual_role(
                block
            ),
        ),
        (
            "Visual shape",
            record.get(
                "visual_shape"
            ),
        ),
        (
            "Motion",
            record.get(
                "motion_type"
            ),
        ),
        (
            "Position",
            tuple(
                int(value)
                for value in block.position
            ),
        ),
        (
            "Size",
            tuple(
                int(value)
                for value in block.size
            ),
        ),
        (
            "Wheel axle",
            getattr(
                block,
                "wheel_axle_axis",
                None,
            ),
        ),
        (
            "Wheel plane",
            getattr(
                block,
                "wheel_disc_plane",
                None,
            ),
        ),
        (
            "Segment ID",
            segment_id,
        ),
        (
            "Segment name",
            segment_name,
        ),
        (
            "Semantic label",
            getattr(
                block,
                "segment_label",
                None,
            ),
        ),
        (
            "Source segment group",
            getattr(
                block,
                "source_segment_ids",
                None,
            ),
        ),
        (
            "Connected group",
            getattr(
                block,
                "connected_group_name",
                None,
            ),
        ),
        (
            "Functional subassembly member",
            getattr(
                block,
                "subassembly_member_role",
                None,
            ),
        ),
        (
            "Interface",
            getattr(
                block,
                "interface_id",
                None,
            ),
        ),
        (
            "Functional target",
            getattr(
                block,
                "physical_target_id",
                None,
            ),
        ),
    ]

    return "<br>".join(
        (
            f"<b>{name}</b>: "
            f"{hover_value_text(value)}"
        )
        for name, value in rows
        if hover_value_is_present(
            value
        )
    )


CUBE_TRIANGLES = np.asarray([
    [0,1,2],[0,2,3],[4,6,5],[4,7,6],
    [0,4,5],[0,5,1],[1,5,6],[1,6,2],
    [2,6,7],[2,7,3],[3,7,4],[3,4,0],
], dtype=int)


def cube_vertices(origin, size):
    x, y, z = (float(v) for v in origin)
    dx, dy, dz = (float(v) for v in size)
    return np.asarray([
        [x,y,z],[x+dx,y,z],[x+dx,y+dy,z],[x,y+dy,z],
        [x,y,z+dz],[x+dx,y,z+dz],[x+dx,y+dy,z+dz],[x,y+dy,z+dz],
    ])


def cube_trace(block, showlegend=False, opacity=None):
    vertices = cube_vertices(block.position, block.size)
    return go.Mesh3d(
        x=vertices[:,0], y=vertices[:,1], z=vertices[:,2],
        i=CUBE_TRIANGLES[:,0],
        j=CUBE_TRIANGLES[:,1],
        k=CUBE_TRIANGLES[:,2],
        color=block_color_css(block),
        opacity=interactive_effective_block_opacity(
            block,
            (
                VISUALIZATION_CONFIG.get(
                    "block_opacity",
                    1.0,
                )
                if opacity is None
                else opacity
            ),
            preview=False,
        ),
        flatshading=True,
        lighting={
            "ambient": 0.46,
            "diffuse": 0.92,
            "specular": 0.08,
            "roughness": 0.92,
        },
        hovertext=block_hover(block),
        hoverinfo="text",
        name=str(block.block_family),
        legendgroup=str(block.block_family),
        showlegend=showlegend,
    )


def cube_edge_trace(
    block,
    *,
    showlegend=False,
    opacity=None,
):
    """Bold rectangular-prism outline for an interactive block."""
    x, y, z = (
        float(value)
        for value in block.position
    )
    dx, dy, dz = (
        float(value)
        for value in block.size
    )

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
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]

    line_x = []
    line_y = []
    line_z = []
    for start, end in edges:
        for index in (start, end):
            line_x.append(vertices[index][0])
            line_y.append(vertices[index][1])
            line_z.append(vertices[index][2])
        line_x.append(None)
        line_y.append(None)
        line_z.append(None)

    return go.Scatter3d(
        x=line_x,
        y=line_y,
        z=line_z,
        mode="lines",
        line={
            "color": VISUALIZATION_CONFIG.get(
                "interactive_block_outline_color",
                "rgba(0,0,0,0.98)",
            ),
            "width": float(
                VISUALIZATION_CONFIG.get(
                    "interactive_block_outline_width",
                    3.0,
                )
            ),
        },
        opacity=float(
            VISUALIZATION_CONFIG.get(
                "interactive_block_outline_opacity",
                1.0,
            )
            if opacity is None
            else opacity
        ),
        hoverinfo="skip",
        name="Block outlines",
        legendgroup=str(block.block_family),
        showlegend=showlegend,
    )


def cylinder_geometry(origin, size, axis, depth=None, segments=36):
    origin = np.asarray(origin, dtype=float)
    size = np.asarray(size, dtype=float)
    center = origin + size / 2.0
    axis = int(axis)
    other = [candidate for candidate in range(3) if candidate != axis]
    radius = 0.48 * min(size[other[0]], size[other[1]])
    depth = float(size[axis] if depth is None else min(depth, size[axis]))
    vertices = []
    for side in [-0.5, 0.5]:
        for theta in np.linspace(0, 2*np.pi, segments, endpoint=False):
            point = center.copy()
            point[axis] += side * depth
            point[other[0]] += radius * np.cos(theta)
            point[other[1]] += radius * np.sin(theta)
            vertices.append(point)
    lower_center = len(vertices)
    point = center.copy()
    point[axis] -= depth / 2
    vertices.append(point)
    upper_center = len(vertices)
    point = center.copy()
    point[axis] += depth / 2
    vertices.append(point)
    triangles = []
    for index in range(segments):
        following = (index + 1) % segments
        lower_a, lower_b = index, following
        upper_a, upper_b = segments + index, segments + following
        triangles.extend([
            [lower_a, lower_b, upper_b],
            [lower_a, upper_b, upper_a],
            [lower_center, lower_b, lower_a],
            [upper_center, upper_a, upper_b],
        ])
    return np.asarray(vertices), np.asarray(triangles, dtype=int)


def infer_connector_render_axis(
    block,
):
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


def wheel_traces(block, showlegend=False):
    size = np.asarray(block.size, dtype=float)
    axis = infer_connector_render_axis(block)
    record = getattr(block, "catalog_record", {}) or {}
    visible_size = record.get("visible_geometry_size")
    visible_depth = float(size[axis])
    if visible_size:
        numbers = [int(v) for v in re.findall(r"\d+", str(visible_size))]
        if len(numbers) >= 3:
            visible_depth = float(
                numbers[axis] if axis < len(numbers) else min(numbers[:3])
            )
    visible_depth = max(0.60, min(float(size[axis]), visible_depth))
    vertices, triangles = cylinder_geometry(
        block.position,
        block.size,
        axis,
        depth=visible_depth,
    )
    return [go.Mesh3d(
        x=vertices[:,0], y=vertices[:,1], z=vertices[:,2],
        i=triangles[:,0], j=triangles[:,1], k=triangles[:,2],
        color=block_color_css(block),
        opacity=interactive_effective_block_opacity(
            block,
            VISUALIZATION_CONFIG.get(
                "block_opacity",
                0.99,
            ),
            preview=False,
        ),
        flatshading=True,
        lighting={
            "ambient": 0.48,
            "diffuse": 0.82,
            "specular": 0.35,
            "roughness": 0.45,
        },
        hovertext=block_hover(block),
        hoverinfo="text",
        name=str(block.block_family),
        legendgroup=str(block.block_family),
        showlegend=showlegend,
    )]


def block_traces(block, showlegend=False):
    record = getattr(
        block,
        "catalog_record",
        {},
    ) or {}
    visual_shape = str(
        record.get(
            "visual_shape",
            "",
        )
    ).lower()
    role = str(
        record.get(
            "functional_role",
            "",
        )
    ).lower()

    if role == "wheel" or "wheel" in visual_shape:
        return wheel_traces(
            block,
            showlegend=showlegend,
        )

    traces = [
        cube_trace(
            block,
            showlegend=showlegend,
        )
    ]
    if VISUALIZATION_CONFIG.get(
        "interactive_block_outlines",
        True,
    ):
        traces.append(
            cube_edge_trace(
                block,
                showlegend=False,
            )
        )
    return traces


FACE_CENTERS = {
    "+X": lambda x,y,z,dx,dy,dz: (x+dx,y+dy/2,z+dz/2),
    "-X": lambda x,y,z,dx,dy,dz: (x,y+dy/2,z+dz/2),
    "+Y": lambda x,y,z,dx,dy,dz: (x+dx/2,y+dy,z+dz/2),
    "-Y": lambda x,y,z,dx,dy,dz: (x+dx/2,y,z+dz/2),
    "+Z": lambda x,y,z,dx,dy,dz: (x+dx/2,y+dy/2,z+dz),
    "-Z": lambda x,y,z,dx,dy,dz: (x+dx/2,y+dy/2,z),
}



def point_inside_interval(
    value,
    minimum,
    maximum,
    tolerance=1e-9,
):
    return bool(
        float(minimum) - tolerance
        <= float(value)
        <= float(maximum) + tolerance
    )


def face_center_is_exposed(
    block,
    face,
    all_blocks,
):
    """False when another block covers the center of this face."""
    center = get_face_center(
        block,
        face,
    )
    x, y, z = (
        float(value)
        for value in block.position
    )
    dx, dy, dz = (
        float(value)
        for value in block.size
    )
    tolerance = 1e-9

    for other in all_blocks:
        if int(other.block_id) == int(
            block.block_id
        ):
            continue

        ox, oy, oz = (
            float(value)
            for value in other.position
        )
        odx, ody, odz = (
            float(value)
            for value in other.size
        )

        if face == "+X":
            touching = abs(
                ox - (x + dx)
            ) <= tolerance
            covered = (
                point_inside_interval(
                    center[1], oy, oy + ody
                )
                and point_inside_interval(
                    center[2], oz, oz + odz
                )
            )
        elif face == "-X":
            touching = abs(
                ox + odx - x
            ) <= tolerance
            covered = (
                point_inside_interval(
                    center[1], oy, oy + ody
                )
                and point_inside_interval(
                    center[2], oz, oz + odz
                )
            )
        elif face == "+Y":
            touching = abs(
                oy - (y + dy)
            ) <= tolerance
            covered = (
                point_inside_interval(
                    center[0], ox, ox + odx
                )
                and point_inside_interval(
                    center[2], oz, oz + odz
                )
            )
        elif face == "-Y":
            touching = abs(
                oy + ody - y
            ) <= tolerance
            covered = (
                point_inside_interval(
                    center[0], ox, ox + odx
                )
                and point_inside_interval(
                    center[2], oz, oz + odz
                )
            )
        elif face == "+Z":
            touching = abs(
                oz - (z + dz)
            ) <= tolerance
            covered = (
                point_inside_interval(
                    center[0], ox, ox + odx
                )
                and point_inside_interval(
                    center[1], oy, oy + ody
                )
            )
        else:
            touching = abs(
                oz + odz - z
            ) <= tolerance
            covered = (
                point_inside_interval(
                    center[0], ox, ox + odx
                )
                and point_inside_interval(
                    center[1], oy, oy + ody
                )
            )

        if touching and covered:
            return False

    return True


def face_traces(blocks):
    blocks = list(blocks)
    groups = {
        "male": {
            "x": [],
            "y": [],
            "z": [],
            "text": [],
        },
        "female": {
            "x": [],
            "y": [],
            "z": [],
            "text": [],
        },
    }
    exposed_only = bool(
        VISUALIZATION_CONFIG.get(
            "interactive_face_markers_exposed_only",
            True,
        )
    )
    marker_offset = float(
        VISUALIZATION_CONFIG.get(
            "interactive_face_marker_offset",
            0.08,
        )
    )
    normals = {
        "+X": (1.0, 0.0, 0.0),
        "-X": (-1.0, 0.0, 0.0),
        "+Y": (0.0, 1.0, 0.0),
        "-Y": (0.0, -1.0, 0.0),
        "+Z": (0.0, 0.0, 1.0),
        "-Z": (0.0, 0.0, -1.0),
    }
    seen = {
        "male": set(),
        "female": set(),
    }

    for block in blocks:
        for face in ALL_FACES:
            face_type = actual_block_face_type(
                block,
                face,
            )
            if face_type not in groups:
                continue
            if (
                exposed_only
                and not face_center_is_exposed(
                    block,
                    face,
                    blocks,
                )
            ):
                continue

            point = list(
                get_face_center(
                    block,
                    face,
                )
            )
            normal = normals[face]
            point = [
                point[axis]
                + normal[axis] * marker_offset
                for axis in range(3)
            ]

            key = tuple(
                round(value, 5)
                for value in point
            )
            if key in seen[face_type]:
                continue
            seen[face_type].add(key)

            groups[face_type]["x"].append(
                point[0]
            )
            groups[face_type]["y"].append(
                point[1]
            )
            groups[face_type]["z"].append(
                point[2]
            )
            groups[face_type]["text"].append(
                f"Block {block.block_id}<br>"
                f"{block.block_family}<br>"
                f"{face}: {face_type}<br>"
                f"Exposed face"
            )

    return [
        go.Scatter3d(
            x=groups["male"]["x"],
            y=groups["male"]["y"],
            z=groups["male"]["z"],
            mode="markers",
            marker={
                "size": int(
                    VISUALIZATION_CONFIG.get(
                        "interactive_male_marker_size",
                        6,
                    )
                ),
                "color": "red",
                "line": {
                    "color": "black",
                    "width": int(
                        VISUALIZATION_CONFIG.get(
                            "interactive_male_marker_line_width",
                            1,
                        )
                    ),
                },
                "symbol": "circle",
            },
            text=groups["male"]["text"],
            hoverinfo="text",
            name="Exposed male faces",
            visible=True,
        ),
        go.Scatter3d(
            x=groups["female"]["x"],
            y=groups["female"]["y"],
            z=groups["female"]["z"],
            mode="markers",
            marker={
                "size": int(
                    VISUALIZATION_CONFIG.get(
                        "interactive_female_marker_size",
                        8,
                    )
                ),
                "color": "white",
                "line": {
                    "color": "dodgerblue",
                    "width": int(
                        VISUALIZATION_CONFIG.get(
                            "interactive_female_marker_line_width",
                            2,
                        )
                    ),
                },
                "symbol": "circle-open",
            },
            text=groups["female"]["text"],
            hoverinfo="text",
            name="Exposed female faces",
            visible=True,
        ),
    ]


def figure_layout(title):
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


_PLOTLY_INLINE_RUNTIME_EMBEDDED = False


def display_plotly_embedded(
    fig,
    *,
    description="Interactive figure",
    force_include_plotlyjs=False,
):
    """Embed a Plotly figure directly into the active interactive output."""
    global _PLOTLY_INLINE_RUNTIME_EMBEDDED

    include_plotlyjs = bool(
        force_include_plotlyjs
        or not _PLOTLY_INLINE_RUNTIME_EMBEDDED
    )
    height = int(
        VISUALIZATION_CONFIG.get(
            "interactive_player_height",
            620,
        )
    )
    width = str(
        VISUALIZATION_CONFIG.get(
            "interactive_player_width",
            "100%",
        )
    )
    config = {
        "displaylogo": False,
        "scrollZoom": True,
        "responsive": True,
    }

    html = fig.to_html(
        full_html=False,
        include_plotlyjs=(
            True
            if include_plotlyjs
            else False
        ),
        config=config,
        default_width=width,
        default_height=f"{height}px",
    )
    pipeline_log(
        "show_inline_render_messages",
        (
            f"[INTERACTIVE EMBEDDED] "
            f"{description}"
        ),
    )
    emit_diagnostic(
        html
    )
    _PLOTLY_INLINE_RUNTIME_EMBEDDED = True
    return html


def write_interactive(
    fig,
    path,
    stage,
    description,
    show_inline=False,
):
    """Save optional HTML and/or display a robust inline Plotly figure."""
    path = Path(path)
    saved_path = None

    if VISUALIZATION_CONFIG.get(
        "save_interactive_html",
        False,
    ):
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        fig.write_html(
            path,
            include_plotlyjs=VISUALIZATION_CONFIG.get(
                "interactive_include_plotlyjs",
                "cdn",
            ),
            full_html=True,
            auto_open=False,
            config={
                "displaylogo": False,
                "scrollZoom": True,
                "responsive": True,
            },
        )
        register_visualization(
            path,
            stage,
            description,
            interactive=True,
        )
        pipeline_log(
            "show_visualization_paths",
            f"[INTERACTIVE HTML] {path}",
        )
        saved_path = path

    if show_inline:
        inline_mode = str(
            VISUALIZATION_CONFIG.get(
                "interactive_inline_mode",
                "embedded_html",
            )
        ).lower()

        if inline_mode == "embedded_html":
            display_plotly_embedded(
                fig,
                description=description,
            )
        else:
            renderer = VISUALIZATION_CONFIG.get(
                "interactive_renderer",
                "browser",
            )
            pipeline_log(
                "show_inline_render_messages",
                (
                    f"[INTERACTIVE INLINE] "
                    f"{description}"
                ),
            )
            fig.show(
                renderer=renderer,
                config={
                    "displaylogo": False,
                    "scrollZoom": True,
                    "responsive": True,
                },
            )

    return (
        saved_path
        if saved_path is not None
        else fig
    )


def interactive_build_figure(
    blocks,
    title,
    include_faces=True,
):
    blocks = list(
        blocks
    )
    figure = go.Figure()
    shown = set()
    family_counts = Counter(
        str(
            block.block_family
        )
        for block in blocks
    )

    for block in blocks:
        family = str(
            block.block_family
        )
        show_family_legend = (
            family
            not in shown
        )
        traces = block_traces(
            block,
            showlegend=(
                show_family_legend
            ),
        )
        for trace in traces:
            if (
                show_family_legend
                and bool(
                    getattr(
                        trace,
                        "showlegend",
                        False,
                    )
                )
            ):
                trace.name = (
                    f"{family} "
                    f"({family_counts[family]})"
                )
                trace.legendgroup = family
            figure.add_trace(
                trace
            )
        shown.add(
            family
        )

    if include_faces:
        for trace in face_traces(
            blocks
        ):
            figure.add_trace(
                trace
            )

    layout = figure_layout(
        title
    )
    layout["title"] = {
        "text": title,
        "x": float(
            VISUALIZATION_CONFIG.get(
                "interactive_final_title_x",
                0.5,
            )
        ),
        "xanchor": "center",
        "y": float(
            VISUALIZATION_CONFIG.get(
                "interactive_final_title_y",
                0.985,
            )
        ),
        "yanchor": "top",
    }
    layout["margin"] = {
        **layout.get(
            "margin",
            {},
        ),
        "t": int(
            VISUALIZATION_CONFIG.get(
                "interactive_final_top_margin",
                105,
            )
        ),
    }
    layout["scene"] = {
        **layout.get(
            "scene",
            {},
        ),
        "domain": {
            "x": [
                0.0,
                1.0,
            ],
            "y": [
                0.0,
                float(
                    VISUALIZATION_CONFIG.get(
                        "interactive_final_scene_top",
                        0.80,
                    )
                ),
            ],
        },
    }

    if include_faces:
        total_traces = len(
            figure.data
        )
        male_index = (
            total_traces - 2
        )
        female_index = (
            total_traces - 1
        )

        default_mode = str(
            VISUALIZATION_CONFIG.get(
                "interactive_face_default_mode",
                "blocks",
            )
        ).lower()
        default_values = {
            "blocks": (
                False,
                False,
            ),
            "male": (
                True,
                False,
            ),
            "female": (
                False,
                True,
            ),
            "both": (
                True,
                True,
            ),
        }.get(
            default_mode,
            (
                False,
                False,
            ),
        )

        figure.data[
            male_index
        ].visible = (
            default_values[
                0
            ]
        )
        figure.data[
            female_index
        ].visible = (
            default_values[
                1
            ]
        )

        control_y = float(
            VISUALIZATION_CONFIG.get(
                "interactive_final_control_y",
                0.93,
            )
        )

        layout["updatemenus"] = [
            {
                "type": "buttons",
                "direction": "left",
                "x": float(
                    VISUALIZATION_CONFIG.get(
                        "interactive_final_male_control_x",
                        0.01,
                    )
                ),
                "y": control_y,
                "xanchor": "left",
                "yanchor": "top",
                "showactive": True,
                "active": (
                    1
                    if default_values[
                        0
                    ]
                    else 0
                ),
                "buttons": [
                    {
                        "label": "Male off",
                        "method": "restyle",
                        "args": [
                            {
                                "visible": False
                            },
                            [
                                male_index
                            ],
                        ],
                    },
                    {
                        "label": "Male on",
                        "method": "restyle",
                        "args": [
                            {
                                "visible": True
                            },
                            [
                                male_index
                            ],
                        ],
                    },
                ],
            },
            {
                "type": "buttons",
                "direction": "left",
                "x": float(
                    VISUALIZATION_CONFIG.get(
                        "interactive_final_female_control_x",
                        0.27,
                    )
                ),
                "y": control_y,
                "xanchor": "left",
                "yanchor": "top",
                "showactive": True,
                "active": (
                    1
                    if default_values[
                        1
                    ]
                    else 0
                ),
                "buttons": [
                    {
                        "label": "Female off",
                        "method": "restyle",
                        "args": [
                            {
                                "visible": False
                            },
                            [
                                female_index
                            ],
                        ],
                    },
                    {
                        "label": "Female on",
                        "method": "restyle",
                        "args": [
                            {
                                "visible": True
                            },
                            [
                                female_index
                            ],
                        ],
                    },
                ],
            },
        ]

    figure.update_layout(
        **layout
    )
    return figure


def visualize_blocks_static(
    blocks,
    grid_size=None,
    elev=25,
    azim=45,
    show_faces=False,
    title="Catalog-Colored Blocks",
    output_path=None,
    show_inline=True,
):
    """Full catalog colors at normal opacity; no grey wash."""
    fig = plt.figure(figsize=(12,10))
    ax = fig.add_subplot(111, projection="3d")
    maximum = int(grid_size or 1)
    minimum = 0
    for block in blocks:
        x,y,z = block.position
        dx,dy,dz = block.size
        minimum = min(
            minimum,
            int(x),
            int(y),
            int(z),
        )
        maximum = max(maximum, int(x+dx), int(y+dy), int(z+dz))
        ax.bar3d(
            x,y,z,dx,dy,dz,
            color=block_rgb(block)/255.0,
            edgecolor="black",
            linewidth=0.7,
            alpha=0.94,
            shade=True,
        )
    if show_faces:
        for block in blocks:
            x,y,z = (float(v) for v in block.position)
            dx,dy,dz = (float(v) for v in block.size)
            for face in ALL_FACES:
                face_type = actual_block_face_type(block, face)
                if face_type not in {"male","female"}:
                    continue
                point = FACE_CENTERS[face](x,y,z,dx,dy,dz)
                if face_type == "male":
                    ax.scatter(*point,color="red",edgecolors="black",s=55,depthshade=False)
                else:
                    ax.scatter(
                        *point,facecolors="none",edgecolors="dodgerblue",
                        linewidths=1.5,s=70,depthshade=False
                    )
    padding = 1
    ax.set_xlim(minimum-padding,maximum+padding)
    ax.set_ylim(minimum-padding,maximum+padding)
    ax.set_zlim(minimum-padding,maximum+padding)
    ax.set_box_aspect((1,1,1))
    ax.set_xlabel("X"); ax.set_ylabel("Y"); ax.set_zlabel("Z")
    ax.view_init(elev=elev,azim=azim)
    ax.set_title(title)
    plt.tight_layout()
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True,exist_ok=True)
        fig.savefig(output_path,dpi=180,bbox_inches="tight")
        register_visualization(output_path,"static_snapshot",title)
        pipeline_log(
            "show_visualization_paths",
            f"[STATIC] {output_path}",
        )
    if show_inline:
        plt.show()
    else:
        plt.close(fig)
    return fig


def segmented_interactive_figure(
    segment_grid,
    segment_table,
    *,
    title="Interactive Segmented Source Model",
    stage_name="Source",
    marker_opacity=0.88,
):
    fig = go.Figure()
    display_column = (
        "segment_display_name"
        if "segment_display_name" in segment_table.columns
        else ("segment_name" if "segment_name" in segment_table.columns else "segment_label")
    )
    labels = dict(zip(
        segment_table["segment_id"].astype(int),
        segment_table[display_column].astype(str),
    ))
    semantic_labels = dict(zip(
        segment_table["segment_id"].astype(int),
        segment_table["segment_label"].astype(str),
    ))
    for segment_id in sorted(
        int(value)
        for value in np.unique(segment_grid)
        if int(value) > 0
    ):
        coordinates = np.argwhere(
            segment_grid == segment_id
        )
        color = np.asarray(
            segment_colors.get(
                segment_id,
                np.asarray([0.65, 0.65, 0.65]),
            ),
            dtype=float,
        )
        if color.max() <= 1.0:
            color *= 255
        red, green, blue = np.clip(
            color,
            0,
            255,
        ).astype(int)
        label = labels.get(
            segment_id,
            f"Segment {segment_id}",
        )
        semantic_label = semantic_labels.get(
            segment_id,
            "unknown",
        )
        fig.add_trace(
            go.Scatter3d(
                x=coordinates[:, 0] + 0.5,
                y=coordinates[:, 1] + 0.5,
                z=coordinates[:, 2] + 0.5,
                mode="markers",
                marker={
                    "size": int(
                        VISUALIZATION_CONFIG.get(
                            "marker_size",
                            5,
                        )
                    ),
                    "color": (
                        f"rgb({red},{green},{blue})"
                    ),
                    "opacity": float(
                        marker_opacity
                    ),
                    "symbol": "square",
                },
                text=[
                    (
                        f"<b>{stage_name}</b><br>"
                        f"Segment {segment_id}<br>"
                        f"Name: {label}<br>"
                        f"Semantic label: {semantic_label}<br>"
                        f"Voxel: {tuple(coordinate.tolist())}"
                    )
                    for coordinate in coordinates
                ],
                hoverinfo="text",
                name=(
                    f"{stage_name} — "
                    f"{segment_id}: {label}"
                ),
                legendgroup=(
                    f"{stage_name}:{segment_id}"
                ),
            )
        )

    fig.update_layout(
        **figure_layout(title)
    )
    return fig


def segmentation_comparison_figure(
    raw_segment_grid,
    structuralized_segment_grid,
    segment_table,
):
    """Single viewer replacing the duplicate raw and structuralized plots."""
    if "segment_display_name" in segment_table.columns:
        display_column = "segment_display_name"
    elif "segment_name" in segment_table.columns:
        display_column = "segment_name"
    elif "confirmed_name" in segment_table.columns:
        display_column = "confirmed_name"
    elif "segment_label" in segment_table.columns:
        display_column = "segment_label"
    else:
        display_column = None

    segment_ids = (
        segment_table["segment_id"]
        .astype(int)
    )

    if display_column is None:
        labels = {
            int(segment_id): (
                f"Segment {int(segment_id)}"
            )
            for segment_id in segment_ids
        }
    else:
        labels = dict(
            zip(
                segment_ids,
                segment_table[
                    display_column
                ].fillna("").astype(str),
            )
        )

    if "segment_label" in segment_table.columns:
        semantic_labels = dict(
            zip(
                segment_ids,
                segment_table[
                    "segment_label"
                ].fillna(
                    "unknown"
                ).astype(str),
            )
        )
    elif "confirmed_label" in segment_table.columns:
        semantic_labels = dict(
            zip(
                segment_ids,
                segment_table[
                    "confirmed_label"
                ].fillna(
                    "unknown"
                ).astype(str),
            )
        )
    else:
        semantic_labels = {
            int(segment_id): "unknown"
            for segment_id in segment_ids
        }

    figure = go.Figure()
    raw_trace_indices = []
    structural_trace_indices = []

    stages = [
        (
            "Raw source",
            raw_segment_grid,
            0.28,
            False,
            raw_trace_indices,
        ),
        (
            "Structuralized planning model",
            structuralized_segment_grid,
            0.90,
            True,
            structural_trace_indices,
        ),
    ]

    for (
        stage_name,
        stage_grid,
        opacity,
        initially_visible,
        trace_indices,
    ) in stages:
        for segment_id in sorted(
            int(value)
            for value in np.unique(
                stage_grid
            )
            if int(value) > 0
        ):
            coordinates = np.argwhere(
                stage_grid == segment_id
            )
            if len(coordinates) == 0:
                continue

            color = np.asarray(
                segment_colors.get(
                    segment_id,
                    np.asarray(
                        [
                            0.65,
                            0.65,
                            0.65,
                        ]
                    ),
                ),
                dtype=float,
            )
            if color.max() <= 1.0:
                color *= 255
            red, green, blue = np.clip(
                color,
                0,
                255,
            ).astype(int)

            label = str(
                labels.get(
                    segment_id,
                    f"Segment {segment_id}",
                )
                or f"Segment {segment_id}"
            )
            semantic_label = str(
                semantic_labels.get(
                    segment_id,
                    "unknown",
                )
                or "unknown"
            )

            figure.add_trace(
                go.Scatter3d(
                    x=(
                        coordinates[:, 0]
                        + 0.5
                    ),
                    y=(
                        coordinates[:, 1]
                        + 0.5
                    ),
                    z=(
                        coordinates[:, 2]
                        + 0.5
                    ),
                    mode="markers",
                    marker={
                        "size": int(
                            VISUALIZATION_CONFIG.get(
                                "marker_size",
                                5,
                            )
                        ),
                        "color": (
                            f"rgb({red},"
                            f"{green},"
                            f"{blue})"
                        ),
                        "opacity": float(
                            opacity
                        ),
                        "symbol": "square",
                    },
                    text=[
                        (
                            f"<b>{stage_name}</b><br>"
                            f"Segment {segment_id}<br>"
                            f"Name: {label}<br>"
                            f"Semantic label: "
                            f"{semantic_label}<br>"
                            f"Voxel: "
                            f"{tuple(coordinate.tolist())}"
                        )
                        for coordinate in coordinates
                    ],
                    hoverinfo="text",
                    name=(
                        f"{stage_name} — "
                        f"{segment_id}: {label}"
                    ),
                    legendgroup=(
                        f"{stage_name}:"
                        f"{segment_id}"
                    ),
                    visible=bool(
                        initially_visible
                    ),
                )
            )
            trace_indices.append(
                len(figure.data) - 1
            )

    trace_count = len(
        figure.data
    )

    def visibility_for(mode):
        visible = [
            False
        ] * trace_count
        if mode in {
            "raw",
            "overlay",
        }:
            for index in raw_trace_indices:
                visible[index] = True
        if mode in {
            "structuralized",
            "overlay",
        }:
            for index in (
                structural_trace_indices
            ):
                visible[index] = True
        return visible

    descriptions = {
        "raw": (
            "Raw semantic voxel segments before "
            "2×2 lattice conversion."
        ),
        "structuralized": (
            "Final structuralized and symmetry-exactified "
            "segment masks used by the block planner."
        ),
        "overlay": (
            "Raw source shown translucently beneath the "
            "structuralized planning model."
        ),
    }
    titles = {
        "raw": (
            "Segment Geometry Review — Raw Source"
        ),
        "structuralized": (
            "Segment Geometry Review — "
            "Structuralized Planning Model"
        ),
        "overlay": (
            "Segment Geometry Review — Overlay"
        ),
    }

    buttons = []
    for button_label, mode in [
        (
            "Raw source",
            "raw",
        ),
        (
            "Structuralized planning model",
            "structuralized",
        ),
        (
            "Overlay",
            "overlay",
        ),
    ]:
        buttons.append(
            {
                "label": button_label,
                "method": "update",
                "args": [
                    {
                        "visible": (
                            visibility_for(
                                mode
                            )
                        )
                    },
                    {
                        "title": (
                            titles[mode]
                        ),
                        "annotations": [
                            {
                                "xref": "paper",
                                "yref": "paper",
                                "x": 0.01,
                                "y": 0.99,
                                "xanchor": "left",
                                "yanchor": "top",
                                "text": (
                                    descriptions[
                                        mode
                                    ]
                                ),
                                "showarrow": False,
                                "bgcolor": (
                                    "rgba("
                                    "255,255,255,"
                                    "0.90)"
                                ),
                                "bordercolor": (
                                    "gray"
                                ),
                                "borderwidth": 1,
                            }
                        ],
                    },
                ],
            }
        )

    layout = figure_layout(
        titles["structuralized"]
    )
    layout["updatemenus"] = [
        {
            "type": "buttons",
            "direction": "left",
            "x": 0.0,
            "y": 1.10,
            "buttons": buttons,
        }
    ]
    layout["annotations"] = [
        {
            "xref": "paper",
            "yref": "paper",
            "x": 0.01,
            "y": 0.99,
            "xanchor": "left",
            "yanchor": "top",
            "text": descriptions[
                "structuralized"
            ],
            "showarrow": False,
            "bgcolor": (
                "rgba(255,255,255,0.90)"
            ),
            "bordercolor": "gray",
            "borderwidth": 1,
        }
    ]
    figure.update_layout(
        **layout
    )
    return figure


def geometry_mask(shape, dataframe, group_column=None, limit_per_group=None):
    mask = np.zeros(shape,dtype=bool)
    if dataframe is None or dataframe.empty:
        return mask
    selected = dataframe
    if group_column and group_column in selected.columns and limit_per_group:
        groups = []
        for _, group in selected.groupby(group_column,sort=True):
            if "score" in group.columns:
                group = group.sort_values("score",ascending=False)
            groups.append(group.head(int(limit_per_group)))
        if groups:
            selected = pd.concat(groups,ignore_index=True)
    for coordinates in selected.get(
        "geometry_coordinates",pd.Series(dtype=object)
    ):
        for coordinate in coordinates or []:
            coordinate = tuple(int(v) for v in coordinate)
            if all(0 <= coordinate[a] < shape[a] for a in range(3)):
                mask[coordinate] = True
    return mask


def add_mask(fig, mask, name, color, opacity, visible=True, size=5):
    coords = np.argwhere(mask)
    if len(coords) == 0:
        return
    fig.add_trace(go.Scatter3d(
        x=coords[:,0]+0.5,y=coords[:,1]+0.5,z=coords[:,2]+0.5,
        mode="markers",
        marker={"size":size,"color":color,"opacity":opacity,"symbol":"square"},
        name=name,visible=visible,hoverinfo="name",
    ))


def planning_layers_figure(
    segment_grid,
    interface_payload,
    connector_candidates,
    selected_connectors,
    physical_targets,
    functional_candidates,
    selected_functional,
):
    fig = go.Figure()
    interface_mask = np.zeros(segment_grid.shape,dtype=bool)
    for payload in interface_payload.values():
        for key in ["a_coordinates","b_coordinates"]:
            for coordinate in payload.get(key,[]):
                interface_mask[tuple(int(v) for v in coordinate)] = True
    source_ids = set()
    if physical_targets is not None and not physical_targets.empty:
        for values in physical_targets["source_segment_ids"]:
            source_ids.update(int(v) for v in values)
    limit = int(VISUALIZATION_CONFIG.get("candidate_preview_limit_per_group",30))
    add_mask(
        fig,segment_grid>0,"Source structure","lightgray",
        float(VISUALIZATION_CONFIG.get("context_opacity",0.10)),True,4
    )
    add_mask(fig,interface_mask,"Structural interfaces","limegreen",0.95,True,6)
    add_mask(
        fig,
        geometry_mask(segment_grid.shape,connector_candidates,"interface_id",limit),
        "Connector candidates","orange",0.35,"legendonly",5
    )
    add_mask(
        fig,geometry_mask(segment_grid.shape,selected_connectors),
        "Selected connector reservation","purple",0.92,True,7
    )
    add_mask(
        fig,np.isin(segment_grid,sorted(source_ids)),
        "Functional source segments","royalblue",0.80,True,6
    )
    add_mask(
        fig,
        geometry_mask(segment_grid.shape,functional_candidates,"physical_target_id",limit),
        "Functional candidates","deeppink",0.30,"legendonly",5
    )
    add_mask(
        fig,geometry_mask(segment_grid.shape,selected_functional),
        "Selected functional geometry","gold",0.95,True,7
    )
    fig.update_layout(**figure_layout("Interactive Planning Layers"))
    return fig


def block_appearance_from_steps(instruction_steps):
    appearance = {}
    for step_number, step in enumerate(instruction_steps,start=1):
        for block in step.get("blocks",[]):
            appearance[int(block.block_id)] = step_number
    return appearance


def sequence_figure(blocks, appearance, title):
    fig = go.Figure()
    trace_steps = []
    shown = set()
    for block in blocks:
        family = str(block.block_family)
        block_step = int(appearance.get(int(block.block_id),1))
        for trace in block_traces(block,showlegend=family not in shown):
            trace.visible = block_step <= 1
            fig.add_trace(trace)
            trace_steps.append(block_step)
        shown.add(family)
    maximum = max(trace_steps,default=1)
    slider_steps = []
    for step in range(1,maximum+1):
        slider_steps.append({
            "method":"update",
            "label":str(step),
            "args":[
                {"visible":[trace_step <= step for trace_step in trace_steps]},
                {"title":f"{title} — Step {step}"},
            ],
        })
    layout = figure_layout(f"{title} — Step 1")
    layout["sliders"] = [{
        "active":0,
        "currentvalue":{"prefix":"Step: "},
        "pad":{"t":45},
        "steps":slider_steps,
    }]
    fig.update_layout(**layout)
    return fig


def save_visualization_manifest():
    path = VISUALIZATION_DIR / "visualization_manifest.json"
    path.write_text(
        json.dumps(
            {
                "config":VISUALIZATION_CONFIG,
                "count":len(VISUALIZATION_MANIFEST),
                "visualizations":VISUALIZATION_MANIFEST,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    pipeline_log(
        "show_visualization_paths",
        f"[VISUALIZATION] {path}",
    )
    return path


# ------------------------------------------------------------------
# Symmetry-aware planning and validation
# ------------------------------------------------------------------

SYMMETRY_CONFIG = TASK_CONTEXT.get("symmetry", {})
SYMMETRY_ENABLED = bool(
    SYMMETRY_CONFIG.get("enabled", False)
)
SYMMETRY_AXIS_INDEX = {
    "X": 0,
    "Y": 1,
    "Z": 2,
}[str(SYMMETRY_CONFIG.get("axis", "X")).upper()]


def mask_iou(mask_a, mask_b):
    mask_a = np.asarray(mask_a, dtype=bool)
    mask_b = np.asarray(mask_b, dtype=bool)
    union = int((mask_a | mask_b).sum())
    if union == 0:
        return 1.0
    return float((mask_a & mask_b).sum() / union)


def mirror_index_coordinate(index, center_plane):
    mirrored = 2.0 * float(center_plane) - (float(index) + 0.5)
    return int(round(mirrored - 0.5))


def mirror_mask(mask, axis, center_plane):
    mask = np.asarray(mask, dtype=bool)
    mirrored = np.zeros_like(mask, dtype=bool)
    for coordinate in np.argwhere(mask):
        reflected = coordinate.astype(int).copy()
        reflected[axis] = mirror_index_coordinate(
            reflected[axis],
            center_plane,
        )
        if all(
            0 <= reflected[current_axis] < mask.shape[current_axis]
            for current_axis in range(3)
        ):
            mirrored[tuple(reflected)] = True
    return mirrored


def infer_symmetry_center_plane(mask, axis):
    occupied = np.argwhere(mask)
    if len(occupied) == 0:
        return (mask.shape[axis] / 2.0), 0.0

    minimum = int(occupied[:, axis].min())
    maximum = int(occupied[:, axis].max())
    bbox_center = (minimum + maximum + 1) / 2.0

    configured = SYMMETRY_CONFIG.get("center_plane")
    if configured is not None:
        candidate_planes = [float(configured)]
    else:
        candidate_planes = list(
            np.arange(
                float(minimum),
                float(maximum + 1) + 0.25,
                0.5,
            )
        )
        candidate_planes.append(float(bbox_center))

    unique_candidates = sorted(set(candidate_planes))
    scored = []
    for plane in unique_candidates:
        score = mask_iou(
            mask,
            mirror_mask(mask, axis, plane),
        )
        scored.append((
            float(score),
            -abs(float(plane) - float(bbox_center)),
            float(plane),
        ))

    best_score, _, best_plane = max(scored)
    return float(best_plane), float(best_score)


def semantic_side_and_base(label):
    text = re.sub(
        r"[^a-z0-9]+",
        "_",
        str(label).strip().lower(),
    ).strip("_")
    tokens = [token for token in text.split("_") if token]

    side = None
    left_tokens = {"left", "lhs"}
    right_tokens = {"right", "rhs"}

    if tokens and tokens[0] in {"l", "r"}:
        side = "left" if tokens[0] == "l" else "right"
        tokens = tokens[1:]
    elif tokens and tokens[-1] in {"l", "r"}:
        side = "left" if tokens[-1] == "l" else "right"
        tokens = tokens[:-1]

    if any(token in left_tokens for token in tokens):
        side = "left"
        tokens = [
            token for token in tokens
            if token not in left_tokens
        ]
    elif any(token in right_tokens for token in tokens):
        side = "right"
        tokens = [
            token for token in tokens
            if token not in right_tokens
        ]

    base = "_".join(tokens) or text
    return side, base


def parse_declared_symmetry_pairs():
    declared = SYMMETRY_CONFIG.get(
        "paired_segment_ids",
        [],
    )
    pairs = []
    for item in declared:
        if isinstance(item, dict):
            segment_a = item.get(
                "segment_a",
                item.get("left_segment_id"),
            )
            segment_b = item.get(
                "segment_b",
                item.get("right_segment_id"),
            )
        elif (
            isinstance(item, (list, tuple))
            and len(item) >= 2
        ):
            segment_a, segment_b = item[:2]
        else:
            continue
        if segment_a is None or segment_b is None:
            continue
        pairs.append((
            int(segment_a),
            int(segment_b),
        ))
    return pairs


def segment_centroid(mask):
    coordinates = np.argwhere(mask)
    if len(coordinates) == 0:
        return np.asarray([np.nan, np.nan, np.nan])
    return coordinates.mean(axis=0) + 0.5


def discover_structural_symmetry_pairs(
    segment_grid,
    segment_table,
    structural_segment_ids,
):
    structural_mask = np.isin(
        segment_grid,
        structural_segment_ids,
    )
    center_plane, global_source_iou = (
        infer_symmetry_center_plane(
            structural_mask,
            SYMMETRY_AXIS_INDEX,
        )
    )
    threshold = float(
        SYMMETRY_CONFIG.get(
            "minimum_mirror_iou",
            0.75,
        )
    )

    labels = dict(
        zip(
            segment_table["segment_id"].astype(int),
            segment_table["segment_label"].astype(str),
        )
    )
    masks = {
        int(segment_id): (
            segment_grid == int(segment_id)
        )
        for segment_id in structural_segment_ids
    }

    accepted_pairs = []
    audit_rows = []
    paired_ids = set()

    def evaluate_pair(
        segment_a,
        segment_b,
        source,
        semantic_base=None,
    ):
        segment_a = int(segment_a)
        segment_b = int(segment_b)
        if (
            segment_a == segment_b
            or segment_a not in masks
            or segment_b not in masks
        ):
            return None

        mirrored_a = mirror_mask(
            masks[segment_a],
            SYMMETRY_AXIS_INDEX,
            center_plane,
        )
        iou = mask_iou(
            mirrored_a,
            masks[segment_b],
        )
        centroid_a = segment_centroid(masks[segment_a])
        centroid_b = segment_centroid(masks[segment_b])
        accepted = bool(iou >= threshold)

        side_a, base_a = semantic_side_and_base(
            labels.get(segment_a, "unknown")
        )
        side_b, base_b = semantic_side_and_base(
            labels.get(segment_b, "unknown")
        )

        row = {
            "pair_id": (
                f"SP_{min(segment_a, segment_b):03d}_"
                f"{max(segment_a, segment_b):03d}"
            ),
            "segment_a": segment_a,
            "segment_b": segment_b,
            "segment_a_label": labels.get(
                segment_a,
                "unknown",
            ),
            "segment_b_label": labels.get(
                segment_b,
                "unknown",
            ),
            "segment_a_side": side_a,
            "segment_b_side": side_b,
            "semantic_base": (
                semantic_base
                or (
                    base_a
                    if base_a == base_b
                    else None
                )
            ),
            "pair_source": source,
            "source_mirror_iou": float(iou),
            "minimum_required_iou": threshold,
            "accepted": accepted,
            "centroid_a_axis": float(
                centroid_a[SYMMETRY_AXIS_INDEX]
            ),
            "centroid_b_axis": float(
                centroid_b[SYMMETRY_AXIS_INDEX]
            ),
            "center_plane": float(center_plane),
        }
        audit_rows.append(row)
        if accepted:
            accepted_pairs.append(dict(row))
            paired_ids.update({
                segment_a,
                segment_b,
            })
        return row

    # 1. Explicit model/task pairs.
    for segment_a, segment_b in parse_declared_symmetry_pairs():
        if (
            segment_a in paired_ids
            or segment_b in paired_ids
        ):
            continue
        evaluate_pair(
            segment_a,
            segment_b,
            "declared",
        )

    # 2. Semantic left/right pairs.
    semantic_groups = defaultdict(
        lambda: {"left": [], "right": []}
    )
    for segment_id in structural_segment_ids:
        if int(segment_id) in paired_ids:
            continue
        side, base_label = semantic_side_and_base(
            labels.get(int(segment_id), "unknown")
        )
        if side in {"left", "right"}:
            semantic_groups[base_label][side].append(
                int(segment_id)
            )

    for base_label, sides in sorted(
        semantic_groups.items()
    ):
        candidates = []
        for left_id in sides["left"]:
            for right_id in sides["right"]:
                score = mask_iou(
                    mirror_mask(
                        masks[left_id],
                        SYMMETRY_AXIS_INDEX,
                        center_plane,
                    ),
                    masks[right_id],
                )
                candidates.append(
                    (score, left_id, right_id)
                )
        for _, left_id, right_id in sorted(
            candidates,
            reverse=True,
        ):
            if (
                left_id in paired_ids
                or right_id in paired_ids
            ):
                continue
            evaluate_pair(
                left_id,
                right_id,
                "semantic",
                semantic_base=base_label,
            )

    # 3. Geometry-only pairing for remaining opposite-side segments.
    geometry_candidates = []
    remaining = [
        int(segment_id)
        for segment_id in structural_segment_ids
        if int(segment_id) not in paired_ids
    ]
    for index, segment_a in enumerate(remaining):
        centroid_a = segment_centroid(
            masks[segment_a]
        )[SYMMETRY_AXIS_INDEX]
        for segment_b in remaining[index + 1:]:
            centroid_b = segment_centroid(
                masks[segment_b]
            )[SYMMETRY_AXIS_INDEX]
            if (
                (centroid_a - center_plane)
                * (centroid_b - center_plane)
                >= 0
            ):
                continue
            iou = mask_iou(
                mirror_mask(
                    masks[segment_a],
                    SYMMETRY_AXIS_INDEX,
                    center_plane,
                ),
                masks[segment_b],
            )
            geometry_candidates.append(
                (iou, segment_a, segment_b)
            )

    for iou, segment_a, segment_b in sorted(
        geometry_candidates,
        reverse=True,
    ):
        if iou < threshold:
            continue
        if (
            segment_a in paired_ids
            or segment_b in paired_ids
        ):
            continue
        evaluate_pair(
            segment_a,
            segment_b,
            "geometry",
        )

    return {
        "center_plane": float(center_plane),
        "global_source_mirror_iou": float(
            global_source_iou
        ),
        "accepted_pairs": accepted_pairs,
        "audit_df": pd.DataFrame(audit_rows),
    }


def mirror_face_name(face, axis):
    axis_letter = ["X", "Y", "Z"][axis]
    if face == f"+{axis_letter}":
        return f"-{axis_letter}"
    if face == f"-{axis_letter}":
        return f"+{axis_letter}"
    return face


def mirrored_structural_rotation(block, axis):
    current_male_face = male_face_for_rotation(
        block.rotation,
        block.size,
    )
    target_male_face = mirror_face_name(
        current_male_face,
        axis,
    )
    for rotation in [0, 90, 180, 270]:
        if male_face_for_rotation(
            rotation,
            block.size,
        ) == target_male_face:
            return rotation
    raise ValueError(
        "No allowed structural rotation mirrors male face "
        f"{current_male_face} to {target_male_face} "
        f"for block size {block.size}."
    )


def mirror_block_origin(
    position,
    size,
    axis,
    center_plane,
):
    origin = list(
        float(value)
        for value in position
    )
    size = list(
        float(value)
        for value in size
    )
    mirrored_value = (
        2.0 * float(center_plane)
        - origin[axis]
        - size[axis]
    )
    rounded = round(mirrored_value)
    if abs(mirrored_value - rounded) > 1e-6:
        raise ValueError(
            "Mirrored block origin is off-grid: "
            f"{mirrored_value}"
        )
    origin[axis] = int(rounded)
    return tuple(int(round(value)) for value in origin)


def choose_pair_template(pair_row):
    segment_a = int(pair_row["segment_a"])
    segment_b = int(pair_row["segment_b"])
    preference = str(
        SYMMETRY_CONFIG.get(
            "template_side_preference",
            "left",
        )
    ).lower()

    if preference in {"left", "right"}:
        side_a = pair_row.get("segment_a_side")
        side_b = pair_row.get("segment_b_side")
        if side_a == preference:
            return segment_a, segment_b
        if side_b == preference:
            return segment_b, segment_a

    return min(segment_a, segment_b), max(
        segment_a,
        segment_b,
    )


def mirror_planning_result(
    template_result,
    template_segment_id,
    partner_segment_id,
    partner_label,
    partner_mask,
    next_block_id,
    center_plane,
    partner_connector_face_requirements=None,
):
    template_planning = template_result[
        "planning_result"
    ]
    old_to_new = {}
    mirrored_blocks = []

    for template_block in template_planning["blocks"]:
        mirrored_block = copy.deepcopy(template_block)
        old_id = int(template_block.block_id)
        mirrored_block.block_id = int(next_block_id)
        next_block_id += 1
        mirrored_block.position = mirror_block_origin(
            template_block.position,
            template_block.size,
            SYMMETRY_AXIS_INDEX,
            center_plane,
        )
        mirrored_rotation = mirrored_structural_rotation(
            template_block,
            SYMMETRY_AXIS_INDEX,
        )
        apply_structural_rotation(
            mirrored_block,
            mirrored_rotation,
        )
        mirrored_block.source_segment_id = int(
            partner_segment_id
        )
        mirrored_block.segment_label = str(
            partner_label
        )
        mirrored_block.subassembly_id = (
            f"segment_{int(partner_segment_id)}"
        )
        mirrored_block.block_role = (
            "segment_structural"
        )
        mirrored_block.symmetry_source_segment_id = int(
            template_segment_id
        )
        old_to_new[old_id] = mirrored_block
        mirrored_blocks.append(mirrored_block)

    mirrored_steps = []
    for template_step in template_planning[
        "instruction_steps"
    ]:
        new_step = copy.deepcopy(template_step)
        new_step_blocks = [
            old_to_new[int(block.block_id)]
            for block in template_step["blocks"]
        ]
        new_step["blocks"] = new_step_blocks
        new_step[
            "planner_row"
        ] = int(
            template_step.get(
                "planner_row",
                template_step.get(
                    "row",
                    len(
                        mirrored_steps
                    )
                    + 1,
                ),
            )
        )
        new_step[
            "row"
        ] = int(
            len(
                mirrored_steps
            )
            + 1
        )
        new_step[
            "world_slice_coordinate"
        ] = int(
            min(
                (
                    block.position[
                        0
                    ]
                    if "X"
                    in str(
                        template_step.get(
                            "build_axis",
                            template_planning.get(
                                "selected_build_axis",
                                "+Y",
                            ),
                        )
                    )
                    else block.position[
                        1
                    ]
                )
                for block
                in new_step_blocks
            )
        )
        new_step["rotation_assignment"] = {
            int(block.block_id): int(block.rotation)
            for block in new_step_blocks
        }
        mirrored_steps.append(new_step)

    if SYMMETRY_AXIS_INDEX == 1:
        mirrored_steps = list(
            reversed(mirrored_steps)
        )

    mirrored_planning = copy.deepcopy(
        template_planning
    )
    mirrored_planning["blocks"] = mirrored_blocks
    mirrored_planning["instruction_steps"] = (
        mirrored_steps
    )
    mirrored_planning["best_state"]["blocks"] = (
        mirrored_blocks
    )
    mirrored_planning["best_state"]["steps"] = (
        mirrored_steps
    )

    row_diagnostics = copy.deepcopy(
        mirrored_planning["best_state"].get(
            "row_diagnostics",
            [],
        )
    )
    for index, step in enumerate(
        mirrored_steps
    ):
        if index < len(
            row_diagnostics
        ):
            step[
                "planning_diagnostic"
            ] = copy.deepcopy(
                row_diagnostics[
                    index
                ]
            )
            step[
                "planner_row"
            ] = int(
                row_diagnostics[
                    index
                ].get(
                    "row",
                    step.get(
                        "planner_row",
                        index + 1,
                    ),
                )
            )
    mirrored_planning["best_state"][
        "row_diagnostics"
    ] = row_diagnostics
    template_build_axis = str(
        template_result.get(
            "selected_build_axis",
            template_planning.get(
                "selected_build_axis",
                "+Y",
            ),
        )
    )
    partner_build_axis = mirrored_build_axis(
        template_build_axis,
        SYMMETRY_AXIS_INDEX,
    )
    mirrored_planning[
        "selected_build_axis"
    ] = partner_build_axis
    for mirrored_block in mirrored_blocks:
        mirrored_block.selected_build_axis = (
            partner_build_axis
        )
    for mirrored_step in mirrored_steps:
        mirrored_step["build_axis"] = (
            partner_build_axis
        )

    covered = rasterize_blocks(
        mirrored_blocks,
        partner_mask.shape,
    )
    exact_coverage = bool(
        np.array_equal(covered, partner_mask)
    )
    validation = validate_planned_instruction_steps(
        mirrored_blocks,
        mirrored_steps,
        connector_face_requirements=[],
    )
    receiving_face_validation = {
        "rows": [],
        "groups": [],
        "total": 0,
        "alternative_total": 0,
        "satisfied_count": 0,
        "satisfaction_ratio": 1.0,
        "valid": True,
        "deferred": True,
        "deferred_requirement_count": int(
            len(
                partner_connector_face_requirements
                or []
            )
        ),
    }
    valid = bool(
        exact_coverage
        and validation[
            "all_blocks_accepted_and_supported"
        ]
    )

    return {
        "segment_id": int(partner_segment_id),
        "segment_label": str(partner_label),
        "planning_result": mirrored_planning,
        "selected_build_axis": partner_build_axis,
        "validation": validation,
        "exact_coverage": exact_coverage,
        "valid": valid,
        "packable_voxels": int(
            partner_mask.sum()
        ),
        "covered_voxels": int(
            (covered & partner_mask).sum()
        ),
        "extra_voxels": int(
            (covered & ~partner_mask).sum()
        ),
        "missing_voxels": int(
            (partner_mask & ~covered).sum()
        ),
        "planning_mode": (
            f"mirrored_from_segment_"
            f"{int(template_segment_id)}"
        ),
        "symmetry_template_segment_id": int(
            template_segment_id
        ),
        "connector_face_requirement_count": (
            receiving_face_validation["total"]
        ),
        "connector_face_requirement_satisfied_count": (
            receiving_face_validation[
                "satisfied_count"
            ]
        ),
        "connector_face_requirement_satisfaction_ratio": (
            receiving_face_validation[
                "satisfaction_ratio"
            ]
        ),
        "connector_face_requirements_valid": (
            receiving_face_validation["valid"]
        ),
        "connector_face_requirement_audit": (
            receiving_face_validation["rows"]
        ),
    }, next_block_id


def mirrored_block_signature(
    block,
    axis,
    center_plane,
):
    return (
        str(block.block_family),
        mirror_block_origin(
            block.position,
            block.size,
            axis,
            center_plane,
        ),
        tuple(int(value) for value in block.size),
        mirror_face_name(
            male_face_for_rotation(
                block.rotation,
                block.size,
            ),
            axis,
        ),
    )


def actual_block_signature(block):
    return (
        str(block.block_family),
        tuple(int(value) for value in block.position),
        tuple(int(value) for value in block.size),
        male_face_for_rotation(
            block.rotation,
            block.size,
        ),
    )


def compare_paired_block_plans(
    blocks_a,
    blocks_b,
    center_plane,
):
    mirrored_counter = Counter(
        mirrored_block_signature(
            block,
            SYMMETRY_AXIS_INDEX,
            center_plane,
        )
        for block in blocks_a
    )
    actual_counter = Counter(
        actual_block_signature(block)
        for block in blocks_b
    )
    exact = mirrored_counter == actual_counter

    if mirrored_counter or actual_counter:
        intersection = sum(
            (
                mirrored_counter
                & actual_counter
            ).values()
        )
        union = sum(
            (
                mirrored_counter
                | actual_counter
            ).values()
        )
        signature_iou = (
            intersection / union
            if union
            else 1.0
        )
    else:
        signature_iou = 1.0

    return {
        "block_plan_exact_mirror": bool(exact),
        "block_signature_iou": float(
            signature_iou
        ),
        "mirrored_signature_count": int(
            sum(mirrored_counter.values())
        ),
        "actual_signature_count": int(
            sum(actual_counter.values())
        ),
    }


def symmetric_target_pairs(
    physical_targets_df,
    segment_grid,
    center_plane,
):
    if (
        physical_targets_df is None
        or physical_targets_df.empty
    ):
        return []

    pairs = []
    for attachment_id, group in (
        physical_targets_df.groupby(
            "attachment_id",
            sort=True,
        )
    ):
        left_rows = group[
            group["side"].astype(str).str.lower()
            == "left"
        ]
        right_rows = group[
            group["side"].astype(str).str.lower()
            == "right"
        ]
        candidates = []
        for _, left_row in left_rows.iterrows():
            left_mask = np.isin(
                segment_grid,
                [
                    int(value)
                    for value in left_row[
                        "source_segment_ids"
                    ]
                ],
            )
            for _, right_row in right_rows.iterrows():
                right_mask = np.isin(
                    segment_grid,
                    [
                        int(value)
                        for value in right_row[
                            "source_segment_ids"
                        ]
                    ],
                )
                iou = mask_iou(
                    mirror_mask(
                        left_mask,
                        SYMMETRY_AXIS_INDEX,
                        center_plane,
                    ),
                    right_mask,
                )
                candidates.append((
                    iou,
                    str(left_row[
                        "physical_target_id"
                    ]),
                    str(right_row[
                        "physical_target_id"
                    ]),
                ))
        used = set()
        for iou, left_id, right_id in sorted(
            candidates,
            reverse=True,
        ):
            if left_id in used or right_id in used:
                continue
            if iou < float(
                SYMMETRY_CONFIG.get(
                    "minimum_mirror_iou",
                    0.75,
                )
            ):
                continue
            pairs.append({
                "attachment_id": attachment_id,
                "left_target_id": left_id,
                "right_target_id": right_id,
                "source_mirror_iou": float(iou),
            })
            used.update({left_id, right_id})
    return pairs


def normalized_face_role_signature(face_roles):
    return tuple(
        sorted(
            (
                str(face),
                str(role),
            )
            for face, role in dict(
                face_roles or {}
            ).items()
        )
    )


def mirrored_face_role_signature(
    face_roles,
    axis,
):
    mirrored = {
        mirror_face_name(face, axis): role
        for face, role in dict(
            face_roles or {}
        ).items()
    }
    return normalized_face_role_signature(
        mirrored
    )


def mirrored_candidate_geometry_signature(
    row,
    center_plane,
):
    origin = tuple(
        int(value)
        for value in row["origin"]
    )
    size = tuple(
        int(value)
        for value in row["size"]
    )
    return (
        str(row["block_family"]),
        mirror_block_origin(
            origin,
            size,
            SYMMETRY_AXIS_INDEX,
            center_plane,
        ),
        size,
        mirrored_face_role_signature(
            row.get("face_roles", {}),
            SYMMETRY_AXIS_INDEX,
        ),
    )


def actual_candidate_geometry_signature(row):
    return (
        str(row["block_family"]),
        tuple(int(value) for value in row["origin"]),
        tuple(int(value) for value in row["size"]),
        normalized_face_role_signature(
            row.get("face_roles", {})
        ),
    )


def select_functional_candidates_symmetry_aware(
    candidates_df,
    physical_targets_df,
    center_plane,
    initial_reserved_coordinates=None,
):
    if candidates_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    reserved = set(
        initial_reserved_coordinates or []
    )
    selected = []
    audit_rows = []
    paired_target_ids = set()

    for pair in symmetric_target_pairs(
        physical_targets_df,
        segment_grid_planner,
        center_plane,
    ):
        left_id = pair["left_target_id"]
        right_id = pair["right_target_id"]
        left_candidates = candidates_df[
            candidates_df["physical_target_id"].astype(str)
            == left_id
        ].copy()
        right_candidates = candidates_df[
            candidates_df["physical_target_id"].astype(str)
            == right_id
        ].copy()

        right_lookup = defaultdict(list)
        for _, right_row in right_candidates.iterrows():
            right_lookup[
                actual_candidate_geometry_signature(
                    right_row
                )
            ].append(right_row)

        chosen_pair = None
        for _, left_row in left_candidates.sort_values(
            ["score", "candidate_id"],
            ascending=[False, True],
        ).iterrows():
            mirrored_signature = (
                mirrored_candidate_geometry_signature(
                    left_row,
                    center_plane,
                )
            )
            for right_row in right_lookup.get(
                mirrored_signature,
                [],
            ):
                left_coordinates = {
                    tuple(value)
                    for value in left_row[
                        "geometry_coordinates"
                    ]
                }
                right_coordinates = {
                    tuple(value)
                    for value in right_row[
                        "geometry_coordinates"
                    ]
                }
                if (
                    left_coordinates & reserved
                    or right_coordinates & reserved
                    or left_coordinates
                    & right_coordinates
                ):
                    continue
                chosen_pair = (
                    left_row.to_dict(),
                    right_row.to_dict(),
                )
                break
            if chosen_pair is not None:
                break

        paired_target_ids.update({
            left_id,
            right_id,
        })
        if chosen_pair is not None:
            left_row, right_row = chosen_pair
            selected.extend([
                left_row,
                right_row,
            ])
            reserved.update(
                tuple(value)
                for value in left_row[
                    "geometry_coordinates"
                ]
            )
            reserved.update(
                tuple(value)
                for value in right_row[
                    "geometry_coordinates"
                ]
            )
            status = "selected_exact_mirrored_pair"
        else:
            status = "no_exact_mirrored_candidate_pair"

        audit_rows.append({
            **pair,
            "selection_status": status,
        })

    # Unpaired/center functional targets remain individually selectable.
    unpaired_candidates = candidates_df[
        ~candidates_df[
            "physical_target_id"
        ].astype(str).isin(paired_target_ids)
    ]
    for target_id, group in unpaired_candidates.groupby(
        "physical_target_id",
        sort=True,
    ):
        for _, row in group.sort_values(
            ["score", "candidate_id"],
            ascending=[False, True],
        ).iterrows():
            coordinates = {
                tuple(value)
                for value in row[
                    "geometry_coordinates"
                ]
            }
            if coordinates & reserved:
                continue
            selected.append(row.to_dict())
            reserved.update(coordinates)
            break

    return (
        pd.DataFrame(selected),
        pd.DataFrame(audit_rows),
    )


def structural_segment_mirror_map(
    structural_pairs,
    segment_grid,
    structural_segment_ids,
    center_plane,
):
    mirror_map = {}
    for pair in structural_pairs:
        segment_a = int(pair["segment_a"])
        segment_b = int(pair["segment_b"])
        mirror_map[segment_a] = segment_b
        mirror_map[segment_b] = segment_a

    threshold = float(
        SYMMETRY_CONFIG.get(
            "minimum_mirror_iou",
            0.75,
        )
    )
    for segment_id in structural_segment_ids:
        segment_id = int(segment_id)
        if segment_id in mirror_map:
            continue
        mask = segment_grid == segment_id
        self_iou = mask_iou(
            mirror_mask(
                mask,
                SYMMETRY_AXIS_INDEX,
                center_plane,
            ),
            mask,
        )
        if self_iou >= threshold:
            mirror_map[segment_id] = segment_id

    return mirror_map


def pair_structural_interfaces_for_symmetry(
    interfaces_df,
    segment_mirror_map,
):
    if interfaces_df is None or interfaces_df.empty:
        return [], set()

    rows = {
        str(row.interface_id): row
        for row in interfaces_df.itertuples(
            index=False
        )
    }
    pair_lookup = defaultdict(list)
    for interface_id, row in rows.items():
        pair_key = frozenset({
            int(row.segment_a),
            int(row.segment_b),
        })
        pair_lookup[pair_key].append(interface_id)

    pairs = []
    self_mirrored = set()
    used = set()

    for interface_id, row in rows.items():
        if interface_id in used:
            continue

        mapped_a = segment_mirror_map.get(
            int(row.segment_a)
        )
        mapped_b = segment_mirror_map.get(
            int(row.segment_b)
        )
        if mapped_a is None or mapped_b is None:
            continue

        target_key = frozenset({
            int(mapped_a),
            int(mapped_b),
        })
        target_ids = [
            candidate_id
            for candidate_id in pair_lookup.get(
                target_key,
                [],
            )
            if candidate_id not in used
        ]
        if not target_ids:
            continue

        if interface_id in target_ids:
            self_mirrored.add(interface_id)
            used.add(interface_id)
            continue

        partner_id = sorted(target_ids)[0]
        pairs.append({
            "interface_a": interface_id,
            "interface_b": partner_id,
        })
        used.update({
            interface_id,
            partner_id,
        })

    return pairs, self_mirrored


def select_connector_candidates_symmetry_aware(
    candidates_df,
    interfaces_df,
    structural_pairs,
    structural_segment_ids,
    center_plane,
):
    if candidates_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    segment_mirror_map = (
        structural_segment_mirror_map(
            structural_pairs,
            segment_grid_planner,
            structural_segment_ids,
            center_plane,
        )
    )
    interface_pairs, self_mirrored_interfaces = (
        pair_structural_interfaces_for_symmetry(
            interfaces_df,
            segment_mirror_map,
        )
    )

    reserved = set()
    selected = []
    audit_rows = []
    paired_interface_ids = set()

    for pair in interface_pairs:
        interface_a = pair["interface_a"]
        interface_b = pair["interface_b"]
        candidates_a = candidates_df[
            candidates_df["interface_id"].astype(str)
            == interface_a
        ].copy()
        candidates_b = candidates_df[
            candidates_df["interface_id"].astype(str)
            == interface_b
        ].copy()

        lookup_b = defaultdict(list)
        for _, row_b in candidates_b.iterrows():
            lookup_b[
                actual_candidate_geometry_signature(
                    row_b
                )
            ].append(row_b)

        chosen_pair = None
        for _, row_a in candidates_a.sort_values(
            ["score", "candidate_id"],
            ascending=[False, True],
        ).iterrows():
            target_signature = (
                mirrored_candidate_geometry_signature(
                    row_a,
                    center_plane,
                )
            )
            for row_b in lookup_b.get(
                target_signature,
                [],
            ):
                coordinates_a = {
                    tuple(value)
                    for value in row_a[
                        "geometry_coordinates"
                    ]
                }
                coordinates_b = {
                    tuple(value)
                    for value in row_b[
                        "geometry_coordinates"
                    ]
                }
                if (
                    coordinates_a & reserved
                    or coordinates_b & reserved
                    or coordinates_a & coordinates_b
                ):
                    continue
                chosen_pair = (
                    row_a.to_dict(),
                    row_b.to_dict(),
                )
                break
            if chosen_pair is not None:
                break

        paired_interface_ids.update({
            interface_a,
            interface_b,
        })
        if chosen_pair is not None:
            row_a, row_b = chosen_pair
            selected.extend([row_a, row_b])
            reserved.update(
                tuple(value)
                for value in row_a[
                    "geometry_coordinates"
                ]
            )
            reserved.update(
                tuple(value)
                for value in row_b[
                    "geometry_coordinates"
                ]
            )
            status = "selected_exact_mirrored_pair"
        else:
            status = (
                "no_exact_mirrored_connector_pair"
            )

        audit_rows.append({
            "interface_a": interface_a,
            "interface_b": interface_b,
            "selection_status": status,
        })

    remaining = candidates_df[
        ~candidates_df["interface_id"].astype(str).isin(
            paired_interface_ids
        )
    ]
    for interface_id, group in remaining.groupby(
        "interface_id",
        sort=True,
    ):
        # A self-mirrored centerline interface can be selected normally.
        # An interface with no mirrored partner remains diagnostic-only
        # unless it is not part of a symmetry-mapped region.
        for _, row in group.sort_values(
            ["score", "candidate_id"],
            ascending=[False, True],
        ).iterrows():
            coordinates = {
                tuple(value)
                for value in row[
                    "geometry_coordinates"
                ]
            }
            if coordinates & reserved:
                continue
            selected.append(row.to_dict())
            reserved.update(coordinates)
            break

    return (
        pd.DataFrame(selected),
        pd.DataFrame(audit_rows),
    )



# ------------------------------------------------------------------
# Connector receiving-face requirements
# ------------------------------------------------------------------

CONNECTOR_FACE_POLICY = (
    TASK_CONTEXT.get("segment_assembly", {})
    .get("structural_connector_policy", {})
)


def opposite_contact_role(connector_role):
    if connector_role == "male":
        return "female"
    if connector_role == "female":
        return "male"
    return None


def coordinate_in_bounds(coordinate, shape):
    return all(
        0 <= int(coordinate[axis]) < int(shape[axis])
        for axis in range(3)
    )


def structural_face_role_possible(face, required_role):
    for record in STRUCTURAL_CATALOG_RECORDS:
        size = tuple(
            int(value)
            for value in record["column_world_size"]
        )
        for rotation in (0, 90, 180, 270):
            if (
                face_type_for_rotation(
                    face,
                    rotation,
                    size,
                )
                == required_role
            ):
                return True
    return False


def connector_candidate_receiving_requirements(
    candidate,
    segment_grid,
):
    """
    Produce ranked alternative receiving anchors.

    A connector side must find one mechanically compatible anchor patch on
    its structural segment. It is no longer required to force every adjacent
    connector voxel onto a particular male/female structural face.
    """
    geometry = box_mask(
        segment_grid.shape,
        tuple(
            int(value)
            for value in candidate[
                "origin"
            ]
        ),
        tuple(
            int(value)
            for value in candidate[
                "size"
            ]
        ),
    )
    if geometry is None:
        return (
            [],
            False,
            "connector_geometry_out_of_bounds",
        )

    policy = (
        CONNECTOR_FACE_POLICY
    )
    maximum_alternatives = max(
        1,
        int(
            policy.get(
                "maximum_receiving_face_alternatives_per_side",
                4,
            )
        ),
    )
    prefer_structural_female = bool(
        policy.get(
            "prefer_structural_female_receiving_face",
            True,
        )
    )

    selected_requirements = []
    errors = []
    face_roles = candidate[
        "face_roles"
    ]

    for side_name, segment_id in [
        (
            "a",
            int(
                candidate[
                    "segment_a"
                ]
            ),
        ),
        (
            "b",
            int(
                candidate[
                    "segment_b"
                ]
            ),
        ),
    ]:
        source_mask = (
            segment_grid
            == segment_id
        )
        retained_mask = (
            source_mask
            & ~geometry
        )
        raw_requirements = []

        for structural_coordinate_array in (
            np.argwhere(
                retained_mask
            )
        ):
            structural_coordinate = tuple(
                int(value)
                for value in (
                    structural_coordinate_array
                )
            )
            for (
                structural_face,
                delta,
            ) in FACE_TO_VECTOR.items():
                connector_coordinate = tuple(
                    structural_coordinate[
                        axis
                    ]
                    + int(
                        delta[
                            axis
                        ]
                    )
                    for axis in range(
                        3
                    )
                )
                if (
                    not coordinate_in_bounds(
                        connector_coordinate,
                        segment_grid.shape,
                    )
                    or not geometry[
                        connector_coordinate
                    ]
                ):
                    continue

                connector_face = (
                    OPPOSITE_FACE[
                        structural_face
                    ]
                )
                connector_role = (
                    face_roles.get(
                        connector_face,
                        "none",
                    )
                )
                required_role = (
                    opposite_contact_role(
                        connector_role
                    )
                )
                if required_role is None:
                    continue

                role_possible = (
                    structural_face_role_possible(
                        structural_face,
                        required_role,
                    )
                )
                raw_requirements.append(
                    {
                        "candidate_id": int(
                            candidate[
                                "candidate_id"
                            ]
                        ),
                        "interface_id": str(
                            candidate[
                                "interface_id"
                            ]
                        ),
                        "segment_id": int(
                            segment_id
                        ),
                        "interface_side": (
                            side_name
                        ),
                        "block_family": str(
                            candidate[
                                "block_family"
                            ]
                        ),
                        "structural_coordinate": (
                            structural_coordinate
                        ),
                        "connector_coordinate": (
                            connector_coordinate
                        ),
                        "structural_face": (
                            structural_face
                        ),
                        "connector_face": (
                            connector_face
                        ),
                        "connector_face_role": (
                            connector_role
                        ),
                        "required_structural_role": (
                            required_role
                        ),
                        "role_possible": bool(
                            role_possible
                        ),
                    }
                )

        feasible = [
            row
            for row in raw_requirements
            if row[
                "role_possible"
            ]
        ]
        if not feasible:
            errors.append(
                f"segment_{segment_id}:"
                "no_feasible_receiving_anchor"
            )
            continue

        group_counts = {}
        for row in feasible:
            group_key = (
                row[
                    "structural_face"
                ],
                row[
                    "required_structural_role"
                ],
                row[
                    "connector_face_role"
                ],
            )
            group_counts[
                group_key
            ] = (
                group_counts.get(
                    group_key,
                    0,
                )
                + 1
            )

        coordinates = np.asarray(
            [
                row[
                    "structural_coordinate"
                ]
                for row in feasible
            ],
            dtype=float,
        )
        centroid = coordinates.mean(
            axis=0
        )

        def anchor_sort_key(row):
            group_key = (
                row[
                    "structural_face"
                ],
                row[
                    "required_structural_role"
                ],
                row[
                    "connector_face_role"
                ],
            )
            distance = float(
                np.sum(
                    (
                        np.asarray(
                            row[
                                "structural_coordinate"
                            ],
                            dtype=float,
                        )
                        - centroid
                    )
                    ** 2
                )
            )
            preferred_role = (
                1
                if (
                    prefer_structural_female
                    and row[
                        "required_structural_role"
                    ]
                    == "female"
                )
                else 0
            )
            return (
                -preferred_role,
                -int(
                    group_counts[
                        group_key
                    ]
                ),
                distance,
                str(
                    row[
                        "structural_face"
                    ]
                ),
                tuple(
                    row[
                        "structural_coordinate"
                    ]
                ),
            )

        ranked = sorted(
            feasible,
            key=anchor_sort_key,
        )

        chosen = []
        seen_face_role = set()

        # First preserve alternatives across distinct faces/roles.
        for row in ranked:
            key = (
                row[
                    "structural_face"
                ],
                row[
                    "required_structural_role"
                ],
            )
            if key in seen_face_role:
                continue
            chosen.append(
                row
            )
            seen_face_role.add(
                key
            )
            if (
                len(chosen)
                >= maximum_alternatives
            ):
                break

        # Then fill remaining slots with the best coordinates.
        if (
            len(chosen)
            < maximum_alternatives
        ):
            chosen_keys = {
                (
                    row[
                        "structural_coordinate"
                    ],
                    row[
                        "structural_face"
                    ],
                    row[
                        "required_structural_role"
                    ],
                )
                for row in chosen
            }
            for row in ranked:
                key = (
                    row[
                        "structural_coordinate"
                    ],
                    row[
                        "structural_face"
                    ],
                    row[
                        "required_structural_role"
                    ],
                )
                if key in chosen_keys:
                    continue
                chosen.append(
                    row
                )
                chosen_keys.add(
                    key
                )
                if (
                    len(chosen)
                    >= maximum_alternatives
                ):
                    break

        requirement_group_id = (
            f"{candidate['interface_id']}:"
            f"segment_{segment_id}:"
            f"side_{side_name}"
        )
        for rank, row in enumerate(
            chosen,
            start=1,
        ):
            group_key = (
                row[
                    "structural_face"
                ],
                row[
                    "required_structural_role"
                ],
                row[
                    "connector_face_role"
                ],
            )
            selected_requirements.append(
                {
                    **row,
                    "requirement_group_id": (
                        requirement_group_id
                    ),
                    "alternative_rank": int(
                        rank
                    ),
                    "raw_side_contact_count": int(
                        len(
                            raw_requirements
                        )
                    ),
                    "feasible_side_contact_count": int(
                        len(
                            feasible
                        )
                    ),
                    "face_patch_contact_count": int(
                        group_counts[
                            group_key
                        ]
                    ),
                    "selection_mode": (
                        "any_one_ranked_anchor_patch"
                    ),
                }
            )

    group_ids = {
        row[
            "requirement_group_id"
        ]
        for row in selected_requirements
    }
    valid = bool(
        len(group_ids) == 2
        and not errors
    )
    return (
        selected_requirements,
        valid,
        ";".join(
            sorted(
                set(
                    errors
                )
            )
        ),
    )


def annotate_connector_candidates_with_receiving_faces(
    candidates_df,
    segment_grid,
):
    if candidates_df.empty:
        empty_audit = pd.DataFrame(
            columns=[
                "candidate_id",
                "interface_id",
                "block_family",
                "receiving_face_requirement_count",
                "receiving_face_group_count",
                "raw_receiving_contact_count",
                "receiving_faces_feasible",
                "receiving_face_error",
            ]
        )
        return (
            candidates_df.copy(),
            empty_audit,
        )

    annotated_rows = []
    audit_rows = []

    for _, row in (
        candidates_df.iterrows()
    ):
        candidate = (
            row.to_dict()
        )
        (
            requirements,
            feasible,
            error,
        ) = (
            connector_candidate_receiving_requirements(
                candidate,
                segment_grid,
            )
        )
        group_count = len(
            {
                requirement[
                    "requirement_group_id"
                ]
                for requirement
                in requirements
            }
        )
        raw_contact_count = sum(
            int(
                requirement.get(
                    "raw_side_contact_count",
                    0,
                )
            )
            for requirement in (
                {
                    requirement[
                        "requirement_group_id"
                    ]: requirement
                    for requirement
                    in requirements
                }.values()
            )
        )

        candidate[
            "receiving_face_requirements"
        ] = requirements
        candidate[
            "receiving_face_requirement_count"
        ] = len(
            requirements
        )
        candidate[
            "receiving_face_group_count"
        ] = int(
            group_count
        )
        candidate[
            "raw_receiving_contact_count"
        ] = int(
            raw_contact_count
        )
        candidate[
            "receiving_faces_feasible"
        ] = bool(
            feasible
        )
        candidate[
            "receiving_face_error"
        ] = (
            error
            or None
        )
        annotated_rows.append(
            candidate
        )
        audit_rows.append(
            {
                "candidate_id": int(
                    candidate[
                        "candidate_id"
                    ]
                ),
                "interface_id": str(
                    candidate[
                        "interface_id"
                    ]
                ),
                "block_family": str(
                    candidate[
                        "block_family"
                    ]
                ),
                "receiving_face_requirement_count": (
                    len(
                        requirements
                    )
                ),
                "receiving_face_group_count": int(
                    group_count
                ),
                "raw_receiving_contact_count": int(
                    raw_contact_count
                ),
                "receiving_faces_feasible": bool(
                    feasible
                ),
                "receiving_face_error": (
                    error
                    or None
                ),
            }
        )

    annotated = pd.DataFrame(
        annotated_rows
    )
    audit = pd.DataFrame(
        audit_rows
    )

    if CONNECTOR_FACE_POLICY.get(
        "reject_candidate_when_receiving_face_impossible",
        True,
    ):
        annotated = annotated[
            annotated[
                "receiving_faces_feasible"
            ].astype(
                bool
            )
        ].reset_index(
            drop=True
        )

    return (
        annotated,
        audit,
    )


def explode_selected_connector_face_requirements(
    selected_connectors_df,
):
    rows = []
    if selected_connectors_df is None or selected_connectors_df.empty:
        return pd.DataFrame(), defaultdict(list)

    for _, connector in selected_connectors_df.iterrows():
        for requirement in connector.get(
            "receiving_face_requirements",
            [],
        ):
            rows.append(
                json_safe_value(requirement)
            )

    dataframe = pd.DataFrame(rows)
    mapping = defaultdict(list)
    for row in rows:
        mapping[int(row["segment_id"])].append(
            dict(row)
        )
    return dataframe, mapping


def block_contains_voxel(block, coordinate):
    return all(
        int(block.position[axis])
        <= int(coordinate[axis])
        < int(block.position[axis])
        + int(block.size[axis])
        for axis in range(3)
    )


def coordinate_is_on_block_face(
    block,
    coordinate,
    face,
):
    coordinate = tuple(
        int(value)
        for value in coordinate
    )
    origin = tuple(
        int(value)
        for value in block.position
    )
    size = tuple(
        int(value)
        for value in block.size
    )
    checks = {
        "+X": (
            coordinate[0]
            == origin[0] + size[0] - 1
        ),
        "-X": coordinate[0] == origin[0],
        "+Y": (
            coordinate[1]
            == origin[1] + size[1] - 1
        ),
        "-Y": coordinate[1] == origin[1],
        "+Z": (
            coordinate[2]
            == origin[2] + size[2] - 1
        ),
        "-Z": coordinate[2] == origin[2],
    }
    return bool(checks[face])


def evaluate_assigned_connector_face_requirements(
    current_blocks,
    assignment,
    requirements,
):
    """
    Evaluate any-of anchor alternatives for groups touched by this row.

    A group that has no coordinate in the current row remains deferred. A group
    touched by the current row is valid when at least one ranked alternative is
    compatible with the block boundary and face role.
    """
    rows = []
    group_rows = defaultdict(
        list
    )

    for requirement in (
        requirements
        or []
    ):
        group_id = str(
            requirement.get(
                "requirement_group_id",
                (
                    f"{requirement.get('interface_id')}:"
                    f"{requirement.get('segment_id')}:"
                    f"{requirement.get('interface_side')}"
                ),
            )
        )
        coordinate = tuple(
            int(
                value
            )
            for value in (
                requirement[
                    "structural_coordinate"
                ]
            )
        )
        matching_blocks = [
            block
            for block in (
                current_blocks
            )
            if block_contains_voxel(
                block,
                coordinate,
            )
        ]
        if not matching_blocks:
            continue

        block = (
            matching_blocks[
                0
            ]
        )
        block_id = int(
            block.block_id
        )
        face = requirement[
            "structural_face"
        ]
        required_role = (
            requirement[
                "required_structural_role"
            ]
        )
        boundary_match = (
            coordinate_is_on_block_face(
                block,
                coordinate,
                face,
            )
        )
        actual_role = (
            face_type_for_rotation(
                face,
                assignment[
                    block_id
                ],
                block.size,
            )
            if block_id
            in assignment
            else None
        )
        satisfied = bool(
            boundary_match
            and actual_role
            == required_role
        )
        evaluated_row = {
            **requirement,
            "requirement_group_id": (
                group_id
            ),
            "block_id": (
                block_id
            ),
            "block_family": (
                block.block_family
            ),
            "block_rotation": (
                int(
                    assignment[
                        block_id
                    ]
                )
                if block_id
                in assignment
                else None
            ),
            "boundary_match": (
                boundary_match
            ),
            "actual_structural_role": (
                actual_role
            ),
            "satisfied": (
                satisfied
            ),
        }
        rows.append(
            evaluated_row
        )
        group_rows[
            group_id
        ].append(
            evaluated_row
        )

    group_summaries = []
    for (
        group_id,
        alternatives,
    ) in sorted(
        group_rows.items()
    ):
        satisfied = any(
            bool(
                row[
                    "satisfied"
                ]
            )
            for row in alternatives
        )
        group_summaries.append(
            {
                "requirement_group_id": (
                    group_id
                ),
                "alternative_count_evaluated": (
                    len(
                        alternatives
                    )
                ),
                "satisfied": bool(
                    satisfied
                ),
            }
        )

    return {
        "rows": rows,
        "groups": (
            group_summaries
        ),
        "evaluated_count": (
            len(
                rows
            )
        ),
        "evaluated_group_count": (
            len(
                group_summaries
            )
        ),
        "satisfied_count": sum(
            bool(
                row[
                    "satisfied"
                ]
            )
            for row in (
                group_summaries
            )
        ),
        "valid": all(
            bool(
                row[
                    "satisfied"
                ]
            )
            for row in (
                group_summaries
            )
        ),
    }


def validate_connector_face_requirements_on_blocks(
    blocks,
    requirements,
):
    """
    Validate one satisfied receiving anchor per requirement group.
    """
    alternative_rows = []
    grouped_requirements = defaultdict(
        list
    )
    for requirement in (
        requirements
        or []
    ):
        group_id = str(
            requirement.get(
                "requirement_group_id",
                (
                    f"{requirement.get('interface_id')}:"
                    f"{requirement.get('segment_id')}:"
                    f"{requirement.get('interface_side')}"
                ),
            )
        )
        grouped_requirements[
            group_id
        ].append(
            requirement
        )

    group_summaries = []

    for (
        group_id,
        alternatives,
    ) in sorted(
        grouped_requirements.items()
    ):
        evaluated = []

        for requirement in sorted(
            alternatives,
            key=lambda row: int(
                row.get(
                    "alternative_rank",
                    999,
                )
            ),
        ):
            coordinate = tuple(
                int(
                    value
                )
                for value in (
                    requirement[
                        "structural_coordinate"
                    ]
                )
            )
            matching_blocks = [
                block
                for block in blocks
                if block_contains_voxel(
                    block,
                    coordinate,
                )
            ]
            if not matching_blocks:
                evaluated.append(
                    {
                        **requirement,
                        "requirement_group_id": (
                            group_id
                        ),
                        "block_id": None,
                        "block_family": None,
                        "block_rotation": None,
                        "boundary_match": False,
                        "actual_structural_role": None,
                        "alternative_satisfied": False,
                        "failure_reason": (
                            "contact_coordinate_not_covered"
                        ),
                    }
                )
                continue

            block = (
                matching_blocks[
                    0
                ]
            )
            face = requirement[
                "structural_face"
            ]
            required_role = (
                requirement[
                    "required_structural_role"
                ]
            )
            boundary_match = (
                coordinate_is_on_block_face(
                    block,
                    coordinate,
                    face,
                )
            )
            actual_role = (
                actual_block_face_type(
                    block,
                    face,
                )
            )
            satisfied = bool(
                boundary_match
                and actual_role
                == required_role
            )
            evaluated.append(
                {
                    **requirement,
                    "requirement_group_id": (
                        group_id
                    ),
                    "block_id": int(
                        block.block_id
                    ),
                    "block_family": (
                        block.block_family
                    ),
                    "block_rotation": int(
                        getattr(
                            block,
                            "rotation",
                            0,
                        )
                    ),
                    "boundary_match": (
                        boundary_match
                    ),
                    "actual_structural_role": (
                        actual_role
                    ),
                    "alternative_satisfied": (
                        satisfied
                    ),
                    "failure_reason": (
                        None
                        if satisfied
                        else (
                            "contact_coordinate_not_on_block_face"
                            if not boundary_match
                            else "wrong_face_role"
                        )
                    ),
                }
            )

        selected_index = next(
            (
                index
                for index, row in enumerate(
                    evaluated
                )
                if row[
                    "alternative_satisfied"
                ]
            ),
            None,
        )
        group_satisfied = (
            selected_index
            is not None
        )

        for index, row in enumerate(
            evaluated
        ):
            row[
                "selected_for_group"
            ] = bool(
                group_satisfied
                and index
                == selected_index
            )
            # Only the selected alternative counts as a satisfied requirement
            # in downstream summary totals.
            row[
                "satisfied"
            ] = bool(
                row[
                    "selected_for_group"
                ]
            )
            row[
                "group_satisfied"
            ] = bool(
                group_satisfied
            )
            alternative_rows.append(
                row
            )

        group_summaries.append(
            {
                "requirement_group_id": (
                    group_id
                ),
                "alternative_count": int(
                    len(
                        alternatives
                    )
                ),
                "satisfied": bool(
                    group_satisfied
                ),
                "selected_alternative_rank": (
                    int(
                        evaluated[
                            selected_index
                        ].get(
                            "alternative_rank",
                            selected_index
                            + 1,
                        )
                    )
                    if group_satisfied
                    else None
                ),
            }
        )

    total_groups = len(
        group_summaries
    )
    satisfied_groups = sum(
        bool(
            row[
                "satisfied"
            ]
        )
        for row in (
            group_summaries
        )
    )
    ratio = (
        satisfied_groups
        / total_groups
        if total_groups
        else 1.0
    )
    minimum_ratio = float(
        CONNECTOR_FACE_POLICY.get(
            "minimum_receiving_face_satisfaction_ratio",
            1.0,
        )
    )

    return {
        "rows": (
            alternative_rows
        ),
        "groups": (
            group_summaries
        ),
        "total": int(
            total_groups
        ),
        "alternative_total": int(
            len(
                alternative_rows
            )
        ),
        "satisfied_count": int(
            satisfied_groups
        ),
        "satisfaction_ratio": float(
            ratio
        ),
        "valid": bool(
            ratio
            >= minimum_ratio
            and (
                total_groups > 0
                or not requirements
            )
        ),
    }


def mirror_connector_face_requirements(
    requirements,
    partner_segment_id,
    center_plane,
):
    mirrored = []
    for requirement in requirements or []:
        structural_coordinate = list(
            requirement["structural_coordinate"]
        )
        connector_coordinate = list(
            requirement["connector_coordinate"]
        )
        structural_coordinate[
            SYMMETRY_AXIS_INDEX
        ] = mirror_index_coordinate(
            structural_coordinate[
                SYMMETRY_AXIS_INDEX
            ],
            center_plane,
        )
        connector_coordinate[
            SYMMETRY_AXIS_INDEX
        ] = mirror_index_coordinate(
            connector_coordinate[
                SYMMETRY_AXIS_INDEX
            ],
            center_plane,
        )
        mirrored_requirement = dict(requirement)
        mirrored_requirement["segment_id"] = int(
            partner_segment_id
        )
        original_group_id = str(
            mirrored_requirement.get(
                "requirement_group_id",
                "",
            )
        )
        if original_group_id:
            mirrored_requirement[
                "requirement_group_id"
            ] = (
                f"{mirrored_requirement.get('interface_id')}:"
                f"segment_{int(partner_segment_id)}:"
                f"side_{mirrored_requirement.get('interface_side')}"
            )
        mirrored_requirement[
            "structural_coordinate"
        ] = tuple(
            int(value)
            for value in structural_coordinate
        )
        mirrored_requirement[
            "connector_coordinate"
        ] = tuple(
            int(value)
            for value in connector_coordinate
        )
        mirrored_requirement[
            "structural_face"
        ] = mirror_face_name(
            requirement["structural_face"],
            SYMMETRY_AXIS_INDEX,
        )
        mirrored_requirement[
            "connector_face"
        ] = mirror_face_name(
            requirement["connector_face"],
            SYMMETRY_AXIS_INDEX,
        )
        mirrored.append(mirrored_requirement)
    return mirrored


def reserved_face_interactive_figure(
    segment_grid,
    requirements_df,
):
    figure = go.Figure()
    source_coordinates = np.argwhere(
        segment_grid > 0
    )
    figure.add_trace(
        go.Scatter3d(
            x=source_coordinates[:, 0] + 0.5,
            y=source_coordinates[:, 1] + 0.5,
            z=source_coordinates[:, 2] + 0.5,
            mode="markers",
            marker={
                "size": 3,
                "color": "lightgray",
                "opacity": 0.08,
                "symbol": "square",
            },
            name="Source structure",
            hoverinfo="name",
        )
    )

    if (
        requirements_df is not None
        and not requirements_df.empty
    ):
        for role, color in [
            ("female", "dodgerblue"),
            ("male", "red"),
        ]:
            subset = requirements_df[
                requirements_df[
                    "required_structural_role"
                ] == role
            ]
            if subset.empty:
                continue
            coordinates = np.asarray(
                subset[
                    "structural_coordinate"
                ].tolist(),
                dtype=float,
            )
            figure.add_trace(
                go.Scatter3d(
                    x=coordinates[:, 0] + 0.5,
                    y=coordinates[:, 1] + 0.5,
                    z=coordinates[:, 2] + 0.5,
                    mode="markers",
                    marker={
                        "size": 8,
                        "color": color,
                        "symbol": (
                            "circle-open"
                            if role == "female"
                            else "circle"
                        ),
                        "line": {
                            "color": "black",
                            "width": 1,
                        },
                    },
                    text=[
                        (
                            f"Interface: {row.interface_id}<br>"
                            f"Segment: {row.segment_id}<br>"
                            f"Face: {row.structural_face}<br>"
                            f"Required: {role}"
                        )
                        for row in subset.itertuples(
                            index=False
                        )
                    ],
                    hoverinfo="text",
                    name=(
                        f"Required structural {role} face"
                    ),
                )
            )

    figure.update_layout(
        **figure_layout(
            "Reserved Connector Receiving Faces"
        )
    )
    return figure


# ------------------------------------------------------------------
# Reservation selective interface reservation policy
# ------------------------------------------------------------------

class InterfaceReservationStrategy(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    NONE = "none"


INTERFACE_RESERVATION_CONFIG = TASK_CONTEXT.get(
    "interface_reservations",
    {},
)


def reservation_normalize_strategy(value, default="soft"):
    text = str(value or default).strip().lower()
    if text not in {"hard", "soft", "none"}:
        raise ValueError(f"Unsupported Reservation reservation strategy: {value}")
    return text


def reservation_normalize_connection_type(value):
    return str(value or "unknown").strip().lower()


def reservation_rule_matches(rule, scope, record):
    if str(rule.get("scope", "")).strip().lower() != str(scope).lower():
        return False

    if bool(rule.get("required_only", False)) and not bool(record.get("required", False)):
        return False

    exact_fields = [
        "interface_id",
        "attachment_id",
        "physical_target_id",
        "required_block_family",
    ]
    for field in exact_fields:
        if field not in rule:
            continue
        if str(record.get(field, "")) != str(rule.get(field, "")):
            return False

    if rule.get("connection_types"):
        allowed = {
            reservation_normalize_connection_type(value)
            for value in rule.get("connection_types", [])
        }
        if reservation_normalize_connection_type(record.get("connection_type")) not in allowed:
            return False

    if rule.get("segment_labels"):
        required_labels = {
            str(value).strip().lower()
            for value in rule.get("segment_labels", [])
        }
        actual_labels = {
            str(record.get("segment_a_label", "")).strip().lower(),
            str(record.get("segment_b_label", "")).strip().lower(),
        }
        if required_labels != actual_labels:
            return False

    return True


def reservation_explicit_strategy(scope, record):
    for rule in INTERFACE_RESERVATION_CONFIG.get(
        "explicit_requirements",
        [],
    ):
        if reservation_rule_matches(rule, scope, record):
            return {
                "reservation_strategy": reservation_normalize_strategy(
                    rule.get("reservation_strategy")
                ),
                "strategy_reason_code": str(
                    rule.get("rule_id", "explicit_task_context_rule")
                ),
                "strategy_reason": str(
                    rule.get("reason", "Explicit task-context reservation rule.")
                ),
                "decision_source": "task_context_explicit_rule",
            }
    return None


def reservation_structural_interface_decision(interface_row, llm2_decision=None):
    row = interface_row.to_dict() if hasattr(interface_row, "to_dict") else dict(interface_row)
    decision = dict(llm2_decision or {})
    connection_type = reservation_normalize_connection_type(
        decision.get(
            "connection_type",
            row.get("connection_type", "rigid"),
        )
    )
    record = {
        **row,
        **decision,
        "connection_type": connection_type,
        "required": True,
    }

    explicit = reservation_explicit_strategy("structural_interface", record)
    if explicit:
        return {**record, **explicit}

    hard_types = {
        reservation_normalize_connection_type(value)
        for value in INTERFACE_RESERVATION_CONFIG.get(
            "hard_connection_types", []
        )
    }
    soft_types = {
        reservation_normalize_connection_type(value)
        for value in INTERFACE_RESERVATION_CONFIG.get(
            "soft_connection_types", []
        )
    }
    none_types = {
        reservation_normalize_connection_type(value)
        for value in INTERFACE_RESERVATION_CONFIG.get(
            "none_connection_types", []
        )
    }

    if connection_type in none_types:
        strategy = "none"
        code = "no_physical_connection"
        reason = "The classified relationship does not require a physical connection."
    elif connection_type in hard_types:
        strategy = "hard"
        code = "motion_or_exact_structural_interface"
        reason = "Motion or exact connector semantics require a preserved receiving face."
    elif connection_type in soft_types:
        strategy = "soft"
        code = "ordinary_rigid_structural_interface"
        reason = "The join should remain connectable, but no single exact face is mandatory."
    else:
        strategy = reservation_normalize_strategy(
            INTERFACE_RESERVATION_CONFIG.get(
                "default_structural_interface_strategy",
                "soft",
            )
        )
        code = "default_structural_interface_strategy"
        reason = "No exact docking requirement was declared; use the configured structural default."

    return {
        **record,
        "reservation_strategy": strategy,
        "strategy_reason_code": code,
        "strategy_reason": reason,
        "decision_source": "reservation_derived_policy",
    }


def reservation_functional_target_decision(target_row, declaration):
    target = target_row.to_dict() if hasattr(target_row, "to_dict") else dict(target_row)
    declaration = dict(declaration or {})
    connection_type = reservation_normalize_connection_type(
        declaration.get(
            "motion_type",
            target.get("connection_type", "functional_attachment"),
        )
    )
    record = {
        **target,
        **declaration,
        "connection_type": connection_type,
        "required": bool(declaration.get("required", False)),
        "required_block_family": declaration.get("required_block_family"),
    }

    explicit = reservation_explicit_strategy("functional_attachment", record)
    if explicit:
        return {**record, **explicit}

    hard_types = {
        reservation_normalize_connection_type(value)
        for value in INTERFACE_RESERVATION_CONFIG.get(
            "hard_connection_types", []
        )
    }
    required = bool(record.get("required", False))
    exact_family = bool(record.get("required_block_family"))

    if required or exact_family or connection_type in hard_types:
        strategy = reservation_normalize_strategy(
            INTERFACE_RESERVATION_CONFIG.get(
                "default_required_functional_strategy",
                "hard",
            )
        )
        code = "required_functional_or_exact_family"
        reason = "A required functional target or exact family needs a validated receiving anchor."
    else:
        strategy = reservation_normalize_strategy(
            INTERFACE_RESERVATION_CONFIG.get(
                "default_optional_functional_strategy",
                "soft",
            )
        )
        code = "optional_functional_target"
        reason = "The optional functional target may guide packing without blocking feasibility."

    return {
        **record,
        "reservation_strategy": strategy,
        "strategy_reason_code": code,
        "strategy_reason": reason,
        "decision_source": "reservation_derived_policy",
    }


def reservation_rank_anchor_rows(rows, maximum_alternatives):
    if not rows:
        return []
    coordinates = np.asarray(
        [row["structural_coordinate"] for row in rows],
        dtype=float,
    )
    centroid = coordinates.mean(axis=0)

    ranked = sorted(
        rows,
        key=lambda row: (
            float(
                np.sum(
                    (
                        np.asarray(row["structural_coordinate"], dtype=float)
                        - centroid
                    ) ** 2
                )
            ),
            str(row.get("structural_face", "")),
            str(row.get("required_structural_role", "")),
            tuple(row.get("structural_coordinate", ())),
        ),
    )

    selected = []
    seen = set()
    for row in ranked:
        key = (
            tuple(row["structural_coordinate"]),
            row["structural_face"],
            row["required_structural_role"],
        )
        if key in seen:
            continue
        seen.add(key)
        selected.append(row)
        if len(selected) >= maximum_alternatives:
            break
    return selected


def reservation_direct_join_requirements(
    required_interfaces_df,
    structural_interface_payload,
    llm2_decision_by_interface,
):
    requirement_rows = []
    decision_rows = []
    maximum = max(
        1,
        int(
            INTERFACE_RESERVATION_CONFIG.get(
                "maximum_anchor_alternatives_per_group",
                8,
            )
        ),
    )

    if required_interfaces_df is None or required_interfaces_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    for _, interface in required_interfaces_df.iterrows():
        interface_id = str(interface["interface_id"])
        decision = reservation_structural_interface_decision(
            interface,
            llm2_decision_by_interface.get(interface_id),
        )
        decision_rows.append({
            "reservation_scope": "structural_interface",
            **decision,
        })
        strategy = decision["reservation_strategy"]
        if strategy == "none":
            continue

        payload = structural_interface_payload.get(interface_id, {})
        normal_a_to_b = str(interface.get("normal_a_to_b"))
        side_specs = [
            (
                "a",
                int(interface["segment_a"]),
                payload.get("a_coordinates", []),
                normal_a_to_b,
            ),
            (
                "b",
                int(interface["segment_b"]),
                payload.get("b_coordinates", []),
                OPPOSITE_FACE[normal_a_to_b],
            ),
        ]

        for side_name, segment_id, coordinates, structural_face in side_specs:
            candidate_rows = []
            possible_roles = [
                role
                for role in ("female", "male")
                if structural_face_role_possible(structural_face, role)
            ]
            if not possible_roles:
                possible_roles = ["any"]

            for coordinate in coordinates:
                structural_coordinate = tuple(int(value) for value in coordinate)
                for required_role in possible_roles:
                    candidate_rows.append({
                        "reservation_owner_id": interface_id,
                        "reservation_scope": "structural_interface",
                        "reservation_strategy": strategy,
                        "strategy_reason_code": decision["strategy_reason_code"],
                        "strategy_reason": decision["strategy_reason"],
                        "interface_id": interface_id,
                        "segment_id": segment_id,
                        "interface_side": side_name,
                        "structural_coordinate": structural_coordinate,
                        "connector_coordinate": None,
                        "structural_face": structural_face,
                        "connector_face": OPPOSITE_FACE[structural_face],
                        "connector_face_role": "direct_structural_join",
                        "required_structural_role": required_role,
                        "role_possible": True,
                        "selection_mode": "any_ranked_source_interface_patch",
                    })

            group_id = f"reservation:{interface_id}:segment_{segment_id}:side_{side_name}"
            for rank, row in enumerate(
                reservation_rank_anchor_rows(candidate_rows, maximum),
                start=1,
            ):
                requirement_rows.append({
                    **row,
                    "requirement_group_id": group_id,
                    "alternative_rank": rank,
                })

    return pd.DataFrame(requirement_rows), pd.DataFrame(decision_rows)


def reservation_functional_candidate_receiving_requirements(
    candidate,
    segment_grid,
    reservation_strategy,
):
    if reservation_strategy == "none":
        return [], True, None

    anchor_segment_id = int(candidate["anchor_segment_id"])
    anchor_coordinates = {
        tuple(int(value) for value in coordinate)
        for coordinate in np.argwhere(segment_grid == anchor_segment_id)
    }
    geometry_coordinates = {
        tuple(int(value) for value in coordinate)
        for coordinate in candidate.get("geometry_coordinates", [])
    }
    face_roles = candidate.get("face_roles", {}) or {}
    inverse_face = {
        tuple(int(value) for value in delta): face
        for face, delta in FACE_TO_VECTOR.items()
    }

    contact_rows = []
    for connector_coordinate in geometry_coordinates:
        for delta, structural_face in inverse_face.items():
            structural_coordinate = tuple(
                connector_coordinate[axis] - delta[axis]
                for axis in range(3)
            )
            if structural_coordinate not in anchor_coordinates:
                continue
            connector_face = OPPOSITE_FACE[structural_face]
            connector_role = str(face_roles.get(connector_face, "none"))
            required_role = opposite_contact_role(connector_role)
            if required_role is None and INTERFACE_RESERVATION_CONFIG.get(
                "allow_boundary_only_requirement_when_catalog_role_is_unknown",
                True,
            ):
                required_role = "any"
            if required_role is None:
                continue
            role_possible = bool(
                required_role == "any"
                or structural_face_role_possible(structural_face, required_role)
            )
            if not role_possible:
                continue
            contact_rows.append({
                "reservation_owner_id": str(candidate.get("physical_target_id")),
                "reservation_scope": "functional_attachment",
                "reservation_strategy": reservation_strategy,
                "physical_target_id": str(candidate.get("physical_target_id")),
                "attachment_id": str(candidate.get("attachment_id")),
                "candidate_id": int(candidate.get("candidate_id")),
                "block_family": str(candidate.get("block_family")),
                "segment_id": anchor_segment_id,
                "interface_side": "anchor",
                "structural_coordinate": structural_coordinate,
                "connector_coordinate": connector_coordinate,
                "structural_face": structural_face,
                "connector_face": connector_face,
                "connector_face_role": connector_role,
                "required_structural_role": required_role,
                "role_possible": role_possible,
                "selection_mode": "any_ranked_functional_anchor_patch",
            })

    maximum = max(
        1,
        int(
            INTERFACE_RESERVATION_CONFIG.get(
                "maximum_anchor_alternatives_per_group",
                8,
            )
        ),
    )
    chosen = reservation_rank_anchor_rows(contact_rows, maximum)
    group_id = (
        f"reservation:functional:{candidate.get('physical_target_id')}:"
        f"segment_{anchor_segment_id}"
    )
    requirements = [
        {
            **row,
            "requirement_group_id": group_id,
            "alternative_rank": rank,
        }
        for rank, row in enumerate(chosen, start=1)
    ]
    feasible = bool(requirements)
    error = None if feasible else "no_feasible_functional_receiving_anchor"
    return requirements, feasible, error


def reservation_annotate_connector_candidates_with_reservations(
    candidates_df,
    segment_grid,
    interfaces_df,
    llm2_decision_rows,
):
    annotated, base_audit = annotate_connector_candidates_with_receiving_faces(
        candidates_df,
        segment_grid,
    )
    if annotated is None or annotated.empty:
        return annotated.copy(), base_audit.copy()

    interface_lookup = {
        str(row.interface_id): row._asdict()
        for row in interfaces_df.itertuples(index=False)
    }
    decision_lookup = {
        str(row.get("interface_id")): row
        for row in (llm2_decision_rows or [])
        if row.get("interface_id") is not None
    }

    rows = []
    audit_rows = []
    soft_penalty = float(
        INTERFACE_RESERVATION_CONFIG.get(
            "soft_unsatisfied_candidate_penalty",
            250,
        )
    )
    for _, candidate_row in annotated.iterrows():
        candidate = candidate_row.to_dict()
        interface_id = str(candidate.get("interface_id"))
        interface_record = interface_lookup.get(interface_id, {"interface_id": interface_id})
        decision = reservation_structural_interface_decision(
            interface_record,
            decision_lookup.get(interface_id),
        )
        strategy = decision["reservation_strategy"]
        feasible = bool(candidate.get("receiving_faces_feasible", False))
        requirements = candidate.get("receiving_face_requirements", []) or []
        for requirement in requirements:
            requirement["reservation_strategy"] = strategy
            requirement["reservation_scope"] = "structural_connector"
            requirement["reservation_owner_id"] = interface_id
            requirement["strategy_reason_code"] = decision["strategy_reason_code"]
            requirement["strategy_reason"] = decision["strategy_reason"]

        hard_valid = bool(strategy != "hard" or feasible)
        penalty = soft_penalty if strategy == "soft" and not feasible else 0.0
        original_score = float(candidate.get("score", 0.0))
        candidate.update({
            "reservation_strategy": strategy,
            "strategy_reason_code": decision["strategy_reason_code"],
            "strategy_reason": decision["strategy_reason"],
            "reservation_hard_valid": hard_valid,
            "reservation_soft_penalty": penalty,
            "score_before_reservation": original_score,
            "score": original_score - penalty,
            "receiving_face_requirements": requirements if strategy != "none" else [],
        })
        rows.append(candidate)
        audit_rows.append({
            "candidate_id": candidate.get("candidate_id"),
            "interface_id": interface_id,
            "block_family": candidate.get("block_family"),
            "reservation_strategy": strategy,
            "receiving_faces_feasible": feasible,
            "reservation_hard_valid": hard_valid,
            "reservation_soft_penalty": penalty,
            "score_before_reservation": original_score,
            "reservation_adjusted_score": original_score - penalty,
            "strategy_reason_code": decision["strategy_reason_code"],
            "geometry_coordinates": candidate.get("geometry_coordinates", []),
        })

    result = pd.DataFrame(rows)
    if INTERFACE_RESERVATION_CONFIG.get(
        "reject_hard_candidate_when_no_receiving_anchor",
        True,
    ):
        result = result[result["reservation_hard_valid"].astype(bool)].reset_index(drop=True)
    return result, pd.DataFrame(audit_rows)


def reservation_annotate_functional_candidates_with_reservations(
    candidates_df,
    segment_grid,
    physical_targets_df,
):
    if candidates_df is None or candidates_df.empty:
        return candidates_df.copy(), pd.DataFrame()

    declaration_by_id = {
        str(declaration["attachment_id"]): declaration
        for declaration in attachment_declarations()
    }
    target_lookup = {
        str(row.physical_target_id): row._asdict()
        for row in physical_targets_df.itertuples(index=False)
    }
    rows = []
    audit_rows = []
    soft_penalty = float(
        INTERFACE_RESERVATION_CONFIG.get(
            "soft_unsatisfied_candidate_penalty",
            250,
        )
    )

    for _, candidate_row in candidates_df.iterrows():
        candidate = candidate_row.to_dict()
        attachment_id = str(candidate.get("attachment_id"))
        physical_target_id = str(candidate.get("physical_target_id"))
        target = target_lookup.get(physical_target_id, {
            "physical_target_id": physical_target_id,
            "attachment_id": attachment_id,
        })
        decision = reservation_functional_target_decision(
            target,
            declaration_by_id.get(attachment_id, {}),
        )
        strategy = decision["reservation_strategy"]
        requirements, feasible, error = reservation_functional_candidate_receiving_requirements(
            candidate,
            segment_grid,
            strategy,
        )
        for requirement in requirements:
            requirement["strategy_reason_code"] = decision["strategy_reason_code"]
            requirement["strategy_reason"] = decision["strategy_reason"]

        hard_valid = bool(strategy != "hard" or feasible)
        penalty = soft_penalty if strategy == "soft" and not feasible else 0.0
        original_score = float(candidate.get("score", 0.0))
        candidate.update({
            "reservation_strategy": strategy,
            "strategy_reason_code": decision["strategy_reason_code"],
            "strategy_reason": decision["strategy_reason"],
            "reservation_hard_valid": hard_valid,
            "reservation_soft_penalty": penalty,
            "score_before_reservation": original_score,
            "score": original_score - penalty,
            "receiving_face_requirements": requirements,
            "receiving_faces_feasible": feasible,
            "receiving_face_error": error,
        })
        rows.append(candidate)
        audit_rows.append({
            "candidate_id": candidate.get("candidate_id"),
            "attachment_id": attachment_id,
            "physical_target_id": physical_target_id,
            "anchor_segment_id": candidate.get("anchor_segment_id"),
            "block_family": candidate.get("block_family"),
            "reservation_strategy": strategy,
            "receiving_faces_feasible": feasible,
            "reservation_hard_valid": hard_valid,
            "reservation_soft_penalty": penalty,
            "score_before_reservation": original_score,
            "reservation_adjusted_score": original_score - penalty,
            "strategy_reason_code": decision["strategy_reason_code"],
            "receiving_face_error": error,
            "geometry_coordinates": candidate.get("geometry_coordinates", []),
        })

    result = pd.DataFrame(rows)
    if INTERFACE_RESERVATION_CONFIG.get(
        "reject_hard_candidate_when_no_receiving_anchor",
        True,
    ):
        result = result[result["reservation_hard_valid"].astype(bool)].reset_index(drop=True)
    return result, pd.DataFrame(audit_rows)


def reservation_selected_functional_requirements(
    selected_functional_df,
    segment_grid,
    physical_targets_df,
):
    if selected_functional_df is None or selected_functional_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    declaration_by_id = {
        str(declaration["attachment_id"]): declaration
        for declaration in attachment_declarations()
    }
    target_lookup = {
        str(row.physical_target_id): row._asdict()
        for row in physical_targets_df.itertuples(index=False)
    }
    requirements = []
    decisions = []
    for _, selected_row in selected_functional_df.iterrows():
        candidate = selected_row.to_dict()
        attachment_id = str(candidate.get("attachment_id"))
        target_id = str(candidate.get("physical_target_id"))
        decision = reservation_functional_target_decision(
            target_lookup.get(target_id, {
                "physical_target_id": target_id,
                "attachment_id": attachment_id,
            }),
            declaration_by_id.get(attachment_id, {}),
        )
        decisions.append({
            "reservation_scope": "functional_attachment",
            **decision,
        })
        candidate_requirements, feasible, error = (
            reservation_functional_candidate_receiving_requirements(
                candidate,
                segment_grid,
                decision["reservation_strategy"],
            )
        )
        for requirement in candidate_requirements:
            requirement["strategy_reason_code"] = decision["strategy_reason_code"]
            requirement["strategy_reason"] = decision["strategy_reason"]
            requirements.append(requirement)
        if not feasible and decision["reservation_strategy"] == "hard":
            decisions[-1]["hard_requirement_generation_error"] = error

    return pd.DataFrame(requirements), pd.DataFrame(decisions)


def reservation_requirement_mapping(requirements_df):
    mapping = defaultdict(list)
    if requirements_df is None or requirements_df.empty:
        return mapping
    for row in requirements_df.to_dict(orient="records"):
        if reservation_normalize_strategy(row.get("reservation_strategy", "hard")) == "none":
            continue
        mapping[int(row["segment_id"])].append(row)
    return mapping


def reservation_reservation_conflicts(requirements_df):
    if requirements_df is None or requirements_df.empty:
        return pd.DataFrame()
    hard = requirements_df[
        requirements_df["reservation_strategy"].astype(str).str.lower().eq("hard")
    ].copy()
    rows = []
    grouped = hard.groupby(
        ["segment_id", "structural_coordinate", "structural_face"],
        dropna=False,
    )
    for key, group in grouped:
        group_ids = set(group["requirement_group_id"].astype(str))
        roles = set(group["required_structural_role"].astype(str)) - {"any"}
        if len(group_ids) > 1 and len(roles) > 1:
            rows.append({
                "segment_id": key[0],
                "structural_coordinate": key[1],
                "structural_face": key[2],
                "requirement_group_ids": json.dumps(sorted(group_ids)),
                "required_roles": json.dumps(sorted(roles)),
                "severity": "fatal",
                "reason": "Distinct hard groups require incompatible roles on the same face patch.",
            })
    return pd.DataFrame(rows)


# ------------------------------------------------------------------
# Override the previous all-or-nothing requirement evaluators.
# ------------------------------------------------------------------

def evaluate_assigned_connector_face_requirements(
    current_blocks,
    assignment,
    requirements,
):
    rows = []
    group_rows = defaultdict(list)

    for requirement in requirements or []:
        strategy = reservation_normalize_strategy(
            requirement.get(
                "reservation_strategy",
                INTERFACE_RESERVATION_CONFIG.get(
                    "unspecified_requirement_default_strategy",
                    "hard",
                ),
            )
        )
        if strategy == "none":
            continue
        group_id = str(
            requirement.get(
                "requirement_group_id",
                f"{requirement.get('interface_id')}:{requirement.get('segment_id')}:{requirement.get('interface_side')}",
            )
        )
        coordinate = tuple(int(value) for value in requirement["structural_coordinate"])
        matching_blocks = [
            block
            for block in current_blocks
            if block_contains_voxel(block, coordinate)
        ]
        if not matching_blocks:
            continue

        block = matching_blocks[0]
        block_id = int(block.block_id)
        face = requirement["structural_face"]
        required_role = requirement.get("required_structural_role", "any")
        boundary_match = coordinate_is_on_block_face(block, coordinate, face)
        actual_role = (
            face_type_for_rotation(face, assignment[block_id], block.size)
            if block_id in assignment
            else None
        )
        role_match = bool(required_role == "any" or actual_role == required_role)
        satisfied = bool(boundary_match and role_match)
        evaluated_row = {
            **requirement,
            "reservation_strategy": strategy,
            "requirement_group_id": group_id,
            "block_id": block_id,
            "block_family": block.block_family,
            "block_rotation": int(assignment[block_id]) if block_id in assignment else None,
            "boundary_match": boundary_match,
            "actual_structural_role": actual_role,
            "alternative_satisfied": satisfied,
            "satisfied": satisfied,
        }
        rows.append(evaluated_row)
        group_rows[group_id].append(evaluated_row)

    group_summaries = []
    for group_id, alternatives in sorted(group_rows.items()):
        strategy = reservation_normalize_strategy(
            alternatives[0].get("reservation_strategy", "hard")
        )
        satisfied = any(bool(row["satisfied"]) for row in alternatives)
        group_summaries.append({
            "requirement_group_id": group_id,
            "reservation_strategy": strategy,
            "alternative_count_evaluated": len(alternatives),
            "satisfied": bool(satisfied),
        })

    hard_groups = [row for row in group_summaries if row["reservation_strategy"] == "hard"]
    soft_groups = [row for row in group_summaries if row["reservation_strategy"] == "soft"]
    return {
        "rows": rows,
        "groups": group_summaries,
        "evaluated_count": len(rows),
        "evaluated_group_count": len(group_summaries),
        "satisfied_count": sum(bool(row["satisfied"]) for row in group_summaries),
        "hard_group_count": len(hard_groups),
        "hard_satisfied_count": sum(bool(row["satisfied"]) for row in hard_groups),
        "soft_group_count": len(soft_groups),
        "soft_satisfied_count": sum(bool(row["satisfied"]) for row in soft_groups),
        "valid": all(bool(row["satisfied"]) for row in hard_groups),
    }


def validate_connector_face_requirements_on_blocks(
    blocks,
    requirements,
):
    alternative_rows = []
    grouped_requirements = defaultdict(list)
    for requirement in requirements or []:
        strategy = reservation_normalize_strategy(
            requirement.get(
                "reservation_strategy",
                INTERFACE_RESERVATION_CONFIG.get(
                    "unspecified_requirement_default_strategy",
                    "hard",
                ),
            )
        )
        if strategy == "none":
            continue
        group_id = str(
            requirement.get(
                "requirement_group_id",
                f"{requirement.get('interface_id')}:{requirement.get('segment_id')}:{requirement.get('interface_side')}",
            )
        )
        grouped_requirements[group_id].append({
            **requirement,
            "reservation_strategy": strategy,
        })

    group_summaries = []
    for group_id, alternatives in sorted(grouped_requirements.items()):
        evaluated = []
        strategy = reservation_normalize_strategy(
            alternatives[0].get("reservation_strategy", "hard")
        )
        for requirement in sorted(
            alternatives,
            key=lambda row: int(row.get("alternative_rank", 999)),
        ):
            coordinate = tuple(int(value) for value in requirement["structural_coordinate"])
            matching_blocks = [
                block for block in blocks
                if block_contains_voxel(block, coordinate)
            ]
            if not matching_blocks:
                evaluated.append({
                    **requirement,
                    "requirement_group_id": group_id,
                    "block_id": None,
                    "block_family": None,
                    "block_rotation": None,
                    "boundary_match": False,
                    "actual_structural_role": None,
                    "alternative_satisfied": False,
                    "failure_reason": "contact_coordinate_not_covered",
                })
                continue

            block = matching_blocks[0]
            face = requirement["structural_face"]
            required_role = requirement.get("required_structural_role", "any")
            boundary_match = coordinate_is_on_block_face(block, coordinate, face)
            actual_role = actual_block_face_type(block, face)
            role_match = bool(required_role == "any" or actual_role == required_role)
            satisfied = bool(boundary_match and role_match)
            evaluated.append({
                **requirement,
                "requirement_group_id": group_id,
                "block_id": int(block.block_id),
                "block_family": block.block_family,
                "block_rotation": int(getattr(block, "rotation", 0)),
                "boundary_match": boundary_match,
                "actual_structural_role": actual_role,
                "alternative_satisfied": satisfied,
                "failure_reason": (
                    None if satisfied
                    else "contact_coordinate_not_on_block_face" if not boundary_match
                    else "wrong_face_role"
                ),
            })

        selected_index = next(
            (index for index, row in enumerate(evaluated) if row["alternative_satisfied"]),
            None,
        )
        group_satisfied = selected_index is not None
        for index, row in enumerate(evaluated):
            row["selected_for_group"] = bool(group_satisfied and index == selected_index)
            row["satisfied"] = bool(row["selected_for_group"])
            row["group_satisfied"] = bool(group_satisfied)
            alternative_rows.append(row)

        group_summaries.append({
            "requirement_group_id": group_id,
            "reservation_strategy": strategy,
            "alternative_count": len(alternatives),
            "satisfied": bool(group_satisfied),
            "selected_alternative_rank": (
                int(evaluated[selected_index].get("alternative_rank", selected_index + 1))
                if group_satisfied else None
            ),
        })

    hard_groups = [row for row in group_summaries if row["reservation_strategy"] == "hard"]
    soft_groups = [row for row in group_summaries if row["reservation_strategy"] == "soft"]
    total_groups = len(group_summaries)
    satisfied_groups = sum(bool(row["satisfied"]) for row in group_summaries)
    hard_satisfied = sum(bool(row["satisfied"]) for row in hard_groups)
    soft_satisfied = sum(bool(row["satisfied"]) for row in soft_groups)

    return {
        "rows": alternative_rows,
        "groups": group_summaries,
        "total": total_groups,
        "alternative_total": len(alternative_rows),
        "satisfied_count": satisfied_groups,
        "satisfaction_ratio": satisfied_groups / total_groups if total_groups else 1.0,
        "hard_total": len(hard_groups),
        "hard_satisfied_count": hard_satisfied,
        "hard_satisfaction_ratio": hard_satisfied / len(hard_groups) if hard_groups else 1.0,
        "soft_total": len(soft_groups),
        "soft_satisfied_count": soft_satisfied,
        "soft_satisfaction_ratio": soft_satisfied / len(soft_groups) if soft_groups else 1.0,
        "valid": bool(all(bool(row["satisfied"]) for row in hard_groups)),
    }


def reservation_final_reservation_audit(segment_results, requirements_df):
    if requirements_df is None or requirements_df.empty:
        return pd.DataFrame(columns=[
            "requirement_group_id", "reservation_strategy", "segment_id",
            "reservation_owner_id", "satisfied", "status",
        ])

    evaluation_rows = [
        row
        for result in segment_results
        for row in result.get("connector_face_requirement_audit", [])
    ]
    evaluation_by_group = defaultdict(list)
    for row in evaluation_rows:
        evaluation_by_group[str(row.get("requirement_group_id"))].append(row)

    audit_rows = []
    for group_id, group in requirements_df.groupby("requirement_group_id", sort=True):
        strategy = reservation_normalize_strategy(group.iloc[0].get("reservation_strategy", "hard"))
        evaluated = evaluation_by_group.get(str(group_id), [])
        satisfied = any(
            bool(row.get("group_satisfied", row.get("alternative_satisfied", row.get("satisfied", False))))
            for row in evaluated
        )
        status = (
            "fulfilled" if satisfied
            else "unresolved_required" if strategy == "hard"
            else "needs_review" if strategy == "soft"
            else "not_required"
        )
        audit_rows.append({
            "requirement_group_id": str(group_id),
            "reservation_strategy": strategy,
            "reservation_scope": group.iloc[0].get("reservation_scope"),
            "reservation_owner_id": group.iloc[0].get("reservation_owner_id"),
            "segment_id": int(group.iloc[0]["segment_id"]),
            "alternative_count": int(len(group)),
            "evaluated_alternative_count": int(len(evaluated)),
            "satisfied": bool(satisfied),
            "status": status,
            "strategy_reason_code": group.iloc[0].get("strategy_reason_code"),
        })
    return pd.DataFrame(audit_rows)


def reserved_face_interactive_figure(segment_grid, requirements_df):
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



# ------------------------------------------------------------------
# Detailed build-step visualizations and final-display gate
# ------------------------------------------------------------------

import textwrap
VISUALIZATION_CONFIG.setdefault(
    "show_inline_subassembly_build_steps",
    True,
)
VISUALIZATION_CONFIG.setdefault(
    "show_inline_assembly_steps",
    True,
)
VISUALIZATION_CONFIG.setdefault(
    "save_static_validated_step_pngs",
    True,
)
VISUALIZATION_CONFIG.setdefault(
    "allow_functional_only_final_display",
    False,
)
VISUALIZATION_CONFIG.setdefault(
    "show_source_context_when_incomplete",
    True,
)
VISUALIZATION_CONFIG.setdefault(
    "maximum_source_context_voxels",
    25000,
)


def progression_lightened_rgb(
    block,
):
    original = np.asarray(
        get_block_color(
            block
        ),
        dtype=float,
    )
    fraction = float(
        VISUALIZATION_CONFIG.get(
            "step_progression_previous_lighten_fraction",
            0.62,
        )
    )
    fraction = min(
        1.0,
        max(
            0.0,
            fraction,
        ),
    )
    return np.rint(
        original
        + (
            255.0
            - original
        )
        * fraction
    ).astype(
        int
    )


def clone_block_for_progression_prior(
    block,
):
    clone = copy.deepcopy(
        block
    )
    clone.base_color = (
        progression_lightened_rgb(
            block
        )
    )
    clone.progression_state = (
        "previously_accepted"
    )
    return clone


def progression_build_axis_label(
    build_axis,
):
    build_axis = str(
        build_axis
    ).upper()
    return build_axis[
        -1
    ] if build_axis else "Y"


def progression_camera(
    build_axis,
):
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


def progression_bounds(
    blocks,
    *,
    fallback_size=16,
):
    blocks = list(
        blocks
    )
    if (
        not blocks
        or not VISUALIZATION_CONFIG.get(
            "step_progression_focus_bounds",
            True,
        )
    ):
        maximum = float(
            fallback_size
        )
        return (
            (
                0.0,
                maximum,
            ),
            (
                0.0,
                maximum,
            ),
            (
                0.0,
                maximum,
            ),
        )

    padding = float(
        VISUALIZATION_CONFIG.get(
            "step_progression_focus_padding",
            1.25,
        )
    )
    minimum_span = float(
        VISUALIZATION_CONFIG.get(
            "step_progression_minimum_span",
            5.0,
        )
    )

    mins = np.min(
        np.asarray(
            [
                block.position
                for block in blocks
            ],
            dtype=float,
        ),
        axis=0,
    )
    maxs = np.max(
        np.asarray(
            [
                np.asarray(
                    block.position,
                    dtype=float,
                )
                + np.asarray(
                    block.size,
                    dtype=float,
                )
                for block in blocks
            ],
            dtype=float,
        ),
        axis=0,
    )

    bounds = []
    for axis_index in range(
        3
    ):
        low = float(
            mins[
                axis_index
            ]
            - padding
        )
        high = float(
            maxs[
                axis_index
            ]
            + padding
        )
        span = high - low
        if span < minimum_span:
            center = (
                low
                + high
            ) / 2.0
            low = (
                center
                - minimum_span
                / 2.0
            )
            high = (
                center
                + minimum_span
                / 2.0
            )
        bounds.append(
            (
                low,
                high,
            )
        )

    return tuple(
        bounds
    )


def apply_progression_axis_view(
    axis,
    blocks,
    build_axis,
    *,
    fallback_size=16,
):
    x_bounds, y_bounds, z_bounds = (
        progression_bounds(
            blocks,
            fallback_size=fallback_size,
        )
    )
    axis.set_xlim(
        *x_bounds
    )
    axis.set_ylim(
        *y_bounds
    )
    axis.set_zlim(
        *z_bounds
    )
    axis.set_box_aspect(
        (
            max(
                1.0,
                x_bounds[
                    1
                ]
                - x_bounds[
                    0
                ],
            ),
            max(
                1.0,
                y_bounds[
                    1
                ]
                - y_bounds[
                    0
                ],
            ),
            max(
                1.0,
                z_bounds[
                    1
                ]
                - z_bounds[
                    0
                ],
            ),
        )
    )
    elevation, azimuth = (
        progression_camera(
            build_axis
        )
    )
    axis.view_init(
        elev=elevation,
        azim=azimuth,
    )

def draw_static_step_block(
    axis,
    block,
    *,
    alpha,
    edgecolor,
    linewidth,
):
    x, y, z = (
        float(value)
        for value in block.position
    )
    dx, dy, dz = (
        float(value)
        for value in block.size
    )
    axis.bar3d(
        x,
        y,
        z,
        dx,
        dy,
        dz,
        color=block_rgb(block) / 255.0,
        edgecolor=edgecolor,
        linewidth=linewidth,
        alpha=alpha,
        shade=True,
    )


def save_validated_segment_step_images(
    result,
    output_dir,
    grid_shape,
):
    if (
        "planning_result" not in result
        or "validation" not in result
    ):
        return []

    blocks = list(
        result[
            "planning_result"
        ][
            "blocks"
        ]
    )
    steps = result[
        "planning_result"
    ][
        "instruction_steps"
    ]
    validation = result[
        "validation"
    ]
    block_lookup = {
        int(
            block.block_id
        ): block
        for block in blocks
    }
    output_dir = Path(
        output_dir
    )
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    written = []
    build_axis = str(
        result.get(
            "selected_build_axis",
            "+Y",
        )
    )

    for step_index, step in enumerate(
        steps
    ):
        step_number = (
            step_index
            + 1
        )
        current_ids = {
            int(
                block.block_id
            )
            for block in step[
                "blocks"
            ]
        }
        accepted_before = set(
            validation[
                "accepted_before_by_step"
            ].get(
                step_index,
                [],
            )
        )
        accepted_after = set(
            validation[
                "accepted_after_by_step"
            ].get(
                step_index,
                [],
            )
        )
        accepted_current = (
            current_ids
            & accepted_after
        )
        rejected_current = (
            current_ids
            - accepted_after
        )

        figure = plt.figure(
            figsize=(
                9.0,
                7.2,
            )
        )
        axis = figure.add_subplot(
            111,
            projection="3d",
        )

        for block_id in sorted(
            accepted_before
        ):
            block = block_lookup.get(
                block_id
            )
            if block is None:
                continue
            draw_static_step_block(
                axis,
                clone_block_for_progression_prior(
                    block
                ),
                alpha=float(
                    VISUALIZATION_CONFIG.get(
                        "saved_step_prior_alpha",
                        0.28,
                    )
                ),
                edgecolor="gray",
                linewidth=0.65,
            )

        for block_id in sorted(
            accepted_current
        ):
            block = block_lookup.get(
                block_id
            )
            if block is None:
                continue
            draw_static_step_block(
                axis,
                block,
                alpha=float(
                    VISUALIZATION_CONFIG.get(
                        "saved_step_current_alpha",
                        1.0,
                    )
                ),
                edgecolor="green",
                linewidth=1.8,
            )

        for block_id in sorted(
            rejected_current
        ):
            block = block_lookup.get(
                block_id
            )
            if block is None:
                continue
            draw_static_step_block(
                axis,
                block,
                alpha=0.72,
                edgecolor="crimson",
                linewidth=2.2,
            )

        current_blocks = [
            block_lookup[
                block_id
            ]
            for block_id in sorted(
                current_ids
            )
            if block_id in block_lookup
        ]
        visible_blocks = [
            block_lookup[
                block_id
            ]
            for block_id in sorted(
                accepted_before
                | current_ids
            )
            if block_id in block_lookup
        ]

        if VISUALIZATION_CONFIG.get(
            "saved_step_show_face_markers",
            True,
        ):
            reference_draw_face_markers(
                axis,
                current_blocks,
                context_blocks=visible_blocks,
            )

        for block in current_blocks:
            center = np.asarray(
                block.position,
                dtype=float,
            ) + np.asarray(
                block.size,
                dtype=float,
            ) / 2.0
            axis.text(
                center[
                    0
                ],
                center[
                    1
                ],
                center[
                    2
                ],
                (
                    f"B{int(block.block_id)}"
                ),
                fontsize=8,
                color="black",
                bbox={
                    "facecolor": "white",
                    "alpha": 0.84,
                    "pad": 1.5,
                },
            )

        axis.set_xlabel(
            "X"
        )
        axis.set_ylabel(
            "Y"
        )
        axis.set_zlabel(
            "Z"
        )
        apply_progression_axis_view(
            axis,
            visible_blocks,
            build_axis,
            fallback_size=int(
                max(
                    grid_shape
                )
            ),
        )

        step_row = validation[
            "step_rows"
        ][
            step_index
        ]
        status = str(
            step_row[
                "step_status"
            ]
        ).upper()
        axis_label = (
            progression_build_axis_label(
                build_axis
            )
        )
        axis.set_title(
            (
                f"Segment {result['segment_id']} — "
                f"Validated Assembly Step "
                f"{step_number}: row "
                f"{axis_label}={step_row['row']} — "
                f"{status}"
            ),
            color={
                "VALID": "green",
                "PARTIAL": "darkorange",
                "INVALID": "crimson",
            }.get(
                status,
                "black",
            ),
        )
        axis.text2D(
            0.01,
            0.98,
            (
                "Previous accepted blocks: "
                f"{','.join(str(value) for value in sorted(accepted_before)) or 'none'}\n"
                "Current accepted blocks: "
                f"{','.join(str(value) for value in sorted(accepted_current)) or 'none'}\n"
                "Current rejected blocks: "
                f"{','.join(str(value) for value in sorted(rejected_current)) or 'none'}\n"
                f"Lock area to previous rows: "
                f"{step_row.get('lock_area_to_accepted_prior', 0)}\n"
                f"Build axis: {build_axis}"
            ),
            transform=axis.transAxes,
            verticalalignment="top",
            fontsize=8.2,
            bbox={
                "facecolor": "white",
                "alpha": 0.90,
                "edgecolor": "black",
            },
        )
        plt.tight_layout()

        path = (
            output_dir
            / (
                f"validated_step_"
                f"{step_number:03d}.png"
            )
        )
        figure.savefig(
            path,
            dpi=180,
            bbox_inches="tight",
        )
        plt.close(
            figure
        )
        register_visualization(
            path,
            "segment_validated_step",
            (
                f"Segment {result['segment_id']} "
                f"validated step {step_number}"
            ),
        )
        written.append(
            path
        )

    return written


def build_subassembly_timeline(segment_results):
    appearance = {}
    step_rows = []
    step_labels = {0: 'Source model — no blocks placed'}
    global_step = 0
    for result in segment_results:
        planning_result = result.get('planning_result')
        validation = result.get('validation')
        if planning_result is None:
            continue
        segment_id = int(result['segment_id'])
        segment_name = str(result.get(
            'segment_name',
            segment_display_name_by_id.get(segment_id, f'Segment {segment_id}'),
        ))
        semantic_label = str(result.get('segment_label', 'unknown'))
        steps = planning_result['instruction_steps']
        validation_rows = validation.get('step_rows', []) if validation is not None else []
        for local_index, step in enumerate(steps, start=1):
            global_step += 1
            new_blocks = list(step.get('blocks', []))
            for block in new_blocks:
                appearance[int(block.block_id)] = global_step
            status = (
                str(validation_rows[local_index - 1]['step_status'])
                if local_index - 1 < len(validation_rows)
                else 'unknown'
            )
            row_value = step.get('row')
            step_labels[global_step] = (
                f'Build {segment_name} (segment {segment_id}) — '
                f'local step {local_index}, row {row_value}, status {status}'
            )
            step_rows.append({
                'global_step': global_step,
                'phase': 'build_segment_subassembly',
                'segment_id': segment_id,
                'segment_name': segment_name,
                'segment_label': semantic_label,
                'local_step': local_index,
                'row': row_value,
                'status': status,
                'new_block_ids': ','.join(str(int(block.block_id)) for block in new_blocks),
                'new_block_count': len(new_blocks),
            })
    return appearance, step_labels, pd.DataFrame(step_rows, columns=[
        'global_step', 'phase', 'segment_id', 'segment_name', 'segment_label',
        'local_step', 'row', 'status', 'new_block_ids', 'new_block_count',
    ])


def build_complete_timeline(
    segment_results,
    segment_blocks,
    connector_blocks,
    functional_blocks,
    structural_ready,
    *,
    valid_connector_interface_ids=None,
    valid_functional_target_ids=None,
):
    (
        appearance,
        step_labels,
        step_table,
    ) = build_subassembly_timeline(
        segment_results
    )
    step_rows = step_table.to_dict(
        orient="records"
    )
    current_step = max(
        step_labels,
        default=0,
    )

    display_blocks = list(
        segment_blocks
    )
    valid_connector_interface_ids = {
        str(value)
        for value in (
            valid_connector_interface_ids
            or set()
        )
    }
    valid_functional_target_ids = {
        str(value)
        for value in (
            valid_functional_target_ids
            or set()
        )
    }

    if structural_ready:
        connector_display_blocks = list(
            connector_blocks
        )
        functional_display_blocks = list(
            functional_blocks
        )
    else:
        connector_display_blocks = [
            block
            for block in connector_blocks
            if str(
                getattr(
                    block,
                    "interface_id",
                    "",
                )
            )
            in valid_connector_interface_ids
        ]
        functional_display_blocks = [
            block
            for block in functional_blocks
            if str(
                getattr(
                    block,
                    "physical_target_id",
                    "",
                )
            )
            in valid_functional_target_ids
        ]

    for connector in connector_display_blocks:
        current_step += 1
        appearance[
            int(connector.block_id)
        ] = current_step
        display_blocks.append(
            connector
        )
        step_labels[current_step] = (
            f"Place validated connector "
            f"{connector.block_family} "
            f"for interface "
            f"{connector.interface_id}"
        )
        step_rows.append(
            {
                "global_step": current_step,
                "phase": "place_connector",
                "segment_id": None,
                "segment_label": None,
                "local_step": None,
                "row": None,
                "status": (
                    "validated"
                    if not structural_ready
                    else "planned"
                ),
                "new_block_ids": str(
                    int(connector.block_id)
                ),
                "new_block_count": 1,
            }
        )

    for functional in functional_display_blocks:
        current_step += 1
        appearance[
            int(functional.block_id)
        ] = current_step
        display_blocks.append(
            functional
        )
        functional_role = str(
            getattr(
                functional,
                "block_role",
                "functional_attachment",
            )
        )
        functional_group_name = str(
            getattr(functional, "connected_group_name", "")
            or getattr(functional, "segment_name", "")
            or getattr(functional, "physical_target_id", "Functional Assembly")
        )
        if functional_role in {"functional_connector", "functional_motion_connector"}:
            step_labels[current_step] = (
                f"Attach {functional_group_name} connector to its validated anchor"
            )
        elif functional_role == "functional_subassembly_structural":
            step_labels[current_step] = (
                f"Add {functional_group_name} "
                f"{getattr(functional, 'subassembly_member_role', 'member')} block"
            )
        else:
            step_labels[current_step] = (
                f"Attach validated functional block "
                f"{functional.block_family} "
                f"for target "
                f"{functional.physical_target_id}"
            )
        if functional_role in {"functional_connector", "functional_motion_connector"}:
            functional_phase = (
                "attach_motion_subassembly_connector"
            )
        elif functional_role == "functional_subassembly_structural":
            functional_phase = (
                "build_functional_subassembly"
            )
        elif "wheel" in str(
            functional.block_family
        ).lower():
            functional_phase = (
                "attach_wheel"
            )
        else:
            functional_phase = (
                "attach_functional_block"
            )

        step_rows.append(
            {
                "global_step": current_step,
                "phase": functional_phase,
                "segment_id": None,
                "segment_label": str(
                    getattr(
                        functional,
                        "physical_target_id",
                        "",
                    )
                    or ""
                ),
                "local_step": None,
                "row": None,
                "status": "valid",
                "new_block_ids": str(
                    int(
                        functional.block_id
                    )
                ),
                "new_block_count": 1,
            }
        )

    if VISUALIZATION_CONFIG.get(
        "append_terminal_final_state_step",
        True,
    ):
        current_step += 1
        if structural_ready:
            terminal_label = (
                "Final validated build state"
            )
            terminal_phase = (
                "final_validated_state"
            )
            terminal_status = "valid"
        else:
            terminal_label = (
                "Available validated state — "
                "build incomplete"
            )
            terminal_phase = (
                "available_validated_state"
            )
            terminal_status = (
                "incomplete_diagnostic"
            )

        step_labels[
            current_step
        ] = terminal_label
        step_rows.append(
            {
                "global_step": current_step,
                "phase": terminal_phase,
                "segment_id": None,
                "segment_label": None,
                "local_step": None,
                "row": None,
                "status": terminal_status,
                "new_block_ids": "",
                "new_block_count": 0,
            }
        )

    return (
        display_blocks,
        appearance,
        step_labels,
        pd.DataFrame(
            step_rows,
            columns=[
                "global_step",
                "phase",
                "segment_id",
                "segment_label",
                "local_step",
                "row",
                "status",
                "new_block_ids",
                "new_block_count",
            ],
        ),
    )


def source_context_trace(
    segment_grid,
    *,
    visible=True,
):
    coordinates = np.argwhere(
        segment_grid > 0
    )
    maximum = int(
        VISUALIZATION_CONFIG.get(
            "maximum_source_context_voxels",
            25000,
        )
    )
    if len(coordinates) > maximum:
        indices = np.linspace(
            0,
            len(coordinates) - 1,
            maximum,
            dtype=int,
        )
        coordinates = coordinates[
            indices
        ]

    return go.Scatter3d(
        x=coordinates[:, 0] + 0.5,
        y=coordinates[:, 1] + 0.5,
        z=coordinates[:, 2] + 0.5,
        mode="markers",
        marker={
            "size": int(
                VISUALIZATION_CONFIG.get(
                    "source_context_marker_size",
                    4,
                )
            ),
            "color": "rgb(165,165,165)",
            "opacity": float(
                VISUALIZATION_CONFIG.get(
                    "source_context_marker_opacity",
                    0.18,
                )
            ),
            "symbol": "square",
        },
        name="Target source geometry",
        hovertemplate=(
            "Target source geometry"
            "<extra></extra>"
        ),
        visible=visible,
    )

def wrap_plotly_annotation_text(
    value,
    width=None,
):
    """
    Wrap plain Plotly annotation text with HTML line breaks.

    Existing HTML tags are preserved approximately; this helper is intended
    for generated status and instruction strings.
    """
    text = str(
        value
        if value is not None
        else ""
    )
    width = int(
        width
        or VISUALIZATION_CONFIG.get(
            "plotly_annotation_wrap_width",
            92,
        )
    )

    paragraphs = text.replace(
        "<br>",
        "\n",
    ).splitlines()

    wrapped = []
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            wrapped.append("")
            continue
        wrapped.extend(
            textwrap.wrap(
                paragraph,
                width=max(
                    30,
                    width,
                ),
                break_long_words=False,
                break_on_hyphens=False,
            )
            or [paragraph]
        )
    return "<br>".join(
        wrapped
    )



def detailed_sequence_figure(
    blocks,
    appearance,
    step_labels,
    title,
    *,
    source_grid=None,
    incomplete_message=None,
):
    """
    Cumulative audit timeline.

    This remains available as an exported HTML audit but the proper active-step
    player is now the default inline build visualization.
    """
    figure = go.Figure()
    trace_steps = []
    always_visible = []

    if (
        source_grid is not None
        and VISUALIZATION_CONFIG.get(
            "show_source_context_when_incomplete",
            True,
        )
    ):
        source_trace = (
            source_context_trace(
                source_grid,
                visible=True,
            )
        )
        figure.add_trace(
            source_trace
        )
        trace_steps.append(
            0
        )
        always_visible.append(
            True
        )

    shown_families = set()
    for block in blocks:
        family = str(
            block.block_family
        )
        block_step = int(
            appearance.get(
                int(
                    block.block_id
                ),
                1,
            )
        )
        for trace in block_traces(
            block,
            showlegend=(
                family
                not in shown_families
            ),
        ):
            trace.visible = False
            figure.add_trace(
                trace
            )
            trace_steps.append(
                block_step
            )
            always_visible.append(
                False
            )
        shown_families.add(
            family
        )

    maximum_step = max(
        step_labels,
        default=0,
    )
    configured_initial = int(
        VISUALIZATION_CONFIG.get(
            "complete_timeline_initial_step",
            1,
        )
    )
    initial_step = (
        min(
            max(
                0,
                configured_initial,
            ),
            maximum_step,
        )
        if maximum_step > 0
        else 0
    )

    def visibility_for_step(
        step_number,
    ):
        return [
            (
                True
                if always_visible[
                    index
                ]
                else (
                    trace_steps[
                        index
                    ]
                    <= step_number
                )
            )
            for index in range(
                len(
                    trace_steps
                )
            )
        ]

    def annotation_for_step(
        step_number,
    ):
        if (
            step_number == 0
            and incomplete_message
        ):
            return wrap_plotly_annotation_text(
                incomplete_message
            )
        return wrap_plotly_annotation_text(
            step_labels.get(
                step_number,
                f"Step {step_number}",
            )
        )

    def annotation_block(
        step_number,
    ):
        return [
            {
                "xref": "paper",
                "yref": "paper",
                "x": 0.01,
                "y": float(
                    VISUALIZATION_CONFIG.get(
                        "complete_timeline_annotation_y",
                        0.86,
                    )
                ),
                "xanchor": "left",
                "yanchor": "top",
                "align": "left",
                "text": annotation_for_step(
                    step_number
                ),
                "showarrow": False,
                "bgcolor": (
                    "rgba(255,255,255,0.94)"
                ),
                "bordercolor": (
                    "crimson"
                    if incomplete_message
                    and step_number == 0
                    else "gray"
                ),
                "borderwidth": 1,
                "font": {
                    "size": 12,
                    "color": (
                        "crimson"
                        if incomplete_message
                        and step_number == 0
                        else "black"
                    ),
                },
            }
        ]

    slider_steps = []
    for step_number in range(
        0,
        maximum_step + 1,
    ):
        slider_steps.append(
            {
                "method": "update",
                "label": str(
                    step_number
                ),
                "args": [
                    {
                        "visible": (
                            visibility_for_step(
                                step_number
                            )
                        )
                    },
                    {
                        "title": {
                            "text": (
                                f"{title} — "
                                f"Step {step_number} "
                                f"of {maximum_step}"
                            ),
                            "x": 0.5,
                            "xanchor": "center",
                            "y": 0.985,
                            "yanchor": "top",
                        },
                        "annotations": (
                            annotation_block(
                                step_number
                            )
                        ),
                    },
                ],
            }
        )

    initial_visible = (
        visibility_for_step(
            initial_step
        )
    )
    for index, visible in enumerate(
        initial_visible
    ):
        figure.data[
            index
        ].visible = bool(
            visible
        )

    layout = figure_layout(
        (
            f"{title} — "
            f"Step {initial_step} "
            f"of {maximum_step}"
        )
    )
    layout["title"] = {
        "text": (
            f"{title} — "
            f"Step {initial_step} "
            f"of {maximum_step}"
        ),
        "x": 0.5,
        "xanchor": "center",
        "y": 0.985,
        "yanchor": "top",
    }
    layout["scene"] = {
        **layout.get(
            "scene",
            {},
        ),
        "domain": {
            "x": [
                0.0,
                1.0,
            ],
            "y": [
                0.0,
                float(
                    VISUALIZATION_CONFIG.get(
                        "complete_timeline_scene_top",
                        0.74,
                    )
                ),
            ],
        },
    }
    layout["sliders"] = [
        {
            "active": int(
                initial_step
            ),
            "currentvalue": {
                "prefix": (
                    "Build step: "
                ),
            },
            "pad": {
                "t": 45
            },
            "steps": (
                slider_steps
            ),
        }
    ]
    layout["annotations"] = (
        annotation_block(
            initial_step
        )
    )
    layout["updatemenus"] = [
        {
            "type": "buttons",
            "direction": "left",
            "x": 0.01,
            "y": float(
                VISUALIZATION_CONFIG.get(
                    "complete_timeline_control_y",
                    0.93,
                )
            ),
            "xanchor": "left",
            "yanchor": "top",
            "buttons": [
                {
                    "label": "Source",
                    "method": "update",
                    "args": [
                        {
                            "visible": (
                                visibility_for_step(
                                    0
                                )
                            )
                        },
                        {
                            "title": {
                                "text": (
                                    f"{title} — "
                                    f"Source geometry"
                                ),
                                "x": 0.5,
                                "xanchor": (
                                    "center"
                                ),
                                "y": 0.985,
                            },
                            "annotations": (
                                annotation_block(
                                    0
                                )
                            ),
                        },
                    ],
                },
                {
                    "label": "Complete",
                    "method": "update",
                    "args": [
                        {
                            "visible": (
                                visibility_for_step(
                                    maximum_step
                                )
                            )
                        },
                        {
                            "title": {
                                "text": (
                                    f"{title} — "
                                    "Complete available state"
                                ),
                                "x": 0.5,
                                "xanchor": (
                                    "center"
                                ),
                                "y": 0.985,
                            },
                            "annotations": (
                                annotation_block(
                                    maximum_step
                                )
                            ),
                        },
                    ],
                },
            ],
        }
    ]
    layout["height"] = int(
        VISUALIZATION_CONFIG.get(
            "interactive_player_height",
            740,
        )
    )
    layout["margin"] = {
        **layout.get(
            "margin",
            {},
        ),
        "t": 115,
    }
    figure.update_layout(
        **layout
    )
    return figure

def clone_block_for_step_display(
    block,
    rgb,
):
    clone = copy.deepcopy(
        block
    )
    clone.base_color = np.asarray(
        rgb,
        dtype=int,
    )
    return clone


def proper_build_step_labels_for_segment(
    result,
):
    labels = {
        0: (
            "Target segment geometry — "
            "no blocks placed"
        )
    }
    validation_rows = (
        result.get(
            "validation",
            {},
        ).get(
            "step_rows",
            [],
        )
    )
    steps = (
        result.get(
            "planning_result",
            {},
        ).get(
            "instruction_steps",
            [],
        )
    )
    build_axis = str(
        result.get(
            "selected_build_axis",
            result.get(
                "planning_result",
                {},
            ).get(
                "selected_build_axis",
                "+Y",
            ),
        )
    )

    for step_number, step in enumerate(
        steps,
        start=1,
    ):
        blocks = list(
            step.get(
                "blocks",
                [],
            )
        )
        families = ", ".join(
            str(
                block.block_family
            )
            for block in blocks
        ) or "none"
        block_ids = ", ".join(
            str(
                int(
                    block.block_id
                )
            )
            for block in blocks
        ) or "none"
        validation_row = (
            validation_rows[
                step_number - 1
            ]
            if (
                step_number - 1
                < len(
                    validation_rows
                )
            )
            else {}
        )
        labels[
            step_number
        ] = (
            f"Build axis {build_axis}; "
            f"place block(s) {block_ids}; "
            f"families: {families}; "
            f"status: "
            f"{validation_row.get('step_status', 'unknown')}; "
            f"lock area to accepted structure: "
            f"{validation_row.get('lock_area_to_accepted_prior', 0)}; "
            f"internal lock area: "
            f"{validation_row.get('internal_lock_area', 0)}."
        )
    return labels


def proper_build_step_figure(
    blocks,
    appearance,
    step_labels,
    title,
    *,
    source_grid=None,
):
    """
    Primary build-step player.

    Earlier accepted blocks retain a lightened version of their family
    color at low opacity. The current placement uses full catalog color.
    Male and female markers can be controlled independently without changing
    step visibility.
    """
    blocks = list(
        blocks
    )
    maximum_step = max(
        step_labels,
        default=0,
    )
    figure = go.Figure()

    trace_step = []
    trace_kind = []
    always_visible = []

    if (
        source_grid is not None
        and VISUALIZATION_CONFIG.get(
            "proper_build_steps_show_source_context",
            True,
        )
    ):
        source_trace = (
            source_context_trace(
                source_grid,
                visible=True,
            )
        )
        source_trace.marker.opacity = float(
            VISUALIZATION_CONFIG.get(
                "proper_build_steps_source_context_opacity",
                0.20,
            )
        )
        figure.add_trace(
            source_trace
        )
        trace_step.append(
            -1
        )
        trace_kind.append(
            "source"
        )
        always_visible.append(
            True
        )

    previous_rgb = (
        VISUALIZATION_CONFIG.get(
            "proper_build_steps_previous_block_rgb",
            [
                185,
                185,
                185,
            ],
        )
    )
    previous_opacity = float(
        VISUALIZATION_CONFIG.get(
            "proper_build_steps_previous_opacity",
            0.42,
        )
    )
    current_opacity = float(
        VISUALIZATION_CONFIG.get(
            "proper_build_steps_current_opacity",
            1.0,
        )
    )
    face_default = bool(
        VISUALIZATION_CONFIG.get(
            "proper_build_steps_face_markers_default",
            False,
        )
    )

    for step_number in range(
        1,
        maximum_step + 1,
    ):
        prior_blocks = [
            block
            for block in blocks
            if int(
                appearance.get(
                    int(
                        block.block_id
                    ),
                    maximum_step + 1,
                )
            )
            < step_number
        ]
        current_blocks = [
            block
            for block in blocks
            if int(
                appearance.get(
                    int(
                        block.block_id
                    ),
                    maximum_step + 1,
                )
            )
            == step_number
        ]

        for block in prior_blocks:
            prior_display_block = (
                clone_block_for_progression_prior(
                    block
                )
            )
            for trace in block_traces(
                prior_display_block,
                showlegend=False,
            ):
                if hasattr(
                    trace,
                    "opacity",
                ):
                    trace.opacity = (
                        previous_opacity
                    )
                trace.visible = False
                figure.add_trace(
                    trace
                )
                trace_step.append(
                    step_number
                )
                trace_kind.append(
                    "prior"
                )
                always_visible.append(
                    False
                )

        for block in current_blocks:
            for trace in block_traces(
                block,
                showlegend=True,
            ):
                if hasattr(
                    trace,
                    "opacity",
                ):
                    trace.opacity = (
                        current_opacity
                    )
                trace.visible = False
                figure.add_trace(
                    trace
                )
                trace_step.append(
                    step_number
                )
                trace_kind.append(
                    "current"
                )
                always_visible.append(
                    False
                )

        if current_blocks:
            (
                male_trace,
                female_trace,
            ) = face_traces(
                current_blocks
            )
            male_trace.visible = False
            female_trace.visible = False
            male_trace.marker.opacity = (
                1.0
                if face_default
                else 0.0
            )
            female_trace.marker.opacity = (
                1.0
                if face_default
                else 0.0
            )

            figure.add_trace(
                male_trace
            )
            trace_step.append(
                step_number
            )
            trace_kind.append(
                "male"
            )
            always_visible.append(
                False
            )

            figure.add_trace(
                female_trace
            )
            trace_step.append(
                step_number
            )
            trace_kind.append(
                "female"
            )
            always_visible.append(
                False
            )

    def visibility_for_step(
        step_number,
    ):
        return [
            bool(
                always_visible[
                    index
                ]
            )
            or (
                step_number > 0
                and trace_step[
                    index
                ]
                == step_number
            )
            for index in range(
                len(
                    trace_step
                )
            )
        ]

    def annotation_block(
        step_number,
    ):
        return [
            {
                "xref": "paper",
                "yref": "paper",
                "x": 0.01,
                "y": float(
                    VISUALIZATION_CONFIG.get(
                        "proper_build_steps_annotation_y",
                        0.86,
                    )
                ),
                "xanchor": "left",
                "yanchor": "top",
                "align": "left",
                "text": (
                    wrap_plotly_annotation_text(
                        step_labels.get(
                            step_number,
                            (
                                "Target source geometry — "
                                "no blocks placed"
                            ),
                        )
                    )
                ),
                "showarrow": False,
                "bgcolor": (
                    "rgba(255,255,255,0.94)"
                ),
                "bordercolor": (
                    "gray"
                ),
                "borderwidth": 1,
                "font": {
                    "size": 12
                },
            }
        ]

    configured_initial = int(
        VISUALIZATION_CONFIG.get(
            "proper_build_steps_initial_step",
            1,
        )
    )
    initial_step = (
        min(
            max(
                0,
                configured_initial,
            ),
            maximum_step,
        )
        if maximum_step > 0
        else 0
    )

    slider_steps = []
    for step_number in range(
        0,
        maximum_step + 1,
    ):
        slider_steps.append(
            {
                "method": "update",
                "label": str(
                    step_number
                ),
                "args": [
                    {
                        "visible": (
                            visibility_for_step(
                                step_number
                            )
                        )
                    },
                    {
                        "title": {
                            "text": (
                                f"{title} — "
                                f"Step {step_number} "
                                f"of {maximum_step}"
                            ),
                            "x": 0.5,
                            "xanchor": (
                                "center"
                            ),
                            "y": 0.985,
                            "yanchor": "top",
                        },
                        "annotations": (
                            annotation_block(
                                step_number
                            )
                        ),
                    },
                ],
            }
        )

    for index, trace in enumerate(
        figure.data
    ):
        trace.visible = (
            visibility_for_step(
                initial_step
            )[
                index
            ]
        )

    male_indices = [
        index
        for index, kind in enumerate(
            trace_kind
        )
        if kind == "male"
    ]
    female_indices = [
        index
        for index, kind in enumerate(
            trace_kind
        )
        if kind == "female"
    ]

    layout = figure_layout(
        (
            f"{title} — "
            f"Step {initial_step} "
            f"of {maximum_step}"
        )
    )
    layout["title"] = {
        "text": (
            f"{title} — "
            f"Step {initial_step} "
            f"of {maximum_step}"
        ),
        "x": 0.5,
        "xanchor": "center",
        "y": 0.985,
        "yanchor": "top",
    }
    layout["scene"] = {
        **layout.get(
            "scene",
            {},
        ),
        "domain": {
            "x": [
                0.0,
                1.0,
            ],
            "y": [
                0.0,
                float(
                    VISUALIZATION_CONFIG.get(
                        "proper_build_steps_scene_top",
                        0.72,
                    )
                ),
            ],
        },
    }
    layout["sliders"] = [
        {
            "active": int(
                initial_step
            ),
            "currentvalue": {
                "prefix": (
                    "Build step: "
                )
            },
            "pad": {
                "t": 45
            },
            "steps": (
                slider_steps
            ),
        }
    ]
    layout["annotations"] = (
        annotation_block(
            initial_step
        )
    )
    control_y = float(
        VISUALIZATION_CONFIG.get(
            "proper_build_steps_control_y",
            0.93,
        )
    )
    layout["updatemenus"] = [
        {
            "type": "buttons",
            "direction": "left",
            "x": 0.01,
            "y": control_y,
            "xanchor": "left",
            "yanchor": "top",
            "active": (
                1
                if face_default
                else 0
            ),
            "buttons": [
                {
                    "label": "Male off",
                    "method": "restyle",
                    "args": [
                        {
                            "marker.opacity": 0.0
                        },
                        male_indices,
                    ],
                },
                {
                    "label": "Male on",
                    "method": "restyle",
                    "args": [
                        {
                            "marker.opacity": 1.0
                        },
                        male_indices,
                    ],
                },
            ],
        },
        {
            "type": "buttons",
            "direction": "left",
            "x": 0.28,
            "y": control_y,
            "xanchor": "left",
            "yanchor": "top",
            "active": (
                1
                if face_default
                else 0
            ),
            "buttons": [
                {
                    "label": "Female off",
                    "method": "restyle",
                    "args": [
                        {
                            "marker.opacity": 0.0
                        },
                        female_indices,
                    ],
                },
                {
                    "label": "Female on",
                    "method": "restyle",
                    "args": [
                        {
                            "marker.opacity": 1.0
                        },
                        female_indices,
                    ],
                },
            ],
        },
    ]
    layout["height"] = int(
        VISUALIZATION_CONFIG.get(
            "proper_build_steps_height",
            760,
        )
    )
    layout["margin"] = {
        **layout.get(
            "margin",
            {},
        ),
        "t": 120,
    }
    figure.update_layout(
        **layout
    )
    return figure



def build_assembly_timeline(
    assembly_steps,
    segment_blocks_by_id,
    connector_blocks,
    functional_blocks,
    connector_validation_df,
    structural_ready,
):
    connector_by_interface = {
        str(
            block.interface_id
        ): block
        for block in connector_blocks
    }
    valid_rows = (
        connector_validation_df.loc[
            connector_validation_df.get(
                "valid",
                pd.Series(
                    dtype=bool
                ),
            ).astype(
                bool
            )
        ].copy()
        if not connector_validation_df.empty
        else pd.DataFrame()
    )
    valid_interfaces = set(
        valid_rows.get(
            "interface_id",
            pd.Series(
                dtype=str
            ),
        ).astype(
            str
        )
    )
    join_mode_by_interface = {
        str(
            row.interface_id
        ): str(
            getattr(
                row,
                "join_mode",
                "special_connector_block",
            )
        )
        for row in valid_rows.itertuples(
            index=False
        )
    }

    visible_blocks = []
    appearance = {}
    labels = {
        0: "No assembled subassemblies"
    }
    rows = []
    step_number = 0

    if not assembly_steps:
        return (
            visible_blocks,
            appearance,
            labels,
            pd.DataFrame(
                rows,
                columns=[
                    "assembly_visual_step",
                    "action",
                    "segment_id",
                    "interface_id",
                    "block_ids",
                    "status",
                ],
            ),
        )

    root_segment_id = int(
        assembly_steps[
            0
        ][
            "attached_segment_id"
        ]
    )
    root_blocks = list(
        segment_blocks_by_id.get(
            root_segment_id,
            [],
        )
    )
    if root_blocks:
        step_number += 1
        for block in root_blocks:
            appearance[
                int(
                    block.block_id
                )
            ] = step_number
            visible_blocks.append(
                block
            )
        labels[
            step_number
        ] = (
            f"Start with completed segment "
            f"{root_segment_id}"
        )
        rows.append(
            {
                "assembly_visual_step": (
                    step_number
                ),
                "action": (
                    "start_with_segment_subassembly"
                ),
                "segment_id": (
                    root_segment_id
                ),
                "interface_id": None,
                "block_ids": ",".join(
                    str(
                        int(
                            block.block_id
                        )
                    )
                    for block in root_blocks
                ),
                "status": "ready",
            }
        )

    if structural_ready:
        for assembly_step in assembly_steps[
            1:
        ]:
            attached_segment_id = int(
                assembly_step[
                    "attached_segment_id"
                ]
            )
            interface_id = str(
                assembly_step[
                    "interface_id"
                ]
            )
            join_mode = (
                join_mode_by_interface.get(
                    interface_id
                )
            )

            if interface_id not in valid_interfaces:
                rows.append(
                    {
                        "assembly_visual_step": None,
                        "action": (
                            "attach_segment_blocked"
                        ),
                        "segment_id": (
                            attached_segment_id
                        ),
                        "interface_id": (
                            interface_id
                        ),
                        "block_ids": "",
                        "status": (
                            "missing_or_invalid_join"
                        ),
                    }
                )
                continue

            if join_mode != "direct_structural_lock":
                connector = (
                    connector_by_interface.get(
                        interface_id
                    )
                )
                if connector is None:
                    rows.append(
                        {
                            "assembly_visual_step": None,
                            "action": (
                                "attach_segment_blocked"
                            ),
                            "segment_id": (
                                attached_segment_id
                            ),
                            "interface_id": (
                                interface_id
                            ),
                            "block_ids": "",
                            "status": (
                                "missing_special_connector"
                            ),
                        }
                    )
                    continue

                step_number += 1
                appearance[
                    int(
                        connector.block_id
                    )
                ] = step_number
                visible_blocks.append(
                    connector
                )
                labels[
                    step_number
                ] = (
                    f"Place special connector for "
                    f"{interface_id}"
                )
                rows.append(
                    {
                        "assembly_visual_step": (
                            step_number
                        ),
                        "action": (
                            "place_special_connector"
                        ),
                        "segment_id": None,
                        "interface_id": (
                            interface_id
                        ),
                        "block_ids": str(
                            int(
                                connector.block_id
                            )
                        ),
                        "status": "ready",
                    }
                )

            attached_blocks = list(
                segment_blocks_by_id.get(
                    attached_segment_id,
                    [],
                )
            )
            if attached_blocks:
                step_number += 1
                for block in attached_blocks:
                    appearance[
                        int(
                            block.block_id
                        )
                    ] = step_number
                    visible_blocks.append(
                        block
                    )
                labels[
                    step_number
                ] = (
                    f"Attach completed segment "
                    f"{attached_segment_id} by "
                    f"{join_mode or 'validated join'}"
                )
                rows.append(
                    {
                        "assembly_visual_step": (
                            step_number
                        ),
                        "action": (
                            "attach_segment_by_"
                            "direct_structural_lock"
                            if join_mode
                            == "direct_structural_lock"
                            else (
                                "attach_segment_"
                                "through_special_connector"
                            )
                        ),
                        "segment_id": (
                            attached_segment_id
                        ),
                        "interface_id": (
                            interface_id
                        ),
                        "block_ids": ",".join(
                            str(
                                int(
                                    block.block_id
                                )
                            )
                            for block in (
                                attached_blocks
                            )
                        ),
                        "status": "ready",
                    }
                )

        for functional in functional_blocks:
            step_number += 1
            appearance[
                int(
                    functional.block_id
                )
            ] = step_number
            visible_blocks.append(
                functional
            )
            functional_role = str(
                getattr(
                    functional,
                    "block_role",
                    "functional_attachment",
                )
            )
            functional_group_name = str(
                getattr(functional, "connected_group_name", "")
                or getattr(functional, "segment_name", "")
                or getattr(functional, "physical_target_id", "Functional Assembly")
            )
            if functional_role in {"functional_connector", "functional_motion_connector"}:
                labels[step_number] = (
                    f"Attach {functional_group_name} connector to its validated anchor"
                )
            elif functional_role == "functional_subassembly_structural":
                labels[step_number] = (
                    f"Add {functional_group_name} "
                    f"{getattr(functional, 'subassembly_member_role', 'member')} block"
                )
            else:
                labels[
                    step_number
                ] = (
                    f"Attach {functional.block_family} "
                    f"at target "
                    f"{functional.physical_target_id}"
                )
            rows.append(
                {
                    "assembly_visual_step": (
                        step_number
                    ),
                    "action": (
                        "attach_functional_block"
                    ),
                    "segment_id": None,
                    "interface_id": None,
                    "block_ids": str(
                        int(
                            functional.block_id
                        )
                    ),
                    "status": "ready",
                }
            )

    return (
        visible_blocks,
        appearance,
        labels,
        pd.DataFrame(
            rows,
            columns=[
                "assembly_visual_step",
                "action",
                "segment_id",
                "interface_id",
                "block_ids",
                "status",
            ],
        ),
    )


# ------------------------------------------------------------------
# Shared 2x2 structural lattice conversion
# ------------------------------------------------------------------

STRUCTURALIZATION_CONFIG = TASK_CONTEXT.get(
    "structuralization",
    {},
)


def structuralization_allowed_heights():
    heights = sorted({
        int(record["column_height"])
        for record in STRUCTURAL_CATALOG_RECORDS
        if int(record["column_height"]) > 0
    })
    if not heights:
        raise RuntimeError(
            "No enabled structural catalog column heights "
            "are available."
        )
    return heights


def height_is_catalog_representable(
    height,
    allowed_heights,
):
    height = int(height)
    reachable = [False] * (
        height + 1
    )
    reachable[0] = True
    for value in range(1, height + 1):
        reachable[value] = any(
            value - block_height >= 0
            and reachable[
                value - block_height
            ]
            for block_height in allowed_heights
        )
    return bool(reachable[height])


def structuralization_mirror_index(
    index,
    center_plane,
):
    mirrored = (
        2.0 * float(center_plane)
        - (float(index) + 0.5)
    )
    return int(round(mirrored - 0.5))


def structuralization_mirror_mask(
    mask,
    axis,
    center_plane,
):
    mask = np.asarray(mask, dtype=bool)
    mirrored = np.zeros_like(mask)
    for coordinate in np.argwhere(mask):
        reflected = coordinate.astype(int).copy()
        reflected[axis] = (
            structuralization_mirror_index(
                reflected[axis],
                center_plane,
            )
        )
        if all(
            0
            <= reflected[current_axis]
            < mask.shape[current_axis]
            for current_axis in range(3)
        ):
            mirrored[tuple(reflected)] = True
    return mirrored


def structuralization_mask_iou(
    mask_a,
    mask_b,
):
    mask_a = np.asarray(mask_a, dtype=bool)
    mask_b = np.asarray(mask_b, dtype=bool)
    union = int((mask_a | mask_b).sum())
    if union == 0:
        return 1.0
    return float(
        (mask_a & mask_b).sum() / union
    )


def infer_structuralization_center_plane(
    occupied_mask,
    axis,
):
    coordinates = np.argwhere(
        occupied_mask
    )
    if len(coordinates) == 0:
        return occupied_mask.shape[
            axis
        ] / 2.0

    minimum = int(
        coordinates[:, axis].min()
    )
    maximum = int(
        coordinates[:, axis].max()
    )
    bbox_center = (
        minimum + maximum + 1
    ) / 2.0

    configured = (
        TASK_CONTEXT.get("symmetry", {})
        .get("center_plane")
    )
    if configured is not None:
        candidates = [float(configured)]
    else:
        candidates = list(
            np.arange(
                float(minimum),
                float(maximum + 1) + 0.25,
                0.5,
            )
        )
        candidates.append(
            float(bbox_center)
        )

    scored = []
    for center_plane in sorted(
        set(candidates)
    ):
        mirrored = (
            structuralization_mirror_mask(
                occupied_mask,
                axis,
                center_plane,
            )
        )
        score = (
            structuralization_mask_iou(
                occupied_mask,
                mirrored,
            )
        )
        scored.append((
            score,
            -abs(
                float(center_plane)
                - float(bbox_center)
            ),
            float(center_plane),
        ))

    return max(scored)[2]


def structuralization_axis_index():
    axis_name = str(
        TASK_CONTEXT.get(
            "symmetry",
            {},
        ).get("axis", "X")
    ).upper()
    return {"X": 0, "Y": 1, "Z": 2}[axis_name]


def cell_layer_source_counts(
    segment_grid,
    x,
    y,
    z,
    allowed_segment_ids,
):
    values = segment_grid[
        x:x + 2,
        y:y + 2,
        z,
    ].ravel()
    return Counter(
        int(value)
        for value in values
        if int(value) in allowed_segment_ids
    )


def optimize_structural_cell_span(
    source_counts_by_layer,
    majority_owner_by_layer,
    candidate_segment_ids,
    allowed_heights,
    config,
):
    layer_count = len(
        source_counts_by_layer
    )
    if layer_count == 0:
        return [], 0.0

    match_weight = float(
        config.get(
            "match_source_weight",
            120.0,
        )
    )
    steal_penalty = float(
        config.get(
            "steal_other_source_penalty",
            80.0,
        )
    )
    drop_penalty = float(
        config.get(
            "drop_source_penalty",
            120.0,
        )
    )
    expansion_penalty = float(
        config.get(
            "expansion_penalty",
            4.0,
        )
    )
    majority_bonus = float(
        config.get(
            "majority_owner_bonus",
            8.0,
        )
    )
    transition_penalty = float(
        config.get(
            "run_transition_penalty",
            2.0,
        )
    )

    best = [None] * (
        layer_count + 1
    )
    best[0] = (
        0.0,
        [],
        None,
    )

    for position in range(
        layer_count
    ):
        if best[position] is None:
            continue
        (
            current_score,
            current_runs,
            previous_label,
        ) = best[position]

        for label in (
            [0]
            + sorted(
                int(value)
                for value in candidate_segment_ids
            )
        ):
            if label == 0:
                lengths = range(
                    1,
                    layer_count - position + 1,
                )
            else:
                lengths = [
                    length
                    for length in range(
                        1,
                        layer_count - position + 1,
                    )
                    if height_is_catalog_representable(
                        length,
                        allowed_heights,
                    )
                ]

            for length in lengths:
                run_score = 0.0
                for local_index in range(
                    position,
                    position + length,
                ):
                    counts = (
                        source_counts_by_layer[
                            local_index
                        ]
                    )
                    total_source = int(
                        sum(counts.values())
                    )
                    if label == 0:
                        run_score -= (
                            drop_penalty
                            * total_source
                        )
                    else:
                        matched = int(
                            counts.get(label, 0)
                        )
                        other = (
                            total_source - matched
                        )
                        run_score += (
                            match_weight
                            * matched
                        )
                        run_score -= (
                            steal_penalty
                            * other
                        )
                        run_score -= (
                            expansion_penalty
                            * (4 - matched)
                        )
                        if (
                            majority_owner_by_layer[
                                local_index
                            ]
                            == label
                        ):
                            run_score += (
                                majority_bonus
                            )

                if (
                    previous_label is not None
                    and previous_label != label
                ):
                    run_score -= (
                        transition_penalty
                    )

                next_position = (
                    position + length
                )
                candidate_score = (
                    current_score
                    + run_score
                )
                candidate_runs = (
                    current_runs
                    + [(
                        position,
                        next_position - 1,
                        int(label),
                    )]
                )

                if (
                    best[next_position]
                    is None
                    or candidate_score
                    > best[next_position][0]
                ):
                    best[next_position] = (
                        candidate_score,
                        candidate_runs,
                        int(label),
                    )

    if best[layer_count] is None:
        raise RuntimeError(
            "Could not optimize structural cell span."
        )

    result = [0] * layer_count
    final_score, runs, _ = (
        best[layer_count]
    )
    for start, end, label in runs:
        for local_index in range(
            start,
            end + 1,
        ):
            result[local_index] = (
                int(label)
            )

    return result, float(final_score)


def connected_component_sizes(
    mask,
):
    remaining = set(
        map(
            tuple,
            np.argwhere(mask),
        )
    )
    sizes = []
    offsets = [
        (1, 0, 0),
        (-1, 0, 0),
        (0, 1, 0),
        (0, -1, 0),
        (0, 0, 1),
        (0, 0, -1),
    ]

    while remaining:
        start = remaining.pop()
        queue = [start]
        size = 1

        while queue:
            coordinate = queue.pop()
            for offset in offsets:
                neighbor = tuple(
                    coordinate[axis]
                    + offset[axis]
                    for axis in range(3)
                )
                if neighbor in remaining:
                    remaining.remove(
                        neighbor
                    )
                    queue.append(
                        neighbor
                    )
                    size += 1

        sizes.append(size)

    return sorted(
        sizes,
        reverse=True,
    )


def catalog_run_audit(
    mask,
    allowed_heights,
):
    invalid_runs = []
    shape = mask.shape

    for x in range(
        0,
        shape[0] - 1,
        2,
    ):
        for y in range(
            0,
            shape[1] - 1,
            2,
        ):
            occupied = [
                bool(mask[x, y, z])
                for z in range(
                    shape[2]
                )
            ]
            start = None
            for z, value in enumerate(
                occupied + [False]
            ):
                if (
                    value
                    and start is None
                ):
                    start = z
                elif (
                    not value
                    and start is not None
                ):
                    height = z - start
                    if not (
                        height_is_catalog_representable(
                            height,
                            allowed_heights,
                        )
                    ):
                        invalid_runs.append({
                            "cell_x": x,
                            "cell_y": y,
                            "z_min": start,
                            "height": height,
                        })
                    start = None

    return invalid_runs


def exact_lattice_mask(
    mask,
):
    shape = mask.shape
    for x in range(
        0,
        shape[0] - 1,
        2,
    ):
        for y in range(
            0,
            shape[1] - 1,
            2,
        ):
            counts = mask[
                x:x + 2,
                y:y + 2,
                :,
            ].sum(
                axis=(0, 1)
            )
            if np.any(
                (counts > 0)
                & (counts < 4)
            ):
                return False
    return True


def apply_confirmed_structural_symmetry_repairs(
    structural_grid,
    center_plane,
    axis,
    config,
):
    repaired = structural_grid.copy()
    audit_rows = []

    for repair in config.get(
        "confirmed_symmetry_repairs",
        [],
    ):
        segment_a = int(
            repair["segment_a"]
        )
        segment_b = int(
            repair["segment_b"]
        )
        template_segment_id = int(
            repair.get(
                "template_segment_id",
                segment_a,
            )
        )
        partner_segment_id = (
            segment_b
            if template_segment_id
            == segment_a
            else segment_a
        )
        apply_repair = bool(
            repair.get("apply", False)
        )

        template_mask = (
            repaired
            == template_segment_id
        )
        current_partner_mask = (
            repaired
            == partner_segment_id
        )
        mirrored_template = (
            structuralization_mirror_mask(
                template_mask,
                axis,
                center_plane,
            )
        )
        conflict_mask = (
            mirrored_template
            & (repaired > 0)
            & (
                repaired
                != partner_segment_id
            )
        )
        conflict_count = int(
            conflict_mask.sum()
        )

        require_conflict_free = bool(
            config.get(
                "symmetry_repair_require_conflict_free",
                True,
            )
        )
        status = "not_applied"

        if (
            apply_repair
            and (
                not require_conflict_free
                or conflict_count == 0
            )
        ):
            repaired[
                current_partner_mask
            ] = 0
            repaired[
                mirrored_template
            ] = partner_segment_id
            status = "applied"
        elif (
            apply_repair
            and conflict_count > 0
        ):
            status = (
                "blocked_by_other_segment_conflict"
            )

        final_partner_mask = (
            repaired
            == partner_segment_id
        )
        final_iou = (
            structuralization_mask_iou(
                mirrored_template,
                final_partner_mask,
            )
        )

        audit_rows.append({
            "repair_id": repair.get(
                "repair_id"
            ),
            "segment_a": segment_a,
            "segment_b": segment_b,
            "template_segment_id": (
                template_segment_id
            ),
            "partner_segment_id": (
                partner_segment_id
            ),
            "apply_requested": (
                apply_repair
            ),
            "status": status,
            "conflict_voxel_count": (
                conflict_count
            ),
            "template_voxel_count": int(
                template_mask.sum()
            ),
            "partner_voxel_count_before": int(
                current_partner_mask.sum()
            ),
            "partner_voxel_count_after": int(
                final_partner_mask.sum()
            ),
            "final_mirror_iou": float(
                final_iou
            ),
            "confirmation_source": (
                repair.get(
                    "confirmation_source"
                )
            ),
            "reason": repair.get(
                "reason"
            ),
        })

    return (
        repaired,
        pd.DataFrame(audit_rows),
    )


def structuralize_segment_grid(
    raw_segment_grid,
    structural_segment_ids,
    functional_target_segment_ids,
):
    config = STRUCTURALIZATION_CONFIG
    if not config.get("enabled", True):
        return {
            "combined_grid": (
                raw_segment_grid.copy()
            ),
            "structural_grid": (
                np.where(
                    np.isin(
                        raw_segment_grid,
                        structural_segment_ids,
                    ),
                    raw_segment_grid,
                    0,
                )
            ),
            "ownership_audit_df": (
                pd.DataFrame()
            ),
            "segment_summary_df": (
                pd.DataFrame()
            ),
            "symmetry_repair_audit_df": (
                pd.DataFrame()
            ),
            "active_structural_segment_ids": (
                sorted(
                    structural_segment_ids
                )
            ),
            "dropped_structural_segment_ids": [],
            "gate_valid": True,
            "center_plane": None,
            "allowed_heights": (
                structuralization_allowed_heights()
            ),
        }

    raw_segment_grid = np.asarray(
        raw_segment_grid,
        dtype=int,
    )
    structural_ids = {
        int(value)
        for value in structural_segment_ids
    }
    functional_ids = {
        int(value)
        for value in functional_target_segment_ids
    }
    allowed_heights = (
        structuralization_allowed_heights()
    )
    shape = raw_segment_grid.shape
    structural_grid = np.zeros(
        shape,
        dtype=int,
    )
    functional_reservation = np.zeros(
        shape,
        dtype=bool,
    )
    ownership_rows = []

    # Reserve complete 2x2 cell layers containing
    # valid functional source geometry.
    for x in range(
        0,
        shape[0] - 1,
        2,
    ):
        for y in range(
            0,
            shape[1] - 1,
            2,
        ):
            for z in range(
                shape[2]
            ):
                layer = raw_segment_grid[
                    x:x + 2,
                    y:y + 2,
                    z,
                ]
                if np.isin(
                    layer,
                    sorted(functional_ids),
                ).any():
                    functional_reservation[
                        x:x + 2,
                        y:y + 2,
                        z,
                    ] = True

    for x in range(
        0,
        shape[0] - 1,
        2,
    ):
        for y in range(
            0,
            shape[1] - 1,
            2,
        ):
            reserved_by_z = [
                bool(
                    functional_reservation[
                        x,
                        y,
                        z,
                    ]
                )
                for z in range(
                    shape[2]
                )
            ]

            source_counts = [
                cell_layer_source_counts(
                    raw_segment_grid,
                    x,
                    y,
                    z,
                    structural_ids,
                )
                for z in range(
                    shape[2]
                )
            ]
            majority_owner = [
                (
                    max(
                        counts,
                        key=lambda segment_id: (
                            counts[segment_id],
                            int(
                                (
                                    raw_segment_grid
                                    == segment_id
                                ).sum()
                            ),
                            -segment_id,
                        ),
                    )
                    if counts
                    else 0
                )
                for counts in source_counts
            ]

            z = 0
            while z < shape[2]:
                if reserved_by_z[z]:
                    ownership_rows.append({
                        "cell_x": x,
                        "cell_y": y,
                        "z": z,
                        "raw_segment_counts": (
                            dict(
                                source_counts[z]
                            )
                        ),
                        "majority_owner": (
                            majority_owner[z]
                        ),
                        "final_owner": 0,
                        "functional_reserved": (
                            True
                        ),
                        "optimization_score": (
                            None
                        ),
                    })
                    z += 1
                    continue

                span_start = z
                while (
                    z < shape[2]
                    and not reserved_by_z[z]
                ):
                    z += 1
                span_end = z
                span_counts = (
                    source_counts[
                        span_start:span_end
                    ]
                )
                span_majority = (
                    majority_owner[
                        span_start:span_end
                    ]
                )
                candidate_ids = {
                    int(segment_id)
                    for counts in span_counts
                    for segment_id in counts
                }

                if not candidate_ids:
                    for absolute_z in range(
                        span_start,
                        span_end,
                    ):
                        ownership_rows.append({
                            "cell_x": x,
                            "cell_y": y,
                            "z": absolute_z,
                            "raw_segment_counts": {},
                            "majority_owner": 0,
                            "final_owner": 0,
                            "functional_reserved": (
                                False
                            ),
                            "optimization_score": (
                                0.0
                            ),
                        })
                    continue

                (
                    optimized_labels,
                    optimization_score,
                ) = optimize_structural_cell_span(
                    span_counts,
                    span_majority,
                    candidate_ids,
                    allowed_heights,
                    config,
                )

                for local_z, owner in enumerate(
                    optimized_labels
                ):
                    absolute_z = (
                        span_start + local_z
                    )
                    if owner > 0:
                        structural_grid[
                            x:x + 2,
                            y:y + 2,
                            absolute_z,
                        ] = int(owner)

                    ownership_rows.append({
                        "cell_x": x,
                        "cell_y": y,
                        "z": absolute_z,
                        "raw_segment_counts": (
                            dict(
                                source_counts[
                                    absolute_z
                                ]
                            )
                        ),
                        "majority_owner": (
                            majority_owner[
                                absolute_z
                            ]
                        ),
                        "final_owner": int(
                            owner
                        ),
                        "functional_reserved": (
                            False
                        ),
                        "optimization_score": (
                            optimization_score
                        ),
                    })

    symmetry_axis = (
        structuralization_axis_index()
    )
    structural_source_mask = np.isin(
        raw_segment_grid,
        sorted(structural_ids),
    )
    center_plane = (
        infer_structuralization_center_plane(
            structural_source_mask,
            symmetry_axis,
        )
    )
    (
        structural_grid,
        repair_audit_df,
    ) = apply_confirmed_structural_symmetry_repairs(
        structural_grid,
        center_plane,
        symmetry_axis,
        config,
    )

    segment_summary_rows = []
    active_ids = []
    dropped_ids = []
    minimum_required_source = int(
        config.get(
            "minimum_source_voxels_to_require_retention",
            4,
        )
    )
    all_segment_checks = []

    for segment_id in sorted(
        structural_ids
    ):
        raw_mask = (
            raw_segment_grid
            == segment_id
        )
        final_mask = (
            structural_grid
            == segment_id
        )
        raw_count = int(
            raw_mask.sum()
        )
        final_count = int(
            final_mask.sum()
        )
        retained_count = int(
            (raw_mask & final_mask).sum()
        )
        added_count = int(
            (final_mask & ~raw_mask).sum()
        )
        removed_count = int(
            (raw_mask & ~final_mask).sum()
        )
        exact_footprint = (
            exact_lattice_mask(
                final_mask
            )
            if final_count
            else True
        )
        invalid_runs = catalog_run_audit(
            final_mask,
            allowed_heights,
        )
        component_sizes = (
            connected_component_sizes(
                final_mask
            )
            if final_count
            else []
        )
        connected = (
            len(component_sizes) <= 1
        )
        retention_required = (
            raw_count
            >= minimum_required_source
        )
        retained_as_active = (
            final_count > 0
        )
        segment_valid = bool(
            (
                retained_as_active
                or not retention_required
            )
            and exact_footprint
            and not invalid_runs
            and connected
        )

        if retained_as_active:
            active_ids.append(
                segment_id
            )
        else:
            dropped_ids.append(
                segment_id
            )

        all_segment_checks.append(
            segment_valid
        )
        segment_summary_rows.append({
            "segment_id": segment_id,
            "segment_label": (
                planner_segment_labels.get(
                    segment_id,
                    "unknown",
                )
            ),
            "raw_voxel_count": (
                raw_count
            ),
            "structuralized_voxel_count": (
                final_count
            ),
            "retained_raw_voxel_count": (
                retained_count
            ),
            "source_retention_ratio": (
                retained_count
                / max(raw_count, 1)
            ),
            "added_lattice_voxel_count": (
                added_count
            ),
            "removed_source_voxel_count": (
                removed_count
            ),
            "exact_2x2_footprint": (
                exact_footprint
            ),
            "invalid_catalog_run_count": (
                len(invalid_runs)
            ),
            "connected_component_count": (
                len(component_sizes)
            ),
            "largest_component_voxel_count": (
                component_sizes[0]
                if component_sizes
                else 0
            ),
            "retention_required": (
                retention_required
            ),
            "active_after_structuralization": (
                retained_as_active
            ),
            "segment_gate_valid": (
                segment_valid
            ),
        })

    combined_grid = (
        structural_grid.copy()
    )
    for functional_id in sorted(
        functional_ids
    ):
        functional_mask = (
            raw_segment_grid
            == functional_id
        )
        combined_grid[
            functional_mask
        ] = functional_id

    repair_valid = bool(
        repair_audit_df.empty
        or repair_audit_df[
            "status"
        ].isin([
            "applied",
            "not_applied",
        ]).all()
    )
    gate_valid = bool(
        all(all_segment_checks)
        and repair_valid
        and all(
            exact_lattice_mask(
                structural_grid
                == segment_id
            )
            for segment_id in active_ids
        )
    )

    return {
        "combined_grid": combined_grid,
        "structural_grid": (
            structural_grid
        ),
        "functional_reservation_mask": (
            functional_reservation
        ),
        "ownership_audit_df": (
            pd.DataFrame(
                ownership_rows
            )
        ),
        "segment_summary_df": (
            pd.DataFrame(
                segment_summary_rows
            )
        ),
        "symmetry_repair_audit_df": (
            repair_audit_df
        ),
        "active_structural_segment_ids": (
            sorted(active_ids)
        ),
        "dropped_structural_segment_ids": (
            sorted(dropped_ids)
        ),
        "gate_valid": gate_valid,
        "center_plane": float(
            center_plane
        ),
        "allowed_heights": (
            allowed_heights
        ),
    }


def structuralization_delta_figure(
    raw_segment_grid,
    structural_grid,
):
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

# ------------------------------------------------------------------
# Lattice-offset search
# ------------------------------------------------------------------

def align_grid_to_lattice_offset(raw_grid, offset_x, offset_y):
    raw_grid = np.asarray(raw_grid, dtype=int)
    offset_x = int(offset_x)
    offset_y = int(offset_y)

    high_x = (2 - ((raw_grid.shape[0] + offset_x) % 2)) % 2
    high_y = (2 - ((raw_grid.shape[1] + offset_y) % 2)) % 2

    aligned = np.pad(
        raw_grid,
        (
            (offset_x, high_x),
            (offset_y, high_y),
            (0, 0),
        ),
        mode="constant",
        constant_values=0,
    )
    transform = {
        "offset_x": offset_x,
        "offset_y": offset_y,
        "low_padding": [offset_x, offset_y, 0],
        "high_padding": [high_x, high_y, 0],
        "source_shape": list(raw_grid.shape),
        "aligned_shape": list(aligned.shape),
    }
    return aligned, transform


def structuralization_candidate_metrics(result):
    summary = result["segment_summary_df"]
    return {
        "gate_valid": bool(result["gate_valid"]),
        "active_segment_count": int(
            len(result["active_structural_segment_ids"])
        ),
        "retained_source_voxel_count": int(
            summary.get(
                "retained_raw_voxel_count",
                pd.Series(dtype=int),
            ).sum()
        ),
        "added_lattice_voxel_count": int(
            summary.get(
                "added_lattice_voxel_count",
                pd.Series(dtype=int),
            ).sum()
        ),
        "removed_source_voxel_count": int(
            summary.get(
                "removed_source_voxel_count",
                pd.Series(dtype=int),
            ).sum()
        ),
        "invalid_catalog_run_count": int(
            summary.get(
                "invalid_catalog_run_count",
                pd.Series(dtype=int),
            ).sum()
        ),
        "disconnected_segment_count": int(
            (
                summary.get(
                    "connected_component_count",
                    pd.Series(dtype=int),
                ) > 1
            ).sum()
        ),
    }


def structuralization_candidate_objective(metrics, transform):
    total_padding = int(
        sum(transform["low_padding"])
        + sum(transform["high_padding"])
    )
    return (
        int(metrics["gate_valid"]),
        int(metrics["active_segment_count"]),
        int(metrics["retained_source_voxel_count"]),
        -int(metrics["invalid_catalog_run_count"]),
        -int(metrics["disconnected_segment_count"]),
        -int(metrics["added_lattice_voxel_count"]),
        -int(metrics["removed_source_voxel_count"]),
        -total_padding,
        -int(transform["offset_x"]),
        -int(transform["offset_y"]),
    )


def search_structuralization_lattice_offsets(
    raw_segment_grid,
    structural_segment_ids,
    functional_target_segment_ids,
):
    config = STRUCTURALIZATION_CONFIG
    candidates = config.get(
        "lattice_offset_candidates",
        [[0, 0], [0, 1], [1, 0], [1, 1]],
    )
    if not config.get("lattice_offset_search_enabled", True):
        candidates = [[0, 0]]

    evaluated = []
    for offset in candidates:
        offset_x, offset_y = (
            int(offset[0]),
            int(offset[1]),
        )
        aligned_grid, transform = align_grid_to_lattice_offset(
            raw_segment_grid,
            offset_x,
            offset_y,
        )
        result = structuralize_segment_grid(
            aligned_grid,
            structural_segment_ids,
            functional_target_segment_ids,
        )
        metrics = structuralization_candidate_metrics(result)
        objective = structuralization_candidate_objective(
            metrics,
            transform,
        )
        evaluated.append({
            "offset_x": offset_x,
            "offset_y": offset_y,
            "transform": transform,
            "aligned_raw_grid": aligned_grid,
            "result": result,
            "metrics": metrics,
            "objective": objective,
        })

    evaluated.sort(
        key=lambda item: item["objective"],
        reverse=True,
    )
    selected = evaluated[0]

    audit_rows = []
    for item in evaluated:
        audit_rows.append({
            "offset_x": item["offset_x"],
            "offset_y": item["offset_y"],
            **item["metrics"],
            "low_padding": item["transform"]["low_padding"],
            "high_padding": item["transform"]["high_padding"],
            "aligned_shape": item["transform"]["aligned_shape"],
            "selected": bool(item is selected),
            "objective": list(item["objective"]),
        })

    selected_result = dict(selected["result"])
    selected_result["aligned_raw_grid"] = selected["aligned_raw_grid"]
    selected_result["lattice_transform"] = selected["transform"]
    selected_result["lattice_offset_audit_df"] = pd.DataFrame(audit_rows)
    return selected_result


# ------------------------------------------------------------------
# Exactify accepted structural symmetry pairs before block packing
# ------------------------------------------------------------------

def symmetry_exactification_source_score(
    candidate_grid,
    aligned_source_grid,
    segment_a,
    segment_b,
):
    score = 0
    added = 0
    removed = 0
    for segment_id in [int(segment_a), int(segment_b)]:
        candidate_mask = candidate_grid == segment_id
        source_mask = aligned_source_grid == segment_id
        score += int((candidate_mask & source_mask).sum())
        added += int((candidate_mask & ~source_mask).sum())
        removed += int((source_mask & ~candidate_mask).sum())
    return score, added, removed


def exactify_accepted_structural_symmetry_pairs(
    structural_grid,
    aligned_source_grid,
    accepted_pairs,
    center_plane,
):
    config = TASK_CONTEXT.get("symmetry", {})
    if not config.get("auto_exactify_accepted_pairs", True):
        return structural_grid.copy(), pd.DataFrame()

    repaired = structural_grid.copy()
    audit_rows = []
    require_conflict_free = bool(
        config.get("auto_exactify_require_conflict_free", True)
    )

    for pair in accepted_pairs:
        segment_a = int(pair["segment_a"])
        segment_b = int(pair["segment_b"])
        mask_a = repaired == segment_a
        mask_b = repaired == segment_b
        mirrored_a = mirror_mask(
            mask_a,
            SYMMETRY_AXIS_INDEX,
            center_plane,
        )
        current_iou = mask_iou(mirrored_a, mask_b)

        row = {
            "pair_id": pair["pair_id"],
            "segment_a": segment_a,
            "segment_b": segment_b,
            "source_mirror_iou": float(pair["source_mirror_iou"]),
            "before_structural_mirror_iou": float(current_iou),
            "status": "already_exact",
            "template_segment_id": None,
            "partner_segment_id": None,
            "conflict_voxel_count": 0,
            "after_structural_mirror_iou": float(current_iou),
        }

        if np.array_equal(mirrored_a, mask_b):
            audit_rows.append(row)
            continue

        candidates = []
        for template_id, partner_id in [
            (segment_a, segment_b),
            (segment_b, segment_a),
        ]:
            template_mask = repaired == template_id
            mirrored_template = mirror_mask(
                template_mask,
                SYMMETRY_AXIS_INDEX,
                center_plane,
            )
            conflict_mask = (
                mirrored_template
                & (repaired > 0)
                & (repaired != partner_id)
            )
            conflict_count = int(conflict_mask.sum())
            if require_conflict_free and conflict_count > 0:
                continue

            candidate_grid = repaired.copy()
            candidate_grid[candidate_grid == partner_id] = 0
            candidate_grid[mirrored_template] = partner_id
            source_score, added, removed = (
                symmetry_exactification_source_score(
                    candidate_grid,
                    aligned_source_grid,
                    segment_a,
                    segment_b,
                )
            )
            candidates.append({
                "template_segment_id": template_id,
                "partner_segment_id": partner_id,
                "grid": candidate_grid,
                "conflict_voxel_count": conflict_count,
                "source_retained_score": source_score,
                "added_geometry": added,
                "removed_source_geometry": removed,
                "objective": (
                    source_score,
                    -removed,
                    -added,
                    -template_id,
                ),
            })

        if not candidates:
            row["status"] = "blocked_by_conflict"
            audit_rows.append(row)
            continue

        selected = max(candidates, key=lambda item: item["objective"])
        repaired = selected["grid"]
        template_id = int(selected["template_segment_id"])
        partner_id = int(selected["partner_segment_id"])
        final_iou = mask_iou(
            mirror_mask(
                repaired == template_id,
                SYMMETRY_AXIS_INDEX,
                center_plane,
            ),
            repaired == partner_id,
        )
        row.update({
            "status": "exactified",
            "template_segment_id": template_id,
            "partner_segment_id": partner_id,
            "conflict_voxel_count": int(
                selected["conflict_voxel_count"]
            ),
            "source_retained_score": int(
                selected["source_retained_score"]
            ),
            "added_geometry": int(selected["added_geometry"]),
            "removed_source_geometry": int(
                selected["removed_source_geometry"]
            ),
            "after_structural_mirror_iou": float(final_iou),
        })
        audit_rows.append(row)

    return repaired, pd.DataFrame(audit_rows)


# Shared static-rendering helpers.
# These shared helpers are used by static reference views and
# their definitions.

def get_face_center(block, face):
    x, y, z = (
        float(value)
        for value in block.position
    )
    dx, dy, dz = (
        float(value)
        for value in block.size
    )
    centers = {
        "+X": (
            x + dx,
            y + dy / 2.0,
            z + dz / 2.0,
        ),
        "-X": (
            x,
            y + dy / 2.0,
            z + dz / 2.0,
        ),
        "+Y": (
            x + dx / 2.0,
            y + dy,
            z + dz / 2.0,
        ),
        "-Y": (
            x + dx / 2.0,
            y,
            z + dz / 2.0,
        ),
        "+Z": (
            x + dx / 2.0,
            y + dy / 2.0,
            z + dz,
        ),
        "-Z": (
            x + dx / 2.0,
            y + dy / 2.0,
            z,
        ),
    }
    if face not in centers:
        raise ValueError(
            f"Unsupported block face: {face}"
        )
    return centers[face]


def get_face_normal(face):
    normals = {
        "+X": (1.0, 0.0, 0.0),
        "-X": (-1.0, 0.0, 0.0),
        "+Y": (0.0, 1.0, 0.0),
        "-Y": (0.0, -1.0, 0.0),
        "+Z": (0.0, 0.0, 1.0),
        "-Z": (0.0, 0.0, -1.0),
    }
    if face not in normals:
        raise ValueError(
            f"Unsupported block face: {face}"
        )
    return normals[face]


def draw_block(
    axis,
    block,
    *,
    alpha=0.90,
    edgecolor="black",
    linewidth=0.8,
):
    """Draw one catalog-colored rectangular block on a Matplotlib 3D axis."""
    x, y, z = (
        float(value)
        for value in block.position
    )
    dx, dy, dz = (
        float(value)
        for value in block.size
    )

    vertices = np.asarray([
        [x, y, z],
        [x + dx, y, z],
        [x + dx, y + dy, z],
        [x, y + dy, z],
        [x, y, z + dz],
        [x + dx, y, z + dz],
        [x + dx, y + dy, z + dz],
        [x, y + dy, z + dz],
    ])

    faces = [
        [vertices[index] for index in [0, 1, 2, 3]],
        [vertices[index] for index in [4, 5, 6, 7]],
        [vertices[index] for index in [0, 1, 5, 4]],
        [vertices[index] for index in [2, 3, 7, 6]],
        [vertices[index] for index in [1, 2, 6, 5]],
        [vertices[index] for index in [0, 3, 7, 4]],
    ]

    catalog_color = (
        np.asarray(
            block_rgb(block),
            dtype=float,
        )
        / 255.0
    )

    collection = Poly3DCollection(
        faces,
        facecolors=[catalog_color],
        edgecolors=edgecolor,
        linewidths=float(linewidth),
        alpha=float(alpha),
        zsort="average",
    )
    axis.add_collection3d(collection)
    return collection



# ------------------------------------------------------------------
# Block, face, validated-step, and assembly views
# ------------------------------------------------------------------


# Compact inline rendering.
# Saved validation PNGs keep their existing resolution; these settings only
# control figures displayed by an interactive development client.

def reference_inline_setting(name, default):
    return VISUALIZATION_CONFIG.get(
        name,
        default,
    )


def reference_inline_figsize():
    value = reference_inline_setting(
        "reference_inline_figsize",
        [7.0, 5.8],
    )
    return tuple(
        float(component)
        for component in value
    )


def reference_new_inline_figure():
    return plt.figure(
        figsize=reference_inline_figsize(),
        dpi=float(
            reference_inline_setting(
                "reference_inline_dpi",
                90,
            )
        ),
    )


def reference_compact_axis_style(
    axis,
    grid_size,
):
    label_size = float(
        reference_inline_setting(
            "reference_inline_label_fontsize",
            8,
        )
    )
    tick_size = float(
        reference_inline_setting(
            "reference_inline_tick_fontsize",
            7,
        )
    )

    axis.set_xlim(0, grid_size)
    axis.set_ylim(0, grid_size)
    axis.set_zlim(0, grid_size)
    axis.set_box_aspect((1, 1, 1))
    axis.set_xlabel(
        "X",
        fontsize=label_size,
        labelpad=2,
    )
    axis.set_ylabel(
        "Y",
        fontsize=label_size,
        labelpad=2,
    )
    axis.set_zlabel(
        "Z",
        fontsize=label_size,
        labelpad=2,
    )
    axis.tick_params(
        axis="both",
        which="major",
        labelsize=tick_size,
        pad=0,
    )


def reference_compact_title(
    axis,
    title,
    *,
    color="black",
):
    axis.set_title(
        title,
        color=color,
        fontsize=float(
            reference_inline_setting(
                "reference_inline_title_fontsize",
                10,
            )
        ),
        pad=5,
    )


def reference_finish_inline_figure(
    figure,
):
    figure.tight_layout(
        pad=float(
            reference_inline_setting(
                "reference_inline_layout_pad",
                0.45,
            )
        )
    )
    plt.show()
    return figure


def reference_effective_block_alpha(
    block,
    requested_alpha,
    *,
    prior=False,
):
    alpha = float(requested_alpha)
    if not block_is_blue_or_green(block):
        return alpha

    setting_name = (
        "reference_blue_green_prior_min_alpha"
        if prior
        else "reference_blue_green_min_alpha"
    )
    default_value = (
        0.28
        if prior
        else 0.93
    )
    return max(
        alpha,
        float(
            reference_inline_setting(
                setting_name,
                default_value,
            )
        ),
    )


def reference_draw_face_markers(
    axis,
    blocks,
    marker_size=None,
    *,
    context_blocks=None,
):
    blocks = list(blocks)
    context_blocks = list(
        context_blocks
        if context_blocks is not None
        else blocks
    )
    exposed_only = bool(
        reference_inline_setting(
            "reference_face_markers_exposed_only",
            True,
        )
    )
    marker_offset = float(
        reference_inline_setting(
            "reference_marker_offset",
            0.08,
        )
    )
    edge_width = float(
        reference_inline_setting(
            "reference_marker_edge_width",
            1.2,
        )
    )
    seen = {
        "male": set(),
        "female": set(),
    }

    for block in blocks:
        for face in ALL_FACES:
            face_type = actual_block_face_type(
                block,
                face,
            )
            if face_type not in {
                "male",
                "female",
            }:
                continue
            if (
                exposed_only
                and not face_center_is_exposed(
                    block,
                    face,
                    context_blocks,
                )
            ):
                continue

            x, y, z = get_face_center(
                block,
                face,
            )
            nx, ny, nz = get_face_normal(
                face
            )
            x += nx * marker_offset
            y += ny * marker_offset
            z += nz * marker_offset

            key = (
                round(x, 5),
                round(y, 5),
                round(z, 5),
            )
            if key in seen[face_type]:
                continue
            seen[face_type].add(key)

            if face_type == "male":
                size = float(
                    reference_inline_setting(
                        "reference_male_marker_size",
                        marker_size or 42,
                    )
                )
                axis.scatter(
                    [x],
                    [y],
                    [z],
                    s=size,
                    facecolors="red",
                    edgecolors="black",
                    linewidths=edge_width,
                    depthshade=False,
                    zorder=1000,
                )
            else:
                size = float(
                    reference_inline_setting(
                        "reference_female_marker_size",
                        marker_size or 54,
                    )
                )
                axis.scatter(
                    [x],
                    [y],
                    [z],
                    s=size,
                    facecolors=str(
                        reference_inline_setting(
                            "reference_female_marker_fill",
                            "white",
                        )
                    ),
                    edgecolors="dodgerblue",
                    linewidths=edge_width * 1.25,
                    depthshade=False,
                    zorder=1001,
                )


def reference_block_type_view(blocks, grid_size, title):
    voxel = np.zeros(
        (grid_size, grid_size, grid_size),
        dtype=bool,
    )
    colors = np.zeros(
        (grid_size, grid_size, grid_size, 4),
        dtype=float,
    )
    for block in blocks:
        x, y, z = block.position
        dx, dy, dz = block.size
        voxel[x:x + dx, y:y + dy, z:z + dz] = True
        rgb = block_rgb(block) / 255.0
        colors[x:x + dx, y:y + dy, z:z + dz, :3] = rgb
        colors[x:x + dx, y:y + dy, z:z + dz, 3] = 0.96

    figure = reference_new_inline_figure()
    axis = figure.add_subplot(111, projection="3d")
    axis.voxels(
        voxel,
        facecolors=colors,
        edgecolor="black",
        linewidth=0.35,
    )
    reference_compact_axis_style(
        axis,
        grid_size,
    )
    reference_compact_title(
        axis,
        title,
    )
    axis.view_init(
        elev=30,
        azim=45,
    )
    reference_finish_inline_figure(
        figure
    )
    return figure, axis


def reference_face_connection_view(blocks, grid_size, title):
    figure = reference_new_inline_figure()
    axis = figure.add_subplot(111, projection="3d")
    for block in blocks:
        draw_block(
            axis,
            block,
            alpha=reference_effective_block_alpha(
                block,
                float(
                    reference_inline_setting(
                        "reference_face_connection_block_alpha",
                        1.0,
                    )
                ),
            ),
            edgecolor="black",
        )

    neighbor_map = build_neighbor_map(blocks, grid_size)
    lookup = {
        int(block.block_id): block
        for block in blocks
    }
    drawn_edges = set()
    for block in blocks:
        block_id = int(block.block_id)
        center_a = tuple(
            float(block.position[axis_index])
            + float(block.size[axis_index]) / 2.0
            for axis_index in range(3)
        )
        for relationship, color, linestyle, linewidth in [
            ("support", "green", "-", 1.8),
            ("side", "gray", "--", 0.8),
        ]:
            for neighbor_id in neighbor_map.get(
                block_id, {}
            ).get(relationship, []):
                edge_key = tuple(sorted((block_id, int(neighbor_id))))
                if edge_key in drawn_edges:
                    continue
                drawn_edges.add(edge_key)
                neighbor = lookup.get(int(neighbor_id))
                if neighbor is None:
                    continue
                center_b = tuple(
                    float(neighbor.position[axis_index])
                    + float(neighbor.size[axis_index]) / 2.0
                    for axis_index in range(3)
                )
                axis.plot(
                    [center_a[0], center_b[0]],
                    [center_a[1], center_b[1]],
                    [center_a[2], center_b[2]],
                    color=color,
                    linestyle=linestyle,
                    linewidth=(
                        linewidth
                        * float(
                            reference_inline_setting(
                                "reference_inline_line_width_scale",
                                0.70,
                            )
                        )
                    ),
                )

    reference_draw_face_markers(
        axis,
        blocks,
        context_blocks=blocks,
    )
    reference_compact_axis_style(
        axis,
        grid_size,
    )
    reference_compact_title(
        axis,
        title,
    )
    axis.view_init(
        elev=25,
        azim=45,
    )
    reference_finish_inline_figure(
        figure
    )
    return figure, axis


def reference_validated_step_view(
    result,
    step_index,
    grid_size,
):
    planning = result["planning_result"]
    validation = result["validation"]
    blocks = planning["blocks"]
    steps = planning["instruction_steps"]
    current_blocks = list(steps[step_index]["blocks"])
    current_ids = {
        int(block.block_id)
        for block in current_blocks
    }
    lookup = {
        int(block.block_id): block
        for block in blocks
    }
    accepted_before = set(
        validation["accepted_before_by_step"].get(
            step_index,
            [],
        )
    )
    step_row = validation["step_rows"][step_index]
    step_number = int(step_row["step"])

    figure = reference_new_inline_figure()
    axis = figure.add_subplot(111, projection="3d")

    for block_id in sorted(accepted_before):
        block = lookup.get(block_id)
        if block is not None:
            draw_block(
                axis,
                block,
                alpha=reference_effective_block_alpha(
                    block,
                    float(
                        reference_inline_setting(
                            "reference_inline_prior_block_alpha",
                            0.16,
                        )
                    ),
                    prior=True,
                ),
                edgecolor="gray",
            )

    for block in current_blocks:
        info = validation["block_validation"].get(
            int(block.block_id),
            {"valid": False, "direct_conflict": False},
        )
        edgecolor = (
            "green"
            if info.get("valid", False)
            else (
                "crimson"
                if info.get("direct_conflict", False)
                else "darkorange"
            )
        )
        draw_block(
            axis,
            block,
            alpha=reference_effective_block_alpha(
                block,
                float(
                    reference_inline_setting(
                        "reference_inline_current_block_alpha",
                        0.78,
                    )
                ),
                prior=False,
            ),
            edgecolor=edgecolor,
        )

    visible_context_blocks = [
        block_lookup[block_id]
        for block_id in sorted(
            accepted_before
            | current_ids
        )
        if block_id in block_lookup
    ]
    reference_draw_face_markers(
        axis,
        current_blocks,
        context_blocks=visible_context_blocks,
    )

    for contact in validation.get("contact_rows", []):
        if int(contact["step"]) != step_number:
            continue
        if contact.get("scope") not in {
            "new_to_prior",
            "within_new_component",
        }:
            continue
        block_a = lookup.get(int(contact["block_a"]))
        block_b = lookup.get(int(contact["block_b"]))
        if block_a is None or block_b is None:
            continue
        if (
            contact.get("scope") == "within_new_component"
            and (
                int(contact["block_a"]) not in current_ids
                or int(contact["block_b"]) not in current_ids
            )
        ):
            continue
        if contact.get("face_a") is None or contact.get("face_b") is None:
            continue

        point_a = get_face_center(block_a, contact["face_a"])
        point_b = get_face_center(block_b, contact["face_b"])
        status = contact.get("contact_status")
        if status == "male_to_female_lock":
            color, width, style = "limegreen", 3.0, "-"
        elif status == "female_to_female_nonlocking":
            color, width, style = "gray", 1.2, "--"
        elif status in {
            "male_to_male_conflict",
            "geometric_overlap_conflict",
        }:
            color, width, style = "crimson", 3.0, "-"
        else:
            color, width, style = "orange", 1.2, ":"
        axis.plot(
            [point_a[0], point_b[0]],
            [point_a[1], point_b[1]],
            [point_a[2], point_b[2]],
            color=color,
            linewidth=(
                width
                * float(
                    reference_inline_setting(
                        "reference_inline_line_width_scale",
                        0.70,
                    )
                )
            ),
            linestyle=style,
        )

    status = str(
        step_row["step_status"]
    ).upper()
    title_color = {
        "VALID": "green",
        "PARTIAL": "darkorange",
        "INVALID": "crimson",
    }.get(
        status,
        "black",
    )
    reference_compact_title(
        axis,
        (
            f"Segment {result['segment_id']} — "
            f"Validated Step {step_number}: "
            f"Y={step_row['row']} — {status}"
        ),
        color=title_color,
    )
    axis.text2D(
        0.01,
        0.985,
        (
            f"Valid: {step_row['valid_components']}  "
            f"Invalid: {step_row['invalid_components']}\n"
            f"Locks prior: {step_row['locks_to_accepted_prior']}  "
            f"Area: {step_row['lock_area_to_accepted_prior']}\n"
            f"Internal area: {step_row['internal_lock_area']}  "
            f"Conflicts: {step_row['male_male_or_overlap_conflicts']}\n"
            f"Accepted: {step_row['accepted_block_ids'] or 'none'}\n"
            f"Rejected: {step_row['rejected_block_ids'] or 'none'}"
        ),
        transform=axis.transAxes,
        verticalalignment="top",
        fontsize=float(
            reference_inline_setting(
                "reference_inline_validation_fontsize",
                7,
            )
        ),
        linespacing=1.05,
        bbox={
            "facecolor": "white",
            "alpha": 0.88,
            "pad": 2.5,
        },
    )
    reference_compact_axis_style(
        axis,
        grid_size,
    )
    axis.view_init(
        elev=25,
        azim=45,
    )
    reference_finish_inline_figure(
        figure
    )
    return figure, axis


def reference_final_object_view(blocks, grid_size, title):
    figure = reference_new_inline_figure()
    axis = figure.add_subplot(111, projection="3d")
    for block in blocks:
        draw_block(
            axis,
            block,
            alpha=reference_effective_block_alpha(
                block,
                float(
                    reference_inline_setting(
                        "reference_final_block_alpha",
                        1.0,
                    )
                ),
            ),
            edgecolor="black",
        )
    reference_draw_face_markers(
        axis,
        blocks,
        context_blocks=blocks,
    )
    exposed = cumulative_exposed_male_area(
        blocks,
        frontier_row=None,
    )
    reference_compact_title(
        axis,
        (
            f"{title} "
            f"(exposed male area={exposed})"
        ),
    )
    reference_compact_axis_style(
        axis,
        grid_size,
    )
    axis.view_init(
        elev=25,
        azim=45,
    )
    reference_finish_inline_figure(
        figure
    )
    return figure, axis



# ------------------------------------------------------------------
# Reference diagnostic views
# ------------------------------------------------------------------

def reference_setting(name, default):
    return VISUALIZATION_CONFIG.get(
        name,
        default,
    )


def reference_block_center(block):
    """Return the geometric center of a rectangular catalog block."""
    return tuple(
        float(block.position[axis])
        + float(block.size[axis]) / 2.0
        for axis in range(3)
    )


def reference_solid_block_overview(
    blocks,
    grid_size,
    title="Solid Catalog-Colored Block Model",
    elev=30,
    azim=45,
):
    """Opaque block overview with no face markers."""
    voxel = np.zeros(
        (grid_size, grid_size, grid_size),
        dtype=bool,
    )
    colors = np.zeros(
        (grid_size, grid_size, grid_size, 3),
        dtype=float,
    )

    for block in blocks:
        x, y, z = (
            int(value)
            for value in block.position
        )
        dx, dy, dz = (
            int(value)
            for value in block.size
        )
        voxel[
            x:x + dx,
            y:y + dy,
            z:z + dz,
        ] = True
        colors[
            x:x + dx,
            y:y + dy,
            z:z + dz,
        ] = block_rgb(block) / 255.0

    figure = plt.figure(
        figsize=tuple(
            reference_setting(
                "reference_solid_figsize",
                [6.0, 5.2],
            )
        )
    )
    axis = figure.add_subplot(
        111,
        projection="3d",
    )
    axis.voxels(
        voxel,
        facecolors=colors,
        edgecolor=reference_setting(
            "reference_solid_edgecolor",
            "black",
        ),
        linewidth=float(
            reference_setting(
                "reference_solid_linewidth",
                0.28,
            )
        ),
    )
    axis.set_xlim(0, grid_size)
    axis.set_ylim(0, grid_size)
    axis.set_zlim(0, grid_size)
    axis.set_box_aspect((1, 1, 1))
    axis.set_xlabel("X")
    axis.set_ylabel("Y")
    axis.set_zlabel("Z")
    axis.view_init(
        elev=elev,
        azim=azim,
    )
    axis.set_title(title)
    plt.tight_layout()
    plt.show()
    return figure, axis


def reference_face_diagnostic(
    blocks,
    neighbor_map,
    grid_size,
    title="Male/Female Faces and Structural Contacts",
    elev=25,
    azim=45,
):
    """Translucent face/connection diagnostic, separate from the solid view."""
    figure = plt.figure(
        figsize=tuple(
            reference_setting(
                "reference_face_figsize",
                [7.0, 5.8],
            )
        )
    )
    axis = figure.add_subplot(
        111,
        projection="3d",
    )
    block_alpha = float(
        reference_setting(
            "reference_face_block_alpha",
            0.22,
        )
    )

    for block in blocks:
        muted_color = (
            0.60 * (
                block_rgb(block)
                / 255.0
            )
            + 0.40
        )
        x, y, z = (
            float(value)
            for value in block.position
        )
        dx, dy, dz = (
            float(value)
            for value in block.size
        )
        axis.bar3d(
            x,
            y,
            z,
            dx,
            dy,
            dz,
            color=muted_color,
            edgecolor=(0, 0, 0, 0),
            linewidth=0.0,
            alpha=block_alpha,
            shade=True,
        )

        for face in ALL_FACES:
            face_type = actual_block_face_type(
                block,
                face,
            )
            if face_type not in {
                "male",
                "female",
            }:
                continue
            center = get_face_center(
                block,
                face,
            )
            axis.scatter(
                [center[0]],
                [center[1]],
                [center[2]],
                color=(
                    "red"
                    if face_type == "male"
                    else "dodgerblue"
                ),
                s=float(
                    reference_setting(
                        (
                            "reference_face_male_marker_size"
                            if face_type == "male"
                            else "reference_face_female_marker_size"
                        ),
                        (
                            40
                            if face_type == "male"
                            else 44
                        ),
                    )
                ),
                edgecolors="black",
                linewidths=0.45,
                depthshade=False,
                alpha=1.0,
                zorder=1000,
            )

    block_lookup = {
        int(block.block_id): block
        for block in blocks
    }
    drawn_edges = set()

    for block in blocks:
        block_id = int(block.block_id)
        center_a = reference_block_center(block)
        neighbor_info = neighbor_map.get(
            block_id,
            {},
        )

        for category, color, width, style in [
            ("support", "green", 1.0, "-"),
            ("side", "gray", 0.55, "--"),
        ]:
            for neighbor_id in neighbor_info.get(
                category,
                [],
            ):
                neighbor_id = int(neighbor_id)
                edge_key = (
                    min(block_id, neighbor_id),
                    max(block_id, neighbor_id),
                    category,
                )
                if edge_key in drawn_edges:
                    continue
                neighbor = block_lookup.get(
                    neighbor_id
                )
                if neighbor is None:
                    continue
                drawn_edges.add(edge_key)
                center_b = reference_block_center(neighbor)
                axis.plot(
                    [center_a[0], center_b[0]],
                    [center_a[1], center_b[1]],
                    [center_a[2], center_b[2]],
                    color=color,
                    linewidth=width,
                    linestyle=style,
                )

    axis.set_xlim(0, grid_size)
    axis.set_ylim(0, grid_size)
    axis.set_zlim(0, grid_size)
    axis.set_box_aspect((1, 1, 1))
    axis.set_xlabel("X")
    axis.set_ylabel("Y")
    axis.set_zlabel("Z")
    axis.view_init(
        elev=elev,
        azim=azim,
    )
    axis.set_title(title)
    plt.tight_layout()
    plt.show()
    return figure, axis

def interactive_face_contact_figure(
    blocks,
    neighbor_map,
    grid_size,
    *,
    title=(
        "Interactive Male/Female Faces "
        "and Structural Contacts"
    ),
):
    """
    Rotatable mechanical-contact viewer.

    The scene bounds are derived from all displayed blocks, including negative
    coordinates used by the declared motion-connected subassembly. Contact lines are
    classified from actual face polarity, not from vertical/side location.
    """
    figure = go.Figure()
    blocks = list(
        blocks
    )

    block_opacity = float(
        VISUALIZATION_CONFIG.get(
            "interactive_face_contact_block_opacity",
            0.24,
        )
    )
    outline_opacity = float(
        VISUALIZATION_CONFIG.get(
            "interactive_face_contact_outline_opacity",
            0.42,
        )
    )
    outline_width = float(
        VISUALIZATION_CONFIG.get(
            "interactive_face_contact_outline_width",
            2.0,
        )
    )

    shown_families = set()
    for block in blocks:
        family = str(
            getattr(
                block,
                "block_family",
                "unknown",
            )
        )
        traces = block_traces(
            block,
            showlegend=(
                family
                not in shown_families
            ),
        )

        if family == "rotation_block":
            family_opacity = max(
                block_opacity,
                float(
                    VISUALIZATION_CONFIG.get(
                        "interactive_face_contact_rotation_block_opacity",
                        0.62,
                    )
                ),
            )
        elif "wheel" in family.lower():
            family_opacity = max(
                block_opacity,
                float(
                    VISUALIZATION_CONFIG.get(
                        "interactive_face_contact_wheel_opacity",
                        0.48,
                    )
                ),
            )
        else:
            family_opacity = block_opacity

        for trace in traces:
            trace = copy.deepcopy(
                trace
            )

            if isinstance(
                trace,
                go.Mesh3d,
            ):
                trace.opacity = (
                    family_opacity
                )
                trace.hovertext = (
                    block_hover(
                        block
                    )
                )
                trace.hoverinfo = "text"
                trace.name = family
                figure.add_trace(
                    trace
                )

            elif (
                isinstance(
                    trace,
                    go.Scatter3d,
                )
                and "lines"
                in str(
                    getattr(
                        trace,
                        "mode",
                        "",
                    )
                )
            ):
                trace.opacity = (
                    outline_opacity
                )
                trace.line.width = (
                    outline_width
                )
                trace.hoverinfo = "skip"
                trace.showlegend = False
                figure.add_trace(
                    trace
                )

        shown_families.add(
            family
        )

    male_rows = []
    female_rows = []

    for block in blocks:
        block_id = int(
            block.block_id
        )
        segment_id = getattr(
            block,
            "source_segment_id",
            None,
        )
        segment_name = getattr(
            block,
            "segment_name",
            getattr(
                block,
                "segment_display_name",
                None,
            ),
        )
        if (
            segment_name
            in {
                None,
                "",
                "None",
            }
            and segment_id
            is not None
        ):
            segment_name = (
                segment_display_name_by_id.get(
                    int(
                        segment_id
                    ),
                    (
                        f"Segment "
                        f"{int(segment_id)}"
                    ),
                )
            )

        for face in ALL_FACES:
            face_type = (
                actual_block_face_type(
                    block,
                    face,
                )
            )
            if face_type not in {
                "male",
                "female",
            }:
                continue

            center = tuple(
                float(
                    value
                )
                for value in get_face_center(
                    block,
                    face,
                )
            )
            row = {
                "center": center,
                "block_id": block_id,
                "block_family": str(
                    block.block_family
                ),
                "face": str(
                    face
                ),
                "segment_id": (
                    segment_id
                ),
                "segment_name": (
                    segment_name
                ),
            }
            if face_type == "male":
                male_rows.append(
                    row
                )
            else:
                female_rows.append(
                    row
                )

    def marker_hover(
        row,
        face_type,
    ):
        segment_id = row[
            "segment_id"
        ]
        segment_name = row[
            "segment_name"
        ]
        segment_text = (
            "not assigned"
            if segment_id
            is None
            else (
                f"{segment_name} "
                f"(segment "
                f"{int(segment_id)})"
            )
        )
        x, y, z = row[
            "center"
        ]
        return (
            f"<b>{face_type.title()} face</b><br>"
            f"Block ID: {row['block_id']}<br>"
            f"Family: {row['block_family']}<br>"
            f"Face: {row['face']}<br>"
            f"Segment: {segment_text}<br>"
            f"Center: "
            f"({x:.2f}, {y:.2f}, {z:.2f})"
        )

    if male_rows:
        figure.add_trace(
            go.Scatter3d(
                x=[
                    row[
                        "center"
                    ][
                        0
                    ]
                    for row
                    in male_rows
                ],
                y=[
                    row[
                        "center"
                    ][
                        1
                    ]
                    for row
                    in male_rows
                ],
                z=[
                    row[
                        "center"
                    ][
                        2
                    ]
                    for row
                    in male_rows
                ],
                mode="markers",
                marker={
                    "size": int(
                        VISUALIZATION_CONFIG.get(
                            (
                                "interactive_face_contact_"
                                "male_marker_size"
                            ),
                            5,
                        )
                    ),
                    "color": "red",
                    "opacity": 0.98,
                    "line": {
                        "color": "darkred",
                        "width": 1,
                    },
                },
                text=[
                    marker_hover(
                        row,
                        "male",
                    )
                    for row
                    in male_rows
                ],
                hoverinfo="text",
                name="Male faces",
                legendgroup=(
                    "face_markers"
                ),
                showlegend=True,
            )
        )

    if female_rows:
        figure.add_trace(
            go.Scatter3d(
                x=[
                    row[
                        "center"
                    ][
                        0
                    ]
                    for row
                    in female_rows
                ],
                y=[
                    row[
                        "center"
                    ][
                        1
                    ]
                    for row
                    in female_rows
                ],
                z=[
                    row[
                        "center"
                    ][
                        2
                    ]
                    for row
                    in female_rows
                ],
                mode="markers",
                marker={
                    "size": int(
                        VISUALIZATION_CONFIG.get(
                            (
                                "interactive_face_contact_"
                                "female_marker_size"
                            ),
                            5,
                        )
                    ),
                    "color": "dodgerblue",
                    "opacity": 0.98,
                    "line": {
                        "color": "navy",
                        "width": 1,
                    },
                },
                text=[
                    marker_hover(
                        row,
                        "female",
                    )
                    for row
                    in female_rows
                ],
                hoverinfo="text",
                name="Female faces",
                legendgroup=(
                    "face_markers"
                ),
                showlegend=True,
            )
        )

    contact_styles = {
        "locking": {
            "color": "green",
            "width": 6,
            "dash": "solid",
            "name": (
                "Male-to-female locks"
            ),
        },
        "nonlocking": {
            "color": "gray",
            "width": 3,
            "dash": "dash",
            "name": (
                "Nonlocking face contacts"
            ),
        },
        "conflict": {
            "color": "crimson",
            "width": 6,
            "dash": "solid",
            "name": "Contact conflicts",
        },
    }
    contact_rows = {
        category: []
        for category in (
            "locking",
            "nonlocking",
            "conflict",
        )
    }

    for index_a, block_a in enumerate(
        blocks
    ):
        for block_b in blocks[
            index_a
            + 1:
        ]:
            contact = (
                contact_status_between_blocks(
                    block_a,
                    block_b,
                )
            )
            if contact is None:
                continue

            status = str(
                contact.get(
                    "contact_status",
                    "",
                )
            )
            if status == "male_to_female_lock":
                category = "locking"
            elif status in {
                "male_to_male_conflict",
                "geometric_overlap_conflict",
            }:
                category = "conflict"
            else:
                category = "nonlocking"

            contact_rows[
                category
            ].append(
                {
                    "block_a": block_a,
                    "block_b": block_b,
                    "contact": contact,
                    "center_a": (
                        reference_block_center(
                            block_a
                        )
                    ),
                    "center_b": (
                        reference_block_center(
                            block_b
                        )
                    ),
                }
            )

    for category in (
        "locking",
        "nonlocking",
        "conflict",
    ):
        rows = contact_rows[
            category
        ]
        if not rows:
            continue

        x_values = []
        y_values = []
        z_values = []
        hover_values = []

        for row in rows:
            block_a = row[
                "block_a"
            ]
            block_b = row[
                "block_b"
            ]
            contact = row[
                "contact"
            ]
            center_a = row[
                "center_a"
            ]
            center_b = row[
                "center_b"
            ]
            hover_text = (
                f"<b>{contact.get('contact_status')}</b><br>"
                f"Block {int(block_a.block_id)} "
                f"({block_a.block_family})<br>"
                f"Block {int(block_b.block_id)} "
                f"({block_b.block_family})<br>"
                f"Faces: {contact.get('face_a')} / "
                f"{contact.get('face_b')}<br>"
                f"Contact area: "
                f"{contact.get('overlap_area')}"
            )

            x_values.extend(
                [
                    center_a[
                        0
                    ],
                    center_b[
                        0
                    ],
                    None,
                ]
            )
            y_values.extend(
                [
                    center_a[
                        1
                    ],
                    center_b[
                        1
                    ],
                    None,
                ]
            )
            z_values.extend(
                [
                    center_a[
                        2
                    ],
                    center_b[
                        2
                    ],
                    None,
                ]
            )
            hover_values.extend(
                [
                    hover_text,
                    hover_text,
                    None,
                ]
            )

        style = contact_styles[
            category
        ]
        figure.add_trace(
            go.Scatter3d(
                x=x_values,
                y=y_values,
                z=z_values,
                mode="lines",
                line={
                    "color": style[
                        "color"
                    ],
                    "width": style[
                        "width"
                    ],
                    "dash": style[
                        "dash"
                    ],
                },
                text=hover_values,
                hoverinfo="text",
                name=style[
                    "name"
                ],
                legendgroup=(
                    f"{category}_contacts"
                ),
                showlegend=True,
            )
        )

    padding = float(
        VISUALIZATION_CONFIG.get(
            "interactive_face_contact_bounds_padding",
            0.8,
        )
    )
    if blocks:
        minimum = np.min(
            np.asarray(
                [
                    block.position
                    for block in blocks
                ],
                dtype=float,
            ),
            axis=0,
        ) - padding
        maximum = np.max(
            np.asarray(
                [
                    np.asarray(
                        block.position,
                        dtype=float,
                    )
                    + np.asarray(
                        block.size,
                        dtype=float,
                    )
                    for block in blocks
                ],
                dtype=float,
            ),
            axis=0,
        ) + padding
    else:
        minimum = np.zeros(
            3,
            dtype=float,
        )
        maximum = np.full(
            3,
            float(
                grid_size
            ),
        )

    figure.update_layout(
        title=title,
        height=int(
            VISUALIZATION_CONFIG.get(
                (
                    "interactive_face_contact_"
                    "height"
                ),
                700,
            )
        ),
        margin={
            "l": 0,
            "r": 0,
            "t": 75,
            "b": 0,
        },
        scene={
            "xaxis": {
                "title": "X",
                "range": [
                    float(
                        minimum[
                            0
                        ]
                    ),
                    float(
                        maximum[
                            0
                        ]
                    ),
                ],
            },
            "yaxis": {
                "title": "Y",
                "range": [
                    float(
                        minimum[
                            1
                        ]
                    ),
                    float(
                        maximum[
                            1
                        ]
                    ),
                ],
            },
            "zaxis": {
                "title": "Z",
                "range": [
                    float(
                        minimum[
                            2
                        ]
                    ),
                    float(
                        maximum[
                            2
                        ]
                    ),
                ],
            },
            "aspectmode": "data",
            "camera": {
                "eye": {
                    "x": 1.45,
                    "y": 1.45,
                    "z": 1.10,
                },
            },
        },
        legend={
            "orientation": "h",
            "x": 0.0,
            "y": 1.04,
            "itemsizing": "constant",
        },
    )
    return figure



def reference_validated_step_view(
    result,
    step_index,
    grid_size,
):
    """
    Previous accepted rows are lightened and translucent. The current row is
    full-color and fully opaque.
    """
    planning = result[
        "planning_result"
    ]
    validation = result[
        "validation"
    ]
    blocks = list(
        planning[
            "blocks"
        ]
    )
    current_blocks = list(
        planning[
            "instruction_steps"
        ][
            step_index
        ][
            "blocks"
        ]
    )
    current_ids = {
        int(
            block.block_id
        )
        for block in current_blocks
    }
    block_lookup = {
        int(
            block.block_id
        ): block
        for block in blocks
    }
    accepted_before = set(
        validation[
            "accepted_before_by_step"
        ].get(
            step_index,
            [],
        )
    )
    step_row = validation[
        "step_rows"
    ][
        step_index
    ]
    step_number = int(
        step_row[
            "step"
        ]
    )
    build_axis = str(
        result.get(
            "selected_build_axis",
            "+Y",
        )
    )

    figure = plt.figure(
        figsize=tuple(
            reference_setting(
                "reference_step_figsize",
                [
                    7.0,
                    5.8,
                ],
            )
        )
    )
    axis = figure.add_subplot(
        111,
        projection="3d",
    )

    for block_id in sorted(
        accepted_before
    ):
        block = block_lookup.get(
            block_id
        )
        if block is not None:
            draw_block(
                axis,
                clone_block_for_progression_prior(
                    block
                ),
                alpha=float(
                    reference_setting(
                        "reference_step_prior_alpha",
                        0.28,
                    )
                ),
                edgecolor="gray",
                linewidth=0.65,
            )

    for block in current_blocks:
        info = validation[
            "block_validation"
        ].get(
            str(
                int(
                    block.block_id
                )
            ),
            validation[
                "block_validation"
            ].get(
                int(
                    block.block_id
                ),
                {
                    "valid": False,
                    "direct_conflict": False,
                },
            ),
        )
        edgecolor = (
            "green"
            if info.get(
                "valid",
                False,
            )
            else (
                "crimson"
                if info.get(
                    "direct_conflict",
                    False,
                )
                else "darkorange"
            )
        )
        draw_block(
            axis,
            block,
            alpha=float(
                reference_setting(
                    "reference_step_current_alpha",
                    1.0,
                )
            ),
            edgecolor=edgecolor,
            linewidth=1.35,
        )

    marker_size = float(
        reference_setting(
            "reference_step_marker_size",
            80,
        )
    )
    marker_offset = float(
        reference_setting(
            "reference_step_marker_offset",
            0.10,
        )
    )

    for block in current_blocks:
        for face in ALL_FACES:
            face_type = actual_block_face_type(
                block,
                face,
            )
            if face_type not in {
                "male",
                "female",
            }:
                continue
            x, y, z = get_face_center(
                block,
                face,
            )
            nx, ny, nz = get_face_normal(
                face
            )
            x += nx * marker_offset
            y += ny * marker_offset
            z += nz * marker_offset
            axis.scatter(
                [x],
                [y],
                [z],
                color=(
                    "red"
                    if face_type == "male"
                    else "dodgerblue"
                ),
                s=marker_size,
                edgecolors="black",
                linewidths=0.4,
                depthshade=False,
                alpha=1.0,
                zorder=1000,
            )

    for contact in validation.get(
        "contact_rows",
        [],
    ):
        if int(
            contact[
                "step"
            ]
        ) != step_number:
            continue
        if contact.get(
            "scope"
        ) not in {
            "new_to_prior",
            "within_new_component",
        }:
            continue
        block_a = block_lookup.get(
            int(
                contact[
                    "block_a"
                ]
            )
        )
        block_b = block_lookup.get(
            int(
                contact[
                    "block_b"
                ]
            )
        )
        if block_a is None or block_b is None:
            continue
        if (
            contact.get(
                "scope"
            )
            == "within_new_component"
            and (
                int(
                    contact[
                        "block_a"
                    ]
                )
                not in current_ids
                or int(
                    contact[
                        "block_b"
                    ]
                )
                not in current_ids
            )
        ):
            continue
        if (
            contact.get(
                "face_a"
            )
            is None
            or contact.get(
                "face_b"
            )
            is None
        ):
            continue

        point_a = get_face_center(
            block_a,
            contact[
                "face_a"
            ],
        )
        point_b = get_face_center(
            block_b,
            contact[
                "face_b"
            ],
        )
        contact_status = contact.get(
            "contact_status"
        )

        if contact_status == "male_to_female_lock":
            line_color, line_width, line_style = (
                "limegreen",
                3.0,
                "-",
            )
        elif contact_status == "female_to_female_nonlocking":
            line_color, line_width, line_style = (
                "gray",
                1.2,
                "--",
            )
        elif contact_status in {
            "male_to_male_conflict",
            "geometric_overlap_conflict",
        }:
            line_color, line_width, line_style = (
                "crimson",
                3.0,
                "-",
            )
        else:
            line_color, line_width, line_style = (
                "orange",
                1.2,
                ":",
            )

        axis.plot(
            [
                point_a[
                    0
                ],
                point_b[
                    0
                ],
            ],
            [
                point_a[
                    1
                ],
                point_b[
                    1
                ],
            ],
            [
                point_a[
                    2
                ],
                point_b[
                    2
                ],
            ],
            color=line_color,
            linewidth=line_width,
            linestyle=line_style,
        )

    if reference_setting(
        "reference_step_show_order_labels",
        True,
    ):
        for block in current_blocks:
            center = reference_block_center(
                block
            )
            axis.text(
                center[
                    0
                ],
                center[
                    1
                ],
                center[
                    2
                ],
                (
                    f"B{int(block.block_id)}"
                ),
                fontsize=8,
                color="black",
                bbox={
                    "facecolor": "white",
                    "alpha": 0.84,
                    "pad": 1.5,
                },
                zorder=1500,
            )

    status = str(
        step_row[
            "step_status"
        ]
    ).upper()
    axis_label = (
        progression_build_axis_label(
            build_axis
        )
    )
    axis.set_title(
        (
            f"Segment {result['segment_id']} — "
            f"Validated Assembly Step "
            f"{step_number}: row "
            f"{axis_label}={step_row['row']} — "
            f"{status}"
        ),
        color={
            "VALID": "green",
            "PARTIAL": "darkorange",
            "INVALID": "crimson",
        }.get(
            status,
            "black",
        ),
        fontsize=11,
    )

    symmetry_value = result.get(
        "pair_plan_valid",
        result.get(
            "symmetry_valid",
            "n/a",
        ),
    )
    placement_order = [
        int(
            block.block_id
        )
        for block in current_blocks
    ]
    validation_text = (
        f"Previous accepted blocks: "
        f"{','.join(str(value) for value in sorted(accepted_before)) or 'none'}\n"
        f"Current block IDs: "
        f"{','.join(str(value) for value in placement_order) or 'none'}\n"
        f"Locking components: "
        f"{step_row['valid_components']} valid / "
        f"{step_row['invalid_components']} invalid\n"
        f"Locks to previous rows: "
        f"{step_row['locks_to_accepted_prior']}\n"
        f"Lock area to previous rows: "
        f"{step_row['lock_area_to_accepted_prior']}\n"
        f"Internal lock area: "
        f"{step_row['internal_lock_area']}\n"
        f"Conflicts: "
        f"{step_row['male_male_or_overlap_conflicts']}\n"
        f"Final symmetry valid: {symmetry_value}"
    )
    axis.text2D(
        0.01,
        0.98,
        validation_text,
        transform=axis.transAxes,
        fontsize=7.5,
        verticalalignment="top",
        bbox={
            "facecolor": "white",
            "alpha": 0.90,
            "edgecolor": "black",
        },
    )

    visible_blocks = [
        block_lookup[
            block_id
        ]
        for block_id in sorted(
            accepted_before
            | current_ids
        )
        if block_id in block_lookup
    ]
    axis.set_xlabel(
        "X"
    )
    axis.set_ylabel(
        "Y"
    )
    axis.set_zlabel(
        "Z"
    )
    apply_progression_axis_view(
        axis,
        visible_blocks,
        build_axis,
        fallback_size=grid_size,
    )
    plt.tight_layout()
    plt.show()
    return (
        figure,
        axis,
    )


def build_assembly_oriented_assembly_steps(
    root_segment_id,
    required_interfaces_df,
    connector_rule_audit_df,
    selected_connectors_df,
    connector_validation_df,
    structural_segment_ids,
):
    valid_rows = (
        connector_validation_df.loc[
            connector_validation_df.get(
                "valid",
                pd.Series(
                    dtype=bool
                ),
            ).astype(
                bool
            )
        ].copy()
        if not connector_validation_df.empty
        else pd.DataFrame()
    )

    adjacency = defaultdict(
        list
    )
    for row in valid_rows.itertuples(
        index=False
    ):
        adjacency[
            int(
                row.segment_a
            )
        ].append(
            (
                int(
                    row.segment_b
                ),
                str(
                    row.interface_id
                ),
                str(
                    getattr(
                        row,
                        "join_mode",
                        "special_connector_block",
                    )
                ),
            )
        )
        adjacency[
            int(
                row.segment_b
            )
        ].append(
            (
                int(
                    row.segment_a
                ),
                str(
                    row.interface_id
                ),
                str(
                    getattr(
                        row,
                        "join_mode",
                        "special_connector_block",
                    )
                ),
            )
        )

    steps = []
    visited = set()
    roots = (
        [
            int(
                root_segment_id
            )
        ]
        if root_segment_id
        is not None
        else []
    )
    roots += [
        int(
            segment_id
        )
        for segment_id in (
            structural_segment_ids
        )
        if int(
            segment_id
        )
        not in roots
    ]

    for root in roots:
        if root in visited:
            continue

        visited.add(
            root
        )
        steps.append(
            {
                "assembly_step": (
                    len(
                        steps
                    )
                    + 1
                ),
                "action": (
                    "start_segment_subassembly"
                ),
                "root_segment_id": (
                    root
                ),
                "anchor_segment_id": None,
                "attached_segment_id": (
                    root
                ),
                "interface_id": None,
                "connector_decision_valid": None,
                "connector_decision_source": None,
                "connector_selected": None,
                "connector_valid": None,
                "step_status": "ready",
            }
        )

        queue = deque(
            [
                root
            ]
        )
        while queue:
            anchor = queue.popleft()
            for (
                attached,
                interface_id,
                join_mode,
            ) in sorted(
                adjacency[
                    anchor
                ]
            ):
                if attached in visited:
                    continue

                visited.add(
                    attached
                )
                queue.append(
                    attached
                )

                direct_join = bool(
                    join_mode
                    == "direct_structural_lock"
                )
                steps.append(
                    {
                        "assembly_step": (
                            len(
                                steps
                            )
                            + 1
                        ),
                        "action": (
                            "attach_segment_by_"
                            "direct_structural_lock"
                            if direct_join
                            else (
                                "attach_segment_"
                                "through_special_connector"
                            )
                        ),
                        "root_segment_id": (
                            root
                        ),
                        "anchor_segment_id": (
                            anchor
                        ),
                        "attached_segment_id": (
                            attached
                        ),
                        "interface_id": (
                            interface_id
                        ),
                        "connector_decision_valid": (
                            True
                        ),
                        "connector_decision_source": (
                            join_mode
                        ),
                        "connector_selected": (
                            False
                            if direct_join
                            else True
                        ),
                        "connector_valid": True,
                        "step_status": (
                            "ready_to_attach"
                        ),
                    }
                )

    return pd.DataFrame(
        steps,
        columns=[
            "assembly_step",
            "action",
            "root_segment_id",
            "anchor_segment_id",
            "attached_segment_id",
            "interface_id",
            "connector_decision_valid",
            "connector_decision_source",
            "connector_selected",
            "connector_valid",
            "step_status",
        ],
    )



def assembly_block_traces_with_opacity(
    block,
    *,
    opacity,
    showlegend=False,
    name_suffix="",
    preview=False,
):
    traces = block_traces(
        block,
        showlegend=showlegend,
    )
    effective_opacity = (
        interactive_effective_block_opacity(
            block,
            opacity,
            preview=preview,
        )
    )
    updated = []
    for trace in traces:
        trace.opacity = float(
            effective_opacity
        )
        if name_suffix:
            trace.name = (
                f"{trace.name} "
                f"{name_suffix}"
            )
        updated.append(trace)
    return updated


def assembly_segment_center(blocks):
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


def assembly_player_step_annotation(row):
    step_number = int(
        row.assembly_step
    )
    if (
        str(row.action)
        == "start_segment_subassembly"
    ):
        segment_id = int(
            row.attached_segment_id
        )
        return (
            f"<b>Step {step_number}</b><br>"
            f"Start with completed "
            f"{segment_display_text(segment_id)}."
        )

    interface_id = str(
        row.interface_id
    )
    attached_segment_id = int(
        row.attached_segment_id
    )
    anchor_segment_id = int(
        row.anchor_segment_id
    )
    status = str(
        row.step_status
    )
    attached_text = (
        segment_display_text(
            attached_segment_id
        )
    )
    anchor_text = (
        segment_display_text(
            anchor_segment_id
        )
    )

    if status == "ready_to_attach":
        return (
            f"<b>Step {step_number}</b><br>"
            f"Place the validated connector "
            f"for interface {interface_id}.<br>"
            f"Attach {attached_text} "
            f"to {anchor_text}."
        )

    explanations = {
        "pending_connector_decision": (
            "No valid LLM2 or fallback catalog "
            "decision is available."
        ),
        "pending_connector_candidate": (
            "The connection requirement is known, "
            "but no catalog candidate was selected."
        ),
        "connector_validation_failed": (
            "A catalog candidate was selected, "
            "but it failed physical validation."
        ),
    }

    return (
        f"<b>Step {step_number}: "
        f"connector pending</b><br>"
        f"Interface {interface_id}.<br>"
        f"Preview {attached_text} "
        f"relative to {anchor_text}.<br>"
        f"Status: {status}.<br>"
        f"{explanations.get(status, '')}"
    )


def assembly_visible_assembly_player(
    assembly_steps_df,
    segment_blocks_by_id,
    connector_blocks,
    interface_payload,
    *,
    title,
):
    config = VISUALIZATION_CONFIG
    ready_opacity = float(
        config.get(
            "assembly_player_ready_opacity",
            0.96,
        )
    )
    ghost_opacity = float(
        config.get(
            "assembly_player_ghost_opacity",
            0.18,
        )
    )

    connector_by_interface = {
        str(block.interface_id): block
        for block in connector_blocks
        if getattr(
            block,
            "interface_id",
            None,
        )
        is not None
    }

    segment_ids = sorted(
        int(segment_id)
        for segment_id in segment_blocks_by_id
        if segment_blocks_by_id[
            segment_id
        ]
    )

    figure = go.Figure()
    trace_metadata = []
    shown_solid_families = set()

    # Every segment gets both solid and ghost traces.
    for segment_id in segment_ids:
        blocks = list(
            segment_blocks_by_id[
                segment_id
            ]
        )
        for block in blocks:
            family = str(
                block.block_family
            )
            solid_traces = (
                assembly_block_traces_with_opacity(
                    block,
                    opacity=ready_opacity,
                    showlegend=(
                        family
                        not in shown_solid_families
                    ),
                    name_suffix="",
                    preview=False,
                )
            )
            shown_solid_families.add(
                family
            )
            for trace in solid_traces:
                trace.visible = False
                figure.add_trace(trace)
                trace_metadata.append({
                    "kind": "segment_solid",
                    "segment_id": segment_id,
                })

            ghost_traces = (
                assembly_block_traces_with_opacity(
                    block,
                    opacity=ghost_opacity,
                    showlegend=False,
                    name_suffix=(
                        f"(segment {segment_id} preview)"
                    ),
                    preview=True,
                )
            )
            for trace in ghost_traces:
                trace.visible = False
                figure.add_trace(trace)
                trace_metadata.append({
                    "kind": "segment_ghost",
                    "segment_id": segment_id,
                })

    # Selected connector traces.
    for interface_id, connector in (
        connector_by_interface.items()
    ):
        for trace in block_traces(
            connector,
            showlegend=True,
        ):
            trace.visible = False
            figure.add_trace(trace)
            trace_metadata.append({
                "kind": "connector",
                "interface_id": interface_id,
            })

    # One interface indicator per non-root step.
    step_rows = list(
        assembly_steps_df.itertuples(
            index=False
        )
    )
    indicator_trace_index = {}

    for row in step_rows:
        if (
            str(row.action)
            == "start_segment_subassembly"
        ):
            continue

        step_number = int(
            row.assembly_step
        )
        interface_id = str(
            row.interface_id
        )
        anchor_segment_id = int(
            row.anchor_segment_id
        )
        attached_segment_id = int(
            row.attached_segment_id
        )

        anchor_center = assembly_segment_center(
            segment_blocks_by_id.get(
                anchor_segment_id,
                [],
            )
        )
        attached_center = (
            assembly_segment_center(
                segment_blocks_by_id.get(
                    attached_segment_id,
                    [],
                )
            )
        )
        interface_center = (
            assembly_interface_center(
                interface_id,
                interface_payload,
            )
        )

        points = [
            point
            for point in [
                anchor_center,
                interface_center,
                attached_center,
            ]
            if point is not None
        ]
        if len(points) < 2:
            continue

        status = str(
            row.step_status
        )
        ready = (
            status
            == "ready_to_attach"
        )
        color = (
            "limegreen"
            if ready
            else "crimson"
        )

        trace = go.Scatter3d(
            x=[point[0] for point in points],
            y=[point[1] for point in points],
            z=[point[2] for point in points],
            mode="lines+markers",
            line={
                "color": color,
                "width": 6,
                "dash": (
                    "solid"
                    if ready
                    else "dash"
                ),
            },
            marker={
                "size": 6,
                "color": color,
                "line": {
                    "color": "black",
                    "width": 1,
                },
            },
            name=(
                f"Interface {interface_id}"
            ),
            text=[
                (
                    f"Anchor segment "
                    f"{anchor_segment_id}"
                ),
                (
                    f"Interface "
                    f"{interface_id}"
                ),
                (
                    f"Attached segment "
                    f"{attached_segment_id}"
                ),
            ][:len(points)],
            hoverinfo="text",
            visible=False,
            showlegend=False,
        )
        figure.add_trace(trace)
        trace_metadata.append({
            "kind": "indicator",
            "assembly_step": step_number,
        })
        indicator_trace_index[
            step_number
        ] = len(
            figure.data
        ) - 1

    # Build player states.
    solid_segments = set()
    visible_connectors = set()
    step_states = []
    audit_rows = []

    for row in step_rows:
        step_number = int(
            row.assembly_step
        )
        action = str(
            row.action
        )
        status = str(
            getattr(
                row,
                "step_status",
                "ready",
            )
        )
        ghost_segments = set()

        if (
            action
            == "start_segment_subassembly"
        ):
            solid_segments.add(
                int(
                    row.attached_segment_id
                )
            )
        elif status == "ready_to_attach":
            interface_id = str(
                row.interface_id
            )
            if (
                interface_id
                in connector_by_interface
            ):
                visible_connectors.add(
                    interface_id
                )
            solid_segments.add(
                int(
                    row.attached_segment_id
                )
            )
        else:
            if config.get(
                "assembly_player_show_pending_segment_ghost",
                True,
            ):
                ghost_segments.add(
                    int(
                        row.attached_segment_id
                    )
                )
            anchor_segment_id = int(
                row.anchor_segment_id
            )
            if (
                anchor_segment_id
                not in solid_segments
                and config.get(
                    "assembly_player_show_pending_anchor_ghost",
                    True,
                )
            ):
                ghost_segments.add(
                    anchor_segment_id
                )

        visibility = []
        for metadata in trace_metadata:
            kind = metadata["kind"]
            if kind == "segment_solid":
                visibility.append(
                    metadata[
                        "segment_id"
                    ]
                    in solid_segments
                )
            elif kind == "segment_ghost":
                visibility.append(
                    metadata[
                        "segment_id"
                    ]
                    in ghost_segments
                )
            elif kind == "connector":
                visibility.append(
                    metadata[
                        "interface_id"
                    ]
                    in visible_connectors
                )
            elif kind == "indicator":
                visibility.append(
                    bool(
                        config.get(
                            "assembly_player_show_interface_indicator",
                            True,
                        )
                        and metadata[
                            "assembly_step"
                        ]
                        == step_number
                    )
                )
            else:
                visibility.append(
                    False
                )

        annotation_text = (
            assembly_player_step_annotation(
                row
            )
        )
        step_states.append({
            "assembly_step": step_number,
            "visibility": visibility,
            "annotation": (
                annotation_text
            ),
            "solid_segment_ids": sorted(
                solid_segments
            ),
            "ghost_segment_ids": sorted(
                ghost_segments
            ),
            "visible_connector_ids": sorted(
                visible_connectors
            ),
            "step_status": status,
        })
        audit_rows.append({
            "assembly_step": step_number,
            "action": action,
            "step_status": status,
            "solid_segment_ids": (
                sorted(
                    solid_segments
                )
            ),
            "ghost_segment_ids": (
                sorted(
                    ghost_segments
                )
            ),
            "visible_connector_ids": (
                sorted(
                    visible_connectors
                )
            ),
            "annotation": (
                re.sub(
                    r"<[^>]+>",
                    " ",
                    annotation_text,
                )
            ),
        })

    if not step_states:
        figure.update_layout(
            **figure_layout(
                f"{title} — no assembly steps"
            )
        )
        return (
            figure,
            pd.DataFrame(
                audit_rows
            ),
        )

    slider_steps = []
    total_steps = len(
        step_states
    )
    for state in step_states:
        step_number = int(
            state["assembly_step"]
        )
        slider_steps.append({
            "method": "update",
            "label": str(
                step_number
            ),
            "args": [
                {
                    "visible": (
                        state[
                            "visibility"
                        ]
                    )
                },
                {
                    "title": (
                        f"{title} — "
                        f"Step {step_number} "
                        f"of {total_steps}"
                    ),
                    "annotations": [{
                        "xref": "paper",
                        "yref": "paper",
                        "x": 0.01,
                        "y": 0.99,
                        "xanchor": "left",
                        "yanchor": "top",
                        "align": "left",
                        "text": (
                            state[
                                "annotation"
                            ]
                        ),
                        "showarrow": False,
                        "bgcolor": (
                            "rgba(255,255,255,0.94)"
                        ),
                        "bordercolor": (
                            "limegreen"
                            if state[
                                "step_status"
                            ]
                            in {
                                "ready",
                                "ready_to_attach",
                            }
                            else "crimson"
                        ),
                        "borderwidth": 1,
                        "font": {
                            "size": 12,
                            "color": "black",
                        },
                    }],
                },
            ],
        })

    initial_state = step_states[0]
    for index, visible in enumerate(
        initial_state["visibility"]
    ):
        figure.data[
            index
        ].visible = bool(
            visible
        )

    all_subassembly_visibility = []
    for metadata in trace_metadata:
        kind = metadata["kind"]
        if kind == "segment_solid":
            all_subassembly_visibility.append(
                True
            )
        elif kind == "connector":
            all_subassembly_visibility.append(
                True
            )
        else:
            all_subassembly_visibility.append(
                False
            )

    pending_count = int(
        assembly_steps_df[
            "step_status"
        ].astype(str).ne(
            "ready_to_attach"
        ).sum()
        - int(
            (
                assembly_steps_df[
                    "action"
                ].astype(str)
                == "start_segment_subassembly"
            ).sum()
        )
    )
    pending_count = max(
        pending_count,
        0,
    )

    complete_annotation = (
        f"<b>All segment subassemblies shown</b><br>"
        f"{len(segment_ids)} structural segment "
        f"subassemblies are displayed in their model "
        f"positions.<br>"
        f"{pending_count} connector-mediated joins "
        f"remain pending; this is not a validated "
        f"connected final assembly."
    )

    layout = figure_layout(
        f"{title} — Step "
        f"{initial_state['assembly_step']} "
        f"of {total_steps}"
    )
    layout["sliders"] = [{
        "active": 0,
        "currentvalue": {
            "prefix": (
                "Assembly step: "
            ),
        },
        "pad": {
            "t": 55,
        },
        "steps": slider_steps,
    }]
    layout["annotations"] = [{
        "xref": "paper",
        "yref": "paper",
        "x": 0.01,
        "y": 0.99,
        "xanchor": "left",
        "yanchor": "top",
        "align": "left",
        "text": initial_state[
            "annotation"
        ],
        "showarrow": False,
        "bgcolor": (
            "rgba(255,255,255,0.94)"
        ),
        "bordercolor": (
            "limegreen"
            if initial_state[
                "step_status"
            ]
            in {
                "ready",
                "ready_to_attach",
            }
            else "crimson"
        ),
        "borderwidth": 1,
        "font": {
            "size": 12,
            "color": "black",
        },
    }]
    layout["updatemenus"] = [{
        "type": "buttons",
        "direction": "left",
        "x": 0.0,
        "y": 1.11,
        "buttons": [
            {
                "label": "Start",
                "method": "update",
                "args": [
                    {
                        "visible": (
                            initial_state[
                                "visibility"
                            ]
                        )
                    },
                    {
                        "title": (
                            f"{title} — "
                            f"Step "
                            f"{initial_state['assembly_step']} "
                            f"of {total_steps}"
                        ),
                        "annotations": [
                            layout[
                                "annotations"
                            ][0]
                        ],
                    },
                ],
            },
            {
                "label": (
                    "All subassemblies"
                ),
                "method": "update",
                "args": [
                    {
                        "visible": (
                            all_subassembly_visibility
                        )
                    },
                    {
                        "title": (
                            f"{title} — "
                            "Unconnected structural state"
                        ),
                        "annotations": [{
                            "xref": "paper",
                            "yref": "paper",
                            "x": 0.01,
                            "y": 0.99,
                            "xanchor": "left",
                            "yanchor": "top",
                            "align": "left",
                            "text": (
                                complete_annotation
                            ),
                            "showarrow": False,
                            "bgcolor": (
                                "rgba(255,255,255,0.94)"
                            ),
                            "bordercolor": (
                                "darkorange"
                            ),
                            "borderwidth": 1,
                            "font": {
                                "size": 12,
                                "color": (
                                    "black"
                                ),
                            },
                        }],
                    },
                ],
            },
        ],
    }]
    figure.update_layout(
        **layout
    )

    audit_df = pd.DataFrame(
        audit_rows,
        columns=[
            "assembly_step",
            "action",
            "step_status",
            "solid_segment_ids",
            "ghost_segment_ids",
            "visible_connector_ids",
            "annotation",
        ],
    )
    return (
        figure,
        audit_df,
    )


# ------------------------------------------------------------
# 0. Segmentation visualization is consolidated after
#    structuralization and symmetry exactification.
# ------------------------------------------------------------

# ------------------------------------------------------------
# 1. Physical functional targets and structural segment set
# ------------------------------------------------------------

all_segment_ids = set(
    segments_labeled_df[
        "segment_id"
    ].astype(int)
)
raw_structural_segment_ids = sorted(
    all_segment_ids
    - set(
        functional_target_segment_ids
    )
)

if not raw_structural_segment_ids:
    raise RuntimeError(
        "No structural segments remain after "
        "semantic preflight and functional grouping."
    )

structuralization_result = (
    search_structuralization_lattice_offsets(
        segment_grid_planner_raw,
        raw_structural_segment_ids,
        functional_target_segment_ids,
    )
)
segment_grid_planner_raw_aligned = (
    structuralization_result["aligned_raw_grid"]
)
structuralization_lattice_transform = (
    structuralization_result["lattice_transform"]
)
structuralization_lattice_offset_audit_df = (
    structuralization_result["lattice_offset_audit_df"]
)
safe_export_dataframe(
    structuralization_lattice_offset_audit_df,
    OUTPUT_DIR / "structuralization_lattice_offset_audit.csv",
)
(OUTPUT_DIR / "structuralization_lattice_transform.json").write_text(
    json.dumps(
        json_safe_value(structuralization_lattice_transform),
        indent=2,
    ),
    encoding="utf-8",
)
segment_grid_structuralized = (
    structuralization_result[
        "structural_grid"
    ]
)
segment_grid_planner = (
    structuralization_result[
        "combined_grid"
    ]
)
structural_segment_ids = (
    structuralization_result[
        "active_structural_segment_ids"
    ]
)
structuralization_dropped_segment_ids = (
    structuralization_result[
        "dropped_structural_segment_ids"
    ]
)
structuralization_gate_valid = bool(
    structuralization_result[
        "gate_valid"
    ]
)
STRUCTURALIZATION_CENTER_PLANE = (
    structuralization_result[
        "center_plane"
    ]
)

if not structural_segment_ids:
    raise RuntimeError(
        "Structuralization produced no active structural segments."
    )

np.save(
    OUTPUT_DIR
    / "segment_grid_planner_raw.npy",
    segment_grid_planner_raw,
)
np.save(
    OUTPUT_DIR
    / "segment_grid_planner_raw_aligned.npy",
    segment_grid_planner_raw_aligned,
)
np.save(
    OUTPUT_DIR
    / "segment_grid_structuralized.npy",
    segment_grid_structuralized,
)
np.save(
    OUTPUT_DIR
    / "segment_grid_planner_combined.npy",
    segment_grid_planner,
)
np.save(
    OUTPUT_DIR
    / "functional_cell_reservation_mask.npy",
    structuralization_result[
        "functional_reservation_mask"
    ],
)

structuralization_ownership_audit_df = (
    structuralization_result[
        "ownership_audit_df"
    ]
)
safe_export_dataframe(
    structuralization_ownership_audit_df,
    OUTPUT_DIR
    / "structuralization_cell_ownership.csv",
)
structuralization_segment_summary_df = (
    structuralization_result[
        "segment_summary_df"
    ]
)
structuralization_segment_summary_df.to_csv(
    OUTPUT_DIR
    / "structuralization_segment_summary.csv",
    index=False,
)
structuralization_symmetry_repair_audit_df = (
    structuralization_result[
        "symmetry_repair_audit_df"
    ]
)
structuralization_symmetry_repair_audit_df.to_csv(
    OUTPUT_DIR
    / "structuralization_symmetry_repair_audit.csv",
    index=False,
)
(
    OUTPUT_DIR
    / "structuralization_summary.json"
).write_text(
    json.dumps(
        {
            "gate_valid": (
                structuralization_gate_valid
            ),
            "allowed_catalog_column_heights": (
                structuralization_result[
                    "allowed_heights"
                ]
            ),
            "center_plane": (
                STRUCTURALIZATION_CENTER_PLANE
            ),
            "lattice_transform": (
                structuralization_lattice_transform
            ),
            "selected_lattice_offset": [
                structuralization_lattice_transform["offset_x"],
                structuralization_lattice_transform["offset_y"],
            ],
            "raw_structural_segment_ids": (
                raw_structural_segment_ids
            ),
            "active_structural_segment_ids": (
                structural_segment_ids
            ),
            "dropped_structural_segment_ids": (
                structuralization_dropped_segment_ids
            ),
            "semantic_preflight_gate_valid": (
                semantic_preflight_gate_valid
            ),
            "semantic_preflight_quarantined_segment_ids": (
                semantic_preflight_quarantined_segment_ids
            ),
        },
        indent=2,
    ),
    encoding="utf-8",
)

if log_enabled(
    "show_intermediate_tables"
):
    print(
        "Structuralization gate valid:",
        structuralization_gate_valid,
    )
    print(
        "Active structural segments:",
        structural_segment_ids,
    )
    print(
        "Dropped structural segments:",
        structuralization_dropped_segment_ids,
    )
    emit_diagnostic(
        structuralization_segment_summary_df
    )
    if not (
        structuralization_symmetry_repair_audit_df.empty
    ):
        emit_diagnostic(
            structuralization_symmetry_repair_audit_df
        )

initial_symmetry_discovery = (
    discover_structural_symmetry_pairs(
        segment_grid_planner,
        segments_labeled_df,
        structural_segment_ids,
    )
    if SYMMETRY_ENABLED
    else {
        "center_plane": None,
        "global_source_mirror_iou": None,
        "accepted_pairs": [],
        "audit_df": pd.DataFrame(),
    }
)
initial_symmetry_center_plane = initial_symmetry_discovery[
    "center_plane"
]
(
    segment_grid_structuralized,
    structural_symmetry_exactification_audit_df,
) = exactify_accepted_structural_symmetry_pairs(
    segment_grid_structuralized,
    segment_grid_planner_raw_aligned,
    initial_symmetry_discovery["accepted_pairs"],
    initial_symmetry_center_plane,
)
safe_export_dataframe(
    structural_symmetry_exactification_audit_df,
    OUTPUT_DIR / "structural_symmetry_exactification_audit.csv",
)

# Rebuild the combined grid after exactification while preserving any
# valid functional source segments from the aligned raw grid.
segment_grid_planner = segment_grid_structuralized.copy()
for functional_segment_id in sorted(
    int(value)
    for value in functional_target_segment_ids
):
    functional_mask = (
        segment_grid_planner_raw_aligned
        == functional_segment_id
    )
    segment_grid_planner[functional_mask] = functional_segment_id

np.save(
    OUTPUT_DIR / "segment_grid_structuralized.npy",
    segment_grid_structuralized,
)
np.save(
    OUTPUT_DIR / "segment_grid_planner_combined.npy",
    segment_grid_planner,
)

if (
    VISUALIZATION_CONFIG.get(
        "enabled",
        True,
    )
    and VISUALIZATION_CONFIG.get(
        "interactive",
        True,
    )
):
    show_comparison_inline = bool(
        VISUALIZATION_CONFIG.get(
            "show_inline_segmentation_comparison",
            True,
        )
    )
    save_interactive = bool(
        VISUALIZATION_CONFIG.get(
            "save_interactive_html",
            False,
        )
    )
    if (
        show_comparison_inline
        or save_interactive
    ):
        segmentation_comparison = (
            segmentation_comparison_figure(
                segment_grid_planner_raw_aligned,
                segment_grid_structuralized,
                segments_labeled_df,
            )
        )
        write_interactive(
            segmentation_comparison,
            VISUALIZATION_DIR
            / "segment_geometry_comparison.html",
            "segmentation_comparison",
            (
                "Raw versus structuralized segment "
                "geometry comparison"
            ),
            show_comparison_inline,
        )

    if (
        VISUALIZATION_CONFIG.get(
            "show_inline_structuralization_delta",
            False,
        )
        or save_interactive
    ):
        write_interactive(
            structuralization_delta_figure(
                segment_grid_planner_raw_aligned,
                segment_grid_structuralized,
            ),
            VISUALIZATION_DIR
            / "structuralization_delta_interactive.html",
            "structuralization",
            (
                "Interactive retained, added, and "
                "removed voxel comparison"
            ),
            bool(
                VISUALIZATION_CONFIG.get(
                    "show_inline_structuralization_delta",
                    False,
                )
            ),
        )

symmetry_discovery = (
    discover_structural_symmetry_pairs(
        segment_grid_planner,
        segments_labeled_df,
        structural_segment_ids,
    )
    if SYMMETRY_ENABLED
    else {
        "center_plane": None,
        "global_source_mirror_iou": None,
        "accepted_pairs": [],
        "audit_df": pd.DataFrame(),
    }
)
SYMMETRY_CENTER_PLANE = symmetry_discovery[
    "center_plane"
]
structural_symmetry_pairs = symmetry_discovery[
    "accepted_pairs"
]
structural_symmetry_source_audit_df = (
    symmetry_discovery["audit_df"]
)
structural_symmetry_source_audit_df.to_csv(
    OUTPUT_DIR / "structural_symmetry_source_pair_audit.csv",
    index=False,
)
(OUTPUT_DIR / "symmetry_center_plane.json").write_text(
    json.dumps(
        {
            "enabled": SYMMETRY_ENABLED,
            "axis": SYMMETRY_CONFIG.get("axis", "X"),
            "axis_index": SYMMETRY_AXIS_INDEX,
            "center_plane": SYMMETRY_CENTER_PLANE,
            "global_source_mirror_iou": (
                symmetry_discovery[
                    "global_source_mirror_iou"
                ]
            ),
            "accepted_pair_count": len(
                structural_symmetry_pairs
            ),
        },
        indent=2,
    ),
    encoding="utf-8",
)

physical_targets_export = physical_targets_df.copy()
if not physical_targets_export.empty:
    physical_targets_export["source_segment_ids"] = (
        physical_targets_export["source_segment_ids"].map(json.dumps)
    )
physical_targets_export.to_csv(
    OUTPUT_DIR / "functional_attachment_physical_targets.csv",
    index=False,
)

required_physical_target_ids = sorted(
    set(
        physical_targets_df.get(
            "physical_target_id",
            pd.Series(dtype=str),
        ).astype(str)
    )
)
functional_segment_group_df = (
    functional_segment_group_table(
        segments_labeled_df
    )
)
safe_export_dataframe(
    functional_segment_group_df,
    OUTPUT_DIR
    / "functional_segment_group_table.csv",
)

# Required count gate applies only to required attachments.
physical_target_count_rows = []
for declaration in attachment_declarations():
    actual = int(
        (
            physical_targets_df.get(
                "attachment_id",
                pd.Series(dtype=str),
            )
            == declaration["attachment_id"]
        ).sum()
    )
    expected = int(declaration.get("expected_count", 0))
    required = bool(declaration.get("required", False))
    count_valid = (
        actual == expected
        if declaration.get("count_policy")
        == "exact_physical_instances"
        else actual >= expected
    )
    physical_target_count_rows.append({
        "attachment_id": declaration["attachment_id"],
        "required": required,
        "expected_count": expected,
        "physical_target_count": actual,
        "count_valid": count_valid,
        "gate_valid": bool(count_valid or not required),
    })
physical_target_count_audit_df = pd.DataFrame(
    physical_target_count_rows
)
physical_target_count_audit_df.to_csv(
    OUTPUT_DIR
    / "functional_attachment_physical_target_count_audit.csv",
    index=False,
)

# ------------------------------------------------------------
# 2. Structural interfaces and assembly graph
# ------------------------------------------------------------

structural_interfaces_df, structural_interface_payload = (
    detect_segment_interfaces(
        segment_grid_planner,
        included_segment_ids=structural_segment_ids,
    )
)
structural_assembly_graph_df, required_interface_ids = (
    required_assembly_interfaces(
        structural_interfaces_df,
        structural_segment_ids,
    )
)
root_segment_id = choose_root_segment(
    structural_segment_ids
)
structural_assembly_graph_df["root_segment_id"] = (
    root_segment_id
)

structural_interfaces_df.to_csv(
    OUTPUT_DIR / "structural_segment_interfaces.csv",
    index=False,
)
structural_assembly_graph_df.to_csv(
    OUTPUT_DIR / "structural_assembly_graph.csv",
    index=False,
)
(OUTPUT_DIR / "structural_segment_interface_coordinates.json").write_text(
    json.dumps(structural_interface_payload, indent=2),
    encoding="utf-8",
)

required_interfaces_df = structural_assembly_graph_df[
    structural_assembly_graph_df["interface_id"].isin(
        required_interface_ids
    )
].copy()


def interface_connector_rule(interface_row):
    pair_ids = {
        int(interface_row.segment_a),
        int(interface_row.segment_b),
    }
    pair_labels = {
        str(interface_row.segment_a_label).lower(),
        str(interface_row.segment_b_label).lower(),
    }
    for rule in TASK_CONTEXT.get("connector_rules", []):
        rule_ids = {int(v) for v in rule.get("segment_ids", [])}
        rule_labels = {
            str(v).lower()
            for v in rule.get("segment_labels", [])
        }
        if rule_ids and rule_ids != pair_ids:
            continue
        if rule_labels and rule_labels != pair_labels:
            continue
        return rule
    return None


interface_catalog_query_by_id = {}
eligible_connector_interface_ids = []

for interface in required_interfaces_df.itertuples(
    index=False
):
    declared_rule = interface_connector_rule(
        interface
    )
    decision = (
        llm2_resolve_interface_decision(
            interface,
            declared_rule,
        )
    )
    LLM2_INTERFACE_DECISION_ROWS.append(
        decision
    )

    interface_id = str(
        interface.interface_id
    )
    if decision.get(
        "valid",
        False,
    ) and decision.get(
        "requires_connector",
        True,
    ):
        interface_catalog_query_by_id[
            interface_id
        ] = decision[
            "catalog_query"
        ]
        eligible_connector_interface_ids.append(
            interface.interface_id
        )

llm2_interface_decisions_df = pd.DataFrame(
    [
        {
            **row,
            "catalog_requirements": json.dumps(
                llm2_json_safe(
                    row.get(
                        "catalog_requirements",
                        {},
                    )
                ),
                sort_keys=True,
            ),
            "catalog_query": json.dumps(
                llm2_json_safe(
                    row.get(
                        "catalog_query",
                        {},
                    )
                ),
                sort_keys=True,
            ),
            "matched_block_families": ",".join(
                str(value)
                for value in row.get(
                    "matched_block_families",
                    [],
                )
                if value is not None
            ),
        }
        for row in LLM2_INTERFACE_DECISION_ROWS
    ]
)
llm2_interface_decisions_df.to_csv(
    OUTPUT_DIR
    / "llm2_structural_interface_decisions.csv",
    index=False,
)
(
    OUTPUT_DIR
    / "llm2_structural_interface_decisions.json"
).write_text(
    json.dumps(
        llm2_json_safe(
            LLM2_INTERFACE_DECISION_ROWS
        ),
        indent=2,
    ),
    encoding="utf-8",
)

# Model-neutral audit name.
connector_rule_audit_df = (
    llm2_interface_decisions_df.copy()
)
connector_rule_audit_df[
    "connector_rule_declared"
] = connector_rule_audit_df[
    "decision_source"
].astype(str).str.contains(
    "connector_rule",
    na=False,
)
connector_rule_audit_df["status"] = np.where(
    connector_rule_audit_df[
        "valid"
    ].fillna(False),
    "eligible_for_catalog_connector_search",
    "pending_interface_connector_decision",
)
connector_rule_audit_df.to_csv(
    OUTPUT_DIR
    / "structural_connector_rule_audit.csv",
    index=False,
)

connector_search_interfaces_df = (
    required_interfaces_df[
        required_interfaces_df[
            "interface_id"
        ].isin(
            eligible_connector_interface_ids
        )
    ].copy()
)

# ------------------------------------------------------------
# 3. Catalog-driven connector and functional candidates
# ------------------------------------------------------------

connector_candidates_df, connector_catalog_records = (
    generate_structural_connector_candidates(
        connector_search_interfaces_df,
        structural_interface_payload,
        structural_segment_ids,
        interface_catalog_queries=(
            interface_catalog_query_by_id
        ),
    )
)
(
    connector_candidates_df,
    connector_receiving_face_candidate_audit_df,
) = reservation_annotate_connector_candidates_with_reservations(
    connector_candidates_df,
    segment_grid_planner,
    connector_search_interfaces_df,
    LLM2_INTERFACE_DECISION_ROWS,
)
connector_receiving_face_candidate_audit_df.to_csv(
    OUTPUT_DIR
    / "connector_receiving_face_candidate_audit.csv",
    index=False,
)
safe_export_dataframe(
    connector_receiving_face_candidate_audit_df,
    OUTPUT_DIR / "reservation_connector_candidate_reservation_audit.csv",
)

selected_connectors_df, connector_symmetry_audit_df = (
    select_connector_candidates_symmetry_aware(
        connector_candidates_df,
        connector_search_interfaces_df,
        structural_symmetry_pairs,
        structural_segment_ids,
        SYMMETRY_CENTER_PLANE,
    )
    if SYMMETRY_ENABLED
    else (
        select_nonoverlapping_candidates(
            connector_candidates_df,
            "interface_id",
        ),
        pd.DataFrame(),
    )
)
connector_symmetry_audit_df.to_csv(
    OUTPUT_DIR / "connector_symmetry_selection_audit.csv",
    index=False,
)

if STRUCTURAL_JOIN_MODE == "direct_structural_lock":
    rejected_special_connector_candidates_df = selected_connectors_df.copy()
    if not rejected_special_connector_candidates_df.empty:
        rejected_special_connector_candidates_df["rejection_reason"] = (
            "The active context uses validated direct structural locks; "
            "special connector candidates remain diagnostic only."
        )
    selected_connectors_df = selected_connectors_df.iloc[0:0].copy()
    connector_symmetry_audit_df = pd.DataFrame([{
        "selection_status": "direct_structural_join_mode",
        "valid": True,
    }])
else:
    rejected_special_connector_candidates_df = selected_connectors_df.iloc[0:0].copy()

safe_export_dataframe(
    rejected_special_connector_candidates_df,
    OUTPUT_DIR / "rejected_special_connector_candidates.csv",
)

prebuild_selected_connectors_df = (
    selected_connectors_df.copy()
)
(
    connector_receiving_face_requirements_df,
    deferred_connector_face_requirements_by_segment,
) = explode_selected_connector_face_requirements(
    prebuild_selected_connectors_df
)
# Preliminary connector-only requirements. Reservation replaces this mapping after
# functional selection with a combined hard/soft/none reservation plan.
connector_face_requirements_by_segment = defaultdict(
    list
)
safe_export_dataframe(
    connector_receiving_face_requirements_df,
    OUTPUT_DIR
    / "connector_receiving_face_requirements.csv",
)
(OUTPUT_DIR / "connector_receiving_face_requirements.json").write_text(
    json.dumps(
        json_safe_value(
            connector_receiving_face_requirements_df.to_dict(
                orient="records"
            )
        ),
        indent=2,
    ),
    encoding="utf-8",
)

if (
    VISUALIZATION_CONFIG.get("enabled", True)
    and VISUALIZATION_CONFIG.get("interactive", True)
):
    write_interactive(
        reserved_face_interactive_figure(
            segment_grid_planner,
            connector_receiving_face_requirements_df,
        ),
        VISUALIZATION_DIR
        / "connector_receiving_faces_interactive.html",
        "connector_receiving_faces",
        (
            "Interactive required male/female receiving faces "
            "derived from selected connector catalog roles"
        ),
        bool(
            VISUALIZATION_CONFIG.get(
                "show_inline_reserved_faces",
                False,
            )
        ),
    )

functional_candidates_df = generate_functional_candidates(
    physical_targets_df,
    structural_segment_ids,
)
(
    functional_candidates_df,
    reservation_functional_candidate_reservation_audit_df,
) = reservation_annotate_functional_candidates_with_reservations(
    functional_candidates_df,
    segment_grid_planner,
    physical_targets_df,
)
safe_export_dataframe(
    reservation_functional_candidate_reservation_audit_df,
    OUTPUT_DIR / "reservation_functional_candidate_reservation_audit.csv",
)

llm2_functional_decisions_df = pd.DataFrame(
    [
        {
            **row,
            "source_segment_ids": json.dumps(
                row.get(
                    "source_segment_ids",
                    [],
                )
            ),
            "source_segment_names": json.dumps(
                row.get(
                    "source_segment_names",
                    [],
                )
            ),
            "source_segment_labels": json.dumps(
                row.get(
                    "source_segment_labels",
                    [],
                )
            ),
            "catalog_requirements": json.dumps(
                llm2_json_safe(
                    row.get(
                        "catalog_requirements",
                        {},
                    )
                ),
                sort_keys=True,
            ),
            "catalog_query": json.dumps(
                llm2_json_safe(
                    row.get(
                        "catalog_query",
                        {},
                    )
                ),
                sort_keys=True,
            ),
            "matched_block_families": ",".join(
                str(value)
                for value in row.get(
                    "matched_block_families",
                    [],
                )
                if value is not None
            ),
        }
        for row in LLM2_FUNCTIONAL_DECISION_ROWS
    ]
)
llm2_functional_decisions_df.to_csv(
    OUTPUT_DIR
    / "llm2_functional_target_decisions.csv",
    index=False,
)
(
    OUTPUT_DIR
    / "llm2_functional_target_decisions.json"
).write_text(
    json.dumps(
        llm2_json_safe(
            LLM2_FUNCTIONAL_DECISION_ROWS
        ),
        indent=2,
    ),
    encoding="utf-8",
)

(
    OUTPUT_DIR
    / "llm2_catalog_capabilities.json"
).write_text(
    json.dumps(
        llm2_json_safe(
            llm2_catalog_capability_rows()
        ),
        indent=2,
    ),
    encoding="utf-8",
)

if LLM2_CONFIG.get(
    "save_raw_responses",
    True,
):
    (
        OUTPUT_DIR
        / "llm2_raw_responses.json"
    ).write_text(
        json.dumps(
            llm2_json_safe(
                LLM2_RAW_RESPONSE_ROWS
            ),
            indent=2,
        ),
        encoding="utf-8",
    )

llm2_run_summary = {
    "execution_mode": EXECUTION_POLICY.mode,
    "runtime_llm_requested": LLM2_REQUESTED_ENABLED,
    "runtime_llm_allowed_by_contract": EXECUTION_POLICY.allow_runtime_llm,
    "runtime_llm_allowed_by_runner": RUNTIME_LLM_ALLOWED_BY_RUNNER,
    "deterministic_build": EXECUTION_POLICY.deterministic_build,
    "final_claim_eligible": EXECUTION_POLICY.final_claim_eligible,
    "enabled": bool(
        LLM2_CONFIG.get(
            "enabled",
            True,
        )
    ),
    "primary_model": (
        LLM2_CONFIG.get("model") if LLM2_EFFECTIVE_ENABLED else None
    ),
    "fallback_models": (
        LLM2_CONFIG.get("fallback_models", []) if LLM2_EFFECTIVE_ENABLED else []
    ),
    "interface_decision_count": len(
        LLM2_INTERFACE_DECISION_ROWS
    ),
    "interface_llm_decision_count": sum(
        1
        for row in LLM2_INTERFACE_DECISION_ROWS
        if row.get(
            "decision_source"
        )
        == "ollama_llm2"
    ),
    "interface_fallback_count": sum(
        1
        for row in LLM2_INTERFACE_DECISION_ROWS
        if row.get("decision_source") != "ollama_llm2"
    ),
    "interface_deterministic_decision_count": sum(
        1
        for row in LLM2_INTERFACE_DECISION_ROWS
        if row.get("decision_source") != "ollama_llm2"
    ),
    "functional_decision_count": len(
        LLM2_FUNCTIONAL_DECISION_ROWS
    ),
    "functional_llm_decision_count": sum(
        1
        for row in LLM2_FUNCTIONAL_DECISION_ROWS
        if row.get(
            "decision_source"
        )
        == "ollama_llm2"
    ),
    "functional_fallback_count": sum(
        1
        for row in LLM2_FUNCTIONAL_DECISION_ROWS
        if row.get("decision_source") != "ollama_llm2"
    ),
    "functional_deterministic_decision_count": sum(
        1
        for row in LLM2_FUNCTIONAL_DECISION_ROWS
        if row.get("decision_source") != "ollama_llm2"
    ),
}
(
    OUTPUT_DIR
    / "llm2_run_summary.json"
).write_text(
    json.dumps(
        llm2_run_summary,
        indent=2,
    ),
    encoding="utf-8",
)
selected_functional_df, functional_symmetry_audit_df = (
    select_functional_candidates_symmetry_aware(
        functional_candidates_df,
        physical_targets_df,
        SYMMETRY_CENTER_PLANE,
        initial_reserved_coordinates=(
            [
                tuple(coordinate)
                for coordinates in selected_connectors_df.get(
                    "geometry_coordinates",
                    pd.Series(dtype=object),
                )
                for coordinate in coordinates
            ]
            if not selected_connectors_df.empty
            else []
        ),
    )
    if SYMMETRY_ENABLED
    else (
        select_nonoverlapping_candidates(
            functional_candidates_df,
            "physical_target_id",
            initial_reserved_coordinates=(
                [
                    tuple(coordinate)
                    for coordinates in selected_connectors_df.get(
                        "geometry_coordinates",
                        pd.Series(dtype=object),
                    )
                    for coordinate in coordinates
                ]
                if not selected_connectors_df.empty
                else []
            ),
        ),
        pd.DataFrame(),
    )
)
functional_symmetry_audit_df.to_csv(
    OUTPUT_DIR / "functional_symmetry_selection_audit.csv",
    index=False,
)

(
    selected_functional_df,
    functional_rotation_centering_audit_df,
) = center_selected_rotation_candidates(
    selected_functional_df
)
safe_export_dataframe(
    functional_rotation_centering_audit_df,
    OUTPUT_DIR
    / "functional_rotation_centering_audit.csv",
)

(
    selected_functional_df,
    wheel_orientation_audit_df,
) = validate_selected_wheel_orientations(
    selected_functional_df
)
safe_export_dataframe(
    wheel_orientation_audit_df,
    OUTPUT_DIR
    / "wheel_orientation_audit.csv",
)


# ------------------------------------------------------------
# Reservation selective reservation plan, finalized before structural packing
# ------------------------------------------------------------

reservation_llm2_interface_decision_by_id = {
    str(row.get("interface_id")): row
    for row in LLM2_INTERFACE_DECISION_ROWS
    if row.get("interface_id") is not None
}
(
    reservation_structural_interface_requirements_df,
    reservation_structural_interface_strategy_decisions_df,
) = reservation_direct_join_requirements(
    required_interfaces_df,
    structural_interface_payload,
    reservation_llm2_interface_decision_by_id,
)
(
    reservation_functional_interface_requirements_df,
    reservation_functional_interface_strategy_decisions_df,
) = reservation_selected_functional_requirements(
    selected_functional_df,
    segment_grid_planner,
    physical_targets_df,
)

reservation_selected_connector_requirements_df, _reservation_connector_requirement_mapping = (
    explode_selected_connector_face_requirements(
        selected_connectors_df
    )
)
if not reservation_selected_connector_requirements_df.empty:
    if "reservation_strategy" not in reservation_selected_connector_requirements_df.columns:
        reservation_selected_connector_requirements_df["reservation_strategy"] = "hard"
    reservation_selected_connector_requirements_df["reservation_scope"] = "structural_connector"
    reservation_selected_connector_requirements_df["reservation_owner_id"] = (
        reservation_selected_connector_requirements_df["interface_id"].astype(str)
    )

reservation_interface_reservation_requirements_df = pd.concat(
    [
        frame
        for frame in [
            reservation_structural_interface_requirements_df,
            reservation_selected_connector_requirements_df,
            reservation_functional_interface_requirements_df,
        ]
        if frame is not None and not frame.empty
    ],
    ignore_index=True,
    sort=False,
) if any(
    frame is not None and not frame.empty
    for frame in [
        reservation_structural_interface_requirements_df,
        reservation_selected_connector_requirements_df,
        reservation_functional_interface_requirements_df,
    ]
) else pd.DataFrame()

reservation_interface_strategy_decisions_df = pd.concat(
    [
        frame
        for frame in [
            reservation_structural_interface_strategy_decisions_df,
            reservation_functional_interface_strategy_decisions_df,
        ]
        if frame is not None and not frame.empty
    ],
    ignore_index=True,
    sort=False,
) if any(
    frame is not None and not frame.empty
    for frame in [
        reservation_structural_interface_strategy_decisions_df,
        reservation_functional_interface_strategy_decisions_df,
    ]
) else pd.DataFrame()

reservation_expected_hard_owner_ids = set()
if not reservation_interface_strategy_decisions_df.empty:
    for decision_row in reservation_interface_strategy_decisions_df.to_dict(orient="records"):
        if str(decision_row.get("reservation_strategy", "")).lower() != "hard":
            continue
        owner_id = (
            decision_row.get("physical_target_id")
            if str(decision_row.get("reservation_scope")) == "functional_attachment"
            else decision_row.get("interface_id")
        )
        if owner_id not in {None, "", "nan"}:
            reservation_expected_hard_owner_ids.add(str(owner_id))

reservation_generated_hard_owner_ids = set()
if not reservation_interface_reservation_requirements_df.empty:
    hard_requirements = reservation_interface_reservation_requirements_df.loc[
        reservation_interface_reservation_requirements_df[
            "reservation_strategy"
        ].astype(str).str.lower().eq("hard")
    ]
    reservation_generated_hard_owner_ids = set(
        hard_requirements.get(
            "reservation_owner_id",
            pd.Series(dtype=str),
        ).dropna().astype(str)
    )

reservation_missing_hard_requirement_owner_ids = sorted(
    reservation_expected_hard_owner_ids - reservation_generated_hard_owner_ids
)
reservation_hard_requirement_generation_complete = bool(
    not reservation_missing_hard_requirement_owner_ids
)

reservation_reservation_conflicts_df = reservation_reservation_conflicts(
    reservation_interface_reservation_requirements_df
)
reservation_reservation_conflicts_complete = bool(
    reservation_reservation_conflicts_df.empty
    or not reservation_reservation_conflicts_df.get(
        "severity",
        pd.Series(dtype=str),
    ).astype(str).eq("fatal").any()
)

# Both paired and unpaired segment planners now receive the same selective map.
deferred_connector_face_requirements_by_segment = reservation_requirement_mapping(
    reservation_interface_reservation_requirements_df
)
connector_face_requirements_by_segment = deferred_connector_face_requirements_by_segment

safe_export_dataframe(
    reservation_interface_strategy_decisions_df,
    OUTPUT_DIR / "reservation_interface_strategy_decisions.csv",
)
safe_export_dataframe(
    reservation_interface_reservation_requirements_df,
    OUTPUT_DIR / "reservation_interface_reservation_requirements.csv",
)
safe_export_dataframe(
    reservation_reservation_conflicts_df,
    OUTPUT_DIR / "reservation_interface_reservation_conflicts.csv",
)
(
    OUTPUT_DIR / "reservation_interface_reservation_preflight.json"
).write_text(
    json.dumps(
        {
            "enabled": bool(INTERFACE_RESERVATION_CONFIG.get("enabled", True)),
            "strategy_mode": INTERFACE_RESERVATION_CONFIG.get("strategy_mode"),
            "decision_count": int(len(reservation_interface_strategy_decisions_df)),
            "requirement_alternative_count": int(len(reservation_interface_reservation_requirements_df)),
            "requirement_group_count": int(
                reservation_interface_reservation_requirements_df.get(
                    "requirement_group_id",
                    pd.Series(dtype=str),
                ).nunique()
            ),
            "hard_group_count": int(
                reservation_interface_reservation_requirements_df.loc[
                    reservation_interface_reservation_requirements_df.get(
                        "reservation_strategy",
                        pd.Series(dtype=str),
                    ).astype(str).eq("hard"),
                    "requirement_group_id",
                ].nunique()
                if not reservation_interface_reservation_requirements_df.empty
                else 0
            ),
            "soft_group_count": int(
                reservation_interface_reservation_requirements_df.loc[
                    reservation_interface_reservation_requirements_df.get(
                        "reservation_strategy",
                        pd.Series(dtype=str),
                    ).astype(str).eq("soft"),
                    "requirement_group_id",
                ].nunique()
                if not reservation_interface_reservation_requirements_df.empty
                else 0
            ),
            "fatal_conflict_count": int(
                reservation_reservation_conflicts_df.get(
                    "severity",
                    pd.Series(dtype=str),
                ).astype(str).eq("fatal").sum()
            ),
            "hard_requirement_generation_complete": bool(
                reservation_hard_requirement_generation_complete
            ),
            "missing_hard_requirement_owner_ids": (
                reservation_missing_hard_requirement_owner_ids
            ),
            "whole_segment_reservation_prohibited": True,
            "replacement_removal_scope": "selected_validated_footprint_only",
        },
        indent=2,
    ),
    encoding="utf-8",
)

if (
    VISUALIZATION_CONFIG.get("enabled", True)
    and VISUALIZATION_CONFIG.get("interactive", True)
    and VISUALIZATION_CONFIG.get("generate_reservation_selective_reservation_view", True)
):
    write_interactive(
        reserved_face_interactive_figure(
            segment_grid_planner,
            reservation_interface_reservation_requirements_df,
        ),
        VISUALIZATION_DIR / "reservation_selective_interface_reservations.html",
        "reservation_selective_interface_reservations",
        "Hard, soft, and unreserved interface requirements",
        bool(
            VISUALIZATION_CONFIG.get(
                "show_inline_reservation_selective_reservation_view",
                False,
            )
        ),
    )

if (
    VISUALIZATION_CONFIG.get("enabled", True)
    and VISUALIZATION_CONFIG.get("interactive", True)
    and VISUALIZATION_CONFIG.get("generate_reservation_candidate_filter_view", True)
):
    write_interactive(
        reservation_candidate_reservation_figure(
            segment_grid_planner,
            reservation_functional_candidate_reservation_audit_df,
            selected_functional_df,
            "Reservation Functional Candidate Reservation Filtering",
        ),
        VISUALIZATION_DIR / "reservation_functional_candidate_filtering.html",
        "reservation_functional_candidate_filtering",
        "Selected, hard-rejected, soft-penalized, and valid functional candidates",
        bool(
            VISUALIZATION_CONFIG.get(
                "show_inline_reservation_candidate_filter_view",
                False,
            )
        ),
    )

safe_export_dataframe(
    connector_candidates_df,
    OUTPUT_DIR / "structural_connector_candidates.csv",
)
safe_export_dataframe(
    selected_connectors_df,
    OUTPUT_DIR / "structural_connector_selected_candidates.csv",
)
safe_export_dataframe(
    functional_candidates_df,
    OUTPUT_DIR / "functional_attachment_candidates.csv",
)
safe_export_dataframe(
    selected_functional_df,
    OUTPUT_DIR / "functional_attachment_selected_physical_instances.csv",
)

connector_catalog_audit = {
    "selector": (
        TASK_CONTEXT.get("segment_assembly", {})
        .get("structural_connector_policy", {})
        .get("catalog_selector", "segment_connector")
    ),
    "eligible_catalog_families": [
        record["block_family"]
        for record in connector_catalog_records
    ],
    "required_interface_count": len(required_interface_ids),
    "candidate_count": int(len(connector_candidates_df)),
    "selected_count": int(len(selected_connectors_df)),
}
(OUTPUT_DIR / "structural_connector_catalog_audit.json").write_text(
    json.dumps(connector_catalog_audit, indent=2),
    encoding="utf-8",
)

if (
    VISUALIZATION_CONFIG.get("enabled", True)
    and VISUALIZATION_CONFIG.get("interactive", True)
):
    planning_figure = planning_layers_figure(
        segment_grid_planner,
        structural_interface_payload,
        connector_candidates_df,
        selected_connectors_df,
        physical_targets_df,
        functional_candidates_df,
        selected_functional_df,
    )
    write_interactive(
        planning_figure,
        VISUALIZATION_DIR / "planning_layers_interactive.html",
        "candidate_planning",
        "Interactive planning layers",
        bool(
            VISUALIZATION_CONFIG.get(
                "show_inline_planning_layers",
                False,
            )
        ),
    )

# ------------------------------------------------------------
# 4. Connector reservation and independent segment packing
# ------------------------------------------------------------

prebuild_connector_candidate_mask = (
    mask_from_selected_candidates(
        segment_grid_structuralized.shape,
        selected_connectors_df,
    )
)
np.save(
    OUTPUT_DIR
    / "structural_connector_prebuild_candidate_mask.npy",
    prebuild_connector_candidate_mask,
)
# Embedded anchors do not remove structural voxels before packing.
connector_reservation_mask = np.zeros(
    segment_grid_structuralized.shape,
    dtype=bool,
)
np.save(
    OUTPUT_DIR
    / "structural_connector_reservation_mask.npy",
    connector_reservation_mask,
)


segment_results = []
segment_blocks = []
segment_blocks_by_id = defaultdict(list)
proper_build_step_visualization_rows = []
next_block_id = 1
processed_segment_ids = set()
symmetry_plan_audit_rows = []

packable_mask_by_segment = {
    int(segment_id): (
        segment_grid_structuralized
        == int(
            segment_id
        )
    )
    for segment_id in structural_segment_ids
}

pair_by_segment = {}
for pair_row in structural_symmetry_pairs:
    segment_a = int(pair_row["segment_a"])
    segment_b = int(pair_row["segment_b"])
    pair_by_segment[segment_a] = pair_row
    pair_by_segment[segment_b] = pair_row


def persist_segment_result(
    result,
    segment_id,
    label,
    packable_mask,
):
    segment_id = int(segment_id)
    display_name = segment_display_name_by_id.get(
        segment_id,
        f"Segment {segment_id}",
    )
    result["segment_name"] = display_name
    result["segment_display_name"] = display_name
    if "planning_result" in result:
        for block in result["planning_result"]["blocks"]:
            block.segment_name = display_name
            block.segment_display_name = display_name
    segment_directory = (
        OUTPUT_DIR
        / "segments"
        / f"segment_{int(segment_id):03d}"
    )
    segment_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    if "planning_result" in result:
        write_better_planner_outputs(
            result["planning_result"],
            segment_directory,
        )
        if result.get("consolidation_audit") is not None:
            (
                segment_directory
                / "segment_local_consolidation_audit.json"
            ).write_text(
                json.dumps(
                    result["consolidation_audit"],
                    indent=2,
                ),
                encoding="utf-8",
            )
        write_step_validation_outputs(
            result["validation"],
            segment_directory,
        )
        safe_export_dataframe(
            pd.DataFrame(
                result.get(
                    "connector_face_requirement_audit",
                    [],
                )
            ),
            segment_directory
            / "connector_receiving_face_audit.csv",
        )
        if VISUALIZATION_CONFIG.get(
            "save_static_validated_step_pngs",
            True,
        ):
            save_validated_segment_step_images(
                result,
                segment_directory,
                packable_mask.shape,
            )
        result_blocks = result[
            "planning_result"
        ]["blocks"]
        segment_blocks.extend(result_blocks)
        segment_blocks_by_id[int(segment_id)].extend(
            result_blocks
        )

        if VISUALIZATION_CONFIG.get("enabled", True):
            if VISUALIZATION_CONFIG.get(
                "save_static_segment_plan_png",
                True,
            ):
                visualize_blocks_static(
                    result_blocks,
                    grid_size=max(packable_mask.shape),
                    title=(
                        f"{display_name} (segment {segment_id}): "
                        f"{result.get('planning_mode', 'independent')}"
                    ),
                    output_path=(
                        segment_directory
                        / "block_plan_full_color.png"
                    ),
                    show_inline=False,
                )

            if VISUALIZATION_CONFIG.get(
                "interactive",
                True,
            ):
                write_interactive(
                    interactive_build_figure(
                        result_blocks,
                        (
                            f"{display_name} (segment {segment_id}): "
                            f"{result.get('planning_mode', 'independent')}"
                        ),
                        include_faces=True,
                    ),
                    segment_directory
                    / "block_plan_interactive.html",
                    "segment_plan",
                    (
                        f"Interactive block plan for "
                        f"segment {segment_id}"
                    ),
                    False,
                )
                write_interactive(
                    sequence_figure(
                        result_blocks,
                        block_appearance_from_steps(
                            result[
                                "planning_result"
                            ][
                                "instruction_steps"
                            ]
                        ),
                        (
                            f"{display_name} (segment {segment_id}): "
                            "Build Sequence"
                        ),
                    ),
                    segment_directory
                    / "build_sequence_interactive.html",
                    "segment_build_sequence",
                    (
                        f"Interactive build sequence "
                        f"for segment {segment_id}"
                    ),
                    bool(
                        VISUALIZATION_CONFIG.get(
                            "show_inline_segment_sequences",
                            False,
                        )
                    ),
                )
                if VISUALIZATION_CONFIG.get(
                    "generate_proper_segment_build_step_players",
                    True,
                ):
                    proper_step_path = (
                        segment_directory
                        / "validated_build_steps_interactive.html"
                    )
                    proper_step_figure = (
                        proper_build_step_figure(
                            result_blocks,
                            block_appearance_from_steps(
                                result[
                                    "planning_result"
                                ][
                                    "instruction_steps"
                                ]
                            ),
                            proper_build_step_labels_for_segment(
                                result
                            ),
                            (
                                f"{display_name} "
                                f"(segment {segment_id}) — "
                                "Validated Build Steps"
                            ),
                            source_grid=(
                                packable_mask.astype(
                                    int
                                )
                            ),
                        )
                    )
                    write_interactive(
                        proper_step_figure,
                        proper_step_path,
                        "proper_segment_build_steps",
                        (
                            f"Validated build steps for "
                            f"segment {segment_id}"
                        ),
                        bool(
                            VISUALIZATION_CONFIG.get(
                                "show_dedicated_inline_proper_segment_build_steps_cell",
                                False,
                            )
                        ),
                    )
                    proper_build_step_visualization_rows.append(
                        {
                            "segment_id": int(
                                segment_id
                            ),
                            "segment_name": (
                                display_name
                            ),
                            "segment_label": str(
                                label
                            ),
                            "selected_build_axis": (
                                result.get(
                                    "selected_build_axis"
                                )
                            ),
                            "valid": bool(
                                result.get(
                                    "valid",
                                    False,
                                )
                            ),
                            "step_count": int(
                                len(
                                    result[
                                        "planning_result"
                                    ][
                                        "instruction_steps"
                                    ]
                                )
                            ),
                            "html_path": str(
                                proper_step_path
                            ),
                        }
                    )

    segment_results.append(result)


for segment_id in structural_segment_ids:
    segment_id = int(segment_id)
    if segment_id in processed_segment_ids:
        continue

    pair_row = pair_by_segment.get(segment_id)

    if pair_row is None:
        label = segment_labels_dict.get(
            segment_id,
            "unknown",
        )
        mask = packable_mask_by_segment[
            segment_id
        ]
        try:
            result, next_block_id = plan_one_segment(
                segment_id,
                label,
                mask,
                next_block_id,
                connector_face_requirements=(
                    connector_face_requirements_by_segment.get(
                        segment_id,
                        [],
                    )
                ),
            )
            result["error"] = None
            result["planning_mode"] = (
                "independent_unpaired"
            )
            (
                result["inventory_reservation_id"],
                result["inventory_committed_requirements"],
            ) = inventory_commit_results_atomic(
                [result],
                scope=f"segment:{segment_id}",
            )
        except Exception as error:
            result = {
                "segment_id": segment_id,
                "segment_label": str(label),
                "valid": False,
                "exact_coverage": False,
                "packable_voxels": int(
                    mask.sum()
                ),
                "covered_voxels": 0,
                "extra_voxels": 0,
                "missing_voxels": int(
                    mask.sum()
                ),
                "planning_mode": (
                    "independent_unpaired_failed"
                ),
                "error": (
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
            }
        persist_segment_result(
            result,
            segment_id,
            label,
            mask,
        )
        processed_segment_ids.add(segment_id)
        continue

    template_segment_id, partner_segment_id = (
        choose_pair_template(pair_row)
    )
    if (
        template_segment_id in processed_segment_ids
        or partner_segment_id in processed_segment_ids
    ):
        continue

    template_label = segment_labels_dict.get(
        template_segment_id,
        "unknown",
    )
    partner_label = segment_labels_dict.get(
        partner_segment_id,
        "unknown",
    )
    template_mask = packable_mask_by_segment[
        template_segment_id
    ]
    partner_mask = packable_mask_by_segment[
        partner_segment_id
    ]
    mirrored_template_mask = mirror_mask(
        template_mask,
        SYMMETRY_AXIS_INDEX,
        SYMMETRY_CENTER_PLANE,
    )
    packable_iou = mask_iou(
        mirrored_template_mask,
        partner_mask,
    )
    packable_exact = bool(
        np.array_equal(
            mirrored_template_mask,
            partner_mask,
        )
    )

    template_result = None
    partner_result = None
    template_error = None
    partner_error = None
    mirror_attempted = False
    mirror_succeeded = False
    mirror_direction = None
    template_recovered_from_partner = False

    try:
        template_result, next_block_id = (
            plan_one_segment(
                template_segment_id,
                template_label,
                template_mask,
                next_block_id,
                connector_face_requirements=(
                    deferred_connector_face_requirements_by_segment.get(
                        template_segment_id,
                        [],
                    )
                ),
                inventory_multiplier=2,
                inventory_scope=(
                    f"symmetry_pair:{pair_row['pair_id']}"
                ),
            )
        )
        template_result[
            "error"
        ] = None
        template_result[
            "planning_mode"
        ] = (
            "independent_symmetry_template"
        )
        template_result[
            "symmetry_pair_id"
        ] = pair_row[
            "pair_id"
        ]
    except Exception as error:
        template_error = (
            f"{type(error).__name__}: "
            f"{error}"
        )
        template_result = {
            "segment_id": (
                template_segment_id
            ),
            "segment_label": str(
                template_label
            ),
            "valid": False,
            "exact_coverage": False,
            "packable_voxels": int(
                template_mask.sum()
            ),
            "covered_voxels": 0,
            "extra_voxels": 0,
            "missing_voxels": int(
                template_mask.sum()
            ),
            "planning_mode": (
                "symmetry_template_failed"
            ),
            "symmetry_pair_id": (
                pair_row[
                    "pair_id"
                ]
            ),
            "error": (
                template_error
            ),
        }

    if (
        template_result.get(
            "valid",
            False,
        )
        and packable_exact
    ):
        mirror_attempted = True
        mirror_direction = (
            f"{template_segment_id}"
            f"_to_"
            f"{partner_segment_id}"
        )
        try:
            partner_result, next_block_id = (
                mirror_planning_result(
                    template_result,
                    template_segment_id,
                    partner_segment_id,
                    partner_label,
                    partner_mask,
                    next_block_id,
                    SYMMETRY_CENTER_PLANE,
                    partner_connector_face_requirements=(
                        deferred_connector_face_requirements_by_segment.get(
                            partner_segment_id,
                            [],
                        )
                    ),
                )
            )
            partner_result[
                "error"
            ] = None
            partner_result[
                "symmetry_pair_id"
            ] = pair_row[
                "pair_id"
            ]
            mirror_succeeded = bool(
                partner_result.get(
                    "valid",
                    False,
                )
            )
        except Exception as error:
            partner_error = (
                f"{type(error).__name__}: "
                f"{error}"
            )
            partner_result = None

    if (
        partner_result is None
        or not partner_result.get(
            "valid",
            False,
        )
    ):
        try:
            partner_result, next_block_id = (
                plan_one_segment(
                    partner_segment_id,
                    partner_label,
                    partner_mask,
                    next_block_id,
                    connector_face_requirements=(
                        deferred_connector_face_requirements_by_segment.get(
                            partner_segment_id,
                            [],
                        )
                    ),
                )
            )
            partner_result[
                "error"
            ] = (
                partner_error
            )
            partner_result[
                "planning_mode"
            ] = (
                "independent_symmetry_fallback"
            )
            partner_result[
                "symmetry_pair_id"
            ] = pair_row[
                "pair_id"
            ]
        except Exception as error:
            partner_error = (
                f"{type(error).__name__}: "
                f"{error}"
            )
            partner_result = {
                "segment_id": (
                    partner_segment_id
                ),
                "segment_label": str(
                    partner_label
                ),
                "valid": False,
                "exact_coverage": False,
                "packable_voxels": int(
                    partner_mask.sum()
                ),
                "covered_voxels": 0,
                "extra_voxels": 0,
                "missing_voxels": int(
                    partner_mask.sum()
                ),
                "planning_mode": (
                    "independent_symmetry_"
                    "fallback_failed"
                ),
                "symmetry_pair_id": (
                    pair_row[
                        "pair_id"
                    ]
                ),
                "error": (
                    partner_error
                ),
            }

    # Reverse recovery: a successful partner becomes the template when the
    # originally chosen template could not be built.
    if (
        not template_result.get(
            "valid",
            False,
        )
        and partner_result.get(
            "valid",
            False,
        )
        and packable_exact
    ):
        mirror_attempted = True
        mirror_direction = (
            f"{partner_segment_id}"
            f"_to_"
            f"{template_segment_id}"
        )
        try:
            recovered_template, next_block_id = (
                mirror_planning_result(
                    partner_result,
                    partner_segment_id,
                    template_segment_id,
                    template_label,
                    template_mask,
                    next_block_id,
                    SYMMETRY_CENTER_PLANE,
                    partner_connector_face_requirements=(
                        deferred_connector_face_requirements_by_segment.get(
                            template_segment_id,
                            [],
                        )
                    ),
                )
            )
            recovered_template[
                "error"
            ] = None
            recovered_template[
                "planning_mode"
            ] = (
                f"mirrored_from_segment_"
                f"{partner_segment_id}"
            )
            recovered_template[
                "symmetry_pair_id"
            ] = pair_row[
                "pair_id"
            ]
            if recovered_template.get(
                "valid",
                False,
            ):
                template_result = (
                    recovered_template
                )
                template_recovered_from_partner = True
                mirror_succeeded = True
        except Exception as error:
            template_error = (
                f"{template_error or ''}; "
                "reverse_mirror_failed: "
                f"{type(error).__name__}: "
                f"{error}"
            ).strip(
                "; "
            )

    if (
        template_result.get("valid", False)
        and partner_result.get("valid", False)
    ):
        (
            pair_inventory_reservation_id,
            pair_inventory_requirements,
        ) = inventory_commit_results_atomic(
            [template_result, partner_result],
            scope=f"symmetry_pair:{pair_row['pair_id']}",
        )
        template_result["inventory_reservation_id"] = (
            pair_inventory_reservation_id
        )
        partner_result["inventory_reservation_id"] = (
            pair_inventory_reservation_id
        )
        template_result["inventory_committed_requirements"] = (
            pair_inventory_requirements
        )
        partner_result["inventory_committed_requirements"] = (
            pair_inventory_requirements
        )

    persist_segment_result(
        template_result,
        template_segment_id,
        template_label,
        template_mask,
    )
    persist_segment_result(
        partner_result,
        partner_segment_id,
        partner_label,
        partner_mask,
    )

    comparison = (
        compare_paired_block_plans(
            segment_blocks_by_id.get(
                template_segment_id,
                [],
            ),
            segment_blocks_by_id.get(
                partner_segment_id,
                [],
            ),
            SYMMETRY_CENTER_PLANE,
        )
    )

    pair_plan_valid = bool(
        packable_exact
        and template_result.get(
            "valid",
            False,
        )
        and partner_result.get(
            "valid",
            False,
        )
        and comparison[
            "block_plan_exact_mirror"
        ]
    )
    symmetry_plan_audit_rows.append(
        {
            "pair_id": (
                pair_row[
                    "pair_id"
                ]
            ),
            "template_segment_id": int(
                template_segment_id
            ),
            "partner_segment_id": int(
                partner_segment_id
            ),
            "source_mirror_iou": float(
                pair_row[
                    "source_mirror_iou"
                ]
            ),
            "packable_mirror_iou": float(
                packable_iou
            ),
            "packable_masks_exact": (
                packable_exact
            ),
            "mirror_attempted": (
                mirror_attempted
            ),
            "mirror_direction": (
                mirror_direction
            ),
            "mirror_succeeded": (
                mirror_succeeded
            ),
            "template_recovered_from_partner": bool(
                template_recovered_from_partner
            ),
            **comparison,
            "pair_plan_valid": (
                pair_plan_valid
            ),
            "template_error": (
                template_error
            ),
            "partner_error": (
                partner_error
            ),
        }
    )

    if VISUALIZATION_CONFIG.get(
        "interactive",
        True,
    ):
        pair_blocks = (
            segment_blocks_by_id.get(
                template_segment_id,
                [],
            )
            + segment_blocks_by_id.get(
                partner_segment_id,
                [],
            )
        )
        write_interactive(
            interactive_build_figure(
                pair_blocks,
                (
                    f"Symmetry Pair "
                    f"{pair_row['pair_id']} — "
                    f"{'VALID' if pair_plan_valid else 'REVIEW'}"
                ),
                include_faces=True,
            ),
            VISUALIZATION_DIR
            / "symmetry_pairs"
            / (
                f"{pair_row['pair_id']}_"
                "interactive.html"
            ),
            "symmetry_pair",
            (
                f"Interactive paired subassembly "
                f"audit for {pair_row['pair_id']}"
            ),
            bool(
                VISUALIZATION_CONFIG.get(
                    "show_inline_symmetry_pairs",
                    False,
                )
            ),
        )

    processed_segment_ids.update({
        template_segment_id,
        partner_segment_id,
    })

segment_symmetry_plan_audit_df = pd.DataFrame(
    symmetry_plan_audit_rows
)
segment_symmetry_plan_audit_df.to_csv(
    OUTPUT_DIR / "segment_symmetry_plan_audit.csv",
    index=False,
)

# ------------------------------------------------------------
# Global deferred inventory allocation
# ------------------------------------------------------------
GLOBAL_INVENTORY_ALLOCATION = {
    "status": "NOT_REQUESTED",
    "coordination_mode": INVENTORY_COORDINATION_MODE,
    "pending_groups": PENDING_INVENTORY_REQUIREMENTS,
    "required_functional_reserve": {},
    "aggregate_requirements": {},
    "shortages": {},
    "committed": False,
}
if GLOBAL_DEFERRED_INVENTORY:
    from collections import Counter as _InventoryCounter

    required_functional_reserve = _InventoryCounter()
    # A required functional attachment may also be the connector component of a
    # declarative functional assembly. Track those physical targets so the same
    # catalog block is reserved once rather than once per declaration layer.
    attachment_family_by_target = {}
    for declaration in TASK_CONTEXT.get("functional_attachments", []) or []:
        if not bool(declaration.get("required", False)):
            continue
        family = str(
            declaration.get("required_block_family")
            or (declaration.get("block_family_requirement", {}) or {}).get(
                "required_block_family", ""
            )
        ).strip()
        expected = int(declaration.get("expected_count", 0) or 0)
        if family and expected > 0:
            required_functional_reserve[family] += expected

        grouping = declaration.get("physical_target_grouping", {}) or {}
        groups = grouping.get("manual_groups", []) or []
        target_ids = {
            str(group.get("physical_target_id", "")).strip()
            for group in groups
            if str(group.get("physical_target_id", "")).strip()
        }
        if not target_ids:
            attachment_id = str(declaration.get("attachment_id", "")).strip()
            if attachment_id:
                target_ids.add(attachment_id)
        for target_id in target_ids:
            attachment_family_by_target[target_id] = family

    for assembly in TASK_CONTEXT.get("functional_assemblies", []) or []:
        if not bool(assembly.get("enabled", True)):
            continue
        assembly_id = str(
            assembly.get("physical_target_id")
            or assembly.get("assembly_id")
            or ""
        ).strip()
        members = assembly.get("members", {}) or {}
        structural_count = int(members.get("count", 0) or 0)
        structural_family = str(members.get("required_block_family", "")).strip()
        if structural_count > 0 and structural_family:
            required_functional_reserve[structural_family] += structural_count
        connector = assembly.get("connector", {}) or {}
        connector_family = str(connector.get("required_block_family", "")).strip()
        connector_is_already_reserved = bool(
            assembly_id
            and connector_family
            and attachment_family_by_target.get(assembly_id) == connector_family
        )
        if connector_family and not connector_is_already_reserved:
            required_functional_reserve[connector_family] += int(
                connector.get("count", 1) or 1
            )

    aggregate = _InventoryCounter(required_functional_reserve)
    for row in PENDING_INVENTORY_REQUIREMENTS:
        aggregate.update(row.get("requirements", {}))

    global_check = InventoryLedger(INVENTORY_PROFILE).check(dict(aggregate))
    all_required_segments_valid = bool(
        segment_results
        and all(bool(result.get("valid", False)) for result in segment_results)
        and len(segment_results) == len(structural_segment_ids)
    )
    global_feasible = bool(
        (not INVENTORY_ENFORCED or global_check["feasible"])
        and all_required_segments_valid
    )
    if global_feasible and aggregate:
        global_reservation_id = INVENTORY_LEDGER.reserve_and_commit(
            dict(aggregate),
            "global_model_allocation",
        )
    else:
        global_reservation_id = None

    GLOBAL_INVENTORY_ALLOCATION = {
        "status": (
            "PASS"
            if global_feasible
            else (
                "FAIL_STRUCTURAL_SEGMENTS_INCOMPLETE"
                if not all_required_segments_valid
                else "FAIL_NO_GLOBAL_INVENTORY_ALLOCATION"
            )
        ),
        "coordination_mode": INVENTORY_COORDINATION_MODE,
        "pending_groups": PENDING_INVENTORY_REQUIREMENTS,
        "required_functional_reserve": dict(
            sorted(required_functional_reserve.items())
        ),
        "aggregate_requirements": dict(sorted(aggregate.items())),
        "shortages": global_check.get("shortages", {}),
        "all_required_segments_valid": all_required_segments_valid,
        "structural_result_count": len(segment_results),
        "expected_structural_segment_count": len(structural_segment_ids),
        "reservation_id": global_reservation_id,
        "committed": bool(global_reservation_id),
    }
    (OUTPUT_DIR / "global_inventory_allocation.json").write_text(
        json.dumps(GLOBAL_INVENTORY_ALLOCATION, indent=2),
        encoding="utf-8",
    )
    safe_export_dataframe(
        pd.DataFrame(PENDING_INVENTORY_REQUIREMENTS),
        OUTPUT_DIR / "global_inventory_candidate_requirements.csv",
    )

all_receiving_face_audit_rows = [
    row
    for result in segment_results
    for row in result.get(
        "connector_face_requirement_audit",
        [],
    )
]
connector_receiving_face_final_audit_df = pd.DataFrame(
    all_receiving_face_audit_rows
)
safe_export_dataframe(
    connector_receiving_face_final_audit_df,
    OUTPUT_DIR
    / "connector_receiving_face_final_audit.csv",
)
connector_receiving_faces_complete = bool(
    connector_receiving_face_requirements_df.empty
    or (
        not connector_receiving_face_final_audit_df.empty
        and connector_receiving_face_final_audit_df[
            "satisfied"
        ].astype(bool).all()
        and len(
            connector_receiving_face_final_audit_df
        )
        == len(
            connector_receiving_face_requirements_df
        )
    )
)

symmetry_requires_pairs = bool(
    SYMMETRY_ENABLED
    and SYMMETRY_CONFIG.get(
        "require_at_least_one_valid_pair",
        False,
    )
)
pair_count_valid = bool(
    len(structural_symmetry_pairs) > 0
    or not symmetry_requires_pairs
)
all_pair_plans_valid = bool(
    segment_symmetry_plan_audit_df.empty
    or segment_symmetry_plan_audit_df[
        "pair_plan_valid"
    ].astype(bool).all()
)
structural_symmetry_complete = bool(
    (
        not SYMMETRY_ENABLED
        or SYMMETRY_CONFIG.get(
            "enforcement",
            "audit_only",
        ) == "audit_only"
    )
    or (
        pair_count_valid
        and all_pair_plans_valid
    )
)

segment_validation_rows = [
    {
        key: value
        for key, value in result.items()
        if key not in {
            "planning_result",
            "validation",
            "connector_face_requirement_audit",
        }
    }
    for result in segment_results
]
segment_subassembly_validation_df = pd.DataFrame(
    segment_validation_rows
)
segment_subassembly_validation_df.to_csv(
    OUTPUT_DIR / "segment_subassembly_validation.csv",
    index=False,
)

segment_build_gate_passed = bool(
    len(
        segment_results
    )
    == len(
        structural_segment_ids
    )
    and all(
        result.get(
            "valid",
            False,
        )
        for result in (
            segment_results
        )
    )
)
failed_segment_gate_mode = str(
    TASK_CONTEXT.get(
        "segment_assembly",
        {},
    )
    .get(
        "segment_packing",
        {},
    )
    .get(
        "failed_segment_gate",
        "",
    )
)
skip_downstream_physical_instantiation = bool(
    not segment_build_gate_passed
    and failed_segment_gate_mode
    == (
        "skip_connector_and_functional_instantiation_"
        "but_write_diagnostics"
    )
)
segment_build_gate_summary = {
    "passed": bool(
        segment_build_gate_passed
    ),
    "mode": (
        failed_segment_gate_mode
    ),
    "skip_downstream_physical_instantiation": bool(
        skip_downstream_physical_instantiation
    ),
    "full_model_player_suppressed_when_invalid": bool(
        VISUALIZATION_CONFIG.get(
            "suppress_full_model_player_when_final_claim_invalid",
            True,
        )
    ),
    "failed_segment_ids": [
        int(
            result[
                "segment_id"
            ]
        )
        for result in (
            segment_results
        )
        if not result.get(
            "valid",
            False,
        )
    ],
}
(
    OUTPUT_DIR
    / "segment_build_gate_summary.json"
).write_text(
    json.dumps(
        segment_build_gate_summary,
        indent=2,
    ),
    encoding="utf-8",
)

# ------------------------------------------------------------
# 4b. Required embedded-anchor connector synthesis and validation
# ------------------------------------------------------------

embedded_connector_candidates_df = (
    generate_required_embedded_connector_candidates(
        required_interfaces_df,
        structural_interface_payload,
        interface_catalog_query_by_id,
    )
)

postbuild_connector_candidate_validation_df = (
    validate_required_embedded_connectors(
        embedded_connector_candidates_df,
        segment_blocks_by_id,
    )
    if segment_build_gate_passed
    else embedded_connector_candidates_df.iloc[
        0:0
    ].copy()
)

physically_valid_connector_candidates_df = (
    postbuild_connector_candidate_validation_df.loc[
        postbuild_connector_candidate_validation_df.get(
            "postbuild_valid",
            pd.Series(
                False,
                index=(
                    postbuild_connector_candidate_validation_df.index
                ),
            ),
        ).astype(
            bool
        )
    ].copy()
    if not postbuild_connector_candidate_validation_df.empty
    else postbuild_connector_candidate_validation_df.copy()
)

if segment_build_gate_passed:
    (
        selected_connectors_df,
        postbuild_connector_symmetry_audit_df,
    ) = (
        select_connector_candidates_symmetry_aware(
            physically_valid_connector_candidates_df,
            required_interfaces_df,
            structural_symmetry_pairs,
            structural_segment_ids,
            SYMMETRY_CENTER_PLANE,
        )
        if SYMMETRY_ENABLED
        else (
            select_nonoverlapping_candidates(
                physically_valid_connector_candidates_df,
                "interface_id",
            ),
            pd.DataFrame(),
        )
    )

    selected_interface_ids = set(
        selected_connectors_df.get(
            "interface_id",
            pd.Series(
                dtype=str
            ),
        ).astype(
            str
        )
    )
    if selected_interface_ids != set(
        required_interface_ids
    ):
        selected_connectors_df = (
            physically_valid_connector_candidates_df.sort_values(
                [
                    "interface_id",
                    "score",
                ],
                ascending=[
                    True,
                    False,
                ],
            )
            .drop_duplicates(
                "interface_id",
                keep="first",
            )
            .reset_index(
                drop=True
            )
        )
        postbuild_connector_symmetry_audit_df = pd.DataFrame(
            [
                {
                    "selection_status": (
                        "selected_embedded_anchor_required_interface_set"
                    ),
                    "selected_count": int(
                        len(
                            selected_connectors_df
                        )
                    ),
                    "required_count": int(
                        len(
                            required_interface_ids
                        )
                    ),
                    "valid": bool(
                        set(
                            selected_connectors_df[
                                "interface_id"
                            ].astype(
                                str
                            )
                        )
                        == set(
                            required_interface_ids
                        )
                    ),
                }
            ]
        )
else:
    selected_connectors_df = (
        embedded_connector_candidates_df.iloc[
            0:0
        ].copy()
    )
    postbuild_connector_symmetry_audit_df = (
        pd.DataFrame()
    )

safe_export_dataframe(
    embedded_connector_candidates_df,
    OUTPUT_DIR
    / "embedded_anchor_connector_candidates.csv",
)
safe_export_dataframe(
    postbuild_connector_candidate_validation_df,
    OUTPUT_DIR
    / "postbuild_structural_connector_candidate_validation.csv",
)
safe_export_dataframe(
    postbuild_connector_symmetry_audit_df,
    OUTPUT_DIR
    / "postbuild_connector_symmetry_selection_audit.csv",
)
safe_export_dataframe(
    selected_connectors_df,
    OUTPUT_DIR
    / "structural_connector_selected_candidates.csv",
)

segment_block_rows = []
for block in segment_blocks:
    segment_block_rows.append({
        "block_id": int(block.block_id),
        "block_role": block.block_role,
        "source_segment_id": int(block.source_segment_id),
        "segment_label": block.segment_label,
        "segment_name": getattr(
            block,
            "segment_name",
            segment_display_name_by_id.get(
                int(block.source_segment_id),
                f"Segment {int(block.source_segment_id)}",
            ),
        ),
        "subassembly_id": block.subassembly_id,
        "block_family": block.block_family,
        "position": tuple(int(value) for value in block.position),
        "size": tuple(int(value) for value in block.size),
        "rotation": int(block.rotation),
        "male_face": male_face_for_rotation(
            block.rotation,
            block.size,
        ),
        "symmetry_source_segment_id": getattr(
            block,
            "symmetry_source_segment_id",
            None,
        ),
    })
segment_subassembly_blocks_df = pd.DataFrame(
    segment_block_rows
)
safe_export_dataframe(
    segment_subassembly_blocks_df,
    OUTPUT_DIR / "segment_subassembly_blocks.csv",
)

# ------------------------------------------------------------
# 5. Instantiate selected connector and functional blocks
# ------------------------------------------------------------

nonstructural_catalog_normalization_rows = []

for candidate_scope, candidate_frame in [
    (
        "connector",
        selected_connectors_df,
    ),
    (
        "functional_attachment",
        selected_functional_df,
    ),
]:
    for _, candidate_row in (
        candidate_frame.iterrows()
    ):
        candidate_record = (
            candidate_row.to_dict().get(
                "catalog_record",
                {},
            )
        )
        normalized_record = (
            prepare_general_catalog_record(
                candidate_record
            )
        )
        nonstructural_catalog_normalization_rows.append(
            {
                "scope": (
                    candidate_scope
                ),
                "candidate_id": (
                    candidate_row.get(
                        "candidate_id"
                    )
                ),
                "interface_id": (
                    candidate_row.get(
                        "interface_id"
                    )
                ),
                "physical_target_id": (
                    candidate_row.get(
                        "physical_target_id"
                    )
                ),
                "block_family": (
                    candidate_row.get(
                        "block_family"
                    )
                ),
                "raw_record_had_color_rgb": bool(
                    isinstance(
                        candidate_record,
                        dict,
                    )
                    and "color_rgb"
                    in candidate_record
                ),
                "normalized_color_rgb": (
                    tuple(
                        int(
                            value
                        )
                        for value in (
                            normalized_record[
                                "color_rgb"
                            ]
                        )
                    )
                ),
                "color_normalization_source": (
                    normalized_record.get(
                        "color_normalization_source"
                    )
                ),
                "native_size": (
                    tuple(
                        int(
                            value
                        )
                        for value in (
                            normalized_record[
                                "native_size"
                            ]
                        )
                    )
                ),
            }
        )

nonstructural_catalog_normalization_df = pd.DataFrame(
    nonstructural_catalog_normalization_rows
)
safe_export_dataframe(
    nonstructural_catalog_normalization_df,
    OUTPUT_DIR
    / "nonstructural_catalog_normalization_audit.csv",
)

connector_blocks = []
functional_blocks = []
generic_functional_blocks = []
custom_subassembly_instances = []

optional_candidate_field_audit_rows = []
for candidate_scope, candidate_frame in [
    (
        "functional",
        selected_functional_df,
    ),
    (
        "connector",
        selected_connectors_df,
    ),
]:
    for _, candidate_row in candidate_frame.iterrows():
        candidate_dict = candidate_row.to_dict()
        raw_axis = candidate_dict.get(
            "wheel_axle_axis_index"
        )
        normalized_axis = candidate_optional_value(
            candidate_dict,
            "wheel_axle_axis_index",
        )
        optional_candidate_field_audit_rows.append(
            {
                "scope": candidate_scope,
                "physical_target_id": (
                    candidate_optional_value(
                        candidate_dict,
                        "physical_target_id",
                    )
                ),
                "interface_id": (
                    candidate_optional_value(
                        candidate_dict,
                        "interface_id",
                    )
                ),
                "block_family": (
                    candidate_optional_value(
                        candidate_dict,
                        "block_family",
                    )
                ),
                "raw_wheel_axle_axis_index": raw_axis,
                "normalized_wheel_axle_axis_index": (
                    normalized_axis
                ),
                "wheel_orientation_applied": bool(
                    normalized_axis
                    is not None
                ),
            }
        )

optional_candidate_field_audit_df = pd.DataFrame(
    optional_candidate_field_audit_rows
)
safe_export_dataframe(
    optional_candidate_field_audit_df,
    OUTPUT_DIR
    / "optional_candidate_field_normalization_audit.csv",
)

if not skip_downstream_physical_instantiation:
    # Ordinary rigid joins do not instantiate hinge blocks.
    for _, candidate in (
        selected_functional_df.iterrows()
    ):
        candidate_dict = (
            candidate.to_dict()
        )
        target_id = str(candidate_dict.get("physical_target_id", ""))
        subassembly_config = custom_functional_subassembly_config_for_target(target_id)
        if subassembly_config:
            (
                motion_connector_block,
                subassembly_blocks,
                subassembly_audit,
                next_block_id,
            ) = create_motion_connected_structural_subassembly(
                subassembly_config,
                candidate_dict,
                next_block_id,
            )
            custom_subassembly_instances.append({
                "config": subassembly_config,
                "connector_block": motion_connector_block,
                "member_blocks": subassembly_blocks,
                "audit": subassembly_audit,
            })
            functional_blocks.append(motion_connector_block)
            functional_blocks.extend(subassembly_blocks)
            continue

        functional_block = (
            make_nonstructural_block(
                candidate_dict,
                next_block_id,
                category=(
                    "functional_attachment"
                ),
            )
        )
        generic_functional_blocks.append(
            functional_block
        )
        functional_blocks.append(
            functional_block
        )
        next_block_id += 1

    (
        OUTPUT_DIR
        / "custom_subassembly_audit.json"
    ).write_text(
        json.dumps(
            json_safe_value({
                "enabled": custom_functional_subassembly_enabled(),
                "assembly_count": len(custom_subassembly_instances),
                "assemblies": [
                    instance["audit"]
                    for instance in custom_subassembly_instances
                ],
            }),
            indent=2,
        ),
        encoding="utf-8",
    )
else:
    pipeline_log(
        "show_gate_messages",
        (
            "[SEGMENT BUILD GATE] "
            "Connector and functional block instantiation "
            "was skipped because at least one structural "
            "segment subassembly is invalid."
        ),
    )

# ------------------------------------------------------------
# 6. Final mechanical validation
# ------------------------------------------------------------

connector_validation_rows = []
connector_validation_df = pd.DataFrame(
    columns=[
        "interface_id",
        "connector_block_id",
        "segment_a",
        "segment_b",
        "locks_to_segment_a",
        "locks_to_segment_b",
        "lock_area_segment_a",
        "lock_area_segment_b",
        "contact_count",
        "join_mode",
        "valid",
    ]
)
connector_receiving_face_requirements_df = (
    pd.DataFrame()
)
connector_receiving_face_final_audit_df = (
    pd.DataFrame()
)
connector_receiving_faces_complete = False

functional_validation_rows = [
    validate_functional_block(
        functional_block,
        segment_blocks_by_id,
    )
    for functional_block in generic_functional_blocks
]
for instance in custom_subassembly_instances:
    functional_validation_rows.append(
        validate_motion_connected_structural_subassembly(
            instance["config"],
            instance["connector_block"],
            instance["member_blocks"],
            segment_blocks_by_id,
        )
    )
functional_validation_df = pd.DataFrame(
    functional_validation_rows
)
functional_validation_df.to_csv(
    OUTPUT_DIR / "functional_attachment_validation.csv",
    index=False,
)
custom_subassembly_target_ids = {
    str(
        instance["config"].get("physical_target_id")
        or instance["config"].get("assembly_id")
        or ""
    )
    for instance in custom_subassembly_instances
}
custom_subassembly_validation_df = (
    functional_validation_df.loc[
        functional_validation_df.get(
            "physical_target_id",
            pd.Series(dtype=str),
        ).astype(str).isin(custom_subassembly_target_ids)
    ].copy()
)
safe_export_dataframe(
    custom_subassembly_validation_df,
    OUTPUT_DIR
    / "functional_subassembly_validation.csv",
)

direct_cross_segment_rows = []
for index_a, block_a in enumerate(segment_blocks):
    for block_b in segment_blocks[index_a + 1:]:
        if (
            int(block_a.source_segment_id)
            == int(block_b.source_segment_id)
        ):
            continue
        contact = contact_status_between_blocks(
            block_a,
            block_b,
        )
        if contact is None:
            continue
        if contact["contact_status"] in {
            "male_to_female_lock",
            "male_to_male_conflict",
            "geometric_overlap_conflict",
        }:
            direct_cross_segment_rows.append({
                **contact,
                "segment_a": int(block_a.source_segment_id),
                "segment_b": int(block_b.source_segment_id),
            })
direct_cross_segment_df = pd.DataFrame(
    direct_cross_segment_rows
)
direct_cross_segment_df.to_csv(
    OUTPUT_DIR / "direct_cross_segment_structural_contacts.csv",
    index=False,
)

(
    connector_validation_df,
    direct_structural_join_candidate_audit_df,
) = direct_structural_join_tree(
    direct_cross_segment_df,
    structural_segment_ids,
)
connector_validation_rows = (
    connector_validation_df.to_dict(
        orient="records"
    )
)
safe_export_dataframe(
    connector_validation_df,
    OUTPUT_DIR
    / "structural_connector_validation.csv",
)
safe_export_dataframe(
    direct_structural_join_candidate_audit_df,
    OUTPUT_DIR
    / "direct_structural_join_candidate_audit.csv",
)

connector_receiving_face_requirements_df = pd.DataFrame(
    [
        {
            "interface_id": str(
                row.interface_id
            ),
            "segment_id": int(
                segment_id
            ),
            "requirement_group_id": (
                f"{row.interface_id}:"
                f"segment_{int(segment_id)}"
            ),
            "selection_mode": (
                "direct_structural_lock"
            ),
            "satisfied": bool(
                row.valid
            ),
        }
        for row in (
            connector_validation_df.itertuples(
                index=False
            )
        )
        for segment_id in (
            int(
                row.segment_a
            ),
            int(
                row.segment_b
            ),
        )
    ]
)
connector_receiving_face_final_audit_df = (
    connector_receiving_face_requirements_df.copy()
)
safe_export_dataframe(
    connector_receiving_face_requirements_df,
    OUTPUT_DIR
    / "connector_receiving_face_requirements.csv",
)
safe_export_dataframe(
    connector_receiving_face_final_audit_df,
    OUTPUT_DIR
    / "connector_receiving_face_final_audit.csv",
)
connector_receiving_faces_complete = bool(
    len(
        connector_validation_df
    )
    == max(
        0,
        len(
            structural_segment_ids
        )
        - 1
    )
    and connector_validation_df[
        "valid"
    ].astype(
        bool
    ).all()
)

all_final_blocks = (
    segment_blocks
    + connector_blocks
    + functional_blocks
)


def assign_display_render_axes(blocks):
    structural_blocks = [
        block
        for block in blocks
        if str(
            getattr(
                block,
                "block_role",
                getattr(block, "category", ""),
            )
        ).lower() in {"segment_structural", "structural", "segment"}
    ]

    for block in blocks:
        record = getattr(block, "catalog_record", {}) or {}
        role = str(record.get("functional_role", "")).lower()
        family = str(getattr(block, "block_family", "")).lower()
        if (
            role == "wheel"
            or "wheel" in family
        ):
            block.render_axis = 0
            block.render_axis_face = "X_AXLE"
            block.wheel_axle_axis = "X"
            block.wheel_disc_plane = "YZ"
            block.wheel_vertical_axis = "Z"
            continue

        if family != "rotation_block":
            continue

        best_contact = None
        best_area = -1
        for structural_block in structural_blocks:
            if int(structural_block.block_id) == int(block.block_id):
                continue
            contact = touching_face_geometry(block, structural_block)
            if contact is None:
                continue
            if contact.get("geometry_status") != "face_contact":
                continue
            area = int(contact.get("overlap_area") or 0)
            if area > best_area:
                best_area = area
                best_contact = contact

        if best_contact is not None and best_contact.get("face_a") in FACE_AXIS_SIGN:
            block.render_axis = int(FACE_AXIS_SIGN[best_contact["face_a"]][0])
            block.render_axis_face = str(best_contact["face_a"])

assign_display_render_axes(all_final_blocks)
collision_rows = []
intended_anchor_overlap_rows = []
for index_a, block_a in enumerate(
    all_final_blocks
):
    for block_b in all_final_blocks[
        index_a + 1:
    ]:
        contact = touching_face_geometry(
            block_a,
            block_b,
        )
        if (
            contact is None
            or contact[
                "geometry_status"
            ]
            != "geometric_overlap_conflict"
        ):
            continue
        if intended_embedded_anchor_overlap(
            block_a,
            block_b,
        ):
            intended_anchor_overlap_rows.append(
                {
                    **contact,
                    "allowed_reason": (
                        "embedded_connector_anchor_layer"
                    ),
                }
            )
            continue
        collision_rows.append(
            contact
        )
collision_audit_columns = [
    "block_a",
    "block_b",
    "face_a",
    "face_b",
    "overlap_area",
    "geometry_status",
    "contact_status",
]
collision_df = pd.DataFrame(
    collision_rows,
    columns=collision_audit_columns,
)
intended_anchor_overlap_df = pd.DataFrame(
    intended_anchor_overlap_rows,
    columns=(
        collision_audit_columns
        + [
            "allowed_reason"
        ]
    ),
)
safe_export_dataframe(
    intended_anchor_overlap_df,
    OUTPUT_DIR
    / "intended_anchor_overlap_audit.csv",
)
safe_export_dataframe(
    collision_df,
    OUTPUT_DIR
    / "final_block_collision_audit.csv",
)

segment_graph_connected, connected_segment_ids = (
    connected_segment_graph(
        structural_segment_ids,
        connector_validation_rows,
    )
)

segment_subassemblies_complete = bool(
    segment_build_gate_passed
)
structural_connectors_complete = bool(
    len(
        connector_validation_df
    )
    == max(
        0,
        len(
            structural_segment_ids
        )
        - 1
    )
    and connector_validation_df.get(
        "valid",
        pd.Series(
            dtype=bool
        ),
    ).astype(
        bool
    ).all()
)
required_count_gate_valid = bool(
    physical_target_count_audit_df.empty
    or physical_target_count_audit_df[
        "gate_valid"
    ].astype(bool).all()
)

declaration_by_id = {
    declaration["attachment_id"]: declaration
    for declaration in attachment_declarations()
}
selected_functional_ids = set(
    selected_functional_df.get(
        "physical_target_id",
        pd.Series(dtype=str),
    ).astype(str)
)
functional_valid_ids = set(
    functional_validation_df.loc[
        functional_validation_df.get(
            "valid",
            pd.Series(dtype=bool),
        ).astype(bool),
        "physical_target_id",
    ].astype(str)
) if not functional_validation_df.empty else set()

required_functional_targets = set()
for target in physical_targets_df.itertuples(index=False):
    declaration = declaration_by_id[target.attachment_id]
    if declaration.get("required", False):
        required_functional_targets.add(
            str(target.physical_target_id)
        )

required_functional_attachments_complete = bool(
    required_count_gate_valid
    and required_functional_targets
    <= functional_valid_ids
)

required_physical_target_ids = sorted(
    required_functional_targets
)

validated_connector_pairs = {
    frozenset(
        {
            int(
                row.segment_a
            ),
            int(
                row.segment_b
            ),
        }
    )
    for row in (
        connector_validation_df.loc[
            connector_validation_df[
                "valid"
            ].astype(
                bool
            )
        ].itertuples(
            index=False
        )
    )
}
unmediated_direct_cross_segment_df = (
    direct_cross_segment_df.loc[
        [
            (
                str(
                    row.contact_status
                )
                != "male_to_female_lock"
            )
            or (
                frozenset(
                    {
                        int(
                            row.segment_a
                        ),
                        int(
                            row.segment_b
                        ),
                    }
                )
                not in validated_connector_pairs
            )
            for row in (
                direct_cross_segment_df.itertuples(
                    index=False
                )
            )
        ]
    ].copy()
    if not direct_cross_segment_df.empty
    else direct_cross_segment_df.copy()
)
safe_export_dataframe(
    unmediated_direct_cross_segment_df,
    OUTPUT_DIR
    / "unmediated_direct_cross_segment_contacts.csv",
)
no_direct_cross_segment_locks = bool(
    unmediated_direct_cross_segment_df.empty
)
collision_free = bool(
    collision_df.empty
)

active_connector_symmetry_audit_df = pd.DataFrame(
    [
        {
            "selection_status": (
                "direct_structural_join_mode"
            ),
            "valid": True,
        }
    ]
)
connector_symmetry_complete = True
functional_symmetry_complete = bool(
    functional_symmetry_audit_df.empty
    or functional_symmetry_audit_df[
        "selection_status"
    ].eq(
        "selected_exact_mirrored_pair"
    ).all()
)
combined_symmetry_complete = bool(
    structural_symmetry_complete
    and connector_symmetry_complete
    and functional_symmetry_complete
)

symmetry_claim_required = bool(
    SYMMETRY_ENABLED
    and SYMMETRY_CONFIG.get(
        "final_claim_requires_symmetry",
        False,
    )
)

reservation_interface_reservation_final_audit_df = reservation_final_reservation_audit(
    segment_results,
    reservation_interface_reservation_requirements_df,
)

# Functional hard reservations are pre-pack receiving-face alternatives.
# Their definitive post-build evidence is the validated functional block, not
# a segment-local structural requirement audit row.  Treat a required target
# as fulfilled when its instantiated wheel/rotation assembly passed the final
# mechanical validation.  This keeps hard reservation gating aligned with the
# the validated build contract and prevents a valid model from being hidden.
if (
    not reservation_interface_reservation_final_audit_df.empty
    and not functional_validation_df.empty
    and "physical_target_id" in functional_validation_df.columns
    and "valid" in functional_validation_df.columns
):
    validated_functional_target_ids = set(
        functional_validation_df.loc[
            functional_validation_df["valid"].astype(bool),
            "physical_target_id",
        ].astype(str)
    )
    functional_fulfilled_mask = (
        reservation_interface_reservation_final_audit_df[
            "reservation_scope"
        ].astype(str).eq("functional_attachment")
        & reservation_interface_reservation_final_audit_df[
            "reservation_owner_id"
        ].astype(str).isin(validated_functional_target_ids)
    )
    reservation_interface_reservation_final_audit_df.loc[
        functional_fulfilled_mask, "satisfied"
    ] = True
    reservation_interface_reservation_final_audit_df.loc[
        functional_fulfilled_mask, "status"
    ] = "fulfilled_by_validated_functional_attachment"
    reservation_interface_reservation_final_audit_df.loc[
        functional_fulfilled_mask, "evaluated_alternative_count"
    ] = 1

safe_export_dataframe(
    reservation_interface_reservation_final_audit_df,
    OUTPUT_DIR / "reservation_interface_reservation_final_audit.csv",
)

reservation_hard_reservations_complete = bool(
    reservation_interface_reservation_final_audit_df.empty
    or reservation_interface_reservation_final_audit_df.loc[
        reservation_interface_reservation_final_audit_df[
            "reservation_strategy"
        ].astype(str).eq("hard")
    ]["satisfied"].astype(bool).all()
)
reservation_soft_reservation_satisfaction_ratio = float(
    reservation_interface_reservation_final_audit_df.loc[
        reservation_interface_reservation_final_audit_df[
            "reservation_strategy"
        ].astype(str).eq("soft")
    ]["satisfied"].astype(bool).mean()
    if (
        not reservation_interface_reservation_final_audit_df.empty
        and reservation_interface_reservation_final_audit_df[
            "reservation_strategy"
        ].astype(str).eq("soft").any()
    )
    else 1.0
)

(
    OUTPUT_DIR / "reservation_interface_reservation_final_summary.json"
).write_text(
    json.dumps(
        {
            "hard_reservations_complete": reservation_hard_reservations_complete,
            "soft_reservation_satisfaction_ratio": reservation_soft_reservation_satisfaction_ratio,
            "reservation_conflicts_complete": reservation_reservation_conflicts_complete,
            "hard_group_count": int(
                reservation_interface_reservation_final_audit_df[
                    "reservation_strategy"
                ].astype(str).eq("hard").sum()
                if not reservation_interface_reservation_final_audit_df.empty
                else 0
            ),
            "unresolved_hard_group_count": int(
                (
                    reservation_interface_reservation_final_audit_df[
                        "reservation_strategy"
                    ].astype(str).eq("hard")
                    & ~reservation_interface_reservation_final_audit_df[
                        "satisfied"
                    ].astype(bool)
                ).sum()
                if not reservation_interface_reservation_final_audit_df.empty
                else 0
            ),
        },
        indent=2,
    ),
    encoding="utf-8",
)

if (
    VISUALIZATION_CONFIG.get("enabled", True)
    and VISUALIZATION_CONFIG.get("interactive", True)
    and VISUALIZATION_CONFIG.get("generate_reservation_reservation_fulfillment_view", True)
):
    write_interactive(
        reservation_reservation_fulfillment_figure(
            segment_grid_planner,
            reservation_interface_reservation_requirements_df,
            reservation_interface_reservation_final_audit_df,
        ),
        VISUALIZATION_DIR / "reservation_interface_reservation_fulfillment.html",
        "reservation_interface_reservation_fulfillment",
        "Post-pack hard and soft reservation fulfillment",
        bool(
            VISUALIZATION_CONFIG.get(
                "show_inline_reservation_reservation_fulfillment_view",
                False,
            )
        ),
    )

final_claim_valid = bool(
    reservation_hard_requirement_generation_complete
    and reservation_hard_reservations_complete
    and reservation_reservation_conflicts_complete
    and segment_subassemblies_complete
    and structural_connectors_complete
    and segment_graph_connected
    and no_direct_cross_segment_locks
    and collision_free
    and required_functional_attachments_complete
    and connector_receiving_faces_complete
    and semantic_preflight_gate_valid
    and structuralization_gate_valid
    and (
        combined_symmetry_complete
        or not symmetry_claim_required
    )
)

if final_claim_valid:
    final_status = "valid_complete_segment_connector_build"
elif not reservation_hard_requirement_generation_complete:
    final_status = "hard_interface_reservation_generation_incomplete"
elif not reservation_reservation_conflicts_complete:
    final_status = "fatal_interface_reservation_conflict"
elif not reservation_hard_reservations_complete:
    final_status = "hard_interface_reservations_incomplete"
elif not segment_subassemblies_complete:
    final_status = "segment_subassemblies_incomplete"
elif not structural_connectors_complete:
    final_status = "structural_segment_connectors_incomplete"
elif not segment_graph_connected:
    final_status = "segment_assembly_graph_disconnected"
elif not no_direct_cross_segment_locks:
    final_status = (
        "unmediated_cross_segment_contact_detected"
    )
elif not collision_free:
    final_status = "final_block_collision_detected"
elif not connector_receiving_faces_complete:
    final_status = "connector_receiving_faces_incomplete"
elif not structuralization_gate_valid:
    final_status = "segment_structuralization_incomplete"
elif not semantic_preflight_gate_valid:
    final_status = "functional_semantic_preflight_failed"
elif symmetry_claim_required and not combined_symmetry_complete:
    final_status = "symmetry_enforcement_incomplete"
else:
    final_status = "required_functional_attachments_incomplete"

# ------------------------------------------------------------
# 7. Build instructions and final outputs
# ------------------------------------------------------------

assembly_adjacency = defaultdict(
    list
)
for row in connector_validation_df.loc[
    connector_validation_df[
        "valid"
    ].astype(
        bool
    )
].itertuples(
    index=False
):
    assembly_adjacency[
        int(
            row.segment_a
        )
    ].append(
        (
            int(
                row.segment_b
            ),
            row.interface_id,
        )
    )
    assembly_adjacency[
        int(
            row.segment_b
        )
    ].append(
        (
            int(
                row.segment_a
            ),
            row.interface_id,
        )
    )

assembly_steps = [{
    "assembly_step": 1,
    "action": "start_with_segment_subassembly",
    "anchor_segment_id": None,
    "attached_segment_id": int(root_segment_id),
    "interface_id": None,
}]
visited = {int(root_segment_id)}
queue = deque([int(root_segment_id)])
while queue:
    anchor = queue.popleft()
    for attached, interface_id in sorted(
        assembly_adjacency[anchor]
    ):
        if attached in visited:
            continue
        visited.add(attached)
        queue.append(attached)
        assembly_steps.append({
            "assembly_step": len(assembly_steps) + 1,
            "action": "attach_segment_by_direct_structural_lock",
            "anchor_segment_id": anchor,
            "attached_segment_id": attached,
            "interface_id": interface_id,
        })

assembly_steps_df = pd.DataFrame(assembly_steps)
assembly_steps_df.to_csv(
    OUTPUT_DIR / "segment_connector_assembly_steps.csv",
    index=False,
)

assembly_oriented_assembly_steps_df = build_assembly_oriented_assembly_steps(
    root_segment_id,
    required_interfaces_df,
    connector_rule_audit_df,
    selected_connectors_df,
    connector_validation_df,
    structural_segment_ids,
)
assembly_oriented_assembly_steps_df.to_csv(
    OUTPUT_DIR / "assembly_oriented_assembly_steps.csv",
    index=False,
)

final_block_rows = []
for block in all_final_blocks:
    final_block_rows.append({
        "block_id": int(block.block_id),
        "block_role": getattr(
            block,
            "block_role",
            block.category,
        ),
        "block_family": block.block_family,
        "position": tuple(int(value) for value in block.position),
        "size": tuple(int(value) for value in block.size),
        "rotation": int(getattr(block, "rotation", 0)),
        "source_segment_id": getattr(
            block,
            "source_segment_id",
            None,
        ),
        "interface_id": getattr(
            block,
            "interface_id",
            None,
        ),
        "physical_target_id": getattr(
            block,
            "physical_target_id",
            None,
        ),
    })
final_blocks_df = pd.DataFrame(
    final_block_rows
)
safe_export_dataframe(
    final_blocks_df,
    OUTPUT_DIR
    / "segment_connector_functional_final_blocks.csv",
)

display_block_family_counts_df = (
    block_family_count_dataframe(
        all_final_blocks
    )
)
display_block_family_count_summary = (
    ", ".join(
        f"{row.block_family}: {int(row.count)}"
        for row in display_block_family_counts_df.itertuples(index=False)
    )
    if not display_block_family_counts_df.empty
    else "No blocks displayed"
)
print(
    "Displayed block counts: "
    + display_block_family_count_summary
)
safe_export_dataframe(
    display_block_family_counts_df,
    OUTPUT_DIR
    / "display_block_family_counts.csv",
)
(
    OUTPUT_DIR
    / "display_block_family_counts.json"
).write_text(
    json.dumps(
        display_block_family_counts_df.to_dict(
            orient="records"
        ),
        indent=2,
    ),
    encoding="utf-8",
)

build_component_counts = {
    "structural_segment_count": len(
        structural_segment_ids
    ),
    "segment_result_count": len(
        segment_results
    ),
    "valid_segment_result_count": sum(
        bool(result.get("valid", False))
        for result in segment_results
    ),
    "segment_structural_block_count": len(
        segment_blocks
    ),
    "selected_connector_block_count": len(
        connector_blocks
    ),
    "selected_functional_block_count": len(
        functional_blocks
    ),
    "connector_rule_count": len(
        TASK_CONTEXT.get(
            "connector_rules",
            [],
        )
    ),
    "segment_subassemblies_complete": (
        segment_subassemblies_complete
    ),
    "structural_connectors_complete": (
        structural_connectors_complete
    ),
    "final_claim_valid": final_claim_valid,
    "final_status": final_status,
}
(OUTPUT_DIR / "build_visualization_status.json").write_text(
    json.dumps(
        build_component_counts,
        indent=2,
    ),
    encoding="utf-8",
)

failed_segment_rows = [
    {
        "segment_id": result.get(
            "segment_id"
        ),
        "segment_label": result.get(
            "segment_label"
        ),
        "planning_mode": result.get(
            "planning_mode"
        ),
        "valid": result.get(
            "valid",
            False,
        ),
        "exact_coverage": result.get(
            "exact_coverage",
            False,
        ),
        "error": result.get("error"),
        "missing_voxels": result.get(
            "missing_voxels"
        ),
        "connector_face_requirements_valid": (
            result.get(
                "connector_face_requirements_valid"
            )
        ),
    }
    for result in segment_results
    if not result.get("valid", False)
]
segment_build_failure_diagnostics_df = pd.DataFrame(
    failed_segment_rows
)
segment_build_failure_diagnostics_df.to_csv(
    OUTPUT_DIR
    / "segment_build_failure_diagnostics.csv",
    index=False,
)

structural_display_ready = bool(
    segment_blocks
    and segment_subassemblies_complete
)

(
    subassembly_appearance,
    subassembly_step_labels,
    subassembly_build_steps_df,
) = build_subassembly_timeline(
    segment_results
)
subassembly_build_steps_df.to_csv(
    OUTPUT_DIR / "subassembly_build_steps.csv",
    index=False,
)

proper_build_step_visualization_manifest_df = pd.DataFrame(
    proper_build_step_visualization_rows
)
safe_export_dataframe(
    proper_build_step_visualization_manifest_df,
    OUTPUT_DIR
    / "proper_build_step_visualization_manifest.csv",
)

step_progression_visual_audit_rows = []
for result in segment_results:
    planning_result = result.get(
        "planning_result",
        {},
    )
    validation = result.get(
        "validation",
        {},
    )
    planning_ids = {
        int(
            block.block_id
        )
        for block in planning_result.get(
            "blocks",
            [],
        )
    }
    validation_ids = {
        int(
            row.get(
                "block_id"
            )
        )
        for row in validation.get(
            "block_rows",
            [],
        )
    }
    steps = planning_result.get(
        "instruction_steps",
        [],
    )
    for step_index, step in enumerate(
        steps
    ):
        current_ids = {
            int(
                block.block_id
            )
            for block in step.get(
                "blocks",
                [],
            )
        }
        previous_ids = set(
            validation.get(
                "accepted_before_by_step",
                {},
            ).get(
                step_index,
                [],
            )
        )
        step_progression_visual_audit_rows.append(
            {
                "segment_id": int(
                    result[
                        "segment_id"
                    ]
                ),
                "segment_name": str(
                    result.get(
                        "segment_name",
                        "",
                    )
                ),
                "step": int(
                    step_index
                    + 1
                ),
                "row": step.get(
                    "row"
                ),
                "build_axis": str(
                    result.get(
                        "selected_build_axis",
                        "+Y",
                    )
                ),
                "previous_block_count": int(
                    len(
                        previous_ids
                    )
                ),
                "current_block_count": int(
                    len(
                        current_ids
                    )
                ),
                "previous_color_mode": (
                    "lightened_family"
                ),
                "previous_alpha": float(
                    VISUALIZATION_CONFIG.get(
                        "step_progression_previous_alpha",
                        0.28,
                    )
                ),
                "current_alpha": float(
                    VISUALIZATION_CONFIG.get(
                        "step_progression_current_alpha",
                        1.0,
                    )
                ),
                "validation_ids_match_planning_ids": bool(
                    validation_ids
                    == planning_ids
                ),
                "previous_ids_exist_in_plan": bool(
                    previous_ids
                    <= planning_ids
                ),
                "current_ids_exist_in_plan": bool(
                    current_ids
                    <= planning_ids
                ),
            }
        )

step_progression_visual_audit_df = pd.DataFrame(
    step_progression_visual_audit_rows
)
safe_export_dataframe(
    step_progression_visual_audit_df,
    OUTPUT_DIR
    / "validated_step_progression_visual_audit.csv",
)

valid_connector_interface_ids_for_display = set(
    connector_validation_df.loc[
        connector_validation_df.get(
            "valid",
            pd.Series(dtype=bool),
        ).astype(bool),
        "interface_id",
    ].astype(str)
) if not connector_validation_df.empty else set()

valid_functional_target_ids_for_display = set(
    str(value)
    for value in functional_valid_ids
)

(
    timeline_blocks,
    complete_build_appearance,
    complete_build_step_labels,
    complete_build_steps_df,
) = build_complete_timeline(
    segment_results,
    segment_blocks,
    connector_blocks,
    functional_blocks,
    structural_display_ready,
    valid_connector_interface_ids=(
        valid_connector_interface_ids_for_display
    ),
    valid_functional_target_ids=(
        valid_functional_target_ids_for_display
    ),
)
complete_build_steps_df.to_csv(
    OUTPUT_DIR / "complete_build_steps.csv",
    index=False,
)

proper_complete_build_steps_figure = None
if (
    VISUALIZATION_CONFIG.get(
        "enabled",
        True,
    )
    and VISUALIZATION_CONFIG.get(
        "interactive",
        True,
    )
    and VISUALIZATION_CONFIG.get(
        "generate_proper_complete_build_step_player",
        True,
    )
    and timeline_blocks
    and (
        final_claim_valid
        or not VISUALIZATION_CONFIG.get(
            "suppress_full_model_player_when_final_claim_invalid",
            True,
        )
    )
):
    proper_complete_build_steps_figure = (
        proper_build_step_figure(
            timeline_blocks,
            complete_build_appearance,
            complete_build_step_labels,
            (
                "Complete Validated Build Steps"
                if final_claim_valid
                else (
                    "Available Validated Build Steps — "
                    "Incomplete"
                )
            ),
            source_grid=(
                segment_grid_planner
            ),
        )
    )
    write_interactive(
        proper_complete_build_steps_figure,
        VISUALIZATION_DIR
        / "proper_complete_build_steps.html",
        "proper_complete_build_steps",
        (
            "Complete build-step player with lightened, translucent "
            "family-colored prior blocks and catalog-colored new blocks"
        ),
        False,
    )

(
    assembly_display_blocks,
    assembly_appearance,
    assembly_step_labels,
    assembly_visual_steps_df,
) = build_assembly_timeline(
    assembly_steps,
    segment_blocks_by_id,
    connector_blocks,
    functional_blocks,
    connector_validation_df,
    structural_display_ready,
)
assembly_visual_steps_df.to_csv(
    OUTPUT_DIR / "assembly_visual_steps.csv",
    index=False,
)

incomplete_message = None
if not structural_display_ready:
    incomplete_message = (
        "INCOMPLETE BUILD — structural segment "
        "subassemblies did not complete. "
        f"Structural blocks: {len(segment_blocks)}; "
        f"functional candidates selected: "
        f"{len(functional_blocks)}. "
        "The terminal viewer shows only currently validated "
        "blocks and is labeled as an incomplete diagnostic. Review "
        "segment_build_failure_diagnostics.csv."
    )
    pipeline_log(
        "show_gate_messages",
        "[BUILD DISPLAY GATE]",
        incomplete_message,
    )

if VISUALIZATION_CONFIG.get("enabled", True):
    static_display_blocks = (
        all_final_blocks
        if structural_display_ready
        else list(segment_blocks)
    )

    if (
        VISUALIZATION_CONFIG.get(
            "save_static_final_png",
            True,
        )
        and static_display_blocks
    ):
        visualize_blocks_static(
            static_display_blocks,
            grid_size=max(
                segment_grid_planner.shape
            ),
            title=(
                "Final Integrated Catalog-Colored Build"
                if final_claim_valid
                else (
                    "Incomplete Structural Build "
                    "Diagnostic"
                )
            ),
            output_path=(
                VISUALIZATION_DIR
                / (
                    "final_build_full_color.png"
                    if final_claim_valid
                    else (
                        "incomplete_structural_build_"
                        "diagnostic.png"
                    )
                )
            ),
            show_inline=False,
        )

    generate_noninline_viewers = bool(
        VISUALIZATION_CONFIG.get(
            "generate_noninline_interactive_viewers",
            False,
        )
        or VISUALIZATION_CONFIG.get(
            "save_interactive_html",
            False,
        )
    )

    if (
        VISUALIZATION_CONFIG.get(
            "interactive",
            True,
        )
        and generate_noninline_viewers
    ):
        # Optional generic viewers. The default inline profile uses
        # the Reference validated steps and Assembly assembly player instead.
        subassembly_figure = detailed_sequence_figure(
            segment_blocks,
            subassembly_appearance,
            subassembly_step_labels,
            "Segment Subassembly Build Steps",
            source_grid=segment_grid_planner,
            incomplete_message=(
                incomplete_message
                if not segment_blocks
                else None
            ),
        )
        write_interactive(
            subassembly_figure,
            VISUALIZATION_DIR
            / "subassembly_build_steps_interactive.html",
            "subassembly_build_steps",
            (
                "Detailed row-by-row build steps across "
                "all segment subassemblies"
            ),
            bool(
                VISUALIZATION_CONFIG.get(
                    "show_inline_subassembly_build_steps",
                    True,
                )
            ),
        )

        # Main interactive file is now a real cumulative
        # build sequence, not a static final-state viewer.
        final_timeline_figure = (
            detailed_sequence_figure(
                timeline_blocks,
                complete_build_appearance,
                complete_build_step_labels,
                (
                    "Complete Build Timeline"
                    if structural_display_ready
                    else (
                        "Incomplete Build Diagnostic "
                        "Timeline"
                    )
                ),
                source_grid=segment_grid_planner,
                incomplete_message=(
                    incomplete_message
                    if not structural_display_ready
                    else None
                ),
            )
        )
        write_interactive(
            final_timeline_figure,
            VISUALIZATION_DIR
            / "final_build_interactive.html",
            "complete_build_timeline",
            (
                "Cumulative structural build steps, "
                "then connectors and functional attachments"
            ),
            bool(
                VISUALIZATION_CONFIG.get(
                    "show_inline_final",
                    True,
                )
            ),
        )

        assembly_figure = detailed_sequence_figure(
            assembly_display_blocks,
            assembly_appearance,
            assembly_step_labels,
            "Segment Assembly Steps",
            source_grid=segment_grid_planner,
            incomplete_message=(
                (
                    incomplete_message
                    if not structural_display_ready
                    else None
                )
            ),
        )
        write_interactive(
            assembly_figure,
            VISUALIZATION_DIR
            / "assembly_sequence_interactive.html",
            "assembly_sequence",
            (
                "Connector-first segment-subassembly "
                "assembly steps"
            ),
            bool(
                VISUALIZATION_CONFIG.get(
                    "show_inline_assembly_steps",
                    True,
                )
            ),
        )



# ------------------------------------------------------------
# Restored reference visualization suite
# ------------------------------------------------------------

# Headless and incomplete runs still execute downstream audits. Define every
# display list before the optional visualization branch.
valid_connector_display_blocks = []
valid_functional_display_blocks = []
valid_wheel_display_blocks = []
reference_display_blocks = []
reference_neighbor_map = {}

if VISUALIZATION_CONFIG.get(
    "enabled",
    True,
):
    reference_grid_size = int(
        max(segment_grid_planner.shape)
    )
    valid_connector_interface_ids = set(
        connector_validation_df.loc[
            connector_validation_df.get(
                "valid",
                pd.Series(dtype=bool),
            ).astype(bool),
            "interface_id",
        ].astype(str)
    ) if not connector_validation_df.empty else set()

    valid_connector_display_blocks = [
        block
        for block in connector_blocks
        if str(
            getattr(
                block,
                "interface_id",
                "",
            )
        ) in valid_connector_interface_ids
    ]

    valid_functional_display_blocks = [
        block
        for block in functional_blocks
        if str(
            getattr(
                block,
                "physical_target_id",
                "",
            )
        ) in functional_valid_ids
    ]

    reference_display_blocks = list(
        segment_blocks
    )

    if VISUALIZATION_CONFIG.get(
        "show_valid_connector_blocks_when_final_incomplete",
        True,
    ):
        reference_display_blocks.extend(
            valid_connector_display_blocks
        )

    if VISUALIZATION_CONFIG.get(
        "show_valid_functional_blocks_when_final_incomplete",
        True,
    ):
        reference_display_blocks.extend(
            valid_functional_display_blocks
        )

    if (
        reference_display_blocks
        and VISUALIZATION_CONFIG.get(
            "save_static_terminal_state_png",
            True,
        )
    ):
        visualize_blocks_static(
            reference_display_blocks,
            grid_size=reference_grid_size,
            title=(
                "Final Validated Build State"
                if final_claim_valid
                else (
                    "Available Validated State — "
                    "Build Incomplete"
                )
            ),
            output_path=(
                VISUALIZATION_DIR
                / (
                    "final_validated_state.png"
                    if final_claim_valid
                    else (
                        "available_validated_state_"
                        "incomplete.png"
                    )
                )
            ),
            show_inline=False,
        )

    if reference_display_blocks:
        reference_neighbor_map = (
            build_neighbor_map(
                reference_display_blocks,
                reference_grid_size,
            )
        )

        if VISUALIZATION_CONFIG.get(
            "show_reference_solid_block_overview",
            True,
        ):
            reference_solid_block_overview(
                reference_display_blocks,
                reference_grid_size,
                title=(
                    "Current Validated Block State"
                ),
            )

        if VISUALIZATION_CONFIG.get(
            "show_reference_face_diagnostic",
            True,
        ):
            reference_face_diagnostic(
                reference_display_blocks,
                reference_neighbor_map,
                reference_grid_size,
                title=(
                    "Male/Female Faces and "
                    "Structural Contacts"
                ),
            )

        if (
            VISUALIZATION_CONFIG.get(
                "interactive",
                True,
            )
            and VISUALIZATION_CONFIG.get(
                (
                    "generate_interactive_"
                    "face_contact_figure"
                ),
                True,
            )
        ):
            interactive_face_contact_fig = (
                interactive_face_contact_figure(
                    reference_display_blocks,
                    reference_neighbor_map,
                    reference_grid_size,
                    title=(
                        "Interactive Male/Female "
                        "Faces and Structural Contacts"
                    ),
                )
            )
            write_interactive(
                interactive_face_contact_fig,
                VISUALIZATION_DIR
                / (
                    "interactive_face_contact_"
                    "diagnostic.html"
                ),
                "interactive_face_contact",
                (
                    "Rotatable male/female face "
                    "and structural-contact diagnostic"
                ),
                False,
            )

        if VISUALIZATION_CONFIG.get(
            "show_reference_validated_steps",
            True,
        ):
            maximum_steps = (
                VISUALIZATION_CONFIG.get(
                    "reference_step_maximum_inline_steps"
                )
            )
            rendered_step_count = 0

            for result in segment_results:
                if (
                    "planning_result" not in result
                    or "validation" not in result
                ):
                    continue

                local_steps = result[
                    "planning_result"
                ]["instruction_steps"]

                for step_index in range(
                    len(local_steps)
                ):
                    if (
                        maximum_steps is not None
                        and rendered_step_count
                        >= int(maximum_steps)
                    ):
                        break

                    reference_validated_step_view(
                        result,
                        step_index,
                        reference_grid_size,
                    )
                    rendered_step_count += 1

                if (
                    maximum_steps is not None
                    and rendered_step_count
                    >= int(maximum_steps)
                ):
                    break

    if log_enabled(
        "show_assembly_step_table"
    ):
        print(
            "Assembly-oriented segment assembly steps:"
        )
        emit_diagnostic(
            assembly_oriented_assembly_steps_df
        )

    if (
        VISUALIZATION_CONFIG.get(
            "interactive",
            True,
        )
        and (
            VISUALIZATION_CONFIG.get(
                "generate_assembly_player_figure",
                True,
            )
            or VISUALIZATION_CONFIG.get(
                "show_inline_assembly_assembly_player",
                False,
            )
            or VISUALIZATION_CONFIG.get(
                "show_dedicated_inline_player_cell",
                True,
            )
        )
    ):
        (
            assembly_player_figure,
            assembly_assembly_player_step_audit_df,
        ) = assembly_visible_assembly_player(
            assembly_oriented_assembly_steps_df,
            segment_blocks_by_id,
            valid_connector_display_blocks,
            structural_interface_payload,
            title=(
                "Assembly Connector-Mediated "
                "Assembly Player"
            ),
        )
        safe_export_dataframe(
            assembly_assembly_player_step_audit_df,
            OUTPUT_DIR
            / "assembly_assembly_player_step_audit.csv",
        )
        write_interactive(
            assembly_player_figure,
            VISUALIZATION_DIR
            / "assembly_assembly_player.html",
            "assembly_assembly_player",
            (
                "Assembly-oriented connector-mediated "
                "assembly steps with visible root and "
                "pending-segment previews"
            ),
            False,
        )

    if (
        VISUALIZATION_CONFIG.get(
            "interactive",
            True,
        )
        and (
            VISUALIZATION_CONFIG.get(
                "generate_complete_build_timeline_figure",
                True,
            )
            or VISUALIZATION_CONFIG.get(
                "show_dedicated_inline_complete_build_timeline_cell",
                True,
            )
        )
        and timeline_blocks
    ):
        inline_complete_build_timeline_figure = (
            detailed_sequence_figure(
                timeline_blocks,
                complete_build_appearance,
                complete_build_step_labels,
                (
                    "Complete Build Timeline"
                    if final_claim_valid
                    else (
                        "Available Build Timeline — "
                        "incomplete diagnostic"
                    )
                ),
                source_grid=segment_grid_planner,
                incomplete_message=(
                    incomplete_message
                    if not final_claim_valid
                    else None
                ),
            )
        )
        write_interactive(
            inline_complete_build_timeline_figure,
            VISUALIZATION_DIR
            / "complete_build_timeline_interactive.html",
            "inline_complete_build_timeline",
            (
                "Complete build timeline with a terminal "
                "validated-state step"
            ),
            False,
        )

    if (
        VISUALIZATION_CONFIG.get(
            "interactive",
            True,
        )
        and (
            VISUALIZATION_CONFIG.get(
                "generate_final_state_figure",
                True,
            )
            or VISUALIZATION_CONFIG.get(
                "show_inline_final_state",
                False,
            )
            or VISUALIZATION_CONFIG.get(
                "show_dedicated_inline_final_state_cell",
                True,
            )
        )
        and reference_display_blocks
    ):
        inline_final_state_figure = interactive_build_figure(
            reference_display_blocks,
            (
                "Interactive Final Build State"
                if final_claim_valid
                else (
                    "Available Validated State — build incomplete"
                )
            ),
            include_faces=True,
        )
        write_interactive(
            inline_final_state_figure,
            VISUALIZATION_DIR / "final_state_interactive.html",
            "inline_final_state",
            "Interactive final build state",
            False,
        )

structural_family_counts = (
    segment_subassembly_blocks_df[
        "block_family"
    ].value_counts().to_dict()
    if not segment_subassembly_blocks_df.empty
    else {}
)
structural_family_voxel_coverage = {}
for family, count in structural_family_counts.items():
    record = STRUCTURAL_CATALOG_BY_FAMILY[
        str(family)
    ]
    structural_family_voxel_coverage[
        str(family)
    ] = int(
        count
        * np.prod(
            record[
                "column_world_size"
            ]
        )
    )

block_family_usage_audit = {
    "family_counts": {
        str(key): int(value)
        for key, value in (
            structural_family_counts.items()
        )
    },
    "family_voxel_coverage": (
        structural_family_voxel_coverage
    ),
    "default_priority_by_family": {
        record["block_family"]: float(
            record[
                "default_packing_priority"
            ]
        )
        for record in STRUCTURAL_CATALOG_RECORDS
    },
    "effective_priority_by_family": {
        record["block_family"]: float(
            record[
                "effective_packing_priority"
            ]
        )
        for record in STRUCTURAL_CATALOG_RECORDS
    },
    "task_priority_overrides": (
        TASK_CONTEXT_PACKING_PRIORITY_OVERRIDES
    ),
    "planner_primary_sort": (
        "minimum block count; priority only breaks "
        "equal-block-count sequence ties"
    ),
    "interpretation": (
        "Blue 2x2x2 blocks dominate when structuralized "
        "columns are height 2 or contain height-2 remainders. "
        "Equal priorities do not create a blue preference."
    ),
}
(
    OUTPUT_DIR
    / "block_family_usage_audit.json"
).write_text(
    json.dumps(
        block_family_usage_audit,
        indent=2,
    ),
    encoding="utf-8",
)

wheel_preflight_rows = (
    semantic_functional_preflight_audit_df.loc[
        semantic_functional_preflight_audit_df[
            "attachment_id"
        ].astype(str)
        == PRIMARY_WHEEL_ATTACHMENT_ID
    ].to_dict(
        orient="records"
    )
    if not (
        semantic_functional_preflight_audit_df.empty
    )
    else []
)

valid_wheel_display_blocks = [
    block
    for block in valid_functional_display_blocks
    if (
        "wheel"
        in str(
            getattr(
                block,
                "block_family",
                "",
            )
        ).lower()
        or str(
            (
                getattr(
                    block,
                    "catalog_record",
                    {},
                )
                or {}
            ).get(
                "functional_role",
                "",
            )
        ).lower()
        == "wheel"
    )
]

wheel_visualization_audit = {
    "wheel_attachment_declared": bool(
        any(
            declaration.get(
                "attachment_id"
            )
            == PRIMARY_WHEEL_ATTACHMENT_ID
            for declaration in attachment_declarations()
        )
    ),
    "semantic_preflight_rows": (
        wheel_preflight_rows
    ),
    "physical_target_count": int(
        len(
            physical_targets_df.loc[
                physical_targets_df.get(
                    "attachment_id",
                    pd.Series(dtype=str),
                ).astype(str)
                == PRIMARY_WHEEL_ATTACHMENT_ID
            ]
        )
    ) if not physical_targets_df.empty else 0,
    "candidate_count": int(
        len(
            functional_candidates_df.loc[
                functional_candidates_df.get(
                    "attachment_id",
                    pd.Series(dtype=str),
                ).astype(str)
                == PRIMARY_WHEEL_ATTACHMENT_ID
            ]
        )
    ) if not functional_candidates_df.empty else 0,
    "selected_valid_wheel_block_count": int(
        len(
            valid_wheel_display_blocks
        )
    ),
    "selected_valid_wheel_block_ids": [
        int(
            block.block_id
        )
        for block in valid_wheel_display_blocks
    ],
    "visible_in_reference_and_interactive_state": bool(
        valid_wheel_display_blocks
    ),
    "orientation_contract": {
        "axle_axis": "X",
        "disc_plane": "YZ",
        "vertical_axis": "Z",
    },
    "interpretation": (
        "Validated wheel count is filtered by wheel family/role; "
        "motion connectors and structural subassembly members are excluded."
    ),
}
(
    OUTPUT_DIR
    / "wheel_visualization_audit.json"
).write_text(
    json.dumps(
        wheel_visualization_audit,
        indent=2,
        default=str,
    ),
    encoding="utf-8",
)

wheel_required_family = required_family_for_attachment(PRIMARY_WHEEL_ATTACHMENT_ID)

selected_wheel_family_audit_df = pd.DataFrame(
    [
        {
            "physical_target_id": str(
                getattr(
                    block,
                    "physical_target_id",
                    "",
                )
            ),
            "block_id": int(
                block.block_id
            ),
            "block_family": str(
                block.block_family
            ),
            "origin": tuple(
                int(
                    value
                )
                for value in block.position
            ),
            "size": tuple(
                int(
                    value
                )
                for value in block.size
            ),
            "required_family": wheel_required_family or "catalog_role:wheel",
            "family_requirement_satisfied": bool(
                not wheel_required_family
                or str(block.block_family) == wheel_required_family
            ),
        }
        for block in valid_wheel_display_blocks
    ]
)
safe_export_dataframe(
    selected_wheel_family_audit_df,
    OUTPUT_DIR
    / "selected_wheel_family_audit.csv",
)

contact_view_bounds_audit = {
    "minimum_block_origin": (
        np.min(
            np.asarray(
                [
                    block.position
                    for block in reference_display_blocks
                ],
                dtype=float,
            ),
            axis=0,
        ).tolist()
        if reference_display_blocks
        else []
    ),
    "maximum_block_extent": (
        np.max(
            np.asarray(
                [
                    np.asarray(
                        block.position,
                        dtype=float,
                    )
                    + np.asarray(
                        block.size,
                        dtype=float,
                    )
                    for block in reference_display_blocks
                ],
                dtype=float,
            ),
            axis=0,
        ).tolist()
        if reference_display_blocks
        else []
    ),
    "rotation_block_ids": [
        int(
            block.block_id
        )
        for block in reference_display_blocks
        if str(
            block.block_family
        )
        == "rotation_block"
    ],
    "dynamic_bounds_enabled": True,
    "contact_classification": (
        "mechanical_face_status"
    ),
}
(
    OUTPUT_DIR
    / "interactive_contact_view_bounds_audit.json"
).write_text(
    json.dumps(
        contact_view_bounds_audit,
        indent=2,
    ),
    encoding="utf-8",
)

if log_enabled(
    "show_debug_settings"
):
    print(
        "Structural block-family use:",
        block_family_usage_audit[
            "family_counts"
        ],
    )
    print(
        "Wheel visualization status:",
        {
            "physical_targets": (
                wheel_visualization_audit[
                    "physical_target_count"
                ]
            ),
            "candidates": (
                wheel_visualization_audit[
                    "candidate_count"
                ]
            ),
            "visible_valid_wheels": (
                wheel_visualization_audit[
                    "selected_valid_wheel_block_count"
                ]
            ),
        },
    )
inline_visualization_plan = {
    "reference_segment_panel": bool(
        VISUALIZATION_CONFIG.get(
            "show_reference_segment_panel",
            True,
        )
    ),
    "reference_solid_block_overview": bool(
        VISUALIZATION_CONFIG.get(
            "show_reference_solid_block_overview",
            True,
        )
    ),
    "reference_face_diagnostic": bool(
        VISUALIZATION_CONFIG.get(
            "show_reference_face_diagnostic",
            True,
        )
    ),
    "reference_validated_steps": bool(
        VISUALIZATION_CONFIG.get(
            "show_reference_validated_steps",
            True,
        )
    ),
    "segmentation_comparison": bool(
        VISUALIZATION_CONFIG.get(
            "show_inline_segmentation_comparison",
            True,
        )
    ),
    "reference_block_type_view": bool(
        VISUALIZATION_CONFIG.get(
            "show_inline_reference_block_type_view",
            False,
        )
    ),
    "reference_face_connection_view": bool(
        VISUALIZATION_CONFIG.get(
            "show_inline_reference_face_connection_view",
            True,
        )
    ),
    "reference_validated_steps": bool(
        VISUALIZATION_CONFIG.get(
            "show_inline_reference_validated_steps",
            True,
        )
    ),
    "reference_final_object": bool(
        VISUALIZATION_CONFIG.get(
            "show_inline_reference_final_object",
            False,
        )
    ),
    "assembly_assembly_player": bool(
        VISUALIZATION_CONFIG.get(
            "show_inline_assembly_assembly_player",
            True,
        )
    ),
    "interactive_final_state": bool(
        VISUALIZATION_CONFIG.get(
            "show_inline_final_state",
            True,
        )
    ),
    "generic_subassembly_timeline": bool(
        VISUALIZATION_CONFIG.get(
            "show_inline_subassembly_build_steps",
            False,
        )
    ),
    "generic_complete_build_timeline": bool(
        VISUALIZATION_CONFIG.get(
            "show_inline_final",
            False,
        )
    ),
    "generic_assembly_sequence": bool(
        VISUALIZATION_CONFIG.get(
            "show_inline_assembly_steps",
            False,
        )
    ),
}
(
    OUTPUT_DIR
    / "inline_visualization_plan.json"
).write_text(
    json.dumps(
        inline_visualization_plan,
        indent=2,
    ),
    encoding="utf-8",
)

final_summary = {
    "task_id": TASK_CONTEXT.get("task_id"),
    "source_model": str(SOURCE_MODEL_PATH),
    "catalog_xlsx": str(CATALOG_XLSX_PATH),
    "root_segment_id": int(root_segment_id),
    "structural_segment_count": len(structural_segment_ids),
    "required_structural_interface_count": len(required_interface_ids),
    "structural_join_mode": STRUCTURAL_JOIN_MODE,
    "selected_structural_connector_count": int(
        len(selected_connectors_df)
        if STRUCTURAL_JOIN_MODE != "direct_structural_lock"
        else 0
    ),
    "special_connector_block_count": int(
        len(
            connector_blocks
        )
    ),
    "direct_structural_join_count": int(
        len(
            connector_validation_df
        )
    ),
    "valid_structural_connector_count": int(
        connector_validation_df.get(
            "valid",
            pd.Series(dtype=bool),
        ).sum()
    ),
    "segment_structural_block_count": len(segment_blocks),
    "functional_attachment_block_count": len(functional_blocks),
    "validated_wheel_block_count": int(
        len(
            valid_wheel_display_blocks
        )
    ),
    "validated_wheel_families": sorted(
        {
            str(
                block.block_family
            )
            for block in valid_wheel_display_blocks
        }
    ),
    "wheel_required_family": wheel_required_family or None,
    "wheel_family_requirement_satisfied": bool(
        not wheel_required_family
        or all(
            str(block.block_family) == wheel_required_family
            for block in valid_wheel_display_blocks
        )
    ),
    "wheel_exact_family_requirement_satisfied": bool(
        wheel_required_family == "big_wheel"
        and len(valid_wheel_display_blocks) == 2
        and all(str(block.block_family) == "big_wheel" for block in valid_wheel_display_blocks)
    ),
    "validated_functional_target_count": int(
        functional_validation_df.get(
            "valid",
            pd.Series(dtype=bool),
        ).astype(bool).sum()
    ),
    "motion_subassembly_connector_count": int(
        len(custom_subassembly_instances)
    ),
    "functional_subassembly_structural_block_count": int(
        sum(
            len(instance["member_blocks"])
            for instance in custom_subassembly_instances
        )
    ),
    "custom_functional_subassembly_source_segment_ids": sorted({
        int(segment_id)
        for instance in custom_subassembly_instances
        for segment_id in instance["config"].get("source_segment_ids", [])
    }),
    "custom_functional_subassembly_count": int(
        len(custom_subassembly_instances)
    ),
    "final_block_count": len(all_final_blocks),
    "structural_display_ready": structural_display_ready,
    "subassembly_build_step_count": int(
        len(subassembly_build_steps_df)
    ),
    "complete_build_step_count": int(
        len(complete_build_steps_df)
    ),
    "assembly_visual_step_count": int(
        assembly_visual_steps_df.get(
            "assembly_visual_step",
            pd.Series(dtype=float),
        ).notna().sum()
    ),
    "segment_build_failure_count": int(
        len(
            segment_build_failure_diagnostics_df
        )
    ),
    "semantic_preflight_gate_valid": (
        semantic_preflight_gate_valid
    ),
    "semantic_preflight_quarantined_segment_ids": (
        semantic_preflight_quarantined_segment_ids
    ),
    "structuralization_gate_valid": (
        structuralization_gate_valid
    ),
    "structuralization_selected_lattice_offset": [
        structuralization_lattice_transform["offset_x"],
        structuralization_lattice_transform["offset_y"],
    ],
    "structural_symmetry_exactification_count": int(
        structural_symmetry_exactification_audit_df.get(
            "status",
            pd.Series(dtype=str),
        ).eq("exactified").sum()
    ),
    "structuralization_active_segment_count": len(
        structural_segment_ids
    ),
    "structuralization_dropped_segment_ids": (
        structuralization_dropped_segment_ids
    ),
    "segment_subassemblies_complete": segment_subassemblies_complete,
    "structural_connectors_complete": structural_connectors_complete,
    "segment_graph_connected": segment_graph_connected,
    "connected_segment_ids": connected_segment_ids,
    "required_functional_target_count_gate_valid": required_count_gate_valid,
    "required_functional_attachments_complete": (
        required_functional_attachments_complete
    ),
    "no_unmediated_structural_cross_segment_contacts": (
        no_direct_cross_segment_locks
    ),
    "collision_free": collision_free,
    "connector_receiving_face_requirement_count": int(
        len(connector_receiving_face_requirements_df)
    ),
    "connector_receiving_face_satisfied_count": int(
        connector_receiving_face_final_audit_df.get(
            "satisfied",
            pd.Series(dtype=bool),
        ).astype(bool).sum()
    ),
    "connector_receiving_faces_complete": (
        connector_receiving_faces_complete
    ),
    "reservation_hard_requirement_generation_complete": bool(
        reservation_hard_requirement_generation_complete
    ),
    "reservation_missing_hard_requirement_owner_ids": (
        reservation_missing_hard_requirement_owner_ids
    ),
    "reservation_hard_reservations_complete": bool(
        reservation_hard_reservations_complete
    ),
    "reservation_soft_reservation_satisfaction_ratio": float(
        reservation_soft_reservation_satisfaction_ratio
    ),
    "reservation_reservation_conflicts_complete": bool(
        reservation_reservation_conflicts_complete
    ),
    "reservation_interface_reservation_group_count": int(
        reservation_interface_reservation_requirements_df.get(
            "requirement_group_id",
            pd.Series(dtype=str),
        ).nunique()
        if not reservation_interface_reservation_requirements_df.empty
        else 0
    ),
    "symmetry_enabled": SYMMETRY_ENABLED,
    "symmetry_axis": SYMMETRY_CONFIG.get("axis", "X"),
    "symmetry_center_plane": SYMMETRY_CENTER_PLANE,
    "structural_symmetry_pair_count": len(
        structural_symmetry_pairs
    ),
    "structural_symmetry_complete": (
        structural_symmetry_complete
    ),
    "connector_symmetry_complete": (
        connector_symmetry_complete
    ),
    "functional_symmetry_complete": (
        functional_symmetry_complete
    ),
    "combined_symmetry_complete": (
        combined_symmetry_complete
    ),
    "symmetry_claim_required": symmetry_claim_required,
    "final_status": final_status,
    "final_claim_valid": final_claim_valid,
}
(OUTPUT_DIR / "segment_connector_final_summary.json").write_text(
    json.dumps(final_summary, indent=2),
    encoding="utf-8",
)
INPUT_DIAGNOSTICS.update({
    "stage": "pipeline_complete",
    "structural_interface_count": int(len(structural_interfaces_df)),
    "functional_candidate_count": int(len(functional_candidates_df)),
    "selected_functional_count": int(len(selected_functional_df)),
    "structural_block_count": int(len(segment_blocks)),
    "reservation_requirement_group_count": int(
        reservation_interface_reservation_requirements_df.get(
            "requirement_group_id",
            pd.Series(dtype=str),
        ).nunique()
        if not reservation_interface_reservation_requirements_df.empty
        else 0
    ),
    "hard_requirement_generation_complete": bool(
        reservation_hard_requirement_generation_complete
    ),
    "missing_hard_requirement_owner_ids": (
        reservation_missing_hard_requirement_owner_ids
    ),
    "hard_reservations_complete": bool(reservation_hard_reservations_complete),
    "final_claim_valid": bool(final_claim_valid),
})
INPUT_DIAGNOSTICS_PATH.write_text(
    json.dumps(INPUT_DIAGNOSTICS, indent=2),
    encoding="utf-8",
)

instruction_lines = [
    "# Integrated Segment Build Instructions",
    "",
    f"- Task: {TASK_CONTEXT.get('task_id')}",
    f"- Root segment: {root_segment_id}",
    f"- Final status: `{final_status}`",
    f"- Symmetry center plane: {SYMMETRY_CENTER_PLANE}",
    f"- Structural symmetry complete: "
    f"{structural_symmetry_complete}",
    f"- Connector symmetry complete: "
    f"{connector_symmetry_complete}",
    f"- Functional symmetry complete: "
    f"{functional_symmetry_complete}",
    f"- Combined symmetry complete: "
    f"{combined_symmetry_complete}",
    f"- Connector receiving faces complete: "
    f"{connector_receiving_faces_complete}",
    f"- Semantic preflight gate valid: "
    f"{semantic_preflight_gate_valid}",
    f"- Structuralization gate valid: "
    f"{structuralization_gate_valid}",
    "",
    "## Build each segment subassembly",
    "",
]
for result in segment_results:
    result_segment_id = int(result["segment_id"])
    result_segment_name = str(result.get(
        "segment_name",
        segment_display_name_by_id.get(result_segment_id, f"Segment {result_segment_id}"),
    ))
    instruction_lines.extend([
        f"### {result_segment_name} (segment {result_segment_id})",
        "",
        f"- Semantic label: {result.get('segment_label', 'unknown')}",
        f"- Valid: {result.get('valid', False)}",
        f"- Packable voxels: {result.get('packable_voxels', 0)}",
        f"- Selected build axis: "
        f"{result.get('selected_build_axis', 'not available')}",
        f"- Error: {result.get('error') or 'none'}",
        "",
    ])

instruction_lines.extend([
    "## Detailed segment build steps",
    "",
])
for row in subassembly_build_steps_df.to_dict(
    orient="records"
):
    row_segment_id = int(row["segment_id"])
    row_segment_name = str(row.get(
        "segment_name",
        segment_display_name_by_id.get(row_segment_id, f"Segment {row_segment_id}"),
    ))
    instruction_lines.append(
        f"- Global step {row['global_step']}: "
        f"{row_segment_name} (segment {row_segment_id}), "
        f"local step {row['local_step']}, "
        f"row {row['row']}, "
        f"status {row['status']}, "
        f"new blocks {row['new_block_ids']}."
    )

instruction_lines.extend([
    "",
    "## Assemble the segment subassemblies",
    "",
])
for step in assembly_steps:
    assembly_step_number = int(
        step["assembly_step"]
    )
    action = str(
        step.get(
            "action",
            "",
        )
    )
    anchor_segment_id = step.get(
        "anchor_segment_id"
    )
    attached_segment_id = step.get(
        "attached_segment_id"
    )
    interface_id = step.get(
        "interface_id"
    )

    attached_text = segment_display_text(
        attached_segment_id,
        missing_text="unassigned segment",
    )

    is_root_step = bool(
        action
        == "start_with_segment_subassembly"
        or optional_value_is_missing(
            anchor_segment_id
        )
    )

    if is_root_step:
        instruction_lines.append(
            f"- Step {assembly_step_number}: "
            f"Start with completed "
            f"{attached_text}."
        )
        continue

    anchor_text = segment_display_text(
        anchor_segment_id
    )
    interface_text = (
        "not assigned"
        if optional_value_is_missing(
            interface_id
        )
        else str(interface_id)
    )

    instruction_lines.append(
        f"- Step {assembly_step_number}: "
        f"{action}; "
        f"attach {attached_text} "
        f"to {anchor_text}; "
        f"interface={interface_text}."
    )

(OUTPUT_DIR / "integrated_build_instructions.md").write_text(
    "\n".join(instruction_lines),
    encoding="utf-8",
)

if VISUALIZATION_CONFIG.get("enabled", True):
    expected_final_visualizations = {
        "assembly_player_html": (
            VISUALIZATION_DIR
            / "assembly_assembly_player.html"
        ),
        "complete_build_timeline_html": (
            VISUALIZATION_DIR
            / "complete_build_timeline_interactive.html"
        ),
        "proper_complete_build_steps_html": (
            VISUALIZATION_DIR
            / "proper_complete_build_steps.html"
        ),
        "face_contact_html": (
            VISUALIZATION_DIR
            / "interactive_face_contact_diagnostic.html"
        ),
        "final_state_html": (
            VISUALIZATION_DIR
            / "final_state_interactive.html"
        ),
        "terminal_state_png": (
            VISUALIZATION_DIR
            / (
                "final_validated_state.png"
                if final_claim_valid
                else (
                    "available_validated_state_"
                    "incomplete.png"
                )
            )
        ),
    }

    final_visualization_export_audit = {
        "final_claim_valid": bool(
            final_claim_valid
        ),
        "expected_files": {
            key: {
                "path": str(path),
                "exists": bool(
                    path.is_file()
                ),
                "size_bytes": (
                    int(path.stat().st_size)
                    if path.is_file()
                    else 0
                ),
            }
            for key, path in (
                expected_final_visualizations.items()
            )
        },
    }
    final_visualization_export_audit[
        "all_expected_files_exist"
    ] = all(
        row["exists"]
        for row in (
            final_visualization_export_audit[
                "expected_files"
            ].values()
        )
    )

    (
        OUTPUT_DIR
        / "final_visualization_export_audit.json"
    ).write_text(
        json.dumps(
            final_visualization_export_audit,
            indent=2,
        ),
        encoding="utf-8",
    )

    visualization_manifest_path = save_visualization_manifest()

# ------------------------------------------------------------
# Concise inline review
#
# Detailed build-step and visualization-driver tables are still exported:
# - subassembly_build_steps.csv
# - complete_build_steps.csv
# - assembly_visual_steps.csv
# - segment_connector_assembly_steps.csv
# ------------------------------------------------------------

print("Final pipeline summary")
final_review_fields = [
    "final_claim_valid",
    "final_status",
    "structural_segment_count",
    "segment_structural_block_count",
    "direct_structural_join_count",
    "valid_structural_connector_count",
    "validated_functional_target_count",
    "validated_wheel_block_count",
    "validated_wheel_families",
    "wheel_required_family",
    "wheel_family_requirement_satisfied",
    "big_wheel_family_requirement_satisfied",
    "motion_subassembly_connector_count",
    "functional_subassembly_structural_block_count",
    "final_block_count",
    "collision_free",
    "combined_symmetry_complete",
]
final_review_rows = [
    {
        "metric": field,
        "value": final_summary.get(field),
    }
    for field in final_review_fields
]
emit_diagnostic(
    pd.DataFrame(final_review_rows)
)

print("Segment subassembly validation")
segment_review_columns = [
    column
    for column in [
        "segment_id",
        "segment_name",
        "segment_label",
        "selected_build_axis",
        "planning_mode",
        "valid",
        "exact_coverage",
        "error",
    ]
    if column in segment_subassembly_validation_df.columns
]
emit_diagnostic(
    segment_subassembly_validation_df[
        segment_review_columns
    ]
)

if not segment_build_failure_diagnostics_df.empty:
    print("Failed segment diagnostics")
    emit_diagnostic(
        segment_build_failure_diagnostics_df
    )

print("Structural join validation")
connector_review_columns = [
    column
    for column in [
        "interface_id",
        "segment_a",
        "segment_b",
        "join_mode",
        "locks_to_segment_a",
        "locks_to_segment_b",
        "lock_area_segment_a",
        "lock_area_segment_b",
        "contact_count",
        "valid",
    ]
    if column in connector_validation_df.columns
]
emit_diagnostic(
    connector_validation_df[
        connector_review_columns
    ]
)

print("Functional attachment validation")
functional_review_columns = [
    column
    for column in [
        "physical_target_id",
        "block_family",
        "block_id",
        "anchor_segment_id",
        "contact_area",
        "valid",
        "validation_status",
    ]
    if column in functional_validation_df.columns
]
emit_diagnostic(
    functional_validation_df[
        functional_review_columns
    ]
)

print("Segment assembly sequence")
assembly_review_columns = [
    column
    for column in [
        "assembly_step",
        "anchor_segment_id",
        "anchor_segment_name",
        "attached_segment_id",
        "attached_segment_name",
        "interface_id",
        "connection_type",
        "instruction",
        "valid",
    ]
    if column in assembly_oriented_assembly_steps_df.columns
]
emit_diagnostic(
    assembly_oriented_assembly_steps_df[
        assembly_review_columns
    ]
    if assembly_review_columns
    else assembly_oriented_assembly_steps_df
)


# ============================================================
# Independent final inventory recount and hard claim gate
# ============================================================
FINAL_INVENTORY_RECOUNT = block_family_counts(all_final_blocks)
LEDGER_BEFORE_FINALIZATION = INVENTORY_LEDGER.committed

# Structural segment plans are committed during planning. Any actual
# connector/functional blocks are committed here as a final atomic group;
# this preserves a hard limit even for catalog-driven nonstructural paths.
finalization_delta = {
    family: int(count) - int(LEDGER_BEFORE_FINALIZATION.get(family, 0))
    for family, count in FINAL_INVENTORY_RECOUNT.items()
    if int(count) - int(LEDGER_BEFORE_FINALIZATION.get(family, 0)) > 0
}
FINALIZATION_INVENTORY_ERROR = None
if finalization_delta:
    if (
        GLOBAL_DEFERRED_INVENTORY
        and not bool(GLOBAL_INVENTORY_ALLOCATION.get("committed", False))
    ):
        FINALIZATION_INVENTORY_ERROR = (
            "Skipped final inventory commit because the global model allocation "
            "did not pass."
        )
    else:
        try:
            INVENTORY_LEDGER.reserve_and_commit(
                finalization_delta,
                scope="final_nonstructural_and_connector_blocks",
            )
        except InventoryExhaustedError as error:
            FINALIZATION_INVENTORY_ERROR = str(error)

(OUTPUT_DIR / "inventory_finalization_status.json").write_text(
    json.dumps(
        {
            "finalization_delta": finalization_delta,
            "error": FINALIZATION_INVENTORY_ERROR,
            "global_allocation_status": GLOBAL_INVENTORY_ALLOCATION.get("status"),
        },
        indent=2,
    ),
    encoding="utf-8",
)

FINAL_INVENTORY_AUDIT = INVENTORY_LEDGER.final_recount(
    all_final_blocks
)

pd.DataFrame(
    FINAL_INVENTORY_AUDIT["usage_rows"]
).to_csv(
    OUTPUT_DIR / "inventory_usage.csv",
    index=False,
)
pd.DataFrame(
    [
        {
            **event,
            "requirements": json.dumps(
                event.get("requirements", {}),
                sort_keys=True,
            ),
            "shortages": json.dumps(
                event.get("shortages", {}),
                sort_keys=True,
            ),
            "committed_after": json.dumps(
                event.get("committed_after", {}),
                sort_keys=True,
            ),
            "reserved_after": json.dumps(
                event.get("reserved_after", {}),
                sort_keys=True,
            ),
        }
        for event in INVENTORY_LEDGER.events()
    ]
).to_csv(
    OUTPUT_DIR / "inventory_events.csv",
    index=False,
)
(OUTPUT_DIR / "inventory_validation.json").write_text(
    json.dumps(FINAL_INVENTORY_AUDIT, indent=2),
    encoding="utf-8",
)

shortage_rows = []
for family, row in FINAL_INVENTORY_AUDIT.get("overages", {}).items():
    shortage_rows.append({"block_family": family, **row})
pd.DataFrame(
    shortage_rows,
    columns=["block_family", "used", "capacity", "overage"],
).to_csv(
    OUTPUT_DIR / "unmet_inventory_requirements.csv",
    index=False,
)

summary_path = OUTPUT_DIR / "segment_connector_final_summary.json"
summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
summary_payload.update({
    "inventory_profile": INVENTORY_PROFILE.inventory_id,
    "inventory_mode": INVENTORY_PROFILE.mode,
    "inventory_enforced": INVENTORY_ENFORCED,
    "inventory_valid": bool(FINAL_INVENTORY_AUDIT["valid"]),
    "inventory_recount": FINAL_INVENTORY_AUDIT["recount"],
    "inventory_ledger_committed": FINAL_INVENTORY_AUDIT["ledger_committed"],
})
summary_payload["final_claim_valid"] = bool(
    summary_payload.get("final_claim_valid", False)
    and FINAL_INVENTORY_AUDIT["valid"]
)
if not summary_payload["final_claim_valid"]:
    summary_payload["final_status"] = "invalid_inventory_or_build_claim"
summary_path.write_text(
    json.dumps(summary_payload, indent=2),
    encoding="utf-8",
)

_raise_on_invalid_inventory = bool(
    INVENTORY_CONFIG.get("raise_on_invalid_final_claim", True)
)
if (
    INVENTORY_ENFORCED
    and not FINAL_INVENTORY_AUDIT["valid"]
    and _raise_on_invalid_inventory
    and not (
        GLOBAL_DEFERRED_INVENTORY
        and not bool(GLOBAL_INVENTORY_ALLOCATION.get("committed", False))
    )
):
    raise InventoryError(
        "Final inventory claim failed: "
        + json.dumps(
            {
                "overages": FINAL_INVENTORY_AUDIT["overages"],
                "ledger_mismatches": FINAL_INVENTORY_AUDIT["ledger_mismatches"],
                "open_reservations": FINAL_INVENTORY_AUDIT["open_reservations"],
            },
            sort_keys=True,
        )
    )

print(
    "Inventory validation:",
    "PASS" if FINAL_INVENTORY_AUDIT["valid"] else "FAIL",
    FINAL_INVENTORY_AUDIT["recount"],
)


if TASK_CONTEXT.get(
    "visualization",
    {},
).get(
    "show_dedicated_inline_player_cell",
    True,
):
    if "assembly_player_figure" not in globals():
        print(
            "The player is not available yet. "
            "Run the integrated planning cell above first."
        )
    else:
        display_plotly_embedded(
            assembly_player_figure,
            description=(
                "Connector-mediated assembly player"
            ),
            force_include_plotlyjs=True,
        )


if TASK_CONTEXT.get(
    "visualization",
    {},
).get(
    "show_dedicated_inline_complete_build_timeline_cell",
    True,
):
    if (
        "inline_complete_build_timeline_figure"
        not in globals()
    ):
        print(
            "The complete-build timeline is not available yet. "
            "Run the integrated planning cell above first."
        )
    else:
        display_plotly_embedded(
            inline_complete_build_timeline_figure,
            description=(
                "Complete build timeline with terminal state"
            ),
            force_include_plotlyjs=False,
        )


if TASK_CONTEXT.get(
    "visualization",
    {},
).get(
    "show_dedicated_inline_face_contact_cell",
    True,
):
    if (
        "interactive_face_contact_fig"
        not in globals()
    ):
        print(
            "The interactive face/contact "
            "diagnostic is not available yet. "
            "Run the integrated planning cell "
            "above first."
        )
    else:
        display_plotly_embedded(
            interactive_face_contact_fig,
            description=(
                "Interactive male/female faces "
                "and structural contacts"
            ),
            force_include_plotlyjs=True,
        )


if TASK_CONTEXT.get(
    "visualization",
    {},
).get(
    "show_dedicated_inline_proper_complete_build_steps_cell",
    True,
):
    if (
        "proper_complete_build_steps_figure"
        not in globals()
        or proper_complete_build_steps_figure
        is None
    ):
        failed_ids = (
            segment_build_gate_summary.get(
                "failed_segment_ids",
                [],
            )
            if (
                "segment_build_gate_summary"
                in globals()
            )
            else []
        )
        print(
            "The full-model build-step player was not generated because "
            "the final build claim is not valid. "
            f"Failed structural segment IDs: {failed_ids}. "
            "Review each valid segment's "
            "segments/segment_NNN/validated_build_steps_interactive.html "
            "and the segment build-axis audits."
        )
    else:
        if (
            "display_block_family_counts_df"
            in globals()
            and not display_block_family_counts_df.empty
        ):
            emit_diagnostic(
                display_block_family_counts_df
            )
        display_plotly_embedded(
            proper_complete_build_steps_figure,
            description=(
                "Proper validated build-step player"
            ),
            force_include_plotlyjs=False,
        )


if TASK_CONTEXT.get(
    "visualization",
    {},
).get(
    "show_dedicated_inline_final_state_cell",
    True,
):
    if "inline_final_state_figure" not in globals():
        print(
            "The final-state figure is not available yet. "
            "Run the integrated planning cell above first."
        )
    else:
        if (
            "display_block_family_counts_df"
            in globals()
            and not display_block_family_counts_df.empty
        ):
            emit_diagnostic(
                display_block_family_counts_df
            )
        if "display_block_family_count_summary" in globals():
            print(
                "Displayed block counts: "
                + display_block_family_count_summary
            )
        display_plotly_embedded(
            inline_final_state_figure,
            description=(
                "Interactive structural/final state"
            ),
            force_include_plotlyjs=False,
        )



if TASK_CONTEXT.get("visualization", {}).get(
    "show_inline_reservation_selective_reservation_view",
    False,
):
    display_plotly_embedded(
        reserved_face_interactive_figure(
            segment_grid_planner,
            reservation_interface_reservation_requirements_df,
        ),
        description="Reservation selective hard/soft/none reservations",
        force_include_plotlyjs=False,
    )

if not reservation_interface_strategy_decisions_df.empty:
    display_columns = [
        column
        for column in [
            "reservation_scope",
            "interface_id",
            "attachment_id",
            "physical_target_id",
            "connection_type",
            "reservation_strategy",
            "strategy_reason_code",
        ]
        if column in reservation_interface_strategy_decisions_df.columns
    ]
    emit_diagnostic(reservation_interface_strategy_decisions_df[display_columns])

emit_diagnostic(reservation_interface_reservation_final_audit_df)


if log_enabled(
    "show_final_summary",
    True,
):
    summary_required_target_ids = list(
        globals().get(
            "required_physical_target_ids",
            sorted(
                set(
                    physical_targets_df.get(
                        "physical_target_id",
                        pd.Series(dtype=str),
                    ).astype(str)
                )
            )
            if "physical_targets_df" in globals()
            else [],
        )
    )
    summary_rows = [
        {
            "Final claim valid": bool(
                final_claim_valid
            ),
            "Structural segments": (
                f"{sum(bool(result.get('valid', False)) for result in segment_results)}"
                f"/{len(structural_segment_ids)}"
            ),
            "Valid connectors": (
                f"{int(connector_validation_df['valid'].sum()) if not connector_validation_df.empty else 0}"
                f"/{len(required_interface_ids)}"
            ),
            "Valid functionals": (
                f"{int(functional_validation_df['valid'].sum()) if not functional_validation_df.empty else 0}"
                f"/{len(summary_required_target_ids)}"
            ),
            "Collisions": int(
                len(
                    collision_df
                )
            ),
            "Hard requirements generated": bool(
                reservation_hard_requirement_generation_complete
            ),
            "Hard reservations": bool(
                reservation_hard_reservations_complete
            ),
            "Soft reservation ratio": round(
                float(reservation_soft_reservation_satisfaction_ratio),
                3,
            ),
        }
    ]
    emit_diagnostic(
        pd.DataFrame(
            summary_rows
        )
    )

    print(
        "Output directory:",
        OUTPUT_DIR,
    )
    print(
        "Review first:"
    )
    for filename in [
        "input_diagnostics.json",
        "reservation_input_diagnostics.json",
        "model_compatibility_preflight.json",
        "instructor_build_intent_preflight.json",
        "reservation_interface_reservation_preflight.json",
        "reservation_interface_strategy_decisions.csv",
        "reservation_interface_reservation_requirements.csv",
        "reservation_interface_reservation_conflicts.csv",
        "reservation_interface_reservation_final_audit.csv",
        "reservation_interface_reservation_final_summary.json",
        "segment_connector_final_summary.json",
        "segment_subassembly_validation.csv",
        "structural_connector_validation.csv",
        "direct_structural_join_candidate_audit.csv",
        "functional_rotation_centering_audit.csv",
        "functional_segment_group_table.csv",
        "custom_subassembly_audit.json",
        "functional_subassembly_validation.csv",
        "display_block_family_counts.csv",
        "functional_attachment_validation.csv",
        "visualizations/reservation_selective_interface_reservations.html",
        "visualizations/reservation_functional_candidate_filtering.html",
        "visualizations/reservation_interface_reservation_fulfillment.html",
        "visualizations/proper_complete_build_steps.html",
    ]:
        print(
            "-",
            OUTPUT_DIR
            / filename,
        )

    if not final_claim_valid:
        print(
            "The complete-model player remains suppressed because "
            "the final claim is not valid."
        )


# The row/column engine is executed as a dedicated subprocess. Large in-memory
# visualization objects can make normal interpreter cleanup spend an unbounded
# amount of time after all artifacts are already written. Terminate
# the completed worker directly; the runner performs post-processing and writes
# the final run manifest in its own process.
if __name__ == "__main__":
    os._exit(0)
