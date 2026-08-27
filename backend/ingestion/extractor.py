"""
KidSpark AI — Section Extractor + Metadata Tagger (Stage 2)
Owner: Developer A

This module maps the raw parsed output from Docling onto the known lesson
section structure, then tags each section with metadata for retrieval.

RESPONSIBILITIES:
  - Take a ParsedDocument and identify semantic sections based on heading
    patterns and content heuristics
  - Map sections to the canonical Teacher Plan structure:
      overview, objectives, vocabulary, anticipatory_set,
      step01_read, step02_learn_explore, step03_invent, closure_reflection
  - For Activity Guides: map to page-based sections (read, vocabulary,
    parts_diagram, example_build, reflection)
  - For Slide Companions: map to per-page sections with visual_role tags
  - Tag each extracted section with metadata:
      doc_kind, audience (teacher | student), lesson_stage, build_target,
      grade_band, visual_role (parts_diagram | example_build | build_step |
      partner_support | null)
  - Generate a unique node_id for each section (e.g., "teacher.step01.read")
  - Write KnowledgeNode records to the database

INPUTS:
  - ParsedDocument from parser.py
  - bundle_id, doc_kind, grade_band, strand

OUTPUTS:
  - List of KnowledgeNode records (written to DB)

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.2, "Stage 2 — Section Extraction"
"""
