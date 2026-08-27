"""Database engine, session factory, and schema creation.

`create_all_tables()` is the module-level entrypoint called by `app.main.create_app()` at startup:
it enables the pgvector extension, creates the ORM tables, and builds the halfvec HNSW + GIN indexes.
"""
from sqlalchemy import create_engine, text as sa_text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.logging import setup_logger
from app.api.models.models import Base, EMBED_DIM, VISUAL_EMBED_DIM

logger = setup_logger("model_init")

# module-level engine/session (create_engine is lazy — no connection until first use)
engine = create_engine(settings.POSTGRESQL_DATABASE_URL) if settings.POSTGRESQL_DATABASE_URL else None
SessionLocal = sessionmaker(bind=engine) if engine is not None else None


class DBUtil:
    """Thin wrapper around a SQLAlchemy engine + session for the star schema."""

    def __init__(self, settings_=None):
        self.settings = settings_ or settings
        self.logger = logger
        self.url = self.settings.POSTGRESQL_DATABASE_URL
        if not self.url:
            raise RuntimeError(
                "Cloud SQL is not configured. Set POSTGRESQL_DATABASE_URL or all POSTGRES_* values."
            )
        self.engine = create_engine(self.url)
        self.base = Base
        self.session = sessionmaker(bind=self.engine)

    def create_all_tables(self):
        try:
            with self.engine.begin() as conn:
                conn.execute(sa_text("CREATE EXTENSION IF NOT EXISTS vector"))
            self.base.metadata.create_all(bind=self.engine)
            self._apply_migrations()
            self._create_indexes()
            self.logger.info("Tables created: %s", ", ".join(self.base.metadata.tables.keys()))
        except SQLAlchemyError as e:
            self.logger.error("Error occurred while creating tables: %s", str(e))
            raise

    def _apply_migrations(self):
        statements = [
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version VARCHAR PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())",
            "ALTER TABLE pdf_node ADD COLUMN IF NOT EXISTS embedding_model VARCHAR",
            "ALTER TABLE pdf_node ADD COLUMN IF NOT EXISTS embedding_dimensions INTEGER",
            "ALTER TABLE pdf_node ADD COLUMN IF NOT EXISTS image_uri VARCHAR",
            f"ALTER TABLE pdf_node ADD COLUMN IF NOT EXISTS visual_embedding vector({VISUAL_EMBED_DIM})",
            "ALTER TABLE pdf_node ADD COLUMN IF NOT EXISTS visual_embedding_model VARCHAR",
            "INSERT INTO schema_migrations(version) VALUES ('2026-07-vertex-rag-v1') "
            "ON CONFLICT (version) DO NOTHING",
        ]
        with self.engine.begin() as conn:
            for statement in statements:
                conn.execute(sa_text(statement))

    def _create_indexes(self):
        # halfvec HNSW (3072-d exceeds vector's 2000-d index limit) + full-text on node text
        stmts = [
            f"CREATE INDEX IF NOT EXISTS idx_pdf_node_hnsw ON pdf_node "
            f"USING hnsw ((embedding::halfvec({EMBED_DIM})) halfvec_cosine_ops)",
            "CREATE INDEX IF NOT EXISTS idx_pdf_node_tsv ON pdf_node "
            "USING gin (to_tsvector('english', text))",
            f"CREATE INDEX IF NOT EXISTS idx_pdf_node_visual_hnsw ON pdf_node "
            f"USING hnsw ((visual_embedding::halfvec({VISUAL_EMBED_DIM})) halfvec_cosine_ops)",
        ]
        for statement in stmts:
            try:
                with self.engine.begin() as conn:
                    conn.execute(sa_text(statement))
            except SQLAlchemyError as e:
                self.logger.warning("index skipped: %s", e)

    def health_report(self):
        with self.engine.connect() as conn:
            vector_version = conn.execute(
                sa_text("SELECT extversion FROM pg_extension WHERE extname='vector'")
            ).scalar_one_or_none()
            tables = {
                name: bool(
                    conn.execute(sa_text("SELECT to_regclass(:name)"), {"name": name}).scalar()
                )
                for name in ("document_bundle", "pdf_node", "standard_rules", "schema_migrations")
            }
            counts = {}
            if all(tables[name] for name in ("document_bundle", "pdf_node", "standard_rules")):
                counts = {
                    "document_bundle": conn.execute(
                        sa_text("SELECT COUNT(*) FROM document_bundle")
                    ).scalar_one(),
                    "pdf_node": conn.execute(sa_text("SELECT COUNT(*) FROM pdf_node")).scalar_one(),
                    "embedded_pdf_node": conn.execute(
                        sa_text("SELECT COUNT(*) FROM pdf_node WHERE embedding IS NOT NULL")
                    ).scalar_one(),
                    "standard_rules": conn.execute(
                        sa_text("SELECT COUNT(*) FROM standard_rules")
                    ).scalar_one(),
                    "image_pdf_node": conn.execute(
                        sa_text("SELECT COUNT(*) FROM pdf_node WHERE image_uri IS NOT NULL")
                    ).scalar_one(),
                    "visual_embedded_pdf_node": conn.execute(
                        sa_text("SELECT COUNT(*) FROM pdf_node WHERE visual_embedding IS NOT NULL")
                    ).scalar_one(),
                }
                counts["embedding_coverage"] = round(
                    counts["embedded_pdf_node"] / max(counts["pdf_node"], 1),
                    4,
                )
            data_ready = bool(
                counts
                and counts.get("pdf_node", 0) > 0
                and counts.get("embedded_pdf_node", 0) > 0
            )
            corpus_fully_embedded = bool(
                counts and counts.get("embedding_coverage", 0) >= 0.95
            )
            return {
                "ok": bool(vector_version) and all(tables.values()),
                "data_ready": data_ready,
                "corpus_fully_embedded": corpus_fully_embedded,
                "pgvector_version": vector_version,
                "tables": tables,
                "counts": counts,
            }

    def get_session(self):
        try:
            return self.session()
        except SQLAlchemyError as e:
            self.logger.error("Error occurred while getting session: %s", str(e))
            raise


def create_all_tables():
    """Create the pgvector extension, ORM tables, and indexes (used at app startup)."""
    DBUtil().create_all_tables()
