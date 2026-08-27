"""Small Hyper3D Rodin/Bang client used by the local demo pipeline."""

from __future__ import annotations

import time
import zipfile
from pathlib import Path
from typing import Any, Callable

import requests

from config import (
    BANG_RESOLUTION,
    BANG_STRENGTH,
    HYPER3D_API_KEY,
    HYPER3D_BASE_URL,
    RODIN_GEOMETRY_FILE_FORMAT,
    RODIN_MATERIAL,
    RODIN_MESH_MODE,
    RODIN_QUALITY,
    RODIN_TIER,
)

ProgressFn = Callable[[str, int, str], None]


class RodinError(RuntimeError):
    """Raised when Hyper3D returns an error or the task fails."""


def _headers(json_content: bool = False) -> dict[str, str]:
    if not HYPER3D_API_KEY:
        raise RodinError("HYPER3D_API_KEY is not configured")
    headers = {"Authorization": f"Bearer {HYPER3D_API_KEY}"}
    if json_content:
        headers["Content-Type"] = "application/json"
        headers["accept"] = "application/json"
    return headers


def check_balance() -> dict[str, Any]:
    resp = requests.get(
        f"{HYPER3D_BASE_URL}/check_balance",
        headers=_headers(),
        timeout=30,
    )
    return _json_or_raise(resp, "check balance")


def submit_text_to_rodin(prompt: str) -> dict[str, Any]:
    files = [
        ("prompt", (None, prompt)),
        ("tier", (None, RODIN_TIER)),
        ("mesh_mode", (None, RODIN_MESH_MODE)),
        ("geometry_file_format", (None, RODIN_GEOMETRY_FILE_FORMAT)),
        ("material", (None, RODIN_MATERIAL)),
        ("quality", (None, RODIN_QUALITY)),
        ("quality_override", (None, "20000")),
        ("texture_mode", (None, "low")),
    ]
    resp = requests.post(
        f"{HYPER3D_BASE_URL}/rodin",
        headers=_headers(),
        files=files,
        timeout=60,
    )
    return _json_or_raise(resp, "submit Rodin")


def submit_bang(asset_id: str) -> dict[str, Any]:
    data = {
        "asset_id": asset_id,
        "strength": str(BANG_STRENGTH),
        "geometry_file_format": RODIN_GEOMETRY_FILE_FORMAT,
        "material": RODIN_MATERIAL,
        "resolution": BANG_RESOLUTION,
    }
    resp = requests.post(
        f"{HYPER3D_BASE_URL}/bang",
        headers=_headers(),
        data=data,
        timeout=60,
    )
    return _json_or_raise(resp, "submit Bang")


def poll_until_done(
    subscription_key: str,
    *,
    label: str,
    progress: ProgressFn,
    percent_start: int,
    percent_end: int,
    interval_seconds: int = 10,
    timeout_seconds: int = 900,
) -> list[dict[str, Any]]:
    started = time.time()
    last_status = "Waiting"
    while True:
        resp = requests.post(
            f"{HYPER3D_BASE_URL}/status",
            headers=_headers(json_content=True),
            json={"subscription_key": subscription_key},
            timeout=30,
        )
        data = _json_or_raise(resp, f"poll {label}")
        jobs = data.get("jobs", [])
        statuses = [str(job.get("status", "Unknown")) for job in jobs]
        if statuses:
            last_status = ", ".join(sorted(set(statuses)))

        elapsed = max(time.time() - started, 1)
        span = max(percent_end - percent_start, 1)
        estimated = min(percent_end - 1, percent_start + int(span * min(elapsed / timeout_seconds, 0.95)))
        progress(f"{label}: {last_status}", estimated, f"{label} status: {last_status}")

        if statuses and all(status == "Done" for status in statuses):
            progress(f"{label}: complete", percent_end, f"{label} completed")
            return jobs
        if any(status == "Failed" for status in statuses):
            raise RodinError(f"{label} failed: {data}")
        if time.time() - started > timeout_seconds:
            raise RodinError(f"{label} timed out after {timeout_seconds} seconds")

        time.sleep(interval_seconds)


def download_task(task_uuid: str, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    resp = requests.post(
        f"{HYPER3D_BASE_URL}/download",
        headers=_headers(json_content=True),
        json={"task_uuid": task_uuid},
        timeout=60,
    )
    data = _json_or_raise(resp, "download task")

    saved: list[Path] = []
    for item in data.get("list", []):
        url = item.get("url")
        name = item.get("name") or "download.bin"
        if not url:
            continue
        safe_name = Path(name).name
        target = output_dir / safe_name
        file_resp = requests.get(url, timeout=180)
        file_resp.raise_for_status()
        target.write_bytes(file_resp.content)
        saved.append(target)
        if target.suffix.lower() == ".zip":
            extract_dir = output_dir / target.stem
            extract_dir.mkdir(exist_ok=True)
            with zipfile.ZipFile(target) as zf:
                zf.extractall(extract_dir)
            saved.extend(p for p in extract_dir.rglob("*") if p.is_file())
    return saved


def choose_obj(paths: list[Path]) -> Path | None:
    obj_paths = [p for p in paths if p.suffix.lower() == ".obj"]
    if not obj_paths:
        return None
    segmented = [p for p in obj_paths if "bang" in p.name.lower() or "segment" in p.name.lower()]
    return (segmented or obj_paths)[0]


def _json_or_raise(resp: requests.Response, action: str) -> dict[str, Any]:
    try:
        data = resp.json()
    except ValueError as exc:
        raise RodinError(f"Could not parse {action} response: {resp.status_code} {resp.text[:500]}") from exc

    if resp.status_code >= 400 or data.get("error"):
        raise RodinError(f"Hyper3D {action} error: {resp.status_code} {data}")
    return data

