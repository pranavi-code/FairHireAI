import pytest

from backend.app.domain.interviews import NextQuestionResult
from backend.app.domain.knowledge import build_seed_question_packages
from backend.app.services.adaptive_question_generation import (
    AdaptiveQuestionGenerationService,
    QuestionGenerationExhaustedError,
)
from backend.app.services.grounded_questions import (
    GroundedQuestionContentError,
    PersonalizedQuestionRequest,
)
from backend.app.services.hybrid_rag import RetrievedQuestion


def _anchors(count: int = 2) -> list[RetrievedQuestion]:
    base = next(
        package
        for package in build_seed_question_packages()
        if package.role_id == "junior_data_analyst"
        and package.competency_id == "data_visualization"
    ).model_copy(update={"validation_status": "generated_validated_for_practice"})
    selection = NextQuestionResult(
        action="ask_question",
        competency_id="data_visualization",
        question_id="da_visual_core_01",
        prompt=base.prompt,
        reason="Selected data visualization.",
    )
    anchors: list[RetrievedQuestion] = []
    for index in range(count):
        package = base.model_copy(
            update={
                "question_id": f"anchor-{index}",
                "package_key": f"anchor-{index}",
            }
        )
        row = package.model_dump(mode="json")
        row["id"] = row.pop("question_id")
        anchors.append(
            RetrievedQuestion(
                package=row,
                package_model=package,
                selection=selection,
                query="data visualization",
                hybrid_score=0.9 - index * 0.1,
            )
        )
    return anchors


def _request() -> PersonalizedQuestionRequest:
    return PersonalizedQuestionRequest(
        role_id="junior_data_analyst",
        competency_id="data_visualization",
        recent_question_prompts=[
            "Which chart would you use to show monthly sales trends?",
            "How would you visualize regional revenue comparisons?",
        ],
        recent_question_ids=["history-1", "history-2"],
        external_ai_processing_consent=True,
    )


class RecoveringQuestionService:
    def __init__(self, reject_count: int) -> None:
        self.reject_count = reject_count
        self.requests: list[PersonalizedQuestionRequest] = []
        self.anchor_ids: list[str] = []

    def generate(self, request, *, anchor_package):  # type: ignore[no-untyped-def]
        self.requests.append(request)
        self.anchor_ids.append(anchor_package.question_id)
        if len(self.requests) <= self.reject_count:
            raise GroundedQuestionContentError(
                "Gemini generated a repetitive question (same_scenario_and_task).",
                candidate_prompt=f"Rejected visualization question {len(self.requests)}",
            )
        return anchor_package.model_copy(
            update={
                "question_id": f"gemini:accepted:{len(self.requests)}",
                "package_key": f"gemini:accepted:{len(self.requests)}",
                "prompt": (
                    "A logistics manager needs to diagnose delivery delays by region and "
                    "carrier. Design a dashboard and justify the visual encodings."
                ),
                "author_type": "gemini_generated",
                "model_id": "gemini-test",
                "prompt_version": "adaptive-test-v1",
                "validation_status": "generated_validated_for_practice",
            }
        )


class AcceptingQuestionService:
    def generate(self, request, *, anchor_package):  # type: ignore[no-untyped-def]
        return anchor_package.model_copy(
            update={
                "question_id": (
                    f"gemini:{request.role_id}:{request.competency_id}:accepted"
                ),
                "package_key": (
                    f"gemini:{request.role_id}:{request.competency_id}:accepted"
                ),
                "prompt": (
                    "Describe a grounded scenario-specific approach and justify the "
                    "technical decisions you would make."
                ),
                "author_type": "gemini_generated",
                "model_id": "gemini-test",
                "prompt_version": "adaptive-test-v1",
                "validation_status": "generated_validated_for_practice",
            }
        )


def test_original_data_visualization_failure_recovers_without_user_facing_error() -> None:
    service = RecoveringQuestionService(reject_count=3)

    result = AdaptiveQuestionGenerationService(service).generate(  # type: ignore[arg-type]
        _request(),
        anchors=_anchors(2),
        correlation_id="original-data-visualization-regression",
    )

    assert result.generated.validation_status == "generated_validated_for_practice"
    assert result.attempted_candidates == 4
    assert result.rejected_candidates == 3
    assert result.strategy == "alternate_anchor"
    assert service.anchor_ids[:3] == ["anchor-0", "anchor-0", "anchor-0"]
    assert service.anchor_ids[3] == "anchor-1"


def test_rejected_candidate_context_and_new_strategy_reach_the_next_attempt() -> None:
    service = RecoveringQuestionService(reject_count=1)

    AdaptiveQuestionGenerationService(service).generate(  # type: ignore[arg-type]
        _request(),
        anchors=_anchors(1),
        correlation_id="rejection-context",
    )

    assert service.requests[0].rejected_question_prompts == []
    assert service.requests[1].rejected_question_prompts == [
        "Rejected visualization question 1"
    ]
    assert service.requests[0].generation_strategy == "preferred_anchor"
    assert service.requests[1].generation_strategy == "diverse_candidate"
    assert service.requests[1].structure_instruction


def test_scenario_and_structure_switches_are_progressive() -> None:
    service = RecoveringQuestionService(reject_count=5)

    AdaptiveQuestionGenerationService(service).generate(  # type: ignore[arg-type]
        _request(),
        anchors=_anchors(1),
        correlation_id="switch-dimensions",
    )

    names = [request.generation_strategy for request in service.requests]
    assert "scenario_switch" in names
    assert "structure_switch" in names
    assert next(
        request for request in service.requests if request.generation_strategy == "scenario_switch"
    ).scenario_instruction


def test_dynamic_fallback_is_not_static_and_uses_controlled_relaxation() -> None:
    service = RecoveringQuestionService(reject_count=7)

    result = AdaptiveQuestionGenerationService(service).generate(  # type: ignore[arg-type]
        _request(),
        anchors=_anchors(1),
        correlation_id="dynamic-fallback",
    )

    fallback = service.requests[-1]
    assert result.strategy == "controlled_dynamic_fallback"
    assert fallback.omit_anchor_wording
    assert fallback.controlled_relaxation
    assert fallback.generation_nonce
    assert "fixed wording" in (fallback.variation_instruction or "")


def test_content_exhaustion_is_a_domain_error_not_an_infrastructure_error() -> None:
    service = RecoveringQuestionService(reject_count=99)

    try:
        AdaptiveQuestionGenerationService(service).generate(  # type: ignore[arg-type]
            _request(),
            anchors=_anchors(1),
            correlation_id="domain-exhaustion",
        )
    except QuestionGenerationExhaustedError as exc:
        assert exc.attempted_candidates == 8
        assert len(exc.rejection_reasons) == 8
    else:
        raise AssertionError("Expected bounded dynamic generation exhaustion")


@pytest.mark.parametrize(
    "package",
    build_seed_question_packages(),
    ids=lambda package: f"{package.role_id}-{package.competency_id}",
)
def test_progressive_generation_is_role_and_competency_agnostic(package) -> None:  # type: ignore[no-untyped-def]
    package = package.model_copy(
        update={"validation_status": "generated_validated_for_practice"}
    )
    row = package.model_dump(mode="json")
    row["id"] = row.pop("question_id")
    anchor = RetrievedQuestion(
        package=row,
        package_model=package,
        selection=NextQuestionResult(
            action="ask_question",
            competency_id=package.competency_id,
            question_id=package.package_key.split(":", 1)[-1],
            prompt=package.prompt,
            reason="Selected role competency.",
        ),
        query="role and competency retrieval",
        hybrid_score=0.8,
    )
    request = PersonalizedQuestionRequest(
        role_id=package.role_id or "",
        competency_id=package.competency_id,
        external_ai_processing_consent=True,
    )

    result = AdaptiveQuestionGenerationService(  # type: ignore[arg-type]
        AcceptingQuestionService()
    ).generate(request, anchors=[anchor], correlation_id="cross-competency")

    assert result.generated.competency_id == package.competency_id
    assert result.generated.role_id == package.role_id
    assert result.strategy == "preferred_anchor"
