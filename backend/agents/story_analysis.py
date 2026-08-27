"""
KidSpark AI — Step A: Storybook Analysis Agent
Owner: Developer B

Automatic one-shot analysis of the uploaded storybook. Runs immediately
after upload, before teacher consultation begins.

When Vertex is unavailable, returns a mock analysis for the sample storybook
so the pipeline is testable offline.
"""

import logging

from llm.vertex_gemini import generate_json, provider_configured
from models.schemas import StoryAnalysis

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a children's literature analyst specializing in early-childhood
STEM education. Given a storybook text, extract the following structured
information to support lesson planning for Kid Spark block-building lessons:

- title: The book's title
- characters: Main characters with brief descriptors
- settings: Locations/environments in the story
- key_events: Important plot events in order
- themes: Central themes (e.g., perseverance, community, invention)
- buildable_objects: Physical things from the story that students could
  build with blocks (vehicles, structures, animals, etc.)
- vocabulary_opportunities: Age-appropriate words worth teaching
- sel_angles: Social-emotional learning connections (helping, teamwork, etc.)

Return ONLY valid JSON matching the schema. Be thorough but concise."""

MOCK_STORY_ANALYSIS = StoryAnalysis(
    title="Milo's Flying Delivery",
    characters=["Milo (young inventor)", "Grandma Rose (baker)", "neighborhood friends"],
    settings=["Milo's workshop", "the neighborhood", "the sky"],
    key_events=[
        "Milo wants to deliver cookies by air",
        "First flying attempt crashes into fence",
        "Second attempt flies into a tree",
        "Friends help redesign the vehicle",
        "Final attempt succeeds — cookies delivered to everyone",
    ],
    themes=["perseverance", "community", "invention", "teamwork"],
    buildable_objects=["flying delivery vehicle", "workshop", "cargo compartment"],
    vocabulary_opportunities=["delivery", "propeller", "design", "invention", "perseverance", "engineer"],
    sel_angles=["helping others", "not giving up", "teamwork", "asking for help"],
)


async def analyze_storybook(storybook_text: str) -> StoryAnalysis:
    """Run one-shot storybook analysis and return a StoryAnalysis."""
    if not provider_configured():
        logger.warning("Vertex unavailable - returning mock StoryAnalysis")
        return MOCK_STORY_ANALYSIS

    return generate_json(
        SYSTEM_PROMPT,
        storybook_text,
        schema=StoryAnalysis,
        temperature=0.3,
    )
