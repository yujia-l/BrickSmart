"""Chunking on top of Docling's structured document (see ksrag.docling_loader).

Sections (heading + body) -> header-anchored text chunks, with header-respecting character overlap.
Tables -> one 'table' chunk each. Images are handled by ksrag.vision from the same Docling pictures.
No pdfplumber / pdfminer here anymore - Docling gives real reading order + semantic headings."""
import re
from dataclasses import dataclass, field
from app.services import naming


@dataclass
class Chunk:
    chunk_id: str; bundle_id: str; doc_kind: str; page_no: int; page_id: str
    kind: str = "text"                       # "text" | "table" | "image"
    header: str = ""; section: int = 0; part: int = 0
    overlap: str = ""; body: str = ""; text: str = ""
    visual_role: str = None; stage: str = None; audience: str = "teacher"
    metadata: dict = field(default_factory=dict); embedding: list = None
    @property
    def chars(self): return len(self.text)


def is_valid_pdf(path):
    """Lightweight %PDF magic-byte gate (no pdf library needed)."""
    try:
        with open(path, "rb") as f:
            return f.read(5)[:4] == b"%PDF"
    except Exception:
        return False


_STAGES = [("overview", r"overview|summary"), ("objectives", r"objective|i can"),
           ("materials", r"material|supplies"), ("vocabulary", r"vocabular|key term"),
           ("read", r"step 0?1|read|story"), ("learn_explore", r"step 0?2|learn|explore|concept"),
           ("invent", r"step 0?3|invent|build|make"), ("closure", r"closure|reflection|share"),
           ("parts_diagram", r"parts|diagram|pieces"), ("example_build", r"example|exemplar")]
_VISUAL = {"parts_diagram": "parts_diagram", "example_build": "example_build"}


def canonical_stage(header, i, n):
    hl = header.lower()
    for s, p in _STAGES:
        if re.search(p, hl):
            return s
    f = i / max(1, n - 1)
    return "overview" if f < 0.15 else ("invent" if f > 0.7 else "learn_explore")


def _window(body, budget, overlap):
    if len(body) <= budget:
        return [(body, "")]
    out, start = [], 0
    while start < len(body):
        end = min(len(body), start + budget)
        out.append((body[start:end], "" if start == 0 else body[max(0, start - overlap):start]))
        if end == len(body):
            break
        start = end
    return out


def _bundle_id(meta):
    # datasource sets meta['bundle_id'] via naming; this only falls back for standalone callers,
    # and still defers to naming so the id format is defined in ONE place (naming.py).
    return meta.get("bundle_id") or naming.bundle_name(
        meta.get("grade_band", ""), meta.get("lab", ""), meta.get("unit", ""), meta.get("lesson", ""), "")


def _node_kind(doc_kind):
    return {"teacher_plan": "teacher", "activity_guide": "activity",
            "slide_companion": "slide"}.get(doc_kind, doc_kind)


def chunk_document(doc, meta, doc_kind, max_chars=800, overlap=120, min_chars=15):
    """Docling doc dict -> text chunks (header-anchored + overlap) + one chunk per table."""
    nk = _node_kind(doc_kind)
    bid = _bundle_id(meta)
    aud = "teacher" if doc_kind == "teacher_plan" else "student"
    gb, strand = meta.get("grade_band", ""), meta.get("strand", "")
    out = []

    sections = doc.get("sections", [])
    n = len(sections)
    for si, sec in enumerate(sections):
        header, page_no, body = sec["header"], sec["page_no"], sec["text"]
        if len(body) < min_chars:
            continue
        stage = canonical_stage(header, si, n)
        pid = f"{bid}:{doc_kind}:p{page_no}"
        prefix = f"[{header}] "
        budget = max(120, max_chars - len(prefix))
        for pi, (win, ov) in enumerate(_window(body, budget, overlap)):
            out.append(Chunk(
                chunk_id=f"{nk}.{stage}.{si:02d}.{pi:02d}", bundle_id=bid, doc_kind=doc_kind,
                page_no=page_no, page_id=pid, kind="text", header=header, section=si, part=pi,
                overlap=ov, body=win, text=prefix + (ov + " " if ov else "") + win,
                visual_role=_VISUAL.get(stage), stage=stage, audience=aud,
                metadata={"grade_band": gb, "strand": strand}))

    for ti, tbl in enumerate(doc.get("tables", [])):
        page_no = tbl["page_no"]
        out.append(Chunk(
            chunk_id=f"{nk}.table.p{page_no}.{ti:02d}", bundle_id=bid, doc_kind=doc_kind,
            page_no=page_no, page_id=f"{bid}:{doc_kind}:p{page_no}", kind="table",
            header=tbl.get("header", "(table)"), section=-1, part=0, overlap="",
            body=tbl["text"], text=f"[table] {tbl['text']}", visual_role="table", stage="table",
            audience=aud, metadata={"grade_band": gb, "strand": strand}))
    return out
