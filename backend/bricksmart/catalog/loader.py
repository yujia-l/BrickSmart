"""CSV block-catalog loader and normalizer.

This module reads the authoritative block catalog, validates required fields,
and exposes normalized rows for downstream planning.
"""

from __future__ import annotations

import csv
import itertools
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from bricksmart.hashing import sha256_file

from bricksmart.catalog.models import (
    BlockCatalog,
    CatalogBlockDefinition,
    CatalogBuildPolicy,
    CatalogGeometrySpec,
    CatalogMotionSpec,
)
from bricksmart.catalog.schema import (
    CATALOG_SCHEMA_VERSION,
    is_rich_catalog_schema,
    validate_rich_catalog_headers,
    validate_rich_catalog_row,
)
from bricksmart.exceptions import CatalogConfigurationError

_ID_ALIASES = (
    "block_family",
    "block_type",
    "block_id",
    "catalog_id",
    "block_name",
    "part_type",
    "part_id",
    "name",
)
_CATEGORY_ALIASES = ("category", "block_category", "block_family", "family", "type")
_EXPLICIT_DIMENSION_ALIASES = (
    "allowed_dimensions",
    "allowed_sizes",
    "packing_dimensions",
    "rotated_dimensions",
    "orientation_dimensions",
)
_BASE_DIMENSION_ALIASES = ("geometry_size", "size", "anchor_size")
_DIMENSION_X_ALIASES = ("size_x", "x_size", "dim_x", "studs_x", "length", "width")
_DIMENSION_Y_ALIASES = ("size_y", "y_size", "dim_y", "studs_y", "depth")
_DIMENSION_Z_ALIASES = ("size_z", "z_size", "dim_z", "studs_z", "height")
_STRUCTURAL_ALIASES = (
    "structural_eligible",
    "is_structural",
    "packing_eligible",
    "structural_block",
)
_PRIORITY_ALIASES = (
    "inventory_priority",
    "default_packing_priority",
    "packing_priority",
    "planner_priority",
    "priority",
    "packing_rank",
)
_COLOR_ALIASES = (
    "display_color",
    "visualization_color",
    "render_color",
    "block_color",
    "hex_color",
    "color_hex",
    "colour",
    "color",
)
_ROTATION_ALIASES = (
    "allowed_orientations",
    "allowed_rotations",
    "rotation_policy",
    "orientation_policy",
    "rotations",
    "rotation",
)
_MALE_FACE_ALIASES = (
    "primary_male_faces",
    "male_faces",
    "male_face",
    "male_connectors",
    "male_connector_faces",
)
_FEMALE_FACE_ALIASES = (
    "primary_female_faces",
    "female_faces",
    "female_face",
    "female_connectors",
    "female_connector_faces",
)

_DIMENSION_RE = re.compile(
    r"(?<!\d)(\d+)\s*[x×,]\s*(\d+)\s*[x×,]\s*(\d+)(?!\d)",
    re.IGNORECASE,
)
_TOKEN_SPLIT_RE = re.compile(r"[,;|\n]+")
_TRUE_VALUES = {"true", "yes", "y", "1", "enabled", "eligible"}
_FALSE_VALUES = {"false", "no", "n", "0", "disabled", "ineligible", ""}


def _normalize_header(value: Any) -> str:
    """Normalize header.
    
    :param value: Value used by the operation.
    :type value: Any
    :returns: The computed result.
    :rtype: str
    """
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _first_present(row: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    """Return the first present value.
    
    :param row: Row record to process.
    :type row: Mapping[str, Any]
    :param aliases: The aliases value.
    :type aliases: Sequence[str]
    :returns: The result produced by the function.
    :rtype: Any
    """
    for alias in aliases:
        if alias in row and row[alias] not in (None, ""):
            return row[alias]
    return None


def _json_safe(value: Any) -> Any:
    """Return the json safe value.
    
    :param value: Value used by the operation.
    :type value: Any
    :returns: The result produced by the function.
    :rtype: Any
    """
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _parse_bool(value: Any, *, field: str, block_type: str) -> bool:
    """Parse bool.
    
    :param value: Value used by the operation.
    :type value: Any
    :param field: The field value.
    :type field: str
    :param block_type: The block type value.
    :type block_type: str
    :returns: The computed result.
    :rtype: bool
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise CatalogConfigurationError(
        f"Cannot parse {field}={value!r} for catalog block {block_type}"
    )


def _parse_int(value: Any, *, default: int, field: str, block_type: str) -> int:
    """Parse int.
    
    :param value: Value used by the operation.
    :type value: Any
    :param default: Fallback value used when no explicit value is available.
    :type default: int
    :param field: The field value.
    :type field: str
    :param block_type: The block type value.
    :type block_type: str
    :returns: The computed result.
    :rtype: int
    """
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError) as exc:
        raise CatalogConfigurationError(
            f"Cannot parse {field}={value!r} for catalog block {block_type}"
        ) from exc


def _parse_face_tokens(value: Any) -> tuple[str, ...]:
    """Parse face tokens.
    
    :param value: Value used by the operation.
    :type value: Any
    :returns: The computed result.
    :rtype: tuple[str, ...]
    """
    if value in (None, ""):
        return ()
    if isinstance(value, (list, tuple, set)):
        raw = [str(item).strip() for item in value]
    else:
        text = str(value).strip()
        if text.startswith("["):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, list):
                raw = [str(item).strip() for item in payload]
            else:
                raw = [item.strip() for item in _TOKEN_SPLIT_RE.split(text)]
        else:
            raw = [item.strip() for item in _TOKEN_SPLIT_RE.split(text)]
    return tuple(dict.fromkeys(item for item in raw if item))


def _parse_dimension_value(value: Any) -> tuple[tuple[int, int, int], ...]:
    """Parse dimension value.
    
    :param value: Value used by the operation.
    :type value: Any
    :returns: The computed result.
    :rtype: tuple[tuple[int, int, int], ...]
    """
    if value in (None, ""):
        return ()
    dimensions: list[tuple[int, int, int]] = []
    if isinstance(value, (list, tuple)):
        candidates = value
    else:
        text = str(value).strip()
        candidates: Any = None
        if text.startswith("["):
            try:
                candidates = json.loads(text)
            except json.JSONDecodeError:
                candidates = None
        if candidates is None:
            candidates = _DIMENSION_RE.findall(text)
    for item in candidates:
        if isinstance(item, str):
            matches = _DIMENSION_RE.findall(item)
            dimensions.extend(tuple(int(v) for v in match) for match in matches)
        elif isinstance(item, (list, tuple)) and len(item) == 3:
            dimensions.append(tuple(int(v) for v in item))
    return tuple(dict.fromkeys(dimensions))




def _parse_single_dimension(value: Any) -> tuple[int, int, int] | None:
    """Parse single dimension.
    
    :param value: Value used by the operation.
    :type value: Any
    :returns: The computed result.
    :rtype: tuple[int, int, int] | None
    """
    values = _parse_dimension_value(value)
    return values[0] if values else None


def _text(row: Mapping[str, Any], field: str) -> str:
    """Return the text value.
    
    :param row: Row record to process.
    :type row: Mapping[str, Any]
    :param field: The field value.
    :type field: str
    :returns: The result produced by the function.
    :rtype: str
    """
    return str(row.get(field) or "").strip()


def _semicolon_tokens(value: Any) -> tuple[str, ...]:
    """Return the semicolon tokens value.
    
    :param value: Value used by the operation.
    :type value: Any
    :returns: The result produced by the function.
    :rtype: tuple[str, ...]
    """
    return tuple(
        dict.fromkeys(
            token.strip()
            for token in str(value or "").split(";")
            if token.strip()
        )
    )

def _rotation_tokens(value: Any) -> tuple[str, ...]:
    """Return rotation tokens.
    
    :param value: Value used by the operation.
    :type value: Any
    :returns: The result produced by the function.
    :rtype: tuple[str, ...]
    """
    if value in (None, ""):
        return ()
    if isinstance(value, (list, tuple, set)):
        tokens = [str(item).strip().lower() for item in value]
    else:
        tokens = [item.strip().lower() for item in _TOKEN_SPLIT_RE.split(str(value))]
    return tuple(dict.fromkeys(token for token in tokens if token))


def _dimensions_from_xyz(
    row: Mapping[str, Any], *, block_type: str
) -> tuple[int, int, int] | None:
    """Return the dimensions from xyz value.
    
    :param row: Row record to process.
    :type row: Mapping[str, Any]
    :param block_type: The block type value.
    :type block_type: str
    :returns: The result produced by the function.
    :rtype: tuple[int, int, int] | None
    """
    values = [
        _first_present(row, _DIMENSION_X_ALIASES),
        _first_present(row, _DIMENSION_Y_ALIASES),
        _first_present(row, _DIMENSION_Z_ALIASES),
    ]
    if all(value in (None, "") for value in values):
        return None
    if any(value in (None, "") for value in values):
        raise CatalogConfigurationError(
            f"Catalog block {block_type} has an incomplete X/Y/Z dimension triplet"
        )
    try:
        parsed = tuple(int(float(value)) for value in values)
    except (TypeError, ValueError) as exc:
        raise CatalogConfigurationError(
            f"Catalog block {block_type} contains non-integer dimensions: {values}"
        ) from exc
    if any(value <= 0 for value in parsed):
        raise CatalogConfigurationError(
            f"Catalog block {block_type} dimensions must all be positive: {parsed}"
        )
    return parsed  # type: ignore[return-value]


def _expand_dimensions_by_rotation(
    base: tuple[int, int, int] | None,
    rotations: tuple[str, ...],
) -> tuple[tuple[int, int, int], ...]:
    """Return the expand dimensions by rotation value.
    
    :param base: The base value.
    :type base: tuple[int, int, int] | None
    :param rotations: The rotations value.
    :type rotations: tuple[str, ...]
    :returns: The result produced by the function.
    :rtype: tuple[tuple[int, int, int], ...]
    """
    if base is None:
        return ()
    normalized = " ".join(rotations)
    rotation_set = set(rotations)
    if not normalized or normalized in {"none", "fixed", "0", "no_rotation", "x"}:
        return (base,)
    if (
        {"x", "y", "z"}.issubset(rotation_set)
        or any(token in normalized for token in ("all", "any", "3d", "xyz", "permutation"))
    ):
        return tuple(dict.fromkeys(itertools.permutations(base, 3)))
    if any(token in rotation_set for token in ("z", "xy", "90", "270", "quarter_turn")):
        x, y, z = base
        return tuple(dict.fromkeys((base, (y, x, z))))
    return (base,)


def _find_header_row(rows: Sequence[Sequence[Any]], *, scan_limit: int = 40) -> tuple[int, list[str]] | None:
    """Find header row.
    
    :param rows: Row records to process.
    :type rows: Sequence[Sequence[Any]]
    :param scan_limit: The scan limit value.
    :type scan_limit: int
    :returns: The computed result.
    :rtype: tuple[int, list[str]] | None
    """
    for row_index, values in enumerate(rows[:scan_limit], start=1):
        headers = [_normalize_header(value) for value in values]
        if any(alias in headers for alias in _ID_ALIASES):
            return row_index, headers
    return None


def load_block_catalog(path: str | Path) -> BlockCatalog:
    """Load the authoritative BrickSmart block catalog from UTF-8 CSV."""
    path = Path(path)
    if not path.exists():
        raise CatalogConfigurationError(
            f"Block catalog CSV not found: {path}. "
            "Place block_definitions.csv at this exact path or pass --catalog."
        )
    if path.suffix.lower() != ".csv":
        raise CatalogConfigurationError(
            "BrickSmart accepts the authoritative CSV catalog only; "
            f"expected block_definitions.csv, got: {path}"
        )

    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            csv_rows = list(csv.reader(handle))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise CatalogConfigurationError(f"Unable to read block catalog CSV {path}: {exc}") from exc

    detected = _find_header_row(csv_rows)
    if detected is None:
        raise CatalogConfigurationError(
            f"No block definition table with a recognized ID column was found in {path}"
        )
    header_row, headers = detected
    id_columns = [alias for alias in _ID_ALIASES if alias in headers]
    if not id_columns:
        raise CatalogConfigurationError(
            f"No recognized block ID column was found in {path}"
        )
    id_column = id_columns[0]
    source_name = path.name
    rich_schema = is_rich_catalog_schema(headers)
    if rich_schema:
        validate_rich_catalog_headers(headers)
    schema_version = CATALOG_SCHEMA_VERSION if rich_schema else "legacy-compatible"
    definitions: list[CatalogBlockDefinition] = []

    for source_row, values in enumerate(csv_rows[header_row:], start=header_row + 1):
        row = {
            header: value
            for header, value in zip(headers, values)
            if header
        }
        block_type = str(row.get(id_column) or "").strip()
        if not block_type:
            continue
        if rich_schema:
            validate_rich_catalog_row(
                row, source_name=source_name, source_row=source_row
            )
        category = str(_first_present(row, _CATEGORY_ALIASES) or "").strip()
        explicit_structural = _first_present(row, _STRUCTURAL_ALIASES)
        structural_eligible = (
            _parse_bool(
                explicit_structural,
                field="structural_eligible",
                block_type=block_type,
            )
            if explicit_structural not in (None, "")
            else "structural" in category.lower()
        )
        rotations = _rotation_tokens(_first_present(row, _ROTATION_ALIASES))

        explicit_dimensions = _parse_dimension_value(
            _first_present(row, _EXPLICIT_DIMENSION_ALIASES)
        )
        if explicit_dimensions:
            dimensions = explicit_dimensions
        else:
            base_dimensions = _parse_dimension_value(
                _first_present(row, _BASE_DIMENSION_ALIASES)
            )
            if base_dimensions:
                dimensions = tuple(
                    dict.fromkeys(
                        dimension
                        for base in base_dimensions
                        for dimension in _expand_dimensions_by_rotation(base, rotations)
                    )
                )
            else:
                dimensions = _expand_dimensions_by_rotation(
                    _dimensions_from_xyz(row, block_type=block_type), rotations
                )

        if structural_eligible and not dimensions:
            raise CatalogConfigurationError(
                f"Structural catalog block {block_type} on {source_name}:{source_row} "
                "has no usable dimensions"
            )
        color = str(_first_present(row, _COLOR_ALIASES) or "").strip()
        if structural_eligible and not color:
            raise CatalogConfigurationError(
                f"Structural catalog block {block_type} on {source_name}:{source_row} "
                "has no visualization color"
            )
        priority = _parse_int(
            _first_present(row, _PRIORITY_ALIASES),
            default=0,
            field="packing_priority",
            block_type=block_type,
        )
        geometry = CatalogGeometrySpec(
            anchor_dimensions=_parse_single_dimension(row.get("anchor_size")),
            representation=_text(row, "geometry_representation"),
            status=_text(row, "geometry_status"),
            visual_shape=_text(row, "visual_shape"),
            visible_dimensions=_parse_single_dimension(row.get("visible_geometry_size")),
            visible_layer_spec=_text(row, "visible_geometry_layer_spec"),
            anchor_layer_spec=_text(row, "anchor_geometry_layer_spec"),
            clearance_dimensions=_parse_single_dimension(
                row.get("clearance_reservation_size")
            ),
            clearance_layer_spec=_text(row, "clearance_reservation_layer_spec"),
            coordinate_frame=_text(row, "geometry_coordinate_frame"),
            off_grid=_parse_bool(
                row.get("off_grid"), field="off_grid", block_type=block_type
            ),
            visible_geometry_may_be_off_grid=_parse_bool(
                row.get("visible_geometry_may_be_off_grid"),
                field="visible_geometry_may_be_off_grid",
                block_type=block_type,
            ),
            validate_with_anchor_size=_parse_bool(
                row.get("validate_with_anchor_size"),
                field="validate_with_anchor_size",
                block_type=block_type,
            ),
        )
        build_policy = CatalogBuildPolicy(
            solver_enabled=_parse_bool(
                row.get("current_solver_enabled"),
                field="current_solver_enabled",
                block_type=block_type,
            ),
            attachment_only=_parse_bool(
                row.get("attachment_only"),
                field="attachment_only",
                block_type=block_type,
            ),
            requires_attachment_check=_parse_bool(
                row.get("requires_attachment_check"),
                field="requires_attachment_check",
                block_type=block_type,
            ),
            functional_role=_text(row, "functional_role"),
            functional_attachment_enabled=_parse_bool(
                row.get("functional_attachment_enabled"),
                field="functional_attachment_enabled",
                block_type=block_type,
            ),
            placement_mode=_text(row, "placement_mode"),
            counts_as_structural_coverage=_parse_bool(
                row.get("counts_as_structural_coverage"),
                field="counts_as_structural_coverage",
                block_type=block_type,
            ),
            attachment_candidate_rule=_text(row, "attachment_candidate_rule"),
            stackability=_text(row, "stackability"),
            support_quality_by_axis=_text(row, "support_quality_by_axis"),
            bulk_fill_axes=_text(row, "bulk_fill_axes"),
            stability_class=_text(row, "stability_class"),
            voxel_operation=_text(row, "voxel_operation"),
            requires_voxel_removal=_text(row, "requires_voxel_removal"),
            insertion_policy=_text(row, "insertion_policy"),
            interface_rule=_text(row, "interface_rule"),
            orientation_policy=_text(row, "orientation_policy"),
            canonical_orientation_policy=_text(
                row, "canonical_orientation_policy"
            ),
            replacement_policy=_text(row, "replacement_policy"),
            source_segment_required=_parse_bool(
                row.get("source_segment_required"),
                field="source_segment_required",
                block_type=block_type,
            ),
            source_segment_policy=_text(row, "source_segment_policy"),
            allowed_source_segment_policy=_text(
                row, "allowed_source_segment_policy"
            ),
            geometry_preservation_policy=_text(
                row, "geometry_preservation_policy"
            ),
            placement_origin_policy=_text(row, "placement_origin_policy"),
            source_geometry_anchor=_text(row, "source_geometry_anchor"),
            shape_preservation_notes=_text(row, "shape_preservation_notes"),
            prohibited_uses=_semicolon_tokens(row.get("prohibited_uses")),
            do_not_resize_to_source_bbox=_parse_bool(
                row.get("do_not_resize_to_source_bbox"),
                field="do_not_resize_to_source_bbox",
                block_type=block_type,
            ),
            catalog_validation_rule=_text(row, "catalog_validation_rule"),
        )
        motion = CatalogMotionSpec(
            motion_type=_text(row, "motion_type"),
            motion_axis=_text(row, "motion_axis"),
            angle_limits=_text(row, "angle_limits"),
            anchor_connection_type=_text(row, "anchor_connection_type"),
            functional_motion=_text(row, "functional_motion"),
            local_axle_axis=_text(row, "local_axle_axis"),
            world_axle_axis_policy=_text(row, "world_axle_axis_policy"),
            wheel_disc_plane_policy=_text(row, "wheel_disc_plane_policy"),
            wheel_vertical_axis_policy=_text(row, "wheel_vertical_axis_policy"),
            wheel_dimension_convention=_text(row, "wheel_dimension_convention"),
            wheel_axle_axis_default=_text(row, "wheel_axle_axis_default"),
            attachment_side_policy=_text(row, "attachment_side_policy"),
            ground_contact_policy=_text(row, "ground_contact_policy"),
        )
        definitions.append(
            CatalogBlockDefinition(
                block_type=block_type,
                category=category,
                allowed_dimensions=dimensions,
                structural_eligible=structural_eligible,
                packing_priority=priority,
                display_color=color,
                male_faces=_parse_face_tokens(
                    _first_present(row, _MALE_FACE_ALIASES)
                ),
                female_faces=_parse_face_tokens(
                    _first_present(row, _FEMALE_FACE_ALIASES)
                ),
                allowed_rotations=rotations,
                geometry=geometry,
                build_policy=build_policy,
                motion=motion,
                source_name=source_name,
                source_row=source_row,
                raw_metadata={
                    key: _json_safe(value) for key, value in row.items()
                },
            )
        )

    if not definitions:
        raise CatalogConfigurationError(
            f"No block definition rows were found in {path}"
        )

    seen: dict[str, CatalogBlockDefinition] = {}
    for item in definitions:
        if item.block_type in seen:
            previous = seen[item.block_type]
            raise CatalogConfigurationError(
                f"Duplicate block ID {item.block_type!r} in "
                f"{previous.source_name}:{previous.source_row} and "
                f"{item.source_name}:{item.source_row}"
            )
        seen[item.block_type] = item

    return BlockCatalog(
        source_path=path.resolve(),
        source_sha256=sha256_file(path),
        definitions=tuple(definitions),
        sources_read=(source_name,),
        header_rows={source_name: header_row},
        schema_version=schema_version,
        columns=tuple(headers),
    )


def load_catalog_block_ids(path: str | Path) -> set[str]:
    """Load catalog block ids.
    
    :param path: Filesystem path used by the operation.
    :type path: str | Path
    :returns: The loaded data.
    :rtype: set[str]
    """
    return load_block_catalog(path).block_ids


def validate_inventory_against_catalog(
    inventory_block_types: Iterable[str], catalog_block_ids: set[str]
) -> None:
    """Validate inventory against catalog.
    
    :param inventory_block_types: The inventory block types value.
    :type inventory_block_types: Iterable[str]
    :param catalog_block_ids: Identifiers for the catalog block records.
    :type catalog_block_ids: set[str]
    """
    unknown = sorted(set(inventory_block_types) - set(catalog_block_ids))
    if unknown:
        raise CatalogConfigurationError(
            "Inventory contains block types missing from block_definitions.csv: "
            + ", ".join(unknown)
        )


def validate_used_block_colors(
    used_block_types: Iterable[str], catalog: BlockCatalog
) -> None:
    """Validate used block colors.
    
    :param used_block_types: The used block types value.
    :type used_block_types: Iterable[str]
    :param catalog: Block catalog data used by the operation.
    :type catalog: BlockCatalog
    """
    missing = sorted(
        block_type
        for block_type in set(used_block_types)
        if not catalog.by_type.get(block_type)
        or not catalog.by_type[block_type].display_color
    )
    if missing:
        raise CatalogConfigurationError(
            "Used block types have no catalog visualization color: " + ", ".join(missing)
        )
