from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from backend.app.providers.gemini import GeminiClient, GeminiProviderError
from backend.app.services.grounded_questions import (
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
