"""
KidSpark AI — Block Awareness Agent (Kid Spark Piece Catalog)
Owner: Developer B

This agent determines what Kid Spark physical pieces are needed for the
agreed build artifact, with focus on movable and articulated parts.

PURPOSE:
  The teacher knows what they want students to build, but may not know which
  Kid Spark pieces enable specific movements (spinning, pivoting, rolling).
  This agent bridges that gap by asking targeted questions about articulation
  and mapping answers to the Kid Spark block catalog.

RESPONSIBILITIES:
  - Load the Kid Spark block catalog from the database
  - Given the ConsultationSummary (agreed artifact and its parts), identify
    which parts could potentially move
  - Ask the teacher about movement preferences:
      * "Should the propeller spin?"
      * "Should the wings flap or stay fixed?"
      * "Should it have rolling wheels?"
  - Map each movement type to specific Kid Spark piece types:
      * Spinning (continuous rotation) -> wheel/axle piece
      * Pivoting (limited arc) -> angle connector
      * Rolling (ground movement) -> wheel pieces + axle
      * Static structure -> cube blocks (windowed)
      * Bridging (flat connection) -> flat connector
  - Produce a BlockRequirements spec listing all parts, their movement type,
    suggested pieces, and connector types needed

INPUTS:
  - ConsultationSummary (from consultation agent)
  - Block catalog (from database)
  - Teacher messages about movement preferences

OUTPUTS:
  - BlockRequirements (Pydantic model, see models/schemas.py)

AGENT SETUP:
  - Pydantic AI Agent with result_type=BlockRequirements, deps_type=BlockAwarenessDeps
  - Block catalog loaded as context dependency
  - 1-2 turns of interaction with teacher, then produces final output

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.3, "Block Awareness Agent"
"""
