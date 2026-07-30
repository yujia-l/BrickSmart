"""
KidSpark AI — Hybrid Search
Owner: Developer B

Vector similarity (pgvector cosine on pdf_node.embedding) fused with Postgres full-text (RRF),
metadata pre-filtered by grade_band / lab / unit / doc_kind / audience. Also fetches unit policy
rules from standard_rules. Ports the proven approach from ingestion/app/services/store.py, but
targets the pdf_node / standard_rules tables and returns plain dict rows.

Public:
  embed_query(text)                 -> np.ndarray (3072-d)
  hybrid_search(query, filters, k)  -> list[node dict] ranked by RRF, each with `score`
  fetch_policies(filters, limit)    -> list[rule dict]
"""
import numpy as np

import config
from retrieval.db import connect

# columns returned for every node card (order matters — used to zip rows)
NODE_COLS = (
    "node_id", "bundle_id", "bundle_name", "text", "doc_kind", "page_no", "page_id",
    "lesson_stage", "visual_role", "audience", "grade_band", "lab", "unit",
    "image_type", "gcs_object_path", "ocr_text", "educational_purpose",
)
# exact-match columns (controlled vocab) vs fuzzy contains (free-text hierarchy labels).
# grade_band/lab/unit are matched with ILIKE '%value%' so a runtime label like "Pre-K" matches the
# stored "Grades_Pre-K-1st" — exact equality would miss.
_EXACT = {"doc_kind", "audience", "visual_role", "bundle_name"}
_FUZZY = {"grade_band", "lab", "unit"}

RULE_COLS = ("rule_id", "bundle_name", "policy_scope", "framework", "grade_band", "lab", "unit",
             "scope", "applies_to", "text")


def embed_query(text: str):
    """Embed a query string with the same model Dev A used for the nodes (text-embedding-3-large)."""
    from openai import OpenAI
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    resp = client.embeddings.create(model=config.EMBED_MODEL, input=[text if text.strip() else " "])
    return np.asarray(resp.data[0].embedding, dtype=np.float32)


def _node_rows(cur):
    return [dict(zip(NODE_COLS, r)) for r in cur.fetchall()]


def _where(filters):
    wh, params = [], {}
    for col, val in (filters or {}).items():
        if not val:
            continue
        if col in _EXACT:
            wh.append(f"{col} = %({col})s")
            params[col] = val
        elif col in _FUZZY:
            wh.append(f"{col} ILIKE %({col})s")
            params[col] = f"%{val}%"
    return (" WHERE " + " AND ".join(wh)) if wh else "", params


def hybrid_search(query_text: str, filters: dict | None = None, k: int = 30):
    """pgvector KNN ⨁ Postgres full-text, RRF-fused, metadata pre-filtered. Returns ranked node dicts."""
    dim = config.EMBED_DIM
    cols = ", ".join(NODE_COLS)
    where, params = _where(filters)
    params.update({"qv": embed_query(query_text), "qt": query_text, "k": k})

    with connect() as c:
        vec_rows = _node_rows(c.execute(
            f"SELECT {cols} FROM pdf_node{where} "
            f"ORDER BY embedding::halfvec({dim}) <=> %(qv)s::halfvec({dim}) "
            f"LIMIT %(k)s", params))
        joiner = (where + " AND") if where else " WHERE"
        txt_rows = _node_rows(c.execute(
            f"SELECT {cols} FROM pdf_node{joiner} "
            f"to_tsvector('english', text) @@ plainto_tsquery('english', %(qt)s) "
            f"ORDER BY ts_rank(to_tsvector('english', text), plainto_tsquery('english', %(qt)s)) DESC "
            f"LIMIT %(k)s", params))
    return _rrf(vec_rows, txt_rows)


def _rrf(list_a, list_b, k: int = 60):
    """Reciprocal-rank fusion of two ranked node lists, keyed by node_id."""
    score = {}
    for ranked in (list_a, list_b):
        for rank, row in enumerate(ranked):
            score[row["node_id"]] = score.get(row["node_id"], 0.0) + 1.0 / (k + rank + 1)
    by_id = {r["node_id"]: r for r in list_a + list_b}
    order = sorted(score, key=score.get, reverse=True)
    return [dict(by_id[nid], score=round(score[nid], 6)) for nid in order]


def fetch_policies(filters: dict | None = None, limit: int = 12):
    """Unit policy rules (standard_rules) by grade_band / lab / unit / policy_scope / framework."""
    cols = ", ".join(RULE_COLS)
    wh, params = [], {"lim": limit}
    for col in ("grade_band", "lab", "unit", "policy_scope", "framework"):
        val = (filters or {}).get(col)
        if not val:
            continue
        if col in _FUZZY:
            wh.append(f"{col} ILIKE %({col})s")
            params[col] = f"%{val}%"
        else:
            wh.append(f"{col} = %({col})s")
            params[col] = val
    where = (" WHERE " + " AND ".join(wh)) if wh else ""
    with connect() as c:
        rows = [dict(zip(RULE_COLS, r))
                for r in c.execute(f"SELECT {cols} FROM standard_rules{where} LIMIT %(lim)s", params).fetchall()]
    return rows
