"""
KidSpark AI — Test Suite

Tests are split by domain so each developer can test independently:
  test_ingestion/  — Developer A (parser, extractor, captioner, embedder)
  test_retrieval/  — Shared (search, expansion, evidence)
  test_agents/     — Developer B (consultation, block awareness, orchestrator)
  test_api/        — Developer B (session endpoints, API flow)
  fixtures/        — Shared test data (sample storybooks, mock KB data)
"""
