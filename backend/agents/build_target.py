"""
KidSpark AI — Step C: Build Target Agent
Owner: Developer B

This agent produces a BuildTargetProfile by combining the LessonSpec with the
BlockRequirements from the Block Awareness Agent. Because the block awareness
phase has already mapped parts to Kid Spark pieces and identified articulation,
the Build Target Profile is richer than a simple label.

RESPONSIBILITIES:
  - Take the LessonSpec and BlockRequirements as input
  - Produce a BuildTargetProfile with:
      * label (e.g., "flying delivery vehicle")
      * required_parts (with piece types from BlockRequirements)
      * part_descriptions (human-readable for teacher/student materials)
      * exemplar_references (similar builds from KB evidence)
      * teacher_build_prompts (guidance for the teacher during build time)
      * connection_hint (how key pieces connect together)
  - Full topology-aware 3D build plans remain Phase 2

INPUTS:
  - LessonSpec (from outline_planner.py)
  - BlockRequirements (from block_awareness.py)

OUTPUTS:
  - BuildTargetProfile (Pydantic model, see models/schemas.py)

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.3, "Step C — Build Target"
"""
