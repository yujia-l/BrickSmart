"""In-memory background jobs for the local build demo."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build3d.pipeline import (
    create_document_bundle,
    create_rodin_preview,
    create_segments_and_build_plan,
    run_pipeline,
)

GENERATED_ROOT = Path(__file__).resolve().parents[2] / "work" / "build_jobs"

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def start_build_job(
    story_text: str,
    teacher_connection_intent: str = "",
    seed_context: dict[str, Any] | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    job_dir = GENERATED_ROOT / job_id
    job = {
        "job_id": job_id,
        "status": "queued",
        "stage": "Queued",
        "progress": 0,
        "message": "Build job queued",
        "created_at": _now(),
        "updated_at": _now(),
        "job_dir": str(job_dir),
        "events": [],
        "result": None,
        "error": None,
        "session_id": session_id,
    }
    with _lock:
        _jobs[job_id] = job

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, story_text, teacher_connection_intent, seed_context, job_dir),
        daemon=True,
    )
    thread.start()
    return snapshot(job_id)


def start_model_preview_job(
    context: dict[str, Any],
    session_id: str,
) -> dict[str, Any]:
    job_dir = GENERATED_ROOT / f"session_{session_id}"
    return _start_stage_job(
        session_id=session_id,
        job_dir=job_dir,
        initial_stage="Rodin preview queued",
        initial_message="Model preview job queued",
        runner=lambda progress: create_rodin_preview(context, job_dir, progress),
    )


def start_segments_job(
    context: dict[str, Any],
    rodin_task_uuid: str,
    rodin_files: list[str],
    session_id: str,
) -> dict[str, Any]:
    job_dir = GENERATED_ROOT / f"session_{session_id}"
    return _start_stage_job(
        session_id=session_id,
        job_dir=job_dir,
        initial_stage="Segmentation queued",
        initial_message="Bang segmentation and notebook build job queued",
        runner=lambda progress: create_segments_and_build_plan(
            context,
            rodin_task_uuid,
            rodin_files,
            job_dir,
            progress,
        ),
    )


def start_document_job(
    story_text: str,
    context: dict[str, Any],
    build_plan: dict[str, Any],
    session_id: str,
) -> dict[str, Any]:
    job_dir = GENERATED_ROOT / f"session_{session_id}"
    return _start_stage_job(
        session_id=session_id,
        job_dir=job_dir,
        initial_stage="Documents queued",
        initial_message="Lesson bundle generation queued",
        runner=lambda progress: create_document_bundle(
            story_text,
            context,
            build_plan,
            job_dir,
            progress,
        ),
    )


def _start_stage_job(
    *,
    session_id: str,
    job_dir: Path,
    initial_stage: str,
    initial_message: str,
    runner: Any,
) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "status": "queued",
        "stage": initial_stage,
        "progress": 0,
        "message": initial_message,
        "created_at": _now(),
        "updated_at": _now(),
        "job_dir": str(job_dir),
        "events": [],
        "result": None,
        "error": None,
        "session_id": session_id,
    }
    with _lock:
        _jobs[job_id] = job

    thread = threading.Thread(
        target=_run_stage_job,
        args=(job_id, runner),
        daemon=True,
    )
    thread.start()
    return snapshot(job_id)


def snapshot(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return _snapshot_from_disk(job_id)
        return dict(job)


def _run_job(
    job_id: str,
    story_text: str,
    teacher_connection_intent: str,
    seed_context: dict[str, Any] | None,
    job_dir: Path,
) -> None:
    def progress(stage: str, percent: int, message: str) -> None:
        with _lock:
            job = _jobs[job_id]
            job["status"] = "running"
            job["stage"] = stage
            job["progress"] = max(0, min(100, percent))
            job["message"] = message
            job["updated_at"] = _now()
            job["events"].append({"at": _now(), "stage": stage, "message": message, "progress": percent})
            job["events"] = job["events"][-30:]

    try:
        progress("Starting", 1, "Starting end-to-end build pipeline")
        result = run_pipeline(
            story_text,
            job_dir,
            progress,
            teacher_connection_intent=teacher_connection_intent,
            seed_context=seed_context,
        )
        with _lock:
            job = _jobs[job_id]
            job["status"] = "complete"
            job["stage"] = "Complete"
            job["progress"] = 100
            job["message"] = "Build generation complete"
            job["result"] = result
            job["updated_at"] = _now()
    except Exception as exc:
        with _lock:
            job = _jobs[job_id]
            job["status"] = "error"
            job["stage"] = "Error"
            job["message"] = str(exc)
            job["error"] = repr(exc)
            job["updated_at"] = _now()


def _run_stage_job(job_id: str, runner: Any) -> None:
    def progress(stage: str, percent: int, message: str) -> None:
        with _lock:
            job = _jobs[job_id]
            job["status"] = "running"
            job["stage"] = stage
            job["progress"] = max(0, min(100, percent))
            job["message"] = message
            job["updated_at"] = _now()
            job["events"].append({"at": _now(), "stage": stage, "message": message, "progress": percent})
            job["events"] = job["events"][-30:]

    try:
        progress("Starting", 1, "Starting stage job")
        result = runner(progress)
        with _lock:
            job = _jobs[job_id]
            job["status"] = "complete"
            job["stage"] = "Complete"
            job["progress"] = 100
            job["message"] = "Stage complete"
            job["result"] = result
            job["updated_at"] = _now()
    except Exception as exc:
        with _lock:
            job = _jobs[job_id]
            job["status"] = "error"
            job["stage"] = "Error"
            job["message"] = str(exc)
            job["error"] = repr(exc)
            job["updated_at"] = _now()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snapshot_from_disk(job_id: str) -> dict[str, Any] | None:
    job_dir = GENERATED_ROOT / job_id
    result_path = job_dir / "result.json"
    if not result_path.exists():
        return None
    import json

    result = json.loads(result_path.read_text(encoding="utf-8"))
    return {
        "job_id": job_id,
        "status": "complete",
        "stage": "Complete",
        "progress": 100,
        "message": "Loaded completed report from disk",
        "created_at": None,
        "updated_at": None,
        "job_dir": str(job_dir),
        "events": [],
        "result": result,
        "error": None,
        "session_id": None,
    }
