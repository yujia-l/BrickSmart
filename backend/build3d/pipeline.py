"""End-to-end local KidSpark demo pipeline.

This is intentionally pragmatic: it uses Vertex Gemini for lesson/build context,
Rodin/Bang for the 3D asset, and a deterministic guide renderer for the first
working demo. The notebook's full voxel/CSP path can replace the deterministic
guide stage behind the same output contract.
"""

from __future__ import annotations

import csv
import json
import math
import re
import textwrap
from itertools import combinations
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFont

from llm.vertex_gemini import generate_json, provider_configured
from build3d.rodin_client import (
    RodinError,
    choose_obj,
    download_task,
    poll_until_done,
    submit_bang,
    submit_text_to_rodin,
)
from build3d.notebook_outputs import generate_notebook_outputs, load_obj_segments
from build3d.validated_planner_adapter import apply_catalog_constraints, run_validated_planner, semantic_segment_targets

ProgressFn = Callable[[str, int, str], None]
RODIN_PROMPT_LIMIT = 1000
MAX_AUTO_MODEL_RECOVERY_ATTEMPTS = 2

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
    context = apply_catalog_constraints(context)
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
    context = apply_catalog_constraints(context)
    full_prompt = _rodin_prompt(context)
    rodin_prompt = _rodin_api_prompt(context, full_prompt)
    if rodin_prompt != full_prompt:
        context["rodin_prompt_full"] = full_prompt
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
    attempt_results: list[dict[str, Any]] = []
    selected_attempt = 0

    first_attempt = _run_segmentation_attempt(
        context=context,
        rodin_task_uuid=rodin_task_uuid,
        rodin_files=rodin_files,
        job_dir=job_dir,
        progress=progress,
    )
    attempt_results.append(first_attempt)

    best_attempt = first_attempt
    best_score = _build_plan_failure_score(first_attempt["build_plan"])
    if _should_auto_recover_model(context, first_attempt["build_plan"]):
        for attempt_number in range(1, MAX_AUTO_MODEL_RECOVERY_ATTEMPTS + 1):
            progress(
                "Auto-simplifying model",
                86,
                "The first segmentation was too detailed, so KidSpark is trying one simpler model automatically.",
            )
            recovery_context = _automatic_model_recovery_context(context, first_attempt["build_plan"], attempt_number)
            recovery_dir = job_dir / f"auto_recovery_{attempt_number}"
            preview_progress = _scaled_progress(progress, 86, 94)
            recovered_preview = create_rodin_preview(recovery_context, recovery_dir / "model_preview", preview_progress)
            recovered_attempt = _run_segmentation_attempt(
                context=recovered_preview["context"],
                rodin_task_uuid=recovered_preview["rodin"]["task_uuid"],
                rodin_files=recovered_preview["rodin"]["files"],
                job_dir=recovery_dir,
                progress=_scaled_progress(progress, 94, 99),
            )
            recovered_attempt["auto_recovery_attempt"] = attempt_number
            attempt_results.append(recovered_attempt)
            recovered_score = _build_plan_failure_score(recovered_attempt["build_plan"])
            if recovered_score < best_score:
                best_attempt = recovered_attempt
                best_score = recovered_score
                selected_attempt = attempt_number
            if _build_plan_is_validated(recovered_attempt["build_plan"]):
                best_attempt = recovered_attempt
                selected_attempt = attempt_number
                break

    result = {
        "context": best_attempt["context"],
        "rodin": best_attempt["rodin"],
        "bang": best_attempt["bang"],
        "build_plan": best_attempt["build_plan"],
        "job_dir": str(job_dir),
        "auto_model_recovery": _auto_model_recovery_summary(attempt_results, selected_attempt),
    }
    result["build_plan"]["auto_model_recovery"] = result["auto_model_recovery"]
    (job_dir / "segments_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def _run_segmentation_attempt(
    *,
    context: dict[str, Any],
    rodin_task_uuid: str,
    rodin_files: list[str] | list[Path],
    job_dir: Path,
    progress: ProgressFn,
) -> dict[str, Any]:
    """Run one Bang + notebook/planner attempt for a specific Rodin model."""
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
    return {
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
    }


def _scaled_progress(progress: ProgressFn, percent_start: int, percent_end: int) -> ProgressFn:
    """Map a nested stage's 0-100 progress into the parent job range."""
    span = max(percent_end - percent_start, 1)

    def emit(stage: str, percent: int, message: str) -> None:
        mapped = percent_start + int(span * max(0, min(percent, 100)) / 100)
        progress(stage, mapped, message)

    return emit


def _build_plan_is_validated(build_plan: dict[str, Any]) -> bool:
    validated = build_plan.get("validated_planner") or {}
    return bool(validated.get("final_claim_valid"))


def _should_auto_recover_model(context: dict[str, Any], build_plan: dict[str, Any]) -> bool:
    constraints = context.get("build_constraints") or {}
    if str(context.get("inventory_mode") or constraints.get("inventory_mode") or "standard_kit") == "unlimited":
        return False
    validated = build_plan.get("validated_planner") or {}
    if not validated or validated.get("final_claim_valid"):
        return False
    status = str(validated.get("build_status") or "")
    if status == "NEEDS_SIMPLER_MODEL":
        return True
    if status == "INCOMPLETE":
        true_steps = int(validated.get("true_build_step_count") or 0)
        final_blocks = int(validated.get("final_block_count") or 0)
        return true_steps == 0 or final_blocks == 0
    return False


def _build_plan_failure_score(build_plan: dict[str, Any]) -> tuple[int, int, int, int]:
    """Lower scores are better; valid plans always win."""
    validated = build_plan.get("validated_planner") or {}
    viability = validated.get("segment_viability") or {}
    max_blocks = int(viability.get("max_validated_blocks") or 32)
    max_segments = int(viability.get("max_semantic_segments") or 5)
    block_count = int(validated.get("final_block_count") or 0)
    source_segments = int(viability.get("source_segment_count") or 0)
    physical_segments = int(viability.get("physical_segment_count") or 0)
    valid_penalty = 0 if validated.get("final_claim_valid") else 1
    return (
        valid_penalty,
        max(source_segments - max_segments, 0) + max(physical_segments - max_segments, 0),
        max(block_count - max_blocks, 0),
        block_count,
    )


def _auto_model_recovery_summary(attempts: list[dict[str, Any]], selected_attempt: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index, attempt in enumerate(attempts):
        build_plan = attempt.get("build_plan") or {}
        validated = build_plan.get("validated_planner") or {}
        viability = validated.get("segment_viability") or {}
        rows.append(
            {
                "attempt": index,
                "auto_recovery": index > 0,
                "rodin_task_uuid": (attempt.get("rodin") or {}).get("task_uuid"),
                "bang_task_uuid": (attempt.get("bang") or {}).get("task_uuid"),
                "build_status": validated.get("build_status"),
                "final_claim_valid": bool(validated.get("final_claim_valid")),
                "block_count": validated.get("final_block_count"),
                "source_segment_count": viability.get("source_segment_count"),
                "physical_segment_count": viability.get("physical_segment_count"),
                "reason": validated.get("reason"),
            }
        )
    return {
        "enabled": len(attempts) > 1,
        "max_attempts": MAX_AUTO_MODEL_RECOVERY_ATTEMPTS,
        "selected_attempt": selected_attempt,
        "attempts": rows,
        "note": (
            "KidSpark first tries local voxel-size tuning. If the segment budget still fails, "
            f"it regenerates up to {MAX_AUTO_MODEL_RECOVERY_ATTEMPTS} progressively simpler Rodin models "
            "before asking the teacher to intervene."
        ),
    }


def _automatic_model_recovery_context(
    context: dict[str, Any],
    build_plan: dict[str, Any],
    attempt_number: int,
) -> dict[str, Any]:
    """Create a stricter Rodin context after Bang/notebook validation fails."""
    recovered = apply_catalog_constraints(dict(context))
    recovered["teacher_requested_parts"] = list(context.get("parts") or [])
    validated = build_plan.get("validated_planner") or {}
    viability = validated.get("segment_viability") or {}
    constraints = dict(recovered.get("build_constraints") or {})
    current_max_blocks = int(viability.get("max_validated_blocks") or constraints.get("max_validated_blocks") or 32)
    current_max_segments = int(viability.get("max_semantic_segments") or constraints.get("max_semantic_segments") or 5)
    target_blocks = min(current_max_blocks, 28 if attempt_number == 1 else 24)
    target_segments = min(current_max_segments, 4 if attempt_number == 1 else 3)
    artifact = str(recovered.get("artifact_label") or recovered.get("artifact_family") or "classroom model")
    moving_parts = [
        dict(part)
        for part in recovered.get("parts", []) or []
        if str(part.get("movement", "static")).lower() != "static" and str(part.get("part_name", "")).strip()
    ]
    primary_moving = moving_parts[0] if moving_parts else {"part_name": "primary moving feature", "movement": "spinning"}
    coarse_static_parts = _coarse_static_parts_for_artifact(artifact)
    recovered["parts"] = [primary_moving] + coarse_static_parts[: max(target_segments - 1, 1)]
    required_parts = [str(part.get("part_name")) for part in recovered["parts"] if part.get("part_name")]
    constraints.update(
        {
            "inventory_mode": "standard_kit",
            "required_visible_parts": required_parts,
            "moving_parts": [str(primary_moving.get("part_name"))],
            "optional_decorative_features": [],
            "max_validated_blocks": target_blocks,
            "max_semantic_segments": target_segments,
            "max_moving_parts": 1,
            "minimum_surviving_segments": 2,
            "auto_recovery_attempt": attempt_number,
            "bang_segmentation_requirements": [
                f"Bang should see no more than {target_segments} large source groups.",
                "Only the primary moving part may be visually separated from the static body.",
                "All static details must be fused into broad 2x2-compatible surfaces.",
                "Do not create separate tail, cargo, window, trim, connector, ridge, or decorative micro-segments.",
                "Use a single connected static mass wherever possible so segmentation does not split tiny contact regions.",
            ],
        }
    )
    recovered["build_constraints"] = constraints
    recovered["buildability_budget"] = {
        "inventory_mode": "standard_kit",
        "max_validated_blocks": target_blocks,
        "max_semantic_segments": target_segments,
        "max_moving_parts": 1,
        "min_segment_survival_fraction": float(constraints.get("min_segment_survival_fraction") or 0.75),
        "minimum_surviving_segments": 2,
    }
    recovered["rodin_prompt"] = _strict_recovery_rodin_prompt(
        artifact,
        primary_moving,
        required_parts,
        target_blocks,
        target_segments,
        attempt_number,
    )
    return apply_catalog_constraints(recovered)


def _coarse_static_parts_for_artifact(artifact: str) -> list[dict[str, str]]:
    text = artifact.lower()
    if any(token in text for token in ["plane", "airplane", "vehicle", "delivery", "car", "truck"]):
        return [
            {"part_name": "merged body/fuselage", "movement": "static"},
            {"part_name": "one broad wing or support slab", "movement": "static"},
            {"part_name": "single simple base", "movement": "static"},
        ]
    if any(token in text for token in ["house", "bakery", "shop", "building"]):
        return [
            {"part_name": "single boxy building shell", "movement": "static"},
            {"part_name": "one broad roof slab", "movement": "static"},
            {"part_name": "single front counter/opening surface", "movement": "static"},
        ]
    if any(token in text for token in ["tree", "plant", "garden"]):
        return [
            {"part_name": "single trunk/body column", "movement": "static"},
            {"part_name": "one broad canopy/platform", "movement": "static"},
        ]
    return [
        {"part_name": "single main body/core", "movement": "static"},
        {"part_name": "one broad support/base region", "movement": "static"},
    ]


def _strict_recovery_rodin_prompt(
    artifact: str,
    primary_moving: dict[str, Any],
    required_parts: list[str],
    target_blocks: int,
    target_segments: int,
    attempt_number: int = 1,
) -> str:
    moving_name = str(primary_moving.get("part_name") or "primary moving feature")
    moving_action = str(primary_moving.get("movement") or "moving")
    strict_extra = (
        "Use one rectangular body block mass, one attached rectangular slab, and one small separated moving marker only. "
        "Avoid realistic airplane details; prioritize a validated simple block construction."
        if attempt_number > 1
        else ""
    )
    prompt = (
        f"Create a very simple chunky block-toy model of a {artifact}. "
        f"Use exactly {target_segments} or fewer large visible regions: {', '.join(required_parts)}. "
        f"The only separated moving region is {moving_name}, which should be {moving_action}. "
        "Merge every static detail into the broad body surfaces. "
        "No separate tail, cargo compartment, window, landing gear, wheel set, trim, ridges, holes, labels, connector stubs, or decorative micro-pieces. "
        "Use flat rectangular 2x2-compatible block masses with strong contact surfaces. "
        f"Target about 20 to {target_blocks} total blocks after voxelization. "
        "Make the silhouette compact, squat, and classroom-buildable. "
        f"{strict_extra}"
    )
    return " ".join(prompt.split())[:RODIN_PROMPT_LIMIT].rstrip(" ,.;") + "."


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
    if not provider_configured():
        raise RuntimeError("Vertex Gemini is not configured")

    job_dir.mkdir(parents=True, exist_ok=True)

    progress("Analyzing story and planning build context", 5, "Gemini is extracting the lesson target.")
    context = create_model_context(story_text, teacher_connection_intent, seed_context, job_dir)

    progress("Generating teacher lesson package", 15, "Gemini is drafting the teacher plan and activity guide.")
    lesson_package = _create_lesson_package(story_text, context)
    (job_dir / "lesson_package.json").write_text(json.dumps(lesson_package, indent=2), encoding="utf-8")

    progress("Submitting Rodin text-to-3D job", 25, "Creating the 3D reference model from the build target.")
    full_prompt = _rodin_prompt(context)
    rodin_prompt = _rodin_api_prompt(context, full_prompt)
    if rodin_prompt != full_prompt:
        context["rodin_prompt_full"] = full_prompt
        context["rodin_prompt"] = rodin_prompt
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


def _json_chat(system: str, user: str, max_tokens: int = 2200) -> dict[str, Any]:
    result = generate_json(
        system,
        user,
        temperature=0.35,
        max_output_tokens=max_tokens,
    )
    return dict(result)


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
  "build_constraints": {{
    "object_type_hint": string,
    "required_visible_parts": [string],
    "moving_parts": [string],
    "wheel_count": number,
    "symmetry": "auto|left_right|none",
    "inventory_mode": "standard_kit",
    "max_validated_blocks": 32,
    "max_semantic_segments": 5,
    "max_moving_parts": 1,
    "optional_decorative_features": [string],
    "bang_segmentation_requirements": [string]
  }},
  "rodin_prompt": string
}}

For "rodin_prompt", write only a physical object description for text-to-3D.
It must describe the build artifact's shape and visible parts. Do not write a
question, lesson objective, student prompt, or explanation.
Make the object simple, chunky, classroom-buildable, and block-toy-like.
Avoid thin fins, tiny details, smooth tapers, dense curves, and features smaller
than a 2x2 block footprint. Moving parts must be visually separate enough for
Bang segmentation.
For standard-kit classroom validation, target about 30 physical blocks, four to
five large semantic parts, and one primary moving feature. Prefer one simple
buildable object over a detailed miniature scene.
"""
    data = _json_chat(system, user)
    data.setdefault("grade_band", "1st Grade")
    data.setdefault("duration_minutes", 35)
    data["parts"] = _normalize_part_movements(data.get("parts", []))
    data.setdefault("build_constraints", _default_build_constraints(data))
    data["standards_anchor"] = STANDARDS
    return apply_catalog_constraints(data)


def _create_lesson_package(story_text: str, context: dict[str, Any]) -> dict[str, Any]:
    system = (
        "You are KidSpark AI. Return only valid JSON. Write detailed, classroom-ready "
        "teacher and student materials matching the Kid Spark Invent an Airplane "
        "structure: Overview, Learning Objectives, Curriculum Connections, Materials, "
        "Vocabulary, UDL, Anticipatory Set, Step 01 Read, Step 02 Learn & Explore, "
        "Step 03 Invent, Closure, Real-World Connection, Standards. For every teacher "
        "lesson phase, provide four or five distinct, actionable content blocks. Include "
        "teacher language, student prompts, a check for understanding, a learner support, "
        "and a transition. Keep projected slide language brief and child-friendly."
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
    "overview": [string, string, string, string],
    "learning_objectives": [string],
    "curriculum_connections": [string],
    "activity_details": {{"time": string, "grade": string, "grouping": string}},
    "materials": [string],
    "vocabulary": [{{"term": string, "definition": string}}],
    "plan_for_all_learners": [string, string, string, string],
    "anticipatory_set": [string, string, string, string, string],
    "step_01_read": [string, string, string, string, string],
    "step_02_learn_explore": [string, string, string, string, string],
    "step_03_invent": [string, string, string, string, string],
    "closure_reflection": [string, string, string, string],
    "real_world_connection": [string, string, string, string],
    "standards": [string]
  }},
  "student_activity_guide": {{
    "title": string,
    "read": string,
    "learn_explore": string,
    "invent": string,
    "real_world_connection": string,
    "reflection_questions": [string]
  }},
  "slide_companion": {{
    "storytime_prompts": [string, string, string, string],
    "story_problem_prompts": [string, string, string, string],
    "big_idea_prompts": [string, string, string, string],
    "vocabulary_prompts": [string, string, string, string],
    "sound_awareness_prompts": [string, string, string, string],
    "parts_and_functions_prompts": [string, string, string, string],
    "planning_prompts": [string, string, string, string],
    "reflection_prompts": [string, string, string, string]
  }}
}}
"""
    return _json_chat(system, user, max_tokens=6500)


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
    context.setdefault("build_constraints", _default_build_constraints(context))
    if not context.get("rodin_prompt"):
        context["rodin_prompt"] = _rodin_prompt(context)
    return apply_catalog_constraints(context)


def _rodin_prompt(context: dict[str, Any]) -> str:
    context = apply_catalog_constraints(context)
    targets = semantic_segment_targets(context)
    parts = ", ".join(
        f"{part.get('part_name', '')} ({part.get('movement', 'static')})"
        for part in context.get("parts", [])
    )
    artifact = context.get("artifact_label", "vehicle")
    candidate = str(context.get("rodin_prompt") or "").strip()
    movement_guidance = (
        f" Teacher-facing part intent: {parts}. "
        "Only the primary moving feature should be separated from the static body for Bang segmentation."
    )
    catalog_guidance = (
        " Use simple chunky block-toy geometry with broad 2x2-compatible features. "
        "Avoid thin fins, tiny details, smooth tapers, dense curves, unsupported decorative parts, "
        "and features smaller than a 2x2 block footprint. "
        "If wheels are needed, show clear left/right anchor locations under the body without wrapping body geometry around them. "
        f"For standard-kit validation, use only these large semantic regions: {', '.join(targets)}. "
        "Merge cargo, windows, tail, trim, classroom labels, and other static details into the nearest large body region; "
        "do not create separate connector, contact, or decorative segments. Keep the model compact: about 20 to 28 physical blocks, "
        "two to four semantic parts, one primary moving feature, and large separated surfaces that can survive coarse voxelization."
    )
    if candidate and "?" not in candidate:
        teacher_note = candidate[:360].rstrip(" .")
        return (
            f"Simple chunky block-toy model of a {artifact}. "
            f"Teacher visual note: {teacher_note}. "
            f"{movement_guidance} {catalog_guidance}"
        )
    return (
        f"A simple, child-friendly toy model of a {artifact}, "
        f"with teacher-facing part intent: {parts}. "
        "Make only the primary moving part visually distinct from static structure so Bang segmentation can separate it. "
        "Bright classroom block-toy style, chunky plastic, simple geometry, stable shape, "
        "suitable for conversion into block-building instructions. "
        + catalog_guidance
    )


def _rodin_api_prompt(context: dict[str, Any], prompt: str) -> str:
    prompt = " ".join(str(prompt or "").split())
    if len(prompt) <= RODIN_PROMPT_LIMIT:
        return prompt

    context = apply_catalog_constraints(context)
    artifact = context.get("artifact_label") or context.get("artifact_family") or "simple classroom vehicle"
    parts = context.get("parts") or []
    targets = semantic_segment_targets(context)
    moving_parts = [
        f"{part.get('part_name')} {part.get('movement')}"
        for part in parts
        if str(part.get("movement", "static")).lower() != "static"
    ][:1]
    static_parts = [
        str(part.get("part_name", "")).strip()
        for part in parts
        if str(part.get("movement", "static")).lower() == "static" and str(part.get("part_name", "")).strip()
    ][:4]

    compact = (
        f"Simple chunky block-toy model of a {artifact}. "
        f"Use only these large semantic regions: {', '.join(targets) or 'body, moving feature, support parts'}. "
        f"Primary moving part: {', '.join(moving_parts) or 'one clear moving feature'}. "
        f"Merge static classroom details ({', '.join(static_parts) or 'body details'}) into those large regions. "
        "Use broad 2x2-compatible plastic block geometry, flat stable surfaces, and readable proportions. "
        "Avoid thin fins, tiny details, smooth tapers, dense curves, decorative clutter, and unsupported parts. "
        "Keep it compact for a standard classroom kit: about 20-28 blocks, 2-4 semantic parts, one moving feature. "
        "Make moving and static regions visually distinct for segmentation."
    )
    compact = " ".join(compact.split())
    return compact[:RODIN_PROMPT_LIMIT].rstrip(" ,.;") + "."


def _create_build_plan(context: dict[str, Any], obj_path: Path | None, job_dir: Path) -> dict[str, Any]:
    context = apply_catalog_constraints(context)
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
    notebook_outputs = _generate_notebook_outputs_with_auto_tuning(
        context,
        obj_path,
        job_dir,
        segments,
    )
    blocker = _validated_planner_blocker(context, notebook_outputs, segments)
    if blocker:
        validated = blocker
    else:
        validated = run_validated_planner(
            context=context,
            obj_path=obj_path,
            segment_rows=segments,
            job_dir=job_dir,
        )
        validated = _promote_compact_notebook_physicalization(context, notebook_outputs, validated)
    notebook_outputs = _merge_validated_outputs(notebook_outputs, validated)
    notebook_validation = notebook_outputs.get("validation", {})
    build_plan = {
        "artifact_label": context.get("artifact_label", "Build artifact"),
        "source_obj": str(obj_path) if obj_path else None,
        "build_status": validated.get("build_status"),
        "final_claim_valid": bool(validated.get("final_claim_valid")),
        "inventory_mode": validated.get("inventory_mode"),
        "inventory_feasibility": validated.get("inventory_feasibility"),
        "shortages": validated.get("shortages", {}),
        "run_id": validated.get("run_id"),
        "artifacts_dir": validated.get("artifacts_dir"),
        "build_instructions_html": validated.get("build_instructions_html"),
        "true_build_step_count": validated.get("true_build_step_count", 0),
        "validated_planner": validated,
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


def _promote_compact_notebook_physicalization(
    context: dict[str, Any],
    notebook_outputs: dict[str, Any],
    validated: dict[str, Any],
) -> dict[str, Any]:
    """Allow compact notebook/CSP outputs to proceed when strict validation stalls.

    The deterministic planner remains preferred. This fallback only unlocks the
    teacher flow when the notebook output already satisfies the same high-level
    classroom constraints: connected, under block budget, under semantic segment
    budget, and backed by generated instruction images.
    """
    if validated.get("final_claim_valid"):
        return validated
    constraints = context.get("build_constraints", {}) or {}
    budget = context.get("buildability_budget", {}) or {}
    inventory_mode = str(context.get("inventory_mode") or constraints.get("inventory_mode") or "standard_kit")
    if inventory_mode == "unlimited":
        return validated

    max_blocks = int(budget.get("max_validated_blocks") or constraints.get("max_validated_blocks") or 32)
    max_segments = int(budget.get("max_semantic_segments") or constraints.get("max_semantic_segments") or 5)
    block_count = int(notebook_outputs.get("block_count") or 0)
    segment_count = int(notebook_outputs.get("segment_count") or 0)
    instruction_steps = notebook_outputs.get("instruction_steps") if isinstance(notebook_outputs.get("instruction_steps"), list) else []
    validation = notebook_outputs.get("validation") if isinstance(notebook_outputs.get("validation"), dict) else {}
    connected = bool(validation.get("is_fully_connected"))
    component_count = int(validation.get("component_count") or 0)
    connector_candidates = int(validation.get("connector_candidate_count") or 0)
    moving_count = sum(
        1
        for part in context.get("parts", []) or []
        if str(part.get("movement", "static")).lower() != "static"
    )
    connected_by_reviewed_motion = component_count <= 2 and connector_candidates > 0 and moving_count > 0
    if (
        not (connected or connected_by_reviewed_motion)
        or not instruction_steps
        or block_count <= 0
        or block_count > max_blocks
        or segment_count > max_segments
    ):
        return validated

    promoted = dict(validated)
    promoted.update(
        {
            "build_status": "NOTEBOOK_CSP_REVIEW_READY",
            "final_claim_valid": True,
            "validation_tier": "notebook_csp_budget_checked",
            "reason": (
                "The strict validated planner did not finish, but the notebook/CSP physicalization is classroom-sized, "
                f"uses {block_count} blocks within the {max_blocks}-block budget, and stays within the "
                f"{max_segments}-segment classroom limit. The moving feature is handled as a teacher-reviewed connector step."
            ),
            "recommendation": (
                "Proceed with teacher review using the notebook-generated build images and instruction steps. "
                "Keep the deterministic planner status visible for engineering follow-up."
            ),
            "final_block_count": block_count,
            "true_build_step_count": len(instruction_steps),
            "instruction_steps": instruction_steps,
            "inventory_rows": notebook_outputs.get("block_inventory", []),
            "notebook_fallback": {
                "enabled": True,
                "original_build_status": validated.get("build_status"),
                "original_reason": validated.get("reason"),
                "block_count": block_count,
                "segment_count": segment_count,
                "component_count": component_count,
                "connector_candidate_count": connector_candidates,
                "connected_by_reviewed_motion": connected_by_reviewed_motion,
                "max_blocks": max_blocks,
                "max_segments": max_segments,
            },
        }
    )
    return promoted


def _generate_notebook_outputs_with_auto_tuning(
    context: dict[str, Any],
    obj_path: Path | None,
    job_dir: Path,
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Try cheap local physicalization variants before asking for a new OBJ."""
    constraints = context.get("build_constraints", {}) or {}
    max_blocks = int(constraints.get("max_validated_blocks") or 32)
    max_segments = int(constraints.get("max_semantic_segments") or 5)
    attempts: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    best_score: tuple[int, int, int] | None = None
    voxel_sizes = [16, 14, 12]

    for voxel_size in voxel_sizes:
        notebook_outputs = generate_notebook_outputs(
            obj_path,
            job_dir,
            segment_rows=segments,
            artifact_label=context.get("artifact_label", "BrickSmart model"),
            movement_intents=context.get("parts", []),
            teacher_connection_intent=context.get("teacher_connection_intent", ""),
            voxel_size=voxel_size,
            max_semantic_segments=max_segments,
        )
        block_count = int(notebook_outputs.get("block_count") or 0)
        physical_segments = int(notebook_outputs.get("segment_count") or 0)
        preservation_fraction = float(notebook_outputs.get("segment_preservation_fraction") or 1.0)
        score = (
            max(block_count - max_blocks, 0),
            max(physical_segments - max_segments, 0),
            -int(round(preservation_fraction * 1000)),
        )
        attempts.append(
            {
                "voxel_size": voxel_size,
                "block_count": block_count,
                "physical_segment_count": physical_segments,
                "preservation_fraction": round(preservation_fraction, 4),
                "passes_local_budget": block_count <= max_blocks and physical_segments <= max_segments,
            }
        )
        if best_score is None or score < best_score:
            best = notebook_outputs
            best_score = score
        if block_count <= max_blocks and physical_segments <= max_segments:
            best = notebook_outputs
            break

    selected = dict(best or {})
    selected["auto_tuning"] = {
        "enabled": True,
        "attempts": attempts,
        "selected_voxel_size": selected.get("voxel_size"),
        "max_validated_blocks": max_blocks,
        "max_semantic_segments": max_segments,
        "note": (
            "KidSpark tried local notebook voxel-size variants after Bang before deciding "
            "whether a new Rodin model is required."
        ),
    }
    return selected


def _default_build_constraints(context: dict[str, Any]) -> dict[str, Any]:
    parts = context.get("parts", [])
    moving = [part.get("part_name", "") for part in parts if part.get("movement") != "static"]
    wheels = [part for part in parts if part.get("movement") == "rolling" or "wheel" in str(part.get("part_name", "")).lower()]
    constraints = {
        "object_type_hint": context.get("artifact_label") or context.get("artifact_family") or "kidspark_model",
        "moving_parts": [name for name in moving if name],
        "teacher_requested_static_parts": [part.get("part_name", "") for part in parts if part.get("movement") == "static"],
        "wheel_count": len(wheels) if wheels else 0,
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
            "Do not create separate connector/contact/decorative regions for standard-kit validation.",
        ],
    }
    context_for_targets = dict(context)
    context_for_targets["build_constraints"] = constraints
    constraints["required_visible_parts"] = semantic_segment_targets(context_for_targets)
    constraints["semantic_segment_targets"] = constraints["required_visible_parts"]
    return constraints


def _validated_planner_blocker(
    context: dict[str, Any],
    notebook_outputs: dict[str, Any],
    segment_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    constraints = context.get("build_constraints", {}) or {}
    inventory_mode = str(context.get("inventory_mode") or constraints.get("inventory_mode") or "standard_kit")
    if inventory_mode == "unlimited":
        return None

    budget = context.get("buildability_budget", {}) or {}
    max_blocks = int(budget.get("max_validated_blocks") or constraints.get("max_validated_blocks") or 32)
    max_segments = int(budget.get("max_semantic_segments") or constraints.get("max_semantic_segments") or 5)
    min_fraction = float(budget.get("min_segment_survival_fraction") or constraints.get("min_segment_survival_fraction") or 0.75)
    minimum_surviving = int(budget.get("minimum_surviving_segments") or constraints.get("minimum_surviving_segments") or 2)

    blocks = notebook_outputs.get("blocks") if isinstance(notebook_outputs.get("blocks"), list) else []
    segment_rows = segment_rows or []
    segment_row_ids = {
        str(row.get("segment_id"))
        for row in segment_rows
        if row.get("segment_id") not in (None, "")
    }
    segment_row_count = len(segment_row_ids) or len(segment_rows)

    block_count = int(notebook_outputs.get("block_count") or len(blocks) or 0)
    raw_source_segments = max(int(notebook_outputs.get("source_segment_count") or 0), segment_row_count)
    physical_segments = int(notebook_outputs.get("segment_count") or 0)
    surviving_segments = int(notebook_outputs.get("surviving_segment_count") or physical_segments or 0)
    preservation_fraction = float(notebook_outputs.get("segment_preservation_fraction") or 1.0)
    semantic_survival = notebook_outputs.get("semantic_target_survival") or {}
    semantic_target_count = int(semantic_survival.get("semantic_target_count") or 0)
    semantic_surviving_count = int(
        semantic_survival.get("surviving_semantic_target_count") or 0
    )
    semantic_preservation_fraction = float(
        semantic_survival.get("preservation_fraction") or 0.0
    )
    coarse_grouped = bool(segment_rows) and all(
        str(row.get("source_segment_grouping") or "") == "coarse_validated_region"
        for row in segment_rows
    )
    validation_segment_count = segment_row_count if coarse_grouped else raw_source_segments
    source_segments = validation_segment_count
    moving_count = sum(
        1
        for part in context.get("parts", []) or []
        if str(part.get("movement", "static")).lower() != "static"
    )
    max_moving = int(budget.get("max_moving_parts") or constraints.get("max_moving_parts") or 1)
    hard_reasons: list[str] = []

    if block_count > max_blocks:
        hard_reasons.append(f"Notebook approximation needs {block_count} blocks; standard-kit preview budget is {max_blocks}.")
    if validation_segment_count > max_segments:
        hard_reasons.append(f"Bang produced {validation_segment_count} validated semantic segment groups; standard-kit validation target is {max_segments} or fewer.")
    if physical_segments > max_segments:
        hard_reasons.append(f"Notebook physicalization has {physical_segments} color-coded segments; validated classroom builds should have {max_segments} or fewer.")
    if moving_count > max_moving:
        hard_reasons.append(f"The model asks for {moving_count} moving parts; standard-kit validation supports {max_moving} primary moving part.")
    if surviving_segments < minimum_surviving and raw_source_segments > 1:
        hard_reasons.append(f"Voxel cleanup preserved only {surviving_segments} segment(s); at least {minimum_surviving} are needed for a teacher-checkable build.")
    if not coarse_grouped and raw_source_segments > 1 and preservation_fraction < min_fraction:
        hard_reasons.append(f"Voxel cleanup preserved {preservation_fraction:.0%} of segments; target is {min_fraction:.0%} or better.")
    if coarse_grouped and semantic_target_count:
        required_semantic_survivors = min(minimum_surviving, semantic_target_count)
        if semantic_surviving_count < required_semantic_survivors:
            hard_reasons.append(
                f"Semantic grouping preserved only {semantic_surviving_count} teacher-approved region(s); "
                f"at least {required_semantic_survivors} are needed."
            )
        if semantic_preservation_fraction < min_fraction:
            hard_reasons.append(
                f"Semantic grouping preserved {semantic_preservation_fraction:.0%} of teacher-approved regions; "
                f"target is {min_fraction:.0%} or better."
            )

    if not hard_reasons:
        return None

    reasons = hard_reasons
    recommendation = (
        "Simplify/regenerate the model with fewer visible parts, larger separated 2x2-compatible surfaces, "
        "or explicitly switch to an unlimited reference preview."
    )
    return {
        "enabled": True,
        "build_status": "NEEDS_SIMPLER_MODEL",
        "final_claim_valid": False,
        "inventory_mode": inventory_mode,
        "reason": " ".join(reasons),
        "recommendation": recommendation,
        "shortages": {},
        "instruction_steps": [],
        "inventory_rows": [],
        "final_block_count": block_count,
        "true_build_step_count": 0,
        "segment_viability": {
            "source_segment_count": source_segments,
            "raw_source_segment_count": raw_source_segments,
            "confirmed_segment_count": segment_row_count,
            "physical_segment_count": physical_segments,
            "surviving_segment_count": surviving_segments,
            "preservation_fraction": preservation_fraction,
            "semantic_target_count": semantic_target_count,
            "semantic_surviving_count": semantic_surviving_count,
            "semantic_preservation_fraction": semantic_preservation_fraction,
            "recommended_next_voxel_size": notebook_outputs.get("recommended_next_voxel_size"),
            "auto_tuning": notebook_outputs.get("auto_tuning"),
            "coarse_segment_grouping": coarse_grouped,
            "max_validated_blocks": max_blocks,
            "max_semantic_segments": max_segments,
            "max_moving_parts": max_moving,
        },
    }


def _merge_validated_outputs(notebook_outputs: dict[str, Any], validated: dict[str, Any]) -> dict[str, Any]:
    merged = dict(notebook_outputs or {})
    validation = dict(merged.get("validation") or {})
    validation.update(
        {
            "validated_planner_enabled": bool(validated.get("enabled")),
            "final_claim_valid": bool(validated.get("final_claim_valid")),
            "build_status": validated.get("build_status"),
            "inventory_mode": validated.get("inventory_mode"),
            "inventory_feasibility": validated.get("inventory_feasibility"),
            "shortages": validated.get("shortages", {}),
            "build_instructions_html": validated.get("build_instructions_html"),
            "true_build_step_count": validated.get("true_build_step_count", 0),
        }
    )
    merged["validation"] = validation
    merged["validated_planner"] = validated
    merged["build_status"] = validated.get("build_status")
    merged["final_claim_valid"] = bool(validated.get("final_claim_valid"))
    merged["inventory_mode"] = validated.get("inventory_mode")
    merged["inventory_feasibility"] = validated.get("inventory_feasibility")
    merged["shortages"] = validated.get("shortages", {})
    merged["run_id"] = validated.get("run_id")
    merged["artifacts_dir"] = validated.get("artifacts_dir")
    merged["build_instructions_html"] = validated.get("build_instructions_html")
    merged["true_build_step_count"] = validated.get("true_build_step_count", 0)
    if validated.get("inventory_rows"):
        merged["block_inventory"] = validated["inventory_rows"]
    if validated.get("instruction_steps") is not None:
        merged["instruction_steps"] = validated.get("instruction_steps", [])
    if validated.get("final_block_count") is not None:
        merged["validated_final_block_count"] = validated.get("final_block_count")
        if validated.get("final_claim_valid"):
            merged["block_count"] = validated.get("final_block_count", merged.get("block_count", 0))
    return merged


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
    obj_segments: list[dict[str, Any]] = []
    if obj_path and obj_path.exists():
        try:
            vertices, loaded_segments = load_obj_segments(obj_path)
            obj_segments = _segment_geometry_descriptors(vertices, loaded_segments)
        except (OSError, ValueError):
            obj_segments = []
    obj_names = [str(item["name"]) for item in obj_segments]
    parts = context.get("parts") or []
    if not parts:
        parts = [{"part_name": context.get("artifact_label", "body"), "movement": "static", "function": "main structure"}]

    constraints = context.get("build_constraints") or {}
    inventory_mode = str(context.get("inventory_mode") or constraints.get("inventory_mode") or "standard_kit")
    if inventory_mode != "unlimited":
        targets = semantic_segment_targets(context)
        max_segments = int(constraints.get("max_semantic_segments") or 4)
        if targets:
            rows = []
            source_groups = _distribute_source_segments(obj_segments, targets)
            for idx, target in enumerate(targets[:max_segments]):
                movement = _movement_for_segment_target(target, parts)
                source_group = source_groups[idx] if idx < len(source_groups) else []
                rows.append(
                    {
                        "segment_id": idx + 1,
                        "source_name": ", ".join(str(item["name"]) for item in source_group)
                        if source_group
                        else f"semantic_region_{idx + 1}",
                        "source_segment_ids": [int(item["segment_id"]) for item in source_group],
                        "semantic_group_id": f"semantic_region_{idx + 1}",
                        "label": _slug(_semantic_label(target)),
                        "movement": movement,
                        "function": target,
                        "teacher_confirmed": True,
                        "source_segment_grouping": "coarse_validated_region",
                    }
                )
            return rows

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


def _distribute_source_segments(
    source_segments: list[dict[str, Any]],
    targets: list[str],
) -> list[list[dict[str, Any]]]:
    """Map raw Bang groups into teacher-approved semantic targets.

    Bang often emits generic names such as ``root.0``. Meaningful names are
    matched first; otherwise deterministic geometry roles identify a broad
    support pair, a compact peripheral moving pair, and the central static
    mass. Remaining fragments merge into the nearest assigned static group.
    """
    groups: list[list[dict[str, Any]]] = [[] for _ in targets]
    if not targets:
        return groups

    moving_terms = ("propeller", "rotor", "fan", "wheel", "axle", "hinge", "spinner")
    broad_terms = ("wing", "support", "slab", "platform", "canopy", "base")
    body_terms = ("body", "fuselage", "core", "shell", "trunk", "main")
    static_default = next(
        (
            index
            for index, target in enumerate(targets)
            if not any(term in target.lower() for term in moving_terms)
        ),
        0,
    )
    assigned: set[int] = set()
    for source in source_segments:
        name = str(source.get("name") or "").lower()
        if re.fullmatch(r"(?:root|mesh|object|group)[._-]?\d+", name):
            continue
        target_index = None
        for index, target in enumerate(targets):
            target_text = target.lower()
            significant = [
                token
                for token in _slug(target_text).split("_")
                if len(token) > 3
                and token
                not in {"single", "main", "with", "details", "merged", "broad", "feature", "separated", "moving"}
            ]
            if any(token in name for token in significant):
                target_index = index
                break
        if target_index is None and any(term in name for term in moving_terms):
            target_index = next(
                (index for index, target in enumerate(targets) if any(term in target.lower() for term in moving_terms)),
                static_default,
            )
        if target_index is not None:
            groups[target_index].append(source)
            assigned.add(int(source["segment_id"]))

    def available() -> list[dict[str, Any]]:
        return [source for source in source_segments if int(source["segment_id"]) not in assigned]

    broad_indexes = [
        index for index, target in enumerate(targets) if any(term in target.lower() for term in broad_terms)
    ]
    for target_index in broad_indexes:
        if groups[target_index]:
            continue
        candidates = available()
        selected = _best_geometry_pair(candidates, role="broad")
        if not selected and candidates:
            selected = [max(candidates, key=_broad_segment_score)]
        for source in selected:
            groups[target_index].append(source)
            assigned.add(int(source["segment_id"]))

    moving_indexes = [
        index for index, target in enumerate(targets) if any(term in target.lower() for term in moving_terms)
    ]
    for target_index in moving_indexes:
        if groups[target_index]:
            continue
        candidates = available()
        selected = _best_geometry_pair(candidates, role="moving")
        if not selected and candidates:
            selected = [max(candidates, key=_moving_segment_score)]
        for source in selected:
            groups[target_index].append(source)
            assigned.add(int(source["segment_id"]))

    body_index = next(
        (index for index, target in enumerate(targets) if any(term in target.lower() for term in body_terms)),
        static_default,
    )
    remaining = available()
    if remaining and not groups[body_index]:
        body_seed = max(remaining, key=lambda source: (int(source.get("vertex_count") or 0), float(source.get("bbox_volume") or 0.0)))
        groups[body_index].append(body_seed)
        assigned.add(int(body_seed["segment_id"]))

    static_indexes = [
        index for index, target in enumerate(targets) if not any(term in target.lower() for term in moving_terms)
    ] or [static_default]
    for source in available():
        populated = [index for index in static_indexes if groups[index]]
        target_index = min(
            populated or [static_default],
            key=lambda index: _centroid_distance(source, groups[index]),
        )
        groups[target_index].append(source)
        assigned.add(int(source["segment_id"]))
    return groups


def _segment_geometry_descriptors(vertices: list[Any], segments: list[Any]) -> list[dict[str, Any]]:
    descriptors: list[dict[str, Any]] = []
    all_points = [tuple(float(value) for value in vertex[:3]) for vertex in vertices]
    if all_points:
        global_centroid = tuple(sum(point[axis] for point in all_points) / len(all_points) for axis in range(3))
    else:
        global_centroid = (0.0, 0.0, 0.0)
    for segment in segments:
        indices = sorted({int(index) for face in segment.faces for index in face})
        points = [all_points[index] for index in indices if 0 <= index < len(all_points)]
        if points:
            lower = tuple(min(point[axis] for point in points) for axis in range(3))
            upper = tuple(max(point[axis] for point in points) for axis in range(3))
            extents = tuple(max(upper[axis] - lower[axis], 0.0) for axis in range(3))
            centroid = tuple(sum(point[axis] for point in points) / len(points) for axis in range(3))
        else:
            extents = (0.0, 0.0, 0.0)
            centroid = global_centroid
        descriptors.append(
            {
                "segment_id": int(segment.segment_id),
                "name": str(segment.name),
                "vertex_count": len(indices),
                "face_count": len(segment.faces),
                "centroid": centroid,
                "global_centroid": global_centroid,
                "extents": extents,
                "bbox_volume": float(extents[0] * extents[1] * extents[2]),
            }
        )
    return descriptors


def _broad_segment_score(source: dict[str, Any]) -> tuple[float, int]:
    extents = sorted((float(value) for value in source.get("extents", (0.0, 0.0, 0.0))), reverse=True)
    broadness = (extents[0] * extents[1]) / max(extents[2], 1e-6)
    return broadness, int(source.get("vertex_count") or 0)


def _moving_segment_score(source: dict[str, Any]) -> tuple[float, float]:
    centroid = source.get("centroid") or (0.0, 0.0, 0.0)
    global_centroid = source.get("global_centroid") or (0.0, 0.0, 0.0)
    distance = math.sqrt(sum((float(centroid[index]) - float(global_centroid[index])) ** 2 for index in range(3)))
    return distance, -float(source.get("vertex_count") or 0)


def _best_geometry_pair(candidates: list[dict[str, Any]], *, role: str) -> list[dict[str, Any]]:
    if len(candidates) < 2:
        return []
    best_pair: tuple[dict[str, Any], dict[str, Any]] | None = None
    best_score: float | None = None
    for left, right in combinations(candidates, 2):
        left_count = max(float(left.get("vertex_count") or 0), 1.0)
        right_count = max(float(right.get("vertex_count") or 0), 1.0)
        size_similarity = min(left_count, right_count) / max(left_count, right_count)
        left_extents = tuple(float(value) for value in left.get("extents", (0.0, 0.0, 0.0)))
        right_extents = tuple(float(value) for value in right.get("extents", (0.0, 0.0, 0.0)))
        extent_similarity = sum(
            min(left_extents[index], right_extents[index]) / max(left_extents[index], right_extents[index], 1e-6)
            for index in range(3)
        ) / 3.0
        left_centroid = tuple(float(value) for value in left.get("centroid", (0.0, 0.0, 0.0)))
        right_centroid = tuple(float(value) for value in right.get("centroid", (0.0, 0.0, 0.0)))
        center = tuple(float(value) for value in left.get("global_centroid", (0.0, 0.0, 0.0)))
        mirror_quality = max(
            1.0 / (1.0 + abs((left_centroid[axis] + right_centroid[axis]) / 2.0 - center[axis]) * 8.0
                 + sum(abs(left_centroid[other] - right_centroid[other]) for other in range(3) if other != axis) * 4.0)
            for axis in range(3)
        )
        if role == "broad":
            role_score = sum(_broad_segment_score(source)[0] for source in (left, right))
        else:
            distance = sum(_moving_segment_score(source)[0] for source in (left, right))
            compactness = 1.0 / (1.0 + (left_count + right_count) / 1000.0)
            role_score = distance + compactness
        score = (size_similarity * 2.0) + extent_similarity + (mirror_quality * 3.0) + role_score
        if best_score is None or score > best_score:
            best_pair = (left, right)
            best_score = score
    return list(best_pair) if best_pair else []


def _centroid_distance(source: dict[str, Any], group: list[dict[str, Any]]) -> float:
    source_centroid = tuple(float(value) for value in source.get("centroid", (0.0, 0.0, 0.0)))
    if not group:
        return float("inf")
    group_centroid = tuple(
        sum(float(item.get("centroid", (0.0, 0.0, 0.0))[axis]) for item in group) / len(group)
        for axis in range(3)
    )
    return math.sqrt(sum((source_centroid[axis] - group_centroid[axis]) ** 2 for axis in range(3)))


def _distribute_source_names(obj_names: list[str], group_count: int) -> list[list[str]]:
    if group_count <= 0:
        return []
    groups: list[list[str]] = [[] for _ in range(group_count)]
    if not obj_names:
        return groups

    moving_terms = ("propeller", "rotor", "fan", "wheel", "axle", "hinge")
    for name in obj_names:
        lower = name.lower()
        if any(term in lower for term in moving_terms):
            groups[0].append(name)
            continue
        if group_count > 2 and any(term in lower for term in ("wing", "support", "slab")):
            groups[-1].append(name)
            continue
        target_index = 1 if group_count > 1 else 0
        groups[target_index].append(name)
    return groups


def _semantic_label(target: str) -> str:
    lower = target.lower()
    if any(term in lower for term in ("propeller", "rotor", "fan")):
        return "propeller"
    if "wheel" in lower or "landing" in lower:
        return "wheel_anchor"
    if "wing" in lower or "support slab" in lower:
        return "wing_slab"
    if any(term in lower for term in ("body", "fuselage", "core", "shell", "trunk")):
        return "body"
    return target


def _movement_for_segment_target(target: str, parts: list[dict[str, Any]]) -> str:
    lower = target.lower()
    for part in parts:
        name = str(part.get("part_name", "")).lower()
        movement = str(part.get("movement", "static")).lower()
        if name and name in lower and movement != "static":
            return movement
    if any(term in lower for term in ("propeller", "rotor", "fan")):
        return "spinning"
    if "wheel" in lower:
        return "rolling"
    if "hinge" in lower or "pivot" in lower:
        return "pivoting"
    return "static"


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


def _content_blocks(value: Any) -> list[str]:
    """Normalize old single-string packages and newer structured content blocks."""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        blocks = []
        for label, item in value.items():
            for text in _content_blocks(item):
                blocks.append(f"**{str(label).replace('_', ' ').title()}:** {text}")
        return blocks
    if isinstance(value, (list, tuple)):
        blocks = []
        for item in value:
            blocks.extend(_content_blocks(item))
        return blocks
    return []


def _expanded_blocks(value: Any, fallbacks: list[str], minimum: int = 4) -> list[str]:
    blocks = _content_blocks(value)
    seen = {re.sub(r"\W+", " ", block.lower()).strip() for block in blocks}
    for fallback in fallbacks:
        normalized = re.sub(r"\W+", " ", fallback.lower()).strip()
        if normalized not in seen:
            blocks.append(fallback)
            seen.add(normalized)
        if len(blocks) >= minimum:
            break
    return blocks[: max(minimum, 5)]


def _markdown_blocks(blocks: list[str]) -> list[str]:
    lines: list[str] = []
    for block in blocks:
        lines.extend([block, ""])
    return lines


def _lesson_plan_markdown(
    lesson_package: dict[str, Any],
    build_plan: dict[str, Any],
    context: dict[str, Any],
) -> str:
    teacher = lesson_package.get("teacher_plan", {})
    notebook = build_plan.get("notebook_outputs", {})
    parts = context.get("parts", [])
    vocabulary = teacher.get("vocabulary", context.get("vocabulary", []))
    artifact = context.get("artifact_label", build_plan.get("artifact_label", "BrickSmart model"))
    theme = context.get("theme", "perseverance, collaboration, and learning from testing")
    moving_parts = [part.get("part_name", "moving part") for part in parts if part.get("movement") != "static"]
    moving_label = ", ".join(moving_parts) or "the teacher-selected moving part"
    overview_blocks = _expanded_blocks(teacher.get("overview"), [
        f"**Story-to-build connection:** Students use the events and problem in the story as a reason to design a {artifact}. The build gives them a concrete way to retell what the character needed and explain how an invention can help.",
        f"**Learning arc:** The lesson moves from listening and noticing, to exploring parts and functions, to planning, building, testing, and sharing. Each phase returns to the central theme of {theme}.",
        f"**Engineering focus:** Students consider how shape, stability, and movement affect function. They will pay special attention to {moving_label}, while keeping the rest of the model sturdy enough for classroom testing.",
        "**Literacy and SEL integration:** Oral language, vocabulary, sound awareness, partner talk, and evidence-based explanations are woven into the engineering work. Students practice asking for help, taking turns, and treating revision as part of learning.",
        "**Teacher role:** Model curiosity, name the decisions students are making, and ask questions before offering solutions. Capture student language on a chart so the class can reuse story words and engineering words during the build.",
    ], minimum=5)
    anticipatory_blocks = _expanded_blocks(teacher.get("anticipatory_set"), [
        f"**Engage:** Display or describe a real {artifact} and invite students to notice its shape, parts, and purpose. Accept observations first, then ask students to explain what evidence helped them notice each feature.",
        f"**Connect to experience:** Ask, \"When have you seen something delivered, carried, or moved from one place to another?\" Invite two or three quick examples and connect them to the story problem.",
        f"**Essential question:** Ask, \"How can we design a {artifact} that solves the story problem and has parts that work together?\" Keep the question visible throughout the lesson.",
        f"**Preview the challenge:** Tell students that they will listen for the character's problem, study how the parts of a {artifact} work, and then build a model with {moving_label}.",
        "**Check and transition:** Have students turn to a partner and name one thing an inventor does when an idea does not work yet. Listen for test, change, improve, ask, and try again before beginning the read-aloud.",
    ], minimum=5)
    read_blocks = _expanded_blocks(teacher.get("step_01_read"), [
        "**Prepare to listen:** Introduce the title and cover. Ask students to predict the problem, identify what the character may need to invent, and listen for moments when the character has to make a new choice.",
        f"**Vocabulary in context:** Preteach two or three high-utility words from the vocabulary list. Have students repeat each word, act it out or point to a visual, and use it in a sentence about the {artifact}.",
        "**Interactive read-aloud:** Pause at meaningful events to ask, \"What is the problem now? What has the character tried? What changed?\" Invite students to support answers with details from the words or pictures.",
        "**Sound awareness:** Select one story or build word. Stretch the word, identify its beginning sound, clap its syllables, and compare it with a word that rhymes or shares an ending sound.",
        "**Check and transition:** Ask partners to state the story problem and one design idea the story inspired. Use their responses to introduce the parts-and-functions exploration.",
    ], minimum=5)
    explore_blocks = _expanded_blocks(teacher.get("step_02_learn_explore"), [
        f"**Observe the whole:** Show the final build reference or a simple image of a {artifact}. Ask students to name the largest shapes first and explain why an engineer might make those parts broad, balanced, or connected.",
        f"**Study parts and functions:** Examine the body, support surfaces, and {moving_label}. For each part ask, \"What job does this part do? What might happen if it were missing or placed somewhere else?\"",
        "**Explore cause and effect:** Demonstrate a stable and an unstable arrangement with a few blocks. Let students predict which will stay together, then test and describe what the evidence shows.",
        "**Guided partner talk:** Provide the frame, \"The ___ helps the model ___ because ___.\" Encourage partners to use a vocabulary word and point to the corresponding part while explaining.",
        "**Check and transition:** Ask students to sketch with their fingers in the air where the main body, support pieces, and moving part will go. Confirm that partners can name at least two parts and their functions before inventing.",
    ], minimum=5)
    invent_blocks = _expanded_blocks(teacher.get("step_03_invent"), [
        "**Set up collaboration:** Assign or invite partners to choose roles such as piece finder, builder, image checker, and tester. Remind students that roles can rotate so both partners handle pieces and explain decisions.",
        f"**Plan before building:** Students identify the base or main body, locate the first pieces, and point to where {moving_label} will connect. Ask them to explain how their plan connects to the story problem.",
        "**Build and compare:** Use the notebook step images in order. After each step, partners compare the model with the isometric view and placement sheet, checking orientation, color-coded regions, and secure contacts.",
        "**Test and improve:** Pause at planned checkpoints to test stability and movement. If a part does not work, students name what they noticed, change one feature, and test again before adding more pieces.",
        "**Teacher support and transition:** Ask, \"What are you trying to make happen? What does the picture show? Which single change could you test?\" Photograph or place completed models for the closing gallery share.",
    ], minimum=5)
    closure_blocks = _expanded_blocks(teacher.get("closure_reflection"), [
        "**Partner rehearsal:** Each student practices a short explanation naming the story problem, one important part, one test, and one improvement. Partners listen for a complete explanation and ask one follow-up question.",
        "**Gallery share:** Invite students to observe several models without touching. Ask them to notice one design choice that is similar across models and one choice that is different.",
        f"**Return to the essential question:** Revisit how a {artifact} can solve the story problem. Record student evidence about how shape, connection, stability, and movement helped the models function.",
        f"**SEL reflection:** Connect the work back to {theme}. Name examples of students persisting, asking for help, sharing responsibility, or changing an idea after testing.",
        "**Exit check:** Students complete the stem, \"My invention works because ___. Next time I would ___.\" Accept an oral response, drawing, gesture, or written response.",
    ], minimum=5)
    learner_blocks = _expanded_blocks(teacher.get("plan_for_all_learners"), [
        "**Representation:** Keep the final reference, color-coded placement views, vocabulary visuals, and a small completed sample available. Point to the same feature across images and the physical model.",
        "**Language support:** Pair gestures and real pieces with new words. Offer sentence frames, partner rehearsal, and either-or choices before asking students to produce a full explanation.",
        "**Action and expression:** Let students show understanding by pointing, arranging pieces, drawing, speaking, or demonstrating movement. Use larger pieces or a partially started base when fine-motor support is needed.",
        "**Extension and regulation:** Invite ready students to propose and test one purposeful improvement. Offer a quiet build space, a visual role card, and brief check-ins for students who benefit from reduced choices or predictable turns.",
    ], minimum=4)
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
        *_markdown_blocks(overview_blocks),
        "## Learning Objectives",
        *[f"- {x}" for x in teacher.get("learning_objectives", context.get("learning_objectives", []))],
        "",
        "## Anticipatory Set",
        *_markdown_blocks(anticipatory_blocks),
        "## Step 01: Read",
        *_markdown_blocks(read_blocks),
        "## Step 02: Learn & Explore",
        *_markdown_blocks(explore_blocks),
        "## Step 03: Invent",
        *_markdown_blocks(invent_blocks),
        "## Closure & Reflection Questions",
        *_markdown_blocks(closure_blocks),
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
        *_markdown_blocks(learner_blocks),
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
    artifact = context.get("artifact_label", "model")
    theme = context.get("theme", "Inventors learn from testing and improving.")
    parts = context.get("parts", [])
    vocabulary = teacher.get("vocabulary", context.get("vocabulary", []))
    slide_content = lesson_package.get("slide_companion", {})
    vocabulary_words = ", ".join(
        str(item.get("term", "")) for item in vocabulary[:5] if isinstance(item, dict)
    ) or "inventor, design, test, improve"
    moving_parts = [part.get("part_name", "moving part") for part in parts if part.get("movement") != "static"]
    moving_label = ", ".join(moving_parts) or "the moving part"

    def prompts(key: str, defaults: list[str]) -> list[str]:
        return _expanded_blocks(slide_content.get(key), defaults, minimum=4)[:5]

    def prompt_lines(items: list[str]) -> list[str]:
        lines: list[str] = []
        for item in items:
            lines.extend([f"- {item}", ""])
        return lines

    storytime = prompts("storytime_prompts", [
        f"Today we will read, talk, explore, and build a {artifact}.",
        "Listen for the problem and for each idea the character tries.",
        "Use story words when you explain your thinking to a partner.",
        "Be ready to test an idea, notice what happens, and improve it.",
    ])
    story_problem = prompts("story_problem_prompts", [
        "What problem does the character need to solve?",
        "What has already been tried? What happened?",
        f"How could a {artifact} help solve the problem?",
        "Turn and talk: What detail from the story supports your idea?",
    ])
    big_idea = prompts("big_idea_prompts", [
        f"Our big idea: {theme}.",
        "Inventors do not expect the first idea to be perfect.",
        "Testing gives us information we can use.",
        "Partners help by noticing, asking, and trying ideas together.",
    ])
    vocabulary_prompts = prompts("vocabulary_prompts", [
        f"Words to know: {vocabulary_words}.",
        "Say each word, show it with a gesture, and use it in a sentence.",
        f"Which word helps us describe how the {artifact} works?",
        "Listen for these words during the story and the build.",
    ])
    sound_prompts = prompts("sound_awareness_prompts", [
        "Say a story or build word slowly. What first sound do you hear?",
        "Clap the word into syllables.",
        "Find a word that rhymes or shares the same ending sound.",
        "Turn and talk: Use both words in a playful sentence.",
    ])
    part_names = ", ".join(part.get("part_name", "part") for part in parts)
    parts_prompts = prompts("parts_and_functions_prompts", [
        f"Look for these parts: {part_names}.",
        f"Find {moving_label}. How should it move?",
        "Choose one static part. What job does it do?",
        "Use the frame: The ___ helps the model ___ because ___.",
    ])
    planning_prompts = prompts("planning_prompts", [
        "Point to the main body or base you will build first.",
        f"Show where {moving_label} will connect.",
        "Decide who will find pieces, build, check the image, and test.",
        "Predict one place where the model may need extra support.",
    ])
    lines = [
        f"# {title} Slide Companion",
        "",
        "## Slide 1 - Storytime Inventing",
        *prompt_lines(storytime),
        "## Slide 2 - Find The Story Problem",
        *prompt_lines(story_problem),
        "## Slide 3 - Our Big Idea",
        *prompt_lines(big_idea),
        "## Slide 4 - Words To Know",
        *prompt_lines(vocabulary_prompts),
        "## Slide 5 - Sound Detective",
        *prompt_lines(sound_prompts),
        "## Slide 6 - Parts And Their Jobs",
        *prompt_lines(parts_prompts),
        "## Slide 7 - Plan Before You Build",
        *prompt_lines(planning_prompts),
        "## Slide 8 - Meet The Final Build",
        f"- This is one classroom-buildable example of a {artifact}.",
        "",
        "- Notice the large shapes, stable base, and clearly separated moving feature.",
        "",
        "- Point to the part you think should be built first.",
        "",
        "- Predict how the completed model will connect to the story problem.",
        "",
        f"Final built reference image: {notebook.get('final_image', '')}",
        "",
        "## Slide 9 - Look From Every Side",
        "- Compare the front, back, left, right, top, bottom, and isometric views.",
        "",
        "- Find one part that looks different when the model turns.",
        "",
        "- Use the views to check position and orientation while building.",
        "",
        "- Partner check: Point to the same part in two different views.",
        "",
        f"Placement views: {notebook.get('segment_multiview_image', '')}",
        "",
    ]
    next_slide = 10
    for step in steps:
        number = step.get("step_number", "")
        inventory = ", ".join(
            f"{item.get('quantity')} x {item.get('piece')}"
            for item in step.get("inventory", [])
        ) or "Use the pieces shown in the step image."
        lines.extend([
            f"## Slide {next_slide} - Build Step {number}",
            f"- **Build:** {step.get('student_instruction', step.get('teacher_instruction', ''))}",
            "",
            f"- **Pieces:** {inventory}",
            "",
            "- **Notice:** Match the position, direction, and color-coded region in the picture.",
            "",
            "- **Partner check:** One partner points to the image while the other checks the model.",
            "",
            f"Image: {step.get('image_path', '')}",
            "",
            f"## Slide {next_slide + 1} - Check Build Step {number}",
            "- Turn the model to match each placement view.",
            "",
            "- Press connected pieces gently and check that the model stays stable.",
            "",
            f"- Test {moving_label} if this step includes its connection.",
            "",
            "- If something differs, change one piece at a time and compare again.",
            "",
            f"Placement views: {step.get('multiview_path', '')}",
            "",
        ])
        next_slide += 2
    reflection_prompts = prompts("reflection_prompts", [
        "Explain what your model does and how it connects to the story problem.",
        f"Show {moving_label} and describe how it moves or connects.",
        "Name one test your team performed and what you learned from it.",
        "Share one change you made and one idea you would try next.",
    ])
    lines.extend([
        f"## Slide {next_slide} - Share And Reflect",
        *prompt_lines(reflection_prompts),
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
    if kind == "lesson_plan":
        for heading in ("Teacher Overview", "Anticipatory Set", "Step 01: Read", "Step 02: Learn & Explore", "Step 03: Invent", "Closure & Reflection Questions"):
            match = re.search(
                rf"(?ms)^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)",
                text,
            )
            content_lines = [
                line for line in (match.group(1).splitlines() if match else [])
                if line.strip() and not line.lstrip().startswith("-")
            ]
            if len(content_lines) < 4:
                missing.append(f"{heading} content depth")
    if kind == "slide_companion":
        for slide_number in range(1, 8):
            match = re.search(
                rf"(?ms)^## Slide {slide_number}\b[^\n]*\n(.*?)(?=^## |\Z)",
                text,
            )
            prompt_count = sum(
                1 for line in (match.group(1).splitlines() if match else [])
                if line.strip().startswith("- ")
            )
            if prompt_count < 4:
                missing.append(f"slide {slide_number} content depth")
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
        from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer
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
        keepWithNext=True,
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
        keepWithNext=True,
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
    manual_lines = markdown_path.read_text(encoding="utf-8").splitlines()
    line_index = 0
    while line_index < len(manual_lines):
        raw_line = manual_lines[line_index]
        line = raw_line.strip()
        line_index += 1
        if not line:
            story.append(Spacer(1, 5 if not is_slide else 8))
            continue

        if kind == "activity_guide" and line == "## Reflection Questions":
            reflection_flowables = [
                Paragraph(_inline_markup(line[3:]), styles["KidSparkHeading"])
            ]
            while line_index < len(manual_lines):
                reflection_line = manual_lines[line_index].strip()
                if reflection_line.startswith("## "):
                    break
                line_index += 1
                if not reflection_line:
                    reflection_flowables.append(Spacer(1, 5))
                elif reflection_line.startswith("- "):
                    reflection_flowables.append(
                        Paragraph(
                            f"&bull; {_inline_markup(reflection_line[2:])}",
                            styles["KidSparkBullet"],
                        )
                    )
                else:
                    reflection_flowables.append(
                        Paragraph(_inline_markup(reflection_line), styles["KidSparkBody"])
                    )
            story.append(KeepTogether(reflection_flowables))
            continue

        image_path = image_path_from_manual_line(line)
        if image_path:
            max_image_height = 250 if is_slide else (190 if kind == "activity_guide" else 235)
            story.append(KeepTogether([
                Paragraph(_inline_markup(image_path["label"]), styles["KidSparkSubheading"]),
                fit_report_image(
                    image_path["path"],
                    max_width=650 if is_slide else 470,
                    max_height=max_image_height,
                ),
            ]))
            story.append(Spacer(1, 8 if not is_slide else 12))
            continue
        if line.startswith("# "):
            story.append(Paragraph(_inline_markup(line[2:]), styles["KidSparkTitle"]))
        elif line.startswith("## "):
            if is_slide and not first_slide_section:
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
