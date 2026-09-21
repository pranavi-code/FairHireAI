"""Read-only live smoke test for history-aware Data Analyst question generation."""

from __future__ import annotations

import json
from urllib.parse import urlparse

from backend.app.config import get_settings
from backend.app.domain.interviews import NextQuestionResult
from backend.app.providers.gemini import GeminiClient
from backend.app.repositories.worker import SupabaseWorkerRepository
from backend.app.services.adaptive_question_generation import (
    AdaptiveQuestionGenerationService,
)
from backend.app.services.grounded_questions import (
    GroundedQuestionService,
    PersonalizedQuestionRequest,
)
from backend.app.services.hybrid_rag import HybridRagService

EXPECTED_PROJECT_REF = "gfsetwljirztyxegiets"


def _project_ref(url: str) -> str:
    return (urlparse(url).hostname or "").split(".", 1)[0]


def main() -> None:
    settings = get_settings()
    project_ref = _project_ref(settings.supabase_url or "")
    if project_ref != EXPECTED_PROJECT_REF:
        raise RuntimeError(
            f"Refusing live smoke test for unexpected Supabase project {project_ref!r}"
        )
    if not settings.worker_configured or settings.supabase_secret_key is None:
        raise RuntimeError("The server-only Supabase key is required for this read-only smoke test")
    if not settings.gemini_configured or settings.gemini_api_key is None:
        raise RuntimeError("Gemini is required for dynamic generation")

    role_id = "junior_data_analyst"
    competency_id = "data_visualization"
    selection = NextQuestionResult(
        action="ask_question",
        competency_id=competency_id,
        question_id="viz_core_01",
        prompt="Assess junior-level data visualization reasoning.",
        reason="Read-only live recovery smoke test.",
    )
    history = [
        "Which chart would you use to show monthly sales trends?",
        "How would you visualize regional revenue comparisons?",
        "Design a conversion funnel dashboard for an ecommerce team.",
        (
            "A placement coordinator wants to compare interview participation, "
            "improvement, and selection rates across departments. Design the dashboard."
        ),
    ]

    with (
        SupabaseWorkerRepository(
            base_url=settings.supabase_url or "",
            secret_key=settings.supabase_secret_key.get_secret_value(),
            timeout_seconds=max(30.0, settings.supabase_timeout_seconds),
        ) as repository,
        GeminiClient(
            api_key=settings.gemini_api_key.get_secret_value(),
            generation_model=settings.gemini_generation_model,
            embedding_model=settings.gemini_embedding_model,
            embedding_dimensions=settings.gemini_embedding_dimensions,
            timeout_seconds=settings.gemini_timeout_seconds,
            max_retries=settings.gemini_max_retries,
        ) as client,
    ):
        anchors = HybridRagService(client).retrieve_question_candidates(
            repository,
            role_id=role_id,
            competency_id=competency_id,
            selection=selection,
            personalization_context={
                "candidate_skill_terms": ["SQL", "dashboards"],
                "jd_skill_terms": ["data visualization", "stakeholder communication"],
                "resume_evidence_summaries": [],
            },
        )
        result = AdaptiveQuestionGenerationService(
            GroundedQuestionService(client)
        ).generate(
            PersonalizedQuestionRequest(
                role_id=role_id,
                competency_id=competency_id,
                candidate_skill_terms=["SQL", "dashboards"],
                jd_skill_terms=["data visualization", "stakeholder communication"],
                recent_question_prompts=history,
                recent_question_ids=[f"synthetic-history-{index}" for index in range(len(history))],
                external_ai_processing_consent=True,
            ),
            anchors=anchors,
            correlation_id="live-read-only-data-visualization-smoke",
        )

    print(
        json.dumps(
            {
                "status": "passed",
                "project_ref": project_ref,
                "role_id": role_id,
                "competency_id": competency_id,
                "history_count": len(history),
                "anchor_count": len(anchors),
                "selected_anchor": result.anchor.package_model.question_id,
                "strategy": result.strategy,
                "attempted_candidates": result.attempted_candidates,
                "rejected_candidates": result.rejected_candidates,
                "question_validation_status": result.generated.validation_status,
                "writes_performed": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    print("LIVE DYNAMIC QUESTION RECOVERY SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
