"""
KidSpark AI — Ingestion API Router
Owner: Developer A

This module defines the FastAPI router for all ingestion-related endpoints.
These endpoints are used to upload lesson bundles, trigger ingestion, and
monitor ingestion job status.

ENDPOINTS TO IMPLEMENT:
  POST /api/v1/bundles
    - Register a new lesson bundle (upload 3 PDF files: teacher plan,
      activity guide, slide companion)
    - Creates a LessonBundle record and stores raw PDFs in GCS
    - Returns bundle_id

  POST /api/v1/bundles/{bundle_id}/ingest
    - Trigger the full ingestion pipeline for a registered bundle
    - Runs stages 1-5 asynchronously, creates an IngestionJob to track progress
    - Returns job_id

  GET /api/v1/bundles
    - List all bundles with their status (pending | ingesting | ready | error)

  GET /api/v1/bundles/{bundle_id}
    - Get bundle detail with summary of extracted nodes

  GET /api/v1/bundles/{bundle_id}/nodes
    - List all knowledge nodes in a bundle (paginated)

  POST /api/v1/policy/ingest
    - Ingest the standards/framework document into policy_rules

  GET /api/v1/ingestion-jobs/{job_id}
    - Check ingestion job status and progress

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 10, "Ingestion APIs"
"""
