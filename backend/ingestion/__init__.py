"""
KidSpark AI — Ingestion Pipeline
Owner: Developer A

This package transforms raw Kid Spark lesson PDFs into structured, searchable
knowledge nodes in the PostgreSQL database. It handles document parsing,
section extraction, visual captioning, embedding generation, and relation linking.

Pipeline stages run in order:
  Stage 0: Bundle Registration (group 3 files into 1 lesson family)
  Stage 1: Layout-Aware Parsing (Docling)
  Stage 2: Section Extraction + Metadata Tagging
  Stage 3: Visual Captioning (GPT-4o Vision for slide companions)
  Stage 4: Embedding Generation (text-embedding-3-large)
  Stage 5: Dedup + Relation Linking
"""
