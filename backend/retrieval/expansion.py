"""
KidSpark AI — Bundle & Page Expansion
Owner: Developer B

After hybrid search returns the top seed nodes, expand context two ways (mirrors the ingestion-side
retrieval): pull the WHOLE lesson for the seed bundles, and pull page-co-located nodes so an image and
its surrounding text travel together (multimodal linkage). Returns plain node dicts (same shape as
search.NODE_COLS).
"""
from retrieval.db import connect
from retrieval.search import NODE_COLS


def _node_rows(cur):
    return [dict(zip(NODE_COLS, r)) for r in cur.fetchall()]


def expand_bundles(bundle_ids, limit_bundles: int = 3):
    """All nodes belonging to the first `limit_bundles` distinct seed bundle_ids (whole-lesson context)."""
    ids = list(dict.fromkeys(b for b in bundle_ids if b))[:limit_bundles]
    if not ids:
        return []
    cols = ", ".join(NODE_COLS)
    with connect() as c:
        return _node_rows(c.execute(f"SELECT {cols} FROM pdf_node WHERE bundle_id = ANY(%s)", (ids,)))


def expand_pages(page_ids):
    """All nodes sharing a seed page_id — co-locates images with their surrounding text."""
    ids = list(dict.fromkeys(p for p in page_ids if p))
    if not ids:
        return []
    cols = ", ".join(NODE_COLS)
    with connect() as c:
        return _node_rows(c.execute(f"SELECT {cols} FROM pdf_node WHERE page_id = ANY(%s)", (ids,)))
