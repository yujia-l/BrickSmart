"""
KidSpark AI — Session API Router
Owner: Developer B

All runtime session endpoints. Sessions progress through phases:
  consultation -> block_awareness -> generation -> refinement -> complete
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from models.schemas import (
    MessageRequest,
    MessageResponse,
    SessionCreatedResponse,
    UploadResponse,
)
from agents.orchestrator import (
    approve_block_awareness,
    approve_consultation,
    confirm_session_build_plan,
    confirm_session_documents,
    confirm_session_model,
    confirm_session_segments,
    confirm_teacher_planning,
    create_session,
    get_session_documents,
    get_session_build,
    get_session_model_preview,
    get_session_segments,
    get_session,
    reset_session_build,
    route_message,
    run_storybook_analysis,
    start_session_documents,
    start_session_build,
    start_session_model_preview,
    start_session_segments,
)
from agents.mock_data import MOCK_BLOCK_CATALOG, SAMPLE_STORYBOOK_TEXT
from ingestion.story_upload import extract_story_text

router = APIRouter(prefix="/api/v1", tags=["sessions"])


class RefineModelRequest(BaseModel):
    rodin_prompt: str | None = None
    refinement: str = ""


class GenericRefinementRequest(BaseModel):
    refinement: str = ""
    updates: dict[str, Any] = Field(default_factory=dict)


# ── Session lifecycle ─────────────────────────────────────────────────────

@router.post("/sessions", response_model=SessionCreatedResponse)
async def create_new_session():
    """Create a new teacher session."""
    session = create_session()
    return SessionCreatedResponse(
        session_id=session.session_id,
        phase=session.phase.value,
    )


@router.post("/sessions/{session_id}/upload", response_model=UploadResponse)
async def upload_storybook(
    session_id: str,
    text: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
):
    """Upload storybook text and trigger automatic analysis.

    For Phase 1 dev: pass ``text`` as a query param, or omit it to use the
    built-in sample storybook (Milo's Flying Delivery).
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    if file:
        storybook_text = extract_story_text(file.filename or "upload.pdf", await file.read())
    else:
        storybook_text = text or SAMPLE_STORYBOOK_TEXT
    analysis = await run_storybook_analysis(session_id, storybook_text)

    return UploadResponse(
        status="analyzed",
        story_analysis=analysis,
        phase=session.phase.value,
    )


# ── Messaging (routes to consultation or block-awareness agent) ───────

@router.post("/sessions/{session_id}/message", response_model=MessageResponse)
async def send_message(session_id: str, body: MessageRequest):
    """Send a teacher message; routed to the active agent for the session phase."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    return await route_message(session_id, body.message)


@router.post("/sessions/{session_id}/confirm-planning")
async def confirm_planning(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    try:
        return await confirm_teacher_planning(session_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/sessions/{session_id}/model-preview")
async def start_model_preview(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    try:
        if session.model_preview_job_id:
            existing = get_session_model_preview(session_id)
            if existing and existing.get("status") in {"queued", "running", "complete"}:
                return existing
        return start_session_model_preview(session_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/sessions/{session_id}/model-preview")
async def poll_model_preview(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    job = get_session_model_preview(session_id)
    if not job:
        raise HTTPException(404, "No model preview job has been started.")
    return job


@router.post("/sessions/{session_id}/model-preview/refine")
async def refine_model_preview(session_id: str, body: RefineModelRequest):
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    try:
        base = None
        if session.model_preview_result:
            base = dict(session.model_preview_result.get("context", {}))
        if not base:
            base = (await confirm_teacher_planning(session_id))["model_task_context"]
        if body.rodin_prompt:
            base["rodin_prompt"] = body.rodin_prompt
        if body.refinement:
            base["rodin_prompt"] = f"{base.get('rodin_prompt', '')} Teacher refinement: {body.refinement}"
        session.model_preview_job_id = None
        session.model_preview_result = None
        return start_session_model_preview(session_id, context_override=base)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/sessions/{session_id}/confirm-model")
async def confirm_model(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    try:
        return confirm_session_model(session_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/sessions/{session_id}/segments")
async def start_segments(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    try:
        if session.segment_job_id:
            existing = get_session_segments(session_id)
            if existing and existing.get("status") in {"queued", "running", "complete"}:
                return existing
        return start_session_segments(session_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/sessions/{session_id}/segments")
async def poll_segments(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    job = get_session_segments(session_id)
    if not job:
        raise HTTPException(404, "No segment job has been started.")
    return job


@router.post("/sessions/{session_id}/segments/refine")
async def refine_segments(session_id: str, body: GenericRefinementRequest):
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.segment_result:
        session.segment_result.setdefault("teacher_segment_refinements", []).append(body.model_dump())
        session.build_result = session.segment_result
    return {"status": "saved", "phase": session.phase.value, "refinement": body.model_dump()}


@router.post("/sessions/{session_id}/confirm-segments")
async def confirm_segments(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    try:
        return confirm_session_segments(session_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/sessions/{session_id}/confirm-build-plan")
async def confirm_build_plan(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    try:
        return confirm_session_build_plan(session_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/sessions/{session_id}/documents")
async def start_documents(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    try:
        if session.document_job_id:
            existing = get_session_documents(session_id)
            if existing and existing.get("status") in {"queued", "running", "complete"}:
                return existing
        return start_session_documents(session_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/sessions/{session_id}/documents")
async def poll_documents(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    job = get_session_documents(session_id)
    if not job:
        raise HTTPException(404, "No document job has been started.")
    return job


@router.post("/sessions/{session_id}/documents/{kind}/refine")
async def refine_document(session_id: str, kind: str, body: GenericRefinementRequest):
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.document_result:
        session.document_result.setdefault("teacher_document_refinements", {}).setdefault(kind, []).append(body.model_dump())
    return {"status": "saved", "kind": kind, "refinement": body.model_dump()}


@router.get("/sessions/{session_id}/documents/{kind}/download")
async def download_document(session_id: str, kind: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    job = get_session_documents(session_id)
    result = (job or {}).get("result") or session.document_result
    bundle = (result or {}).get("document_bundle", {})
    doc = bundle.get("documents", {}).get(kind)
    if not doc:
        raise HTTPException(404, f"Document '{kind}' was not found.")
    pdf_path = Path(doc.get("pdf_path", ""))
    if not pdf_path.is_file():
        raise HTTPException(404, "PDF file was not found on disk.")
    return FileResponse(str(pdf_path), media_type="application/pdf", filename=f"{kind}.pdf")


@router.post("/sessions/{session_id}/confirm-documents")
async def confirm_documents(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    try:
        return confirm_session_documents(session_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# ── Phase transitions ────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/approve-plan")
async def approve_plan(session_id: str):
    """Teacher approves the consultation direction → block_awareness phase."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.phase.value != "consultation":
        raise HTTPException(400, f"Cannot approve in phase '{session.phase.value}'")

    summary = await approve_consultation(session_id)
    return {
        "status": "approved",
        "consultation_summary": summary.model_dump(),
        "phase": "block_awareness",
    }


@router.post("/sessions/{session_id}/approve-blocks")
async def approve_blocks(session_id: str):
    """Finalize block requirements → generation phase."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.phase.value != "block_awareness":
        raise HTTPException(400, f"Cannot approve blocks in phase '{session.phase.value}'")

    reqs = await approve_block_awareness(session_id)
    return {
        "status": "approved",
        "block_requirements": reqs.model_dump(),
        "phase": "generation",
    }


@router.post("/sessions/{session_id}/build-plan")
async def start_build_plan(session_id: str):
    """Start the Rodin/Bang-backed build plan for this teacher session."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if not session.block_requirements or not session.consultation_summary:
        raise HTTPException(400, "Approve the lesson plan and block requirements before starting the build.")
    if session.build_job_id:
        existing = get_session_build(session_id)
        if existing:
            return existing
    try:
        return await start_session_build(session_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/sessions/{session_id}/build-plan")
async def get_build_plan(session_id: str):
    """Poll build plan status for this teacher session."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    job = get_session_build(session_id)
    if not job:
        raise HTTPException(404, "No build job has been started for this session.")
    return job


@router.post("/sessions/{session_id}/build-plan/restart")
async def restart_build_plan(session_id: str):
    """Allow the teacher to restart generation after reviewing a bad output."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    reset_session_build(session_id)
    return await start_build_plan(session_id)


# ── Informational / debugging ────────────────────────────────────────────

@router.get("/sessions/{session_id}")
async def get_session_detail(session_id: str):
    """Inspect current session state."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session.model_dump()


@router.get("/blocks/catalog")
async def get_block_catalog():
    """Return the Kid Spark block catalog."""
    return [p.model_dump() for p in MOCK_BLOCK_CATALOG]
