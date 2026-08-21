"""The pipeline. Two entry points, both with visible steps.

  build_chunks()  load -> chunk -> caption images   (no embed/DB — for chunk-quality inspection)
  ingest()        + embed + store                    (calls datasource separately)
  retrieve()      embed -> hybrid search -> bundle expansion -> page (multimodal) expansion
"""
from app.services import datasource, chunking, vision, embeddings, docling_loader
from app.services.store import PgVectorStore
from app.core.logging import get_logger

_log = get_logger("pipeline")


def build_chunks(meta, pdfs, settings, caption=True):
    chunks = []
    for doc_kind, path in pdfs.items():
        if not chunking.is_valid_pdf(path):
            continue
        dl_doc = docling_loader.load_document(path, settings)                 # loader = Docling
        chunks += chunking.chunk_document(dl_doc, meta, doc_kind,             # splitter
                                          settings.CHUNK_MAX_CHARS, settings.CHUNK_OVERLAP, settings.CHUNK_MIN_CHARS)
        if caption:
            chunks += vision.image_chunks(dl_doc, meta, doc_kind, settings)
    return chunks


def ingest(settings, store=None, limit=None, caption=True, log=print):
    store = store or PgVectorStore(settings)
    store.ensure_schema()
    bundles = datasource.discover(settings)          # <-- data-source module called separately
    if limit:
        bundles = bundles[:limit]
    total = 0
    for meta, pdfs in bundles:
        chunks = build_chunks(meta, pdfs, settings, caption=caption)
        vecs = embeddings.embed_texts([c.text for c in chunks], settings)     # embedder (swappable)
        for c, v in zip(chunks, vecs):
            c.embedding = v
        store.upsert(chunks)
        total += len(chunks)
        log(f"ingested {meta['bundle_id']}: {len(chunks)} chunks")
    return total


def retrieve(query, settings, filters=None, store=None, seed_k=5, k=30, expand_bundles=3):
    store = store or PgVectorStore(settings)
    filters = filters or {}
    steps = []
    _log.info("retrieve: %r  filters=%s", query[:80], filters or 'none')

    qvec = embeddings.embed_query(query, settings)
    steps.append(("1. embed_query", query[:80]))

    cand = store.hybrid_search(qvec, query, filters, k)
    steps.append(("2. hybrid_search (pgvector KNN + Postgres full-text, RRF)",
                  f"filters={filters or 'none'} -> {len(cand)} candidates"))
    if not cand:
        return {"query": query, "steps": steps, "pages": [], "teacher": [], "student": [], "visual": []}

    from app.services.reranker import get_reranker
    pool = cand[: getattr(settings, "RERANK_POOL", 20)]
    seeds = get_reranker(settings).rerank(query, pool, seed_k)       # precision rerank (biggest quality lever)
    steps.append(("3. rerank -> seeds", [c["chunk_id"] for c in seeds]))

    collected = {c["chunk_id"]: c for c in seeds}
    bundles = list(dict.fromkeys(c["bundle_id"] for c in seeds))[:expand_bundles]
    for r in store.by_bundle(bundles):
        collected.setdefault(r["chunk_id"], dict(r, score=0.0))
    steps.append(("4. bundle_expansion (whole lesson)", bundles))

    pages = list(dict.fromkeys(c["page_id"] for c in seeds if c["page_id"]))
    added = 0
    for r in store.by_page(pages):
        if r["chunk_id"] not in collected:
            collected[r["chunk_id"]] = dict(r, score=0.0); added += 1
    steps.append(("5. page_expansion (multimodal image<->text)", f"{len(pages)} pages, +{added} co-located"))

    items = list(collected.values())
    return {"query": query, "steps": steps,
            "pages": sorted({c["page_id"] for c in items if c["page_id"]}),
            "teacher": [c for c in items if c["audience"] == "teacher" and not c["visual_role"]],
            "student": [c for c in items if c["audience"] == "student" and not c["visual_role"]],
            "visual":  [c for c in items if c["visual_role"] or c["kind"] == "image"]}
