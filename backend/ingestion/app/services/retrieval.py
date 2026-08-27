"""Templated RAG retrieval for the teacher-facing API.

The teacher's FINAL prompt (after the front-end conversation loop) + the UI-selected grade come in.
This module turns that into an optimized, lineage-preserving RAG pack for the LLM finetuning agent:

  1. understand_query  -> pull {lab?, unit?, lesson?, theme, build_target, clean_query} from the prompt
  2. repository.retrieve_from_db -> grade-anchored, metadata-narrowed vector + full-text search over pdf_node
                            (the optimized JOIN: bundle context + rules come back with the nodes)
  3. rerank            -> cross-encoder precision pass over the shortlist
  4. group_by_page     -> expand to the seed bundle(s) and place IMAGES with their same-page TEXT,
                          preserving lineage (bundle -> page_id -> {text, images, tables})
  5. policies          -> the unit rules for the post-generation compliance check

Grade is authoritative (from the UI); lab/unit/lesson are only applied if inferred with confidence.
"""
import json
from collections import OrderedDict
from app.core.config import settings as _SETTINGS
from app.core.logging import get_logger
from app.api.models import model_init
from app.services import reranker, repository

_log = get_logger("rag")

_UNDERSTAND_PROMPT = (
    "You extract retrieval filters from a teacher's request to teach a K-8 STEM lesson around a "
    "storybook. Return STRICT JSON with keys: lab, unit, lesson, theme, build_target, clean_query.\n"
    "  lab/unit/lesson: best-guess name/slug ONLY if the request clearly implies it, else \"\"\n"
    "  theme: the pedagogical theme (e.g. perseverance, invention)\n"
    "  build_target: the thing students will build, if any\n"
    "  clean_query: a concise search query capturing what curriculum content to retrieve"
)

_SLIM = ("node_id", "type", "text", "doc_kind", "page_id", "page_no", "visual_role", "lesson_stage",
         "audience", "image_type", "educational_purpose", "ocr_text", "bundle_id", "bundle_name",
         "grade_band", "lab", "unit", "lesson", "image_uri", "score")


def understand_query(prompt, grade_band, settings):
    """Gemini query understanding. Falls back to the raw prompt on any model error."""
    u = {"grade_band": grade_band, "lab": "", "unit": "", "lesson": "",
         "theme": "", "build_target": "", "clean_query": prompt}
    if not settings.RAG_QUERY_UNDERSTANDING_ENABLED:
        return u
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            vertexai=True,
            project=settings.GCP_PROJECT_ID,
            location=settings.VERTEX_GENERATION_LOCATION,
        )
        d = None
        for model in (settings.GEMINI_PRIMARY_MODEL, settings.GEMINI_FALLBACK_MODEL):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=f"Grade: {grade_band}\nRequest: {prompt}",
                    config=types.GenerateContentConfig(
                        system_instruction=_UNDERSTAND_PROMPT,
                        temperature=0,
                        response_mime_type="application/json",
                        response_schema={
                            "type": "object",
                            "properties": {
                                key: {"type": "string"}
                                for key in ("lab", "unit", "lesson", "theme", "build_target", "clean_query")
                            },
                        },
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                    ),
                )
                d = json.loads(response.text)
                break
            except Exception:
                continue
        if d is None:
            raise RuntimeError("both Gemini query-understanding models failed")
        for k in ("lab", "unit", "lesson", "theme", "build_target", "clean_query"):
            if d.get(k):
                u[k] = d[k]
    except Exception as e:
        _log.warning("query understanding failed (%s); using raw prompt", e)
    return u


def _slim(n):
    return {k: n.get(k) for k in _SLIM}


def _group_by_page(bundle_rows, nodes):
    """bundle -> ordered pages -> {text, images, tables}. Images (+OCR) land on their own page_id,
    beside the same-page text, so multimodal lineage is preserved for the agent."""
    byb = {b["bundle_id"]: {**{k: b.get(k) for k in ("bundle_id", "bundle_name", "grade_band", "lab",
                                                     "unit", "lesson")}, "pages": OrderedDict()}
           for b in bundle_rows}
    for n in nodes:
        b = byb.setdefault(n["bundle_id"], {"bundle_id": n["bundle_id"], "bundle_name": n.get("bundle_name"),
                                            "grade_band": n.get("grade_band"), "lab": n.get("lab"),
                                            "unit": n.get("unit"), "lesson": n.get("lesson"),
                                            "pages": OrderedDict()})
        pg = b["pages"].setdefault(n["page_id"], {"page_id": n["page_id"], "page_no": n.get("page_no"),
                                                  "doc_kind": n.get("doc_kind"),
                                                  "text": [], "images": [], "tables": []})
        item = _slim(n)
        t = n.get("type")
        if t in ("figure",) or t == "ocr":
            pg["images"].append(item)
        elif t == "table":
            pg["tables"].append(item)
        else:
            pg["text"].append(item)
    out = []
    for b in byb.values():
        pages = sorted(b["pages"].values(), key=lambda p: (p.get("page_no") or 0))
        out.append({**{k: v for k, v in b.items() if k != "pages"}, "pages": pages})
    return out


def templated_retrieve(prompt, grade_band, filters=None, k=40, seed_k=8, rerank=True,
                       settings=None, dbu=None):
    settings = settings or _SETTINGS
    dbu = dbu or model_init.DBUtil(settings)

    u = understand_query(prompt, grade_band, settings)
    f = {"grade_band": grade_band}                       # grade is authoritative (from the UI)
    for col in ("lab", "unit", "lesson"):
        v = (filters or {}).get(col) or u.get(col)
        if v:
            f[col] = v
    query = u.get("clean_query") or prompt

    # 1-2. filtered vector + full-text retrieval over the fact table (bundle + rules joined in)
    res = repository.retrieve_from_db(query, settings=settings, filters=f, k=k, seed_k=seed_k, hybrid=True, db=dbu)
    if not res["seeds"] and set(f) - {"grade_band"}:
        _log.info(
            "Inferred metadata filters returned no results; retrying with authoritative grade only."
        )
        f = {"grade_band": grade_band}
        res = repository.retrieve_from_db(
            query,
            settings=settings,
            filters=f,
            k=k,
            seed_k=seed_k,
            hybrid=True,
            db=dbu,
        )
    seeds = res["seeds"]

    # 3. rerank the shortlist for precision
    if rerank and seeds:
        for s in seeds:
            s.setdefault("content", s.get("text", ""))
        seeds = reranker.get_reranker(settings).rerank(query, seeds, seed_k)

    # 4. expand to seed bundle(s) and group by page (images with same-page text = lineage)
    bundle_ids = list(dict.fromkeys(s["bundle_id"] for s in seeds)) if seeds \
        else [b["bundle_id"] for b in res["bundles"]]
    all_nodes = repository.nodes_for_bundles(bundle_ids, dbu) if bundle_ids else []
    bundles = _group_by_page(res["bundles"], all_nodes)

    _log.info("templated_retrieve: grade=%s filters=%s -> %d seeds, %d bundle(s), %d policy rule(s)",
              grade_band, f, len(seeds), len(bundles), len(res["rules"]))
    return {"query": prompt, "understood": u, "filters": f,
            "seeds": [_slim(s) for s in seeds],
            "bundles": bundles,
            "policies": res["rules"]}
