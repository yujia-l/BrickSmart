"""
KidSpark AI — Teacher Consultation Agent (Multi-Turn, KB-Informed)
Owner: Developer B

This is the core interactive agent. Unlike other pipeline steps, this agent
is CONVERSATIONAL — it engages in a multi-turn dialog with the teacher,
guided by evidence from the knowledge base retrieved at each turn.

PURPOSE:
  Many teachers may not know how to structure a Kid Spark lesson. This agent
  is instructive — it proactively suggests directions, shows relevant examples
  from existing lessons, and progressively narrows the conversation toward a
  concrete lesson plan direction.

RESPONSIBILITIES:
  - Maintain conversation state across multiple teacher messages
  - At each turn, optionally retrieve from the knowledge base to inform responses:
      * retrieve_lessons: find similar lesson bundles by query + grade_band
      * retrieve_policy: find curriculum rules by grade_band + framework
  - Progressively cover these key areas before producing a summary:
      * Central theme (from the storybook's themes)
      * Grade band + duration (logistical constraints)
      * Learning objectives (informed by KB exemplars and policy rules)
      * Build artifact (what students will physically build)
      * Literacy focus (vocabulary, phonics, Science of Reading alignment)
      * SEL focus (social-emotional learning, CASEL alignment)
  - When all areas are covered, present a clear summary and ask for approval
  - On approval, produce a ConsultationSummary

INPUTS:
  - teacher message: str (current turn)
  - StoryAnalysis (from Step A)
  - chat_history: list of previous messages
  - KB access via tool functions

OUTPUTS:
  - Per turn: response text + progress indicators (areas_covered, areas_remaining)
  - On approval: ConsultationSummary (Pydantic model, see models/schemas.py)

AGENT SETUP:
  - Pydantic AI Agent with deps_type=ConsultationDeps
  - Two tool functions: retrieve_lessons() and retrieve_policy()
  - System prompt should instruct the model to be KidSpark AI curriculum designer
  - Multi-turn: called once per teacher message, maintains state via session

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.3, "Teacher Consultation Agent"
"""
