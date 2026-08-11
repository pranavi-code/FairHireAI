from fastapi.testclient import TestClient

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
    response = client.post(
        "/api/v1/roadmap/plan",
        json=request.model_dump(mode="json"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["skill_gap_node_id"] == "gap_debug"
    assert "current 0.45" in payload["items"][0]["rationale"]
