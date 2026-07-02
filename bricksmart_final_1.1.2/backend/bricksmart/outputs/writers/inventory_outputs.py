from __future__ import annotations

import csv
import json
from html import escape
from pathlib import Path

from bricksmart.inventory.ledger import InventoryLedger
from bricksmart.planning.models import PlanningResult


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _format_metadata(metadata: object) -> str:
    if metadata in (None, {}, []):
        return ""
    return escape(json.dumps(metadata, sort_keys=True, ensure_ascii=False))


def _write_build_instructions_html(path: Path, *, result: PlanningResult) -> None:
    """Write a portable HTML view of the structured build instructions.

    The full row/column pipeline replaces this static view with its interactive
    3D build player. The constrained planning service still emits this page so
    every run that writes ``build_instructions.json`` also has a human-readable
    ``build_instructions.html`` artifact.
    """
    parts = sorted(
        result.final_parts,
        key=lambda part: (
            part.step is None,
            part.step if part.step is not None else 0,
            str(part.segment_id or ""),
            str(part.part_id),
        ),
    )
    part_rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(part.step if part.step is not None else '—'))}</td>"
        f"<td>{escape(str(part.part_id))}</td>"
        f"<td><code>{escape(str(part.block_type))}</code></td>"
        f"<td>{escape(str(part.segment_id or '—'))}</td>"
        f"<td><code>{_format_metadata(part.metadata)}</code></td>"
        "</tr>"
        for part in parts
    ) or '<tr><td colspan="5">No parts were selected.</td></tr>'

    decision_rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(decision.group_id))}</td>"
        f"<td>{escape(str(decision.selected_candidate_id or '—'))}</td>"
        f"<td>{escape(str(decision.status))}</td>"
        f"<td><code>{escape(json.dumps(decision.requirements, sort_keys=True))}</code></td>"
        "</tr>"
        for decision in result.decisions
    ) or '<tr><td colspan="4">No planning decisions were recorded.</td></tr>'

    status_class = (
        "pass"
        if result.status.lower() in {"success", "succeeded", "pass", "complete"}
        else "review"
    )
    payload = {
        "status": result.status,
        "parts": [part.to_dict() for part in result.final_parts],
        "decisions": [decision.to_dict() for decision in result.decisions],
    }
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BrickSmart build instructions</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f3f4f6; color: #111827; }}
  main {{ width: min(1120px, calc(100% - 24px)); margin: 24px auto; }}
  .card {{ background: #fff; border: 1px solid #d1d5db; border-radius: 14px; padding: 20px; margin-bottom: 16px; box-shadow: 0 4px 16px rgba(0,0,0,.06); }}
  h1, h2 {{ margin-top: 0; }}
  .status {{ display: inline-block; border-radius: 999px; padding: 5px 11px; font-weight: 800; }}
  .status.pass {{ background: #dcfce7; color: #166534; }}
  .status.review {{ background: #fef3c7; color: #92400e; }}
  .summary {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
  .metric {{ border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px; }}
  .metric strong {{ display: block; font-size: 1.4rem; }}
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ padding: 10px 12px; border-bottom: 1px solid #e5e7eb; text-align: left; vertical-align: top; }}
  th {{ background: #f9fafb; font-size: .82rem; text-transform: uppercase; letter-spacing: .035em; }}
  code {{ overflow-wrap: anywhere; }}
  details pre {{ white-space: pre-wrap; overflow-wrap: anywhere; }}
  @media (max-width: 700px) {{ .summary {{ grid-template-columns: 1fr; }} }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #111827; color: #f9fafb; }}
    .card {{ background: #1f2937; border-color: #4b5563; }}
    .metric, th, td {{ border-color: #374151; }}
    th {{ background: #111827; }}
  }}
</style>
</head>
<body>
<main>
  <section class="card">
    <h1>BrickSmart build instructions</h1>
    <p><span class="status {status_class}">{escape(result.status)}</span></p>
    <div class="summary">
      <div class="metric"><span>Total blocks</span><strong>{len(parts)}</strong></div>
      <div class="metric"><span>Planning decisions</span><strong>{len(result.decisions)}</strong></div>
    </div>
  </section>
  <section class="card">
    <h2>Parts by build step</h2>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Step</th><th>Part</th><th>Block type</th><th>Segment</th><th>Metadata</th></tr></thead>
        <tbody>{part_rows}</tbody>
      </table>
    </div>
  </section>
  <section class="card">
    <h2>Planning decisions</h2>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Group</th><th>Selected candidate</th><th>Status</th><th>Requirements</th></tr></thead>
        <tbody>{decision_rows}</tbody>
      </table>
    </div>
  </section>
  <section class="card">
    <details>
      <summary>Structured instruction data</summary>
      <pre>{escape(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))}</pre>
    </details>
  </section>
</main>
</body>
</html>
"""
    path.write_text(page, encoding="utf-8")


def write_run_outputs(
    output_dir: str | Path,
    *,
    result: PlanningResult,
    ledger: InventoryLedger,
) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    effective_inventory_path = output_dir / "effective_inventory.json"
    _write_json(effective_inventory_path, ledger.inventory.to_dict())
    written.append(effective_inventory_path)

    usage_path = output_dir / "inventory_usage.csv"
    usage_rows = ledger.usage_summary()
    with usage_path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = [
            "block_type",
            "capacity",
            "committed",
            "reserved",
            "remaining",
            "utilization_fraction",
            "limit_source",
            "status",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(usage_rows)
    written.append(usage_path)

    events_path = output_dir / "inventory_events.csv"
    with events_path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = [
            "sequence",
            "action",
            "reservation_id",
            "reason",
            "requirements",
            "snapshot",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for event in ledger.events:
            row = event.to_dict()
            row["requirements"] = json.dumps(row["requirements"], sort_keys=True)
            row["snapshot"] = json.dumps(row["snapshot"], sort_keys=True)
            writer.writerow(row)
    written.append(events_path)

    validation_path = output_dir / "inventory_validation.json"
    _write_json(validation_path, result.inventory_validation)
    written.append(validation_path)

    unmet_path = output_dir / "unmet_inventory_requirements.csv"
    with unmet_path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = [
            "group_id",
            "required",
            "selection_kind",
            "candidate_shortages",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for item in result.unmet_requirements:
            writer.writerow(
                {
                    "group_id": item.get("group_id"),
                    "required": item.get("required"),
                    "selection_kind": item.get("selection_kind"),
                    "candidate_shortages": json.dumps(
                        item.get("candidate_shortages", {}), sort_keys=True
                    ),
                }
            )
    written.append(unmet_path)

    parts_path = output_dir / "final_parts.csv"
    part_rows = [part.to_dict() for part in result.final_parts]
    base_fields = ["part_id", "block_type", "segment_id", "step", "metadata"]
    with parts_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=base_fields)
        writer.writeheader()
        for row in part_rows:
            csv_row = dict(row)
            csv_row["metadata"] = json.dumps(csv_row["metadata"], sort_keys=True)
            writer.writerow(csv_row)
    written.append(parts_path)

    instructions_path = output_dir / "build_instructions.json"
    _write_json(
        instructions_path,
        {
            "status": result.status,
            "parts": part_rows,
            "decisions": [decision.to_dict() for decision in result.decisions],
        },
    )
    written.append(instructions_path)

    instructions_html_path = output_dir / "build_instructions.html"
    _write_build_instructions_html(instructions_html_path, result=result)
    written.append(instructions_html_path)

    return written
