"""Multimodal image handling with stable crops and selective visual embeddings.
(the expert-recommended caption-then-embed approach). Each Docling picture produces:

  * an IMAGE chunk whose embeddable text is a rich caption = content + educational purpose + relation
    hint (retrieves well against conceptual queries), and
  * an optional OCR chunk carrying the in-image text verbatim (so exact labels/terms like "thrust"
    retrieve well) - its own embeddable row, sharing the image's page_id.

GPT-4o Vision is grounded with document context (doc_kind, lesson, grade, nearby page text) so it never
captions in a vacuum. No API key -> Docling's own caption / a placeholder (offline-safe)."""
import json
import os
from app.services.chunking import Chunk, _bundle_id, _node_kind
from app.services.embeddings import embed_image
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
        image_uri = _persist_crop(
            pic.get("image_bytes"),
            bid,
            doc_kind,
            page_no,
            pi,
            settings,
        )
        visual_embedding = None
        selected_roles = {
            item.strip()
            for item in settings.VISUAL_EMBED_ROLES.split(",")
            if item.strip()
        }
        if pic.get("image_bytes") and role in selected_roles:
            try:
                visual_embedding = embed_image(pic["image_bytes"], caption, settings)
            except Exception as exc:
                _log.warning("visual embedding failed for %s: %s", image_uri or page_id, exc)
        md = {"grade_band": meta.get("grade_band", ""), "strand": meta.get("strand", ""),
              "source": "docling", "image_type": role,
              "educational_purpose": s.get("educational_purpose", ""),
              "relation_hint": s.get("relation_hint", ""), "ocr_text": s.get("ocr_text", ""),
              "image_uri": image_uri, "visual_embedding": visual_embedding,
              "visual_embedding_model": settings.VISUAL_EMBED_MODEL if visual_embedding else None}
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
    if pic.get("image_bytes"):
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(
                vertexai=True,
                project=settings.GCP_PROJECT_ID,
                location=settings.VERTEX_GENERATION_LOCATION,
            )
            d = None
            for model in (settings.VISION_MODEL, settings.VISION_FALLBACK_MODEL):
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=[
                            types.Part.from_text(
                                text=f"Context: {lesson_ctx}\nNearby page text: {page_text}"
                            ),
                            types.Part.from_bytes(
                                data=pic["image_bytes"],
                                mime_type="image/png",
                            ),
                        ],
                        config=types.GenerateContentConfig(
                            system_instruction=_STRUCT_PROMPT,
                            temperature=0,
                            response_mime_type="application/json",
                            response_schema={
                                "type": "object",
                                "properties": {
                                    key: {"type": "string"}
                                    for key in (
                                        "image_type",
                                        "content",
                                        "educational_purpose",
                                        "ocr_text",
                                        "relation_hint",
                                    )
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
                raise RuntimeError("both Gemini image-caption models failed")
            return {k: d.get(k, "") for k in
                    ["image_type", "content", "educational_purpose", "ocr_text", "relation_hint"]}
        except Exception as e:
            _log.warning("vision caption failed (%s); using fallback", e)
    cap = pic.get("caption") or ""
    return {"image_type": "figure",
            "content": cap or "[image - Vertex caption unavailable]",
            "educational_purpose": "", "ocr_text": "", "relation_hint": ""}


def _persist_crop(image_bytes, bundle_id, doc_kind, page_no, picture_index, settings):
    if not image_bytes or not settings.SAVE_IMAGE_CROPS:
        return None
    relative = (
        f"{settings.KNOWLEDGE_PREFIX}/images/{bundle_id}/{doc_kind}/"
        f"p{int(page_no):04d}-{int(picture_index):03d}.png"
    )
    if settings.KNOWLEDGE_LOCAL_DIR:
        path = os.path.join(settings.KNOWLEDGE_LOCAL_DIR, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(image_bytes)
        return path
    from app.utils.gcs import get_client

    bucket_name = settings.GCS_PROCESSED_BUCKET or settings.GCS_BUCKET_NAME
    get_client().bucket(bucket_name).blob(relative).upload_from_string(
        image_bytes,
        content_type="image/png",
    )
    return f"gs://{bucket_name}/{relative}"
