"""
KidSpark AI — Visual Captioner (Stage 3)
Owner: Developer A

This module generates structured text descriptions for image-heavy Slide
Companion pages using GPT-4o Vision. These captions become the searchable
text content for visual knowledge nodes (the "visual shadow index").

RESPONSIBILITIES:
  - For each Slide Companion page image (PNG stored in GCS):
      * Send the image to GPT-4o Vision with a structured prompt
      * Request a SlideCaption response: page_number, visual_elements
        (list of element descriptions), instructional_purpose, build_relevance,
        text_on_slide
      * Store the caption as the content_text of the corresponding KnowledgeNode
  - Skip pages that are primarily text (already handled by extractor)
  - Track which pages were captioned vs. text-extracted

INPUTS:
  - List of page image GCS URIs from the Slide Companion
  - Corresponding KnowledgeNode IDs to update

OUTPUTS:
  - Updated KnowledgeNode records with caption text in content_text field

DEPENDENCIES:
  - OpenAI client (GPT-4o Vision)
  - Google Cloud Storage client (read page images)

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 7.2, "Stage 3 — Visual Captioning"
"""
