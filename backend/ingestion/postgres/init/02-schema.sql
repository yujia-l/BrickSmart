-- Auto-generated from ksrag/db.py (SQLAlchemy models) — keep in sync via that source of truth.
-- KidSpark RAG star schema: document_bundle (dim) · pdf_node (FACT + pgvector) · standard_rules

CREATE TABLE IF NOT EXISTS document_bundle (
	id SERIAL NOT NULL, 
	bundle_id VARCHAR NOT NULL, 
	bundle_name VARCHAR NOT NULL, 
	grade_band VARCHAR, 
	lab VARCHAR, 
	unit VARCHAR, 
	lesson VARCHAR, 
	title VARCHAR, 
	policy_scope VARCHAR, 
	policy_path VARCHAR, 
	manifest_path VARCHAR, 
	processing_version VARCHAR, 
	ingested_at VARCHAR, 
	created_at TIMESTAMP WITH TIME ZONE, 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_document_bundle_grade_band ON document_bundle (grade_band);
CREATE UNIQUE INDEX ix_document_bundle_bundle_id ON document_bundle (bundle_id);
CREATE INDEX IF NOT EXISTS ix_document_bundle_lab ON document_bundle (lab);
CREATE UNIQUE INDEX ix_document_bundle_bundle_name ON document_bundle (bundle_name);
CREATE INDEX IF NOT EXISTS ix_document_bundle_unit ON document_bundle (unit);
CREATE INDEX IF NOT EXISTS ix_document_bundle_policy_scope ON document_bundle (policy_scope);

CREATE TABLE IF NOT EXISTS pdf_node (
	id SERIAL NOT NULL, 
	node_id VARCHAR NOT NULL, 
	chunk_id VARCHAR, 
	type VARCHAR, 
	text TEXT, 
	doc_kind VARCHAR, 
	page_no INTEGER, 
	page_id VARCHAR, 
	section_header VARCHAR, 
	header VARCHAR, 
	lesson_stage VARCHAR, 
	visual_role VARCHAR, 
	audience VARCHAR, 
	bundle_id VARCHAR NOT NULL, 
	bundle_name VARCHAR, 
	doc_id VARCHAR, 
	gcs_object_path VARCHAR, 
	lesson VARCHAR, 
	grade_band VARCHAR, 
	lab VARCHAR, 
	unit VARCHAR, 
	image_type VARCHAR, 
	educational_purpose TEXT, 
	ocr_text TEXT, 
	relation_hint TEXT, 
	embedding VECTOR(3072),
	embedding_model VARCHAR,
	embedding_dimensions INTEGER,
	image_uri VARCHAR,
	visual_embedding VECTOR(1408),
	visual_embedding_model VARCHAR,
	created_at TIMESTAMP WITH TIME ZONE, 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_pdf_node UNIQUE (bundle_id, node_id), 
	FOREIGN KEY(bundle_id) REFERENCES document_bundle (bundle_id)
);

CREATE INDEX IF NOT EXISTS ix_pdf_node_chunk_id ON pdf_node (chunk_id);
CREATE INDEX IF NOT EXISTS ix_pdf_node_lesson_stage ON pdf_node (lesson_stage);
CREATE INDEX IF NOT EXISTS ix_pdf_node_node_id ON pdf_node (node_id);
CREATE INDEX IF NOT EXISTS ix_pdf_node_doc_id ON pdf_node (doc_id);
CREATE INDEX IF NOT EXISTS ix_pdf_node_grade_band ON pdf_node (grade_band);
CREATE INDEX IF NOT EXISTS ix_pdf_node_unit ON pdf_node (unit);
CREATE INDEX IF NOT EXISTS ix_pdf_node_type ON pdf_node (type);
CREATE INDEX IF NOT EXISTS ix_pdf_node_bundle_id ON pdf_node (bundle_id);
CREATE INDEX IF NOT EXISTS ix_pdf_node_image_type ON pdf_node (image_type);
CREATE INDEX IF NOT EXISTS ix_pdf_node_bundle_name ON pdf_node (bundle_name);
CREATE INDEX IF NOT EXISTS ix_pdf_node_doc_kind ON pdf_node (doc_kind);
CREATE INDEX IF NOT EXISTS ix_pdf_node_visual_role ON pdf_node (visual_role);
CREATE INDEX IF NOT EXISTS ix_pdf_node_lab ON pdf_node (lab);
CREATE INDEX IF NOT EXISTS ix_pdf_node_page_id ON pdf_node (page_id);
CREATE INDEX IF NOT EXISTS ix_pdf_node_audience ON pdf_node (audience);

CREATE TABLE IF NOT EXISTS standard_rules (
	id SERIAL NOT NULL, 
	rule_id VARCHAR, 
	bundle_name VARCHAR NOT NULL, 
	policy_scope VARCHAR, 
	framework VARCHAR, 
	grade_band VARCHAR, 
	lab VARCHAR, 
	unit VARCHAR, 
	scope VARCHAR, 
	applies_to VARCHAR, 
	text TEXT, 
	created_at TIMESTAMP WITH TIME ZONE, 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_standard_rule UNIQUE (bundle_name, rule_id), 
	FOREIGN KEY(bundle_name) REFERENCES document_bundle (bundle_name)
);

CREATE INDEX IF NOT EXISTS ix_standard_rules_policy_scope ON standard_rules (policy_scope);
CREATE INDEX IF NOT EXISTS ix_standard_rules_bundle_name ON standard_rules (bundle_name);
CREATE INDEX IF NOT EXISTS ix_standard_rules_rule_id ON standard_rules (rule_id);
CREATE INDEX IF NOT EXISTS ix_standard_rules_framework ON standard_rules (framework);

-- vector ANN (halfvec: 3072-d exceeds vector's 2000-d index limit) + full-text on node text
CREATE INDEX IF NOT EXISTS idx_pdf_node_hnsw ON pdf_node USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_pdf_node_visual_hnsw ON pdf_node USING hnsw ((visual_embedding::halfvec(1408)) halfvec_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_pdf_node_tsv ON pdf_node USING gin (to_tsvector('english', text));
