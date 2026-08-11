from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.domain.interviews import (
    CompetencyProgress,
    NextQuestionRequest,
    select_next_question,
)
from backend.app.domain.resume import ResumeEvidence, summarize_resume_evidence
from backend.app.domain.roles import load_role_template
from backend.app.main import app

client = TestClient(app)


def role_weights() -> dict[str, float]:
    role = load_role_template()
    return {competency.competency_id: competency.base_weight for competency in role.competencies}


def request_with_progress(
    progress: list[CompetencyProgress],
    *,
    current: str | None = None,
) -> NextQuestionRequest:
    role = load_role_template()
    return NextQuestionRequest(
        attempt_id=uuid4(),
        role_id=role.role_id,
        role_template_version=role.template_version,
        competency_weights=role_weights(),
        progress=progress,
        current_competency_id=current,
    )


def test_selector_starts_with_highest_weight_first_template_competency() -> None:
    result = select_next_question(request_with_progress([]))
    assert result.action == "ask_question"
    assert result.competency_id == "programming_fundamentals"
    assert result.question_id == "pf_core_01"
    assert not result.is_follow_up


def test_selector_asks_at_most_one_approved_follow_up() -> None:
    weak = CompetencyProgress(
        competency_id="api_design",
        core_answered=True,
        competency_coverage=0.50,
        rubric_match=0.55,
        answer_completeness=0.80,
        evidence_confidence=0.90,
        weakest_criterion="authorization",
    )
    result = select_next_question(request_with_progress([weak], current="api_design"))
    assert result.is_follow_up
    assert result.question_id == "api_follow_01"

    weak.follow_up_used = True
    next_result = select_next_question(request_with_progress([weak], current="api_design"))
    assert not next_result.is_follow_up
    assert next_result.competency_id == "programming_fundamentals"


def test_selector_completes_when_all_core_and_follow_up_rules_are_satisfied() -> None:
    progress = [
        CompetencyProgress(
            competency_id=competency_id,
            core_answered=True,
            follow_up_used=False,
            competency_coverage=0.85,
            rubric_match=0.80,
            answer_completeness=0.80,
            evidence_confidence=0.90,
        )
        for competency_id in role_weights()
    ]
    result = select_next_question(request_with_progress(progress))
    assert result.action == "complete"
    assert result.question_id is None


def test_resume_evidence_requires_traceable_source_and_unique_ids() -> None:
    payload = {
        "document_sha256": "a" * 64,
        "extractor_name": "resume-parser",
        "extractor_version": "1.0.0",
        "claims": [
            {
                "claim_id": "project_api",
                "claim_type": "project",
                "normalized_text": "Built a REST API",
                "source": {
                    "page": 1,
                    "start_character": 10,
                    "end_character": 45,
                    "source_text": "Built a REST API using FastAPI",
                },
                "confidence": 0.92,
                "normalized_skills": ["fastapi", "rest api"],
            },
            {
                "claim_id": "skill_sql",
                "claim_type": "skill",
                "normalized_text": "SQL",
                "source": {
                    "page": 1,
                    "start_character": 50,
                    "end_character": 53,
                    "source_text": "SQL",
                },
                "confidence": 0.55,
                "normalized_skills": ["sql"],
            },
        ],
    }
    evidence = ResumeEvidence.model_validate(payload)
    summary = summarize_resume_evidence(evidence)
    assert summary.claim_count == 2
    assert summary.counts_by_type["project"] == 1
    assert summary.low_confidence_claim_ids == ["skill_sql"]

    payload["claims"][1]["claim_id"] = "project_api"
    with pytest.raises(ValidationError, match="unique"):
        ResumeEvidence.model_validate(payload)


def test_resume_and_question_endpoints_use_the_validated_domain_contracts() -> None:
    evidence_response = client.post(
        "/api/v1/resume-evidence/validate",
        json={
            "document_sha256": "b" * 64,
            "extractor_name": "resume-parser",
            "extractor_version": "1.0.0",
            "claims": [],
        },
    )
    assert evidence_response.status_code == 200
    assert evidence_response.json()["claim_count"] == 0

    request = request_with_progress([])
    question_response = client.post(
        "/api/v1/interviews/next-question",
        json=request.model_dump(mode="json"),
    )
    assert question_response.status_code == 200
    assert question_response.json()["question_id"] == "pf_core_01"
