"""
KidSpark AI — Teacher Consultation Agent (Multi-Turn, KB-Informed)
Owner: Developer B

Core interactive agent. Engages in multi-turn dialog with the teacher,
guided by evidence from the knowledge base (mock data for Phase 1).

When no OpenAI API key is configured, returns scripted mock responses
so the pipeline is testable offline.
"""

import logging

from config import OPENAI_API_KEY, OPENAI_MODEL
from models.schemas import (
    ConsultationResponse,
    ConsultationSummary,
    StoryAnalysis,
)
from agents.mock_data import format_evidence_for_prompt, get_mock_evidence

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
- After each response, mentally track which areas are covered vs remaining.
- When ALL areas are covered, present a clear summary of agreed directions
  and ask the teacher if they are ready to approve and proceed.
- Do not say the plan is ready to proceed unless the teacher has provided all
  required checklist details: grade, duration, core concept/theme, learning
  goals, build object, moving parts, static parts, constraints, literacy focus,
  and SEL focus. If any are missing, ask directly for the missing details.

RESPONSE FORMAT:
Always respond conversationally in a warm, professional tone. Focus on
one or two areas per turn. Do not overwhelm the teacher with all areas
at once."""


def _build_system_prompt(
    story_analysis: StoryAnalysis | None,
    chat_history: list[dict[str, str]],
) -> str:
    evidence = get_mock_evidence()
    evidence_text = format_evidence_for_prompt(evidence)
    story_text = story_analysis.model_dump_json(indent=2) if story_analysis else "Not yet available."
    return SYSTEM_PROMPT.format(
        story_analysis=story_text,
        kb_evidence=evidence_text,
    )


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
) -> ConsultationResponse:
    """Process one teacher message through the consultation agent."""

    updated_history = chat_history + [{"role": "user", "content": message}]

    if not OPENAI_API_KEY:
        logger.warning("No OpenAI API key — returning mock consultation response")
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

    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    system_prompt = _build_system_prompt(story_analysis, chat_history)

    messages = [{"role": "system", "content": system_prompt}]
    for msg in chat_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": message})

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=800,
    )

    reply = response.choices[0].message.content
    updated_history.append({"role": "assistant", "content": reply})
    covered, remaining = _infer_areas_covered(updated_history)
    ready = len(remaining) == 0

    return ConsultationResponse(
        response=reply,
        areas_covered=covered,
        areas_remaining=remaining,
        ready_to_approve=ready,
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
    if not OPENAI_API_KEY:
        logger.warning("No OpenAI API key — returning mock ConsultationSummary")
        return MOCK_CONSULTATION_SUMMARY

    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)

    system_prompt = _build_system_prompt(story_analysis, chat_history)

    messages = [{"role": "system", "content": system_prompt}]
    for msg in chat_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({
        "role": "user",
        "content": (
            "Based on everything we have discussed, produce a final "
            "ConsultationSummary in the required JSON format. Include all "
            "the areas we agreed upon."
        ),
    })

    response = client.beta.chat.completions.parse(
        model=OPENAI_MODEL,
        messages=messages,
        response_format=ConsultationSummary,
        temperature=0.3,
    )

    return response.choices[0].message.parsed
