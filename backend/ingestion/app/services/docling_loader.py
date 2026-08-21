"""Docling-based loader. One converter turns a PDF into a structured
DoclingDocument with real reading order, semantic headings, tables, and page-linked pictures — the
foundation for multimodal RAG. See https://docling-project.github.io/docling/examples/custom_convert/

load_document(path, settings) -> {
    "sections":  [{header, page_no, text}],     # heading + body, from SECTION_HEADER/TITLE labels
    "tables":    [{header, page_no, text}],      # markdown of each detected table
    "pictures":  [{page_no, image_bytes, caption}],  # image bytes for GPT-4o captioning
    "page_count": int,
}
Architecture is unchanged — the chunker/vision/knowledge/store layers consume this dict exactly like
before; only the parser swapped.
"""
import io
from app.core.logging import get_logger

_log = get_logger("docling")
_CONVERTER = None


def _converter(settings):
    """Build (once) a Docling converter configured for tables + picture images."""
    global _CONVERTER
    if _CONVERTER is not None:
        return _CONVERTER
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = bool(getattr(settings, "DOCLING_OCR", False))
    opts.do_table_structure = bool(getattr(settings, "DOCLING_TABLES", True))
    opts.table_structure_options.do_cell_matching = True
    opts.generate_picture_images = True                       # keep picture bitmaps for captioning
    opts.images_scale = float(getattr(settings, "DOCLING_IMAGE_SCALE", 2.0))
    _CONVERTER = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    return _CONVERTER


def load_document(path, settings):
    from docling_core.types.doc import DocItemLabel
    from docling_core.types.doc.document import TextItem, TableItem, PictureItem

    doc = _converter(settings).convert(path).document

    sections, cur = [], {"header": "(start)", "page_no": 1, "lines": []}
    tables, pictures = [], []
    for item, _level in doc.iterate_items():
        page_no = item.prov[0].page_no if getattr(item, "prov", None) else cur["page_no"]

        if isinstance(item, TextItem):
            text = (item.text or "").strip()
            if not text:
                continue
            if item.label in (DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE):
                if cur["lines"]:
                    sections.append(cur)
                cur = {"header": text, "page_no": page_no, "lines": []}
            else:
                cur["lines"].append(text)

        elif isinstance(item, TableItem):
            try:
                md = item.export_to_markdown(doc)
            except TypeError:
                md = item.export_to_markdown()
            tables.append({"header": cur["header"], "page_no": page_no, "text": md})

        elif isinstance(item, PictureItem):
            img_bytes = None
            try:
                pil = item.get_image(doc)
                if pil is not None:
                    buf = io.BytesIO(); pil.save(buf, format="PNG"); img_bytes = buf.getvalue()
            except Exception:
                pass
            caption = ""
            try:
                caption = item.caption_text(doc) or ""
            except Exception:
                pass
            pictures.append({"page_no": page_no, "image_bytes": img_bytes, "caption": caption})

    if cur["lines"]:
        sections.append(cur)
    for s in sections:
        s["text"] = "\n".join(s["lines"]).strip()

    page_count = 0
    try:
        page_count = len(doc.pages)
    except Exception:
        pass
    _log.info("docling parsed %s: %d sections, %d tables, %d pictures",
              path.split("/")[-1], len(sections), len(tables), len(pictures))
    return {"sections": sections, "tables": tables, "pictures": pictures, "page_count": page_count}
