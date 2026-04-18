"""
KidSpark AI — Document Parser (Stage 1)
Owner: Developer A

This module uses Docling (IBM's open-source document conversion toolkit) to
extract structured content from Kid Spark lesson PDFs while preserving layout,
heading hierarchy, and image bounding boxes.

RESPONSIBILITIES:
  - Accept a raw PDF file path or GCS URI as input
  - Use Docling to parse the PDF and extract:
      * Text blocks with reading order
      * Heading hierarchy (H1, H2, H3)
      * Image regions and their bounding boxes
      * Table structures (if present)
  - For Slide Companion PDFs: render each page to a PNG image and upload to GCS
  - Return a structured ParsedDocument with all extracted elements

INPUTS:
  - PDF file path (local or GCS URI)
  - doc_kind: "teacher_plan" | "activity_guide" | "slide_companion"
  - bundle_id: the parent lesson bundle ID

OUTPUTS:
  - ParsedDocument containing text blocks, headings, image regions, page images

DEPENDENCIES:
  - docling (IBM document conversion)
  - Google Cloud Storage client (for page image uploads)

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.2, "Stage 1 — Layout-Aware Parsing"
"""
