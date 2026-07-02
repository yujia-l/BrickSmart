"""
KidSpark AI — Pydantic v2 Schemas
Owner: SHARED (Dev A and Dev B both import from here)

Single source of truth for data contracts between the ingestion pipeline
and the runtime/agent pipeline.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SessionPhase(str, Enum):
    story_upload = "story_upload"
    lesson_planning = "lesson_planning"
    model_preview = "model_preview"
    segments_connectors = "segments_connectors"
    build_plan = "build_plan"
    lesson_bundle = "lesson_bundle"
    consultation = "consultation"
    block_awareness = "block_awareness"
    generation = "generation"
    refinement = "refinement"
    complete = "complete"


class MovementType(str, Enum):
    spinning = "spinning"
    pivoting = "pivoting"
    rolling = "rolling"
    static = "static"


# ---------------------------------------------------------------------------
# Step A — Storybook Analysis
# ---------------------------------------------------------------------------

class StoryAnalysis(BaseModel):
    title: str
    characters: list[str]
    settings: list[str]
    key_events: list[str]
    themes: list[str]
    buildable_objects: list[str]
    vocabulary_opportunities: list[str]
    sel_angles: list[str]


# ---------------------------------------------------------------------------
# Consultation Agent
# ---------------------------------------------------------------------------

class ConsultationResponse(BaseModel):
    response: str
    areas_covered: list[str] = Field(default_factory=list)
    areas_remaining: list[str] = Field(default_factory=list)
    ready_to_approve: bool = False


class ConsultationSummary(BaseModel):
    agreed_theme: str
    agreed_artifact: str
    artifact_parts: list[str]
    learning_objectives: list[str]
    grade_band: str
    duration_minutes: int
    literacy_focus: str
    sel_focus: str
    teacher_preferences: list[str]
    kb_evidence_used: list[str]
    storybook_title: str


# ---------------------------------------------------------------------------
# Block Awareness Agent
# ---------------------------------------------------------------------------

class ArtifactPart(BaseModel):
    part_name: str
    movement: str
    suggested_pieces: list[str]
    piece_count: int
    notes: str


class BlockRequirements(BaseModel):
    artifact_label: str
    parts: list[ArtifactPart]
    connector_types_needed: list[str]
    total_cube_blocks: int
    total_special_pieces: int
    articulation_summary: str


class KidSparkPiece(BaseModel):
    piece_type: str
    piece_name: str
    colors_available: list[str]
    quantity_per_kit: int
    connection_mechanism: str
    supports_rotation: bool
    supports_pivot: bool
    supports_axle: bool
    structural_role: str
    dimensions: dict
    description: str


# ---------------------------------------------------------------------------
# Generation Pipeline
# ---------------------------------------------------------------------------

class TimeBlock(BaseModel):
    activity: str
    duration_minutes: int
    description: str


class LessonSpec(BaseModel):
    theme: str
    objectives: list[str]
    lesson_flow: list[TimeBlock]
    teacher_prompts: list[str]
    student_steps: list[str]
    materials: list[str]
    standards_alignment: list[str]
    build_target_profile_ref: str
    validation_flags: dict[str, bool] = Field(default_factory=dict)


class BuildTargetProfile(BaseModel):
    target_label: str
    target_family: str
    required_visible_parts: list[str]
    exemplar_assets: list[str] = Field(default_factory=list)
    teacher_planning_prompts: list[str]
    variation_prompts: list[str]


class TeacherPrompt(BaseModel):
    context: str
    prompt_text: str
    expected_response: str


class TeacherLessonPlan(BaseModel):
    title: str
    overview: str
    learning_objectives: list[str]
    curriculum_connections: list[str]
    activity_details: dict
    materials: list[str]
    vocabulary: list[dict[str, str]]
    pre_lesson_preparation: list[str]
    plan_for_all_learners: str
    anticipatory_set: str
    step_01_read: str
    step_02_learn_explore: str
    step_03_invent: str
    closure_reflection: str
    teacher_prompts: list[TeacherPrompt]
    troubleshooting_tips: list[dict[str, str]]
    standards: list[str]


class StudentGuideSection(BaseModel):
    section_type: str
    title: str
    content: str
    visual_description: Optional[str] = None


class StudentActivityGuide(BaseModel):
    title: str
    grade_band: str
    sections: list[StudentGuideSection]
    example_build_description: str
    real_world_connection: str
    reflection_questions: list[str]


class ValidationResult(BaseModel):
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    auto_fixes_applied: list[str] = Field(default_factory=list)
    checks: dict[str, bool] = Field(default_factory=dict)


class LessonPackage(BaseModel):
    teacher_plan: TeacherLessonPlan
    student_guide: StudentActivityGuide
    build_target_profile: BuildTargetProfile
    validation: ValidationResult
    evidence_trace: list[TraceEntry] = Field(default_factory=list)
    iteration: int = 1
    session_id: str = ""


# ---------------------------------------------------------------------------
# Retrieval / Evidence
# ---------------------------------------------------------------------------

class EvidenceCard(BaseModel):
    node_id: str
    bundle_id: str
    content_text: str
    doc_kind: str
    audience: str
    lesson_stage: str
    relevance_score: float


class TraceEntry(BaseModel):
    node_id: str
    bundle_id: str
    score: float
    retrieval_reason: str = ""


class EvidencePack(BaseModel):
    teacher_cards: list[EvidenceCard] = Field(default_factory=list)
    student_cards: list[EvidenceCard] = Field(default_factory=list)
    visual_cards: list[EvidenceCard] = Field(default_factory=list)
    policy_cards: list[EvidenceCard] = Field(default_factory=list)
    trace: list[TraceEntry] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Ingestion DTOs (Dev A writes, Dev B reads)
# ---------------------------------------------------------------------------

class KnowledgeNodeCreate(BaseModel):
    bundle_id: str
    node_id: str
    doc_kind: str
    audience: str
    lesson_stage: str
    content_text: str
    build_target: Optional[str] = None
    visual_role: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class RelationCreate(BaseModel):
    source_node_id: str
    target_node_id: str
    relation_type: str


class PolicyRuleCreate(BaseModel):
    framework: str
    grade_band: str
    strand: str
    standard_code: Optional[str] = None
    rule_text: str


# ---------------------------------------------------------------------------
# Session (in-memory runtime state)
# ---------------------------------------------------------------------------

class SessionState(BaseModel):
    session_id: str
    phase: SessionPhase = SessionPhase.story_upload
    storybook_text: Optional[str] = None
    storybook_analysis: Optional[StoryAnalysis] = None
    teacher_messages: list[dict[str, str]] = Field(default_factory=list)
    consultation_summary: Optional[ConsultationSummary] = None
    block_requirements: Optional[BlockRequirements] = None
    lesson_package: Optional[LessonPackage] = None
    build_job_id: Optional[str] = None
    model_preview_job_id: Optional[str] = None
    segment_job_id: Optional[str] = None
    document_job_id: Optional[str] = None
    build_result: Optional[dict] = None
    model_preview_result: Optional[dict] = None
    segment_result: Optional[dict] = None
    document_result: Optional[dict] = None
    planning_state: dict = Field(default_factory=dict)
    iteration: int = 0


# ---------------------------------------------------------------------------
# API request / response helpers
# ---------------------------------------------------------------------------

class MessageRequest(BaseModel):
    message: str


class MessageResponse(BaseModel):
    response: str
    phase: str
    areas_covered: list[str] = Field(default_factory=list)
    areas_remaining: list[str] = Field(default_factory=list)
    ready_to_approve: bool = False
    ready_to_generate: bool = False
    planning_state: dict = Field(default_factory=dict)


class SessionCreatedResponse(BaseModel):
    session_id: str
    phase: str


class UploadResponse(BaseModel):
    status: str
    story_analysis: StoryAnalysis
    phase: str
