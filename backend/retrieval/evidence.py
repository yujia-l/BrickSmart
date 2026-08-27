"""
KidSpark AI — Evidence Pack Assembly
Owner: Developer B

This module assembles the final EvidencePack from the expanded retrieval
results. The EvidencePack is the structured context object passed to the
generation pipeline agents.

RESPONSIBILITIES:
  - Take the expanded node set from expansion.py and organize it into
    categorized "cards":
      * teacher_cards: nodes where audience == "teacher"
      * student_cards: nodes where audience == "student"
      * visual_cards: nodes where visual_role is not null
      * policy_cards: matching PolicyRule records
      * trace: list of TraceEntry records (node_id, score, bundle_id)
        for debugging and transparency
  - Truncate or summarize if the total context exceeds token limits
  - Return a typed EvidencePack (defined in models/schemas.py)

INPUTS:
  - Expanded node set from expansion.py
  - Policy rules from search.py

OUTPUTS:
  - EvidencePack object ready for agent consumption

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.3, retrieval pipeline output
"""
