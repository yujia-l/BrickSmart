"""
KidSpark AI — Hybrid Search
Owner: Developer B

This module implements the core search logic: vector similarity search on
knowledge node embeddings combined with metadata pre-filtering.

RESPONSIBILITIES:
  - Accept a query string and metadata filters (grade_band, doc_kind, strand,
    lesson_stage, audience)
  - Embed the query using text-embedding-3-large
  - Run a filtered vector similarity search (pgvector cosine distance) against
    the knowledge_nodes table
  - Apply metadata pre-filters to narrow the candidate set before vector ranking
  - Return the top-K candidate nodes ranked by relevance
  - Also support direct policy rule retrieval by grade_band and framework

INPUTS:
  - query: str (natural language search query)
  - grade_band: optional filter
  - doc_kind: optional filter
  - limit: int (default 20)

OUTPUTS:
  - List of candidate KnowledgeNode records with distance scores

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.3, "Retrieval Pipeline"
"""
