from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from backend.app.domain.knowledge import build_seed_question_packages
from backend.app.providers.gemini import GeminiClient, GeminiProviderError
from backend.app.services.grounded_questions import (
    GroundedQuestionContentError,
    GroundedQuestionService,
    PersonalizedQuestionRequest,
)


def _generation_response(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": json.dumps(payload)}],
                    }
                }
            ]
        },
    )


def test_gemini_key_is_sent_only_as_header_and_embedding_is_384_values() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["key"] = request.headers.get("x-goog-api-key")
        captured["body"] = json.loads(request.read())
        return httpx.Response(200, json={"embedding": {"values": [0.01] * 384}})

    with GeminiClient(
        api_key="private-test-key",
        transport=httpx.MockTransport(handler),
        max_retries=0,
    ) as client:
        vector = client.embed("HTTP authorization", task_type="RETRIEVAL_QUERY")

    assert len(vector) == 384
    assert captured["key"] == "private-test-key"
    assert "private-test-key" not in str(captured["url"])
    assert captured["body"]["outputDimensionality"] == 384  # type: ignore[index]


def test_gemini_retries_rate_limit_without_leaking_key() -> None:
    requests = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(429, json={"error": {"message": "quota reached"}})

    with GeminiClient(
        api_key="secret",
        transport=httpx.MockTransport(handler),
        max_retries=1,
        sleep=lambda _: None,
    ) as client:
        with pytest.raises(GeminiProviderError, match="quota reached") as error:
            client.embed("query", task_type="RETRIEVAL_QUERY")
    assert error.value.status_code == 429
    assert error.value.retryable
    assert requests == 2


def test_gemini_retries_timeout_then_returns_embedding() -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        if requests == 1:
            raise httpx.ReadTimeout("temporary timeout", request=request)
        return httpx.Response(200, json={"embedding": {"values": [0.02] * 384}})

    with GeminiClient(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
        max_retries=1,
        sleep=lambda _: None,
    ) as client:
        vector = client.embed("query", task_type="RETRIEVAL_QUERY")

    assert requests == 2
    assert len(vector) == 384


def test_gemini_rejects_malformed_structured_output() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "not valid json"}]}}
                ]
            },
        )

    with GeminiClient(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
        max_retries=0,
    ) as client:
        with pytest.raises(GeminiProviderError, match="malformed structured output"):
            client.generate_json(
                system_instruction="Return JSON.",
                prompt="Test",
                response_schema={"type": "object"},
            )


def test_gemini_generation_temperature_is_explicit_and_bounded() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.read()))
        return _generation_response({"value": "ok"})

    with GeminiClient(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
        max_retries=0,
    ) as client:
        client.generate_json(
            system_instruction="Return JSON.",
            prompt="Test",
            response_schema={"type": "object"},
            temperature=0.9,
        )
        with pytest.raises(ValueError, match="temperature"):
            client.generate_json(
                system_instruction="Return JSON.",
                prompt="Test",
                response_schema={"type": "object"},
                temperature=2.1,
            )

    assert captured["generationConfig"]["temperature"] == 0.9  # type: ignore[index]


def test_gemini_ocr_sends_inline_media_and_returns_text() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.read())
        return _generation_response({"text": "Junior Data Analyst\nSQL and Python required"})

    with GeminiClient(
        api_key="private-test-key",
        transport=httpx.MockTransport(handler),
        max_retries=0,
    ) as client:
        text = client.extract_text_from_media(
            content=b"\xff\xd8\xffimage",
            media_type="image/jpeg",
        )

    body = captured["body"]
    assert isinstance(body, dict)
    inline_data = body["contents"][0]["parts"][0]["inlineData"]
    assert inline_data["mimeType"] == "image/jpeg"
    assert inline_data["data"]
    assert text == "Junior Data Analyst\nSQL and Python required"


def test_personalized_question_requires_external_processing_consent() -> None:
    with pytest.raises(ValidationError, match="Explicit consent"):
        PersonalizedQuestionRequest(
            role_id="junior_backend_developer",
            competency_id="api_design",
            external_ai_processing_consent=False,
        )


def test_grounded_question_requires_independent_validation() -> None:
    generated = {
        "prompt": (
            "How would you design an HTTP endpoint and check that the signed-in "
            "caller may access the requested object?"
        ),
        "expected_concepts": ["request response", "object authorization"],
        "rubric": {
            "level_1": "No relevant understanding.",
            "level_2": "Mentions an endpoint but omits authorization.",
            "level_3": "Explains HTTP and a server-side authorization check.",
            "level_4": "Adds statuses, validation, and ownership checks.",
            "level_5": "Also explains risks, testing, and trade-offs.",
        },
        "follow_ups": [],
        "reference_explanation": (
            "A request identifies a resource and the server must separately verify "
            "authorization for that exact object and action."
        ),
        "source_to_concept_mapping": {
            "SRC-013": ["request response"],
            "SRC-014": ["object authorization"],
        },
    }
    validation = {
        "grounded": True,
        "fair": True,
        "junior_level": True,
        "answerable_from_sources": True,
        "novel_against_recent_questions": True,
        "unsupported_claims": [],
        "confidence": 0.95,
        "reason": "The reviewed HTTP and authorization summaries support the question.",
    }
    responses = iter([generated, validation])

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "test-key"
        body = json.loads(request.read())
        properties = body["generationConfig"]["responseJsonSchema"]["properties"]
        rubric_schema = properties.get("rubric")
        if rubric_schema:
            assert set(rubric_schema["properties"]) == {"1", "2", "3", "4", "5"}
        return _generation_response(next(responses))

    with GeminiClient(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
        max_retries=0,
    ) as client:
        package = GroundedQuestionService(client).generate(
            PersonalizedQuestionRequest(
                role_id="junior_backend_developer",
                competency_id="api_design",
                candidate_skill_terms=["REST API"],
                jd_skill_terms=["HTTP"],
                external_ai_processing_consent=True,
            )
        )

    assert package.author_type == "gemini_generated"
    assert package.validation_status == "generated_validated_for_practice"
    assert package.automatic_validation["retrievable"] is True
    assert package.model_id == "gemini-3.5-flash-lite"
    assert set(package.rubric) == {"1", "2", "3", "4", "5"}


def test_personalization_cannot_change_retrieved_assessment_standard() -> None:
    anchor = build_seed_question_packages()[0].model_copy(
        update={"validation_status": "faculty_reviewed_research_set"}
    )
    generated = {
        "prompt": "Tell me how you would approach this approved technical scenario.",
        "expected_concepts": anchor.expected_concepts,
        "rubric": {**anchor.rubric, "5": "A changed unapproved standard."},
        "follow_ups": [item.model_dump(mode="json") for item in anchor.follow_ups],
        "reference_explanation": anchor.reference_explanation,
        "source_to_concept_mapping": anchor.source_to_concept_mapping,
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return _generation_response(generated)

    with GeminiClient(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
        max_retries=0,
    ) as client:
        with pytest.raises(
            GroundedQuestionContentError, match="approved assessment standard"
        ):
            GroundedQuestionService(client).generate(
                PersonalizedQuestionRequest(
                    role_id=anchor.role_id or "",
                    competency_id=anchor.competency_id,
                    external_ai_processing_consent=True,
                ),
                anchor_package=anchor,
            )


def test_follow_up_generation_uses_answer_evidence_and_rejects_recent_repetition() -> None:
    anchor = build_seed_question_packages()[0].model_copy(
        update={"validation_status": "faculty_reviewed_research_set"}
    )
    generated = {
        "prompt": (
            "Your answer covered request validation but omitted authorization. "
            "How would you verify ownership before returning the resource?"
        ),
        "expected_concepts": anchor.expected_concepts,
        "rubric": anchor.rubric,
        "follow_ups": [item.model_dump(mode="json") for item in anchor.follow_ups],
        "reference_explanation": anchor.reference_explanation,
        "source_to_concept_mapping": anchor.source_to_concept_mapping,
    }
    validation = {
        "grounded": True,
        "fair": True,
        "junior_level": True,
        "answerable_from_sources": True,
        "novel_against_recent_questions": True,
        "unsupported_claims": [],
        "confidence": 0.94,
        "reason": "The follow-up targets omitted authorization using reviewed material.",
    }
    captured: list[dict[str, object]] = []
    responses = iter([generated, validation])

    class FakeClient:
        generation_model = "gemini-test"

        def generate_json(self, **kwargs):  # type: ignore[no-untyped-def]
            captured.append(json.loads(kwargs["prompt"]))
            return next(responses)

    package = GroundedQuestionService(FakeClient()).generate(  # type: ignore[arg-type]
        PersonalizedQuestionRequest(
            role_id=anchor.role_id or "",
            competency_id=anchor.competency_id,
            previous_question="How would you validate an incoming API request?",
            previous_answer_excerpt="I would validate the payload with a schema.",
            missing_concepts=["object authorization"],
            weakest_criterion="authorization",
            recent_question_prompts=[
                "How would you validate an incoming API request?",
                "Describe how you would design and validate a basic REST endpoint.",
            ],
            is_follow_up=True,
            external_ai_processing_consent=True,
        ),
        anchor_package=anchor,
    )

    assert package.question_type == "follow_up"
    assert package.prompt_version == "grounded-adaptive-question-gemini-v2"
    assert captured[0]["previous_answer_excerpt"] == (
        "I would validate the payload with a schema."
    )
    assert captured[0]["missing_concepts_from_evaluation"] == ["object authorization"]
    assert captured[0]["recent_question_themes_to_avoid"]
    assert captured[1]["previous_answer_excerpt"] == (
        "I would validate the payload with a schema."
    )
    assert captured[1]["weakest_rubric_criterion"] == "authorization"


def test_question_generation_rejects_exact_recent_prompt() -> None:
    anchor = build_seed_question_packages()[0].model_copy(
        update={"validation_status": "faculty_reviewed_research_set"}
    )
    repeated = "Describe how you would validate an incoming API request safely."
    generated = {
        "prompt": repeated,
        "expected_concepts": anchor.expected_concepts,
        "rubric": anchor.rubric,
        "follow_ups": [item.model_dump(mode="json") for item in anchor.follow_ups],
        "reference_explanation": anchor.reference_explanation,
        "source_to_concept_mapping": anchor.source_to_concept_mapping,
    }

    class FakeClient:
        generation_model = "gemini-test"

        def generate_json(self, **_kwargs):  # type: ignore[no-untyped-def]
            return generated

    with pytest.raises(GroundedQuestionContentError, match="repetitive"):
        GroundedQuestionService(FakeClient()).generate(  # type: ignore[arg-type]
            PersonalizedQuestionRequest(
                role_id=anchor.role_id or "",
                competency_id=anchor.competency_id,
                recent_question_prompts=[repeated],
                external_ai_processing_consent=True,
            ),
            anchor_package=anchor,
        )


def test_follow_up_rejects_an_exact_repeat_of_its_parent_question() -> None:
    anchor = build_seed_question_packages()[0].model_copy(
        update={"validation_status": "faculty_reviewed_research_set"}
    )
    parent = "How would you validate an incoming API request safely?"
    generated = {
        "prompt": parent,
        "expected_concepts": anchor.expected_concepts,
        "rubric": anchor.rubric,
        "follow_ups": [item.model_dump(mode="json") for item in anchor.follow_ups],
        "reference_explanation": anchor.reference_explanation,
        "source_to_concept_mapping": anchor.source_to_concept_mapping,
    }

    class FakeClient:
        generation_model = "gemini-test"

        def generate_json(self, **_kwargs):  # type: ignore[no-untyped-def]
            return generated

    with pytest.raises(GroundedQuestionContentError, match="repeated the parent"):
        GroundedQuestionService(FakeClient()).generate(  # type: ignore[arg-type]
            PersonalizedQuestionRequest(
                role_id=anchor.role_id or "",
                competency_id=anchor.competency_id,
                previous_question=parent,
                previous_answer_excerpt="I would use a schema.",
                recent_question_prompts=[parent],
                is_follow_up=True,
                external_ai_processing_consent=True,
            ),
            anchor_package=anchor,
        )
