"""Generate publication artifacts for the KidSpark AI handoff package.

Markdown remains the maintainable source. This tool exports diagrams, DOCX, PDF,
and OpenAPI snapshots without reading runtime secrets.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image as RLImage,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
HANDOFF = DOCS / "handoff"
IMAGES = DOCS / "images" / "handoff"
OPENAPI = DOCS / "openapi"
RUNTIME_PYTHON = Path(sys.executable)

NAVY = "#17324D"
TEAL = "#2F7F8D"
SKY = "#E8F4F7"
CORAL = "#EF5B54"
GOLD = "#E8B84C"
INK = "#243142"
MUTED = "#667085"
LIGHT = "#F6F8FA"
GREEN = "#3A7D44"


@dataclass(frozen=True)
class Diagram:
    slug: str
    title: str
    lanes: list[tuple[str, list[str]]]
    arrows: list[tuple[int, int, str]]


DIAGRAMS = [
    Diagram(
        "system-context",
        "System Context",
        [
            ("Teacher", ["Story/PDF", "Planning decisions", "Approvals"]),
            ("KidSpark AI", ["Guided workflow", "Evidence-grounded coaching", "Validated outputs"]),
            ("External Services", ["Vertex AI", "Cloud SQL + pgvector", "Hyper3D Rodin / Bang"]),
            ("Classroom", ["BrickSmart build", "Lesson plan", "Activity guide", "Slide companion"]),
        ],
        [(0, 1, "plans"), (1, 2, "calls"), (2, 1, "returns"), (1, 3, "publishes")],
    ),
    Diagram(
        "gcp-deployment",
        "GCP Deployment",
        [
            ("Browser", ["Streamlit /kidspark", "HTTPS"]),
            ("Cloud Run: kidspark", ["Port 8080 Streamlit", "Port 8001 FastAPI (loopback)", "Ephemeral work directory"]),
            ("Managed Data", ["Cloud SQL PostgreSQL", "pgvector", "GCS raw + processed buckets"]),
            ("Managed AI + Secrets", ["Vertex AI Gemini", "Vertex embeddings", "Secret Manager"]),
        ],
        [(0, 1, "HTTPS"), (1, 2, "SQL / objects"), (1, 3, "ADC / secrets")],
    ),
    Diagram(
        "application-components",
        "Application Components",
        [
            ("Streamlit UI", ["Step rail", "Teacher coach", "Review checkpoints", "Downloads"]),
            ("FastAPI Orchestration", ["Session API", "Readiness gates", "Background jobs", "File responses"]),
            ("Domain Services", ["Agents + prompts", "RAG adapter", "3D pipeline", "Document generator"]),
            ("Validated Runtime", ["Notebook port", "Inventory planner", "Model registry", "Instruction renderer"]),
        ],
        [(0, 1, "HTTP"), (1, 2, "orchestrates"), (2, 3, "physicalizes")],
    ),
    Diagram(
        "teacher-session-sequence",
        "Teacher Session Sequence",
        [
            ("1 Upload", ["Extract story", "Analyze", "Retrieve evidence"]),
            ("2 Plan", ["Coach dialogue", "Fill readiness state", "Teacher confirms"]),
            ("3 Preview", ["Generate Rodin prompt", "Poll", "Teacher approves"]),
            ("4 Physicalize", ["Bang", "Voxelize", "Auto-simplify", "Teacher reviews"]),
            ("5 Build", ["Inventory validation", "Step images", "Approve plan"]),
            ("6 Bundle", ["Generate 3 PDFs", "Validate", "Download"]),
        ],
        [(0, 1, "gate"), (1, 2, "gate"), (2, 3, "gate"), (3, 4, "gate"), (4, 5, "gate")],
    ),
    Diagram(
        "rag-ingestion-retrieval",
        "RAG Ingestion and Retrieval",
        [
            ("Source Corpus", ["PDFs", "Lesson bundles", "Standards and policy"]),
            ("Ingestion", ["Extract nodes", "Caption selective visuals", "Normalize grade bands", "Embed"]),
            ("Storage", ["GCS artifacts", "document_bundle", "pdf_node + vectors", "standard_rules"]),
            ("Teacher Query", ["Grade-band filter", "Vector candidates", "Policy lookup", "Evidence trace"]),
            ("Planning Agent", ["Grounded suggestions", "Static fallback", "Citation lineage"]),
        ],
        [(0, 1, "process"), (1, 2, "load"), (2, 3, "retrieve"), (3, 4, "ground")],
    ),
    Diagram(
        "rodin-validated-build",
        "Rodin to Validated Build",
        [
            ("Approved Intent", ["Object", "Moving/static parts", "Kit limits"]),
            ("Rodin", ["Text-to-3D OBJ", "Teacher preview"]),
            ("Bang", ["Semantic segments", "OBJ parts"]),
            ("Notebook Port", ["Voxelize", "Merge/clean", "Contacts/connectors", "Step renders"]),
            ("Validated Planner", ["Catalog mapping", "Inventory feasibility", "Instruction status"]),
        ],
        [(0, 1, "prompt"), (1, 2, "approved OBJ"), (2, 3, "segments"), (3, 4, "physical plan")],
    ),
    Diagram(
        "document-generation",
        "Document Generation",
        [
            ("Approved Session", ["Story + framework", "Planning state", "Build plan"]),
            ("Document Agents", ["Teacher lesson plan", "Student activity guide", "Class slide companion"]),
            ("Validation", ["Required sections", "Audience tone", "No placeholders", "Notebook images"]),
            ("Publication", ["Markdown + JSON", "Three PDFs", "Teacher downloads"]),
        ],
        [(0, 1, "compose"), (1, 2, "check"), (2, 3, "publish")],
    ),
    Diagram(
        "automatic-recovery",
        "Automatic Simplification and Exception Recovery",
        [
            ("Candidate", ["OBJ + segments", "Initial voxel plan"]),
            ("Feasibility Check", ["Block budget", "Segment budget", "Preservation", "Inventory"]),
            ("Bounded Auto-Recovery", ["Tune voxel size", "Merge fragments", "Re-run planner", "Record attempts"]),
            ("Outcome", ["Valid plan", "Review-ready CSP fallback", "Teacher regeneration guidance"]),
        ],
        [(0, 1, "measure"), (1, 2, "if recoverable"), (2, 1, "retry"), (1, 3, "resolve")],
    ),
]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/aptos.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
    ]
    if bold:
        candidates = [Path("C:/Windows/Fonts/aptos-bold.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")] + candidates
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _xml_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def export_diagram(diagram: Diagram) -> None:
    width = 1600
    lane_count = len(diagram.lanes)
    columns = 3 if lane_count > 4 else 2
    rows = (lane_count + columns - 1) // columns
    height = 210 + rows * 270
    png = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(png)
    draw.rectangle((0, 0, width, 92), fill=NAVY)
    draw.text((54, 26), diagram.title, font=_font(34, True), fill="white")

    cell_w = 470 if columns == 3 else 650
    gap_x = 55
    start_x = (width - (columns * cell_w + (columns - 1) * gap_x)) // 2
    boxes: list[tuple[int, int, int, int]] = []
    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<rect width="{width}" height="92" fill="{NAVY}"/>',
        f'<text x="54" y="60" font-family="Arial" font-size="34" font-weight="700" fill="white">{_xml_escape(diagram.title)}</text>',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#667085"/></marker></defs>',
    ]
    for index, (heading, items) in enumerate(diagram.lanes):
        row, col = divmod(index, columns)
        x = start_x + col * (cell_w + gap_x)
        y = 140 + row * 270
        box = (x, y, x + cell_w, y + 205)
        boxes.append(box)
        draw.rounded_rectangle(box, radius=12, fill=LIGHT, outline=TEAL, width=3)
        draw.rectangle((x, y, x + cell_w, y + 52), fill=SKY)
        draw.text((x + 20, y + 12), heading, font=_font(24, True), fill=NAVY)
        svg_parts.extend([
            f'<rect x="{x}" y="{y}" width="{cell_w}" height="205" rx="12" fill="{LIGHT}" stroke="{TEAL}" stroke-width="3"/>',
            f'<rect x="{x}" y="{y}" width="{cell_w}" height="52" rx="12" fill="{SKY}"/>',
            f'<text x="{x+20}" y="{y+35}" font-family="Arial" font-size="24" font-weight="700" fill="{NAVY}">{_xml_escape(heading)}</text>',
        ])
        yy = y + 76
        for item in items:
            wrapped = textwrap.wrap(item, 44 if columns == 2 else 31) or [item]
            draw.ellipse((x + 22, yy + 7, x + 30, yy + 15), fill=CORAL)
            svg_parts.append(f'<circle cx="{x+26}" cy="{yy+11}" r="4" fill="{CORAL}"/>')
            for line_no, line in enumerate(wrapped):
                draw.text((x + 42, yy + line_no * 25), line, font=_font(18), fill=INK)
                svg_parts.append(f'<text x="{x+42}" y="{yy+17+line_no*25}" font-family="Arial" font-size="18" fill="{INK}">{_xml_escape(line)}</text>')
            yy += max(30, len(wrapped) * 25 + 5)

    for src, dst, label in diagram.arrows:
        if src >= len(boxes) or dst >= len(boxes):
            continue
        a, b = boxes[src], boxes[dst]
        x1, y1 = (a[2], (a[1] + a[3]) // 2) if a[0] < b[0] else ((a[0] + a[2]) // 2, a[3])
        x2, y2 = (b[0], (b[1] + b[3]) // 2) if a[0] < b[0] else ((b[0] + b[2]) // 2, b[1])
        draw.line((x1, y1, x2, y2), fill=MUTED, width=3)
        midx, midy = (x1 + x2) // 2, (y1 + y2) // 2
        draw.rounded_rectangle((midx - 54, midy - 17, midx + 54, midy + 17), radius=8, fill="white", outline="#D0D5DD")
        draw.text((midx - 45, midy - 10), label, font=_font(14), fill=MUTED)
        svg_parts.extend([
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{MUTED}" stroke-width="3" marker-end="url(#arrow)"/>',
            f'<rect x="{midx-54}" y="{midy-17}" width="108" height="34" rx="8" fill="white" stroke="#D0D5DD"/>',
            f'<text x="{midx}" y="{midy+5}" text-anchor="middle" font-family="Arial" font-size="14" fill="{MUTED}">{_xml_escape(label)}</text>',
        ])

    png.save(IMAGES / f"diagram-{diagram.slug}.png", optimize=True)
    svg_parts.append("</svg>")
    (IMAGES / f"diagram-{diagram.slug}.svg").write_text("\n".join(svg_parts), encoding="utf-8")
    mermaid = ["flowchart LR"]
    for i, (heading, items) in enumerate(diagram.lanes):
        label = f"{heading}<br/>" + "<br/>".join(items)
        mermaid.append(f'  N{i}["{label}"]')
    for src, dst, label in diagram.arrows:
        mermaid.append(f"  N{src} -->|{label}| N{dst}")
    mermaid.append("  classDef primary fill:#E8F4F7,stroke:#2F7F8D,color:#17324D,stroke-width:2px;")
    mermaid.append("  class N0,N1,N2,N3,N4,N5 primary;")
    (IMAGES / f"diagram-{diagram.slug}.mmd").write_text("\n".join(mermaid) + "\n", encoding="utf-8")


def copy_reference_visuals() -> None:
    source = ROOT / "work" / "build_jobs" / "session_9bed4a65-06d9-4eb1-9eac-4a21abfb1ecc"
    copies = {
        source / "notebook_outputs" / "segment_visualization.png": "08-segment-review.png",
        source / "notebook_outputs" / "brick_approximation.png": "09-validated-build.png",
        source / "notebook_outputs" / "notebook_step_03.png": "10-build-step.png",
        source / "notebook_outputs" / "notebook_step_03_multiview.png": "11-build-step-multiview.png",
    }
    for src, name in copies.items():
        if src.exists():
            shutil.copy2(src, IMAGES / name)


def render_bundle_contact_sheet() -> None:
    source = ROOT / "work" / "build_jobs" / "session_9bed4a65-06d9-4eb1-9eac-4a21abfb1ecc" / "lesson_bundle"
    thumbs: list[tuple[str, Image.Image]] = []
    try:
        import fitz
    except ImportError:
        return
    for label, filename in [
        ("Teacher Lesson Plan", "lesson_plan.pdf"),
        ("Student Activity Guide", "activity_guide.pdf"),
        ("Slide Companion", "slide_companion.pdf"),
    ]:
        path = source / filename
        if not path.exists():
            continue
        doc = fitz.open(path)
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(1.3, 1.3), alpha=False)
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        image.thumbnail((430, 560))
        thumbs.append((label, image.copy()))
        doc.close()
    if not thumbs:
        return
    canvas = Image.new("RGB", (1540, 720), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 1540, 82), fill=NAVY)
    draw.text((42, 23), "Validated Lesson Bundle", font=_font(30, True), fill="white")
    x = 58
    for label, image in thumbs:
        draw.rounded_rectangle((x - 10, 112, x + 450, 676), radius=10, fill=LIGHT, outline="#D0D5DD", width=2)
        draw.text((x, 126), label, font=_font(20, True), fill=NAVY)
        canvas.paste(image, (x, 168))
        x += 500
    canvas.save(IMAGES / "12-lesson-bundle.png", optimize=True)


def _shade_cell(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill.replace("#", ""))
    tc_pr.append(shd)


def _set_cell_width(cell, dxa: int) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_w = tc_pr.find(qn("w:tcW"))
    if tc_w is None:
        tc_w = OxmlElement("w:tcW")
        tc_pr.append(tc_w)
    tc_w.set(qn("w:w"), str(dxa))
    tc_w.set(qn("w:type"), "dxa")


def _add_page_number(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run("Page ")
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    run._r.addnext(fld)


def _style_doc(doc: Document, title: str, preset: str) -> None:
    section = doc.sections[0]
    section.top_margin = Inches(0.78)
    section.bottom_margin = Inches(0.72)
    section.left_margin = Inches(0.82)
    section.right_margin = Inches(0.82)
    section.header_distance = Inches(0.35)
    section.footer_distance = Inches(0.35)
    header = section.header.paragraphs[0]
    header.text = "KIDSPARK AI / BRICKSMART  |  FINAL HANDOFF"
    header.runs[0].font.name = "Aptos"
    header.runs[0].font.size = Pt(8)
    header.runs[0].font.color.rgb = RGBColor.from_string("667085")
    _add_page_number(section.footer.paragraphs[0])

    normal = doc.styles["Normal"]
    normal.font.name = "Aptos"
    normal.font.size = Pt(10.5 if preset == "compact" else 9.8)
    normal.font.color.rgb = RGBColor.from_string("243142")
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.18
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT if preset == "compact" else WD_ALIGN_PARAGRAPH.JUSTIFY
    for name, size, color, before, after in [
        ("Title", 26, "17324D", 0, 12),
        ("Heading 1", 17, "17324D", 16, 8),
        ("Heading 2", 14, "2F7F8D", 12, 6),
        ("Heading 3", 11.5, "17324D", 9, 4),
    ]:
        style = doc.styles[name]
        style.font.name = "Aptos Display" if name != "Heading 3" else "Aptos"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True
    if "Code Block" not in [s.name for s in doc.styles]:
        code_style = doc.styles.add_style("Code Block", WD_STYLE_TYPE.PARAGRAPH)
        code_style.font.name = "Consolas"
        code_style.font.size = Pt(8)
        code_style.paragraph_format.left_indent = Inches(0.18)
        code_style.paragraph_format.right_indent = Inches(0.18)
        code_style.paragraph_format.space_after = Pt(6)


def _strip_inline(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"\[([^]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    return text


def _docx_rich_paragraph(doc: Document, text: str, style: str | None = None):
    p = doc.add_paragraph(style=style)
    pattern = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)")
    pos = 0
    for match in pattern.finditer(text):
        if match.start() > pos:
            p.add_run(text[pos:match.start()])
        token = match.group(0)
        run = p.add_run(token.strip("*`"))
        if token.startswith("**"):
            run.bold = True
        elif token.startswith("*"):
            run.italic = True
        else:
            run.font.name = "Consolas"
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor.from_string("A23E34")
        pos = match.end()
    if pos < len(text):
        p.add_run(text[pos:])
    return p


def _parse_table(lines: list[str]) -> list[list[str]]:
    rows = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", c or "") for c in cells):
            continue
        rows.append(cells)
    return rows


def markdown_to_docx(source: Path, destination: Path, preset: str) -> None:
    doc = Document()
    _style_doc(doc, source.stem, preset)
    lines = source.read_text(encoding="utf-8").splitlines()
    in_code = False
    code: list[str] = []
    i = 0
    first_title = True
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            if in_code:
                p = doc.add_paragraph("\n".join(code), style="Code Block")
                _shade_cell if False else None
                code = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code.append(line)
            i += 1
            continue
        if line.strip() == "\\pagebreak":
            doc.add_page_break()
            i += 1
            continue
        image_match = re.match(r"!\[([^]]*)\]\(([^)]+)\)", line.strip())
        if image_match:
            path = (source.parent / image_match.group(2)).resolve()
            if path.exists():
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run()
                run.add_picture(str(path), width=Inches(6.55))
                cap = doc.add_paragraph(image_match.group(1))
                cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                cap.runs[0].italic = True
                cap.runs[0].font.size = Pt(8)
                cap.runs[0].font.color.rgb = RGBColor.from_string("667085")
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and lines[i + 1].startswith("|"):
            block = []
            while i < len(lines) and lines[i].startswith("|"):
                block.append(lines[i])
                i += 1
            rows = _parse_table(block)
            if rows:
                cols = max(len(r) for r in rows)
                table = doc.add_table(rows=len(rows), cols=cols)
                table.alignment = WD_TABLE_ALIGNMENT.CENTER
                table.autofit = False
                width = 9360 // cols
                for r, row in enumerate(rows):
                    for c in range(cols):
                        cell = table.cell(r, c)
                        cell.text = _strip_inline(row[c] if c < len(row) else "")
                        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                        _set_cell_width(cell, width)
                        if r == 0:
                            _shade_cell(cell, "E8F4F7")
                            for run in cell.paragraphs[0].runs:
                                run.bold = True
                                run.font.color.rgb = RGBColor.from_string("17324D")
                doc.add_paragraph().paragraph_format.space_after = Pt(2)
            continue
        if line.startswith("# "):
            p = doc.add_paragraph(style="Title" if first_title else "Heading 1")
            p.add_run(_strip_inline(line[2:]))
            first_title = False
        elif line.startswith("## "):
            doc.add_paragraph(_strip_inline(line[3:]), style="Heading 1")
        elif line.startswith("### "):
            doc.add_paragraph(_strip_inline(line[4:]), style="Heading 2")
        elif line.startswith("#### "):
            doc.add_paragraph(_strip_inline(line[5:]), style="Heading 3")
        elif re.match(r"^[-*] ", line):
            p = _docx_rich_paragraph(doc, line[2:], style="List Bullet")
            p.paragraph_format.left_indent = Inches(0.38)
            p.paragraph_format.first_line_indent = Inches(-0.18)
        elif re.match(r"^\d+\. ", line):
            body = re.sub(r"^\d+\. ", "", line)
            p = _docx_rich_paragraph(doc, body, style="List Number")
            p.paragraph_format.left_indent = Inches(0.38)
            p.paragraph_format.first_line_indent = Inches(-0.18)
        elif line.startswith("> "):
            p = _docx_rich_paragraph(doc, line[2:])
            p.paragraph_format.left_indent = Inches(0.25)
            p.paragraph_format.right_indent = Inches(0.25)
            p.paragraph_format.space_before = Pt(5)
            p.paragraph_format.space_after = Pt(8)
            for run in p.runs:
                run.font.color.rgb = RGBColor.from_string("17324D")
                run.italic = True
        elif line.strip() == "---":
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(4)
            p_pr = p._p.get_or_add_pPr()
            border = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single")
            bottom.set(qn("w:sz"), "8")
            bottom.set(qn("w:color"), "2F7F8D")
            border.append(bottom)
            p_pr.append(border)
        elif line.strip():
            _docx_rich_paragraph(doc, line)
        i += 1
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc.save(destination)


def _rl_styles(preset: str):
    base = getSampleStyleSheet()
    base.add(ParagraphStyle(name="KSBody", fontName="Helvetica", fontSize=9.2, leading=12.1, textColor=colors.HexColor(INK), alignment=TA_JUSTIFY if preset == "narrative" else TA_LEFT, spaceAfter=6))
    base.add(ParagraphStyle(name="KSTitle", fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=colors.HexColor(NAVY), alignment=TA_CENTER, spaceAfter=18))
    base.add(ParagraphStyle(name="KSH1", fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=colors.HexColor(NAVY), spaceBefore=12, spaceAfter=7))
    base.add(ParagraphStyle(name="KSH2", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=colors.HexColor(TEAL), spaceBefore=9, spaceAfter=5))
    base.add(ParagraphStyle(name="KSH3", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=colors.HexColor(NAVY), spaceBefore=7, spaceAfter=4))
    base.add(ParagraphStyle(name="KSCode", fontName="Courier", fontSize=6.8, leading=8.5, backColor=colors.HexColor("#F2F4F7"), leftIndent=8, rightIndent=8, borderPadding=5, spaceAfter=7))
    base.add(ParagraphStyle(name="KSCaption", fontName="Helvetica-Oblique", fontSize=7.2, leading=9, textColor=colors.HexColor(MUTED), alignment=TA_CENTER, spaceAfter=8))
    base.add(ParagraphStyle(name="KSQuote", fontName="Helvetica-Oblique", fontSize=9, leading=12, textColor=colors.HexColor(NAVY), leftIndent=18, rightIndent=18, backColor=colors.HexColor(SKY), borderPadding=8, spaceAfter=8))
    return base


def markdown_to_pdf(source: Path, destination: Path, preset: str) -> None:
    styles = _rl_styles(preset)
    story = []
    lines = source.read_text(encoding="utf-8").splitlines()
    in_code = False
    code: list[str] = []
    i = 0
    first_title = True
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            if in_code:
                story.append(Paragraph(_xml_escape("\n".join(code)).replace("\n", "<br/>"), styles["KSCode"]))
                code = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code.append(line)
            i += 1
            continue
        if line.strip() == "\\pagebreak":
            story.append(PageBreak())
            i += 1
            continue
        image_match = re.match(r"!\[([^]]*)\]\(([^)]+)\)", line.strip())
        if image_match:
            path = (source.parent / image_match.group(2)).resolve()
            if path.exists():
                with Image.open(path) as im:
                    w, h = im.size
                max_w, max_h = 6.85 * inch, 8.0 * inch
                scale = min(max_w / w, max_h / h)
                story.append(RLImage(str(path), width=w * scale, height=h * scale))
                story.append(Paragraph(_xml_escape(image_match.group(1)), styles["KSCaption"]))
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and lines[i + 1].startswith("|"):
            block = []
            while i < len(lines) and lines[i].startswith("|"):
                block.append(lines[i])
                i += 1
            rows = _parse_table(block)
            if rows:
                data = [[Paragraph(_xml_escape(_strip_inline(c)), styles["KSBody"]) for c in row] for row in rows]
                table = Table(data, repeatRows=1, hAlign="LEFT", colWidths=[6.8 * inch / len(data[0])] * len(data[0]))
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(SKY)),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(NAVY)),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D0D5DD")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]))
                story.append(table)
                story.append(Spacer(1, 7))
            continue
        text = _xml_escape(_strip_inline(line.lstrip("#>0123456789.- ")))
        if line.startswith("# "):
            if not first_title:
                story.append(PageBreak())
            story.append(Paragraph(text, styles["KSTitle"]))
            first_title = False
        elif line.startswith("## "):
            story.append(Paragraph(text, styles["KSH1"]))
        elif line.startswith("### "):
            story.append(Paragraph(text, styles["KSH2"]))
        elif line.startswith("#### "):
            story.append(Paragraph(text, styles["KSH3"]))
        elif re.match(r"^[-*] ", line):
            story.append(ListFlowable([ListItem(Paragraph(_xml_escape(_strip_inline(line[2:])), styles["KSBody"]))], bulletType="bullet", leftIndent=18, bulletFontSize=6))
        elif re.match(r"^\d+\. ", line):
            story.append(ListFlowable([ListItem(Paragraph(_xml_escape(_strip_inline(re.sub(r"^\d+\. ", "", line))), styles["KSBody"]))], bulletType="1", leftIndent=18))
        elif line.startswith("> "):
            story.append(Paragraph(_xml_escape(_strip_inline(line[2:])), styles["KSQuote"]))
        elif line.strip() == "---":
            story.append(Spacer(1, 8))
        elif line.strip():
            story.append(Paragraph(_xml_escape(_strip_inline(line)), styles["KSBody"]))
        i += 1

    def header_footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor(NAVY))
        canvas.rect(0, LETTER[1] - 28, LETTER[0], 28, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.setFillColor(colors.white)
        canvas.drawString(0.72 * inch, LETTER[1] - 19, "KIDSPARK AI / BRICKSMART  |  FINAL HANDOFF")
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawRightString(LETTER[0] - 0.72 * inch, 0.34 * inch, f"Page {doc.page}")
        canvas.restoreState()

    destination.parent.mkdir(parents=True, exist_ok=True)
    pdf = SimpleDocTemplate(
        str(destination),
        pagesize=LETTER,
        leftMargin=0.72 * inch,
        rightMargin=0.72 * inch,
        topMargin=0.68 * inch,
        bottomMargin=0.55 * inch,
        title=source.stem.replace("_", " "),
        author="KidSpark AI / BrickSmart Project Team",
    )
    pdf.build(story, onFirstPage=header_footer, onLaterPages=header_footer)


def export_openapi() -> None:
    os.environ.setdefault("KIDSPARK_OFFLINE_MODE", "true")
    os.environ.setdefault("DATABASE_REQUIRED", "false")
    backend = ROOT / "backend"
    sys.path.insert(0, str(backend))
    try:
        from api.main import app
    except ModuleNotFoundError as exc:
        if exc.name != "fastapi":
            raise
        app_python = shutil.which("python")
        if not app_python or Path(app_python).resolve() == Path(sys.executable).resolve():
            raise RuntimeError("Application Python with FastAPI is required to export OpenAPI") from exc
        env = os.environ.copy()
        env.setdefault("KIDSPARK_OFFLINE_MODE", "true")
        env.setdefault("DATABASE_REQUIRED", "false")
        command = (
            "import json,sys; "
            f"sys.path.insert(0, {str(backend)!r}); "
            "from api.main import app; "
            "schema=app.openapi(); "
            "schema['info']['description']='Sanitized OpenAPI snapshot for the KidSpark AI application API.'; "
            f"open({str(OPENAPI / 'kidspark-api.openapi.json')!r}, 'w', encoding='utf-8').write(json.dumps(schema, indent=2))"
        )
        subprocess.run([app_python, "-c", command], check=True, env=env, cwd=ROOT)
        return

    schema = app.openapi()
    schema["info"]["description"] = "Sanitized OpenAPI snapshot for the KidSpark AI application API."
    OPENAPI.mkdir(parents=True, exist_ok=True)
    (OPENAPI / "kidspark-api.openapi.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")


def main() -> int:
    HANDOFF.mkdir(parents=True, exist_ok=True)
    IMAGES.mkdir(parents=True, exist_ok=True)
    OPENAPI.mkdir(parents=True, exist_ok=True)
    for diagram in DIAGRAMS:
        export_diagram(diagram)
    copy_reference_visuals()
    render_bundle_contact_sheet()
    export_openapi()
    pairs = [
        (DOCS / "KIDSPARK_TECHNICAL_DESIGN.md", HANDOFF / "KidSpark_Technical_Design.docx", HANDOFF / "KidSpark_Technical_Design.pdf", "compact"),
        (DOCS / "KIDSPARK_PROJECT_OVERVIEW.md", HANDOFF / "KidSpark_Project_Overview.docx", HANDOFF / "KidSpark_Project_Overview.pdf", "narrative"),
    ]
    for source, docx, pdf, preset in pairs:
        if not source.exists():
            raise FileNotFoundError(source)
        markdown_to_docx(source, docx, preset)
        markdown_to_pdf(source, pdf, preset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
