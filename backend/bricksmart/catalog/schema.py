"""Block-catalog schema definition and validation helpers.

This module defines the expected BrickSmart catalog contract and reports missing,
extra, or malformed catalog fields.
"""

from __future__ import annotations

from collections.abc import Sequence

from bricksmart.exceptions import CatalogConfigurationError

CATALOG_SCHEMA_VERSION = "bricksmart-block-catalog-2"

# The production catalog is intentionally explicit. The first 36 columns retain
# the runtime vocabulary introduced during the CSV migration; the remaining
# columns preserve generic model-building rules from the verified workbook.
CATALOG_COLUMNS: tuple[str, ...] = (
    "block_family",
    "color",
    "category",
    "geometry_size",
    "anchor_size",
    "geometry_representation",
    "geometry_status",
    "visual_shape",
    "primary_male_faces",
    "primary_female_faces",
    "allowed_orientations",
    "default_packing_priority",
    "current_solver_enabled",
    "attachment_only",
    "off_grid",
    "requires_attachment_check",
    "functional_role",
    "functional_attachment_enabled",
    "placement_mode",
    "motion_type",
    "motion_axis",
    "angle_limits",
    "anchor_connection_type",
    "functional_motion",
    "counts_as_structural_coverage",
    "attachment_candidate_rule",
    "visible_geometry_size",
    "visible_geometry_layer_spec",
    "anchor_geometry_layer_spec",
    "clearance_reservation_size",
    "clearance_reservation_layer_spec",
    "geometry_coordinate_frame",
    "local_axle_axis",
    "world_axle_axis_policy",
    "wheel_disc_plane_policy",
    "wheel_vertical_axis_policy",
    "stackability",
    "support_quality_by_axis",
    "bulk_fill_axes",
    "stability_class",
    "voxel_operation",
    "requires_voxel_removal",
    "insertion_policy",
    "interface_rule",
    "orientation_policy",
    "canonical_orientation_policy",
    "replacement_policy",
    "source_segment_required",
    "source_segment_policy",
    "allowed_source_segment_policy",
    "visible_geometry_may_be_off_grid",
    "validate_with_anchor_size",
    "geometry_preservation_policy",
    "placement_origin_policy",
    "source_geometry_anchor",
    "shape_preservation_notes",
    "prohibited_uses",
    "do_not_resize_to_source_bbox",
    "wheel_dimension_convention",
    "wheel_axle_axis_default",
    "attachment_side_policy",
    "ground_contact_policy",
    "catalog_validation_rule",
)

CORE_RUNTIME_COLUMNS: tuple[str, ...] = CATALOG_COLUMNS[:36]
RICH_SCHEMA_MARKERS: frozenset[str] = frozenset(
    {"geometry_representation", "geometry_status", "catalog_validation_rule"}
)

GEOMETRY_STATUSES: frozenset[str] = frozenset({"verified", "partial", "missing"})
GEOMETRY_REPRESENTATIONS: frozenset[str] = frozenset(
    {
        "solid_box",
        "mechanical_block_envelope",
        "layered_wheel",
        "beam_envelope",
        "curved_beam_envelope",
        "angled_part_envelope",
        "u_shape_envelope",
        "unresolved",
    }
)
CANONICAL_FACE_TOKENS: frozenset[str] = frozenset(
    {"+X", "-X", "+Y", "-Y", "+Z", "-Z", "+N", "-N"}
)
CANONICAL_ORIENTATION_TOKENS: frozenset[str] = frozenset({"X", "Y", "Z"})


def is_rich_catalog_schema(headers: Sequence[str]) -> bool:
    """Return whether rich catalog schema.
    
    :param headers: The headers value.
    :type headers: Sequence[str]
    :returns: ``True`` when the condition is satisfied; otherwise ``False``.
    :rtype: bool
    """
    return bool(RICH_SCHEMA_MARKERS.intersection(headers))


def validate_rich_catalog_headers(headers: Sequence[str]) -> None:
    """Validate rich catalog headers.
    
    :param headers: The headers value.
    :type headers: Sequence[str]
    """
    actual = tuple(headers)
    if actual == CATALOG_COLUMNS:
        return

    missing = [column for column in CATALOG_COLUMNS if column not in actual]
    unexpected = [column for column in actual if column not in CATALOG_COLUMNS]
    order_mismatch = not missing and not unexpected and actual != CATALOG_COLUMNS

    details: list[str] = []
    if missing:
        details.append("missing=" + ", ".join(missing))
    if unexpected:
        details.append("unexpected=" + ", ".join(unexpected))
    if order_mismatch:
        details.append("column order does not match the documented catalog contract")

    raise CatalogConfigurationError(
        "The production block catalog does not match "
        f"{CATALOG_SCHEMA_VERSION}: " + "; ".join(details)
    )


def _comma_tokens(value: object) -> tuple[str, ...]:
    """Return the comma tokens value.
    
    :param value: Value used by the operation.
    :type value: object
    :returns: The result produced by the function.
    :rtype: tuple[str, ...]
    """
    return tuple(
        token.strip()
        for token in str(value or "").split(",")
        if token.strip()
    )


def _catalog_bool(value: object) -> bool:
    """Return whether catalog bool.
    
    :param value: Value used by the operation.
    :type value: object
    :returns: The result produced by the function.
    :rtype: bool
    """
    normalized = str(value or "").strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no", ""}:
        return False
    raise CatalogConfigurationError(f"Invalid catalog boolean value: {value!r}")


def validate_rich_catalog_row(
    row: dict[str, object], *, source_name: str, source_row: int
) -> None:
    """Validate rich catalog row.
    
    :param row: Row record to process.
    :type row: dict[str, object]
    :param source_name: The source name value.
    :type source_name: str
    :param source_row: The source row value.
    :type source_row: int
    """
    block_family = str(row.get("block_family") or "").strip()
    location = f"{source_name}:{source_row} ({block_family or 'unknown block'})"

    status = str(row.get("geometry_status") or "").strip()
    if status not in GEOMETRY_STATUSES:
        raise CatalogConfigurationError(
            f"Invalid geometry_status={status!r} at {location}"
        )

    representation = str(row.get("geometry_representation") or "").strip()
    if representation not in GEOMETRY_REPRESENTATIONS:
        raise CatalogConfigurationError(
            f"Invalid geometry_representation={representation!r} at {location}"
        )

    male_faces = _comma_tokens(row.get("primary_male_faces"))
    female_faces = _comma_tokens(row.get("primary_female_faces"))
    invalid_faces = sorted(
        (set(male_faces) | set(female_faces)) - CANONICAL_FACE_TOKENS
    )
    if invalid_faces:
        raise CatalogConfigurationError(
            f"Invalid connector face token(s) at {location}: "
            + ", ".join(invalid_faces)
        )

    orientations = _comma_tokens(row.get("allowed_orientations"))
    invalid_orientations = sorted(
        set(orientations) - CANONICAL_ORIENTATION_TOKENS
    )
    if invalid_orientations:
        raise CatalogConfigurationError(
            f"Invalid orientation token(s) at {location}: "
            + ", ".join(invalid_orientations)
        )

    enabled = _catalog_bool(row.get("current_solver_enabled"))
    geometry_size = str(row.get("geometry_size") or "").strip()
    if status == "missing":
        if enabled or geometry_size:
            raise CatalogConfigurationError(
                f"Missing geometry must be disabled and have a blank geometry_size at {location}"
            )
        if _catalog_bool(row.get("validate_with_anchor_size")):
            raise CatalogConfigurationError(
                f"Missing geometry cannot request anchor-size validation at {location}"
            )

    category = str(row.get("category") or "").strip()
    if category == "structural_block":
        if status != "verified":
            raise CatalogConfigurationError(
                f"Structural geometry must be verified at {location}"
            )
        if not _catalog_bool(row.get("counts_as_structural_coverage")):
            raise CatalogConfigurationError(
                f"Structural block must count as structural coverage at {location}"
            )
        if not str(row.get("default_packing_priority") or "").strip():
            raise CatalogConfigurationError(
                f"Structural block requires default_packing_priority at {location}"
            )
