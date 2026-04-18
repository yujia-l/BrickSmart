"""
KidSpark AI — Step F: Validator Agent
Owner: Developer B

This agent validates the generated lesson package against structural
requirements, standards alignment, and build coherence.

RESPONSIBILITIES:
  - Take the TeacherLessonPlan, StudentActivityGuide, LessonSpec, and
    PolicyRules as input
  - Run validation checks:
      * structure_check: Do both documents follow the canonical section structure?
      * standards_alignment_check: Are the claimed standards actually reflected
        in the content?
      * build_coherence_check: Do the build instructions in both documents
        reference the same artifact and pieces? Are the BlockRequirements
        consistently reflected?
      * duration_check: Do the time blocks add up to the specified duration?
      * vocabulary_check: Are the target vocabulary words used consistently?
  - Produce a ValidationResult with:
      * is_valid: bool (overall pass/fail)
      * warnings: list of specific issues found
      * Per-check results (structure, standards, build, duration, vocabulary)

INPUTS:
  - TeacherLessonPlan + StudentActivityGuide + LessonSpec + PolicyRules

OUTPUTS:
  - ValidationResult (Pydantic model, see models/schemas.py)

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.3, "Step F — Validator"
"""
