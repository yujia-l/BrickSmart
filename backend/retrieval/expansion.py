"""
KidSpark AI — Bundle Expansion
Owner: Developer B

This module implements the critical "bundle expansion" behavior. When a search
returns a high-scoring node, this module fetches all related content from the
same lesson bundle to provide coherent, cross-document context.

RESPONSIBILITIES:
  - Given a set of top-scoring nodes from search.py:
      * Fetch all sibling nodes from the same bundle(s) — teacher plan sections,
        activity guide sections, slide captions
      * Follow Relation links (uses_example_from, mirrored_by, visualized_by)
        to pull in connected nodes from other documents
      * Fetch matching PolicyRule records for the bundle's grade_band and strand
  - This ensures the agent receives a coherent lesson family, not scattered
    fragments from different bundles

INPUTS:
  - List of top-K candidate nodes (from search.py)

OUTPUTS:
  - Expanded set of nodes organized by bundle, plus related policy rules

EXAMPLE:
  If "teacher.step03.invent" from the airplane bundle scores highly, expansion
  also pulls: teacher.overview, teacher.objectives, teacher.vocabulary,
  activity.p2.example_airplane, slide.p14.build_step_1, and policy rules for
  K-2-ETS1-2, UDL, CASEL, SoR.

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.3, "Bundle Expansion"
"""
