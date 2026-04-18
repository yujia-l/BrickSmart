"""
Tests for ingestion/embedder.py
Owner: Developer A

TEST CASES TO IMPLEMENT:
  - test_embed_knowledge_nodes: Verify embeddings are generated and stored for
    nodes with content_text
  - test_embed_policy_rules: Verify policy rule embeddings are generated
  - test_skip_already_embedded: Verify nodes with existing embeddings are skipped
  - test_batch_processing: Verify batching behavior for large node sets
  - test_rate_limit_retry: Verify retry logic on OpenAI rate limit errors
"""
