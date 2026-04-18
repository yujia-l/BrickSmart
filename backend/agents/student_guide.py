"""
KidSpark AI — Step E: Student Activity Guide Generator
Owner: Developer B

This agent generates a Student Activity Guide — the student-facing companion
to the Teacher Lesson Plan. It runs in parallel with the Teacher Plan
generator (Step D).

RESPONSIBILITIES:
  - Take LessonSpec, BuildTargetProfile, and EvidencePack as input
  - Generate a StudentActivityGuide with age-appropriate pages:
      * Reading activity page (story discussion prompts)
      * Vocabulary page (target words with visual cues)
      * Parts diagram page (labeled diagram of the build artifact)
      * Building activity page (simplified step-by-step build instructions)
      * Reflection page (drawing/writing space, sharing prompts)
  - Use simple language appropriate for the grade band (Pre-K through 1st Grade)
  - Reference the specific Kid Spark pieces students will use
  - Include partner collaboration prompts (aligned with SEL focus)

INPUTS:
  - LessonSpec + BuildTargetProfile + EvidencePack

OUTPUTS:
  - StudentActivityGuide (Pydantic model, see models/schemas.py)

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.3, "Step E — Student Guide"
"""
