"""Canonical grade-band mapping shared by the UI and pgvector filters."""

from __future__ import annotations

import re

GRADE_PRE_K_1 = "Grades_Pre-K-1st"
GRADE_2_5 = "Grades_2nd-5th"
GRADE_6_8 = "Grades_6th-8th"
CANONICAL_GRADE_BANDS = (GRADE_PRE_K_1, GRADE_2_5, GRADE_6_8)


def normalize_grade_band(value: str | None) -> str:
    raw = (value or "").strip()
    if raw in CANONICAL_GRADE_BANDS:
        return raw
    text = raw.lower().replace("_", " ").replace("-", " ")
    if any(token in text for token in ("pre k", "prek", "kindergarten", "1st", "grade 1")):
        return GRADE_PRE_K_1
    match = re.search(r"(?:grade|grades?)?\s*([2-8])", text)
    if match:
        grade = int(match.group(1))
        return GRADE_2_5 if grade <= 5 else GRADE_6_8
    return GRADE_PRE_K_1
