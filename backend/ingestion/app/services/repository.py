"""Repository — data access over the star schema.

Loads processed bundles into the tables and runs CONTEXT-AWARE retrieval off the pdf_node FACT table
(halfvec KNN + Postgres full-text, RRF-fused).

Bundles can be loaded two ways:
  * ``load_knowledge_from_gcs`` - streams the artifacts straight out of GCS (nothing hits local disk)
  * ``load_knowledge`` / ``load_bundle_dir`` — reads an already-local Knowledge_chunks tree
"""
import glob
import json
import os
import uuid

from sqlalchemy import text as sa_text, bindparam

from app.core.config import settings as _SETTINGS
from app.core.logging import get_logger
from app.api.models.models import DocumentBundle, PdfNode, StandardRule, EMBED_DIM, _now
from app.api.models.model_init import DBUtil
from app.services.embeddings import embed_texts, embed_query

_log = get_logger("repository")

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "kidspark.knowledge")


def _doc_id(path):
    return str(uuid.uuid5(_NS, "doc:" + (path or "").lower()))


def _upsert(session, model, keys, values):
    obj = session.query(model).filter_by(**keys).one_or_none()
    if obj:
        for k, v in values.items():
            setattr(obj, k, v)
    else:
        obj = model(**{**keys, **values})
        session.add(obj)
    return obj


# ─────────────────────────── core loader (works on parsed dicts) ───────────────────────────
def load_bundle_payload(session, bundle, nodes, rules_json=None, settings=None, embed=True):
    """Upsert ONE bundle's already-parsed artifacts into the star schema.

    Source-agnostic: the caller supplies the parsed ``bundle.json`` / ``nodes.json`` / ``rules.json``
    dicts, whether they came from GCS (in memory) or from local files.
    """
    settings = settings or _SETTINGS
    b = bundle
    lm = b.get("lesson_metadata", {})
    prov = b.get("source_lineage", {})
    pol = b.get("policy_references", {})

    _upsert(session, DocumentBundle, {"bundle_id": b["bundle_id"]}, dict(
        bundle_name=b["bundle_name"], grade_band=lm.get("grade_band"), lab=lm.get("lab"),
        unit=lm.get("unit"), lesson=lm.get("lesson"), title=lm.get("title"),
        policy_scope=pol.get("policy_scope"), policy_path=pol.get("policy_path"),
        manifest_path=b.get("manifest_references", {}).get("manifest_path"),
        processing_version=prov.get("processing_version"), ingested_at=prov.get("ingested_at"),
        updated_at=_now()))

    vecs = None
    if embed and settings.OPENAI_API_KEY:
        vecs = embed_texts([n.get("text", "") for n in nodes], settings)
    for i, n in enumerate(nodes):
        p = n.get("provenance", {})
        _upsert(session, PdfNode, {"bundle_id": b["bundle_id"], "node_id": n["node_id"]}, dict(
            chunk_id=n["node_id"], type=n.get("type"), text=n.get("text"), doc_kind=n.get("doc_kind"),
            page_no=n.get("page_no"), page_id=n.get("page_id"), section_header=n.get("section_header"),
            header=n.get("section_header"), lesson_stage=n.get("lesson_stage"),
            visual_role=n.get("visual_role"), audience=n.get("audience"),
            bundle_name=b["bundle_name"], doc_id=_doc_id(p.get("gcs_object_path", "")),
            gcs_object_path=p.get("gcs_object_path"), lesson=p.get("lesson"),
            grade_band=p.get("grade_band"), lab=p.get("lab"), unit=p.get("unit"),
            image_type=n.get("image_type"), educational_purpose=n.get("educational_purpose"),
            ocr_text=n.get("ocr_text"), relation_hint=n.get("relation_hint"),
            embedding=(vecs[i] if vecs else None), updated_at=_now()))

    if rules_json:
        for rule in rules_json.get("rules", []):
            _upsert(session, StandardRule,
                    {"bundle_name": b["bundle_name"], "rule_id": rule.get("rule_id")},
                    dict(policy_scope=rules_json.get("policy_scope"), framework=rule.get("framework"),
                         grade_band=rule.get("grade_band"), lab=rule.get("lab"), unit=rule.get("unit"),
                         scope=rule.get("scope"), applies_to=rule.get("applies_to"),
                         text=rule.get("text"), updated_at=_now()))
    return b["bundle_name"], len(nodes)


# ─────────────────────────── GCS loader (streams — no local disk) ───────────────────────────
def load_knowledge_from_gcs(settings=None, embed=True, db=None):
    """Stream every processed bundle from GCS into the star schema.

    Artifacts are read into memory with ``download_as_text`` — nothing is written to local disk. Only
    the embeddings call goes out to OpenAI. Each bundle is loaded and committed individually.
    """
    settings = settings or _SETTINGS
    from app.utils import gcs

    bucket_name = settings.GCS_PROCESSED_BUCKET or "kidspark-processed"
    prefix = settings.KNOWLEDGE_PREFIX
    bundle_prefix = f"{prefix}/bundles/"
    client = gcs.get_client()

    _log.info("streaming gs://%s/%s/ -> database (no local download)", bucket_name, prefix)
    blobs = {b.name: b for b in client.list_blobs(bucket_name, prefix=f"{prefix}/")}
    names = sorted({n[len(bundle_prefix):].split("/")[0]
                    for n in blobs if n.startswith(bundle_prefix) and n[len(bundle_prefix):]})
    if not names:
        raise RuntimeError(
            f"No bundles under gs://{bucket_name}/{bundle_prefix} — run the processing pipeline first.")

    db = db or DBUtil(settings)
    db.create_all_tables()
    session = db.get_session()

    rules_cache = {}
    count = 0
    for name in names:
        bkey, nkey = f"{bundle_prefix}{name}/bundle.json", f"{bundle_prefix}{name}/nodes.json"
        if bkey not in blobs or nkey not in blobs:
            _log.warning("skipping %s (missing bundle.json or nodes.json)", name)
            continue
        bundle = json.loads(blobs[bkey].download_as_text())
        nodes = json.loads(blobs[nkey].download_as_text())

        # unit policy (read in memory too), cached so each rules.json is fetched once
        ppath = (bundle.get("policy_references") or {}).get("policy_path")
        rules_json = None
        if ppath:
            if ppath not in rules_cache:
                rb = blobs.get(ppath)
                rules_cache[ppath] = json.loads(rb.download_as_text()) if rb else None
            rules_json = rules_cache[ppath]

        bname, cnt = load_bundle_payload(session, bundle, nodes, rules_json, settings, embed=embed)
        session.commit()
        _log.info("loaded %s (%d nodes)", bname, cnt)
        count += 1

    session.close()
    return count


# ─────────────────────────── local loaders (dev / already-downloaded tree) ───────────────────────────
def load_bundle_dir(session, bundle_dir, knowledge_root, settings=None, embed=True):
    """Load one LOCAL Knowledge_chunks/bundles/<name>/ directory into the star schema."""
    settings = settings or _SETTINGS
    bundle = json.load(open(os.path.join(bundle_dir, "bundle.json"), encoding="utf-8"))
    nodes = json.load(open(os.path.join(bundle_dir, "nodes.json"), encoding="utf-8"))

    pol = bundle.get("policy_references", {})
    rules_json = None
    rpath = os.path.join(knowledge_root, pol.get("policy_path", "")) if pol.get("policy_path") else None
    if rpath and os.path.exists(rpath):
        rules_json = json.load(open(rpath, encoding="utf-8"))
    return load_bundle_payload(session, bundle, nodes, rules_json, settings, embed=embed)


def load_knowledge(knowledge_root, settings=None, embed=True, db=None):
    """Load ALL bundles from a LOCAL <knowledge_root>/Knowledge_chunks/ tree."""
    settings = settings or _SETTINGS
    db = db or DBUtil(settings)
    db.create_all_tables()
    session = db.get_session()
    n = 0
    for bdir in sorted(glob.glob(os.path.join(knowledge_root, "Knowledge_chunks", "bundles", "*"))):
        if os.path.isdir(bdir):
            name, cnt = load_bundle_dir(session, bdir, knowledge_root, settings, embed=embed)
            db.logger.info("loaded %s (%d nodes)", name, cnt)
            n += 1
    session.commit()
    session.close()
    return n


# ─────────────────────────── context-aware retrieval ───────────────────────────
def _rrf(*ranked_lists, k=60):
    score = {}
    for lst in ranked_lists:
        for rank, nid in enumerate(lst):
            score[nid] = score.get(nid, 0.0) + 1.0 / (k + rank + 1)
    return score


_NODE_COLS = ("n.node_id, n.type, n.text, n.doc_kind, n.page_id, n.page_no, n.visual_role, "
              "n.lesson_stage, n.audience, n.bundle_id, n.bundle_name, n.grade_band, n.lab, n.unit, "
              "n.lesson, n.image_type, n.educational_purpose, n.ocr_text")


def retrieve_from_db(query, settings=None, filters=None, k=30, seed_k=5, hybrid=True, db=None):
    """Context-aware retrieval off pdf_node: metadata pre-filter + halfvec KNN ⨁ full-text (RRF)."""
    settings = settings or _SETTINGS
    filters = filters or {}
    db = db or DBUtil(settings)
    dim = EMBED_DIM

    qvec = embed_query(query, settings)
    qlit = "[" + ",".join(str(float(x)) for x in qvec) + "]"

    where, params = [], {"qv": qlit, "qt": query, "k": k}
    for col in ("grade_band", "lab", "unit", "doc_kind", "lesson"):
        if filters.get(col):
            where.append(f"n.{col} = :{col}")
            params[col] = filters[col]
    wsql = ("WHERE " + " AND ".join(where)) if where else ""

    vec_sql = (f"SELECT {_NODE_COLS}, "
               f"(n.embedding::halfvec({dim}) <=> (:qv)::vector({dim})::halfvec({dim})) AS distance "
               f"FROM pdf_node n {wsql} "
               f"ORDER BY n.embedding::halfvec({dim}) <=> (:qv)::vector({dim})::halfvec({dim}) "
               f"LIMIT :k")
    txt_sql = (f"SELECT {_NODE_COLS}, "
               f"ts_rank(to_tsvector('english', n.text), plainto_tsquery('english', :qt)) AS rank "
               f"FROM pdf_node n {wsql} {'AND' if where else 'WHERE'} "
               f"to_tsvector('english', n.text) @@ plainto_tsquery('english', :qt) "
               f"ORDER BY rank DESC LIMIT :k")

    with db.engine.connect() as conn:
        vrows = [dict(r._mapping) for r in conn.execute(sa_text(vec_sql), params)]
        trows = [dict(r._mapping) for r in conn.execute(sa_text(txt_sql), params)] if hybrid else []
        fused = _rrf([r["node_id"] for r in vrows], [r["node_id"] for r in trows])
        by = {r["node_id"]: r for r in vrows + trows}
        candidates = [dict(by[nid], score=round(fused[nid], 5))
                      for nid in sorted(fused, key=fused.get, reverse=True)]
        seeds = candidates[:seed_k]

        bundle_ids = list(dict.fromkeys(s_["bundle_id"] for s_ in seeds))
        bundles, rules = [], []
        if bundle_ids:
            bq = sa_text("SELECT * FROM document_bundle WHERE bundle_id IN :ids").bindparams(
                bindparam("ids", expanding=True))
            bundles = [dict(r._mapping) for r in conn.execute(bq, {"ids": bundle_ids})]
            names = [b["bundle_name"] for b in bundles]
            if names:
                rq = sa_text("SELECT * FROM standard_rules WHERE bundle_name IN :names").bindparams(
                    bindparam("names", expanding=True))
                rules = [dict(r._mapping) for r in conn.execute(rq, {"names": names})]

    _log.info("retrieve_from_db: %r filters=%s -> %d candidates, %d seeds, %d bundle(s), %d rule(s)",
              query[:60], filters or "none", len(candidates), len(seeds), len(bundles), len(rules))
    return {"query": query, "filters": filters, "seeds": seeds, "candidates": candidates,
            "bundles": bundles, "rules": rules}


def nodes_for_bundles(bundle_ids, db=None, settings=None):
    """All pdf_node rows for the given bundles (for page-grouped lineage assembly)."""
    if not bundle_ids:
        return []
    db = db or DBUtil(settings or _SETTINGS)
    q = sa_text(f"SELECT {_NODE_COLS} FROM pdf_node n WHERE n.bundle_id IN :ids "
                "ORDER BY n.bundle_id, n.page_no, n.node_id").bindparams(
                    bindparam("ids", expanding=True))
    with db.engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(q, {"ids": list(bundle_ids)})]


def policies_for(bundle_name=None, unit=None, policy_scope=None, db=None, settings=None):
    """Fetch standard_rules by bundle_name / unit / policy_scope (post-generation compliance check)."""
    db = db or DBUtil(settings or _SETTINGS)
    where, params = [], {}
    if bundle_name:
        where.append("bundle_name = :bn")
        params["bn"] = bundle_name
    if unit:
        where.append("unit = :u")
        params["u"] = unit
    if policy_scope:
        where.append("policy_scope = :ps")
        params["ps"] = policy_scope
    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    with db.engine.connect() as conn:
        return [dict(r._mapping)
                for r in conn.execute(sa_text(f"SELECT * FROM standard_rules {wsql}"), params)]
