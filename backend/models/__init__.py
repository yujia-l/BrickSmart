"""
KidSpark AI — Shared Data Models

This package contains all Pydantic v2 schemas and SQLAlchemy ORM models.
Both Developer A (ingestion) and Developer B (runtime/agents) import from here.

This is the primary shared contract between the two workstreams. Any changes
to these models should be coordinated between both developers.
"""
