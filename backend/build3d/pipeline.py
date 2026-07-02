"""End-to-end local KidSpark demo pipeline.

This is intentionally pragmatic: it uses OpenAI for the lesson/build context,
Rodin/Bang for the 3D asset, and a deterministic guide renderer for the first
working demo. The notebook's full voxel/CSP path can replace the deterministic
guide stage behind the same output contract.
"""

from __future__ import annotations

import csv
import json
import re
import textwrap
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

from config import OPENAI_API_KEY, OPENAI_MODEL
from build3d.rodin_client import (
    RodinError,
    choose_obj,
    download_task,
    poll_until_done,
    submit_bang,
    submit_text_to_rodin,
)
from build3d.notebook_outputs import generate_notebook_outputs

ProgressFn = Callable[[str, int, str], None]

STANDARDS = [
    "NGSS K-2-ETS1-2: Develop a simple sketch, drawing, or physical model to illustrate how the shape of an object helps it function as needed to solve a given problem.",
    "ISTE 1.4 Innovative Designer: Students use technologies within a design process to identify and solve problems by creating new, useful, or imaginative solutions.",
    "CCSS RF.1.2: Demonstrate understanding of spoken words, syllables, and sounds.",
    "CCSS L.1.4: Determine or clarify word meanings based on grade 1 reading and content.",
    "CCSS SL.1.1: Participate in collaborative conversations with peers and adults.",
    "CASEL 1-5: Self-awareness, self-management, social awareness, relationship skills, and responsible decision-making.",
    "UDL: Use visual, verbal, and tactile representation with flexible action and expression.",
    "Science of Reading: Include phonemic awareness, vocabulary, comprehension, and oral expression in a brief integrated literacy moment.",
]


def create_model_context(
    story_text: str,
    teacher_connection_intent: str = "",
    seed_context: dict[str, Any] | None = None,
    job_dir: Path | None = None,
) -> dict[str, Any]:
    """Create the model task context used by Rodin and notebook physicalization."""
    if seed_context:
        context = _normalize_seed_context(seed_context)
    else:
        context = _create_model_task_context(story_text)
    context["teacher_connection_intent"] = teacher_connection_intent.strip()
    if job_dir:
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "model_task_context.json").write_text(json.dumps(context, indent=2), encoding="utf-8")
    return context


def create_rodin_preview(
    context: dict[str, Any],
    job_dir: Path,
    progress: ProgressFn,
) -> dict[str, Any]:
    """Run Rodin only so the teacher can approve the visual model before Bang."""
    job_dir.mkdir(parents=True, exist_ok=True)
    rodin_prompt = _rodin_prompt(context)
    context["rodin_prompt"] = rodin_prompt
    (job_dir / "model_task_context.json").write_text(json.dumps(context, indent=2), encoding="utf-8")

    progress("Submitting Rodin model preview", 10, "Creating the 3D reference model from the approved teacher prompt.")
    rodin_result = submit_text_to_rodin(rodin_prompt)
    rodin_uuid = rodin_result["uuid"]
    rodin_subscription = rodin_result["jobs"]["subscription_key"]
    (job_dir / "rodin_submit.json").write_text(json.dumps(rodin_result, indent=2), encoding="utf-8")

    poll_until_done(
        rodin_subscription,
        label="Rodin generation",
        progress=progress,
        percent_start=15,
        percent_end=85,
    )

    progress("Downloading Rodin preview", 92, "Saving generated model files locally.")
    rodin_files = download_task(rodin_uuid, job_dir / "rodin")
    result = {
        "context": context,
        "rodin": {
            "task_uuid": rodin_uuid,
            "prompt": rodin_prompt,
            "files": [str(p) for p in rodin_files],
        },
        "job_dir": str(job_dir),
    }
    (job_dir / "model_preview_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def create_segments_and_build_plan(
    context: dict[str, Any],
    rodin_task_uuid: str,
    rodin_files: list[str] | list[Path],
    job_dir: Path,
    progress: ProgressFn,
) -> dict[str, Any]:
    """Run Bang segmentation and notebook/CSP output generation."""
    job_dir.mkdir(parents=True, exist_ok=True)
    progress("Submitting Bang segmentation", 10, "Splitting the approved model into semantic parts.")
    bang_result = submit_bang(rodin_task_uuid)
    bang_uuid = bang_result["uuid"]
    bang_subscription = bang_result["jobs"]["subscription_key"]
    (job_dir / "bang_submit.json").write_text(json.dumps(bang_result, indent=2), encoding="utf-8")

    poll_until_done(
        bang_subscription,
        label="Bang segmentation",
        progress=progress,
        percent_start=15,
        percent_end=65,
    )

    progress("Downloading segmented asset", 72, "Saving Bang segmented model files locally.")
    bang_files = download_task(bang_uuid, job_dir / "bang")
    rodin_paths = [Path(p) for p in rodin_files]
    obj_path = choose_obj(bang_files) or choose_obj(rodin_paths)

    progress("Generating notebook build plan", 84, "Voxelizing segments and creating BrickSmart instruction images.")
    build_plan = _create_build_plan(context, obj_path, job_dir)
    result = {
        "context": context,
        "rodin": {
            "task_uuid": rodin_task_uuid,
            "files": [str(p) for p in rodin_paths],
        },
        "bang": {
            "task_uuid": bang_uuid,
            "files": [str(p) for p in bang_files],
            "selected_obj": str(obj_path) if obj_path else None,
        },
        "build_plan": build_plan,
        "job_dir": str(job_dir),
    }
    (job_dir / "segments_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def create_document_bundle(
    story_text: str,
    context: dict[str, Any],
    build_plan: dict[str, Any],
    job_dir: Path,
    progress: ProgressFn | None = None,
    lesson_package: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate the lesson plan, activity guide, and slide companion PDFs."""
    job_dir.mkdir(parents=True, exist_ok=True)
    if progress:
        progress("Drafting lesson bundle", 20, "Creating teacher, activity, and slide companion source documents.")
    lesson_package = lesson_package or _create_lesson_package(story_text, context)
    (job_dir / "lesson_package.json").write_text(json.dumps(lesson_package, indent=2), encoding="utf-8")
    bundle = _write_document_bundle(lesson_package, build_plan, context, job_dir)
    if progress:
        progress("Validating lesson bundle", 90, "Checking required sections and build images before download.")
    (job_dir / "document_bundle.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return {
        "lesson_package": lesson_package,
        "document_bundle": bundle,
        "job_dir": str(job_dir),
    }


def run_pipeline(
    story_text: str,
    job_dir: Path,
    progress: ProgressFn,
    teacher_connection_intent: str = "",
    seed_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    job_dir.mkdir(parents=True, exist_ok=True)

    progress("Analyzing story and planning build context", 5, "OpenAI is extracting the lesson target.")
    context = create_model_context(story_text, teacher_connection_intent, seed_context, job_dir)

    progress("Generating teacher lesson package", 15, "OpenAI is drafting the teacher plan and activity guide.")
    lesson_package = _create_lesson_package(story_text, context)
    (job_dir / "lesson_package.json").write_text(json.dumps(lesson_package, indent=2), encoding="utf-8")

    progress("Submitting Rodin text-to-3D job", 25, "Creating the 3D reference model from the build target.")
    rodin_prompt = _rodin_prompt(context)
    rodin_result = submit_text_to_rodin(rodin_prompt)
    rodin_uuid = rodin_result["uuid"]
    rodin_subscription = rodin_result["jobs"]["subscription_key"]
    (job_dir / "rodin_submit.json").write_text(json.dumps(rodin_result, indent=2), encoding="utf-8")

    poll_until_done(
        rodin_subscription,
        label="Rodin generation",
        progress=progress,
        percent_start=30,
        percent_end=55,
    )

    progress("Downloading Rodin asset", 56, "Saving generated model files locally.")
    rodin_files = download_task(rodin_uuid, job_dir / "rodin")

    progress("Submitting Bang segmentation job", 60, "Splitting the generated model into semantic parts.")
    bang_result = submit_bang(rodin_uuid)
    bang_uuid = bang_result["uuid"]
    bang_subscription = bang_result["jobs"]["subscription_key"]
    (job_dir / "bang_submit.json").write_text(json.dumps(bang_result, indent=2), encoding="utf-8")

    poll_until_done(
        bang_subscription,
        label="Bang segmentation",
        progress=progress,
        percent_start=65,
        percent_end=82,
    )

    progress("Downloading segmented asset", 83, "Saving Bang segmented model files locally.")
    bang_files = download_task(bang_uuid, job_dir / "bang")
    obj_path = choose_obj(bang_files) or choose_obj(rodin_files)

    progress("Generating BrickSmart build guide", 88, "Creating segment tables, connection labels, and build steps.")
    build_plan = _create_build_plan(context, obj_path, job_dir)
    manual_path = _write_teacher_manual(lesson_package, build_plan, context, job_dir)
    manual_pdf_path = _write_teacher_manual_pdf(manual_path)
    document_result = create_document_bundle(story_text, context, build_plan, job_dir, lesson_package=lesson_package)

    result = {
        "context": context,
        "lesson_package": lesson_package,
        "rodin": {
            "task_uuid": rodin_uuid,
            "files": [str(p) for p in rodin_files],
        },
        "bang": {
            "task_uuid": bang_uuid,
            "files": [str(p) for p in bang_files],
            "selected_obj": str(obj_path) if obj_path else None,
        },
        "build_plan": build_plan,
        "manual_path": str(manual_path),
        "manual_pdf_path": str(manual_pdf_path),
        "document_bundle": document_result.get("document_bundle", {}),
        "job_dir": str(job_dir),
    }
    (job_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    progress("Complete", 100, "End-to-end lesson and build guide are ready.")
    return result


def _client() -> OpenAI:
    return OpenAI(api_key=OPENAI_API_KEY)


def _json_chat(system: str, user: str, max_tokens: int = 2200) -> dict[str, Any]:
    resp = _client().chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.35,
        max_tokens=max_tokens,
    )
    content = resp.choices[0].message.content or "{}"
    return json.loads(content)


def _create_model_task_context(story_text: str) -> dict[str, Any]:
    system = (
        "You are KidSpark AI, a curriculum and block-building planner. "
        "Return only valid JSON. Anchor every plan to 1st Grade Storytime "
        "Inventing standards, UDL, CASEL, and Science of Reading."
    )
    user = f"""
Create model_task_context JSON for a Kid Spark lesson from this story.

Story:
{story_text}

JSON schema:
{{
  "storybook_title": string,
  "grade_band": "1st Grade",
  "duration_minutes": 35,
  "theme": string,
  "artifact_label": string,
  "artifact_family": string,
  "parts": [
    {{"part_name": string, "movement": "spinning|rolling|pivoting|static", "function": string, "suggested_piece": string}}
  ],
  "learning_objectives": [string, string],
  "literacy_focus": string,
  "sel_focus": string,
  "vocabulary": [{{"term": string, "definition": string}}],
  "rodin_prompt": string
}}

For "rodin_prompt", write only a physical object description for text-to-3D.
It must describe the build artifact's shape and visible parts. Do not write a
question, lesson objective, student prompt, or explanation.
"""
    data = _json_chat(system, user)
    data.setdefault("grade_band", "1st Grade")
    data.setdefault("duration_minutes", 35)
    data["parts"] = _normalize_part_movements(data.get("parts", []))
    data["standards_anchor"] = STANDARDS
    return data


def _create_lesson_package(story_text: str, context: dict[str, Any]) -> dict[str, Any]:
    system = (
        "You are KidSpark AI. Return only valid JSON. Write concise, classroom-ready "
        "teacher and student materials matching the Kid Spark Invent an Airplane "
        "structure: Overview, Learning Objectives, Curriculum Connections, Materials, "
        "Vocabulary, UDL, Anticipatory Set, Step 01 Read, Step 02 Learn & Explore, "
        "Step 03 Invent, Closure, Real-World Connection, Standards."
    )
    user = f"""
Story:
{story_text}

Model task context:
{json.dumps(context, indent=2)}

Standards anchor:
{json.dumps(STANDARDS, indent=2)}

Return JSON:
{{
  "teacher_plan": {{
    "title": string,
    "overview": string,
    "learning_objectives": [string],
    "curriculum_connections": [string],
    "activity_details": {{"time": string, "grade": string, "grouping": string}},
    "materials": [string],
    "vocabulary": [{{"term": string, "definition": string}}],
    "plan_for_all_learners": string,
    "anticipatory_set": string,
    "step_01_read": string,
    "step_02_learn_explore": string,
    "step_03_invent": string,
    "closure_reflection": string,
    "real_world_connection": string,
    "standards": [string]
  }},
  "student_activity_guide": {{
    "title": string,
    "read": string,
    "learn_explore": string,
    "invent": string,
    "real_world_connection": string,
    "reflection_questions": [string]
  }}
}}
"""
    return _json_chat(system, user, max_tokens=3600)


def _normalize_part_movements(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    static_terms = ("wing", "fin", "stabilizer", "body", "frame", "cargo", "compartment", "seat", "tail")
    spinning_terms = ("propeller", "rotor", "fan")
    rolling_terms = ("wheel", "tire")
    pivoting_terms = ("hinge", "door", "flap", "rudder")

    normalized = []
    for part in parts:
        row = dict(part)
        name = str(row.get("part_name", "")).lower()
        movement_value = str(row.get("movement", "static")).strip().lower()
        row["movement"] = movement_value
        if any(term in name for term in spinning_terms):
            row["movement"] = "spinning"
        elif any(term in name for term in rolling_terms):
            row["movement"] = "rolling"
        elif any(term in name for term in pivoting_terms):
            row["movement"] = "pivoting"
        elif any(term in name for term in static_terms):
            row["movement"] = "static"
        elif row.get("movement") not in ("spinning", "rolling", "pivoting", "static"):
            row["movement"] = "static"
        normalized.append(row)
    return normalized


def _normalize_seed_context(seed_context: dict[str, Any]) -> dict[str, Any]:
    context = dict(seed_context)
    context.setdefault("grade_band", "1st Grade")
    context.setdefault("duration_minutes", 35)
    context.setdefault("artifact_label", "Build artifact")
    context.setdefault("artifact_family", "teacher-selected build")
    context.setdefault("parts", [])
    context.setdefault("learning_objectives", [])
    context.setdefault("vocabulary", [])
    context.setdefault("standards_anchor", STANDARDS)
    context["parts"] = _normalize_part_movements(context.get("parts", []))
    if not context.get("rodin_prompt"):
        context["rodin_prompt"] = _rodin_prompt(context)
    return context


def _rodin_prompt(context: dict[str, Any]) -> str:
    parts = ", ".join(
        f"{part.get('part_name', '')} ({part.get('movement', 'static')})"
        for part in context.get("parts", [])
    )
    artifact = context.get("artifact_label", "vehicle")
    candidate = str(context.get("rodin_prompt") or "").strip()
    movement_guidance = (
        f" Clearly separate visible parts and movement intent: {parts}. "
        "Moving or articulated parts should be distinct from the static body so Bang segmentation can isolate them."
    )
    if candidate and "?" not in candidate and artifact.lower().split()[0] in candidate.lower():
        if "movement" in candidate.lower() or "moving" in candidate.lower() or not parts:
            return candidate
        return f"{candidate.rstrip('.')}.{movement_guidance}"
    return (
        f"A simple, child-friendly toy model of a {artifact}, "
        f"with clearly separated parts and movement intent: {parts}. "
        "Make moving parts visually distinct from static structure so Bang segmentation can separate them. "
        "Bright classroom block-toy style, chunky plastic, simple geometry, stable shape, "
        "suitable for conversion into block-building instructions."
    )


def _create_build_plan(context: dict[str, Any], obj_path: Path | None, job_dir: Path) -> dict[str, Any]:
    segments = _segments_from_context(context, obj_path)
    interfaces = _interfaces_from_segments(segments, context.get("teacher_connection_intent", ""))
    segment_csv = job_dir / "segments_labeled.csv"
    interface_csv = job_dir / "interfaces_labeled.csv"
    _write_csv(segment_csv, segments)
    _write_csv(interface_csv, interfaces)

    steps = _assembly_steps(context, segments)
    image_paths = _render_step_images(context, steps, job_dir / "step_images")
    for step, image_path in zip(steps, image_paths):
        step["image_path"] = str(image_path)

    inventory = _inventory(context)
    notebook_outputs = generate_notebook_outputs(
        obj_path,
        job_dir,
        segment_rows=segments,
        artifact_label=context.get("artifact_label", "BrickSmart model"),
        movement_intents=context.get("parts", []),
        teacher_connection_intent=context.get("teacher_connection_intent", ""),
    )
    notebook_validation = notebook_outputs.get("validation", {})
    build_plan = {
        "artifact_label": context.get("artifact_label", "Build artifact"),
        "source_obj": str(obj_path) if obj_path else None,
        "segments_csv": str(segment_csv),
        "interfaces_csv": str(interface_csv),
        "segments": segments,
        "interfaces": interfaces,
        "inventory": inventory,
        "assembly_steps": steps,
        "notebook_outputs": notebook_outputs,
        "teacher_connection_intent": context.get("teacher_connection_intent", ""),
        "validation": {
            "is_connected": bool(notebook_validation.get("is_fully_connected")),
            "invalid_interface_count": notebook_validation.get("invalid_interface_count", 0),
            "connector_review_required": notebook_validation.get("connector_review_required", False),
            "warnings": build_validation_warnings(notebook_validation),
        },
    }
    (job_dir / "build_plan.json").write_text(json.dumps(build_plan, indent=2), encoding="utf-8")
    return build_plan


def build_validation_warnings(validation: dict[str, Any]) -> list[str]:
    warnings = []
    if not validation.get("is_fully_connected"):
        warnings.append("CSP connectivity check found disconnected block components; teacher should review physical buildability.")
    invalid_count = int(validation.get("invalid_interface_count") or 0)
    if invalid_count:
        warnings.append(f"{invalid_count} block interfaces did not form a secure male/female attachment.")
    if validation.get("connector_review_required"):
        warnings.append("One or more moving-part connector sites need teacher placement review.")
    return warnings or ["CSP physicalization checks passed for this generated block plan."]


def _segments_from_context(context: dict[str, Any], obj_path: Path | None) -> list[dict[str, Any]]:
    obj_names: list[str] = []
    if obj_path and obj_path.exists():
        for line in obj_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("o "):
                obj_names.append(line[2:].strip())
    parts = context.get("parts") or []
    if not parts:
        parts = [{"part_name": context.get("artifact_label", "body"), "movement": "static", "function": "main structure"}]

    rows = []
    max_count = max(len(parts), len(obj_names) or 0)
    for idx in range(max_count):
        part = parts[idx % len(parts)]
        rows.append({
            "segment_id": idx + 1,
            "source_name": obj_names[idx] if idx < len(obj_names) else f"generated_part_{idx + 1}",
            "label": _slug(part.get("part_name", f"part_{idx + 1}")),
            "movement": part.get("movement", "static"),
            "function": part.get("function", ""),
            "teacher_confirmed": True,
        })
    return rows


def _interfaces_from_segments(segments: list[dict[str, Any]], teacher_connection_intent: str = "") -> list[dict[str, Any]]:
    rows = []
    teacher_intent = teacher_connection_intent.strip()
    for idx in range(max(len(segments) - 1, 0)):
        a = segments[idx]
        b = segments[idx + 1]
        connection = _connection_type_from_teacher_intent(a, b, teacher_intent)
        rows.append({
            "interface_id": idx + 1,
            "segment_a": a["segment_id"],
            "label_a": a["label"],
            "segment_b": b["segment_id"],
            "label_b": b["label"],
            "connection_type": connection,
            "source": "teacher_prompt_plus_adjacency" if teacher_intent else "adjacency_heuristic",
            "teacher_intent": teacher_intent,
            "confidence": 0.82,
            "teacher_confirmed": True,
        })
    return rows


def _connection_type_from_teacher_intent(a: dict[str, Any], b: dict[str, Any], teacher_intent: str) -> str:
    labels = f"{a.get('label', '')} {b.get('label', '')}".lower()
    intent = teacher_intent.lower()
    movement = str(b.get("movement", "static")).lower()

    pair_mentions_propeller = any(term in labels for term in ("propeller", "rotor", "fan"))
    pair_mentions_wheel = any(term in labels for term in ("wheel", "tire"))
    pair_mentions_hinge = any(term in labels for term in ("hinge", "flap", "door", "rudder"))
    pair_mentions_rigid_part = any(term in labels for term in ("cargo", "box", "compartment", "wing", "tail", "fin"))
    pair_mentions_static = any(term in labels for term in ("body", "cargo", "box", "compartment", "wing", "tail", "fin"))

    if pair_mentions_rigid_part and any(term in intent for term in ("rigid", "snap", "fixed", "static", "stable")):
        return "static_snap"
    if pair_mentions_propeller and any(term in intent for term in ("propeller", "spin", "rotate", "rotor", "fan", "axle")):
        return "axle_rotation"
    if pair_mentions_wheel and any(term in intent for term in ("wheel", "roll", "tire", "axle")):
        return "wheel_axle"
    if pair_mentions_hinge and any(term in intent for term in ("hinge", "pivot", "flap", "door", "rudder")):
        return "hinge_connector"
    if pair_mentions_static and any(term in intent for term in ("rigid", "snap", "fixed", "static", "stable")):
        return "static_snap"
    if movement == "spinning":
        return "axle_rotation"
    if movement == "rolling":
        return "wheel_axle"
    if movement == "pivoting":
        return "hinge_connector"
    return "static_snap"


def _assembly_steps(context: dict[str, Any], segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    artifact = context.get("artifact_label", "artifact")
    parts = context.get("parts") or []
    steps = [
        {
            "step_number": 1,
            "title": "Build the main body",
            "instruction": f"Connect blue cube blocks in a straight, sturdy row to form the main body of the {artifact}.",
            "parts_used": ["Blue cube blocks"],
        }
    ]
    moving = [p for p in parts if p.get("movement") != "static"]
    static = [p for p in parts if p.get("movement") == "static"]
    if static:
        labels = ", ".join(sorted({p.get("part_name", "part").lower() for p in static})) or "side structures"
        steps.append({
            "step_number": len(steps) + 1,
            "title": "Add the stable parts",
            "instruction": f"Add the static parts, including {labels}. Make each side balanced so the model can sit flat.",
            "parts_used": ["Green and blue cube blocks", "Flat connectors"],
        })
    seen_moving: set[str] = set()
    for part in moving:
        movement = part.get("movement")
        label = part.get("part_name", "moving part").lower()
        key = f"{label}:{movement}"
        if key in seen_moving:
            continue
        seen_moving.add(key)
        if movement == "spinning":
            instruction = f"Attach the {label} with a wheel/axle assembly so it can spin freely."
            parts = ["Wheel/axle assembly", "Connector block"]
        elif movement == "rolling":
            instruction = f"Attach the {label} under the body with wheel/axle pieces so the model can roll."
            parts = ["Wheel/axle assemblies", "Flat connectors"]
        elif movement == "pivoting":
            instruction = f"Attach the {label} with an angle connector so students can test a pivoting motion."
            parts = ["Angle connector", "Cube block"]
        else:
            instruction = f"Attach the {label} securely to the body."
            parts = ["Cube block"]
        steps.append({
            "step_number": len(steps) + 1,
            "title": f"Add {label}",
            "instruction": instruction,
            "parts_used": parts,
        })
    steps.append({
        "step_number": len(steps) + 1,
        "title": "Test and explain",
        "instruction": f"Check that the {artifact} stays together, then ask students to explain how each part helps it work.",
        "parts_used": ["Completed model"],
    })
    return steps


def _inventory(context: dict[str, Any]) -> list[dict[str, Any]]:
    parts = context.get("parts", [])
    static_count = max(8, 2 * len([p for p in parts if p.get("movement") == "static"]))
    moving = [p for p in parts if p.get("movement") != "static"]
    inventory = [
        {"piece": "2x2x2 cube block", "color": "Blue", "quantity": static_count},
        {"piece": "2x2x3 cube block", "color": "Green", "quantity": max(2, len(parts))},
        {"piece": "Flat connector", "color": "Assorted", "quantity": max(2, len(parts) // 2)},
    ]
    wheel_qty = sum(1 for p in moving if p.get("movement") in ("spinning", "rolling"))
    hinge_qty = sum(1 for p in moving if p.get("movement") == "pivoting")
    if wheel_qty:
        inventory.append({"piece": "Wheel/axle assembly", "color": "Black/Red", "quantity": wheel_qty})
    if hinge_qty:
        inventory.append({"piece": "Angle connector", "color": "Red", "quantity": hinge_qty})
    return inventory


def _render_step_images(context: dict[str, Any], steps: list[dict[str, Any]], image_dir: Path) -> list[Path]:
    image_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for step in steps:
        img = Image.new("RGB", (1100, 700), "#f7fbff")
        draw = ImageDraw.Draw(img)
        title_font = _font(44)
        body_font = _font(28)
        small_font = _font(22)
        draw.rounded_rectangle((40, 40, 1060, 660), radius=18, outline="#0a9fd8", width=4, fill="#ffffff")
        draw.text((80, 75), f"Step {step['step_number']}: {step['title']}", fill="#18a0d8", font=title_font)
        _draw_wrapped(draw, step["instruction"], (80, 155), 64, body_font, "#222222")
        draw.text((80, 455), "Parts used:", fill="#72bf44", font=body_font)
        _draw_wrapped(draw, ", ".join(step["parts_used"]), (80, 505), 72, small_font, "#333333")
        draw.rectangle((760, 210, 970, 380), outline="#1b75bb", width=5, fill="#d8ecff")
        draw.rectangle((820, 160, 930, 430), outline="#72bf44", width=5)
        draw.ellipse((790, 405, 850, 465), fill="#222222")
        draw.ellipse((900, 405, 960, 465), fill="#222222")
        draw.text((760, 500), context.get("artifact_label", "Build model").title(), fill="#666666", font=small_font)
        path = image_dir / f"step_{step['step_number']:02d}.png"
        img.save(path)
        paths.append(path)
    return paths


def _write_document_bundle(
    lesson_package: dict[str, Any],
    build_plan: dict[str, Any],
    context: dict[str, Any],
    job_dir: Path,
) -> dict[str, Any]:
    docs_dir = job_dir / "lesson_bundle"
    docs_dir.mkdir(parents=True, exist_ok=True)
    docs = {
        "lesson_plan": _lesson_plan_markdown(lesson_package, build_plan, context),
        "activity_guide": _activity_guide_markdown(lesson_package, build_plan, context),
        "slide_companion": _slide_companion_markdown(lesson_package, build_plan, context),
    }
    manifest: dict[str, Any] = {"documents": {}, "validation": {}}
    for kind, text in docs.items():
        md_path = docs_dir / f"{kind}.md"
        md_path.write_text(text, encoding="utf-8")
        pdf_path = _write_teacher_manual_pdf(md_path)
        validation = _validate_document(kind, text, build_plan)
        manifest["documents"][kind] = {
            "markdown_path": str(md_path),
            "pdf_path": str(pdf_path),
            "title": _document_title(kind),
        }
        manifest["validation"][kind] = validation
    manifest["all_valid"] = all(item.get("is_valid") for item in manifest["validation"].values())
    return manifest


def _document_title(kind: str) -> str:
    return {
        "lesson_plan": "Teacher Lesson Plan",
        "activity_guide": "Student Activity Guide",
        "slide_companion": "Slide Companion",
    }.get(kind, kind.replace("_", " ").title())


def _lesson_plan_markdown(
    lesson_package: dict[str, Any],
    build_plan: dict[str, Any],
    context: dict[str, Any],
) -> str:
    teacher = lesson_package.get("teacher_plan", {})
    notebook = build_plan.get("notebook_outputs", {})
    parts = context.get("parts", [])
    vocabulary = teacher.get("vocabulary", context.get("vocabulary", []))
    reflection_questions = [
        "How did the story problem connect to the model students built?",
        "Which part of the build helped the invention work?",
        "Where did students test, improve, or explain their design choices?",
        "How did partners help each other during the inventing work?",
    ]
    lines = [
        f"# {teacher.get('title', context.get('storybook_title', 'KidSpark Lesson Plan'))}",
        "",
        "## Storytime Inventing Teacher Lesson Plan",
        f"Grade: {context.get('grade_band', teacher.get('activity_details', {}).get('grade', '1st Grade'))}",
        f"Time: {context.get('duration_minutes', 35)} minutes",
        "Grouping: Whole-group read-aloud, then pairs or small groups for inventing.",
        "",
        "## Teacher Overview",
        teacher.get("overview", f"Students connect the story theme to a hands-on {context.get('artifact_label', 'model')} build."),
        "",
        "## Learning Objectives",
        *[f"- {x}" for x in teacher.get("learning_objectives", context.get("learning_objectives", []))],
        "",
        "## Anticipatory Set",
        teacher.get("anticipatory_set", "Invite students to describe the build object, how it might move, and what problem it helps solve in the story."),
        "",
        "## Step 01: Read",
        teacher.get("step_01_read", "Read the story aloud and pause for vocabulary, character feelings, and the problem students will solve through building."),
        "",
        "## Step 02: Learn & Explore",
        teacher.get("step_02_learn_explore", "Explore the parts of the build object and connect each part to what it does in the real world."),
        "",
        "## Step 03: Invent",
        teacher.get("step_03_invent", f"Students build and test a {context.get('artifact_label', 'model')} with Kid Spark pieces, then explain how their model connects to the story."),
        "",
        "## Closure & Reflection Questions",
        teacher.get("closure_reflection", "Students share what worked, what changed, and how the story inspired their invention."),
        "",
        *[f"- {q}" for q in reflection_questions],
        "",
        "## Build Preview",
        f"Students will build: **{context.get('artifact_label', build_plan.get('artifact_label', 'BrickSmart model'))}**",
        "",
        "Key visible parts:",
        *[f"- {part.get('part_name', 'part')}: {part.get('movement', 'static')}" for part in parts],
        "",
        f"Final built reference image: {notebook.get('final_image', '')}",
        "",
        f"Placement views: {notebook.get('segment_multiview_image', '')}",
        "",
        "## Materials",
        *[f"- {x}" for x in teacher.get("materials", ["Kid Spark blocks", "Student activity guide", "Slide companion", "Build step images"])],
        "",
        "## Vocabulary And Literacy Focus",
        *[f"- **{v.get('term', '')}:** {v.get('definition', '')}" for v in vocabulary if isinstance(v, dict)],
        f"- Literacy focus: {context.get('literacy_focus', teacher.get('step_01_read', 'Vocabulary and oral language connected to the story.'))}",
        "",
        "## Plan For All Learners",
        teacher.get("plan_for_all_learners", "Use visual, verbal, and tactile options. Let students point, explain, draw, or build to show understanding."),
        "",
        "## Standards And Framework Alignment",
        *[f"- {x}" for x in teacher.get("standards", context.get("standards_anchor", STANDARDS))],
        "",
        "## SEL Focus",
        context.get("sel_focus", "Collaboration, perseverance, and responsible decision-making."),
    ]
    return "\n".join(lines)


def _activity_guide_markdown(
    lesson_package: dict[str, Any],
    build_plan: dict[str, Any],
    context: dict[str, Any],
) -> str:
    student = lesson_package.get("student_activity_guide", {})
    notebook = build_plan.get("notebook_outputs", {})
    vocabulary = context.get("vocabulary", [])
    focus_term = (vocabulary[0].get("term") if vocabulary and isinstance(vocabulary[0], dict) else context.get("artifact_label", "machine"))
    parts = [part.get("part_name", "part") for part in context.get("parts", [])]
    lines = [
        f"# {student.get('title', 'Storytime Inventing Activity Guide')}",
        "",
        f"## Activity Guide - {context.get('grade_band', '1st Grade')}",
        f"Build focus: **{context.get('artifact_label', 'BrickSmart model')}**",
        "",
        "## Step 01 - Read",
        student.get("read", f"Listen for the problem in the story and notice how characters try new ideas."),
        "",
        "## Step 02 - Learn & Explore",
        student.get("learn_explore", f"Look closely at the parts of a {context.get('artifact_label', 'model')} and talk about how each part helps it work."),
        "",
        "Important parts to notice:",
        *[f"- {part}" for part in parts],
        "",
        "## Vocabulary",
        f"Vocabulary word: **{focus_term}**",
        "",
        "A machine is something people make to help with work or make tasks easier.",
        "",
        "## Sound Awareness",
        "Sound awareness: Say the word slowly. What beginning sound do you hear? What words rhyme or share an ending sound?",
        "",
        "## Step 03 - Invent",
        student.get("invent", f"Build your own {context.get('artifact_label', 'model')} with BrickSmart pieces."),
        "",
        "## Example Build",
        f"Final built reference image: {notebook.get('final_image', '')}",
        "",
        f"Placement views: {notebook.get('segment_multiview_image', '')}",
        "",
        "## Real-World Connection",
        student.get("real_world_connection", "Engineers test ideas, improve designs, and explain how their inventions help people."),
        "",
        "## Reflection Questions",
        *[f"- {q}" for q in student.get("reflection_questions", [])],
    ]
    if not student.get("reflection_questions"):
        lines.extend([
            "- What did your invention do?",
            "- Which part moved or helped the model work?",
            "- What would you improve next time?",
        ])
    return "\n".join(lines)


def _slide_companion_markdown(
    lesson_package: dict[str, Any],
    build_plan: dict[str, Any],
    context: dict[str, Any],
) -> str:
    teacher = lesson_package.get("teacher_plan", {})
    notebook = build_plan.get("notebook_outputs", {})
    steps = notebook.get("instruction_steps", [])
    title = context.get("storybook_title", "KidSpark")
    lines = [
        f"# {title} Slide Companion",
        "",
        "## Slide 1 - Storytime Inventing",
        f"Today we will read, talk, and build a {context.get('artifact_label', 'model')}.",
        "",
        "## Slide 2 - Big Idea",
        context.get("theme", teacher.get("overview", "Inventors learn from testing and improving.")),
        "",
        "## Slide 3 - Vocabulary",
        context.get("literacy_focus", "Listen for important words from the story."),
        "",
        "## Slide 4 - Parts Of The Build",
        ", ".join(part.get("part_name", "part") for part in context.get("parts", [])),
        "",
        "## Slide 5 - Final Build Preview",
        f"Final built reference image: {notebook.get('final_image', '')}",
        "",
        f"Placement views: {notebook.get('segment_multiview_image', '')}",
        "",
    ]
    for step in steps:
        number = step.get("step_number", "")
        lines.extend([
            f"## Slide {5 + int(number or 0)} - Build Step {number}",
            step.get("student_instruction", step.get("teacher_instruction", "")),
            "",
            f"Image: {step.get('image_path', '')}",
            "",
            f"Placement views: {step.get('multiview_path', '')}",
            "",
        ])
    lines.extend([
        "## Final Slide - Share And Reflect",
        "Turn to a partner. Explain what your model does, which part moves, and one thing you improved.",
    ])
    return "\n".join(lines)


def _build_step_markdown(step: dict[str, Any], student_facing: bool = False) -> list[str]:
    instruction_key = "student_instruction" if student_facing else "teacher_instruction"
    inventory = ", ".join(
        f"{item.get('quantity')} x {item.get('piece')}"
        for item in step.get("inventory", [])
    )
    return [
        f"### Build Step {step.get('step_number')}: {step.get('title', '')}",
        step.get(instruction_key, step.get("teacher_instruction", "")),
        "",
        f"Pieces: {inventory}",
        "",
        f"Image: {step.get('image_path', '')}",
        "",
        f"Placement views: {step.get('multiview_path', '')}",
        "",
    ]


def _validate_document(kind: str, text: str, build_plan: dict[str, Any]) -> dict[str, Any]:
    required = {
        "lesson_plan": ["Learning Objectives", "Step 01", "Step 02", "Step 03", "Closure", "Build Preview", "Standards"],
        "activity_guide": ["Step 01", "Step 02", "Step 03", "Example Build", "Real-World Connection", "Reflection"],
        "slide_companion": ["Slide", "Build Step", "Reflect"],
    }[kind]
    missing = [item for item in required if item.lower() not in text.lower()]
    notebook_steps = build_plan.get("notebook_outputs", {}).get("instruction_steps", [])
    image_refs = [step.get("image_path") for step in notebook_steps if step.get("image_path")]
    if kind == "activity_guide" and "Final built reference image:" not in text:
        missing.append("final build image")
    if kind == "slide_companion" and image_refs and "Image:" not in text:
        missing.append("notebook build images")
    return {
        "is_valid": not missing,
        "missing": missing,
        "image_count": len(image_refs) if kind == "slide_companion" else int("Final built reference image:" in text),
    }


def _write_teacher_manual(
    lesson_package: dict[str, Any],
    build_plan: dict[str, Any],
    context: dict[str, Any],
    job_dir: Path,
) -> Path:
    teacher = lesson_package.get("teacher_plan", {})
    student = lesson_package.get("student_activity_guide", {})
    lines = [
        f"# {teacher.get('title', 'KidSpark Lesson Plan')}",
        "",
        "## Overview",
        teacher.get("overview", ""),
        "",
        "## Learning Objectives",
        *[f"- {x}" for x in teacher.get("learning_objectives", context.get("learning_objectives", []))],
        "",
        "## Standards Anchor",
        *[f"- {x}" for x in teacher.get("standards", STANDARDS)],
        "",
        "## Vocabulary",
        *[f"- **{v.get('term', '')}:** {v.get('definition', '')}" for v in teacher.get("vocabulary", context.get("vocabulary", []))],
        "",
        "## Plan for All Learners",
        teacher.get("plan_for_all_learners", ""),
        "",
        "## Lesson Flow",
        f"**Anticipatory Set:** {teacher.get('anticipatory_set', '')}",
        "",
        f"**Step 01 - Read:** {teacher.get('step_01_read', '')}",
        "",
        f"**Step 02 - Learn & Explore:** {teacher.get('step_02_learn_explore', '')}",
        "",
        f"**Step 03 - Invent:** {teacher.get('step_03_invent', '')}",
        "",
        f"**Closure & Reflection:** {teacher.get('closure_reflection', '')}",
        "",
        "## Student Activity Guide",
        student.get("read", ""),
        "",
        student.get("learn_explore", ""),
        "",
        student.get("invent", ""),
        "",
        "## BrickSmart Build Guide",
        f"Artifact: **{build_plan.get('artifact_label', '')}**",
        "",
        "### Inventory",
        *[f"- {i['quantity']} x {i['color']} {i['piece']}" for i in build_plan.get("inventory", [])],
        "",
        "### Generated BrickSmart Instructions",
    ]
    notebook_outputs = build_plan.get("notebook_outputs", {})
    notebook_steps = notebook_outputs.get("instruction_steps", [])
    validation = notebook_outputs.get("validation", {})
    connector_candidates = notebook_outputs.get("connector_candidates", [])
    if validation:
        lines.extend([
            "### Physical Build Validation",
            f"- Fully connected: {validation.get('is_fully_connected')}",
            f"- Component count: {validation.get('component_count')}",
            f"- Invalid block interfaces: {validation.get('invalid_interface_count')}",
            f"- Connector sites needing review: {validation.get('connector_review_required')}",
            "",
        ])
    if connector_candidates:
        lines.extend(["### Moving-Part Connector Sites"])
        for candidate in connector_candidates:
            lines.append(
                "- "
                f"{candidate.get('part_name', 'part')}: {candidate.get('movement')} via "
                f"{candidate.get('connector_type')} ({candidate.get('status')}); "
                f"segments {candidate.get('segments')}"
            )
        lines.append("")
    if notebook_steps:
        lines.extend([
            "### Notebook Brick Instructions",
            f"Final built reference image: {notebook_outputs.get('final_image', '')}",
            "",
        ])
        for step in notebook_steps:
            inventory = ", ".join(
                f"{item.get('quantity')} x {item.get('piece')}"
                for item in step.get("inventory", [])
            )
            lines.extend([
                f"#### Notebook Step {step.get('step_number')}: {step.get('title', '')}",
                f"Teacher: {step.get('teacher_instruction', '')}",
                "",
                f"Student: {step.get('student_instruction', '')}",
                "",
                f"Segments: {', '.join(step.get('segment_labels', []))}",
                "",
                f"Pieces: {inventory}",
                "",
                f"Image: {step.get('image_path', '')}",
                "",
                f"Placement views: {step.get('multiview_path', '')}",
                "",
            ])
    lines.extend([
        "## Reflection Questions",
        *[f"- {q}" for q in student.get("reflection_questions", [])],
    ])
    path = job_dir / "teacher_manual.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_teacher_manual_pdf(markdown_path: Path) -> Path:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
    except Exception:
        return markdown_path

    pdf_path = markdown_path.with_suffix(".pdf")
    kind = markdown_path.stem
    is_slide = kind == "slide_companion"
    page_size = landscape(letter) if is_slide else letter
    accent = {
        "lesson_plan": colors.HexColor("#1f6fb2"),
        "activity_guide": colors.HexColor("#f6a623"),
        "slide_companion": colors.HexColor("#17a2b8"),
    }.get(kind, colors.HexColor("#1f6fb2"))
    soft = {
        "lesson_plan": colors.HexColor("#eaf4ff"),
        "activity_guide": colors.HexColor("#fff3d8"),
        "slide_companion": colors.HexColor("#e8fbff"),
    }.get(kind, colors.HexColor("#eaf4ff"))

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="KidSparkTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=24 if not is_slide else 28,
        leading=30 if not is_slide else 34,
        textColor=colors.HexColor("#1f2937"),
        spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="KidSparkHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14 if not is_slide else 20,
        leading=18 if not is_slide else 24,
        textColor=accent,
        backColor=soft,
        borderPadding=(6, 8, 6, 8),
        spaceBefore=10,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="KidSparkSubheading",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=12 if not is_slide else 15,
        leading=15 if not is_slide else 18,
        textColor=colors.HexColor("#344054"),
        spaceBefore=8,
        spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="KidSparkBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.8 if not is_slide else 13,
        leading=13.5 if not is_slide else 17,
        textColor=colors.HexColor("#283243"),
        spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="KidSparkBullet",
        parent=styles["KidSparkBody"],
        leftIndent=14,
        firstLineIndent=-8,
    ))
    story = []
    first_slide_section = True
    for raw_line in markdown_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 5 if not is_slide else 8))
            continue
        image_path = image_path_from_manual_line(line)
        if image_path:
            story.append(Paragraph(_inline_markup(image_path["label"]), styles["KidSparkSubheading"]))
            story.append(
                fit_report_image(
                    image_path["path"],
                    max_width=650 if is_slide else 470,
                    max_height=350 if is_slide else 250,
                )
            )
            story.append(Spacer(1, 8 if not is_slide else 12))
            continue
        if line.startswith("# "):
            story.append(Paragraph(_inline_markup(line[2:]), styles["KidSparkTitle"]))
        elif line.startswith("## "):
            if is_slide and line.startswith("## Slide") and not first_slide_section:
                story.append(PageBreak())
            first_slide_section = False
            story.append(Paragraph(_inline_markup(line[3:]), styles["KidSparkHeading"]))
        elif line.startswith("### "):
            story.append(Paragraph(_inline_markup(line[4:]), styles["KidSparkSubheading"]))
        elif line.startswith("#### "):
            story.append(Paragraph(_inline_markup(line[5:]), styles["KidSparkSubheading"]))
        elif line.startswith("- "):
            story.append(Paragraph(f"&bull; {_inline_markup(line[2:])}", styles["KidSparkBullet"]))
        else:
            story.append(Paragraph(_inline_markup(line), styles["KidSparkBody"]))

    def draw_page(canvas, doc):
        canvas.saveState()
        width, height = page_size
        canvas.setFillColor(accent)
        canvas.rect(0, height - 0.34 * inch, width, 0.34 * inch, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(0.55 * inch, height - 0.22 * inch, "KID SPARK EDUCATION")
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(width - 0.55 * inch, 0.32 * inch, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=page_size,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.62 * inch,
        bottomMargin=0.52 * inch,
    )
    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return pdf_path


def _inline_markup(text: str) -> str:
    from xml.sax.saxutils import escape

    escaped = escape(str(text))
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)


def image_path_from_manual_line(line: str) -> dict[str, Any] | None:
    prefixes = [
        ("Final built reference image:", "Final built reference"),
        ("Image:", "Notebook step image"),
        ("Placement views:", "Notebook placement views"),
    ]
    for prefix, label in prefixes:
        if not line.startswith(prefix):
            continue
        raw_path = line[len(prefix):].strip()
        path = Path(raw_path)
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            return {"label": label, "path": path}
    return None


def fit_report_image(path: Path, max_width: int, max_height: int) -> Any:
    from PIL import Image as PILImage
    from reportlab.platypus import Image as ReportImage

    with PILImage.open(path) as img:
        width, height = img.size
    scale = min(max_width / max(width, 1), max_height / max(height, 1), 1.0)
    return ReportImage(str(path), width=width * scale, height=height * scale)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _draw_wrapped(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], width: int, font: Any, fill: str) -> None:
    x, y = xy
    for line in textwrap.wrap(text, width=width):
        draw.text((x, y), line, fill=fill, font=font)
        y += int(font.size * 1.25) if hasattr(font, "size") else 24


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    return value.strip("_") or "part"
