"""Postgres + pgvector store with HYBRID search (vector KNN ⨁ Postgres full-text, RRF-fused).
Every row carries full provenance (grade_band, lab, unit, lesson, filename, gcs_object_path,
bundle_name, bundle_id, policy_scope, ingested_at, processing_version + the whole provenance blob in
JSONB) so any retrieved chunk is traceable to its source object and unit policy."""
import json
from app.core.logging import get_logger

_log = get_logger("store")

# columns returned by search / expansion (include provenance for traceable retrieval)
_COLS = ("chunk_id,bundle_id,bundle_name,doc_kind,page_no,page_id,kind,visual_role,stage,audience,"
         "grade_band,lab,unit,lesson,gcs_object_path,policy_scope,content")
_KEYS = _COLS.split(",")
_FILTERABLE = {"grade_band", "lab", "unit", "lesson", "bundle_name", "policy_scope"}


class PgVectorStore:
    def __init__(self, settings):
        self.s = settings
        self.dim = settings.EMBED_DIM

    def _c(self):
        import psycopg
        from pgvector.psycopg import register_vector
        c = psycopg.connect(self.s.POSTGRESQL_DATABASE_URL.replace("+psycopg", ""), autocommit=True)
        c.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(c)
        return c

    def ensure_schema(self):
        with self._c() as c:
            c.execute(f"""CREATE TABLE IF NOT EXISTS chunks(
                chunk_id TEXT PRIMARY KEY, bundle_id TEXT, bundle_name TEXT, doc_kind TEXT,
                page_no INT, page_id TEXT, kind TEXT, header TEXT, visual_role TEXT, stage TEXT,
                audience TEXT, grade_band TEXT, lab TEXT, unit TEXT, lesson TEXT,
                filename TEXT, gcs_object_path TEXT, policy_scope TEXT, policy_path TEXT,
                manifest_path TEXT, ingested_at TEXT, processing_version TEXT,
                content TEXT, tsv tsvector, embedding vector({self.dim}), metadata JSONB)""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_tsv ON chunks USING gin(tsv)")
            for col in ("page_id", "bundle_name", "grade_band", "lab", "unit", "policy_scope"):
                c.execute(f"CREATE INDEX IF NOT EXISTS idx_{col} ON chunks({col})")
            try:
                c.execute(f"""CREATE INDEX IF NOT EXISTS idx_hnsw ON chunks
                    USING hnsw ((embedding::halfvec({self.dim})) halfvec_cosine_ops)""")
            except Exception as e:
                _log.warning("hnsw index skipped: %s", e)
        _log.info("schema ready (chunks table + indexes)")

    _INSERT_COLS = ("chunk_id,bundle_id,bundle_name,doc_kind,page_no,page_id,kind,header,visual_role,"
                    "stage,audience,grade_band,lab,unit,lesson,filename,gcs_object_path,policy_scope,"
                    "policy_path,manifest_path,ingested_at,processing_version,content,tsv,embedding,metadata")

    def upsert(self, chunks):
        import numpy as np
        placeholders = ("%s," * 23) + "to_tsvector('english',%s),%s,%s"   # 23 scalar +tsv +emb +json = 26
        with self._c() as c:
            for ch in chunks:
                pv = ch.metadata.get("provenance", {})
                emb = np.asarray(ch.embedding, dtype=np.float32) if ch.embedding is not None else None
                c.execute(
                    f"INSERT INTO chunks ({self._INSERT_COLS}) VALUES ({placeholders}) "
                    "ON CONFLICT (chunk_id) DO UPDATE SET content=EXCLUDED.content, tsv=EXCLUDED.tsv, "
                    "embedding=EXCLUDED.embedding, metadata=EXCLUDED.metadata",
                    (ch.chunk_id, ch.bundle_id, ch.metadata.get("bundle_name", ""), ch.doc_kind,
                     ch.page_no, ch.page_id, ch.kind, ch.header, ch.visual_role, ch.stage, ch.audience,
                     pv.get("grade_band", ""), pv.get("lab", ""), pv.get("unit", ""), pv.get("lesson", ""),
                     pv.get("filename", ""), pv.get("gcs_object_path", ""), pv.get("policy_scope", ""),
                     pv.get("policy_path", ""), pv.get("manifest_path", ""), pv.get("ingested_at", ""),
                     pv.get("processing_version", ""), ch.text, ch.text, emb, json.dumps(ch.metadata)))

    def _rows(self, cur):
        return [dict(zip(_KEYS, r)) for r in cur.fetchall()]

    def hybrid_search(self, qvec, qtext, filters, k):
        import numpy as np
        qv = np.asarray(qvec, dtype=np.float32)
        wh, p = [], {"qv": qv, "qt": qtext, "k": k}
        for col, val in (filters or {}).items():
            if val and col in _FILTERABLE:
                wh.append(f"{col}=%({col})s"); p[col] = val
        where = ("WHERE " + " AND ".join(wh)) if wh else ""
        with self._c() as c:
            v = self._rows(c.execute(
                f"SELECT {_COLS} FROM chunks {where} "
                f"ORDER BY embedding::halfvec({self.dim}) <=> %(qv)s::halfvec({self.dim}) LIMIT %(k)s", p))
            t = self._rows(c.execute(
                f"SELECT {_COLS} FROM chunks {where} {'AND' if wh else 'WHERE'} "
                f"tsv @@ plainto_tsquery('english',%(qt)s) "
                f"ORDER BY ts_rank(tsv, plainto_tsquery('english',%(qt)s)) DESC LIMIT %(k)s", p))
        return _rrf(v, t)

    def by_bundle(self, bundle_ids):
        with self._c() as c:
            return self._rows(c.execute(f"SELECT {_COLS} FROM chunks WHERE bundle_id = ANY(%s)",
                                        (list(bundle_ids),)))

    def by_page(self, page_ids):
        with self._c() as c:
            return self._rows(c.execute(f"SELECT {_COLS} FROM chunks WHERE page_id = ANY(%s)",
                                        (list(page_ids),)))


def _rrf(v, t, k=60):
    score = {}
    for lst in (v, t):
        for rank, row in enumerate(lst):
            score[row["chunk_id"]] = score.get(row["chunk_id"], 0.0) + 1.0 / (k + rank + 1)
    by = {r["chunk_id"]: r for r in v + t}
    return [dict(by[cid], score=round(score[cid], 5)) for cid in sorted(score, key=score.get, reverse=True)]
