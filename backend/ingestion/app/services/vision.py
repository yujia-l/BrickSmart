"""Multimodal image handling - STRUCTURED, context-grounded captioning + a separate OCR signal
(the expert-recommended caption-then-embed approach). Each Docling picture produces:

  * an IMAGE chunk whose embeddable text is a rich caption = content + educational purpose + relation
    hint (retrieves well against conceptual queries), and
  * an optional OCR chunk carrying the in-image text verbatim (so exact labels/terms like "thrust"
    retrieve well) - its own embeddable row, sharing the image's page_id.

GPT-4o Vision is grounded with document context (doc_kind, lesson, grade, nearby page text) so it never
captions in a vacuum. No API key -> Docling's own caption / a placeholder (offline-safe)."""
import base64, json
from app.services.chunking import Chunk, _bundle_id, _node_kind
from app.core.logging import get_logger

_log = get_logger("vision")

_STRUCT_PROMPT = (
    "You label an image from a K-8 STEM lesson so teachers can retrieve it by query. "
    "Return STRICT JSON with keys: image_type, content, educational_purpose, ocr_text, relation_hint.\n"
    "  image_type: one of [parts_diagram, build_step, worksheet, diagram, photo, chart, illustration, other]\n"
    "  content: what is literally depicted (objects, layout)\n"
    "  educational_purpose: the concept/skill it teaches; include grade level if inferable\n"
    "  ocr_text: text rendered IN the image (labels, instructions, worksheet words); \"\" if none\n"
    "  relation_hint: what the image is for (e.g. 'supports Step 03: Invent', 'example build')"
)


def _page_context(doc):
    """Nearby text per page (surrounding sections) to ground the captioner."""
    ctx = {}
    for s in doc.get("sections", []):
        ctx.setdefault(s["page_no"], []).append(f"[{s['header']}] {s['text'][:280]}")
    return {p: " ".join(v)[:800] for p, v in ctx.items()}


def image_chunks(doc, meta, doc_kind, settings, context=None):
    nk, bid = _node_kind(doc_kind), _bundle_id(meta)
    aud = "student" if doc_kind != "teacher_plan" else "teacher"
    page_ctx = context or _page_context(doc)
    lesson_ctx = f"lesson='{meta.get('title','')}' grade='{meta.get('grade_band','')}' doc='{doc_kind}'"
    out = []
    for pi, pic in enumerate(doc.get("pictures", [])):
        page_no = pic.get("page_no", 1)
        page_id = f"{bid}:{doc_kind}:p{page_no}"
        s = _structured_caption(pic, lesson_ctx, page_ctx.get(page_no, ""), settings)
        role = s.get("image_type") or "figure"
        caption = _compose(s)
        md = {"grade_band": meta.get("grade_band", ""), "strand": meta.get("strand", ""),
              "source": "docling", "image_type": role,
              "educational_purpose": s.get("educational_purpose", ""),
              "relation_hint": s.get("relation_hint", ""), "ocr_text": s.get("ocr_text", "")}
        out.append(Chunk(chunk_id=f"{nk}.img.p{page_no}.{pi:02d}", bundle_id=bid, doc_kind=doc_kind,
                         page_no=page_no, page_id=page_id, kind="image", header=f"(image p{page_no})",
                         visual_role=role, audience=aud, body=caption,
                         text=f"[image {role}] {caption}", metadata=md))
        # separate OCR signal — exact in-image terms as their own embeddable chunk (same page_id)
        ocr = (s.get("ocr_text") or "").strip()
        if ocr:
            out.append(Chunk(chunk_id=f"{nk}.ocr.p{page_no}.{pi:02d}", bundle_id=bid, doc_kind=doc_kind,
                             page_no=page_no, page_id=page_id, kind="ocr",
                             header=f"(in-image text p{page_no})", visual_role="ocr_text", audience=aud,
                             body=ocr, text=f"[in-image text] {ocr}", metadata=dict(md, ocr_text=ocr)))
    return out


def _compose(s):
    parts = [s.get("content", "")]
    if s.get("educational_purpose"):
        parts.append("Purpose: " + s["educational_purpose"])
    if s.get("relation_hint"):
        parts.append(s["relation_hint"])
    return ". ".join(p for p in parts if p).strip() or "(image)"


def _structured_caption(pic, lesson_ctx, page_text, settings):
    if settings.OPENAI_API_KEY and pic.get("image_bytes"):
        try:
            b64 = base64.b64encode(pic["image_bytes"]).decode()
            from openai import OpenAI
            r = OpenAI(api_key=settings.OPENAI_API_KEY).chat.completions.create(
                model=settings.VISION_MODEL, temperature=0, response_format={"type": "json_object"},
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": _STRUCT_PROMPT + f"\nContext: {lesson_ctx}\nNearby page text: {page_text}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}])
            d = json.loads(r.choices[0].message.content)
            return {k: d.get(k, "") for k in
                    ["image_type", "content", "educational_purpose", "ocr_text", "relation_hint"]}
        except Exception as e:
            _log.warning("vision caption failed (%s); using fallback", e)
    cap = pic.get("caption") or ""
    return {"image_type": "figure",
            "content": cap or "[image - set OPENAI_API_KEY for a rich caption]",
            "educational_purpose": "", "ocr_text": "", "relation_hint": ""}
