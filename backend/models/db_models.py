"""
KidSpark AI — SQLAlchemy ORM Models
Owner: SHARED (Dev A creates tables, Dev B reads from them)

This file defines the SQLAlchemy ORM models that map to PostgreSQL tables.
Dev A is responsible for creating and migrating these tables. Dev B reads
from them via the retrieval service.

Tables to implement (see KIDSPARK_TECHNICAL_SPEC.md Section 7.1 for schema):

  - LessonBundle: A family of 3 related documents (teacher plan, activity guide,
    slide companion). Fields: bundle_id, grade_band, strand, title,
    storybook_title, status, created_at.

  - KnowledgeNode: A single semantic section extracted from a lesson document.
    Fields: id, bundle_id (FK), node_id, doc_kind (teacher_plan | activity_guide |
    slide_companion), lesson_stage, audience, visual_role, content_text,
    content_json, embedding (vector 3072), metadata, created_at.

  - Relation: A typed link between two knowledge nodes (e.g., uses_example_from,
    mirrored_by, visualized_by, aligned_to_standard). Fields: id,
    source_node_id (FK), target_node_id (FK), relation_type, metadata.

  - PolicyRule: Curriculum standards and framework rules (UDL, CASEL, SoR, NGSS,
    ISTE, CCSS). Fields: id, framework, grade_band, strand, rule_text,
    standard_code, embedding (vector 3072), metadata.

  - Session: Teacher session state tracking. Fields: id, session_id,
    storybook_analysis (JSONB), consultation_state (JSONB),
    block_requirements (JSONB), teacher_messages (JSONB),
    lesson_package (JSONB), iteration_count, storybook_gcs_uri,
    phase (consultation | block_awareness | generation | refinement | complete),
    created_at, updated_at.

  - BlockCatalog: Kid Spark physical piece definitions. Fields: id, piece_type,
    piece_name, colors_available (JSONB), quantity_per_kit,
    connection_mechanism, supports_rotation, supports_pivot, supports_axle,
    structural_role, dimensions (JSONB), description.

  - IngestionJob: Tracks ingestion pipeline progress per bundle. Fields: id,
    bundle_id (FK), stage, status, error_detail (JSONB), started_at,
    completed_at.

NOTE: The database uses PostgreSQL 15 with the pgvector extension for vector
similarity search. The embedding columns use vector(3072) for
text-embedding-3-large dimensions.
"""
