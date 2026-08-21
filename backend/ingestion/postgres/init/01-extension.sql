-- Runs once on first DB init (alphabetical order in /docker-entrypoint-initdb.d).
-- Enable pgvector (ships with the pgvector/pgvector base image) before the schema is created.
CREATE EXTENSION IF NOT EXISTS vector;
