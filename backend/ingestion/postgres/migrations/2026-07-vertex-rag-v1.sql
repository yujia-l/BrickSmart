CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE pdf_node ADD COLUMN IF NOT EXISTS embedding_model VARCHAR;
ALTER TABLE pdf_node ADD COLUMN IF NOT EXISTS embedding_dimensions INTEGER;
ALTER TABLE pdf_node ADD COLUMN IF NOT EXISTS image_uri VARCHAR;
ALTER TABLE pdf_node ADD COLUMN IF NOT EXISTS visual_embedding vector(1408);
ALTER TABLE pdf_node ADD COLUMN IF NOT EXISTS visual_embedding_model VARCHAR;

CREATE INDEX IF NOT EXISTS idx_pdf_node_visual_hnsw
ON pdf_node USING hnsw ((visual_embedding::halfvec(1408)) halfvec_cosine_ops);

INSERT INTO schema_migrations(version)
VALUES ('2026-07-vertex-rag-v1')
ON CONFLICT (version) DO NOTHING;
