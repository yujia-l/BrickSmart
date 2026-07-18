"""Data source — reads the RAW layout (GCS or local) and preserves every path component as metadata.

  raw_documents/<grade_band>/<lab>/<unit>/<lesson>/<filename>

discover(settings)        -> from GCS   (downloads PDFs to a temp cache)
discover_local(data_root) -> from disk

Both return [(meta, pdfs)] with the SAME shape, so chunking / process consume them identically:
  meta = {grade_band, lab, unit, lesson, title, raw_folder, bundle_id,
          documents:[{doc_kind, filename, gcs_object_path}]}
  pdfs = {doc_kind: LOCAL_path}

Identity (`bundle_id`) and doc-kind classification are computed HERE, once, so downstream modules
(chunking, process) never re-derive them.
"""
import os, tempfile
from app.services import naming
from app.core.logging import get_logger

_log = get_logger("datasource")

# Single source of truth: filename (or stem) -> canonical document kind. Used by BOTH discover paths.
_DOC_KINDS = {
    "teacher_plan":      ["teacher lesson plan", "teacher plan", "teacher"],
    "activity_guide":    ["activity guide", "activity"],
    "slide_companion":   ["student companion", "slide companion", "companion", "slide"],
    "curriculum_packet": ["curriculum packet"],
    "student_workbook":  ["student engineering workbook", "workbook"],
}


def detect_doc_kind(name):
    """Filename or stem -> canonical doc_kind, or None if it matches no known type."""
    n = name.lower()
    for kind, needles in _DOC_KINDS.items():
        if any(x in n for x in needles):
            return kind
    return None


def _lesson_meta(grade_band, lab, unit, lesson, raw_folder, documents):
    """Assemble the shared meta, including the deterministic bundle_id (identity lives in naming.py)."""
    primary = next((d["filename"] for d in documents if d["doc_kind"] == "teacher_plan"),
                   documents[0]["filename"] if documents else "")
    return {"grade_band": grade_band, "lab": lab, "unit": unit, "lesson": lesson,
            "title": lesson or unit, "raw_folder": raw_folder, "documents": documents,
            "bundle_id": naming.bundle_name(grade_band, lab, unit, lesson, primary)}


def discover(settings):
    if not settings.GCS_BUCKET_NAME:
        raise ValueError("Settings.GCS_BUCKET_NAME is required — this data source reads from GCS only.")
    from app.utils.gcs import get_client
    client = get_client()
    base = (settings.GCS_PREFIX.strip("/") + "/" if settings.GCS_PREFIX else "") + settings.RAW_PREFIX + "/"
    cache = tempfile.mkdtemp(prefix="ksrag_raw_")
    _log.info("listing gs://%s/%s", settings.GCS_BUCKET_NAME, base)

    lessons = {}   # (grade,lab,unit,lesson) -> list[(filename, blob)]
    for blob in client.list_blobs(settings.GCS_BUCKET_NAME, prefix=base):
        rel = blob.name[len(base):]
        if not rel or rel.endswith("/"):
            continue
        info = naming.parse_raw_path(rel, raw_prefix="")   # rel already stripped of base
        key = (info["grade_band"], info["lab"], info["unit"], info["lesson"])
        lessons.setdefault(key, []).append((info["filename"], blob))

    out = []
    for (grade_band, lab, unit, lesson), files in sorted(lessons.items()):
        documents, pdfs = [], {}
        for fname, blob in sorted(files):
            kind = detect_doc_kind(fname) or fname.rsplit(".", 1)[0]   # stem fallback keeps every file
            documents.append({"doc_kind": kind, "filename": fname, "gcs_object_path": blob.name})
            if fname.lower().endswith(".pdf"):
                lp = os.path.join(cache, blob.name.replace("/", "__"))
                if not os.path.exists(lp):
                    blob.download_to_filename(lp)
                pdfs[kind] = lp
        raw_folder = base + "/".join([grade_band, lab, unit, lesson]).strip("/")
        out.append((_lesson_meta(grade_band, lab, unit, lesson, raw_folder, documents), pdfs))
    _log.info("discovered %d lesson bundle(s)", len(out))
    return out


def discover_local(data_root):
    """Walk <data_root>/<grade_band>/<lab>/<unit>/<lesson>/*.pdf and return the same
    [(meta, {doc_kind: local_path})] shape as discover()."""
    from pathlib import Path
    root = Path(data_root)
    out = []
    for grade in sorted(x for x in root.iterdir() if x.is_dir()):
        for lab in sorted(x for x in grade.iterdir() if x.is_dir()):
            for unit in sorted(x for x in lab.iterdir() if x.is_dir()):
                for lesson in sorted(x for x in unit.iterdir() if x.is_dir()):
                    documents, pdfs = [], {}
                    for pdf in sorted(lesson.glob("*.pdf")):
                        kind = detect_doc_kind(pdf.stem)
                        if not kind:                 # skip non-lesson files (overviews, notes, ...)
                            continue
                        documents.append({"doc_kind": kind, "filename": pdf.name,
                                          "gcs_object_path": str(pdf)})
                        pdfs.setdefault(kind, str(pdf))
                    if not pdfs:
                        continue
                    out.append((_lesson_meta(grade.name, lab.name, unit.name, lesson.name,
                                             str(lesson), documents), pdfs))
    _log.info("discovered %d local lesson bundle(s) under %s", len(out), data_root)
    return out
