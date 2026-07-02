"""KidSpark end-to-end local demo.

This page runs the local pipeline from story text to Rodin/Bang-backed
BrickSmart outputs, then gives the teacher explicit review checkpoints before
they use or download the final report.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import requests
import streamlit as st
from streamlit.errors import StreamlitAPIException

BACKEND_URL = "http://localhost:8001"
WORK_BUILD_JOBS = Path(__file__).resolve().parents[1] / "work" / "build_jobs"

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

PIPELINE_STEPS = [
    ("Story", 5, "Story analyzed and model task context created"),
    ("Lesson", 15, "Teacher plan and student guide drafted"),
    ("Rodin", 25, "Text-to-3D generation submitted"),
    ("Rodin asset", 56, "Generated 3D model downloaded"),
    ("Bang", 60, "Segmentation submitted"),
    ("Segments", 83, "Segmented asset downloaded"),
    ("Build guide", 88, "BrickSmart tables and build steps generated"),
    ("Complete", 100, "Final teacher manual ready"),
]

REVIEW_KEYS = [
    "lesson_target",
    "standards_anchor",
    "rodin_asset",
    "segments",
    "connections",
    "build_steps",
    "notebook_output",
    "final_report",
]


st.set_page_config(page_title="KidSpark E2E Demo", page_icon=":bricks:", layout="wide")

st.markdown(
    """
    <style>
    div[data-testid="stTabs"] button p {
        font-weight: 800;
        font-size: 1.02rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def api(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    try:
        resp = getattr(requests, method)(f"{BACKEND_URL}{path}", timeout=30, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except requests.ConnectionError:
        st.error("Cannot reach the KidSpark backend at http://localhost:8000.")
        st.stop()
    except requests.HTTPError as exc:
        st.error(exc.response.text)
        st.stop()


def load_job(job_id: str) -> dict[str, Any]:
    try:
        resp = requests.get(f"{BACKEND_URL}/api/v1/build-demo/jobs/{job_id}", timeout=30)
        if resp.ok:
            return resp.json()
        result_path = WORK_BUILD_JOBS / job_id / "result.json"
        if not result_path.exists():
            resp.raise_for_status()
        result = json.loads(result_path.read_text(encoding="utf-8"))
        return {
            "job_id": job_id,
            "status": "complete",
            "stage": "Complete",
            "progress": 100,
            "message": "Loaded completed report from disk",
            "job_dir": str(result_path.parent),
            "events": [],
            "result": result,
            "error": None,
        }
    except requests.ConnectionError:
        result_path = WORK_BUILD_JOBS / job_id / "result.json"
        if not result_path.exists():
            st.error("Cannot reach the KidSpark backend at http://localhost:8000.")
            st.stop()
        result = json.loads(result_path.read_text(encoding="utf-8"))
        return {
            "job_id": job_id,
            "status": "complete",
            "stage": "Complete",
            "progress": 100,
            "message": "Loaded completed report from disk",
            "job_dir": str(result_path.parent),
            "events": [],
            "result": result,
            "error": None,
        }


def reset_demo() -> None:
    exact_keys = [
        "ks_demo_job_id",
        "ks_demo_last_job",
        "ks_demo_review",
        "ks_demo_segments",
        "ks_demo_interfaces",
        "ks_demo_notes",
        "ks_demo_connection_intent",
        "ks_demo_connection_review_notes",
        "ks_demo_notebook_notes",
        "ks_demo_final_notes",
    ]
    prefixes = ["review_", "approve_step_", "approve_notebook_step_", "segments_editor", "interfaces_editor"]
    for key in exact_keys:
        st.session_state.pop(key, None)
    for key in list(st.session_state.keys()):
        if any(key.startswith(prefix) for prefix in prefixes):
            st.session_state.pop(key, None)


def ensure_review_state() -> dict[str, bool]:
    review = st.session_state.setdefault(
        "ks_demo_review",
        {key: False for key in REVIEW_KEYS},
    )
    for key in REVIEW_KEYS:
        review.setdefault(key, False)
    return review


def approve_checkbox(key: str, label: str, help_text: str | None = None) -> bool:
    review = ensure_review_state()
    value = st.checkbox(label, value=review[key], key=f"review_{key}", help=help_text)
    review[key] = value
    return value


def sidebar_page_link(page: str, label: str) -> None:
    try:
        st.page_link(page, label=label, use_container_width=True)
    except StreamlitAPIException:
        st.caption(label)


def event_has_reached(job: dict[str, Any], percent: int) -> bool:
    if job.get("progress", 0) >= percent:
        return True
    return any(event.get("progress", 0) >= percent for event in job.get("events", []))


def render_pipeline_status(job: dict[str, Any]) -> None:
    st.subheader("Pipeline Status")
    progress = job.get("progress", 0)
    st.progress(progress / 100)

    state_col, detail_col = st.columns([1, 2])
    with state_col:
        st.metric("Current progress", f"{progress}%")
        st.write(f"**Stage:** {job.get('stage', 'Queued')}")
    with detail_col:
        st.info(job.get("message", "Waiting for pipeline update."))

    cols = st.columns(4)
    for idx, (stage, percent, description) in enumerate(PIPELINE_STEPS):
        with cols[idx % 4]:
            if event_has_reached(job, percent):
                st.success(stage)
            elif progress >= percent - 10:
                st.warning(stage)
            else:
                st.caption(stage)
            st.caption(description)

    with st.expander("Recent backend events", expanded=False):
        for event in job.get("events", [])[-14:]:
            st.write(f"{event.get('progress', 0):>3}% - {event.get('stage')}: {event.get('message')}")


def render_story_setup(story_text: str) -> None:
    st.subheader("Teacher Preflight")
    st.caption("Confirm the source material before spending Rodin credits.")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.checkbox("Story text is final", value=len(story_text.strip()) >= 50, key="preflight_story")
    with col_b:
        st.checkbox("Target grade is 1st Grade", value=True, key="preflight_grade")
    with col_c:
        st.checkbox("Use standards alignment framework", value=True, key="preflight_standards")

    if not all(
        [
            st.session_state.get("preflight_story"),
            st.session_state.get("preflight_grade"),
            st.session_state.get("preflight_standards"),
        ]
    ):
        st.warning("Complete the preflight checks before starting the build.")


def render_lesson_target(context: dict[str, Any], lesson: dict[str, Any]) -> None:
    teacher = lesson.get("teacher_plan", {})
    left, right = st.columns([1, 1])
    with left:
        st.write(f"**Story:** {context.get('storybook_title')}")
        st.write(f"**Artifact:** {context.get('artifact_label')}")
        st.write(f"**Theme:** {context.get('theme')}")
        st.write(f"**Literacy:** {context.get('literacy_focus')}")
        st.write(f"**SEL:** {context.get('sel_focus')}")
    with right:
        st.markdown("**Learning Objectives**")
        for objective in teacher.get("learning_objectives", context.get("learning_objectives", [])):
            st.write(f"- {objective}")
        st.markdown("**Vocabulary**")
        for item in teacher.get("vocabulary", context.get("vocabulary", [])):
            st.write(f"- **{item.get('term', '')}:** {item.get('definition', '')}")


def render_standards(lesson: dict[str, Any], context: dict[str, Any]) -> None:
    teacher = lesson.get("teacher_plan", {})
    standards = teacher.get("standards") or context.get("standards_anchor", [])
    for standard in standards:
        st.write(f"- {standard}")


def render_asset_review(result: dict[str, Any]) -> None:
    rodin = result.get("rodin", {})
    bang = result.get("bang", {})
    preview = next((path for path in rodin.get("files", []) if str(path).lower().endswith(".webp")), None)

    left, right = st.columns([1, 1])
    with left:
        if preview and Path(preview).exists():
            st.image(preview, caption="Rodin preview", use_column_width=True)
        else:
            st.info("No preview image was returned. Use the OBJ path below for 3D inspection.")
    with right:
        st.write(f"**Rodin task:** `{rodin.get('task_uuid')}`")
        st.write(f"**Bang task:** `{bang.get('task_uuid')}`")
        st.write(f"**Selected OBJ:** `{bang.get('selected_obj')}`")
        st.caption("This source model is reviewed before the brick conversion output is approved.")


def render_editable_table(title: str, rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    st.markdown(f"**{title}**")
    edited = st.data_editor(
        rows,
        key=key,
        use_container_width=True,
        num_rows="fixed",
        hide_index=True,
    )
    if isinstance(edited, list):
        return edited
    return edited.to_dict("records")


def render_build_steps(build_plan: dict[str, Any]) -> None:
    st.markdown("**Inventory**")
    inv_cols = st.columns(3)
    for idx, item in enumerate(build_plan.get("inventory", [])):
        with inv_cols[idx % 3]:
            st.write(f"{item['quantity']} x {item['color']} {item['piece']}")

    st.divider()
    step_approvals = []
    for step in build_plan.get("assembly_steps", []):
        with st.container(border=True):
            left, right = st.columns([2, 1])
            with left:
                st.markdown(f"#### Step {step['step_number']}: {step['title']}")
                st.write(step["instruction"])
                st.caption("Parts used: " + ", ".join(step.get("parts_used", [])))
                approved = st.checkbox(
                    "Teacher approves this build step",
                    key=f"approve_step_{step['step_number']}",
                    value=False,
                )
                step_approvals.append(approved)
            with right:
                image_path = step.get("image_path")
                if image_path and Path(image_path).exists():
                    st.image(image_path, use_column_width=True)
    ensure_review_state()["build_steps"] = bool(step_approvals and all(step_approvals))


def numbered_path_key(path: Path) -> tuple[int, str]:
    match = re.search(r"(\d+)", path.stem)
    if match:
        return int(match.group(1)), path.name
    return 9999, path.name


def existing_file_path(path_value: Any) -> Path | None:
    if not path_value:
        return None
    path = Path(str(path_value))
    return path if path.is_file() else None


def notebook_output_images(build_plan: dict[str, Any]) -> list[Path]:
    manifest = build_plan.get("notebook_outputs", {})
    manifest_images = [path for value in manifest.get("images", []) if (path := existing_file_path(value))]
    if manifest_images:
        return sorted(manifest_images, key=numbered_path_key)
    return []


def render_notebook_output(result: dict[str, Any], build_plan: dict[str, Any]) -> None:
    st.markdown("**Notebook/CSP Brick Output Review**")
    st.write(
        "This checkpoint is where the teacher confirms that the output looks like real BrickSmart pieces "
        "and can be physically assembled before the final classroom report is approved."
    )

    source_obj = build_plan.get("source_obj") or result.get("bang", {}).get("selected_obj")
    st.write(f"**Segmented source OBJ:** `{source_obj}`")
    st.write(f"**Segment table:** `{build_plan.get('segments_csv')}`")
    st.write(f"**Connection table:** `{build_plan.get('interfaces_csv')}`")

    notebook_outputs = build_plan.get("notebook_outputs", {})
    status = notebook_outputs.get("status", "missing")
    st.write(f"**Notebook output status:** `{status}`")
    if notebook_outputs.get("source_obj"):
        st.write(f"**Generated from OBJ:** `{notebook_outputs.get('source_obj')}`")
    if notebook_outputs.get("voxel_size") is not None:
        st.write(
            f"**Voxel resolution:** `{notebook_outputs.get('voxel_size')}` "
            f"({notebook_outputs.get('resolution_profile', 'custom')})"
        )
    if notebook_outputs.get("block_count") is not None:
        st.write(f"**Approximate block count:** `{notebook_outputs.get('block_count')}`")
    if notebook_outputs.get("block_inventory"):
        st.markdown("**Approximate generated pieces**")
        st.dataframe(notebook_outputs["block_inventory"], use_container_width=True, hide_index=True)
    if notebook_outputs.get("note"):
        st.caption(notebook_outputs["note"])

    validation = notebook_outputs.get("validation", {})
    if validation:
        st.markdown("**Physical Validation**")
        metric_cols = st.columns(4)
        metric_cols[0].metric("Connected", "Yes" if validation.get("is_fully_connected") else "Review")
        metric_cols[1].metric("Components", validation.get("component_count", 0))
        metric_cols[2].metric("Invalid interfaces", validation.get("invalid_interface_count", 0))
        metric_cols[3].metric("Bridge blocks", validation.get("bridge_block_count", 0))
        if not validation.get("is_fully_connected") or validation.get("invalid_interface_count"):
            st.warning("Physical checks found items to review before approving the final teacher document.")

    connector_candidates = notebook_outputs.get("connector_candidates", [])
    if connector_candidates:
        st.markdown("**Teacher Movement Intent to Connector Sites**")
        st.dataframe(connector_candidates, use_container_width=True, hide_index=True)
        if any(item.get("status") != "candidate" for item in connector_candidates):
            st.info("Some moving parts need the teacher to confirm where the connector should attach.")

    final_image = existing_file_path(notebook_outputs.get("final_image"))
    if final_image:
        st.markdown("**Final Built Reference**")
        st.image(
            str(final_image),
            caption="Target final BrickSmart build generated from the segmented OBJ",
            use_column_width=True,
        )
    else:
        images = notebook_output_images(build_plan)
        if images:
            st.image(str(images[0]), caption=images[0].stem.replace("_", " ").title(), use_column_width=True)
        else:
            st.error(
                "No generated notebook outputs were found for this job. Run a new build or regenerate the job outputs; "
                "the UI no longer falls back to static images from the project folder."
            )

    notebook_steps = notebook_outputs.get("instruction_steps", [])
    step_approvals = []
    if notebook_steps:
        st.markdown("**Segment-to-Step Teacher and Student Instructions**")
        if st.button("Approve all build guide steps", use_container_width=True):
            for step in notebook_steps:
                st.session_state[f"approve_notebook_step_{step.get('step_number', 0)}"] = True
            review = ensure_review_state()
            review["build_steps"] = True
            review["notebook_output"] = True
            st.session_state["review_notebook_output"] = True
            st.rerun()
        for step in notebook_steps:
            step_number = step.get("step_number", len(step_approvals) + 1)
            with st.expander(f"Step {step_number}: {step.get('title', 'Build next section')}", expanded=True):
                left, right = st.columns([3, 2])
                with left:
                    st.markdown(f"#### Notebook Step {step_number}: {step.get('title', 'Build next section')}")
                    labels = step.get("segment_labels", [])
                    if labels:
                        st.caption("Segments: " + ", ".join(labels))
                    st.write(f"**Teacher:** {step.get('teacher_instruction', '')}")
                    st.write(f"**Student:** {step.get('student_instruction', '')}")
                    if step.get("teacher_check"):
                        st.info(step["teacher_check"])
                    inventory = step.get("inventory", [])
                    if inventory:
                        st.dataframe(inventory, use_container_width=True, hide_index=True)
                    approved = st.checkbox(
                        "Teacher confirms this notebook step is buildable",
                        key=f"approve_notebook_step_{step_number}",
                    )
                    step_approvals.append(approved)
                with right:
                    multiview_path = existing_file_path(step.get("multiview_path"))
                    if multiview_path:
                        st.image(str(multiview_path), caption=f"Notebook step {step_number} placement views", use_column_width=True)
                    image_path = existing_file_path(step.get("image_path"))
                    if image_path:
                        if st.checkbox("Show single isometric view", key=f"show_iso_step_{step_number}", value=False):
                            st.image(str(image_path), caption=f"Notebook step {step_number}", use_column_width=True)
                    else:
                        st.warning("Step render missing on disk.")
    else:
        st.warning("Notebook step instructions were not found in this job manifest. Regenerate notebook outputs for this job.")

    with st.expander("Notebook source views and legacy demo images", expanded=False):
        source_views = [
            ("Segment visualization", notebook_outputs.get("segment_visualization_image")),
            ("Segment multiview", notebook_outputs.get("segment_multiview_image")),
        ]
        for caption, path_value in source_views:
            image_path = existing_file_path(path_value)
            if image_path:
                st.image(str(image_path), caption=caption, use_column_width=True)
        generated_images = [
            existing_file_path(step.get("image_path"))
            for step in build_plan.get("assembly_steps", [])
            if existing_file_path(step.get("image_path"))
        ]
        if generated_images:
            cols = st.columns(2)
            for idx, image_path in enumerate(generated_images):
                with cols[idx % 2]:
                    st.image(str(image_path), caption=image_path.stem.replace("_", " ").title(), use_column_width=True)
        else:
            st.info("No generated demo step images were found.")

    st.text_area(
        "Teacher requested changes before final report",
        key="ks_demo_notebook_notes",
        height=120,
        placeholder="Example: make the wings static, move the connector to the body, reduce tall blocks...",
    )
    final_notebook_approval = st.checkbox(
        "Approve notebook brick output and buildability",
        value=ensure_review_state()["notebook_output"],
        key="review_notebook_output",
        help="Approve only after the visible pieces look like physical BrickSmart pieces and the model looks buildable.",
    )
    ensure_review_state()["notebook_output"] = final_notebook_approval and (
        not notebook_steps or bool(step_approvals and all(step_approvals))
    )
    ensure_review_state()["build_steps"] = not notebook_steps or bool(step_approvals and all(step_approvals))
    if notebook_steps and not all(step_approvals):
        st.info("Approve each notebook step before the notebook-output checkpoint is complete.")


def render_final_report(result: dict[str, Any], context: dict[str, Any], lesson: dict[str, Any], build_plan: dict[str, Any]) -> None:
    manual_path = result.get("manual_path")
    manual_text = ""
    if manual_path and Path(manual_path).exists():
        manual_text = Path(manual_path).read_text(encoding="utf-8")

    notes = st.text_area(
        "Teacher notes for this run",
        value=st.session_state.get("ks_demo_final_notes", ""),
        key="ks_demo_final_notes",
        height=120,
    )

    st.markdown("### Report Preview")
    if manual_text:
        st.markdown(manual_text)
    else:
        st.warning("The manual was not found on disk.")

    report_payload = {
        "context": context,
        "lesson_package": lesson,
        "build_plan": build_plan,
        "teacher_notes": notes,
        "teacher_connection_intent": build_plan.get("teacher_connection_intent", ""),
        "teacher_notebook_notes": st.session_state.get("ks_demo_notebook_notes", ""),
        "source_files": {
            "manual": manual_path,
            "job_dir": result.get("job_dir"),
            "segments_csv": build_plan.get("segments_csv"),
            "interfaces_csv": build_plan.get("interfaces_csv"),
            "notebook_outputs": build_plan.get("notebook_outputs", {}),
        },
    }

    col_a, col_b = st.columns(2)
    with col_a:
        if manual_text:
            st.download_button(
                "Download Teacher Manual",
                data=manual_text,
                file_name="kidspark_teacher_manual.md",
                mime="text/markdown",
                use_container_width=True,
            )
    with col_b:
        st.download_button(
            "Download Full Report JSON",
            data=json.dumps(report_payload, indent=2),
            file_name="kidspark_full_report.json",
            mime="application/json",
            use_container_width=True,
        )


def render_teacher_review(result: dict[str, Any]) -> None:
    context = result.get("context", {})
    lesson = result.get("lesson_package", {})
    build_plan = result.get("build_plan", {})
    review = ensure_review_state()

    tabs = st.tabs(
        [
            "1 Lesson Target",
            "2 Standards",
            "3 3D Asset",
            "4 Segment Labels",
            "5 Connections",
            "6 Brick Build Guide",
            "7 Notebook Source",
            "8 Final Report",
        ]
    )

    with tabs[0]:
        render_lesson_target(context, lesson)
        approve_checkbox("lesson_target", "Approve lesson target and vocabulary")

    with tabs[1]:
        render_standards(lesson, context)
        approve_checkbox(
            "standards_anchor",
            "Approve standards alignment",
            "The lesson remains anchored to the Literacy Program Standards Alignment and Framework.",
        )

    with tabs[2]:
        render_asset_review(result)
        approve_checkbox("rodin_asset", "Approve Rodin/Bang asset for this classroom build")

    with tabs[3]:
        rows = build_plan.get("segments", [])
        st.session_state["ks_demo_segments"] = render_editable_table(
            "Teacher-editable segment labels",
            st.session_state.get("ks_demo_segments", rows),
            "segments_editor",
        )
        approve_checkbox("segments", "Approve segment labels")

    with tabs[4]:
        st.info(
            "Connection intent should come from the teacher conversation first, then be checked against detected segment adjacency."
        )
        intent = build_plan.get("teacher_connection_intent") or result.get("context", {}).get("teacher_connection_intent", "")
        st.text_area(
            "Teacher connection intent",
            value=st.session_state.get("ks_demo_connection_review_notes", intent),
            key="ks_demo_connection_review_notes",
            height=90,
            placeholder="Example: propeller spins on a front axle; cargo box snaps rigidly under the body.",
        )
        rows = build_plan.get("interfaces", [])
        st.session_state["ks_demo_interfaces"] = render_editable_table(
            "Teacher-editable connection labels",
            st.session_state.get("ks_demo_interfaces", rows),
            "interfaces_editor",
        )
        approve_checkbox("connections", "Approve connection labels")

    with tabs[5]:
        render_notebook_output(result, build_plan)
        if not review["build_steps"]:
            st.info("Approve the generated notebook build steps to complete this checkpoint.")

    with tabs[6]:
        st.markdown("**Notebook Source Diagnostics**")
        notebook_outputs = build_plan.get("notebook_outputs", {})
        for caption, key in [
            ("Segment visualization", "segment_visualization_image"),
            ("Segment multiview", "segment_multiview_image"),
            ("Final block reference", "final_image"),
        ]:
            image_path = existing_file_path(notebook_outputs.get(key))
            if image_path:
                st.image(str(image_path), caption=caption, use_column_width=True)

    with tabs[7]:
        prior_keys = [key for key in REVIEW_KEYS if key != "final_report"]
        if not all(review.get(key) for key in prior_keys):
            st.warning(
                "Final confirmation should happen after lesson, standards, asset, segment, connection, "
                "build-step, and notebook-output review."
            )
        render_final_report(result, context, lesson, build_plan)
        approve_checkbox("final_report", "Approve final report for classroom use")

    st.subheader("Teacher Validation Summary")
    cols = st.columns(len(REVIEW_KEYS))
    labels = {
        "lesson_target": "Lesson",
        "standards_anchor": "Standards",
        "rodin_asset": "Asset",
        "segments": "Segments",
        "connections": "Connections",
        "build_steps": "Steps",
        "notebook_output": "Notebook",
        "final_report": "Report",
    }
    for idx, key in enumerate(REVIEW_KEYS):
        with cols[idx]:
            if review.get(key):
                st.success(labels[key])
            else:
                st.warning(labels[key])

    approved_count = sum(1 for key in REVIEW_KEYS if review.get(key))
    st.progress(approved_count / len(REVIEW_KEYS))
    if approved_count == len(REVIEW_KEYS):
        st.success("Teacher validation complete. The lesson plan and BrickSmart guide are ready to use.")
    else:
        st.info(f"{approved_count} of {len(REVIEW_KEYS)} validation checkpoints approved.")


query_job_id = st.query_params.get("job_id")
if query_job_id and not st.session_state.get("ks_demo_job_id"):
    st.session_state["ks_demo_job_id"] = query_job_id


with st.sidebar:
    sidebar_page_link("home.py", "Homepage")
    sidebar_page_link("pages/kidspark.py", "Teacher Chat Prototype")
    st.divider()
    st.caption("Local services")
    if st.button("Validate Rodin Balance", use_container_width=True):
        health = api("get", "/api/v1/build-demo/health")
        st.success(f"Rodin balance: {health['rodin'].get('balance')} credits")
    if st.button("Reset Demo", use_container_width=True):
        reset_demo()
        st.rerun()
    st.divider()
    st.caption("Open a generated report")
    existing_job_id = st.text_input("Existing job id", value="", key="load_existing_job_id")
    if st.button("Load Job Report", use_container_width=True):
        if existing_job_id.strip():
            st.session_state["ks_demo_job_id"] = existing_job_id.strip()
            st.session_state.pop("ks_demo_last_job", None)
            st.rerun()
        else:
            st.warning("Paste a job id first.")

st.title("KidSpark End-to-End Demo")
st.caption("Story text to teacher-reviewed lesson plan, Rodin/Bang asset, and BrickSmart build guide.")

story_text = st.text_area(
    "Story text",
    value=SAMPLE_STORY,
    height=260,
    help="Use the current example or paste a new story/lesson source.",
)

teacher_connection_intent = st.text_area(
    "Teacher connection and motion intent",
    value=st.session_state.get(
        "ks_demo_connection_intent",
        "The propeller should spin on a front axle. The wings and cargo compartment should attach rigidly to the body.",
    ),
    key="ks_demo_connection_intent",
    height=110,
    help="This text is carried into the interface table so connection choices come from teacher intent plus detected adjacency.",
)

render_story_setup(story_text)

launch_disabled = not all(
    [
        st.session_state.get("preflight_story"),
        st.session_state.get("preflight_grade"),
        st.session_state.get("preflight_standards"),
    ]
)

run_col, status_col = st.columns([1, 2])
with run_col:
    if st.button(
        "Start End-to-End Build",
        type="primary",
        use_container_width=True,
        disabled=launch_disabled,
    ):
        reset_demo()
        job = api(
            "post",
            "/api/v1/build-demo/jobs",
            json={
                "story_text": story_text,
                "teacher_connection_intent": teacher_connection_intent,
            },
        )
        st.session_state["ks_demo_job_id"] = job["job_id"]
        st.session_state["ks_demo_last_job"] = job
        st.rerun()
with status_col:
    st.write("The build calls OpenAI, Rodin text-to-3D, Bang segmentation, then assembles teacher outputs.")

job_id = st.session_state.get("ks_demo_job_id")
if not job_id:
    st.info("Start a build to generate a teacher-reviewed Rodin/Bang-backed guide.")
    st.stop()

st.caption(f"Current job: `{job_id}`")
job = load_job(job_id)
st.session_state["ks_demo_last_job"] = job

render_pipeline_status(job)

if job["status"] in ("queued", "running"):
    st.status("Pipeline running. This page refreshes every 10 seconds while long-running 3D jobs finish.", state="running")
    time.sleep(10)
    st.rerun()

if job["status"] == "error":
    st.error(job.get("message", "Build job failed."))
    if job.get("error"):
        st.code(job["error"])
    st.stop()

result = job.get("result") or {}
st.success("End-to-end generation complete. Teacher validation is ready.")
render_teacher_review(result)
