"""Typed data models for block-catalog records.

The models represent catalog geometry, connectors, policy fields, colors, and
functional metadata after schema validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

Dimension = tuple[int, int, int]


@dataclass(frozen=True)
class CatalogGeometrySpec:
    anchor_dimensions: Dimension | None = None
    representation: str = ""
    status: str = ""
    visual_shape: str = ""
    visible_dimensions: Dimension | None = None
    visible_layer_spec: str = ""
    anchor_layer_spec: str = ""
    clearance_dimensions: Dimension | None = None
    clearance_layer_spec: str = ""
    coordinate_frame: str = ""
    off_grid: bool = False
    visible_geometry_may_be_off_grid: bool = False
    validate_with_anchor_size: bool = False

    def to_summary(self) -> dict[str, Any]:
        """Convert the object to summary.
        
        :returns: The result produced by the function.
        :rtype: dict[str, Any]
        """
        return {
            "anchor_dimensions": list(self.anchor_dimensions) if self.anchor_dimensions else None,
            "representation": self.representation,
            "status": self.status,
            "visual_shape": self.visual_shape,
            "visible_dimensions": list(self.visible_dimensions) if self.visible_dimensions else None,
            "visible_layer_spec": self.visible_layer_spec,
            "anchor_layer_spec": self.anchor_layer_spec,
            "clearance_dimensions": (
                list(self.clearance_dimensions) if self.clearance_dimensions else None
            ),
            "clearance_layer_spec": self.clearance_layer_spec,
            "coordinate_frame": self.coordinate_frame,
            "off_grid": self.off_grid,
            "visible_geometry_may_be_off_grid": self.visible_geometry_may_be_off_grid,
            "validate_with_anchor_size": self.validate_with_anchor_size,
        }


@dataclass(frozen=True)
class CatalogBuildPolicy:
    solver_enabled: bool = False
    attachment_only: bool = False
    requires_attachment_check: bool = False
    functional_role: str = ""
    functional_attachment_enabled: bool = False
    placement_mode: str = ""
    counts_as_structural_coverage: bool = False
    attachment_candidate_rule: str = ""
    stackability: str = ""
    support_quality_by_axis: str = ""
    bulk_fill_axes: str = ""
    stability_class: str = ""
    voxel_operation: str = ""
    requires_voxel_removal: str = ""
    insertion_policy: str = ""
    interface_rule: str = ""
    orientation_policy: str = ""
    canonical_orientation_policy: str = ""
    replacement_policy: str = ""
    source_segment_required: bool = False
    source_segment_policy: str = ""
    allowed_source_segment_policy: str = ""
    geometry_preservation_policy: str = ""
    placement_origin_policy: str = ""
    source_geometry_anchor: str = ""
    shape_preservation_notes: str = ""
    prohibited_uses: tuple[str, ...] = ()
    do_not_resize_to_source_bbox: bool = False
    catalog_validation_rule: str = ""

    def to_summary(self) -> dict[str, Any]:
        """Convert the object to summary.
        
        :returns: The result produced by the function.
        :rtype: dict[str, Any]
        """
        return {
            "solver_enabled": self.solver_enabled,
            "attachment_only": self.attachment_only,
            "requires_attachment_check": self.requires_attachment_check,
            "functional_role": self.functional_role,
            "functional_attachment_enabled": self.functional_attachment_enabled,
            "placement_mode": self.placement_mode,
            "counts_as_structural_coverage": self.counts_as_structural_coverage,
            "attachment_candidate_rule": self.attachment_candidate_rule,
            "stackability": self.stackability,
            "support_quality_by_axis": self.support_quality_by_axis,
            "bulk_fill_axes": self.bulk_fill_axes,
            "stability_class": self.stability_class,
            "voxel_operation": self.voxel_operation,
            "requires_voxel_removal": self.requires_voxel_removal,
            "insertion_policy": self.insertion_policy,
            "interface_rule": self.interface_rule,
            "orientation_policy": self.orientation_policy,
            "canonical_orientation_policy": self.canonical_orientation_policy,
            "replacement_policy": self.replacement_policy,
            "source_segment_required": self.source_segment_required,
            "source_segment_policy": self.source_segment_policy,
            "allowed_source_segment_policy": self.allowed_source_segment_policy,
            "geometry_preservation_policy": self.geometry_preservation_policy,
            "placement_origin_policy": self.placement_origin_policy,
            "source_geometry_anchor": self.source_geometry_anchor,
            "shape_preservation_notes": self.shape_preservation_notes,
            "prohibited_uses": list(self.prohibited_uses),
            "do_not_resize_to_source_bbox": self.do_not_resize_to_source_bbox,
            "catalog_validation_rule": self.catalog_validation_rule,
        }


@dataclass(frozen=True)
class CatalogMotionSpec:
    motion_type: str = ""
    motion_axis: str = ""
    angle_limits: str = ""
    anchor_connection_type: str = ""
    functional_motion: str = ""
    local_axle_axis: str = ""
    world_axle_axis_policy: str = ""
    wheel_disc_plane_policy: str = ""
    wheel_vertical_axis_policy: str = ""
    wheel_dimension_convention: str = ""
    wheel_axle_axis_default: str = ""
    attachment_side_policy: str = ""
    ground_contact_policy: str = ""

    def to_summary(self) -> dict[str, str]:
        """Convert the object to summary.
        
        :returns: The result produced by the function.
        :rtype: dict[str, str]
        """
        return {
            "motion_type": self.motion_type,
            "motion_axis": self.motion_axis,
            "angle_limits": self.angle_limits,
            "anchor_connection_type": self.anchor_connection_type,
            "functional_motion": self.functional_motion,
            "local_axle_axis": self.local_axle_axis,
            "world_axle_axis_policy": self.world_axle_axis_policy,
            "wheel_disc_plane_policy": self.wheel_disc_plane_policy,
            "wheel_vertical_axis_policy": self.wheel_vertical_axis_policy,
            "wheel_dimension_convention": self.wheel_dimension_convention,
            "wheel_axle_axis_default": self.wheel_axle_axis_default,
            "attachment_side_policy": self.attachment_side_policy,
            "ground_contact_policy": self.ground_contact_policy,
        }


@dataclass(frozen=True)
class CatalogBlockDefinition:
    block_type: str
    category: str
    allowed_dimensions: tuple[Dimension, ...]
    structural_eligible: bool
    packing_priority: int
    display_color: str
    male_faces: tuple[str, ...] = ()
    female_faces: tuple[str, ...] = ()
    allowed_rotations: tuple[str, ...] = ()
    geometry: CatalogGeometrySpec = field(default_factory=CatalogGeometrySpec)
    build_policy: CatalogBuildPolicy = field(default_factory=CatalogBuildPolicy)
    motion: CatalogMotionSpec = field(default_factory=CatalogMotionSpec)
    source_name: str = ""
    source_row: int = 0
    raw_metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def source_sheet(self) -> str:
        """Backward-compatible alias retained for older API consumers."""
        return self.source_name

    @property
    def maximum_volume(self) -> int:
        """Return the maximum volume value.
        
        :returns: The result produced by the function.
        :rtype: int
        """
        if not self.allowed_dimensions:
            return 0
        return max(x * y * z for x, y, z in self.allowed_dimensions)

    def to_summary(self) -> dict[str, Any]:
        """Convert the object to summary.
        
        :returns: The result produced by the function.
        :rtype: dict[str, Any]
        """
        return {
            "block_type": self.block_type,
            "category": self.category,
            "allowed_dimensions": [list(value) for value in self.allowed_dimensions],
            "structural_eligible": self.structural_eligible,
            "packing_priority": self.packing_priority,
            "display_color": self.display_color,
            "male_faces": list(self.male_faces),
            "female_faces": list(self.female_faces),
            "allowed_rotations": list(self.allowed_rotations),
            "geometry": self.geometry.to_summary(),
            "build_policy": self.build_policy.to_summary(),
            "motion": self.motion.to_summary(),
            "source_name": self.source_name,
            "source_sheet": self.source_sheet,
            "source_row": self.source_row,
        }


@dataclass(frozen=True)
class BlockCatalog:
    source_path: Path
    source_sha256: str
    definitions: tuple[CatalogBlockDefinition, ...]
    sources_read: tuple[str, ...]
    header_rows: dict[str, int]
    schema_version: str = "legacy-compatible"
    columns: tuple[str, ...] = ()

    @property
    def sheets_read(self) -> tuple[str, ...]:
        """Backward-compatible alias retained for older API consumers."""
        return self.sources_read

    @property
    def by_type(self) -> dict[str, CatalogBlockDefinition]:
        """Return the by type value.
        
        :returns: The result produced by the function.
        :rtype: dict[str, CatalogBlockDefinition]
        """
        return {item.block_type: item for item in self.definitions}

    @property
    def block_ids(self) -> set[str]:
        """Return block ids.
        
        :returns: The result produced by the function.
        :rtype: set[str]
        """
        return set(self.by_type)

    @property
    def colors(self) -> dict[str, str]:
        """Return the colors value.
        
        :returns: The result produced by the function.
        :rtype: dict[str, str]
        """
        return {
            item.block_type: item.display_color
            for item in self.definitions
            if item.display_color
        }

    @property
    def structural_definitions(self) -> tuple[CatalogBlockDefinition, ...]:
        """Return structural definitions.
        
        :returns: The result produced by the function.
        :rtype: tuple[CatalogBlockDefinition, ...]
        """
        return tuple(
            sorted(
                (item for item in self.definitions if item.structural_eligible),
                key=lambda item: (-item.packing_priority, item.block_type),
            )
        )

    def to_summary(self) -> dict[str, Any]:
        """Convert the object to summary.
        
        :returns: The result produced by the function.
        :rtype: dict[str, Any]
        """
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "schema_version": self.schema_version,
            "columns": list(self.columns),
            "sources_read": list(self.sources_read),
            "sheets_read": list(self.sheets_read),
            "header_rows": dict(self.header_rows),
            "block_count": len(self.definitions),
            "structural_block_count": len(self.structural_definitions),
            "block_ids": sorted(self.block_ids),
        }


# Deprecated compatibility alias for callers written before the CSV migration.
WorkbookCatalog = BlockCatalog
