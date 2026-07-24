"""Data-layer orchestration: raw docs -> processed ``Knowledge_chunks`` artifacts, fully traceable.

Public functions
    process_lesson    -- build ``bundle.json`` / ``nodes.json`` / ``relations.json`` for one lesson.
    write_unit_policy -- write the shared ``rules.json`` for a unit's policy scope.
    run               -- process every lesson discovered in GCS.
    run_local         -- process every lesson discovered on the local filesystem.

``run`` and ``run_local`` share :func:`_process_bundles`; they differ only in the data source.
"""

from app.services import chunking, datasource, docling_loader, knowledge, naming, provenance, vision
from app.core.logging import get_logger

_log = get_logger("process")


def _primary_filename(meta):
    """Return the lesson's representative filename (teacher plan, else the first document)."""
    documents = meta.get("documents", [])
    for document in documents:
        if document["doc_kind"] == "teacher_plan":
            return document["filename"]
    if documents:
        return documents[0]["filename"]
    return meta.get("lesson", "") + ".pdf"


def process_lesson(meta, pdfs, settings, kstore=None, caption=True):
    """Turn one lesson's PDFs into bundle / nodes / relations artifacts.

    Args:
        meta: lesson metadata from :mod:`ksrag.datasource` (grade/lab/unit/lesson + documents).
        pdfs: mapping of ``doc_kind`` -> local PDF path.
        settings: a :class:`ksrag.config.Settings` instance.
        kstore: optional :class:`ksrag.knowledge.KnowledgeStore`; artifacts are written when given.
        caption: caption image pages with GPT-4o Vision when ``True``.

    Returns:
        dict with ``bundle_name``, ``policy_scope``, ``chunks``, ``bundle``, ``nodes`` and
        ``relations``.
    """
    bundle_name = naming.bundle_name(
        meta["grade_band"], meta["lab"], meta["unit"],
        meta.get("lesson", ""), _primary_filename(meta),
    )
    policy_scope = naming.policy_scope(meta["grade_band"], meta["lab"], meta["unit"])
    policy_path = f"{settings.KNOWLEDGE_PREFIX}/policies/{policy_scope}/rules.json"

    documents = meta.get("documents", [])
    gcs_by_kind = {d["doc_kind"]: d["gcs_object_path"] for d in documents}
    filename_by_kind = {d["doc_kind"]: d["filename"] for d in documents}

    # Per-document provenance so every chunk is traceable to its own source file.
    provenance_by_doc = {
        doc_kind: provenance.build(
            meta, filename_by_kind.get(doc_kind, ""), gcs_by_kind.get(doc_kind, ""),
            bundle_name, policy_scope, policy_path, settings.MANIFEST_PATH,
            processing_version=settings.PROC_VERSION,
        )
        for doc_kind in pdfs
    }
    bundle_prov = provenance.build(
        meta, _primary_filename(meta), meta.get("raw_folder", ""),
        bundle_name, policy_scope, policy_path, settings.MANIFEST_PATH,
        processing_version=settings.PROC_VERSION,
    )

    # ``page_id`` and ``chunk.bundle_id`` use the derived bundle name.
    meta = dict(meta, bundle_id=bundle_name)

    chunks = []
    for doc_kind, path in pdfs.items():
        if not chunking.is_valid_pdf(path):
            continue
        document = docling_loader.load_document(path, settings)
        doc_chunks = chunking.chunk_document(
            document, meta, doc_kind,
            settings.CHUNK_MAX_CHARS, settings.CHUNK_OVERLAP, settings.CHUNK_MIN_CHARS,
        )
        if caption:
            doc_chunks += vision.image_chunks(document, meta, doc_kind, settings)
        for chunk in doc_chunks:
            chunk.metadata["provenance"] = provenance_by_doc.get(doc_kind, bundle_prov)
            chunk.metadata["bundle_name"] = bundle_name
            chunk.metadata["policy_scope"] = policy_scope
        chunks += doc_chunks

    nodes = knowledge.assemble_nodes(chunks, provenance_by_doc)
    relations = knowledge.assemble_relations(chunks, bundle_prov["bundle_id"])
    bundle = knowledge.assemble_bundle(
        meta, documents, chunks, bundle_prov, policy_scope, policy_path, settings.MANIFEST_PATH,
    )
    if kstore:
        kstore.write_bundle(bundle_name, bundle, nodes, relations)

    return {
        "bundle_name": bundle_name,
        "policy_scope": policy_scope,
        "chunks": chunks,
        "bundle": bundle,
        "nodes": nodes,
        "relations": relations,
    }


def write_unit_policy(meta, settings, kstore=None):
    """Build (and optionally write) the shared ``rules.json`` for a unit's policy scope."""
    policy_scope = naming.policy_scope(meta["grade_band"], meta["lab"], meta["unit"])
    policy_path = f"{settings.KNOWLEDGE_PREFIX}/policies/{policy_scope}/rules.json"
    rules_bundle_name = naming.bundle_name(
        meta["grade_band"], meta["lab"], meta["unit"], meta.get("lesson", ""), "rules",
    )
    prov = provenance.build(
        meta, "rules.json", "", rules_bundle_name, policy_scope, policy_path,
        settings.MANIFEST_PATH, r_id=provenance.rule_id(policy_scope),
        processing_version=settings.PROC_VERSION,
    )
    rules = knowledge.assemble_rules(meta, policy_scope, prov)
    if kstore:
        kstore.write_policy(policy_scope, rules)
    return rules


def _process_bundles(bundles, settings, kstore, caption, emit):
    """Process ``(meta, pdfs)`` bundles, writing one policy file per unit; return the count."""
    seen_scopes = set()
    total = len(bundles)
    for index, (meta, pdfs) in enumerate(bundles, start=1):
        result = process_lesson(meta, pdfs, settings, kstore, caption=caption)
        emit(f"[{index}/{total}] bundle: {result['bundle_name']}  ({len(result['chunks'])} chunks)")
        if result["policy_scope"] not in seen_scopes:
            write_unit_policy(meta, settings, kstore)
            seen_scopes.add(result["policy_scope"])
            emit(f"    policy: {result['policy_scope']}")
    emit(f"done: {total} bundle(s), {len(seen_scopes)} unit policy file(s)")
    return total


def run(settings, kstore=None, limit=None, caption=True, log=None):
    """Process every lesson discovered in GCS into ``Knowledge_chunks`` artifacts."""
    emit = log or _log.info
    kstore = kstore or knowledge.KnowledgeStore(settings)
    bundles = datasource.discover(settings, limit=limit)   # limit applied BEFORE download (fast)
    emit(f"processing {len(bundles)} lesson bundle(s)")
    return _process_bundles(bundles, settings, kstore, caption, emit)


def run_local(settings, data_root, kstore=None, limit=None, caption=True, log=None):
    """Process every lesson discovered on the LOCAL filesystem (same pipeline as :func:`run`)."""
    emit = log or _log.info
    kstore = kstore or knowledge.KnowledgeStore(settings)
    bundles = datasource.discover_local(data_root)
    if limit:
        bundles = bundles[:limit]
    emit(f"processing {len(bundles)} local lesson bundle(s) from {data_root}")
    return _process_bundles(bundles, settings, kstore, caption, emit)


# ─────────────────────────────── CLI: python -m ksrag.process ───────────────────────────────
def _build_arg_parser():
    import argparse

    parser = argparse.ArgumentParser(
        description="Process raw docs (GCS or local) into Knowledge_chunks artifacts. "
                    "Buckets/prefixes come from .env (see app.core.config).")
    parser.add_argument("--raw-prefix", default="Data",
                        help="local root when using --local-out")
    parser.add_argument("--local-out", default="",
                        help="write artifacts to this local dir instead of GCS (dev)")
    parser.add_argument("--limit", type=int, default=None, help="only process the first N lessons")
    parser.add_argument("--no-caption", action="store_true", help="skip GPT-4o image captioning")
    return parser


def _main():
    from app.core.config import settings
    from app.services.knowledge import KnowledgeStore

    args = _build_arg_parser().parse_args()
    if args.local_out:
        print(f"local: {args.raw_prefix}/  ->  {args.local_out}/{settings.KNOWLEDGE_PREFIX}/")
        count = run_local(settings, args.raw_prefix, KnowledgeStore(settings),
                          limit=args.limit, caption=not args.no_caption)
    else:
        print(f"raw: gs://{settings.GCS_BUCKET_NAME}/{settings.RAW_PREFIX}/  ->  processed: "
              f"{settings.GCS_PROCESSED_BUCKET or settings.GCS_BUCKET_NAME}/{settings.KNOWLEDGE_PREFIX}/")
        count = run(settings, KnowledgeStore(settings), limit=args.limit,
                    caption=not args.no_caption)
    print(f"done: processed {count} lesson bundle(s)")


if __name__ == "__main__":
    _main()
