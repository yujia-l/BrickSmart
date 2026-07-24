"""Multimodal image handling — STRUCTURED, context-grounded captioning + a separate OCR signal
(the expert-recommended caption-then-embed approach). Each Docling picture produces:

  * an IMAGE chunk whose embeddable text is a rich caption = content + educational purpose + relation
    hint (retrieves well against conceptual queries), and
  * an optional OCR chunk carrying the in-image text verbatim (so exact labels/terms like "thrust"
    retrieve well) — its own embeddable row, sharing the image's page_id.

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


_CAPTION_FIELDS = ["image_type", "content", "educational_purpose", "ocr_text", "relation_hint"]


def _coerce(d):
    """Keep only the expected keys; guarantee every value is a string (never None)."""
    return {k: (str(d.get(k)).strip() if d.get(k) is not None else "") for k in _CAPTION_FIELDS}


def _parse_json_lenient(text):
    """json.loads, but tolerate models that wrap JSON in prose / code fences."""
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        i, j = text.find("{"), text.rfind("}")
        if i != -1 and j != -1 and j > i:
            try:
                return json.loads(text[i:j + 1])
            except Exception:
                return None
    return None


def _openai_caption(b64, prompt, settings):
    """Primary captioner: OpenAI Vision. Adapts request params by model family — reasoning models
    (gpt-5.x / o-series) reject `temperature` and use `max_completion_tokens`; classic chat models
    (gpt-4o and older) use `temperature` + `max_tokens`. Returns a fields dict, or None."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        model = settings.VISION_MODEL or "gpt-5.6-luna"
        messages = [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]
        params = {"model": model, "messages": messages,
                  "response_format": {"type": "json_object"}}
        if model.startswith(("gpt-5", "o1", "o3", "o4")):      # reasoning models
            params["max_completion_tokens"] = 1500             # room for reasoning + JSON output
            params["reasoning_effort"] = "low"                 # captions don't need deep reasoning
        else:                                                  # gpt-4o and older chat models
            params["temperature"] = 0
            params["max_tokens"] = 700
        for attempt in range(2):
            r = client.chat.completions.create(**params)
            choice = r.choices[0]
            content = choice.message.content
            if content:
                d = _parse_json_lenient(content)
                if d:
                    return _coerce(d)
            refusal = getattr(choice.message, "refusal", None)
            _log.warning("openai caption empty (model=%s, finish_reason=%s, refusal=%s) attempt %d/2",
                         model, choice.finish_reason, (refusal or "").strip()[:200], attempt + 1)
    except Exception as e:
        _log.warning("openai caption failed (%s: %s)", type(e).__name__, e)
    return None


def _ollama_caption(b64, prompt, settings):
    """Local fallback: an Ollama vision model (e.g. llava / moondream). No API key, offline,
    no content refusals. Returns a fields dict, or None if Ollama isn't reachable/installed."""
    import urllib.request
    host = (getattr(settings, "OLLAMA_HOST", "") or "http://localhost:11434").rstrip("/")
    model = getattr(settings, "OLLAMA_VISION_MODEL", "") or "llava"
    body = json.dumps({
        "model": model, "prompt": prompt, "images": [b64],
        "format": "json", "stream": False, "options": {"temperature": 0},
    }).encode()
    try:
        req = urllib.request.Request(host + "/api/generate", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode())
        d = _parse_json_lenient(data.get("response", ""))
        if d:
            _log.info("ollama caption ok (model=%s)", model)
            return _coerce(d)
        _log.warning("ollama caption returned no JSON (model=%s)", model)
    except Exception as e:
        _log.warning("ollama caption failed (%s: %s) — is Ollama running and '%s' pulled?",
                     type(e).__name__, e, model)
    return None


def _structured_caption(pic, lesson_ctx, page_text, settings):
    """Caption one picture, trying providers in order: OpenAI -> local Ollama -> docling/OCR text."""
    prompt = _STRUCT_PROMPT + f"\nContext: {lesson_ctx}\nNearby page text: {page_text}"
    if pic.get("image_bytes"):
        b64 = base64.b64encode(pic["image_bytes"]).decode()
        if settings.OPENAI_API_KEY:
            d = _openai_caption(b64, prompt, settings)
            if d and d.get("content"):
                return d
        if getattr(settings, "CAPTION_FALLBACK", True):
            d = _ollama_caption(b64, prompt, settings)
            if d and d.get("content"):
                return d
    # last resort: docling's own embedded caption if present, else a labelled placeholder
    cap = pic.get("caption") or ""
    return {"image_type": "figure",
            "content": cap or "[image — no captioner available (set OPENAI_API_KEY or run Ollama)]",
            "educational_purpose": "", "ocr_text": "", "relation_hint": ""}
