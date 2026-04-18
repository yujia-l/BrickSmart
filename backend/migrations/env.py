"""
KidSpark AI — Alembic Migration Environment
Owner: Developer A (primary), Developer B (may add session-related migrations)

This is the Alembic environment configuration file. It connects Alembic to
the database and tells it where to find the SQLAlchemy models.

RESPONSIBILITIES:
  - Load database URL from config.py
  - Import all SQLAlchemy models from models/db_models.py so Alembic can
    detect schema changes for auto-generation
  - Configure online and offline migration modes
  - Ensure pgvector extension is created before running migrations

SETUP:
  1. Install alembic: pip install alembic
  2. Initialize (already done): alembic init migrations
  3. Generate migration: alembic revision --autogenerate -m "description"
  4. Apply migration: alembic upgrade head

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.1, database schema
"""
