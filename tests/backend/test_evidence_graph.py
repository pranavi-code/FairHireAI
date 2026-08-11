from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.domain.evidence_graph import (
    EvidenceGraph,
    GraphEdge,
    GraphNode,
    MetricEvidence,
    ScorecardEvidence,
    ScorecardRequest,
    calculate_scorecard,
)
from backend.app.domain.roles import load_role_template
from backend.app.main import app

client = TestClient(app)


def node(node_id: str, node_type: str, attempt_id: object) -> GraphNode:
    return GraphNode(
        id=node_id,
        type=node_type,
        source="unit-test",
        attempt_id=attempt_id,
        created_at=datetime.now(timezone.utc),
        confidence=0.9,
        visibility="student",
    )


def metric(value: float, node_id: str = "prediction_1") -> MetricEvidence:
    return MetricEvidence(value=value, evidence_node_ids=[node_id])


def graph_with_prediction() -> EvidenceGraph:
    attempt_id = uuid4()
    return EvidenceGraph(
        attempt_id=attempt_id,
        nodes=[node("prediction_1", "ModelPrediction", attempt_id)],
    )


def scorecard_request(*, signal_quality: float = 0.9) -> ScorecardRequest:
    role = load_role_template()
    graph = graph_with_prediction()
    competency_ids = [item.competency_id for item in role.competencies]
    return ScorecardRequest(
        graph=graph,
        role_id=role.role_id,
        role_template_version=role.template_version,
        competency_weights={item.competency_id: item.base_weight for item in role.competencies},
        evidence=ScorecardEvidence(
            competency_rubric_scores={
                competency_id: metric(0.8) for competency_id in competency_ids
            },
            competency_coverage={competency_id: metric(0.8) for competency_id in competency_ids},
            answer_depth_and_correctness=metric(0.6),
            technical_follow_up_quality=MetricEvidence(applicable=False),
            resume_project_consistency=metric(0.9),
            answer_relevance=metric(0.8),
            answer_structure=metric(0.7),
            answer_completeness=metric(0.9),
            pace_and_filler_quality=metric(0.6),
            transcript_confidence=metric(0.9),
            follow_up_responsiveness=MetricEvidence(applicable=False),
            professionalism_rubric=metric(0.8),
            evidence_confidence=metric(0.9),
            signal_quality=metric(signal_quality),
        ),
    )


def test_graph_rejects_missing_or_wrong_typed_endpoints() -> None:
    attempt_id = uuid4()
    nodes = [
        node("question_1", "Question", attempt_id),
        node("answer_1", "AnswerSegment", attempt_id),
    ]
    valid = GraphEdge(
        id="edge_valid",
        type="answered_by",
        source="unit-test",
        attempt_id=attempt_id,
        created_at=datetime.now(timezone.utc),
        confidence=1.0,
        visibility="student",
        source_node_id="question_1",
        target_node_id="answer_1",
    )
    graph = EvidenceGraph(attempt_id=attempt_id, nodes=nodes, edges=[valid])
    assert len(graph.edges) == 1

    invalid = valid.model_copy(
        update={
            "id": "edge_invalid",
            "type": "transcribed_as",
        }
    )
    with pytest.raises(ValidationError, match="requires"):
        EvidenceGraph(attempt_id=attempt_id, nodes=nodes, edges=[invalid])

    missing = valid.model_copy(update={"target_node_id": "missing_node"})
    with pytest.raises(ValidationError, match="missing node"):
        EvidenceGraph(attempt_id=attempt_id, nodes=nodes, edges=[missing])


def test_scorecard_uses_transparent_formulas_and_excludes_delivery() -> None:
    result = calculate_scorecard(scorecard_request())
    assert result.technical_readiness == pytest.approx(0.7625)
    assert result.communication_clarity == pytest.approx(0.775)
    assert result.interview_response_quality == pytest.approx(0.876923)
    assert result.placement_readiness == pytest.approx(0.794231)
    assert result.overall_evidence_confidence == pytest.approx(0.81)
    assert result.sufficient_evidence
    assert "hiring decisions" in result.safety_note


def test_scorecard_clamps_floating_point_boundary_drift() -> None:
    request = scorecard_request()
    # The six canonical decimal weights sum to 1.0000000000000002 in binary
    # floating point. Perfect rubric scores must still remain schema-valid.
    for item in request.evidence.competency_rubric_scores.values():
        item.value = 1.0

    result = calculate_scorecard(request)

    assert result.technical_readiness <= 1.0


def test_low_signal_quality_reduces_confidence_not_capability_scores() -> None:
    high_quality = calculate_scorecard(scorecard_request(signal_quality=0.9))
    low_quality = calculate_scorecard(scorecard_request(signal_quality=0.5))
    assert low_quality.technical_readiness == high_quality.technical_readiness
    assert low_quality.communication_clarity == high_quality.communication_clarity
    assert not low_quality.sufficient_evidence
    assert low_quality.placement_readiness is None
    assert low_quality.overall_evidence_confidence == pytest.approx(0.45)


def test_scorecard_rejects_untraceable_metric_references() -> None:
    request = scorecard_request()
    request.evidence.answer_relevance.evidence_node_ids = ["missing_evidence"]
    with pytest.raises(ValueError, match="missing nodes"):
        calculate_scorecard(request)


def test_scorecard_endpoint_returns_auditable_result() -> None:
    response = client.post(
        "/api/v1/evidence/scorecard",
        json=scorecard_request().model_dump(mode="json"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["formula_version"] == "readiness-scorecard-v1"
    assert payload["placement_readiness"] == pytest.approx(0.794231)
    assert payload["sufficient_evidence"]
