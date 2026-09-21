from __future__ import annotations

from backend.app.domain.answer_evaluation import TechnicalAnswerEvaluation
from backend.app.domain.roadmap import (
    LearningResource,
    RoadmapItem,
    RoadmapResult,
    SkillGap,
)
from backend.app.providers.gemini import GeminiProviderError
from backend.app.services.grounded_guidance import GroundedGuidanceService


def _evaluation() -> TechnicalAnswerEvaluation:
    return TechnicalAnswerEvaluation(
        competency_id="api_design",
        competency_rubric_score=0.45,
        competency_coverage=0.8,
        answer_depth_and_correctness=0.45,
        answer_relevance=0.8,
        answer_structure=0.7,
        answer_completeness=0.6,
        resume_project_consistency=0.5,
        professionalism_rubric=0.9,
        evidence_confidence=0.85,
        criterion_evidence=[
            {
                "criterion": "Authorization",
                "score": 0.3,
                "rationale": "The answer did not describe an ownership check.",
            }
        ],
        missing_concepts=["object authorization"],
        weakest_criterion="Authorization",
        safety_note="Evidence-only student feedback; no hiring decision was made.",
    )


def _gap() -> SkillGap:
    return SkillGap(
        skill_gap_node_id="gap:api_design:test",
        competency_id="api_design",
        current_score=0.45,
        target_score=0.7,
        severity=0.25,
        evidence_node_ids=["evidence:test"],
    )


def _resource() -> LearningResource:
    return LearningResource(
        resource_id="RES-API",
        title="Reviewed API authorization guide",
        canonical_url="https://example.com/api",
        source_organization="Example reviewer",
        competency_ids=["api_design"],
        difficulty="beginner",
        estimated_minutes=30,
        description="A reviewed guide to endpoint authorization and ownership checks.",
        reviewer_status="approved",
        reviewer_id="faculty-reviewer",
        retrieval_scores={"api_design": 0.9},
    )


def test_gemini_guides_fixed_gaps_and_only_reviewed_rag_resources() -> None:
    responses = iter(
        [
            {
                "items": [
                    {
                        "skill_gap_node_id": "gap:api_design:test",
                        "competency_id": "api_design",
                        "title": "Strengthen endpoint authorization",
                        "rationale": (
                            "The response described validation but did not explain an "
                            "ownership check."
                        ),
                        "practice_focus": ["Add object-level authorization checks"],
                    }
                ]
            },
            {
                "items": [
                    {
                        "skill_gap_node_id": "gap:api_design:test",
                        "resource_id": "RES-API",
                        "priority": 1,
                        "rationale": (
                            "Use this reviewed guide to practise ownership checks missing "
                            "from the answer."
                        ),
                    }
                ]
            },
        ]
    )

    class FakeClient:
        def generate_json(self, **_kwargs):  # type: ignore[no-untyped-def]
            return next(responses)

    service = GroundedGuidanceService(FakeClient())  # type: ignore[arg-type]
    gap = _gap()
    resource = _resource()
    guidance = service.generate_gap_guidance(
        role_id="junior_backend_developer",
        gaps=[gap],
        evaluations=[_evaluation()],
    )
    result = service.personalize_roadmap(
        role_id="junior_backend_developer",
        gaps=[gap],
        draft=RoadmapResult(
            items=[
                RoadmapItem(
                    skill_gap_node_id=gap.skill_gap_node_id,
                    competency_id=gap.competency_id,
                    resource_id=resource.resource_id,
                    priority=1,
                    rationale="Deterministic reviewed-RAG selection.",
                )
            ],
            unresolved_skill_gap_node_ids=[],
            safety_note="Reviewed resources only.",
        ),
        resources=[resource],
        gap_guidance=guidance,
    )

    assert guidance[gap.skill_gap_node_id].practice_focus
    assert result.policy_version == "grounded-dynamic-roadmap-gemini-v1"
    assert result.items[0].resource_id == "RES-API"
    assert "ownership checks" in result.items[0].rationale


def test_gemini_cannot_replace_a_reviewed_roadmap_resource() -> None:
    class FakeClient:
        def generate_json(self, **_kwargs):  # type: ignore[no-untyped-def]
            return {
                "items": [
                    {
                        "skill_gap_node_id": "gap:api_design:test",
                        "resource_id": "UNREVIEWED",
                        "priority": 1,
                        "rationale": (
                            "This unreviewed resource must never be accepted by the service."
                        ),
                    }
                ]
            }

    gap = _gap()
    resource = _resource()
    service = GroundedGuidanceService(FakeClient())  # type: ignore[arg-type]
    try:
        service.personalize_roadmap(
            role_id="junior_backend_developer",
            gaps=[gap],
            draft=RoadmapResult(
                items=[
                    RoadmapItem(
                        skill_gap_node_id=gap.skill_gap_node_id,
                        competency_id=gap.competency_id,
                        resource_id=resource.resource_id,
                        priority=1,
                        rationale="Deterministic reviewed-RAG selection.",
                    )
                ],
                unresolved_skill_gap_node_ids=[],
                safety_note="Reviewed resources only.",
            ),
            resources=[resource],
            gap_guidance={},
        )
    except GeminiProviderError as exc:
        assert "resource set" in str(exc)
    else:
        raise AssertionError("An unreviewed Gemini resource was accepted")
