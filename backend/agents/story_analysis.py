"""
KidSpark AI — Step A: Storybook Analysis Agent
Owner: Developer B

This agent performs an automatic, one-shot analysis of the uploaded storybook.
It runs immediately after upload, before the teacher consultation begins.
It extracts the raw material that the Consultation Agent uses to guide the
conversation.

RESPONSIBILITIES:
  - Accept raw storybook text as input
  - Use GPT-4o to extract structured information:
      * title, characters, settings
      * key_events (plot summary points)
      * themes (e.g., perseverance, community, invention)
      * buildable_objects (things from the story students could build)
      * vocabulary_opportunities (age-appropriate words to teach)
      * sel_angles (social-emotional learning connections)
  - Return a typed StoryAnalysis model

INPUTS:
  - storybook_text: str (full text extracted from the uploaded PDF)

OUTPUTS:
  - StoryAnalysis (Pydantic model, see models/schemas.py)

AGENT SETUP:
  - Pydantic AI Agent with result_type=StoryAnalysis
  - System prompt should instruct the model to be a children's literature analyst
  - One-shot (not conversational, no tools needed)

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.3, "Step A — Storybook Analysis"
"""
