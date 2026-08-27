# Verification tools

This directory contains developer and release-verification commands. These tools
are intentionally outside `backend/bricksmart/` because they are not part of the
BrickSmart runtime API or planner package.

## Build-equivalence report

`generate_build_equivalence_report.py` compares a compact reviewed regression
baseline with artifacts from a fresh build. It checks canonical CSV/JSON files,
final placements, the true build timeline, summary metrics, inventory usage, and
(optionally) byte identity of the interactive build player. It then writes a
self-contained HTML report with side-by-side model renderings and the candidate
interactive player.

From the repository root, generate the bird report with:

```bash
make equivalence-report-bird
```

The target first creates a fresh deterministic bird run and then writes:

```text
release/verification/reports/bird_build_equivalence.html
```

The report command exits nonzero when it detects a difference, so it can also be
used as a CI release gate. Generated HTML reports are ignored by Git by default;
a report may be attached to a release or CI run when evidence needs to be kept.
