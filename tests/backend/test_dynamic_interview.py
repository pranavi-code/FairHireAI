from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from backend.app.api.v1 import journey
from backend.app.config import Settings
from backend.app.domain.attempts import AttemptRecord
from backend.app.domain.interviews import NextQuestionResult
from backend.app.domain.journey import PersistedQuestion
from backend.app.domain.knowledge import build_seed_question_packages
from backend.app.domain.roles import load_role_template
from backend.app.providers.gemini import GeminiProviderError
from backend.app.repositories.supabase import SupabaseRepositoryError
from backend.app.services.grounded_questions import GroundedQuestionContentError
from backend.app.services.hybrid_rag import RetrievedQuestion


class DynamicInterviewRepository:
    def __init__(
        self,
        *,
        consent: bool = True,
        role_id: str = "junior_backend_developer",
        competency_id: str | None = None,
    ) -> None:
        self.consent = consent
        self.closed = False
        self.persisted_selection = None
        self.persist_count = 0
        self.persisted_kwargs: dict[str, object] = {}
        self.attempt_id = uuid4()
        self.user_id = uuid4()
        role = load_role_template(role_id)
        now = datetime.now(timezone.utc)
        self.attempt = AttemptRecord(
            id=self.attempt_id,
            user_id=self.user_id,
            role_id=role.role_id,
            role_template_version=role.template_version,
            assessment_profile_source="approved_role",
            assessment_profile_version="approved-role-selection-v2",
            status="role_confirmed",
            competency_weights={
                item.competency_id: item.base_weight for item in role.competencies
            },
            created_at=now,
            updated_at=now,
        )
        package = next(
            item
            for item in build_seed_question_packages()
            if item.role_id == role_id
            and (competency_id is None or item.competency_id == competency_id)
        ).model_copy(
            update={"validation_status": "generated_validated_for_practice"}
        )
        self.package_model = package
        self.package = package.model_dump(mode="json")
        self.package["id"] = self.package.pop("question_id")

    def get(self, _attempt_id: UUID) -> AttemptRecord:
        return self.attempt

    def list_questions(self, _attempt_id: UUID) -> list[PersistedQuestion]:
        return []

    def validated_question_package(self, **_kwargs):  # type: ignore[no-untyped-def]
        return self.package

    def external_ai_consent(self, _attempt_id: UUID) -> bool:
        return self.consent

    def question_personalization_context(self, _attempt_id: UUID):  # type: ignore[no-untyped-def]
        return {
            "candidate_skill_terms": ["Python"],
            "jd_skill_terms": ["REST"],
            "resume_evidence_summaries": ["Built a student API."],
        }

    def recent_same_role_questions(self, **_kwargs):  # type: ignore[no-untyped-def]
        return []

    def persist_question(self, attempt_id, selection, **kwargs):  # type: ignore[no-untyped-def]
        self.persist_count += 1
        self.persisted_selection = selection
        self.persisted_kwargs = kwargs
        return PersistedQuestion(
            id=uuid4(),
            attempt_id=attempt_id,
            question_template_id=selection.question_id,
            competency_id=selection.competency_id,
            prompt_snapshot=kwargs["prompt_override"],
            is_follow_up=selection.is_follow_up,
            sequence_number=1,
            selection_reason=selection.reason,
            question_package_id=self.package["id"],
            question_package_version="1.0.0",
            expected_concepts_snapshot=self.package["expected_concepts"],
            rubric_snapshot=self.package["rubric"],
            source_mapping_snapshot=self.package["source_to_concept_mapping"],
            model_id=kwargs["model_id"],
            prompt_version=kwargs["prompt_version"],
            created_at=datetime.now(timezone.utc),
        )

    def transition(self, _attempt_id: UUID, _status: str) -> AttemptRecord:
        return self.attempt

    def close(self) -> None:
        self.closed = True


def _patch_dynamic_services(monkeypatch, repository: DynamicInterviewRepository) -> None:  # type: ignore[no-untyped-def]
    generated = repository.package_model.model_copy(
        update={
            "question_id": "gemini:dynamic:unique-question",
            "package_key": "gemini:dynamic:unique-question",
            "prompt": "How would you validate and authorize a new REST endpoint for this project?",
            "author_type": "gemini_generated",
            "model_id": "gemini-test",
            "prompt_version": "grounded-adaptive-question-gemini-v2",
            "validation_status": "generated_validated_for_practice",
        }
    )

    class FakeGeminiClient:
        def __init__(self, **_kwargs):  # type: ignore[no-untyped-def]
            pass

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args):  # type: ignore[no-untyped-def]
            return None

    class FakeRag:
        def __init__(self, _client):  # type: ignore[no-untyped-def]
            pass

        def retrieve_question_candidates(  # type: ignore[no-untyped-def]
            self, _repository, **kwargs
        ):
            return [
                RetrievedQuestion(
                    package=repository.package,
                    package_model=repository.package_model,
                    selection=kwargs["selection"],
                    query="synthetic retrieval query",
                    hybrid_score=0.8,
                )
            ]

    class FakeQuestionService:
        def __init__(self, _client):  # type: ignore[no-untyped-def]
            pass

        def generate(self, _request, **_kwargs):  # type: ignore[no-untyped-def]
            return generated

    monkeypatch.setattr(journey, "GeminiClient", FakeGeminiClient)
    monkeypatch.setattr(journey, "HybridRagService", FakeRag)
    monkeypatch.setattr(journey, "GroundedQuestionService", FakeQuestionService)
    monkeypatch.setattr(
        journey,
        "get_settings",
        lambda: Settings(gemini_api_key="test-key"),
    )


def test_student_journey_persists_a_new_gemini_question_not_anchor_wording(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    repository = DynamicInterviewRepository()
    _patch_dynamic_services(monkeypatch, repository)

    result = journey.next_persisted_question(repository.attempt_id, repository)  # type: ignore[arg-type]

    assert result.question is not None
    assert result.question.prompt_snapshot != repository.package["prompt"]
    assert result.question.question_template_id == "gemini:dynamic:unique-question"
    assert result.question.model_id == "gemini-test"
    assert result.question.prompt_version == "grounded-adaptive-question-gemini-v2"
    assert "history-aware" in result.question.selection_reason
    assert repository.closed


def test_live_journey_does_not_fall_back_to_a_fixed_question_without_ai_consent() -> None:
    repository = DynamicInterviewRepository(consent=False)

    with pytest.raises(HTTPException) as raised:
        journey.next_persisted_question(repository.attempt_id, repository)  # type: ignore[arg-type]

    assert raised.value.status_code == 403
    assert raised.value.detail["code"] == "external_ai_processing_consent_required"
    assert repository.persisted_selection is None
    assert repository.closed


def test_student_journey_recovers_from_rejected_gemini_content_without_503(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    repository = DynamicInterviewRepository()
    generated = repository.package_model.model_copy(
        update={
            "question_id": "gemini:dynamic:retry-success",
            "package_key": "gemini:dynamic:retry-success",
            "prompt": "How would you diagnose and safely correct an authorization failure?",
            "author_type": "gemini_generated",
            "model_id": "gemini-test",
            "prompt_version": "grounded-adaptive-question-gemini-v2",
            "validation_status": "generated_validated_for_practice",
        }
    )
    calls = 0
    variation_strategies: list[str | None] = []

    class FakeGeminiClient:
        def __init__(self, **_kwargs):  # type: ignore[no-untyped-def]
            pass

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args):  # type: ignore[no-untyped-def]
            return None

    class FakeRag:
        def __init__(self, _client):  # type: ignore[no-untyped-def]
            pass

        def retrieve_question_candidates(  # type: ignore[no-untyped-def]
            self, _repository, **kwargs
        ):
            return [
                RetrievedQuestion(
                    package=repository.package,
                    package_model=repository.package_model,
                    selection=kwargs["selection"],
                    query="synthetic retrieval query",
                    hybrid_score=0.8,
                )
            ]

    class FlakyQuestionService:
        def __init__(self, _client):  # type: ignore[no-untyped-def]
            pass

        def generate(self, request, **_kwargs):  # type: ignore[no-untyped-def]
            nonlocal calls
            calls += 1
            variation_strategies.append(request.variation_instruction)
            if calls < 3:
                raise GroundedQuestionContentError("synthetic grounding rejection")
            return generated

    monkeypatch.setattr(journey, "GeminiClient", FakeGeminiClient)
    monkeypatch.setattr(journey, "HybridRagService", FakeRag)
    monkeypatch.setattr(journey, "GroundedQuestionService", FlakyQuestionService)
    monkeypatch.setattr(journey, "get_settings", lambda: Settings(gemini_api_key="test-key"))

    result = journey.next_persisted_question(repository.attempt_id, repository)  # type: ignore[arg-type]

    assert calls == 3
    assert len(set(variation_strategies)) == 3
    assert all(variation_strategies)
    assert result.question is not None
    assert result.question.question_template_id == "gemini:dynamic:retry-success"


def test_original_data_analyst_visualization_api_succeeds_after_three_rejections(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    repository = DynamicInterviewRepository(
        role_id="junior_data_analyst",
        competency_id="data_visualization",
    )
    package_id = str(repository.package["id"])
    prior_attempt = uuid4()
    historical_prompts = [
        "Which chart would you use to show monthly sales trends?",
        "How would you visualize regional revenue comparisons?",
        "Design a conversion funnel dashboard for an ecommerce team.",
    ]
    historical_questions = [
        PersistedQuestion(
            id=uuid4(),
            attempt_id=prior_attempt,
            question_template_id=f"gemini:historical:{index}",
            competency_id="data_visualization",
            prompt_snapshot=prompt,
            is_follow_up=False,
            sequence_number=index,
            selection_reason="Previously delivered question.",
            question_package_id=package_id,
            question_package_version="1.0.0",
            expected_concepts_snapshot=[],
            rubric_snapshot={},
            source_mapping_snapshot={},
            model_id="gemini-historical",
            prompt_version="historical-v1",
            created_at=datetime.now(timezone.utc),
        )
        for index, prompt in enumerate(historical_prompts, start=1)
    ]
    repository.recent_same_role_questions = (  # type: ignore[method-assign]
        lambda **_kwargs: historical_questions
    )
    generated = repository.package_model.model_copy(
        update={
            "question_id": "gemini:data-visualization:recovered",
            "package_key": "gemini:data-visualization:recovered",
            "prompt": (
                "A logistics manager needs to diagnose delivery delays by region and "
                "carrier. Design a dashboard and justify the visual encodings."
            ),
            "author_type": "gemini_generated",
            "model_id": "gemini-test",
            "prompt_version": "grounded-adaptive-question-gemini-v2",
            "validation_status": "generated_validated_for_practice",
        }
    )
    generation_requests = []

    class FakeGeminiClient:
        def __init__(self, **_kwargs):  # type: ignore[no-untyped-def]
            pass

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args):  # type: ignore[no-untyped-def]
            return None

    class FakeRag:
        def __init__(self, _client):  # type: ignore[no-untyped-def]
            pass

        def retrieve_question_candidates(  # type: ignore[no-untyped-def]
            self, _repository, **kwargs
        ):
            anchor = RetrievedQuestion(
                package=repository.package,
                package_model=repository.package_model,
                selection=kwargs["selection"],
                query="data analyst visualization retrieval",
                hybrid_score=0.8,
            )
            alternate_model = repository.package_model.model_copy(
                update={
                    "question_id": "data-visualization-alternate-anchor",
                    "package_key": "data-visualization-alternate-anchor",
                }
            )
            alternate_row = alternate_model.model_dump(mode="json")
            alternate_row["id"] = alternate_row.pop("question_id")
            return [
                anchor,
                RetrievedQuestion(
                    package=alternate_row,
                    package_model=alternate_model,
                    selection=kwargs["selection"],
                    query="data analyst visualization retrieval",
                    hybrid_score=0.7,
                ),
            ]

    class RecoveringQuestionService:
        def __init__(self, _client):  # type: ignore[no-untyped-def]
            pass

        def generate(self, request, **_kwargs):  # type: ignore[no-untyped-def]
            generation_requests.append(request)
            if len(generation_requests) <= 3:
                raise GroundedQuestionContentError(
                    "synthetic repetition rejection",
                    candidate_prompt=f"Rejected candidate {len(generation_requests)}",
                )
            return generated

    monkeypatch.setattr(
        journey,
        "select_next_question",
        lambda _request: NextQuestionResult(
            action="ask_question",
            competency_id="data_visualization",
            question_id=repository.package_model.package_key.split(":", 1)[-1],
            prompt=repository.package_model.prompt,
            reason="Selected the next uncovered competency.",
        ),
    )
    monkeypatch.setattr(journey, "GeminiClient", FakeGeminiClient)
    monkeypatch.setattr(journey, "HybridRagService", FakeRag)
    monkeypatch.setattr(journey, "GroundedQuestionService", RecoveringQuestionService)
    monkeypatch.setattr(journey, "get_settings", lambda: Settings(gemini_api_key="test-key"))

    result = journey.next_persisted_question(repository.attempt_id, repository)  # type: ignore[arg-type]

    assert result.question is not None
    assert result.question.question_template_id == "gemini:data-visualization:recovered"
    assert len(generation_requests) == 4
    assert generation_requests[0].recent_question_prompts == historical_prompts
    assert generation_requests[3].generation_strategy == "alternate_anchor"
    assert generation_requests[3].rejected_question_prompts == [
        "Rejected candidate 1",
        "Rejected candidate 2",
        "Rejected candidate 3",
    ]
    assert repository.persisted_selection is not None
    assert repository.persist_count == 1


def test_actual_gemini_unavailability_remains_an_infrastructure_503(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    repository = DynamicInterviewRepository()

    class FakeGeminiClient:
        def __init__(self, **_kwargs):  # type: ignore[no-untyped-def]
            pass

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args):  # type: ignore[no-untyped-def]
            return None

    class UnavailableRag:
        def __init__(self, _client):  # type: ignore[no-untyped-def]
            pass

        def retrieve_question_candidates(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            raise GeminiProviderError(
                "synthetic provider outage",
                status_code=503,
                retryable=True,
            )

    monkeypatch.setattr(journey, "GeminiClient", FakeGeminiClient)
    monkeypatch.setattr(journey, "HybridRagService", UnavailableRag)
    monkeypatch.setattr(journey, "get_settings", lambda: Settings(gemini_api_key="test-key"))

    with pytest.raises(HTTPException) as raised:
        journey.next_persisted_question(repository.attempt_id, repository)  # type: ignore[arg-type]

    assert raised.value.status_code == 503
    assert raised.value.detail["code"] == "gemini_temporarily_unavailable"
    assert repository.persist_count == 0


def test_student_journey_returns_domain_conflict_after_all_content_rejections(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    repository = DynamicInterviewRepository()
    calls = 0

    class FakeGeminiClient:
        def __init__(self, **_kwargs):  # type: ignore[no-untyped-def]
            pass

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args):  # type: ignore[no-untyped-def]
            return None

    class FakeRag:
        def __init__(self, _client):  # type: ignore[no-untyped-def]
            pass

        def retrieve_question_candidates(  # type: ignore[no-untyped-def]
            self, _repository, **kwargs
        ):
            return [
                RetrievedQuestion(
                    package=repository.package,
                    package_model=repository.package_model,
                    selection=kwargs["selection"],
                    query="synthetic retrieval query",
                    hybrid_score=0.8,
                )
            ]

    class RejectingQuestionService:
        def __init__(self, _client):  # type: ignore[no-untyped-def]
            pass

        def generate(self, _request, **_kwargs):  # type: ignore[no-untyped-def]
            nonlocal calls
            calls += 1
            raise GroundedQuestionContentError("synthetic grounding rejection")

    monkeypatch.setattr(journey, "GeminiClient", FakeGeminiClient)
    monkeypatch.setattr(journey, "HybridRagService", FakeRag)
    monkeypatch.setattr(journey, "GroundedQuestionService", RejectingQuestionService)
    monkeypatch.setattr(journey, "get_settings", lambda: Settings(gemini_api_key="test-key"))

    with pytest.raises(HTTPException) as raised:
        journey.next_persisted_question(repository.attempt_id, repository)  # type: ignore[arg-type]

    assert calls == 8
    assert raised.value.status_code == 409
    assert raised.value.detail["code"] == "dynamic_question_generation_exhausted"
    assert "progressive anchor" in raised.value.detail["message"]


def test_student_journey_continues_when_optional_cross_attempt_history_times_out(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    repository = DynamicInterviewRepository()

    def unavailable_history(**_kwargs):  # type: ignore[no-untyped-def]
        raise SupabaseRepositoryError(503, "synthetic history timeout")

    repository.recent_same_role_questions = unavailable_history  # type: ignore[method-assign]
    _patch_dynamic_services(monkeypatch, repository)

    result = journey.next_persisted_question(repository.attempt_id, repository)  # type: ignore[arg-type]

    assert result.question is not None
    assert result.question.question_template_id == "gemini:dynamic:unique-question"
