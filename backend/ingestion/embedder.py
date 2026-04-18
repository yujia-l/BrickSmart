"""
KidSpark AI — Embedding Generator (Stage 4)
Owner: Developer A

This module generates vector embeddings for all knowledge nodes and policy
rules using OpenAI's text-embedding-3-large model (3072 dimensions).

RESPONSIBILITIES:
  - Query all KnowledgeNodes that have content_text but no embedding yet
  - Batch the text content and call text-embedding-3-large
  - Store the resulting 3072-dimension vectors in the embedding column
  - Handle rate limiting and retries for the OpenAI embeddings API
  - Also embed PolicyRule text when policy rules are ingested

INPUTS:
  - KnowledgeNode records with content_text (from extractor or captioner)
  - PolicyRule records with rule_text (from policy_loader)

OUTPUTS:
  - Updated records with embedding vectors in the database

DEPENDENCIES:
  - OpenAI client (text-embedding-3-large)
  - PostgreSQL with pgvector extension

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.2, "Stage 4 — Embedding Generation"
"""
