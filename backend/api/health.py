"""
KidSpark AI — Health Check Endpoint
Owner: Developer B

This module provides health and readiness endpoints for Cloud Run.

ENDPOINTS TO IMPLEMENT:

  GET /health
    - Basic liveness check
    - Returns {"status": "ok"}

  GET /health/ready
    - Readiness check that verifies:
        * Database connection is alive
        * OpenAI API key is configured
        * GCS bucket is accessible
    - Returns {"status": "ready", "checks": {...}} or 503 if not ready

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 12, "Deployment and Operations"
"""
