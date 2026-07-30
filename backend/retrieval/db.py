"""
KidSpark AI — Retrieval DB connection
Owner: Developer B

A thin psycopg connection factory pointed at the SAME Postgres + pgvector that Dev A's ingestion
populates (config.POSTGRES_DSN). We use raw psycopg (not the ORM) for the vector query so we can
cast to halfvec for the HNSW index exactly like the ingestion side does.
"""
import config

_VECTOR_REGISTERED = False


def connect():
    """Open an autocommit psycopg connection with pgvector types registered."""
    import psycopg
    from pgvector.psycopg import register_vector

    conn = psycopg.connect(config.POSTGRES_DSN, autocommit=True, connect_timeout=10)
    register_vector(conn)
    return conn
