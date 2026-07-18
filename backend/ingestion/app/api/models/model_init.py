"""Database engine, session factory, and schema creation.

`create_all_tables()` is the module-level entrypoint called by `app.main.create_app()` at startup:
it enables the pgvector extension, creates the ORM tables, and builds the halfvec HNSW + GIN indexes.
"""
from sqlalchemy import create_engine, text as sa_text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.logging import setup_logger
from app.api.models.models import Base, EMBED_DIM

logger = setup_logger("model_init")

# module-level engine/session (create_engine is lazy — no connection until first use)
engine = create_engine(settings.POSTGRESQL_DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


class DBUtil:
    """Thin wrapper around a SQLAlchemy engine + session for the star schema."""

    def __init__(self, settings_=None):
        self.settings = settings_ or settings
        self.logger = logger
        self.url = self.settings.POSTGRESQL_DATABASE_URL
        self.engine = create_engine(self.url)
        self.base = Base
        self.session = sessionmaker(bind=self.engine)

    def create_all_tables(self):
        try:
            with self.engine.begin() as conn:
                conn.execute(sa_text("CREATE EXTENSION IF NOT EXISTS vector"))
            self.base.metadata.create_all(bind=self.engine)
            self._create_indexes()
            self.logger.info("Tables created: %s", ", ".join(self.base.metadata.tables.keys()))
        except SQLAlchemyError as e:
            self.logger.error("Error occurred while creating tables: %s", str(e))

    def _create_indexes(self):
        # halfvec HNSW (3072-d exceeds vector's 2000-d index limit) + full-text on node text
        stmts = [
            f"CREATE INDEX IF NOT EXISTS idx_pdf_node_hnsw ON pdf_node "
            f"USING hnsw ((embedding::halfvec({EMBED_DIM})) halfvec_cosine_ops)",
            "CREATE INDEX IF NOT EXISTS idx_pdf_node_tsv ON pdf_node "
            "USING gin (to_tsvector('english', text))",
        ]
        with self.engine.begin() as conn:
            for s in stmts:
                try:
                    conn.execute(sa_text(s))
                except SQLAlchemyError as e:
                    self.logger.warning("index skipped: %s", e)

    def get_session(self):
        try:
            return self.session()
        except SQLAlchemyError as e:
            self.logger.error("Error occurred while getting session: %s", str(e))
            return None


def create_all_tables():
    """Create the pgvector extension, ORM tables, and indexes (used at app startup)."""
    DBUtil().create_all_tables()
