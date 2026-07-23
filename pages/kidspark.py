"""KidSpark AI six-step teacher workflow."""

from __future__ import annotations

import json
import os
import re
import time
from base64 import b64encode
from pathlib import Path
from typing import Any

import requests
import streamlit as st

BACKEND_URL = os.getenv("KIDSPARK_BACKEND_URL", "http://localhost:8001")
OPENAI_KEY_FILE = Path(__file__).resolve().parents[1] / "openai.key"
STATIC_DOWNLOAD_DIR = Path(__file__).resolve().parents[1] / "static" / "kidspark_downloads"
DATA_URI_DOWNLOAD_LIMIT = 2_500_000

SAMPLE_STORY = """Milo's Flying Delivery

Milo was a young inventor who loved building things in his workshop. His
grandmother, Grandma Rose, ran a small bakery on the other side of town.
Every Saturday, Milo walked her fresh-baked cookies to their neighbors.

One rainy Saturday, Milo had an idea. "What if I could fly the cookies
to everyone?" He grabbed his toolbox and started designing a flying
delivery vehicle.

His first attempt crashed into the garden fence. His second attempt
flew sideways into a tree. Milo felt frustrated, but Grandma Rose
reminded him: "Every great inventor learns from what didn't work."

Milo asked his neighborhood friends for help. Together, they redesigned
the wings to be wider, added a stronger propeller, and built a secure
cargo compartment for the cookies.

On the next attempt, the flying delivery vehicle soared over the
rooftops! Milo delivered cookies to every neighbor, and everyone
cheered. Milo learned that perseverance and teamwork can turn any
idea into reality.
"""

WIZARD_STEPS = [
    ("story_upload", "Upload Story"),
    ("lesson_planning", "Plan With Coach"),
    ("model_preview", "Model Preview"),
    ("segments_connectors", "Segments & Connectors"),
    ("build_plan", "Build Plan"),
    ("lesson_bundle", "Lesson Bundle"),
    ("complete", "Ready for Class"),
]

STEP_INDEX = {key: index for index, (key, _) in enumerate(WIZARD_STEPS)}
LEGACY_PHASE_MAP = {
    "consultation": "lesson_planning",
    "block_awareness": "lesson_planning",
    "generation": "model_preview",
    "refinement": "segments_connectors",
}

SUGGESTED_TEACHER_DIRECTION = (
    "I teach 1st grade for 40 minutes. Focus on perseverance, teamwork, "
    "and how inventors learn from testing. Students should build a flying "
    "delivery plane. The propeller should spin. The body, wings, cargo "
    "compartment, and tail should stay static. Use vocabulary and rhyming "
    "around machine, delivery, and propeller. Students will work in partners."
)

st.set_page_config(page_title="KidSpark AI", page_icon=":bricks:", layout="wide")

st.markdown(
    """
    <style>
    [data-testid="stSidebarNav"] { display: none; }
    .ks-shell-title {
        font-size: 2.1rem;
        font-weight: 900;
        letter-spacing: 0;
        margin-bottom: .15rem;
    }
    .ks-subtle {
        color: #657080;
        font-size: .96rem;
    }
    .ks-step-card {
        padding: .9rem 1rem;
        margin: .55rem 0;
        border: 1px solid #d9e0e8;
        background: #f7f8fb;
        border-radius: 8px;
        font-weight: 800;
    }
    .ks-step-card.done {
        border-color: #bfe4ca;
        background: #e8f6ec;
        color: #216736;
    }
    .ks-step-card.active {
        border-color: #f0dc94;
        background: #fff8df;
        color: #7d6111;
    }
    .ks-panel {
        padding: 1rem 1.1rem;
        border: 1px solid #dfe7ef;
        border-radius: 8px;
        background: #ffffff;
    }
    .ks-sticky-panel {
        position: sticky;
        top: 1rem;
    }
    .ks-component-row {
        display: grid;
        grid-template-columns: 28px 150px 1fr;
        gap: .6rem;
        padding: .55rem 0;
        border-bottom: 1px solid #edf1f5;
        align-items: start;
    }
    .ks-component-row:last-child { border-bottom: 0; }
    .ks-label { color: #657080; font-weight: 800; }
    .ks-value { color: #222938; }
    .ks-empty { color: #a1a9b5; }
    .ks-check {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 1.25rem;
        height: 1.25rem;
        border-radius: 999px;
        background: #34a853;
        color: #fff;
        font-weight: 900;
        margin-right: .4rem;
    }
    .ks-pending {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 1.25rem;
        height: 1.25rem;
        border-radius: 999px;
        border: 2px solid #cbd5e1;
        color: #94a3b8;
        font-weight: 900;
    }
    .ks-question-cue {
        display: inline-block;
        padding: .08rem .35rem;
        border-radius: 6px;
        background: #fff2b8;
        color: #6f5100;
        font-weight: 900;
    }
    .ks-ready-note {
        margin-top: .75rem;
        padding: .85rem .9rem;
        border-radius: 8px;
        background: #eaf6ee;
        color: #216736;
        font-weight: 800;
    }
    .ks-blocked-note {
        margin-top: .75rem;
        padding: .85rem .9rem;
        border-radius: 8px;
        background: #eef5ff;
        color: #17437a;
        font-weight: 700;
    }
    div[data-testid="column"] div[data-testid="stVerticalBlock"]:has(#ks-lesson-components-sticky) {
        position: static;
        z-index: 20;
        align-self: flex-start;
        max-height: none;
        overflow: visible;
        padding-bottom: 1rem;
        background: #ffffff;
    }
    .ks-wait {
        position: fixed;
        right: 2rem;
        bottom: 2rem;
        z-index: 9999;
        width: min(420px, calc(100vw - 3rem));
        padding: 1rem 1.1rem;
        border-radius: 8px;
        border: 1px solid #f3c0b7;
        background: #fff8f5;
        box-shadow: 0 18px 50px rgba(28, 35, 47, .18);
    }
    .ks-wait-title {
        color: #d94d49;
        font-weight: 900;
        margin-bottom: .25rem;
    }
    .ks-wait-bar {
        height: .35rem;
        overflow: hidden;
        border-radius: 999px;
        background: #f7ddd7;
        margin-top: .7rem;
    }
    .ks-wait-bar span {
        display: block;
        width: 38%;
        height: 100%;
        border-radius: inherit;
        background: #ef5a55;
        animation: ks-slide 1.2s ease-in-out infinite;
    }
    @keyframes ks-slide {
        0% { transform: translateX(-110%); }
        100% { transform: translateX(270%); }
    }
    .ks-break-card {
        margin: 1rem 0;
        padding: 1.1rem 1.2rem;
        border: 1px solid #f0c7a7;
        border-radius: 8px;
        background: linear-gradient(135deg, #fff8ed, #fffefe);
        color: #6f3d12;
    }
    .ks-break-title {
        font-size: 1.15rem;
        font-weight: 900;
        margin-bottom: .25rem;
    }
    .ks-steam {
        display: inline-block;
        animation: ks-bob 1.4s ease-in-out infinite;
        margin-right: .35rem;
    }
    @keyframes ks-bob {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-4px); }
    }
    .ks-hero-upload {
        min-height: 230px;
        display: flex;
        align-items: center;
        justify-content: center;
        border: 2px dashed #c7d2df;
        border-radius: 8px;
        background: #fbfcfe;
        color: #536173;
        font-weight: 800;
    }
    div[data-testid="stButton"] button {
        border-radius: 8px;
        font-weight: 800;
    }
    div[data-testid="stTabs"] button p {
        font-weight: 850;
        font-size: 1rem;
    }
    .ks-direct-download {
        margin: .35rem 0 1rem 0;
        font-size: .92rem;
        color: #475467;
    }
    .ks-direct-download a {
        color: #1f6fb2;
        font-weight: 750;
        text-decoration: none;
    }
    .ks-direct-download a:hover {
        text-decoration: underline;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def api(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    try:
        resp = getattr(requests, method)(f"{BACKEND_URL}{path}", timeout=90, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except requests.ConnectionError:
        st.error(f"Cannot reach the KidSpark backend at {BACKEND_URL}.")
        st.stop()
    except requests.HTTPError as exc:
        st.error(exc.response.text)
        st.stop()


def api_bytes(path: str) -> bytes | None:
    try:
        resp = requests.get(f"{BACKEND_URL}{path}", timeout=90)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException as exc:
        st.warning(f"Could not prepare the PDF download yet: {exc}")
        return None


def stage_pdf_download(kind: str, pdf_bytes: bytes) -> str | None:
    session_id = st.session_state.get("ks_session_id", "session")
    if not pdf_bytes:
        return None
    try:
        target_dir = STATIC_DOWNLOAD_DIR / re.sub(r"[^a-zA-Z0-9_-]+", "_", str(session_id))
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{kind}.pdf"
        target.write_bytes(pdf_bytes)
        return f"/app/static/kidspark_downloads/{target_dir.name}/{kind}.pdf"
    except OSError as exc:
        st.caption(f"Direct PDF link could not be staged: {exc}")
        return None


def render_pdf_downloads(kind: str, title: str, pdf_bytes: bytes) -> None:
    safe_title = title or kind.replace("_", " ").title()
    st.download_button(
        f"Download {safe_title} PDF",
        pdf_bytes,
        file_name=f"{kind}.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
    static_url = stage_pdf_download(kind, pdf_bytes)
    link_bits = []
    if static_url:
        link_bits.append(f"<a href='{static_url}' download='{kind}.pdf' target='_blank'>Open direct PDF link</a>")
    if len(pdf_bytes) <= DATA_URI_DOWNLOAD_LIMIT:
        fallback = b64encode(pdf_bytes).decode("ascii")
        link_bits.append(
            f"<a href='data:application/pdf;base64,{fallback}' download='{kind}.pdf'>Download via fallback link</a>"
        )
    if link_bits:
        st.markdown(
            "<div class='ks-direct-download'>"
            + " <span>&middot;</span> ".join(link_bits)
            + "</div>",
            unsafe_allow_html=True,
        )


def masked_key(value: str) -> str:
    if not value:
        return "Not configured"
    return f"{value[:7]}...{value[-4:]}" if len(value) > 12 else "Configured"


def local_openai_key() -> str:
    if "ks_openai_api_key" in st.session_state:
        return st.session_state["ks_openai_api_key"]
    if OPENAI_KEY_FILE.exists():
        try:
            key = OPENAI_KEY_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            key = ""
        st.session_state["ks_openai_api_key"] = key
        return key
    return ""


def backend_openai_status() -> dict[str, Any]:
    try:
        resp = requests.get(f"{BACKEND_URL}/api/v1/settings/openai-key", timeout=8)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return {"configured": False, "masked": ""}


def save_openai_key(api_key: str) -> None:
    key = api_key.strip()
    if not key:
        st.warning("Paste an OpenAI API key before saving.")
        return
    OPENAI_KEY_FILE.write_text(key, encoding="utf-8")
    st.session_state["ks_openai_api_key"] = key
    try:
        requests.post(f"{BACKEND_URL}/api/v1/settings/openai-key", json={"api_key": key}, timeout=15).raise_for_status()
    except requests.RequestException:
        st.warning("Saved locally. Restart or reconnect the backend to use the new key there.")
    else:
        st.success("OpenAI key saved for this app.")


def render_openai_key_box() -> None:
    current = local_openai_key()
    backend_status = backend_openai_status()
    status_text = masked_key(current) if current else backend_status.get("masked") or "Not configured"
    st.markdown("### OpenAI")
    st.caption(f"Status: {status_text}")
    entered = st.text_input(
        "OpenAI API key",
        value=current,
        type="password",
        key="ks_sidebar_openai_key_input",
        label_visibility="collapsed",
        placeholder="sk-...",
    )
    if st.button("Save OpenAI Key", use_container_width=True):
        save_openai_key(entered)


def reset_session() -> None:
    for key in list(st.session_state.keys()):
        if key.startswith("ks_") or key.startswith("approve_") or key.startswith("show_"):
            st.session_state.pop(key, None)


def hydrate_session_from_query() -> None:
    if "ks_session_id" in st.session_state:
        return
    session_id = st.query_params.get("session_id")
    if not session_id:
        return
    data = api("get", f"/api/v1/sessions/{session_id}")
    st.session_state["ks_session_id"] = session_id
    set_phase(data.get("phase", "story_upload"))
    st.session_state["ks_story_analysis"] = data.get("storybook_analysis")
    st.session_state["ks_messages"] = data.get("teacher_messages") or []
    st.session_state["ks_planning_state"] = data.get("planning_state") or {}
    if data.get("model_preview_result"):
        st.session_state["ks_model_result"] = data["model_preview_result"]
        st.session_state["ks_model_context"] = data["model_preview_result"].get("context", {})
    if data.get("segment_result"):
        st.session_state["ks_segment_result"] = data["segment_result"]
    if data.get("document_result"):
        st.session_state["ks_document_result"] = data["document_result"]
    if data.get("model_preview_job_id"):
        try:
            st.session_state["ks_model_job"] = api("get", f"/api/v1/sessions/{session_id}/model-preview")
        except Exception:
            pass
    if data.get("segment_job_id"):
        try:
            st.session_state["ks_segment_job"] = api("get", f"/api/v1/sessions/{session_id}/segments")
        except Exception:
            pass
    if data.get("document_job_id"):
        try:
            st.session_state["ks_document_job"] = api("get", f"/api/v1/sessions/{session_id}/documents")
        except Exception:
            pass


def current_phase() -> str:
    raw = st.session_state.get("ks_phase", "story_upload")
    return LEGACY_PHASE_MAP.get(raw, raw)


def set_phase(phase: str) -> None:
    st.session_state["ks_phase"] = LEGACY_PHASE_MAP.get(phase, phase)


def clear_downstream_generation_state() -> None:
    """Clear UI caches that depend on the currently approved model preview."""
    for key in (
        "ks_segment_job",
        "ks_segment_result",
        "ks_document_job",
        "ks_document_result",
        "ks_step_approvals",
        "ks_document_approvals",
        "ks_segment_editor",
        "ks_interface_editor",
    ):
        st.session_state.pop(key, None)


def phase_position(phase: str) -> int:
    return STEP_INDEX.get(LEGACY_PHASE_MAP.get(phase, phase), 0)


def render_sidebar() -> None:
    with st.sidebar:
        render_openai_key_box()
        st.divider()
        st.markdown("### KidSpark AI")
        st.caption("Story to BrickSmart lesson bundle")
        if st.button("New Lesson Session", use_container_width=True):
            reset_session()
            st.rerun()
        phase = current_phase()
        current = phase_position(phase)
        st.divider()
        st.markdown("### Progress")
        st.progress(current / (len(WIZARD_STEPS) - 1))
        for idx, (key, label) in enumerate(WIZARD_STEPS):
            if key == "complete" and phase != "complete":
                continue
            state = "done" if idx < current else "active" if idx == current else "todo"
            prefix = "&#10003; " if state == "done" else ""
            st.markdown(
                f"<div class='ks-step-card {state}'>{prefix}{idx + 1}. {label}</div>",
                unsafe_allow_html=True,
            )
        if "ks_session_id" in st.session_state:
            st.divider()
            st.caption(f"Session: `{st.session_state['ks_session_id'][:8]}...`")


def existing_file(path_value: Any) -> Path | None:
    if not path_value:
        return None
    path = Path(str(path_value))
    return path if path.is_file() else None


def normalized_validated_planner(validated: dict[str, Any], notebook: dict[str, Any]) -> dict[str, Any]:
    """Translate raw validated-planner failures into teacher-actionable states."""
    payload = dict(validated or {})
    if not payload or payload.get("final_claim_valid"):
        return payload
    status = str(payload.get("build_status") or "").upper()
    if status and status != "INCOMPLETE":
        return payload

    blocks = notebook.get("blocks") if isinstance(notebook.get("blocks"), list) else []
    block_count = int(notebook.get("block_count") or len(blocks) or payload.get("final_block_count") or 0)
    segment_count = int(notebook.get("segment_count") or 0)
    segment_viability = dict(payload.get("segment_viability") or {})
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    semantic = summary.get("semantic_target_preservation") if isinstance(summary.get("semantic_target_preservation"), dict) else {}
    confirmed_count = (
        len(semantic.get("ungrouped_authoritative_source_segment_ids") or [])
        or int(segment_viability.get("confirmed_segment_count") or 0)
    )

    max_blocks = int(segment_viability.get("max_validated_blocks") or 32)
    max_segments = int(segment_viability.get("max_semantic_segments") or 5)
    semantic_status = str(semantic.get("status") or segment_viability.get("semantic_preservation_status") or "")
    missing_segments = (
        semantic.get("missing_ungrouped_authoritative_source_segment_ids")
        or segment_viability.get("missing_segment_ids")
        or []
    )

    reasons: list[str] = []
    if block_count > max_blocks:
        reasons.append(f"Notebook approximation needs {block_count} blocks; standard-kit preview budget is {max_blocks}.")
    if confirmed_count > max_segments:
        reasons.append(f"Bang produced {confirmed_count} confirmed source segments; standard-kit validation target is {max_segments} or fewer.")
    if segment_count > max_segments:
        reasons.append(f"Notebook physicalization has {segment_count} color-coded segments; validated classroom builds should have {max_segments} or fewer.")
    if semantic_status.startswith("FAIL"):
        reasons.append(f"Validated semantic preservation failed; missing segment ids: {missing_segments or 'unknown'}.")

    if reasons:
        segment_viability.update(
            {
                "notebook_block_count": block_count,
                "confirmed_segment_count": confirmed_count,
                "physical_segment_count": segment_count,
                "max_validated_blocks": max_blocks,
                "max_semantic_segments": max_segments,
                "semantic_preservation_status": semantic_status or None,
                "missing_segment_ids": missing_segments,
            }
        )
        payload["build_status"] = "NEEDS_SIMPLER_MODEL"
        payload["reason"] = payload.get("reason") or " ".join(reasons)
        payload["recommendation"] = payload.get("recommendation") or (
            "Regenerate a simpler model with fewer large parts, one clear moving feature, "
            "and broad separated 2x2-compatible surfaces before generating final instructions."
        )
        payload["segment_viability"] = segment_viability
    return payload


def stage4_simplification_recommendation(
    validated: dict[str, Any],
    notebook: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """Create a concrete recovery package for a model that cannot validate."""
    viability = dict(validated.get("segment_viability") or {})
    max_blocks = int(viability.get("max_validated_blocks") or 32)
    max_segments = int(viability.get("max_semantic_segments") or 5)
    block_count = int(viability.get("notebook_block_count") or notebook.get("block_count") or 0)
    physical_segments = int(viability.get("physical_segment_count") or notebook.get("segment_count") or 0)
    confirmed_segments = int(viability.get("confirmed_segment_count") or physical_segments or 0)
    artifact = str(context.get("artifact_label") or context.get("build_object") or context.get("object_type_hint") or "classroom model")

    parts = context.get("parts", []) if isinstance(context.get("parts"), list) else []
    moving_parts = [
        str(part.get("part_name", "")).strip()
        for part in parts
        if str(part.get("part_name", "")).strip() and part.get("movement") != "static"
    ]
    primary_moving = moving_parts[0] if moving_parts else "one primary moving feature"
    artifact_lower = artifact.lower()
    if any(token in artifact_lower for token in ("plane", "airplane", "vehicle", "fly", "flying")):
        required_parts = [primary_moving, "merged body/fuselage", "one broad wing slab"]
        forbidden_details = "tail, cargo compartment, windows, landing gear, wheel sets, decorative ridges, and tiny connector/contact regions"
    else:
        required_parts = [primary_moving, "merged main body", "single support/base region"]
        forbidden_details = "windows, trim, small decorations, separate shelves, tiny connector/contact regions, and extra sub-parts"
    required_parts = list(dict.fromkeys([part for part in required_parts if part]))

    target_blocks = min(max_blocks, 28)
    target_segments = min(max_segments, 4)
    rodin_prompt = (
        f"Create a simple chunky block-toy model of a {artifact}. "
        f"Use only {target_segments} large visible regions: {', '.join(required_parts)}. "
        f"The only moving feature should be {primary_moving}; make it clearly separated from the static body. "
        f"Merge all static details into broad 2x2-compatible block surfaces. "
        f"Do not create separate {forbidden_details}. "
        f"Keep the shape compact and classroom-buildable: about 20 to {target_blocks} total blocks, "
        f"two to {target_segments} semantic parts, no decorative micro-pieces, and strong flat contact surfaces."
    )
    bang_requirements = [
        "Keep the primary moving part visually separate from the static body.",
        "Merge static details into a few broad 2x2-compatible surfaces.",
        f"Target two to {target_segments} semantic regions and about 20 to {target_blocks} blocks.",
        "Do not preserve decorative/contact-only fragments as separate segments.",
    ]

    reasons = []
    if block_count and block_count > max_blocks:
        reasons.append(f"Reduce block count from about {block_count} to {target_blocks} or fewer.")
    if confirmed_segments and confirmed_segments > max_segments:
        reasons.append(f"Reduce Bang source segments from {confirmed_segments} to {target_segments} or fewer.")
    if physical_segments and physical_segments > max_segments:
        reasons.append(f"Merge voxelized physical regions from {physical_segments} to {target_segments} or fewer.")
    if not reasons:
        reasons.append("Use fewer, larger parts so the validated planner can preserve each segment.")

    return {
        "summary": (
            "KidSpark cannot create valid standard-kit instructions from this model yet. "
            "The safest next step is to regenerate a simpler model preview."
        ),
        "reasons": reasons,
        "rodin_prompt": rodin_prompt,
        "build_constraints": {
            "object_type_hint": artifact,
            "required_visible_parts": required_parts,
            "moving_parts": [primary_moving] if primary_moving else [],
            "wheel_count": 0,
            "symmetry": "auto",
            "inventory_mode": "standard_kit",
            "max_validated_blocks": target_blocks,
            "max_semantic_segments": target_segments,
            "max_moving_parts": 1 if primary_moving else 0,
            "min_segment_survival_fraction": 0.75,
            "minimum_surviving_segments": 2,
            "optional_decorative_features": [],
            "bang_segmentation_requirements": bang_requirements,
        },
    }


def seed_build_constraint_widget_values(constraints: dict[str, Any], *, overwrite: bool = False) -> None:
    values = {
        "ks_constraint_object_type": str(constraints.get("object_type_hint", "")),
        "ks_constraint_inventory_mode": str(constraints.get("inventory_mode", "standard_kit")),
        "ks_constraint_symmetry": str(constraints.get("symmetry", "auto")),
        "ks_constraint_required": ", ".join(str(x) for x in constraints.get("required_visible_parts", [])),
        "ks_constraint_moving": ", ".join(str(x) for x in constraints.get("moving_parts", [])),
        "ks_constraint_wheel_count": int(constraints.get("wheel_count") or 0),
        "ks_constraint_max_blocks": int(constraints.get("max_validated_blocks") or 32),
        "ks_constraint_max_segments": int(constraints.get("max_semantic_segments") or 5),
        "ks_constraint_max_moving": int(constraints.get("max_moving_parts") or 1),
        "ks_constraint_optional": ", ".join(str(x) for x in constraints.get("optional_decorative_features", [])),
        "ks_constraint_bang": "\n".join(str(x) for x in constraints.get("bang_segmentation_requirements", [])),
    }
    for key, value in values.items():
        if overwrite or key not in st.session_state:
            st.session_state[key] = value


def apply_stage4_recommendation_to_step3(context: dict[str, Any]) -> dict[str, Any] | None:
    recommendation = st.session_state.get("ks_stage4_recommendation")
    if not isinstance(recommendation, dict):
        return None
    token = str(recommendation.get("rodin_prompt", ""))[:120]
    if st.session_state.get("ks_stage4_recommendation_applied") == token:
        return recommendation
    updated_context = dict(context)
    merged_constraints = default_build_constraints(updated_context)
    merged_constraints.update(recommendation.get("build_constraints") or {})
    updated_context["build_constraints"] = merged_constraints
    updated_context["rodin_prompt"] = recommendation.get("rodin_prompt") or updated_context.get("rodin_prompt", "")
    st.session_state["ks_model_context"] = updated_context
    st.session_state["ks_rodin_prompt"] = updated_context["rodin_prompt"]
    seed_build_constraint_widget_values(merged_constraints, overwrite=True)
    st.session_state["ks_stage4_recommendation_applied"] = token
    return recommendation


def image_from_files(files: list[str]) -> Path | None:
    for file in files:
        path = existing_file(file)
        if path and path.suffix.lower() in {".webp", ".png", ".jpg", ".jpeg"}:
            return path
    return None


def coarse_validation_parts(context: dict[str, Any]) -> list[str]:
    constraints = context.get("build_constraints") or {}
    existing_targets = constraints.get("semantic_segment_targets")
    if isinstance(existing_targets, list) and existing_targets:
        return [str(item) for item in existing_targets if str(item).strip()]

    parts = context.get("parts", [])
    artifact = str(context.get("artifact_label") or context.get("artifact_family") or "model").lower()
    max_segments = int(constraints.get("max_semantic_segments") or 4)
    max_moving = int(constraints.get("max_moving_parts") or 1)
    moving = [
        str(part.get("part_name", "")).strip()
        for part in parts
        if str(part.get("movement", "static")).lower() != "static" and str(part.get("part_name", "")).strip()
    ][:max_moving]
    static_text = " ".join(
        str(part.get("part_name", ""))
        for part in parts
        if str(part.get("movement", "static")).lower() == "static"
    ).lower()

    targets = [f"{name} as the one separated moving feature" for name in moving]
    if any(token in artifact or token in static_text for token in ["plane", "airplane", "vehicle", "car", "truck", "delivery"]):
        targets.extend(
            [
                "single main body/fuselage with cargo, nose, and tail details merged",
                "one broad left-right wing or support slab",
            ]
        )
    elif any(token in artifact or token in static_text for token in ["house", "bakery", "shop", "building", "wall", "roof"]):
        targets.extend(["single boxy building shell with walls and roof merged", "front opening or counter detail merged into the shell"])
    elif any(token in artifact or token in static_text for token in ["tree", "plant", "garden"]):
        targets.extend(["single trunk/body column", "one broad canopy or platform mass"])
    else:
        targets.extend(["single main body/core", "one broad support/base region"])

    deduped: list[str] = []
    seen: set[str] = set()
    for target in targets:
        key = target.lower()
        if key not in seen:
            deduped.append(target)
            seen.add(key)
    return deduped[:max_segments]


def default_build_constraints(context: dict[str, Any]) -> dict[str, Any]:
    existing = dict(context.get("build_constraints") or {})
    parts = context.get("parts", [])
    moving = [part.get("part_name", "") for part in parts if part.get("movement") != "static"]
    wheels = [part for part in parts if part.get("movement") == "rolling" or "wheel" in str(part.get("part_name", "")).lower()]
    existing.setdefault("object_type_hint", context.get("artifact_label", "kidspark_model"))
    existing.setdefault("required_visible_parts", coarse_validation_parts(context))
    existing.setdefault("moving_parts", [name for name in moving if name])
    existing.setdefault("teacher_requested_static_parts", [part.get("part_name", "") for part in parts if part.get("movement") == "static"])
    existing.setdefault("wheel_count", len(wheels) if wheels else 0)
    existing.setdefault("symmetry", "auto")
    existing.setdefault("inventory_mode", "standard_kit")
    existing.setdefault("max_validated_blocks", 28)
    existing.setdefault("max_semantic_segments", 4)
    existing.setdefault("max_moving_parts", 1)
    existing.setdefault("min_segment_survival_fraction", 0.75)
    existing.setdefault("minimum_surviving_segments", 2)
    existing.setdefault("optional_decorative_features", [])
    existing.setdefault(
        "bang_segmentation_requirements",
        [
            "Keep the primary moving part visually separate from the static body.",
            "Merge static details into a few broad 2x2-compatible surfaces.",
            "Target two to four semantic regions and about 20 to 28 blocks.",
            "Do not create separate connector/contact/decorative regions for standard-kit validation.",
        ],
    )
    return existing


def render_build_constraints_editor(context: dict[str, Any]) -> dict[str, Any]:
    constraints = default_build_constraints(context)
    seed_build_constraint_widget_values(constraints)
    with st.container(border=True):
        st.markdown("#### BrickSmart Build Constraints")
        col_a, col_b, col_c = st.columns(3)
        object_type = col_a.text_input("Object type hint", key="ks_constraint_object_type")
        inventory_mode = col_b.selectbox(
            "Inventory basis",
            ["standard_kit", "unlimited"],
            key="ks_constraint_inventory_mode",
        )
        symmetry = col_c.selectbox(
            "Symmetry",
            ["auto", "left_right", "none"],
            key="ks_constraint_symmetry",
        )
        required = st.text_input(
            "Required visible parts",
            key="ks_constraint_required",
        )
        moving = st.text_input(
            "Moving parts",
            key="ks_constraint_moving",
        )
        wheel_count = st.number_input("Wheel count", min_value=0, max_value=8, step=1, key="ks_constraint_wheel_count")
        budget_a, budget_b, budget_c = st.columns(3)
        max_blocks = budget_a.number_input(
            "Max validated blocks",
            min_value=12,
            max_value=80,
            step=4,
            help="Standard-kit builds should stay small enough to validate and physically build.",
            key="ks_constraint_max_blocks",
        )
        max_segments = budget_b.number_input(
            "Max semantic parts",
            min_value=2,
            max_value=10,
            step=1,
            help="Fewer, larger source segments survive voxelization better.",
            key="ks_constraint_max_segments",
        )
        max_moving = budget_c.number_input(
            "Max moving parts",
            min_value=0,
            max_value=4,
            step=1,
            key="ks_constraint_max_moving",
        )
        optional = st.text_input(
            "Optional decorative features",
            key="ks_constraint_optional",
        )
        bang = st.text_area(
            "Bang segmentation requirements",
            height=90,
            key="ks_constraint_bang",
        )
    return {
        "object_type_hint": object_type,
        "required_visible_parts": split_list(required),
        "moving_parts": split_list(moving),
        "wheel_count": int(wheel_count),
        "symmetry": symmetry,
        "inventory_mode": inventory_mode,
        "max_validated_blocks": int(max_blocks),
        "max_semantic_segments": int(max_segments),
        "max_moving_parts": int(max_moving),
        "min_segment_survival_fraction": float(constraints.get("min_segment_survival_fraction") or 0.75),
        "minimum_surviving_segments": int(constraints.get("minimum_surviving_segments") or 2),
        "optional_decorative_features": split_list(optional),
        "bang_segmentation_requirements": [line.strip() for line in bang.splitlines() if line.strip()],
    }


def split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def render_wait(job: dict[str, Any], title: str) -> None:
    st.markdown(
        f"""
        <div class="ks-wait">
            <div class="ks-wait-title">{title}</div>
            <div class="ks-subtle">{job.get('message', 'Working through the build stage...')}</div>
            <div class="ks-wait-bar"><span></span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_job_status(job: dict[str, Any], title: str) -> None:
    st.markdown(f"#### {title}")
    progress = int(job.get("progress", 0))
    st.progress(progress / 100)
    cols = st.columns([1, 2])
    cols[0].metric("Progress", f"{progress}%")
    cols[1].info(f"**{job.get('stage', 'Queued')}** - {job.get('message', 'Waiting for updates.')}")
    if job.get("events"):
        rows = list(reversed(job["events"][-5:]))
        st.dataframe(rows, use_container_width=True, hide_index=True)
    if job.get("status") in ("queued", "running"):
        render_wait(job, "KidSpark is building")


def render_step_4_break_notice(job: dict[str, Any]) -> None:
    if job.get("status") not in ("queued", "running"):
        return
    st.markdown(
        f"""
        <div class="ks-break-card">
            <div class="ks-break-title"><span class="ks-steam">coffee</span>Good moment for a tiny teacher break</div>
            <div>Bang and the notebook physicalization can take a few minutes. KidSpark is still tracking the build, so you can stretch, refill coffee, or peek back in while the segments take shape.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_auto_model_recovery_status(result: dict[str, Any]) -> None:
    recovery = result.get("auto_model_recovery") or {}
    attempts = recovery.get("attempts") if isinstance(recovery.get("attempts"), list) else []
    if not attempts:
        return
    if recovery.get("enabled"):
        selected = int(recovery.get("selected_attempt") or 0)
        selected_attempt = next((attempt for attempt in attempts if int(attempt.get("attempt", -1)) == selected), attempts[-1])
        recovery_count = max(len(attempts) - 1, 0)
        if selected_attempt.get("final_claim_valid"):
            st.success(
                f"KidSpark automatically simplified the model {recovery_count} time(s) "
                "and found a validated standard-kit build."
            )
        else:
            st.warning(
                f"KidSpark already tried {recovery_count} automatic simplification pass(es). "
                "This is now a real model-design exception that needs a revised preview."
            )
        with st.expander("Automatic validation attempts", expanded=False):
            st.dataframe(attempts, use_container_width=True, hide_index=True)


def poll_job(endpoint: str, state_key: str, delay: int = 8) -> dict[str, Any] | None:
    job = st.session_state.get(state_key)
    if not job:
        return None
    return job


def refresh_running_job(endpoint: str, state_key: str, delay: int = 8) -> None:
    job = st.session_state.get(state_key)
    if job and job.get("status") in ("queued", "running"):
        time.sleep(delay)
        st.session_state[state_key] = api("get", endpoint)
        st.rerun()


def format_value(value: Any) -> str:
    if value is None or value == "" or value == []:
        return "<span class='ks-empty'>Waiting for teacher input</span>"
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return "<br>".join(
                f"{item.get('part_name', item.get('name', 'part'))}: {item.get('movement', item.get('notes', ''))}"
                for item in value
            )
        return "<br>".join(str(item) for item in value)
    return str(value)


COMPONENT_FIELDS = [
    ("target_grade", "Target grade"),
    ("duration_minutes", "Duration"),
    ("core_concept", "Core concept"),
    ("learning_goals", "Learning goals"),
    ("build_object", "Build object"),
    ("moving_parts", "Moving parts"),
    ("static_parts", "Static parts"),
    ("literacy_focus", "Literacy"),
    ("sel_focus", "SEL"),
    ("constraints", "Constraints"),
]


def field_complete(value: Any) -> bool:
    if value is None or value == "" or value == []:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(field_complete(item) for item in value)
    if isinstance(value, dict):
        return any(field_complete(item) for item in value.values())
    return True


def planning_components_complete(state: dict[str, Any]) -> bool:
    return all(field_complete(state.get(key)) for key, _ in COMPONENT_FIELDS)


def missing_component_labels(state: dict[str, Any]) -> list[str]:
    return [label for key, label in COMPONENT_FIELDS if not field_complete(state.get(key))]


def emphasize_planning_cues(text: str) -> str:
    cues = [
        "target grade",
        "grade",
        "duration",
        "timing",
        "core concept",
        "theme",
        "learning goals",
        "learning objectives",
        "build artifact",
        "build object",
        "moving parts",
        "static parts",
        "literacy focus",
        "vocabulary",
        "SEL focus",
        "constraints",
    ]
    highlighted = text
    for cue in sorted(cues, key=len, reverse=True):
        highlighted = re.sub(
            rf"(?<![\w*])({re.escape(cue)})(?![\w*])",
            r"<span class='ks-question-cue'>\1</span>",
            highlighted,
            flags=re.IGNORECASE,
        )
    return highlighted


CHECKLIST_ADDENDUM_RE = re.compile(
    r"\n*\*{0,2}Before we move on, I still need to complete the checklist:\*{0,2}.*?(?:Could you share those details\?|$)",
    flags=re.IGNORECASE | re.DOTALL,
)


def strip_checklist_addendum(content: str) -> str:
    return CHECKLIST_ADDENDUM_RE.sub("", content).rstrip()


def render_chat_message(role: str, content: str, *, show_checklist_addendum: bool = True) -> None:
    display_content = content if show_checklist_addendum else strip_checklist_addendum(content)
    with st.chat_message(role):
        if role == "assistant":
            st.markdown(emphasize_planning_cues(display_content), unsafe_allow_html=True)
        else:
            st.markdown(display_content)


def render_component_panel(state: dict[str, Any]) -> None:
    st.markdown("#### Lesson Components")
    st.markdown("<div class='ks-panel'>", unsafe_allow_html=True)
    for key, label in COMPONENT_FIELDS:
        done = field_complete(state.get(key))
        icon = "<span class='ks-check'>&#10003;</span>" if done else "<span class='ks-pending'>-</span>"
        st.markdown(
            f"<div class='ks-component-row'><div>{icon}</div><div class='ks-label'>{label}</div><div class='ks-value'>{format_value(state.get(key))}</div></div>",
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)
    if state.get("framework_matches"):
        st.markdown("#### Framework Anchors")
        for item in state["framework_matches"]:
            st.markdown(f"<span class='ks-check'>&#10003;</span>{item}", unsafe_allow_html=True)


def create_session_from_story(story_text: str, uploaded_file: Any | None) -> None:
    session = api("post", "/api/v1/sessions")
    session_id = session["session_id"]
    if uploaded_file is not None:
        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type or "application/pdf")}
        upload = api("post", f"/api/v1/sessions/{session_id}/upload", files=files)
    else:
        upload = api("post", f"/api/v1/sessions/{session_id}/upload", data={"text": story_text})
    analysis = upload["story_analysis"]
    st.session_state["ks_session_id"] = session_id
    set_phase(upload["phase"])
    st.session_state["ks_story_analysis"] = analysis
    st.session_state["ks_messages"] = [
        {
            "role": "assistant",
            "content": (
                f"I read **{analysis.get('title', 'the story')}** and found a few promising build ideas: "
                f"{', '.join(analysis.get('buildable_objects', []))}.\n\n"
                "Let's shape this into a classroom-ready lesson. Tell me the grade, timing, "
                "what story theme you want students to notice, and what object you want them to build."
            ),
        }
    ]
    st.session_state["ks_planning_state"] = {}


def render_header() -> None:
    st.markdown("<div class='ks-shell-title'>KidSpark AI</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='ks-subtle'>A guided teacher workflow for turning a story into a BrickSmart build, lesson plan, activity guide, and slide companion.</div>",
        unsafe_allow_html=True,
    )
    st.divider()


def render_step_1() -> None:
    st.subheader("Step 1 - Upload Storybook")
    left, right = st.columns([1.1, 1])
    with left:
        st.markdown("<div class='ks-hero-upload'>Drop in a story PDF or paste your own text below</div>", unsafe_allow_html=True)
        uploaded_file = st.file_uploader("Upload story PDF or text", type=["pdf", "txt", "md"], label_visibility="collapsed")
        story_text = st.text_area("Or type/paste the story", value=SAMPLE_STORY, height=260)
        disabled = uploaded_file is None and len(story_text.strip()) < 50
        if st.button("Confirm & Next Step", type="primary", disabled=disabled, use_container_width=True):
            with st.spinner("Analyzing story, matching framework anchors, and finding buildable ideas..."):
                create_session_from_story(story_text, uploaded_file)
            st.rerun()
    with right:
        st.markdown("#### What KidSpark looks for")
        st.markdown(
            """
            - Story theme and SEL opportunities
            - Vocabulary and sound-awareness moments
            - Buildable objects from the plot
            - Standards/framework anchors
            - Early hints for moving or static parts
            """
        )


def render_analysis_preview() -> None:
    analysis = st.session_state.get("ks_story_analysis")
    if not analysis:
        return
    with st.container(border=True):
        st.markdown("#### Story Analysis Preview")
        cols = st.columns(4)
        cols[0].markdown(f"**Title**<br>{analysis.get('title', '')}", unsafe_allow_html=True)
        cols[1].markdown("**Themes**<br>" + "<br>".join(analysis.get("themes", [])[:4]), unsafe_allow_html=True)
        cols[2].markdown("**Build Ideas**<br>" + "<br>".join(analysis.get("buildable_objects", [])[:4]), unsafe_allow_html=True)
        cols[3].markdown("**Vocabulary**<br>" + "<br>".join(analysis.get("vocabulary_opportunities", [])[:4]), unsafe_allow_html=True)


def render_step_2() -> None:
    st.subheader("Step 2 - Plan With KidSpark Coach")
    render_analysis_preview()
    state = st.session_state.get("ks_planning_state", {})
    ready = planning_components_complete(state)
    messages = st.session_state.get("ks_messages", [])
    latest_assistant_index = next(
        (idx for idx in range(len(messages) - 1, -1, -1) if messages[idx].get("role") == "assistant"),
        -1,
    )
    chat_col, panel_col = st.columns([1.55, 1])
    with chat_col:
        st.markdown("#### Teacher Conversation")
        for idx, msg in enumerate(messages):
            show_checklist = not ready and idx == latest_assistant_index
            render_chat_message(msg["role"], msg["content"], show_checklist_addendum=show_checklist)
        if st.button("Use Suggested Teacher Direction", use_container_width=True):
            st.session_state["ks_messages"].append({"role": "user", "content": SUGGESTED_TEACHER_DIRECTION})
            with st.spinner("KidSpark is turning the suggested direction into lesson components..."):
                data = api(
                    "post",
                    f"/api/v1/sessions/{st.session_state['ks_session_id']}/message",
                    json={"message": SUGGESTED_TEACHER_DIRECTION},
                )
            st.session_state["ks_messages"].append({"role": "assistant", "content": data["response"]})
            set_phase(data.get("phase", "lesson_planning"))
            st.session_state["ks_planning_state"] = data.get("planning_state", {})
            st.session_state["ks_ready_to_confirm_planning"] = data.get("ready_to_approve", False)
            st.rerun()
        with st.form("ks_chat_form", clear_on_submit=True):
            message = st.text_area(
                "Message KidSpark",
                placeholder="Example: I teach 1st grade for 40 minutes. Let's focus on perseverance and build a plane. The propeller should spin; the body and wings stay static.",
                height=95,
            )
            sent = st.form_submit_button("Send", type="primary", use_container_width=True)
        if sent and message.strip():
            st.session_state["ks_messages"].append({"role": "user", "content": message.strip()})
            with st.spinner("KidSpark is updating the lesson components..."):
                data = api(
                    "post",
                    f"/api/v1/sessions/{st.session_state['ks_session_id']}/message",
                    json={"message": message.strip()},
                )
            st.session_state["ks_messages"].append({"role": "assistant", "content": data["response"]})
            set_phase(data.get("phase", "lesson_planning"))
            st.session_state["ks_planning_state"] = data.get("planning_state", {})
            st.session_state["ks_ready_to_confirm_planning"] = data.get("ready_to_approve", False)
            st.rerun()
    with panel_col:
        st.markdown("<span id='ks-lesson-components-sticky'></span>", unsafe_allow_html=True)
        render_component_panel(state)
        missing = missing_component_labels(state)
        if ready:
            st.markdown("<div class='ks-ready-note'>All lesson components are checked. Ready for the model preview.</div>", unsafe_allow_html=True)
        else:
            st.markdown(
                "<div class='ks-blocked-note'>KidSpark will unlock the next step once these are complete: "
                + ", ".join(missing)
                + ".</div>",
                unsafe_allow_html=True,
            )
        if st.button("Confirm & Next Step", type="primary", disabled=not ready, use_container_width=True):
            with st.spinner("Finalizing the teacher-approved planning state..."):
                data = api("post", f"/api/v1/sessions/{st.session_state['ks_session_id']}/confirm-planning")
            set_phase(data["phase"])
            st.session_state["ks_planning_state"] = data.get("planning_state", {})
            st.session_state["ks_model_context"] = data.get("model_task_context", {})
            st.rerun()


def render_step_3() -> None:
    st.subheader("Step 3 - Review Model Preview")
    context = st.session_state.get("ks_model_context", {})
    if not context:
        data = api("post", f"/api/v1/sessions/{st.session_state['ks_session_id']}/confirm-planning")
        st.session_state["ks_planning_state"] = data.get("planning_state", {})
        st.session_state["ks_model_context"] = data.get("model_task_context", {})
        context = st.session_state.get("ks_model_context", {})
        if not context:
            st.info("Confirm the planning conversation first.")
            return
    recommendation = apply_stage4_recommendation_to_step3(context)
    if recommendation:
        context = st.session_state.get("ks_model_context", context)
        st.warning("Loaded simplification recommendations from the segment review. Regenerate a simpler model before continuing.")
        for reason in recommendation.get("reasons", []):
            st.markdown(f"- {reason}")
    st.markdown("KidSpark sends this teacher-approved prompt to Rodin. Regenerate until the model looks right before segmentation.")
    if "ks_rodin_prompt" not in st.session_state:
        st.session_state["ks_rodin_prompt"] = context.get("rodin_prompt", "")
    prompt = st.text_area("Rodin visual prompt", height=160, key="ks_rodin_prompt")
    build_constraints = render_build_constraints_editor(context)
    if st.button("Generate / Regenerate Model Preview", type="primary", use_container_width=True):
        clear_downstream_generation_state()
        context["build_constraints"] = build_constraints
        context["rodin_prompt"] = prompt
        st.session_state["ks_model_context"] = context
        body = {"rodin_prompt": prompt, "refinement": "", "build_constraints": build_constraints}
        job = api("post", f"/api/v1/sessions/{st.session_state['ks_session_id']}/model-preview/refine", json=body)
        st.session_state["ks_model_job"] = job
        st.session_state.pop("ks_stage4_recommendation", None)
        st.session_state.pop("ks_stage4_recommendation_applied", None)
        st.rerun()
    job = poll_job(f"/api/v1/sessions/{st.session_state['ks_session_id']}/model-preview", "ks_model_job")
    if job:
        render_job_status(job, "Rodin Preview Progress")
        refresh_running_job(f"/api/v1/sessions/{st.session_state['ks_session_id']}/model-preview", "ks_model_job")
        if job.get("status") == "error":
            st.error(job.get("message", "Rodin preview failed."))
            st.code(job.get("error", ""))
        if job.get("status") == "complete":
            result = job.get("result", {})
            st.session_state["ks_model_result"] = result
            preview = image_from_files(result.get("rodin", {}).get("files", []))
            with st.container(border=True):
                left, right = st.columns([1.2, 1])
                with left:
                    if preview:
                        st.image(str(preview), caption="Rodin model preview", use_column_width=True)
                    else:
                        st.info("Rodin returned model files but no preview image. The generated model will still be used for segmentation.")
                with right:
                    st.markdown("#### Model Details")
                    st.write(f"Rodin task: `{result.get('rodin', {}).get('task_uuid')}`")
                    st.write("Moving parts are intentionally described as visually separate so Bang can segment them.")
                    if st.button("Confirm & Next Step", type="primary", use_container_width=True):
                        clear_downstream_generation_state()
                        data = api("post", f"/api/v1/sessions/{st.session_state['ks_session_id']}/confirm-model")
                        set_phase(data["phase"])
                        st.rerun()


def render_segments_tables(build_plan: dict[str, Any]) -> None:
    segments = build_plan.get("segments", [])
    interfaces = build_plan.get("interfaces", [])
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("#### Segment Labels")
        edited = st.data_editor(segments, key="ks_segment_editor", use_container_width=True, hide_index=True)
        if st.button("Save Segment Label Notes", use_container_width=True):
            rows = edited.to_dict("records") if hasattr(edited, "to_dict") else edited
            api("post", f"/api/v1/sessions/{st.session_state['ks_session_id']}/segments/refine", json={"updates": {"segments": rows}})
            st.success("Segment notes saved for this session.")
    with col_b:
        st.markdown("#### Connector / Interface Table")
        edited = st.data_editor(interfaces, key="ks_interface_editor", use_container_width=True, hide_index=True)
        if st.button("Save Connector Notes", use_container_width=True):
            rows = edited.to_dict("records") if hasattr(edited, "to_dict") else edited
            api("post", f"/api/v1/sessions/{st.session_state['ks_session_id']}/segments/refine", json={"updates": {"interfaces": rows}})
            st.success("Connector notes saved for this session.")


def render_step_4() -> None:
    st.subheader("Step 4 - Segments & Connectors")
    st.markdown("Review the notebook voxelization, color-coded segments, movement mapping, and connector candidates before moving into build instructions.")
    if "ks_segment_job" not in st.session_state:
        if st.button("Run Bang Segmentation And Notebook Voxelization", type="primary", use_container_width=True):
            st.session_state["ks_segment_job"] = api("post", f"/api/v1/sessions/{st.session_state['ks_session_id']}/segments")
            st.rerun()
        return
    job = poll_job(f"/api/v1/sessions/{st.session_state['ks_session_id']}/segments", "ks_segment_job")
    if not job:
        return
    render_step_4_break_notice(job)
    render_job_status(job, "Segmentation And Notebook Progress")
    refresh_running_job(f"/api/v1/sessions/{st.session_state['ks_session_id']}/segments", "ks_segment_job")
    if job.get("status") == "error":
        st.error(job.get("message", "Segmentation failed."))
        st.code(job.get("error", ""))
        if st.button("Back To Model Preview", use_container_width=True):
            set_phase("model_preview")
            st.rerun()
        return
    if job.get("status") != "complete":
        return
    result = job.get("result", {})
    st.session_state["ks_segment_result"] = result
    build_plan = result.get("build_plan", {})
    render_auto_model_recovery_status(result)
    notebook = build_plan.get("notebook_outputs", {})
    validated = normalized_validated_planner(
        build_plan.get("validated_planner", {}) or notebook.get("validated_planner", {}),
        notebook,
    )
    if validated:
        status = validated.get("build_status", "unknown")
        if status == "NOTEBOOK_CSP_REVIEW_READY":
            st.success("Notebook/CSP classroom build is ready for teacher review.")
            if validated.get("reason"):
                st.info(validated["reason"])
        elif validated.get("final_claim_valid"):
            st.success(f"Validated planner status: {status}")
        elif status == "NEEDS_SIMPLER_MODEL":
            st.warning("This model needs to be simplified before KidSpark can produce validated standard-kit instructions.")
            if validated.get("reason"):
                st.info(validated["reason"])
            if validated.get("segment_viability"):
                st.dataframe([validated["segment_viability"]], use_container_width=True, hide_index=True)
            if validated.get("recommendation"):
                st.caption(validated["recommendation"])
        elif status == "INFEASIBLE_INVENTORY":
            st.warning("Validated planner found that this model needs more pieces than the selected kit provides.")
            if validated.get("shortages"):
                st.dataframe(
                    [
                        {"piece": key, **value} if isinstance(value, dict) else {"piece": key, "shortage": value}
                        for key, value in validated.get("shortages", {}).items()
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
        else:
            st.warning(f"Validated planner status: {status}")
    metrics = st.columns(4)
    metrics[0].metric("Voxel size", notebook.get("voxel_size", "unknown"))
    metrics[1].metric("Segments", notebook.get("segment_count", 0))
    notebook_blocks = notebook.get("blocks") if isinstance(notebook.get("blocks"), list) else []
    block_count = int(notebook.get("block_count") or len(notebook_blocks) or validated.get("final_block_count", 0) or 0)
    metrics[2].metric("Blocks", block_count)
    metrics[3].metric("Validated steps", validated.get("true_build_step_count", len(notebook.get("instruction_steps", []))))
    img_cols = st.columns(3)
    for col, label, key in [
        (img_cols[0], "Voxelized segments", "segment_visualization_image"),
        (img_cols[1], "Notebook multiview", "segment_multiview_image"),
        (img_cols[2], "Final block reference", "final_image"),
    ]:
        image = existing_file(notebook.get(key))
        with col:
            st.markdown(f"#### {label}")
            if image:
                st.image(str(image), use_column_width=True)
            else:
                st.info("Image not available.")
    can_confirm_segments = not validated or bool(validated.get("final_claim_valid"))
    if validated and not validated.get("final_claim_valid"):
        recommendation = stage4_simplification_recommendation(
            validated,
            notebook,
            result.get("context") or st.session_state.get("ks_model_context", {}),
        )
        st.markdown("#### Recommended Recovery")
        st.warning(recommendation["summary"])
        st.markdown("KidSpark recommends changing the next model preview like this:")
        for reason in recommendation.get("reasons", []):
            st.markdown(f"- {reason}")
        with st.container(border=True):
            st.markdown("##### Suggested Rodin prompt update")
            st.write(recommendation["rodin_prompt"])
            suggested_constraints = recommendation.get("build_constraints", {})
            st.markdown("##### Suggested build constraints")
            st.write(
                f"Required parts: {', '.join(suggested_constraints.get('required_visible_parts', []))} | "
                f"Blocks: {suggested_constraints.get('max_validated_blocks')} max | "
                f"Semantic parts: {suggested_constraints.get('max_semantic_segments')} max"
            )
        st.caption("This will prefill the Rodin prompt and BrickSmart Build Constraints fields on the model preview screen.")
        if st.button("Revise Model Preview With These Recommendations", type="primary", use_container_width=True):
            st.session_state["ks_stage4_recommendation"] = recommendation
            st.session_state.pop("ks_stage4_recommendation_applied", None)
            set_phase("model_preview")
            st.rerun()

    if notebook.get("connector_candidates"):
        st.markdown("#### Moving Parts To Connector Candidates")
        st.dataframe(notebook["connector_candidates"], use_container_width=True, hide_index=True)
    render_segments_tables(build_plan)
    refinement = st.text_area("Segment or connector refinement notes", placeholder="Example: propeller should be the spinning segment attached to the front nose.", height=100)
    if not can_confirm_segments:
        if st.button("Save Refinement Notes", use_container_width=True, disabled=not refinement.strip()):
            api("post", f"/api/v1/sessions/{st.session_state['ks_session_id']}/segments/refine", json={"refinement": refinement})
            st.success("Refinement notes saved.")
        return
    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button("Save Refinement Notes", use_container_width=True, disabled=not refinement.strip()):
            api("post", f"/api/v1/sessions/{st.session_state['ks_session_id']}/segments/refine", json={"refinement": refinement})
            st.success("Refinement notes saved.")
    with col_b:
        if st.button("Confirm & Next Step", type="primary", use_container_width=True):
            data = api("post", f"/api/v1/sessions/{st.session_state['ks_session_id']}/confirm-segments")
            set_phase(data["phase"])
            st.rerun()


def render_notebook_build_plan(build_plan: dict[str, Any]) -> bool:
    notebook = build_plan.get("notebook_outputs", {})
    validated = normalized_validated_planner(
        build_plan.get("validated_planner", {}) or notebook.get("validated_planner", {}),
        notebook,
    )
    if validated:
        status = validated.get("build_status", "unknown")
        if validated.get("final_claim_valid"):
            st.success(f"Validated build passed: {status}")
            html_path = existing_file(validated.get("build_instructions_html"))
            if html_path:
                st.markdown(f"Validated HTML instructions: `{html_path}`")
        elif status == "NEEDS_SIMPLER_MODEL":
            st.error("This model is too detailed or unstable for validated standard-kit instructions.")
            if validated.get("reason"):
                st.info(validated["reason"])
            if validated.get("segment_viability"):
                st.dataframe([validated["segment_viability"]], use_container_width=True, hide_index=True)
            st.info(validated.get("recommendation", "Regenerate a simpler model or switch to an unlimited reference preview."))
            return False
        elif status == "INFEASIBLE_INVENTORY":
            st.error("This model cannot be built with the selected physical kit inventory.")
            shortages = validated.get("shortages", {})
            if shortages:
                st.dataframe(
                    [
                        {"piece": key, **value} if isinstance(value, dict) else {"piece": key, "shortage": value}
                        for key, value in shortages.items()
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            st.info("Simplify/regenerate the model or run an explicitly labeled unlimited reference preview.")
            return False
        else:
            st.error(f"Validated planner did not produce an approvable build: {status}")
            if validated.get("reason"):
                st.code(str(validated["reason"]))
            return False
    steps = notebook.get("instruction_steps", [])
    final_image = existing_file(notebook.get("final_image"))
    if final_image:
        st.image(str(final_image), caption="Final BrickSmart build target", use_column_width=True)
    if notebook.get("block_inventory"):
        st.markdown("#### Inventory")
        st.dataframe(notebook["block_inventory"], use_container_width=True, hide_index=True)
    if not steps:
        st.warning("No notebook build steps were generated.")
        return False
    st.markdown("#### Step-by-step build guide")
    cols = st.columns([1, 1, 2])
    with cols[0]:
        if st.button("Approve All Steps", use_container_width=True):
            for step in steps:
                st.session_state[f"approve_step_{step.get('step_number')}"] = True
            st.rerun()
    with cols[1]:
        st.checkbox("Show all multiview sheets", key="show_all_multiviews")
    approvals = []
    for step in steps:
        number = step.get("step_number")
        with st.container(border=True):
            left, right = st.columns([1.15, 1])
            with left:
                st.markdown(f"### Step {number}: {step.get('title', 'Build next section')}")
                st.write(f"**Teacher:** {step.get('teacher_instruction', '')}")
                st.write(f"**Student:** {step.get('student_instruction', '')}")
                if step.get("segment_labels"):
                    st.caption("Segments: " + ", ".join(step.get("segment_labels", [])))
                if step.get("inventory"):
                    st.dataframe(step["inventory"], use_container_width=True, hide_index=True)
                approvals.append(st.checkbox("Teacher approves this build step", key=f"approve_step_{number}"))
            with right:
                image = existing_file(step.get("image_path"))
                multiview = existing_file(step.get("multiview_path"))
                if image:
                    st.image(str(image), caption=f"Step {number}", use_column_width=True)
                if multiview and st.session_state.get("show_all_multiviews", False):
                    st.image(str(multiview), caption=f"Step {number} placement views", use_column_width=True)
    return bool(approvals and all(approvals))


def render_step_5() -> None:
    st.subheader("Step 5 - Build Plan")
    result = st.session_state.get("ks_segment_result")
    if not result:
        job = api("get", f"/api/v1/sessions/{st.session_state['ks_session_id']}/segments")
        result = job.get("result") if job.get("status") == "complete" else None
    if not result:
        st.info("Confirm segments and connectors first.")
        return
    complete = render_notebook_build_plan(result.get("build_plan", {}))
    st.info("This build plan uses the actual notebook/CSP output. Placeholder demo step art is not used in this flow.")
    if st.button("Confirm & Next Step", type="primary", disabled=not complete, use_container_width=True):
        data = api("post", f"/api/v1/sessions/{st.session_state['ks_session_id']}/confirm-build-plan")
        set_phase(data["phase"])
        st.rerun()


def render_document_preview(kind: str, doc: dict[str, Any]) -> None:
    md_path = existing_file(doc.get("markdown_path"))
    if md_path:
        render_markdown_with_images(md_path.read_text(encoding="utf-8"))
    else:
        st.warning("Markdown preview was not found.")
    pdf_bytes = api_bytes(f"/api/v1/sessions/{st.session_state['ks_session_id']}/documents/{kind}/download")
    if pdf_bytes:
        render_pdf_downloads(kind, doc.get("title", kind), pdf_bytes)
    else:
        st.error("PDF download is not ready. Try refreshing this step; if it persists, regenerate the lesson bundle.")


def render_markdown_with_images(markdown_text: str) -> None:
    pending: list[str] = []
    for raw_line in markdown_text.splitlines():
        image_info = image_line(raw_line)
        if not image_info:
            pending.append(raw_line)
            continue
        if pending:
            st.markdown("\n".join(pending))
            pending = []
        st.caption(image_info["label"])
        st.image(str(image_info["path"]), use_column_width=True)
    if pending:
        st.markdown("\n".join(pending))


def image_line(line: str) -> dict[str, Any] | None:
    prefixes = [
        ("Final built reference image:", "Final built reference"),
        ("Image:", "Build step image"),
        ("Placement views:", "Placement views"),
    ]
    stripped = line.strip()
    for prefix, label in prefixes:
        if not stripped.startswith(prefix):
            continue
        path = existing_file(stripped[len(prefix):].strip())
        if path and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            return {"label": label, "path": path}
    return None


def render_step_6(*, review_only: bool = False) -> None:
    st.subheader("Step 6 - Lesson Bundle")
    st.markdown("Review the three classroom documents before downloading: teacher lesson plan, student activity guide, and slide companion.")
    if "ks_document_job" not in st.session_state:
        if st.button("Generate Lesson Bundle", type="primary", use_container_width=True):
            st.session_state["ks_document_job"] = api("post", f"/api/v1/sessions/{st.session_state['ks_session_id']}/documents")
            st.rerun()
        return
    job = poll_job(f"/api/v1/sessions/{st.session_state['ks_session_id']}/documents", "ks_document_job", delay=5)
    if not job:
        return
    render_job_status(job, "Lesson Bundle Progress")
    refresh_running_job(f"/api/v1/sessions/{st.session_state['ks_session_id']}/documents", "ks_document_job", delay=5)
    if job.get("status") == "error":
        st.error(job.get("message", "Document generation failed."))
        st.code(job.get("error", ""))
        return
    if job.get("status") != "complete":
        return
    result = job.get("result", {})
    bundle = result.get("document_bundle", {})
    validation = bundle.get("validation", {})
    st.markdown("#### Validation")
    cols = st.columns(3)
    for idx, kind in enumerate(["lesson_plan", "activity_guide", "slide_companion"]):
        item = validation.get(kind, {})
        with cols[idx]:
            if item.get("is_valid"):
                st.success(kind.replace("_", " ").title())
            else:
                st.warning(f"{kind.replace('_', ' ').title()}: {', '.join(item.get('missing', []))}")
    documents = bundle.get("documents", {})
    tabs = st.tabs(["Lesson Plan", "Activity Guide", "Slide Companion", "Full JSON"])
    for tab, kind in zip(tabs[:3], ["lesson_plan", "activity_guide", "slide_companion"]):
        with tab:
            refinement = st.text_area(f"Refinement notes for {kind.replace('_', ' ')}", key=f"refine_{kind}", height=80)
            if st.button(f"Save {kind.replace('_', ' ').title()} Notes", key=f"save_{kind}", disabled=not refinement.strip()):
                api("post", f"/api/v1/sessions/{st.session_state['ks_session_id']}/documents/{kind}/refine", json={"refinement": refinement})
                st.success("Notes saved.")
            render_document_preview(kind, documents.get(kind, {}))
    with tabs[3]:
        st.download_button(
            "Download Full Result JSON",
            json.dumps(result, indent=2),
            file_name="kidspark_lesson_bundle.json",
            mime="application/json",
            use_container_width=True,
        )
        st.json(result)
    if bundle.get("all_valid"):
        st.success("All three documents are validated and ready for classroom use.")
        if not review_only and st.button("Confirm Ready For Class", type="primary", use_container_width=True):
            data = api("post", f"/api/v1/sessions/{st.session_state['ks_session_id']}/confirm-documents")
            set_phase(data.get("phase", "complete"))
            st.rerun()


def render_active_step() -> None:
    phase = current_phase()
    if phase == "story_upload":
        render_step_1()
    elif phase == "lesson_planning":
        render_step_2()
    elif phase == "model_preview":
        render_step_3()
    elif phase == "segments_connectors":
        render_step_4()
    elif phase == "build_plan":
        render_step_5()
    elif phase == "lesson_bundle":
        render_step_6()
    elif phase == "complete":
        reviewing_bundle = bool(st.session_state.get("ks_review_completed_bundle"))
        if reviewing_bundle:
            if st.button("Back To Ready For Class Summary", use_container_width=True):
                st.session_state["ks_review_completed_bundle"] = False
                st.rerun()
            render_step_6(review_only=True)
        else:
            st.success("This KidSpark lesson is ready for class. The lesson plan, activity guide, and slide companion are ready to review and download.")
            if st.button("Review And Download Lesson Bundle", type="primary", use_container_width=True):
                st.session_state["ks_review_completed_bundle"] = True
                st.rerun()


hydrate_session_from_query()
render_sidebar()
render_header()
render_active_step()
