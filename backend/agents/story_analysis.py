"""
KidSpark AI — Step A: Storybook Analysis Agent
Owner: Developer B

Automatic one-shot analysis of the uploaded storybook. Runs immediately
after upload, before teacher consultation begins.

When no OpenAI API key is configured, returns a mock analysis for the
sample storybook so the pipeline is testable offline.
"""

import logging

from config import OPENAI_API_KEY, OPENAI_MODEL
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
    if not OPENAI_API_KEY:
        logger.warning("No OpenAI API key — returning mock StoryAnalysis")
        return MOCK_STORY_ANALYSIS

    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)

    response = client.beta.chat.completions.parse(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": storybook_text},
        ],
        response_format=StoryAnalysis,
        temperature=0.3,
    )

    return response.choices[0].message.parsed
