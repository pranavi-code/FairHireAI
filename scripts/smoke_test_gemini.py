"""Verify Gemini generation and embedding without printing credentials."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.config import get_settings
from backend.app.providers.gemini import GeminiClient
from backend.app.services.answer_evaluation import AnswerEvaluationService
from backend.app.services.grounded_questions import (
    GroundedQuestionService,
    PersonalizedQuestionRequest,
)


def main() -> None:
    settings = get_settings()
    if not settings.gemini_configured or settings.gemini_api_key is None:
        raise RuntimeError("ROLEREADY_GEMINI_API_KEY is not available")
    with GeminiClient(
        api_key=settings.gemini_api_key.get_secret_value(),
        generation_model=settings.gemini_generation_model,
        embedding_model=settings.gemini_embedding_model,
        embedding_dimensions=settings.gemini_embedding_dimensions,
        timeout_seconds=settings.gemini_timeout_seconds,
        max_retries=settings.gemini_max_retries,
    ) as client:
        vector = client.embed(
            "HTTP object authorization for a junior backend interview",
            task_type="RETRIEVAL_QUERY",
        )
        package = GroundedQuestionService(client).generate(
            PersonalizedQuestionRequest(
                role_id="junior_backend_developer",
                competency_id="api_design",
                candidate_skill_terms=["REST API"],
                jd_skill_terms=["HTTP", "authorization"],
                external_ai_processing_consent=True,
            )
        )
        evaluation = AnswerEvaluationService(client).evaluate(
            competency_id="api_design",
            prompt_snapshot=(
                "Explain how an API verifies that an authenticated user may access "
                "a requested object."
            ),
            expected_concepts=["authentication", "object authorization"],
            rubric={
                "1": "No relevant answer.",
                "2": "Mentions authentication only.",
                "3": "Separates authentication and authorization.",
                "4": "Adds object ownership checks and safe status handling.",
                "5": "Also explains tests and denial-by-default trade-offs.",
            },
            source_mapping={"SRC-014": ["object authorization"]},
            transcript={
                "text": (
                    "The API authenticates the token, loads the object, and checks "
                    "that its owner id matches the signed-in user before returning it."
                ),
                "segments": [
                    {
                        "start": 0.0,
                        "end": 8.0,
                        "text": "authenticate the token and check the object owner id",
                    }
                ],
                "average_word_confidence": 0.95,
            },
            resume_claims=[],
            is_follow_up=False,
        )
    summary = {
        "schema_version": "gemini-smoke-v1",
        "generation_model": settings.gemini_generation_model,
        "embedding_model": settings.gemini_embedding_model,
        "embedding_dimensions": len(vector),
        "question_id": package.question_id,
        "question_validation_status": package.validation_status,
        "answer_evaluation_competency": evaluation.competency_id,
        "answer_evaluation_evidence_count": len(evaluation.criterion_evidence),
        "grounding_validation": package.automatic_validation["grounded_semantic_validation"],
        "passed": (
            len(vector) == 384
            and package.validation_status == "generated_validated_for_practice"
            and evaluation.competency_id == "api_design"
            and bool(evaluation.criterion_evidence)
        ),
    }
    output = Path("outputs/knowledge/gemini_smoke_summary.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["passed"]:
        raise RuntimeError("Gemini smoke validation did not pass")
    print("GEMINI LIVE SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
