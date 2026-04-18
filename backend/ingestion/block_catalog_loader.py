"""
KidSpark AI — Block Catalog Loader
Owner: Developer A

This module populates the block_catalog table with Kid Spark piece definitions.
The block catalog is used by the Block Awareness Agent (Dev B) to map build
artifacts to specific physical pieces.

RESPONSIBILITIES:
  - Define or load the full Kid Spark Early Inventors STEM Lab piece catalog
  - For each piece type, store:
      * piece_type: cube | half_circle | wheel | axle | flat_connector | angle_connector
      * piece_name: human-readable name (e.g., "Cube Block (Windowed)")
      * colors_available: list of available colors
      * quantity_per_kit: how many come in a standard kit
      * connection_mechanism: how pieces connect (e.g., "triangular prism connector")
      * supports_rotation: can this piece enable spinning motion?
      * supports_pivot: can this piece enable hinge/pivot motion?
      * supports_axle: can this piece hold an axle through it?
      * structural_role: body | connector | articulation | wheel
      * dimensions: width, height, depth in grid units
      * description: human-readable description of the piece
  - This may be loaded from a JSON/CSV seed file or defined programmatically

INPUTS:
  - Kid Spark piece catalog data (JSON seed file or hardcoded definitions)

OUTPUTS:
  - BlockCatalog records in the database

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.1 (block_catalog table)
"""
