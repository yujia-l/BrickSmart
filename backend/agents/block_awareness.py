"""
KidSpark AI — Block Awareness Agent (Kid Spark Piece Catalog)
Owner: Developer B

Determines what Kid Spark physical pieces are needed for the agreed
build artifact, with focus on movable and articulated parts.

When Vertex is unavailable, returns scripted mock responses so the pipeline is
testable offline.
"""

import json
import logging

from llm.vertex_gemini import generate_json, generate_text, provider_configured
from models.schemas import (
    ArtifactPart,
    BlockRequirements,
    ConsultationSummary,
)
from agents.mock_data import MOCK_BLOCK_CATALOG

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a Kid Spark block-building expert. Given an agreed build artifact
from the teacher consultation, you determine which Kid Spark Early Inventors
STEM Lab pieces are needed.

CONSULTATION SUMMARY:
{consultation_summary}

KID SPARK BLOCK CATALOG:
{block_catalog}

YOUR JOB:
1. List the main parts of the artifact
2. Ask the teacher which parts should move and how
3. Map each part to specific Kid Spark piece types
4. Identify which special connectors are needed for articulated parts
5. Produce a BlockRequirements spec

When producing BlockRequirements, movement values must be exactly one of:
spinning, rolling, pivoting, static.

Movement-to-piece mapping:
- Spinning (continuous rotation) → Wheel/axle piece
- Pivoting (limited arc) → Angle connector
- Rolling (ground movement) → Wheel pieces + axle
- Static structure → Cube blocks (windowed)
- Bridging (flat connection) → Flat connector

Be concise and helpful. If the teacher isn't sure about movement, suggest
what would be fun and educational based on the artifact type.

Respond conversationally first. When you have enough information about
movement preferences, you will produce the final BlockRequirements."""


def _build_system_prompt(consultation_summary: ConsultationSummary) -> str:
    catalog_text = "\n".join(
        f"- {p.piece_name} ({p.piece_type}): {p.description} "
        f"[rotation={p.supports_rotation}, pivot={p.supports_pivot}, "
        f"axle={p.supports_axle}]"
        for p in MOCK_BLOCK_CATALOG
    )
    return SYSTEM_PROMPT.format(
        consultation_summary=consultation_summary.model_dump_json(indent=2),
        block_catalog=catalog_text,
    )


MOCK_BLOCK_RESPONSE = (
    "Your **flying delivery vehicle** has these main parts: "
    "wings, body, cargo compartment, propeller, and landing gear.\n\n"
    "Let me ask about movement:\n"
    "- Should the **propeller** spin?\n"
    "- Should the **wings** move or stay fixed?\n"
    "- Should the **cargo compartment** open?\n"
    "- Should it have **rolling wheels** on the landing gear?\n\n"
    "Tell me which parts should move and how!"
)

MOCK_BLOCK_REQUIREMENTS = BlockRequirements(
    artifact_label="flying delivery vehicle",
    parts=[
        ArtifactPart(
            part_name="propeller",
            movement="spinning",
            suggested_pieces=["wheel_axle"],
            piece_count=1,
            notes="Axle through front-mounted cube block",
        ),
        ArtifactPart(
            part_name="wings",
            movement="static",
            suggested_pieces=["cube_block"],
            piece_count=4,
            notes="Two cubes per wing, extending from body sides",
        ),
        ArtifactPart(
            part_name="body",
            movement="static",
            suggested_pieces=["cube_block"],
            piece_count=4,
            notes="Central fuselage structure",
        ),
        ArtifactPart(
            part_name="cargo_compartment",
            movement="static",
            suggested_pieces=["cube_block"],
            piece_count=2,
            notes="Attached under or behind body",
        ),
        ArtifactPart(
            part_name="landing_gear",
            movement="rolling",
            suggested_pieces=["wheel_axle", "flat_connector"],
            piece_count=2,
            notes="Wheels mounted on axles under body",
        ),
    ],
    connector_types_needed=["flat_connector", "wheel_axle"],
    total_cube_blocks=10,
    total_special_pieces=4,
    articulation_summary="Spinning propeller (1x wheel/axle), rolling landing gear (2x wheel/axle + flat connectors)",
)


async def handle_block_awareness_message(
    message: str,
    consultation_summary: ConsultationSummary,
    chat_history: list[dict[str, str]],
) -> str:
    """Process a teacher message about block/movement preferences."""
    if not provider_configured():
        logger.warning("Vertex unavailable - returning mock block awareness response")
        return MOCK_BLOCK_RESPONSE

    system_prompt = _build_system_prompt(consultation_summary)
    return generate_text(
        system_prompt,
        json.dumps({"history": chat_history[-12:], "teacher_message": message}, ensure_ascii=True),
        temperature=0.7,
        max_output_tokens=1000,
    )


async def finalize_block_requirements(
    consultation_summary: ConsultationSummary,
    chat_history: list[dict[str, str]],
) -> BlockRequirements:
    """Produce the final BlockRequirements from the conversation."""
    if not provider_configured():
        logger.warning("Vertex unavailable - returning mock BlockRequirements")
        return MOCK_BLOCK_REQUIREMENTS

    system_prompt = _build_system_prompt(consultation_summary)
    return generate_json(
        system_prompt,
        json.dumps(
            {
                "conversation": chat_history,
                "instruction": "Produce the final BlockRequirements from the teacher-approved discussion.",
            },
            ensure_ascii=True,
        ),
        schema=BlockRequirements,
        temperature=0.3,
    )
