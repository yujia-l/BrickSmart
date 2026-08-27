"""
KidSpark AI — Policy / Standards Loader
Owner: Developer A

This module ingests the curriculum standards and framework documents (UDL,
CASEL, Science of Reading, NGSS, ISTE, CCSS) into the policy_rules table.

RESPONSIBILITIES:
  - Parse the "Early Childhood STEM & Literacy Program — Standards Alignment
    and Framework" PDF
  - Extract individual standards/rules with their:
      * framework (UDL | CASEL | SoR | NGSS | ISTE | CCSS)
      * grade_band (Pre-K | Kindergarten | 1st Grade)
      * strand (STEM Foundations | Storytime Inventing)
      * standard_code (e.g., K-2-ETS1-2, RF.1.2)
      * rule_text (full text of the standard or rule)
  - Write PolicyRule records to the database
  - Embeddings are generated separately by embedder.py

INPUTS:
  - Standards framework PDF file

OUTPUTS:
  - PolicyRule records in the database

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.1 (policy_rules table)
"""
