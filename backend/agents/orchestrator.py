"""
KidSpark AI — Pipeline Orchestrator
Owner: Developer B

This module manages the full pipeline execution across all phases. It is split
into four entry points, called at different times during the session lifecycle.

RESPONSIBILITIES:

  Phase 1 — Storybook Analysis (automatic, on upload):
    analyze_storybook(storybook_text, session) -> StoryAnalysis
    - Runs story_analysis agent
    - Stores result in session.storybook_analysis

  Phase 2 — Teacher Consultation (multi-turn, called per message):
    handle_consultation_message(message, session) -> ConsultationResponse
    - Runs consultation agent with KB tool access
    - Appends to session.teacher_messages

    finalize_consultation(session) -> ConsultationSummary
    - Called when teacher approves via POST /approve-plan
    - Produces final ConsultationSummary
    - Transitions session.phase to "block_awareness"

  Phase 3 — Block Awareness (1-2 turns):
    handle_block_awareness_message(message, session) -> BlockAwarenessResponse
    - Runs block_awareness agent with catalog context
    - Stores BlockRequirements in session

  Phase 4 — Generation Pipeline (automated, no teacher input):
    run_generation_pipeline(session) -> LessonPackage
    - Retrieves evidence from KB
    - Runs Steps B through F in sequence (D+E in parallel)
    - Returns complete LessonPackage

  The API layer (api/sessions.py) routes incoming requests to the correct
  orchestrator function based on session.phase.

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.3, orchestrator code example
"""
