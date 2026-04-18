"""
KidSpark AI — Step D: Teacher Lesson Plan Generator
Owner: Developer B

This agent generates a complete Teacher Lesson Plan following the canonical
Kid Spark structure. It runs in parallel with the Student Guide generator
(Step E).

RESPONSIBILITIES:
  - Take LessonSpec, BuildTargetProfile, and EvidencePack as input
  - Generate a TeacherLessonPlan with sections matching the canonical structure:
      * overview (lesson summary, grade, duration, storybook)
      * objectives (2-3 "I can..." statements)
      * vocabulary (target words with definitions and phonics cues)
      * anticipatory_set (hook activity)
      * step_read (reading activity with discussion prompts)
      * step_learn_explore (vocabulary and concept exploration)
      * step_invent (building activity with step-by-step teacher guidance)
      * closure_reflection (sharing, reflection questions)
  - Reference specific Kid Spark pieces by name in the build steps
  - Include teacher prompts and scaffolding suggestions from KB evidence
  - Align with the standards listed in LessonSpec.standards_alignment

INPUTS:
  - LessonSpec + BuildTargetProfile + EvidencePack

OUTPUTS:
  - TeacherLessonPlan (Pydantic model, see models/schemas.py)

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.3, "Step D — Teacher Plan"
"""
