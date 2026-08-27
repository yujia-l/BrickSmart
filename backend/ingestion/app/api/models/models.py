"""SQLAlchemy ORM models (the 'M' in MVC) — the KidSpark star schema for context-aware retrieval.

  DocumentBundle  (dimension)   — one row per lesson bundle (grade/lab/unit/lesson + policy refs)
  PdfNode         (FACT)        — one row per node/chunk, holding the pgvector EMBEDDING plus the
                                  denormalized grade/lab/unit so vector search can be metadata
                                  pre-filtered (context aware) WITHOUT a join
  StandardRule    (unit policy) — rules.json rows, FK bundle_name -> DocumentBundle
"""
from datetime import datetime, timezone

from sqlalchemy import (Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint)
from sqlalchemy.orm import declarative_base, relationship
from pgvector.sqlalchemy import Vector

from app.core.config import settings

Base = declarative_base()
EMBED_DIM = settings.EMBED_DIM          # 3072 for gemini-embedding-001
VISUAL_EMBED_DIM = settings.VISUAL_EMBED_DIM


def _now():
    return datetime.now(timezone.utc)


class DocumentBundle(Base):
    """Dimension: one lesson bundle (the 3 docs of a lesson)."""
    __tablename__ = "document_bundle"
    id = Column(Integer, primary_key=True, autoincrement=True)
    bundle_id = Column(String, unique=True, index=True, nullable=False)   # deterministic uuid
    bundle_name = Column(String, unique=True, index=True, nullable=False)
    grade_band = Column(String, index=True)
    lab = Column(String, index=True)
    unit = Column(String, index=True)
    lesson = Column(String)
    title = Column(String)
    policy_scope = Column(String, index=True)
    policy_path = Column(String)
    manifest_path = Column(String)
    processing_version = Column(String)
    ingested_at = Column(String)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class PdfNode(Base):
    """FACT table: one row per node/chunk, carrying the vector embedding + denormalized context."""
    __tablename__ = "pdf_node"
    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(String, index=True, nullable=False)
    chunk_id = Column(String, index=True)
    type = Column(String, index=True)          # text|figure|table|ocr|learning_objective
    text = Column(Text)
    doc_kind = Column(String, index=True)
    page_no = Column(Integer)
    page_id = Column(String, index=True)
    section_header = Column(String)
    header = Column(String)
    lesson_stage = Column(String, index=True)
    visual_role = Column(String, index=True)
    audience = Column(String, index=True)
    # lineage / provenance
    bundle_id = Column(String, ForeignKey("document_bundle.bundle_id"), index=True, nullable=False)
    bundle_name = Column(String, index=True)
    doc_id = Column(String, index=True)
    gcs_object_path = Column(String)
    lesson = Column(String)
    # denormalized for filtered (context-aware) vector search
    grade_band = Column(String, index=True)
    lab = Column(String, index=True)
    unit = Column(String, index=True)
    # image / vision extras (context-aware image retrieval)
    image_type = Column(String, index=True)
    educational_purpose = Column(Text)
    ocr_text = Column(Text)
    relation_hint = Column(Text)
    # the vector
    embedding = Column(Vector(EMBED_DIM))
    embedding_model = Column(String)
    embedding_dimensions = Column(Integer)
    image_uri = Column(String)
    visual_embedding = Column(Vector(VISUAL_EMBED_DIM))
    visual_embedding_model = Column(String)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)
    __table_args__ = (UniqueConstraint("bundle_id", "node_id", name="uq_pdf_node"),)

    bundle = relationship("DocumentBundle", backref="nodes")


class StandardRule(Base):
    """Unit-level policy rule (rules.json), linked to a bundle by bundle_name."""
    __tablename__ = "standard_rules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(String, index=True)
    bundle_name = Column(String, ForeignKey("document_bundle.bundle_name"), index=True, nullable=False)
    policy_scope = Column(String, index=True)
    framework = Column(String, index=True)
    grade_band = Column(String)
    lab = Column(String)
    unit = Column(String)
    scope = Column(String)
    applies_to = Column(String)
    text = Column(Text)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)
    __table_args__ = (UniqueConstraint("bundle_name", "rule_id", name="uq_standard_rule"),)
