from agents import orchestrator
from api.sessions import _segment_job_matches_current_model
from models.schemas import SessionState


def test_starting_a_new_model_preview_clears_all_downstream_results(monkeypatch):
    session = SessionState(
        session_id="state-reset",
        model_preview_result={"rodin": {"task_uuid": "old-model"}},
        segment_job_id="old-segments",
        document_job_id="old-documents",
        build_job_id="old-build",
        segment_result={"old": True},
        build_result={"old": True},
        document_result={"old": True},
    )
    orchestrator._sessions[session.session_id] = session
    monkeypatch.setattr(
        orchestrator,
        "start_model_preview_job",
        lambda context, session_id: {"job_id": "new-model-job", "status": "queued"},
    )

    try:
        orchestrator.start_session_model_preview(
            session.session_id,
            context_override={"artifact_label": "compact plane"},
        )

        assert session.model_preview_job_id == "new-model-job"
        assert session.segment_job_id is None
        assert session.document_job_id is None
        assert session.build_job_id is None
        assert session.segment_result is None
        assert session.build_result is None
        assert session.document_result is None
    finally:
        orchestrator._sessions.pop(session.session_id, None)


def test_completed_segment_result_is_reused_only_for_the_current_rodin_model():
    session = SessionState(
        session_id="task-match",
        model_preview_result={"rodin": {"task_uuid": "current-model"}},
    )

    assert _segment_job_matches_current_model(
        session,
        {"result": {"rodin": {"task_uuid": "current-model"}}},
    )
    assert not _segment_job_matches_current_model(
        session,
        {"result": {"rodin": {"task_uuid": "previous-model"}}},
    )
    assert not _segment_job_matches_current_model(session, {"result": {}})
