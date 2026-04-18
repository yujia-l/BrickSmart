"""
Tests for api/sessions.py
Owner: Developer B

TEST CASES TO IMPLEMENT:
  - test_create_session: POST /sessions returns session_id
  - test_upload_storybook: POST /sessions/{id}/upload triggers analysis
  - test_send_message_consultation: POST /sessions/{id}/message during
    consultation phase routes to consultation agent
  - test_approve_plan: POST /sessions/{id}/approve-plan transitions to
    block_awareness phase
  - test_send_message_block_awareness: POST /sessions/{id}/message during
    block_awareness phase routes to block awareness agent
  - test_generate_lesson: POST /sessions/{id}/generate triggers full pipeline
  - test_generate_before_ready: Verify 400 error when generating before
    block awareness is complete
  - test_refine_lesson: POST /sessions/{id}/refine re-generates with feedback
  - test_get_package: GET /sessions/{id}/package returns LessonPackage
  - test_get_trace: GET /sessions/{id}/trace returns retrieval evidence
"""
