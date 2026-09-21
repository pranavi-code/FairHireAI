from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.api.dependencies import authenticated_user_id
from backend.app.domain.roadmap import (
    LearningResource,
    RoadmapRequest,
    SkillGap,
    build_roadmap,
)
from backend.app.main import app

client = TestClient(app)


def resource(
    resource_id: str,
    competency_id: str,
    *,
    status: str = "approved",
    retrieval_score: float = 0.0,
) -> LearningResource:
    return LearningResource(
        resource_id=resource_id,
        title=f"Learning resource {resource_id}",
        canonical_url=f"https://docs.example.org/{resource_id}",
        source_organization="Faculty-reviewed source",
        competency_ids=[competency_id],
        difficulty="beginner",
        estimated_minutes=45,
        description="A concrete reviewed learning activity for the competency.",
        reviewer_status=status,
        reviewer_id="reviewer_1" if status == "approved" else None,
        retrieval_scores={competency_id: retrieval_score},
    )


def test_roadmap_uses_only_approved_matching_resources() -> None:
    request = RoadmapRequest(
        gaps=[
            SkillGap(
                skill_gap_node_id="gap_api",
                competency_id="api_design",
                current_score=0.4,
                target_score=0.75,
                severity=0.8,
                evidence_node_ids=["evidence_api"],
            ),
            SkillGap(
                skill_gap_node_id="gap_database",
                competency_id="database_reasoning",
                current_score=0.5,
                target_score=0.75,
                severity=0.6,
                evidence_node_ids=["evidence_database"],
            ),
        ],
        resources=[
            resource("approved_api", "api_design"),
            resource("pending_database", "database_reasoning", status="pending"),
        ],
    )
    result = build_roadmap(request)
    assert [item.resource_id for item in result.items] == ["approved_api"]
    assert result.unresolved_skill_gap_node_ids == ["gap_database"]


def test_roadmap_endpoint_returns_traceable_rationale() -> None:
    request = RoadmapRequest(
        gaps=[
            SkillGap(
                skill_gap_node_id="gap_debug",
                competency_id="debugging_problem_solving",
                current_score=0.45,
                target_score=0.7,
                severity=0.7,
                evidence_node_ids=["evidence_debug"],
            )
        ],
        resources=[resource("approved_debug", "debugging_problem_solving")],
    )
    app.dependency_overrides[authenticated_user_id] = uuid4
    try:
        response = client.post(
            "/api/v1/roadmap/plan",
            json=request.model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(authenticated_user_id, None)
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["skill_gap_node_id"] == "gap_debug"
    assert "current 0.45" in payload["items"][0]["rationale"]


def test_roadmap_prefers_the_highest_hybrid_retrieval_score() -> None:
    gap = SkillGap(
        skill_gap_node_id="gap_api",
        competency_id="api_design",
        current_score=0.4,
        target_score=0.7,
        severity=0.3,
        evidence_node_ids=["evidence_api"],
    )
    result = build_roadmap(
        RoadmapRequest(
            gaps=[gap],
            resources=[
                resource("lower_score", "api_design", retrieval_score=0.2),
                resource("higher_score", "api_design", retrieval_score=0.9),
            ],
            maximum_resources_per_gap=1,
        )
    )

    assert [item.resource_id for item in result.items] == ["higher_score"]
    assert "Hybrid RAG retrieved" in result.items[0].rationale


def test_roadmap_ignores_resources_for_other_supported_roles() -> None:
    result = build_roadmap(
        RoadmapRequest(
            role_id="junior_data_analyst",
            gaps=[
                SkillGap(
                    skill_gap_node_id="gap_sql",
                    competency_id="data_analysis_sql",
                    current_score=0.4,
                    target_score=0.7,
                    severity=0.3,
                    evidence_node_ids=["evidence_sql"],
                )
            ],
            resources=[
                resource("python_errors", "programming_fundamentals"),
                resource("approved_sql", "data_analysis_sql"),
            ],
        )
    )

    assert [item.resource_id for item in result.items] == ["approved_sql"]
    assert result.unresolved_skill_gap_node_ids == []
