"""
KidSpark AI — Pipeline Orchestrator
Owner: Developer B

Manages the full pipeline execution across all phases with in-memory
session storage for Phase 1 development.
"""

import uuid
from hashlib import sha256

from models.schemas import (
    BlockRequirements,
    ConsultationResponse,
    ConsultationSummary,
    MessageResponse,
    SessionPhase,
    SessionState,
    StoryAnalysis,
)
from agents.story_analysis import analyze_storybook
from agents.consultation import (
    handle_consultation_message,
    finalize_consultation,
)
from agents.block_awareness import (
    handle_block_awareness_message,
    finalize_block_requirements,
)
from build3d.jobs import snapshot as build_snapshot
from build3d.jobs import (
    start_build_job,
    start_document_job,
    start_model_preview_job,
    start_segments_job,
)
from build3d.validated_planner_adapter import apply_catalog_constraints, semantic_segment_targets
from retrieval.provider import retrieve_teacher_evidence

# ---------------------------------------------------------------------------
# In-memory session store (replaced by DB in production)
# ---------------------------------------------------------------------------

_sessions: dict[str, SessionState] = {}


def create_session() -> SessionState:
    sid = str(uuid.uuid4())
    session = SessionState(session_id=sid)
    _sessions[sid] = session
    return session


def get_session(session_id: str) -> SessionState | None:
    return _sessions.get(session_id)


# ---------------------------------------------------------------------------
# Phase 1 — Storybook Analysis (automatic, on upload)
# ---------------------------------------------------------------------------

async def run_storybook_analysis(
    session_id: str, storybook_text: str
) -> StoryAnalysis:
    session = _sessions[session_id]
    session.storybook_text = storybook_text
    analysis = await analyze_storybook(storybook_text)
    session.storybook_analysis = analysis
    session.phase = SessionPhase.lesson_planning
    session.planning_state = planning_state_snapshot(session)
    _refresh_rag_evidence(session, teacher_message="")
    return analysis


# ---------------------------------------------------------------------------
# Phase 2 — Teacher Consultation (multi-turn)
# ---------------------------------------------------------------------------

async def route_message(session_id: str, message: str) -> MessageResponse:
    """Route a teacher message to the correct agent based on session phase."""
    session = _sessions[session_id]

    if session.phase in (SessionPhase.consultation, SessionPhase.lesson_planning):
        session.planning_state = planning_state_snapshot(session)
        evidence = _refresh_rag_evidence(session, teacher_message=message)
        result: ConsultationResponse = await handle_consultation_message(
            message=message,
            story_analysis=session.storybook_analysis,
            chat_history=session.teacher_messages,
            evidence=evidence,
            planning_state=session.planning_state,
        )
        session.teacher_messages.append({"role": "user", "content": message})
        session.teacher_messages.append({"role": "assistant", "content": result.response})
        derived_state = planning_state_snapshot(session)
        update = (
            result.planning_update.model_dump(exclude_none=True)
            if result.planning_update is not None
            else {}
        )
        session.planning_state = _merge_planning_state(
            derived_state,
            update,
            teacher_messages=session.teacher_messages,
        )
        checklist_ready = bool(session.planning_state.get("required_complete"))
        if not checklist_ready:
            missing = _missing_planning_fields(session.planning_state)
            result.response = _append_missing_checklist_prompt(
                _strip_premature_readiness_claims(result.response),
                missing,
            )
        else:
            result.response = _strip_missing_checklist_prompt(result.response)
        session.teacher_messages[-1]["content"] = result.response

        return MessageResponse(
            response=result.response,
            phase=SessionPhase.lesson_planning.value,
            areas_covered=result.areas_covered,
            areas_remaining=result.areas_remaining,
            ready_to_approve=checklist_ready,
            planning_state=session.planning_state,
            rag_status=session.rag_status,
            rag_trace=session.rag_trace,
        )

    elif session.phase == SessionPhase.block_awareness:
        reply = await handle_block_awareness_message(
            message=message,
            consultation_summary=session.consultation_summary,
            chat_history=session.teacher_messages,
        )
        session.teacher_messages.append({"role": "user", "content": message})
        session.teacher_messages.append({"role": "assistant", "content": reply})
        session.planning_state = planning_state_snapshot(session)

        has_movement_info = any(
            kw in message.lower()
            for kw in ["spin", "roll", "pivot", "fixed", "static", "move", "flap", "wheel"]
        )
        return MessageResponse(
            response=reply,
            phase=session.phase.value,
            ready_to_generate=has_movement_info,
            planning_state=session.planning_state,
        )

    return MessageResponse(
        response="Session is not in an interactive phase.",
        phase=session.phase.value,
        rag_status=session.rag_status,
        rag_trace=session.rag_trace,
    )


def _refresh_rag_evidence(
    session: SessionState,
    *,
    teacher_message: str,
) -> dict:
    """Refresh bounded evidence only when the effective planning query changes."""
    state = session.planning_state or planning_state_snapshot(session)
    missing = _missing_planning_fields(state)
    query_parts = [
        session.storybook_analysis.title if session.storybook_analysis else "",
        teacher_message,
        str(state.get("core_concept", "")),
        str(state.get("build_object", "")),
        "Next planning needs: " + ", ".join(missing),
    ]
    query = " ".join(part for part in query_parts if part).strip()
    grade = str(state.get("target_grade") or "1st Grade")
    signature = sha256(
        f"{grade}\n{' '.join(query.lower().split())}".encode("utf-8")
    ).hexdigest()
    if signature == session.rag_query_signature and session.rag_evidence:
        return session.rag_evidence

    evidence = retrieve_teacher_evidence(query, grade)
    session.rag_evidence = evidence
    session.rag_trace = list(evidence.get("trace", []))
    session.rag_status = str(evidence.get("status", "unknown"))
    session.rag_query_signature = signature
    return evidence


# ---------------------------------------------------------------------------
# Phase transition — approve consultation
# ---------------------------------------------------------------------------

async def approve_consultation(session_id: str) -> ConsultationSummary:
    session = _sessions[session_id]
    summary = await finalize_consultation(
        story_analysis=session.storybook_analysis,
        chat_history=session.teacher_messages,
    )
    session.consultation_summary = summary
    session.phase = SessionPhase.block_awareness
    session.planning_state = planning_state_snapshot(session)
    return summary


# ---------------------------------------------------------------------------
# Phase transition — finalize block awareness
# ---------------------------------------------------------------------------

async def approve_block_awareness(session_id: str) -> BlockRequirements:
    session = _sessions[session_id]
    reqs = await finalize_block_requirements(
        consultation_summary=session.consultation_summary,
        chat_history=session.teacher_messages,
    )
    session.block_requirements = reqs
    session.phase = SessionPhase.generation
    session.planning_state = planning_state_snapshot(session)
    return reqs


async def confirm_teacher_planning(session_id: str) -> dict:
    session = _sessions[session_id]
    if not session.consultation_summary:
        session.consultation_summary = await finalize_consultation(
            story_analysis=session.storybook_analysis,
            chat_history=session.teacher_messages,
        )
    if not session.block_requirements:
        session.block_requirements = await finalize_block_requirements(
            consultation_summary=session.consultation_summary,
            chat_history=session.teacher_messages,
        )
    session.phase = SessionPhase.model_preview
    session.planning_state = planning_state_snapshot(session)
    context = build_seed_context(session)
    return {
        "status": "confirmed",
        "phase": session.phase.value,
        "planning_state": session.planning_state,
        "model_task_context": context,
    }


# ---------------------------------------------------------------------------
# Phase 3 — Build generation
# ---------------------------------------------------------------------------

def build_teacher_connection_intent(session: SessionState) -> str:
    reqs = session.block_requirements
    if not reqs:
        return ""
    part_lines = [
        f"{part.part_name}: {str(part.movement).strip().lower()}; {part.notes}"
        for part in reqs.parts
    ]
    connectors = ", ".join(reqs.connector_types_needed)
    return (
        f"Teacher-approved movement plan for {reqs.artifact_label}. "
        f"Connectors needed: {connectors}. "
        f"Parts: {' | '.join(part_lines)}. "
        f"Summary: {reqs.articulation_summary}"
    )


def build_seed_context(session: SessionState) -> dict:
    summary = session.consultation_summary
    reqs = session.block_requirements
    analysis = session.storybook_analysis
    if not summary or not reqs:
        raise ValueError("Consultation summary and block requirements are required before build generation.")

    parts = [
        {
            "part_name": part.part_name,
            "movement": str(part.movement).strip().lower(),
            "function": part.notes or f"{part.part_name} part of the build",
            "suggested_piece": ", ".join(part.suggested_pieces),
        }
        for part in reqs.parts
    ]
    moving_parts = [part for part in parts if part["movement"] != "static"]
    static_parts = [part for part in parts if part["movement"] == "static"]
    moving_names = [part["part_name"] for part in moving_parts]
    static_names = [part["part_name"] for part in static_parts]
    movement_text = (
        "; ".join(f"{part['part_name']} should be {part['movement']}" for part in moving_parts)
        if moving_parts
        else "No separate moving feature is required"
    )
    artifact = reqs.artifact_label or summary.agreed_artifact
    title = summary.storybook_title or (analysis.title if analysis else "Uploaded story")
    build_constraints = session.build_constraints or {
        "object_type_hint": artifact,
        "moving_parts": moving_names,
        "teacher_requested_static_parts": static_names,
        "wheel_count": sum(1 for part in parts if part["movement"] == "rolling"),
        "symmetry": "auto",
        "inventory_mode": "standard_kit",
        "max_validated_blocks": 28,
        "max_semantic_segments": 4,
        "max_moving_parts": 1,
        "min_segment_survival_fraction": 0.75,
        "minimum_surviving_segments": 2,
        "optional_decorative_features": [],
        "bang_segmentation_requirements": [
            "Keep the primary moving part visually separate from the static body.",
            "Merge static details into a few broad 2x2-compatible surfaces.",
            "Target two to four semantic regions and about 20 to 28 blocks.",
            "Do not preserve decorative/contact-only fragments as separate segments.",
        ],
    }
    segment_targets = semantic_segment_targets(
        {"artifact_label": artifact, "artifact_family": "teacher-selected story build", "parts": parts, "build_constraints": build_constraints}
    )
    build_constraints.setdefault("required_visible_parts", segment_targets)
    build_constraints.setdefault("semantic_segment_targets", segment_targets)
    static_merge_note = (
        f"Teacher-requested static details ({', '.join(static_names)}) should be represented as labels or surface details inside those large regions, not separate source segments. "
        if static_names
        else ""
    )
    base_context = {
        "storybook_title": title,
        "grade_band": summary.grade_band,
        "duration_minutes": summary.duration_minutes,
        "theme": summary.agreed_theme,
        "artifact_label": artifact,
        "artifact_family": "teacher-selected story build",
        "parts": parts,
        "learning_objectives": summary.learning_objectives,
        "literacy_focus": summary.literacy_focus,
        "sel_focus": summary.sel_focus,
        "vocabulary": [
            {"term": word, "definition": f"Story vocabulary connected to {title}"}
            for word in (analysis.vocabulary_opportunities if analysis else [])
        ],
        "rodin_prompt": (
            f"Create a very simple chunky block-toy model of a {artifact}. "
            f"Use only {len(segment_targets)} large visible regions for the validated build: {', '.join(segment_targets)}. "
            f"Movement intent: {movement_text}. "
            "Make the primary moving part visually distinct from the static body so Bang segmentation can identify it. "
            f"{static_merge_note}"
            "Use chunky plastic block-like toy geometry, stable proportions, simple readable shapes, and broad flat contact surfaces. "
            "Avoid thin fins, tiny details, smooth tapers, dense curves, connector/contact decorations, unsupported decorative pieces, and features smaller than a 2x2 block footprint."
        ),
        "build_constraints": build_constraints,
    }
    return apply_catalog_constraints(base_context)


def planning_state_snapshot(session: SessionState) -> dict:
    analysis = session.storybook_analysis
    summary = session.consultation_summary
    reqs = session.block_requirements
    user_messages = [
        m.get("content", "") for m in session.teacher_messages if m.get("role") == "user"
    ]
    chat_text = " ".join(user_messages).lower()

    grade = summary.grade_band if summary else _grade_from_text(chat_text)
    duration = summary.duration_minutes if summary else _duration_from_text(chat_text)
    theme = summary.agreed_theme if summary else (_theme_from_text(chat_text) or (analysis.themes[0] if analysis and analysis.themes else ""))
    artifact = ""
    if reqs:
        artifact = reqs.artifact_label
    elif summary:
        artifact = summary.agreed_artifact
    elif analysis and analysis.buildable_objects:
        artifact = analysis.buildable_objects[0]
    moving_parts = []
    static_parts = []
    if reqs:
        for part in reqs.parts:
            movement = str(part.movement).strip().lower()
            item = {
                "part_name": part.part_name,
                "movement": movement,
                "notes": part.notes,
            }
            if "static" in movement:
                static_parts.append(item)
            else:
                moving_parts.append(item)
        if not static_parts:
            static_parts = _static_mentions(chat_text, moving_parts)
    else:
        mentions = _movement_mentions(chat_text)
        moving_parts = [item for item in mentions if item.get("movement") != "static"]
        static_parts = [item for item in mentions if item.get("movement") == "static"]
        if not static_parts:
            static_parts = _static_mentions(chat_text, moving_parts)
    learning_goals = summary.learning_objectives if summary else []
    if not learning_goals:
        learning_goals = _learning_goals_from_text(chat_text)
    vocabulary = analysis.vocabulary_opportunities if analysis else []
    movement_confirmed = bool(moving_parts) or _movement_was_confirmed(user_messages)
    state = {
        "target_grade": grade or "",
        "duration_minutes": duration or "",
        "core_concept": theme or "",
        "learning_goals": learning_goals,
        "story_emphasis": theme or "",
        "build_object": artifact or "",
        "moving_parts": moving_parts,
        "movement_confirmed": movement_confirmed,
        "static_parts": static_parts,
        "static_parts_confirmed": bool(static_parts),
        "constraints": _constraints_from_text(chat_text),
        "literacy_focus": summary.literacy_focus if summary else (", ".join(vocabulary[:4]) if vocabulary else ""),
        "sel_focus": summary.sel_focus if summary else ((analysis.sel_angles[0] if analysis and analysis.sel_angles else "")),
        "framework_matches": [
            "NGSS engineering design",
            "CCSS speaking/listening and vocabulary",
            "CASEL collaboration and perseverance",
            "UDL visual, verbal, and tactile expression",
            "Science of Reading vocabulary and sound awareness",
        ],
    }
    return _merge_planning_state(
        state,
        session.planning_state,
        teacher_messages=session.teacher_messages,
    )


def _merge_planning_state(
    base: dict,
    update: dict | None,
    *,
    teacher_messages: list[dict[str, str]] | None = None,
) -> dict:
    """Merge confirmed values without letting empty inference erase prior work."""
    merged = dict(base)
    for key, value in (update or {}).items():
        if key == "required_complete" or value is None:
            continue
        if value == "":
            continue
        if value == [] and key != "moving_parts":
            continue
        merged[key] = value

    messages = [
        item.get("content", "")
        for item in (teacher_messages or [])
        if item.get("role") == "user"
    ]
    if _latest_movement_decision(messages) == "none":
        merged["moving_parts"] = []
        merged["movement_confirmed"] = True
    elif merged.get("moving_parts"):
        merged["movement_confirmed"] = True

    if merged.get("static_parts"):
        merged["static_parts_confirmed"] = True

    merged["required_complete"] = all(
        [
            merged.get("target_grade"),
            merged.get("duration_minutes"),
            merged.get("core_concept"),
            merged.get("learning_goals"),
            merged.get("build_object"),
            merged.get("movement_confirmed"),
            merged.get("static_parts"),
            merged.get("constraints"),
            merged.get("literacy_focus"),
            merged.get("sel_focus"),
        ]
    )
    return merged


def planning_ready(session: SessionState, consultation_ready: bool) -> bool:
    state = planning_state_snapshot(session)
    return bool(state.get("required_complete"))


def _missing_planning_fields(state: dict) -> list[str]:
    labels = [
        ("target_grade", "target grade"),
        ("duration_minutes", "lesson duration"),
        ("core_concept", "core concept or story theme"),
        ("learning_goals", "learning goals"),
        ("build_object", "build object"),
        ("static_parts", "static parts"),
        ("constraints", "classroom constraints or grouping"),
        ("literacy_focus", "literacy focus"),
        ("sel_focus", "SEL focus"),
    ]
    missing = []
    for key, label in labels:
        value = state.get(key)
        if value is None or value == "" or value == []:
            missing.append(label)
    if not state.get("movement_confirmed"):
        missing.insert(5, "moving parts or confirmation that the build is fully static")
    return missing


def _append_missing_checklist_prompt(response: str, missing: list[str]) -> str:
    if not missing:
        return response
    missing_text = ", ".join(missing)
    clean_response = _strip_missing_checklist_prompt(response)
    return (
        clean_response.rstrip()
        + "\n\n**Before we move on, I still need to complete the checklist:** "
        + missing_text
        + ". Could you share those details?"
    )


def _strip_missing_checklist_prompt(response: str) -> str:
    marker = "Before we move on, I still need to complete the checklist:"
    clean_response = response
    for needle in (f"**{marker}**", marker):
        index = clean_response.find(needle)
        if index != -1:
            clean_response = clean_response[:index]
    return clean_response.rstrip()


def _strip_premature_readiness_claims(response: str) -> str:
    """Remove model-owned status claims; checklist readiness belongs to the app."""
    blocked_phrases = (
        "all checklist",
        "checklist is complete",
        "everything is complete",
        "all lesson components are complete",
        "ready to approve",
        "ready to proceed",
        "ready to move on",
    )
    paragraphs = response.split("\n\n")
    kept = [
        paragraph
        for paragraph in paragraphs
        if not any(phrase in paragraph.lower() for phrase in blocked_phrases)
    ]
    return "\n\n".join(kept).strip()


def _first_match(text: str, options: list[str]) -> str:
    for option in options:
        if option in text:
            return option.title().replace("Grade 1", "1st Grade").replace("Grade 2", "2nd Grade")
    return ""


def _grade_from_text(text: str) -> str:
    grade_terms = (
        ("Pre-K", ("pre-k", "pre k", "preschool")),
        ("Kindergarten", ("kindergarten",)),
        ("1st Grade", ("1st grade", "first grade", "grade 1")),
        ("2nd Grade", ("2nd grade", "second grade", "grade 2")),
    )
    for normalized, terms in grade_terms:
        if any(term in text for term in terms):
            return normalized
    return ""


def _duration_from_text(text: str) -> int | None:
    import re

    match = re.search(r"(\d{2,3})\s*(?:min|minute)", text)
    if match:
        return int(match.group(1))
    return None


def _theme_from_text(text: str) -> str:
    for theme in ["perseverance", "teamwork", "community", "invention", "transportation", "problem solving"]:
        if theme in text:
            return theme
    return ""


def _constraints_from_text(text: str) -> list[str]:
    constraints = []
    for keyword in ["small group", "pairs", "partner", "limited time", "whole group", "independent"]:
        if keyword in text:
            constraints.append(keyword)
    return constraints


def _learning_goals_from_text(text: str) -> list[str]:
    goals = []
    goal_map = {
        "perseverance": "Students identify perseverance in the story and apply it while testing their build.",
        "teamwork": "Students collaborate with a partner to plan, build, test, and improve a model.",
        "vocabulary": "Students use story and build vocabulary to describe how their model works.",
        "machine": "Students explain how parts of a machine work together to solve a problem.",
        "explain": "Students explain the function of visible model parts using evidence from their build.",
        "testing": "Students test a design, notice what changes, and revise their idea.",
    }
    for keyword, goal in goal_map.items():
        if keyword in text:
            goals.append(goal)
    return goals


def _movement_mentions(text: str) -> list[dict]:
    if _contains_no_movement(text):
        return []
    candidates = [
        ("propeller", "spinning", ["spin", "spinning propeller", "rotate", "rotating propeller"]),
        ("wheels", "rolling", ["wheels roll", "rolling wheels", "wheel should move"]),
        ("door", "pivoting", ["door", "open", "pivot", "hinge"]),
        ("flap", "pivoting", ["flap", "pivot", "hinge"]),
        ("wings", "static", ["wing", "fixed", "static"]),
    ]
    found = []
    for part, movement, keywords in candidates:
        if any(keyword in text for keyword in keywords):
            found.append({"part_name": part, "movement": movement, "notes": "Captured from teacher conversation"})
    return found


def _contains_no_movement(text: str) -> bool:
    normalized = " ".join(text.lower().replace("-", " ").split())
    return any(
        phrase in normalized
        for phrase in (
            "no moving parts",
            "nothing moves",
            "nothing should move",
            "fully static",
            "entirely static",
            "all parts are static",
            "everything is static",
        )
    )


def _latest_movement_decision(messages: list[str]) -> str | None:
    for message in reversed(messages):
        lowered = message.lower()
        if _contains_no_movement(lowered):
            return "none"
        if _movement_mentions(lowered):
            return "moving"
    return None


def _movement_was_confirmed(messages: list[str]) -> bool:
    return _latest_movement_decision(messages) is not None


def _static_mentions(text: str, moving_parts: list[dict] | None = None) -> list[dict]:
    moving_names = {
        str(item.get("part_name", "")).lower()
        for item in (moving_parts or [])
    }
    static_cues = ("static", "stay still", "fixed", "not move", "do not move", "stay in place")
    if not any(cue in text for cue in static_cues):
        return []
    candidates = [
        "body",
        "wings",
        "cargo compartment",
        "compartment",
        "tail",
        "frame",
        "nose",
        "traffic signal",
        "signal body",
        "signal lights",
        "pole",
        "base",
    ]
    found = []
    for part in candidates:
        if part in text and part not in moving_names:
            found.append({"part_name": part, "movement": "static", "notes": "Captured from teacher conversation"})
    return found


def start_session_model_preview(session_id: str, context_override: dict | None = None) -> dict:
    session = _sessions[session_id]
    reset_downstream_model_outputs(session)
    context = apply_catalog_constraints(context_override or build_seed_context(session))
    session.build_constraints = context.get("build_constraints", session.build_constraints)
    job = start_model_preview_job(context, session_id=session_id)
    session.model_preview_job_id = job["job_id"]
    return job


def get_session_model_preview(session_id: str) -> dict | None:
    session = _sessions[session_id]
    if not session.model_preview_job_id:
        return None
    job = build_snapshot(session.model_preview_job_id)
    if job and job.get("status") == "complete":
        session.model_preview_result = job.get("result")
    return job


def reset_downstream_model_outputs(session: SessionState) -> None:
    """Discard artifacts that were generated from an older model preview."""
    session.segment_job_id = None
    session.document_job_id = None
    session.build_job_id = None
    session.segment_result = None
    session.build_result = None
    session.document_result = None


def confirm_session_model(session_id: str) -> dict:
    session = _sessions[session_id]
    job = get_session_model_preview(session_id)
    if not job or job.get("status") != "complete":
        raise ValueError("Model preview must be complete before confirming.")
    session.model_preview_result = job.get("result")
    reset_downstream_model_outputs(session)
    session.phase = SessionPhase.segments_connectors
    return {"status": "confirmed", "phase": session.phase.value, "model_preview": session.model_preview_result}


def start_session_segments(session_id: str) -> dict:
    session = _sessions[session_id]
    preview = session.model_preview_result or (get_session_model_preview(session_id) or {}).get("result")
    if not preview:
        raise ValueError("Confirm a model preview before segmentation.")
    rodin = preview.get("rodin", {})
    job = start_segments_job(
        preview.get("context", build_seed_context(session)),
        rodin.get("task_uuid"),
        rodin.get("files", []),
        session_id=session_id,
    )
    session.segment_job_id = job["job_id"]
    return job


def get_session_segments(session_id: str) -> dict | None:
    session = _sessions[session_id]
    if not session.segment_job_id:
        return None
    job = build_snapshot(session.segment_job_id)
    if job and job.get("status") == "complete":
        session.segment_result = job.get("result")
        session.build_result = job.get("result")
    return job


def confirm_session_segments(session_id: str) -> dict:
    session = _sessions[session_id]
    job = get_session_segments(session_id)
    if not job or job.get("status") != "complete":
        raise ValueError("Segments must be complete before confirming.")
    session.segment_result = job.get("result")
    session.build_result = job.get("result")
    _require_validated_build_result(session.build_result)
    session.phase = SessionPhase.build_plan
    return {"status": "confirmed", "phase": session.phase.value}


def confirm_session_build_plan(session_id: str) -> dict:
    session = _sessions[session_id]
    if not session.build_result:
        raise ValueError("Build plan is not available yet.")
    _require_validated_build_result(session.build_result)
    session.phase = SessionPhase.lesson_bundle
    return {"status": "confirmed", "phase": session.phase.value}


def _require_validated_build_result(result: dict) -> None:
    build_plan = (result or {}).get("build_plan", {})
    notebook = build_plan.get("notebook_outputs", {}) if isinstance(build_plan, dict) else {}
    validated = {}
    if isinstance(build_plan, dict):
        validated = build_plan.get("validated_planner") or notebook.get("validated_planner") or {}
    if validated and not validated.get("final_claim_valid"):
        status = validated.get("build_status") or "not validated"
        reason = validated.get("reason") or "Regenerate a simpler model before moving to classroom build instructions."
        raise ValueError(f"Validated build is not approvable yet ({status}). {reason}")


def start_session_documents(session_id: str) -> dict:
    session = _sessions[session_id]
    if not session.storybook_text or not session.build_result:
        raise ValueError("Story and build plan are required before documents.")
    context = session.build_result.get("context") or build_seed_context(session)
    build_plan = session.build_result.get("build_plan", {})
    job = start_document_job(session.storybook_text, context, build_plan, session_id=session_id)
    session.document_job_id = job["job_id"]
    return job


def get_session_documents(session_id: str) -> dict | None:
    session = _sessions[session_id]
    if not session.document_job_id:
        return None
    job = build_snapshot(session.document_job_id)
    if job and job.get("status") == "complete":
        session.document_result = job.get("result")
    return job


def confirm_session_documents(session_id: str) -> dict:
    session = _sessions[session_id]
    job = get_session_documents(session_id)
    result = (job or {}).get("result") or session.document_result
    bundle = (result or {}).get("document_bundle", {})
    if not bundle.get("all_valid"):
        raise ValueError("All lesson bundle documents must validate before the session can be completed.")
    session.document_result = result
    session.phase = SessionPhase.complete
    return {"status": "confirmed", "phase": session.phase.value}


async def start_session_build(session_id: str) -> dict:
    session = _sessions[session_id]
    if not session.storybook_text:
        raise ValueError("No story text is available for this session.")
    context = build_seed_context(session)
    intent = build_teacher_connection_intent(session)
    job = start_build_job(
        session.storybook_text,
        teacher_connection_intent=intent,
        seed_context=context,
        session_id=session_id,
    )
    session.build_job_id = job["job_id"]
    return job


def get_session_build(session_id: str) -> dict | None:
    session = _sessions[session_id]
    if not session.build_job_id:
        return None
    job = build_snapshot(session.build_job_id)
    if job and job.get("status") == "complete":
        session.build_result = job.get("result")
        session.phase = SessionPhase.refinement
    return job


def reset_session_build(session_id: str) -> None:
    session = _sessions[session_id]
    session.build_job_id = None
    session.build_result = None
    if session.block_requirements:
        session.phase = SessionPhase.generation
