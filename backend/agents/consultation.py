"""
KidSpark AI — Teacher Consultation Agent (Multi-Turn, KB-Informed)
Owner: Developer B

Core interactive agent. Engages in multi-turn dialog with the teacher,
guided by evidence from the knowledge base (mock data for Phase 1).

When Vertex is unavailable, returns scripted mock responses so the pipeline is
testable offline.
"""

import json
import logging

from llm.vertex_gemini import generate_json, provider_configured
from models.schemas import (
    ConsultationResponse,
    ConsultationSummary,
    ConsultationTurn,
    StoryAnalysis,
)
from retrieval.provider import format_teacher_evidence, retrieve_teacher_evidence

logger = logging.getLogger(__name__)

ALL_AREAS = [
    "central_theme",
    "grade_band",
    "duration",
    "learning_objectives",
    "build_artifact",
    "moving_parts",
    "static_parts",
    "constraints",
    "literacy_focus",
    "sel_focus",
]

SYSTEM_PROMPT = """\
You are KidSpark AI, an expert curriculum designer for Kid Spark Education
block-building lessons. You are guiding a teacher through planning a new
lesson based on a storybook they uploaded.

STORYBOOK ANALYSIS:
{story_analysis}

KNOWLEDGE BASE EVIDENCE (existing lessons and policy rules):
{kb_evidence}

AUTHORITATIVE CURRENT LESSON STATE:
{planning_state}

FIELDS THE APPLICATION STILL NEEDS:
{missing_fields}

YOUR JOB:
- Be INSTRUCTIVE — if the teacher is unsure, suggest concrete options
  grounded in the knowledge base evidence above.
- Progressively cover these areas before producing a final summary:
  1. Central theme (from the storybook's themes)
  2. Grade band + duration (logistical constraints)
  3. Learning objectives (informed by KB exemplars and policy rules)
  4. Build artifact (what students will physically build with Kid Spark blocks)
  5. Moving parts (what should spin, roll, pivot, flap, or otherwise move)
  6. Static parts (what should stay fixed for the physical build)
  7. Classroom constraints (groups, materials, timing, accessibility, or management needs)
  8. Literacy focus (vocabulary, phonics, Science of Reading alignment)
  9. SEL focus (social-emotional learning, CASEL alignment)
- Reference specific examples from the KB evidence when making suggestions.
- Treat AUTHORITATIVE CURRENT LESSON STATE as the only checklist source of truth.
- Return teacher-confirmed values in planning_update. A value is confirmed when
  the teacher states it, accepts a proposal, or explicitly delegates the choice
  with language such as "choose for me" or "fill it out".
- Suggestions that the teacher has not accepted or delegated must remain
  conversational proposals and must not be written to planning_update.
- If the teacher confirms that nothing should move, return moving_parts as an
  empty list and movement_confirmed as true. This is a complete, valid choice.
- If the teacher names moving parts, return them and set movement_confirmed true.
- Preserve completed values unless the teacher explicitly changes them.
- Ask only about the most useful one or two missing fields. Do not repeat fields
  that are already present in AUTHORITATIVE CURRENT LESSON STATE.
- Never announce that the checklist is complete, ready to approve, or ready to
  proceed. The application owns that decision and displays the approval state.

RESPONSE FORMAT:
Return a structured ConsultationTurn. The response field must be warm,
professional Markdown focused on one or two areas. The planning_update field
must contain only values confirmed during this turn."""


def _build_system_prompt(
    story_analysis: StoryAnalysis | None,
    chat_history: list[dict[str, str]],
    teacher_message: str = "",
    evidence: dict | None = None,
    planning_state: dict | None = None,
) -> str:
    history_text = " ".join(m.get("content", "") for m in chat_history[-8:])
    grade_hint = next(
        (
            token
            for token in (
                "Pre-K",
                "Kindergarten",
                "1st Grade",
                "2nd Grade",
                "3rd Grade",
                "4th Grade",
                "5th Grade",
            )
            if token.lower() in history_text.lower()
        ),
        "1st Grade",
    )
    evidence = evidence or retrieve_teacher_evidence(
        " ".join(
            part
            for part in (
                story_analysis.title if story_analysis else "",
                teacher_message,
                history_text[-2500:],
            )
            if part
        ),
        grade_hint,
    )
    evidence_text = format_teacher_evidence(evidence)
    story_text = story_analysis.model_dump_json(indent=2) if story_analysis else "Not yet available."
    return SYSTEM_PROMPT.format(
        story_analysis=story_text,
        kb_evidence=evidence_text,
        planning_state=json.dumps(planning_state or {}, indent=2, ensure_ascii=True),
        missing_fields=", ".join(_missing_fields(planning_state or {})) or "None",
    )


def _missing_fields(state: dict) -> list[str]:
    fields = [
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
    missing = [label for key, label in fields if not state.get(key)]
    if not state.get("movement_confirmed"):
        missing.insert(5, "moving parts or confirmation that the build is fully static")
    return missing


def _infer_areas_covered(chat_history: list[dict[str, str]]) -> tuple[list[str], list[str]]:
    """Heuristic area tracking based on conversation content."""
    full_text = " ".join(
        m["content"].lower() for m in chat_history if m["role"] == "user"
    )

    covered = []
    for area in ALL_AREAS:
        keywords = {
            "central_theme": ["theme", "perseverance", "community", "invention", "focus on"],
            "grade_band": ["grade", "1st", "2nd", "kindergarten", "pre-k"],
            "duration": ["minute", "time", "35", "30", "45", "duration"],
            "learning_objectives": ["objective", "i can", "learn", "goal"],
            "build_artifact": ["build", "artifact", "vehicle", "airplane", "construct", "flying"],
            "moving_parts": ["move", "moving", "spin", "spinning", "roll", "rolling", "pivot", "flap", "propeller", "wheel"],
            "static_parts": ["static", "fixed", "stay still", "stays still", "stay in place", "body", "wings", "tail"],
            "constraints": ["pairs", "partner", "small group", "whole group", "limited time", "materials", "accessibility"],
            "literacy_focus": ["vocabulary", "literacy", "phonics", "rhyming", "reading", "letter"],
            "sel_focus": ["sel", "partner", "collaboration", "teamwork", "social", "emotional", "casel"],
        }
        if any(kw in full_text for kw in keywords.get(area, [])):
            covered.append(area)

    remaining = [a for a in ALL_AREAS if a not in covered]
    return covered, remaining


MOCK_RESPONSES = [
    (
        "Great choice of storybook! **Milo's Flying Delivery** has wonderful themes "
        "of perseverance and community. I found a similar lesson in our library — "
        "'Invent an Airplane' for 1st grade, which is also about flying machines.\n\n"
        "To get started: **What grade are you teaching, and how much class time "
        "do you have?**"
    ),
    (
        "Perfect -- 1st grade with 35 minutes works well with a Read > Learn & "
        "Explore → Invent structure, just like the airplane lesson.\n\n"
        "For **learning objectives**, similar lessons use:\n"
        "- *I can build a model of a flying delivery vehicle*\n"
        "- *I can tell about the parts of my design*\n\n"
        "Students could **build Milo's flying delivery vehicle** with wings, body, "
        "propeller, cargo compartment, and landing gear.\n\n"
        "**What literacy or vocabulary focus would you like?** The word 'delivery' "
        "starts with Dd — we could include a rhyming activity."
    ),
    (
        "Excellent! Here's what we have so far:\n\n"
        "- **Theme:** Perseverance through invention\n"
        "- **Grade:** 1st Grade, 35 minutes\n"
        "- **Build artifact:** Flying delivery vehicle\n"
        "- **Objectives:** Build a model; tell about its parts\n"
        "- **Literacy:** Dd is for delivery, rhyming with /ee/\n"
        "- **SEL:** Partner talk, helping others (CASEL competencies)\n\n"
        "Does this direction look good? If so, you can **approve the plan** "
        "and we'll move on to mapping Kid Spark blocks!"
    ),
]


async def handle_consultation_message(
    message: str,
    story_analysis: StoryAnalysis | None,
    chat_history: list[dict[str, str]],
    evidence: dict | None = None,
    planning_state: dict | None = None,
) -> ConsultationResponse:
    """Process one teacher message through the consultation agent."""

    updated_history = chat_history + [{"role": "user", "content": message}]

    if not provider_configured():
        logger.warning("Vertex unavailable - returning mock consultation response")
        turn = len([m for m in chat_history if m["role"] == "user"])
        reply = MOCK_RESPONSES[min(turn, len(MOCK_RESPONSES) - 1)]
        updated_history.append({"role": "assistant", "content": reply})
        covered, remaining = _infer_areas_covered(updated_history)
        return ConsultationResponse(
            response=reply,
            areas_covered=covered,
            areas_remaining=remaining,
            ready_to_approve=len(remaining) == 0,
        )

    evidence = evidence or {}
    system_prompt = _build_system_prompt(
        story_analysis,
        chat_history,
        message,
        evidence=evidence or None,
        planning_state=planning_state,
    )
    turn = generate_json(
        system_prompt,
        json.dumps(
            {"history": chat_history[-12:], "teacher_message": message},
            ensure_ascii=True,
        ),
        schema=ConsultationTurn,
        temperature=0.45,
        max_output_tokens=1800,
    )
    reply = turn.response
    updated_history.append({"role": "assistant", "content": reply})
    covered, remaining = _infer_areas_covered(updated_history)
    ready = len(remaining) == 0

    return ConsultationResponse(
        response=reply,
        planning_update=turn.planning_update,
        areas_covered=covered,
        areas_remaining=remaining,
        ready_to_approve=ready,
        rag_status=str(evidence.get("status", "not_requested")),
        rag_trace=evidence.get("trace", []),
    )


MOCK_CONSULTATION_SUMMARY = ConsultationSummary(
    agreed_theme="perseverance through invention",
    agreed_artifact="flying delivery vehicle",
    artifact_parts=["wings", "body", "propeller", "cargo compartment", "landing gear"],
    learning_objectives=[
        "Build a model of a flying delivery vehicle",
        "Tell about the parts of my design and why I chose them",
    ],
    grade_band="1st Grade",
    duration_minutes=35,
    literacy_focus="Dd is for delivery, rhyming with /ee/ sound",
    sel_focus="Partner talk, helping others, teamwork",
    teacher_preferences=["partner collaboration", "vocabulary focus"],
    kb_evidence_used=["storytime_inventing.grade1.invent_an_airplane"],
    storybook_title="Milo's Flying Delivery",
)


async def finalize_consultation(
    story_analysis: StoryAnalysis | None,
    chat_history: list[dict[str, str]],
) -> ConsultationSummary:
    """Produce the final ConsultationSummary from the conversation."""
    if not provider_configured():
        logger.warning("Vertex unavailable - returning mock ConsultationSummary")
        return MOCK_CONSULTATION_SUMMARY

    system_prompt = _build_system_prompt(story_analysis, chat_history)
    return generate_json(
        system_prompt,
        json.dumps(
            {
                "conversation": chat_history,
                "instruction": (
                    "Produce the final ConsultationSummary. Include every "
                    "teacher-approved checklist area and evidence identifiers."
                ),
            },
            ensure_ascii=True,
        ),
        schema=ConsultationSummary,
        temperature=0.3,
    )
