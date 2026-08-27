from types import SimpleNamespace

from google import genai

from agents import orchestrator
from llm import vertex_gemini
from models.schemas import (
    ConsultationResponse,
    PlanningPart,
    PlanningStateUpdate,
    SessionPhase,
    StoryAnalysis,
)
from retrieval import provider
from retrieval.grade_bands import (
    GRADE_2_5,
    GRADE_6_8,
    GRADE_PRE_K_1,
    normalize_grade_band,
)


def test_grade_band_normalization_matches_database_contract():
    assert normalize_grade_band("Kindergarten") == GRADE_PRE_K_1
    assert normalize_grade_band("1st Grade") == GRADE_PRE_K_1
    assert normalize_grade_band("Grade 4") == GRADE_2_5
    assert normalize_grade_band("8th grade") == GRADE_6_8
    assert normalize_grade_band(GRADE_2_5) == GRADE_2_5


def test_teacher_grade_words_fill_deterministic_checklist():
    assert orchestrator._grade_from_text("I teach first grade") == "1st Grade"
    assert orchestrator._grade_from_text("a second grade class") == "2nd Grade"


def _planning_test_session():
    session = orchestrator.create_session()
    session.phase = SessionPhase.lesson_planning
    session.storybook_analysis = StoryAnalysis(
        title="The Helpful Signal",
        characters=["Maya"],
        settings=["Neighborhood"],
        key_events=["Maya designs a safer crossing"],
        themes=["helping the community"],
        buildable_objects=["traffic signal"],
        vocabulary_opportunities=["signal", "safety", "community"],
        sel_angles=["responsible decision making"],
    )
    session.planning_state = orchestrator.planning_state_snapshot(session)
    return session


def test_static_only_build_completes_the_movement_checklist(monkeypatch):
    orchestrator._sessions.clear()
    session = _planning_test_session()

    async def fake_consultation(**_kwargs):
        return ConsultationResponse(
            response="A static traffic signal is a strong fit for this lesson.",
            planning_update=PlanningStateUpdate(
                target_grade="2nd Grade",
                duration_minutes=40,
                core_concept="community safety",
                learning_goals=["Students explain how traffic signals help a community."],
                build_object="traffic signal",
                moving_parts=[],
                movement_confirmed=True,
                static_parts=[
                    PlanningPart(part_name="signal body", movement="static"),
                    PlanningPart(part_name="base", movement="static"),
                ],
                static_parts_confirmed=True,
                constraints=["pairs"],
                literacy_focus="signal and safety vocabulary",
                sel_focus="responsible decision making",
            ),
        )

    monkeypatch.setattr(orchestrator, "handle_consultation_message", fake_consultation)
    monkeypatch.setattr(
        orchestrator,
        "retrieve_teacher_evidence",
        lambda *_args, **_kwargs: {"status": "disabled", "trace": []},
    )

    import asyncio

    result = asyncio.run(
        orchestrator.route_message(
            session.session_id,
            "There are no moving parts. Please fill out the remaining lesson choices for me.",
        )
    )

    assert result.ready_to_approve is True
    assert result.planning_state["movement_confirmed"] is True
    assert result.planning_state["moving_parts"] == []
    assert "Before we move on" not in result.response
    assert "moving parts" not in orchestrator._missing_planning_fields(result.planning_state)


def test_completed_planning_values_do_not_regress_on_later_turn(monkeypatch):
    orchestrator._sessions.clear()
    session = _planning_test_session()
    session.teacher_messages.append(
        {"role": "user", "content": "There are no moving parts; the build is fully static."}
    )
    session.planning_state = {
        "target_grade": "2nd Grade",
        "duration_minutes": 40,
        "core_concept": "community safety",
        "learning_goals": ["Students explain how signals keep people safe."],
        "build_object": "traffic signal",
        "moving_parts": [],
        "movement_confirmed": True,
        "static_parts": [{"part_name": "signal body", "movement": "static", "notes": ""}],
        "static_parts_confirmed": True,
        "constraints": ["pairs"],
        "literacy_focus": "signal vocabulary",
        "sel_focus": "responsible decision making",
    }

    async def fake_consultation(**_kwargs):
        return ConsultationResponse(
            response="We can connect that idea to the closing reflection.",
            planning_update=PlanningStateUpdate(),
        )

    monkeypatch.setattr(orchestrator, "handle_consultation_message", fake_consultation)
    monkeypatch.setattr(
        orchestrator,
        "retrieve_teacher_evidence",
        lambda *_args, **_kwargs: {"status": "disabled", "trace": []},
    )

    import asyncio

    result = asyncio.run(orchestrator.route_message(session.session_id, "That sounds good."))

    assert result.ready_to_approve is True
    assert result.planning_state["learning_goals"] == [
        "Students explain how signals keep people safe."
    ]
    assert result.planning_state["moving_parts"] == []


def test_no_movement_statement_overrides_earlier_propeller_idea():
    orchestrator._sessions.clear()
    session = _planning_test_session()
    session.teacher_messages.extend(
        [
            {"role": "user", "content": "Maybe we could use a propeller."},
            {"role": "assistant", "content": "That is one option."},
            {"role": "user", "content": "No moving parts. Everything should be static."},
        ]
    )

    state = orchestrator.planning_state_snapshot(session)

    assert state["movement_confirmed"] is True
    assert state["moving_parts"] == []


def test_gemini_client_prefers_api_key(monkeypatch):
    calls = []
    monkeypatch.setattr(vertex_gemini, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(genai, "Client", lambda **kwargs: calls.append(kwargs) or object())

    vertex_gemini._client()

    assert calls == [{"vertexai": True, "api_key": "test-key"}]
    assert vertex_gemini.auth_mode() == "api_key"


def test_gemini_client_uses_adc_without_api_key(monkeypatch):
    calls = []
    monkeypatch.setattr(vertex_gemini, "GEMINI_API_KEY", "")
    monkeypatch.setattr(vertex_gemini, "GCP_PROJECT_ID", "kidspark-test")
    monkeypatch.setattr(vertex_gemini, "VERTEX_GENERATION_LOCATION", "global")
    monkeypatch.setattr(genai, "Client", lambda **kwargs: calls.append(kwargs) or object())

    vertex_gemini._client()

    assert calls == [
        {
            "vertexai": True,
            "project": "kidspark-test",
            "location": "global",
        }
    ]
    assert vertex_gemini.auth_mode() == "application_default_credentials"


def test_retrieval_pack_is_cached_and_traced(monkeypatch):
    provider._CACHE.clear()
    calls = []

    def fake_retrieve(prompt, grade_band, seed_k):
        calls.append((prompt, grade_band, seed_k))
        return {
            "seeds": [
                {
                    "node_id": "node-1",
                    "bundle_id": "bundle-1",
                    "doc_kind": "teacher_plan",
                    "score": 0.93,
                }
            ],
            "bundles": [],
            "policies": [],
        }

    monkeypatch.setattr(provider, "KIDSPARK_RAG_ENABLED", True)
    monkeypatch.setattr(provider, "KIDSPARK_RAG_SERVICE_URL", "")
    monkeypatch.setattr(provider, "_retrieve_direct", fake_retrieve)

    first = provider.retrieve_teacher_evidence("build a plane", "1st Grade")
    second = provider.retrieve_teacher_evidence("build  a   plane", "1st Grade")

    assert first["status"] == "ok"
    assert first["trace"][0]["node_id"] == "node-1"
    assert second["cache_hit"] is True
    assert len(calls) == 1


def test_gemini_primary_falls_back(monkeypatch):
    attempts = []

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            attempts.append(model)
            if len(attempts) == 1:
                raise RuntimeError("primary unavailable")
            return SimpleNamespace(text="fallback result")

    monkeypatch.setattr(vertex_gemini, "provider_configured", lambda: True)
    monkeypatch.setattr(
        vertex_gemini,
        "_client",
        lambda: SimpleNamespace(models=FakeModels()),
    )
    monkeypatch.setattr(vertex_gemini, "_config", lambda *args, **kwargs: {})
    monkeypatch.setattr(vertex_gemini.time, "sleep", lambda _: None)

    result = vertex_gemini.generate_text("system", "user")

    assert result == "fallback result"
    assert attempts == [
        vertex_gemini.GEMINI_PRIMARY_MODEL,
        vertex_gemini.GEMINI_FALLBACK_MODEL,
    ]


def test_story_analysis_stores_rag_trace(monkeypatch):
    orchestrator._sessions.clear()
    session = orchestrator.create_session()
    analysis = StoryAnalysis(
        title="A Flying Story",
        characters=["Milo"],
        settings=["Workshop"],
        key_events=["Milo invents"],
        themes=["perseverance"],
        buildable_objects=["plane"],
        vocabulary_opportunities=["invent"],
        sel_angles=["teamwork"],
    )

    async def fake_analysis(_text):
        return analysis

    monkeypatch.setattr(orchestrator, "analyze_storybook", fake_analysis)
    monkeypatch.setattr(
        orchestrator,
        "retrieve_teacher_evidence",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "trace": [{"node_id": "node-1", "bundle_id": "bundle-1"}],
        },
    )

    import asyncio

    asyncio.run(orchestrator.run_storybook_analysis(session.session_id, "story"))

    assert session.rag_status == "ok"
    assert session.rag_trace[0]["bundle_id"] == "bundle-1"
    assert session.rag_query_signature
