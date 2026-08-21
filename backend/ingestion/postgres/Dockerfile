# KidSpark RAG — Postgres 16 with pgvector, pre-loaded with the project's star schema.
# Design adopted from the "pgvector as a vector database" pattern: a Dockerfile-built image whose
# init scripts enable the extension and create the tables, so the DB is query-ready on first boot.
# (We keep OpenAI + our vision embeddings — nothing about the embedding model lives in the DB image.)
FROM pgvector/pgvector:pg16

# init/*.sql run in alphabetical order the first time the data volume is created:
#   01-extension.sql -> CREATE EXTENSION vector
#   02-schema.sql    -> document_bundle, pdf_node (FACT + VECTOR(3072)), standard_rules + indexes
COPY init/ /docker-entrypoint-initdb.d/
