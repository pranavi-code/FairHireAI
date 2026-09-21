from uuid import uuid4

import httpx
import pytest

from backend.app.domain.journey import EvidenceEdgeView
from backend.app.domain.roles import load_role_template
from backend.app.repositories.supabase import (
    SupabaseAttemptRepository,
    SupabaseRepositoryError,
)


def test_competency_scores_are_normalized_for_frontend_contract() -> None:
    role = load_role_template("junior_backend_developer")
    weights = {item.competency_id: item.base_weight for item in role.competencies}

    views = SupabaseAttemptRepository._competency_score_views(
        [
            {
                "competency_id": "api_design",
                "score": 0.72,
                "coverage": 0.8,
                "sufficient_evidence": True,
                "evidence_node_ids": ["evidence:api"],
            }
        ],
        role=role,
        competency_weights=weights,
    )

    assert len(views) == 6
    api_design = next(item for item in views if item.competency_id == "api_design")
    assert api_design.name == "API Design"
    assert api_design.score == 0.72
    assert api_design.coverage == 0.8
    assert api_design.sufficient_evidence
    assert api_design.evidence_node_ids == ["evidence:api"]
    assert all(item.score is None for item in views if item.competency_id != "api_design")


def test_evidence_edge_serializes_with_frontend_field_names() -> None:
    edge = EvidenceEdgeView(
        id="edge-1",
        from_node_id="node-a",
        to_node_id="node-b",
        relation="supports",
        confidence=0.8,
    )

    assert edge.model_dump(by_alias=True) == {
        "id": "edge-1",
        "from": "node-a",
        "to": "node-b",
        "relation": "supports",
        "confidence": 0.8,
    }


def test_evidence_node_exposes_persisted_rubric_details() -> None:
    view = SupabaseAttemptRepository._evidence_node_view(
        {
            "id": "evidence:answer-1",
            "node_type": "EvidenceClaim",
            "normalized_text": "Explained input validation",
            "confidence": 0.86,
            "attributes": {
                "competency_id": "api_design",
                "criterion_evidence": [
                    {
                        "criterion": "Validation",
                        "score": 0.75,
                        "rationale": "The answer describes schema validation.",
                        "citations": [
                            {
                                "text": "validate the request body",
                                "start_seconds": 1.2,
                                "end_seconds": 3.4,
                            }
                        ],
                    }
                ],
                "missing_concepts": ["idempotency"],
            },
        }
    )

    assert view.criterion_evidence[0]["criterion"] == "Validation"
    assert view.criterion_evidence[0]["citations"][0]["text"] == "validate the request body"
    assert view.missing_concepts == ["idempotency"]


def test_progress_accepts_postgrest_to_one_scorecard_object() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rest/v1/attempts"
        return httpx.Response(
            200,
            json=[
                {
                    "id": "0d3aca63-1135-450d-a7d3-a34df94f1f3b",
                    "role_id": "junior_backend_developer",
                    "completed_at": "2026-08-04T12:00:00Z",
                    "scorecards": {
                        "placement_readiness": 0.72,
                        "sufficient_evidence": True,
                        "overall_evidence_confidence": 0.81,
                        "insufficiency_reasons": [],
                        "competency_scores": [],
                    },
                }
            ],
        )

    repository = SupabaseAttemptRepository(
        base_url="https://example.supabase.co",
        publishable_key="publishable-test-key",
        access_token="user-test-token",
        transport=httpx.MockTransport(handler),
    )
    try:
        progress = repository.progress()
    finally:
        repository.close()

    assert len(progress.attempts) == 1
    assert progress.attempts[0].placement_readiness == 0.72
    assert progress.attempts[0].sufficient_evidence
    assert progress.attempts[0].overall_evidence_confidence == 0.81


def test_recent_same_role_question_history_is_bounded_and_user_rls_scoped() -> None:
    current_attempt = uuid4()
    previous_attempt = uuid4()
    question_id = uuid4()
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/rest/v1/attempts":
            assert request.url.params["role_id"] == "eq.junior_backend_developer"
            assert request.url.params["id"] == f"neq.{current_attempt}"
            assert request.url.params["status"] == "in.(interviewing,processing,completed,failed)"
            return httpx.Response(200, json=[{"id": str(previous_attempt)}])
        assert request.url.path == "/rest/v1/interview_questions"
        assert str(previous_attempt) in request.url.params["attempt_id"]
        assert request.url.params["competency_id"] == "eq.api_design"
        return httpx.Response(
            200,
            json=[
                {
                    "id": str(question_id),
                    "attempt_id": str(previous_attempt),
                    "question_template_id": "gemini:api:history",
                    "competency_id": "api_design",
                    "prompt_snapshot": "A previously generated API design question.",
                    "is_follow_up": False,
                    "sequence_number": 1,
                    "selection_reason": "Generated from a reviewed RAG anchor.",
                    "expected_concepts_snapshot": [],
                    "rubric_snapshot": {},
                    "source_mapping_snapshot": {},
                    "created_at": "2026-09-13T10:00:00Z",
                }
            ],
        )

    repository = SupabaseAttemptRepository(
        base_url="https://example.supabase.co",
        publishable_key="publishable-test-key",
        access_token="user-test-token",
        transport=httpx.MockTransport(handler),
    )
    try:
        history = repository.recent_same_role_questions(
            role_id="junior_backend_developer",
            competency_id="api_design",
            exclude_attempt_id=current_attempt,
        )
    finally:
        repository.close()

    assert [item.prompt_snapshot for item in history] == [
        "A previously generated API design question."
    ]
    assert seen == ["/rest/v1/attempts", "/rest/v1/interview_questions"]


def test_recent_question_history_retries_read_timeout_then_reports_service_unavailable() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    repository = SupabaseAttemptRepository(
        base_url="https://example.supabase.co",
        publishable_key="publishable-test-key",
        access_token="user-test-token",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(SupabaseRepositoryError) as raised:
            repository.recent_same_role_questions(
                role_id="junior_backend_developer",
                competency_id="api_design",
                exclude_attempt_id=uuid4(),
            )
    finally:
        repository.close()

    assert calls == 2
    assert raised.value.status_code == 503
