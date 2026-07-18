"""Processed-knowledge layer. Assembles the four required artifacts from a lesson's chunks and writes
them to GCS under Knowledge_chunks/ (or a local mirror for dev). Naming is 100% derived from the raw
path via ksrag.naming - never hard-coded.

  Knowledge_chunks/bundles/<bundle_name>/{bundle.json, nodes.json, relations.json}
  Knowledge_chunks/policies/<policy_scope>/rules.json
"""
import json
from collections import defaultdict
from app.services import naming, provenance
from app.core.logging import get_logger

_log = get_logger("knowledge")


# ─────────────────────────── artifact assembly ───────────────────────────
def assemble_nodes(chunks, prov_by_doc):
    """One node per chunk: text (header already inside its text), figures(=images), tables, OCR."""
    nodes = []
    for c in chunks:
        prov = prov_by_doc.get(c.doc_kind, {})
        # No separate heading node: the section header is already embedded in each chunk's text
        # (the "[Header] ..." prefix), and section grouping is kept via section_header + chunk_id.
        if c.kind == "image":
            ntype = "figure"
        elif c.kind == "table":
            ntype = "table"
        elif c.stage == "objectives":
            ntype = "learning_objective"
        else:
            ntype = "text"
        md = c.metadata or {}
        nodes.append({
            "node_id": c.chunk_id, "type": ntype, "text": c.text,
            "doc_kind": c.doc_kind, "page_no": c.page_no, "page_id": c.page_id,
            "section_header": c.header, "lesson_stage": c.stage, "visual_role": c.visual_role,
            "audience": c.audience,
            "image_type": md.get("image_type"), "educational_purpose": md.get("educational_purpose"),
            "ocr_text": md.get("ocr_text"), "relation_hint": md.get("relation_hint"),
            "provenance": prov,
        })
    # reserved node classes we don't NLP-extract yet, kept for schema stability
    return nodes


def assemble_relations(chunks, bundle_id):
    """Graph edges: parent-child, sequence (next), page co-location, and cross-document links."""
    rels = []
    def edge(s, t, ty): rels.append({"source": s, "target": t, "type": ty})
    # parent-child: bundle contains every node
    for c in chunks:
        edge(bundle_id, c.chunk_id, "parent_child")
    # sequence within a section
    by_sec = defaultdict(list)
    for c in chunks:
        if c.kind == "text":
            by_sec[(c.doc_kind, c.section)].append(c)
    for grp in by_sec.values():
        grp.sort(key=lambda c: c.part)
        for a, b in zip(grp, grp[1:]):
            edge(a.chunk_id, b.chunk_id, "next")
    # cross reference: image <-> text on the same page (multimodal linkage)
    by_page = defaultdict(lambda: {"img": [], "txt": []})
    for c in chunks:
        by_page[c.page_id]["img" if c.kind == "image" else "txt"].append(c.chunk_id)
    for g in by_page.values():
        for im in g["img"]:
            for tx in g["txt"]:
                edge(im, tx, "co_located_on_page")
    # cross-document links (teacher <-> activity <-> slide) by shared lesson_stage — this is what
    # connects the three files under one bundle. One representative chunk per (doc, stage) keeps it compact.
    rep = {}
    for c in chunks:
        if c.stage:
            rep.setdefault((c.doc_kind, c.stage), c.chunk_id)
    for stg in {stage for (_dk, stage) in rep}:
        tp, ag, sc = rep.get(("teacher_plan", stg)), rep.get(("activity_guide", stg)), rep.get(("slide_companion", stg))
        if tp and ag:
            edge(tp, ag, "mirrored_by" if stg == "closure" else "uses_example_from" if stg == "invent" else "parallels")
        if tp and sc:
            edge(tp, sc, "visualized_by")
        if ag and sc:
            edge(ag, sc, "visualized_by")
    return rels


def assemble_bundle(meta, docs, chunks, prov, policy_scope, policy_path, manifest_path):
    """The canonical lesson bundle."""
    text_chunks = [c for c in chunks if c.kind == "text"]
    sections = [{"section_index": c.section, "header": c.header, "page_no": c.page_no,
                 "doc_kind": c.doc_kind, "chunk_id": c.chunk_id, "part": c.part}
                for c in text_chunks]
    return {
        "bundle_id": prov["bundle_id"], "bundle_name": prov["bundle_name"],
        "lesson_metadata": {"grade_band": meta["grade_band"], "lab": meta["lab"],
                            "unit": meta["unit"], "lesson": meta.get("lesson", ""),
                            "title": meta.get("title", meta.get("lesson", ""))},
        "document_metadata": docs,
        "parsed_sections": sections,
        "parsed_tables": [{"page_no": c.page_no, "header": c.header, "chunk_id": c.chunk_id,
                           "markdown": c.body} for c in chunks if c.kind == "table"],
        "chunk_references": [c.chunk_id for c in chunks],
        "source_lineage": prov,
        "manifest_references": {"manifest_path": manifest_path},
        "policy_references": {"policy_scope": policy_scope, "policy_path": policy_path},
    }


def assemble_rules(meta, policy_scope, prov, standards_source=None):
    """Unit-level policy shared by every lesson in the unit."""
    frameworks = ["NGSS", "CASEL", "UDL", "SoR"]
    rules = [{
        "rule_id": provenance.rule_id(policy_scope, i), "framework": fw,
        "grade_band": meta["grade_band"], "lab": meta["lab"], "unit": meta["unit"],
        "scope": policy_scope, "applies_to": "all lessons in unit",
        "text": f"(populate from Standards Alignment document for {fw})",
    } for i, fw in enumerate(frameworks)]
    return {"policy_scope": policy_scope,
            "unit": {"grade_band": meta["grade_band"], "lab": meta["lab"], "unit": meta["unit"]},
            "standards_source": standards_source, "rules": rules,
            "provenance": prov, "referenced_by_bundles": []}


# ─────────────────────────── writer (GCS or local mirror) ───────────────────────────
class KnowledgeStore:
    def __init__(self, settings):
        self.s = settings

    def _write(self, rel_path, obj):
        full = f"{self.s.KNOWLEDGE_PREFIX}/{rel_path}"
        data = json.dumps(obj, indent=2, ensure_ascii=False)
        if self.s.KNOWLEDGE_LOCAL_DIR:
            import os
            path = os.path.join(self.s.KNOWLEDGE_LOCAL_DIR, full)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w", encoding="utf-8").write(data)
            return path
        from app.utils.gcs import get_client
        out_bucket = self.s.GCS_PROCESSED_BUCKET or self.s.GCS_BUCKET_NAME
        get_client().bucket(out_bucket).blob(full).upload_from_string(
            data, content_type="application/json")
        uri = f"gs://{out_bucket}/{full}"
        _log.debug("wrote %s", uri)
        return uri

    def write_bundle(self, bundle_name, bundle, nodes, relations):
        base = f"bundles/{bundle_name}"
        return [self._write(f"{base}/bundle.json", bundle),
                self._write(f"{base}/nodes.json", nodes),
                self._write(f"{base}/relations.json", relations)]

    def write_policy(self, policy_scope, rules):
        return self._write(f"policies/{policy_scope}/rules.json", rules)
