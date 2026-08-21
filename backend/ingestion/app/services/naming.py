"""Deterministic, reusable naming derived from the raw GCS path components.
NOTHING in the pipeline hard-codes a directory name — it all comes from these functions.

Raw layout:   Data/<grade_band>/<lab>/<unit>/<lesson>/<filename>
Bundle name:  <grade_band>-<lab>-<unit>-<lesson>-<filename_stem>   (starts at the grade path)
Policy scope: <grade_band>-<lab>-<unit>

Components are slugged for path-safety; the ORIGINAL values are always kept in provenance metadata,
so a bundle name is traceable but never the source of truth.
"""
import re


def slug(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[^\w\-.]+", "_", s)      # keep word chars, hyphen, dot; everything else -> _
    return re.sub(r"_+", "_", s).strip("_")


def bundle_name(grade_band, lab, unit, lesson, filename) -> str:
    """<grade_band>-<lab>-<unit>-<lesson>-<filename_stem>  (starts at grade; empty parts dropped)."""
    stem = filename.rsplit(".", 1)[0] if filename else ""
    parts = [grade_band, lab, unit, lesson, stem]
    return "-".join(slug(p) for p in parts if p)


def policy_scope(grade_band, lab, unit) -> str:
    """<grade_band>-<lab>-<unit>  — one policy scope per unit."""
    return "-".join(slug(p) for p in [grade_band, lab, unit] if p)


def parse_raw_path(object_path: str, raw_prefix: str = "Data") -> dict:
    """Reverse of the raw layout: Data/<grade_band>/<lab>/<unit>/<lesson>/<filename>
    -> {grade_band, lab, unit, lesson, filename}. Extra depth folds into `lesson` (nested lessons)."""
    p = object_path.replace("\\", "/").strip("/")
    if p.startswith(raw_prefix + "/"):
        p = p[len(raw_prefix) + 1:]
    seg = p.split("/")
    if len(seg) < 5:
        # tolerate shallow paths (e.g. unit-level files): pad from the right
        grade_band = seg[0] if len(seg) > 0 else ""
        lab = seg[1] if len(seg) > 1 else ""
        unit = seg[2] if len(seg) > 2 else ""
        lesson = ""
        filename = seg[-1] if seg else ""
    else:
        grade_band, lab, unit = seg[0], seg[1], seg[2]
        lesson = "/".join(seg[3:-1])
        filename = seg[-1]
    return {"grade_band": grade_band, "lab": lab, "unit": unit, "lesson": lesson, "filename": filename}
