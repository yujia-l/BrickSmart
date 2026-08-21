import sys
from pathlib import Path
from types import SimpleNamespace


INGESTION_ROOT = Path(__file__).resolve().parents[1] / "ingestion"
if str(INGESTION_ROOT) not in sys.path:
    sys.path.insert(0, str(INGESTION_ROOT))

from app.api.models.models import DocumentBundle, PdfNode  # noqa: E402
from app.services import repository, retrieval  # noqa: E402


def test_query_understanding_can_skip_generation():
    settings = SimpleNamespace(RAG_QUERY_UNDERSTANDING_ENABLED=False)

    result = retrieval.understand_query(
        "Find a perseverance lesson about inventing an airplane.",
        "Grades_Pre-K-1st",
        settings,
    )

    assert result["clean_query"] == (
        "Find a perseverance lesson about inventing an airplane."
    )
    assert result["grade_band"] == "Grades_Pre-K-1st"
    assert result["lab"] == ""


def test_metadata_only_reload_preserves_existing_embedding(monkeypatch):
    existing = SimpleNamespace(
        node_id="node-1",
        text="Existing lesson text",
        embedding=[0.25, 0.5],
        embedding_model="gemini-embedding-001",
        embedding_dimensions=3072,
    )

    class FakeQuery:
        def filter_by(self, **_kwargs):
            return self

        def all(self):
            return [existing]

    class FakeSession:
        def query(self, model):
            assert model is PdfNode
            return FakeQuery()

        def add(self, _value):
            raise AssertionError("existing node should be updated, not inserted")

    monkeypatch.setattr(
        repository,
        "_upsert",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )

    bundle = {
        "bundle_id": "bundle-1",
        "bundle_name": "airplane",
        "lesson_metadata": {"grade_band": "Grades_Pre-K-1st"},
    }
    nodes = [
        {
            "node_id": "node-1",
            "text": "Updated lesson text",
            "provenance": {"grade_band": "Grades_Pre-K-1st"},
        }
    ]

    repository.load_bundle_payload(
        FakeSession(),
        bundle,
        nodes,
        settings=SimpleNamespace(
            EMBED_MODEL="gemini-embedding-001",
            EMBED_DIM=3072,
        ),
        embed=False,
    )

    assert existing.text == "Updated lesson text"
    assert existing.embedding == [0.25, 0.5]
    assert existing.embedding_model == "gemini-embedding-001"
    assert existing.embedding_dimensions == 3072


def test_backfill_targets_one_bundle_and_commits_batches(monkeypatch):
    rows = [
        SimpleNamespace(
            id=index,
            bundle_name="airplane",
            text=f"node {index}",
            embedding=None,
            embedding_model=None,
            embedding_dimensions=None,
            updated_at=None,
        )
        for index in range(3)
    ]
    filters = []

    class FakeQuery:
        def filter(self, *criteria):
            filters.extend(criteria)
            return self

        def order_by(self, _value):
            return self

        def limit(self, size):
            self.size = size
            return self

        def all(self):
            missing = [row for row in rows if row.embedding is None]
            return missing[: self.size]

    class FakeSession:
        commits = 0
        closed = False

        def query(self, model):
            assert model is PdfNode
            return FakeQuery()

        def commit(self):
            self.commits += 1

        def rollback(self):
            raise AssertionError("backfill should not roll back")

        def close(self):
            self.closed = True

    session = FakeSession()
    db = SimpleNamespace(get_session=lambda: session)
    settings = SimpleNamespace(
        EMBED_MODEL="gemini-embedding-001",
        EMBED_DIM=3072,
    )
    monkeypatch.setattr(
        repository,
        "embed_texts",
        lambda texts, _settings: [[float(index)] * 2 for index, _ in enumerate(texts)],
    )

    completed = repository.backfill_embeddings(
        settings=settings,
        db=db,
        limit=3,
        batch_size=2,
        bundle_name="airplane",
    )

    assert completed == 3
    assert session.commits == 2
    assert session.closed is True
    assert filters
    assert all(row.embedding is not None for row in rows)
    assert all(row.embedding_model == "gemini-embedding-001" for row in rows)
    assert all(row.embedding_dimensions == 3072 for row in rows)
