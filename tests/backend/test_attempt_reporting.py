from __future__ import annotations

from uuid import uuid4

from backend.app.domain.roles import load_role_template
from backend.app.services.attempt_reporting import build_attempt_output


def _evaluation(competency_id: str) -> dict[str, object]:
    return {
        "schema_version": "technical-answer-evaluation-v1",
        "competency_id": competency_id,
        "competency_rubric_score": 0.40,
        "competency_coverage": 0.80,
        "answer_depth_and_correctness": 0.45,
        "answer_relevance": 0.80,
        "answer_structure": 0.75,
        "answer_completeness": 0.65,
        "resume_project_consistency": 0.50,
        "follow_up_responsiveness": None,
        "professionalism_rubric": 0.90,
        "evidence_confidence": 0.90,
        "criterion_evidence": [
            {
                "criterion": "Reviewed criterion",
                "score": 0.40,
                "rationale": "The transcript contains partial evidence only.",
                "citations": [],
            }
        ],
        "missing_concepts": ["A required technical detail"],
        "weakest_criterion": "Reviewed criterion",
        "high_confidence_resume_contradiction": False,
        "safety_note": "Evidence-only student feedback; no hiring decision was made.",
    }


def test_report_builder_creates_evidence_backed_gaps_and_rag_roadmap() -> None:
    role = load_role_template("junior_backend_developer")
    attempt_id = uuid4()
    user_id = uuid4()
    questions: list[dict[str, object]] = []
    answers: list[dict[str, object]] = []
    analyses: list[dict[str, object]] = []
    resources: list[dict[str, object]] = []

    for competency in role.competencies:
        question_id = uuid4()
        answer_id = uuid4()
        questions.append(
            {
                "id": str(question_id),
                "competency_id": competency.competency_id,
                "prompt_snapshot": competency.core_question.prompt,
                "question_package_version": "v1",
            }
        )
        answers.append({"id": str(answer_id), "question_id": str(question_id)})
        analyses.append(
            {
                "answer_id": str(answer_id),
                "technical_evaluation": _evaluation(competency.competency_id),
                "delivery_metrics": {
                    "pace_and_filler_quality": 0.80,
                    "transcript_confidence": 0.95,
                    "signal_quality": 0.90,
                },
                "base_multimodal_interview_signal": 0.55,
                "signal_quality": 0.90,
                "transcript_confidence": 0.95,
                "transcript_text": "A partial but relevant technical response.",
                "model_run_name": "fi_v2_mag_bert",
                "model_checkpoint_sha256": "a" * 64,
                "evaluator_model_id": "gemini-test-contract",
            }
        )
        resources.append(
            {
                "id": f"RES-{competency.competency_id}",
                "title": f"Reviewed {competency.name} guide",
                "canonical_url": f"https://example.com/{competency.competency_id}",
                "source_organization": "Example reviewer",
                "competency_ids": [competency.competency_id],
                "difficulty": "beginner",
                "estimated_minutes": 30,
                "description": "A reviewed practice resource for this competency.",
                "reviewer_status": "approved",
                "reviewer_id": "faculty-reviewer",
                "retrieval_scores": {competency.competency_id: 0.85},
            }
        )

    retrieved_gaps = []

    def retrieve(gaps):  # type: ignore[no-untyped-def]
        retrieved_gaps.extend(gaps)
        return resources

    output = build_attempt_output(
        attempt={
            "id": str(attempt_id),
            "user_id": str(user_id),
            "role_id": role.role_id,
            "competency_weights": {
                item.competency_id: item.base_weight for item in role.competencies
            },
        },
        questions=questions,
        answers=answers,
        analyses=analyses,
        resume_claims=[],
        resources=[],
        resource_retriever=retrieve,
    )

    competency_ids = {item.competency_id for item in role.competencies}
    gap_nodes = [item for item in output.nodes if item["node_type"] == "SkillGap"]
    assert output.scorecard["sufficient_evidence"] is True
    assert {item["attributes"]["competency_id"] for item in gap_nodes} == competency_ids
    assert {item.competency_id for item in retrieved_gaps} == competency_ids
    assert {
        str(item["skill_gap_node_id"]).split(":")[1]
        for item in output.roadmap_items
    } == competency_ids
    assert all("Hybrid RAG" in str(item["rationale"]) for item in output.roadmap_items)


def test_report_graph_identifiers_are_unique_across_attempts_for_the_same_user() -> None:
    role = load_role_template("junior_backend_developer")
    user_id = uuid4()

    def output_for(attempt_id):  # type: ignore[no-untyped-def]
        questions: list[dict[str, object]] = []
        answers: list[dict[str, object]] = []
        analyses: list[dict[str, object]] = []
        for competency in role.competencies:
            question_id = uuid4()
            answer_id = uuid4()
            questions.append(
                {
                    "id": str(question_id),
                    "competency_id": competency.competency_id,
                    "prompt_snapshot": competency.core_question.prompt,
                    "question_package_version": "v1",
                }
            )
            answers.append({"id": str(answer_id), "question_id": str(question_id)})
            analyses.append(
                {
                    "answer_id": str(answer_id),
                    "technical_evaluation": _evaluation(competency.competency_id),
                    "delivery_metrics": {
                        "pace_and_filler_quality": 0.8,
                        "transcript_confidence": 0.95,
                        "signal_quality": 0.9,
                    },
                    "base_multimodal_interview_signal": 0.55,
                    "signal_quality": 0.9,
                    "transcript_confidence": 0.95,
                    "transcript_text": "A grounded technical response.",
                    "model_run_name": "fi_v2_mag_bert",
                    "model_checkpoint_sha256": "a" * 64,
                    "evaluator_model_id": "gemini-test-contract",
                }
            )
        return build_attempt_output(
            attempt={
                "id": str(attempt_id),
                "user_id": str(user_id),
                "role_id": role.role_id,
                "competency_weights": {
                    item.competency_id: item.base_weight for item in role.competencies
                },
            },
            questions=questions,
            answers=answers,
            analyses=analyses,
            resume_claims=[],
            resources=[],
        )

    first = output_for(uuid4())
    second = output_for(uuid4())

    first_node_ids = {str(item["id"]) for item in first.nodes}
    second_node_ids = {str(item["id"]) for item in second.nodes}
    first_edge_ids = {str(item["id"]) for item in first.edges}
    second_edge_ids = {str(item["id"]) for item in second.edges}
    assert first_node_ids.isdisjoint(second_node_ids)
    assert first_edge_ids.isdisjoint(second_edge_ids)
    assert max(map(len, first_node_ids | second_node_ids)) <= 120
    assert max(map(len, first_edge_ids | second_edge_ids)) <= 120
