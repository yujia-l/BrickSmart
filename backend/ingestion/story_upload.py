"""Story source extraction helpers for runtime teacher uploads."""

from __future__ import annotations

from io import BytesIO


def extract_story_text(filename: str, data: bytes) -> str:
    """Extract text from a teacher-uploaded PDF or text file."""
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix == "pdf":
        return extract_pdf_text(data)
    if suffix in {"txt", "md"}:
        return data.decode("utf-8", errors="ignore").strip()
    raise ValueError("Upload a PDF, TXT, or MD story source.")


def extract_pdf_text(data: bytes) -> str:
    """Extract readable text from a PDF using the lightweight local parser."""
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("pypdf is required for PDF story uploads.") from exc

    reader = PdfReader(BytesIO(data))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = text.strip()
        if text:
            pages.append(f"[Page {index}]\n{text}")
    extracted = "\n\n".join(pages).strip()
    if not extracted:
        raise ValueError("No readable text was found in this PDF.")
    return extracted
