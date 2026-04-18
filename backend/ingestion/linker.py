"""
KidSpark AI — Relation Linker + Dedup (Stage 5)
Owner: Developer A

This module establishes typed relations between knowledge nodes within and
across documents in the same lesson bundle, and deduplicates near-identical
content that appears in multiple documents.

RESPONSIBILITIES:
  - For each lesson bundle, identify and create Relation records:
      * uses_example_from: teacher plan step references an activity guide example
      * mirrored_by: teacher plan section has a parallel in activity guide or slides
      * visualized_by: text section has a corresponding slide visual
      * aligned_to_standard: bundle aligns to specific policy rules / standards
  - Use heuristics based on:
      * Section names and lesson_stage overlap
      * Content similarity (cosine distance on embeddings)
      * visual_role matching across documents
  - Dedup: detect near-duplicate nodes (e.g., vocabulary lists that appear in
    both teacher plan and activity guide) and mark the duplicate with a
    "duplicate_of" relation rather than deleting
  - Link grade_band + strand to matching PolicyRule records

INPUTS:
  - All KnowledgeNodes for a given bundle_id (with embeddings)
  - PolicyRules matching the bundle's grade_band and strand

OUTPUTS:
  - Relation records written to the database

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.2, "Stage 5 — Relation Linking"
"""
