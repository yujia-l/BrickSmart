"""
KidSpark AI — Pydantic v2 Schemas
Owner: SHARED (Dev A and Dev B both import from here)

This file defines ALL Pydantic data models used across the system. It is the
single source of truth for data contracts between the ingestion pipeline and
the runtime/agent pipeline.

Models to implement (see KIDSPARK_TECHNICAL_SPEC.md Section 11 for full details):

STEP A OUTPUT:
  - StoryAnalysis: Automatic storybook analysis result. Fields include title,
    characters, settings, key_events, themes, buildable_objects,
    vocabulary_opportunities, sel_angles.

CONSULTATION AGENT OUTPUT:
  - ConsultationSummary: Result of the multi-turn teacher consultation loop.
    Fields include agreed_theme, agreed_artifact, artifact_parts,
    learning_objectives, grade_band, duration_minutes, literacy_focus,
    sel_focus, teacher_preferences, kb_evidence_used, storybook_title.

BLOCK AWARENESS AGENT OUTPUT:
  - ArtifactPart: Single part of the build artifact with movement type and
    suggested Kid Spark pieces.
  - BlockRequirements: Full block awareness result. Fields include
    artifact_label, parts (list of ArtifactPart), connector_types_needed,
    total_cube_blocks, total_special_pieces, articulation_summary.

BLOCK CATALOG:
  - KidSparkPiece: A single Kid Spark block/piece definition. Fields include
    piece_type, piece_name, colors_available, quantity_per_kit,
    connection_mechanism, supports_rotation, supports_pivot, supports_axle,
    structural_role, dimensions, description.

GENERATION PIPELINE:
  - TimeBlock: A single time block in the lesson flow (activity, duration, description).
  - LessonSpec: The shared internal blueprint (Step B output). Fields include
    theme, objectives, lesson_flow, teacher_prompts, student_steps, materials,
    standards_alignment, build_target_profile_ref, validation_flags.
  - BuildTargetProfile: Build target description (Step C output). Fields include
    label, required_parts, part_descriptions, exemplar_references,
    teacher_build_prompts, connection_hint.
  - TeacherLessonPlan: Full teacher plan (Step D output) with sections matching
    the canonical structure (overview, objectives, vocabulary, anticipatory_set,
    step_read, step_learn_explore, step_invent, closure_reflection).
  - StudentActivityGuide: Student-facing guide (Step E output) with pages
    matching the canonical structure.
  - ValidationResult: Validation output (Step F). Fields include is_valid,
    warnings, structure_check, standards_alignment_check, build_coherence_check.

RETRIEVAL:
  - EvidencePack: Assembled retrieval results. Fields include teacher_cards,
    student_cards, visual_cards, policy_cards, trace.
  - TraceEntry: A single retrieval trace entry (node_id, score, bundle_id).

LESSON PACKAGE:
  - LessonPackage: The complete output — teacher_plan, student_guide,
    build_target_profile, validation.

INGESTION (Dev A writes, Dev B reads):
  - KnowledgeNodeCreate: Schema for creating a knowledge node during ingestion.
  - RelationCreate: Schema for creating a relation during ingestion.
  - PolicyRuleCreate: Schema for creating a policy rule during ingestion.
  - IngestionJobStatus: Status tracking for ingestion jobs.
"""
