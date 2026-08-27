"""
KidSpark AI — Step B: Outline Planner Agent
Owner: Developer B

This agent takes the ConsultationSummary, BlockRequirements, and EvidencePack
and produces a LessonSpec — the shared internal blueprint from which both the
Teacher Plan and Student Guide are rendered.

RESPONSIBILITIES:
  - Synthesize the consultation results, block requirements, and KB evidence
    into a coherent lesson outline
  - Produce a LessonSpec with:
      * theme, objectives, lesson_flow (list of TimeBlocks)
      * teacher_prompts, student_steps, materials
      * standards_alignment (mapped from policy rules in EvidencePack)
      * build_target_profile_ref
  - The lesson flow should follow the canonical structure:
      Step 01: Read (~10 min)
      Step 02: Learn & Explore (~10 min)
      Step 03: Invent (~10 min)
      Closure & Reflection (~5 min)
  - Total duration must match the teacher's specified duration

INPUTS:
  - ConsultationSummary + BlockRequirements + EvidencePack

OUTPUTS:
  - LessonSpec (Pydantic model, see models/schemas.py)

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.3, "Step B — Outline Planner"
"""
