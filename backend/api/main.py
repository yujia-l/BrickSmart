"""
KidSpark AI — FastAPI Application Entry Point
Owner: Developer B

This module creates and configures the FastAPI application instance.

RESPONSIBILITIES:
  - Create the FastAPI app with title, version, description
  - Include routers:
      * ingestion router (from ingestion/router.py — Dev A's endpoints)
      * session router (from api/sessions.py — Dev B's endpoints)
      * health router (from api/health.py)
  - Configure middleware:
      * CORS (allow Streamlit/React frontend origins)
      * Request logging
  - Set up lifespan events:
      * on_startup: initialize database connection pool, verify GCP credentials
      * on_shutdown: close database connections
  - Mount under /api/v1 prefix

RUNNING:
  uvicorn api.main:app --reload --port 8000

DEPLOYMENT:
  This app is containerized via backend/Dockerfile and deployed to GCP Cloud Run.

REFERENCE: KIDSPARK_TECHNICAL_SPEC.md Section 5, "System Architecture"
"""
