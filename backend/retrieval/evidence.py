"""
KidSpark AI — Evidence Pack Assembly
Owner: Developer B

The bridge entry point the generation pipeline calls. It builds the retrieval query from BOTH the
final teacher-consultation prompt AND the 3D/Lego block context (build target + a caption of the
block image), runs hybrid search + bundle/page expansion + policy fetch, and assembles a typed
EvidencePack (teacher / student / visual / policy cards + trace) that grounds the 3 PDFs.

Public:
  build_evidence_pack(EvidenceRequest)         -> EvidencePack
  request_from_session(summary, blocks, ...)   -> EvidenceRequest   (from Dev B session objects)
  caption_block_image(image_bytes|path)        -> str               (best-effort, seeds the query)
"""
import base64
import logging

import config
from models.schemas import EvidenceCard, EvidencePack, EvidenceRequest, TraceEntry
from retrieval import search, expansion

logger = logging.getLogger(__name__)


# ── query composition: teacher prompt + block/3D image is the retrieval basis ──────────────────
def compose_query(prompt: str, block_context: str = "", image_caption: str = "") -> str:
    parts = [prompt or ""]
    if block_context:
        parts.append("Build target: " + block_context)
    if image_caption:
        parts.append("Lego block model: " + image_caption)
    return "\n".join(p for p in parts if p).strip()


def caption_block_image(image_bytes: bytes | None = None, image_path: str | None = None) -> str:
    """Best-effort caption of the rendered 3D Lego build so the image can seed retrieval.
    Returns '' if no image or captioning fails (the pipeline still works from the text prompt)."""
    if image_bytes is None and image_path:
        try:
            with open(image_path, "rb") as fh:
                image_bytes = fh.read()
        except OSError:
            return ""
    if not image_bytes or not config.OPENAI_API_KEY:
        return ""
    try:
        from openai import OpenAI
        b64 = base64.b64encode(image_bytes).decode()
        client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=30, max_retries=0)
        r = client.chat.completions.create(
            model=config.OPENAI_MODEL, max_tokens=120,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "Describe this Lego/Kid Spark block model in one sentence: "
                                         "what object it is and its main visible parts."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}])
        return (r.choices[0].message.content or "").strip()
    except Exception as e:  # noqa: BLE001 — captioning is best-effort
        logger.warning("block image caption failed (%s: %s)", type(e).__name__, e)
        return ""


# ── card assembly ───────────────────────────────────────────────────────────────────────────
def _visual_ref(row) -> str | None:
    path = row.get("gcs_object_path")
    if not path:
        return None
    ref = f"gs://{config.GCS_PROCESSED_BUCKET}/{path}"
    page = row.get("page_no")
    return f"{ref}#page={page}" if page else ref


def _card(row) -> EvidenceCard:
    return EvidenceCard(
        node_id=row.get("node_id", ""), bundle_id=row.get("bundle_id", ""),
        content_text=row.get("text") or "", doc_kind=row.get("doc_kind") or "",
        audience=row.get("audience") or "", lesson_stage=row.get("lesson_stage") or "",
        relevance_score=float(row.get("score") or 0.0),
        visual_ref=_visual_ref(row), image_type=row.get("image_type") or None,
    )


def _policy_card(rule) -> EvidenceCard:
    return EvidenceCard(
        node_id=rule.get("rule_id") or "", bundle_id=rule.get("bundle_name") or rule.get("policy_scope") or "",
        content_text=rule.get("text") or "", doc_kind="policy",
        audience="teacher", lesson_stage="", relevance_score=0.0,
    )


def _is_visual(row) -> bool:
    return bool(row.get("visual_role")) or (row.get("doc_kind") == "" and row.get("image_type"))


def build_evidence_pack(req: EvidenceRequest) -> EvidencePack:
    """Retrieve and organize the evidence that grounds the 3 lesson PDFs."""
    query = compose_query(req.prompt, req.block_context or "", req.image_caption or "")
    filters = {"grade_band": req.grade_band or None, "lab": req.lab or None, "unit": req.unit or None}
    if req.doc_kinds:
        # doc_kind is single-valued in the SQL filter; when multiple are requested we filter post-hoc.
        pass

    seeds = search.hybrid_search(query, filters, k=req.k)
    if req.doc_kinds:
        seeds = [s for s in seeds if s.get("doc_kind") in set(req.doc_kinds)] or seeds
    seeds = seeds[: req.seed_k]

    # expand: whole lesson (by bundle) + page co-location (image <-> text)
    collected = {s["node_id"]: s for s in seeds}
    for row in expansion.expand_bundles([s["bundle_id"] for s in seeds], req.expand_bundles):
        collected.setdefault(row["node_id"], dict(row, score=0.0))
    for row in expansion.expand_pages([s["page_id"] for s in seeds if s.get("page_id")]):
        collected.setdefault(row["node_id"], dict(row, score=0.0))
    rows = sorted(collected.values(), key=lambda r: r.get("score") or 0.0, reverse=True)

    policies = search.fetch_policies(filters, limit=req.policy_k)

    teacher, student, visual = [], [], []
    for r in rows:
        if _is_visual(r):
            visual.append(_card(r))
        elif r.get("audience") == "student":
            student.append(_card(r))
        else:
            teacher.append(_card(r))

    trace = [TraceEntry(node_id=s["node_id"], bundle_id=s["bundle_id"], score=float(s.get("score") or 0.0),
                        retrieval_reason="hybrid_seed") for s in seeds]

    return EvidencePack(
        teacher_cards=teacher, student_cards=student, visual_cards=visual,
        policy_cards=[_policy_card(p) for p in policies], trace=trace,
    )


# ── convenience: build a request straight from Dev B session objects ───────────────────────────
def request_from_session(consultation_summary, block_requirements=None, image_caption: str = "",
                         k: int = 30, seed_k: int = 8) -> EvidenceRequest:
    """Assemble an EvidenceRequest from the consultation summary + block requirements (+ block image
    caption). This is where 'final teacher prompt + Lego block image' becomes the retrieval basis."""
    cs = consultation_summary
    prompt = "; ".join(p for p in [
        f"Theme: {getattr(cs, 'agreed_theme', '')}",
        f"Artifact: {getattr(cs, 'agreed_artifact', '')}",
        "Objectives: " + "; ".join(getattr(cs, "learning_objectives", []) or []),
        f"Literacy focus: {getattr(cs, 'literacy_focus', '')}",
        f"SEL focus: {getattr(cs, 'sel_focus', '')}",
    ] if p and not p.endswith(": "))

    block_context = ""
    if block_requirements is not None:
        parts = getattr(block_requirements, "parts", []) or []
        label = getattr(block_requirements, "artifact_label", "")
        block_context = (f"{label}: " + "; ".join(
            f"{getattr(p, 'part_name', '')} ({getattr(p, 'movement', '')})" for p in parts)).strip(": ")

    return EvidenceRequest(
        prompt=prompt, grade_band=getattr(cs, "grade_band", "") or "",
        block_context=block_context or None, image_caption=image_caption or None,
        k=k, seed_k=seed_k,
    )
