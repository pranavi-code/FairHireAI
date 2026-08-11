import httpx

from backend.app.domain.journey import EvidenceEdgeView
from backend.app.domain.roles import load_role_template
from backend.app.repositories.supabase import SupabaseAttemptRepository


def test_competency_scores_are_normalized_for_frontend_contract() -> None:
    role = load_role_template("junior_backend_developer")
    weights = {item.competency_id: item.base_weight for item in role.competencies}

    views = SupabaseAttemptRepository._competency_score_views(
        [
            {
                "competency_id": "api_design",
                "score": 0.72,
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
