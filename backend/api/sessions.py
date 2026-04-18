"""
KidSpark AI — Session API Router
Owner: Developer B

This module defines the FastAPI router for all runtime session endpoints.
Sessions follow a phased model: consultation -> block_awareness -> generation
-> refinement -> complete.

ENDPOINTS TO IMPLEMENT:

  POST /api/v1/sessions
    - Create a new teacher session
    - Returns session_id, initial phase is "consultation"

  POST /api/v1/sessions/{id}/upload
    - Upload a storybook PDF/DOCX
    - Triggers automatic Step A (storybook analysis)
    - Parses storybook text and runs story_analysis agent
    - Returns StoryAnalysis summary

  POST /api/v1/sessions/{id}/message
    - Send a teacher message
    - Routes to the appropriate agent based on session.phase:
        * phase "consultation" -> consultation agent
        * phase "block_awareness" -> block awareness agent
    - Returns agent response + progress indicators

  GET /api/v1/sessions/{id}/consultation
    - Get current consultation state and progress
    - Returns areas_covered, areas_remaining, current_summary

  POST /api/v1/sessions/{id}/approve-plan
    - Teacher approves the consultation direction
    - Calls finalize_consultation() in orchestrator
    - Transitions session to "block_awareness" phase
    - Returns ConsultationSummary

  POST /api/v1/sessions/{id}/generate
    - Trigger the generation pipeline (Steps B-F)
    - Only available when phase is "generation" (after block awareness completes)
    - Runs the full pipeline via orchestrator.run_generation_pipeline()
    - Returns complete LessonPackage

  GET /api/v1/sessions/{id}/package
    - Get the generated LessonPackage (after generation is complete)

  POST /api/v1/sessions/{id}/refine
    - Submit feedback and re-generate (up to 3 iterations)
    - Takes feedback text, re-runs generation with adjustments

  GET /api/v1/sessions/{id}/trace
    - Get the retrieval evidence trace for the current package
    - Returns which KB nodes were used and their relevance scores

  GET /api/v1/blocks/catalog
    - Get the Kid Spark block catalog (for UI display or debugging)

  POST /api/v1/retrieve
    - Direct retrieval query (for debugging / testing)

  GET /api/v1/nodes/{node_id}
    - Inspect a specific knowledge node (for debugging)

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 10, "Runtime APIs"
"""
