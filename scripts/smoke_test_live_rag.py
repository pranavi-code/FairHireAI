"""Read-only live smoke test for graph-guided hybrid RAG."""

from __future__ import annotations

import json
from urllib.parse import urlparse

from backend.app.config import get_settings
from backend.app.domain.interviews import NextQuestionResult
from backend.app.domain.roadmap import SkillGap
from backend.app.providers.gemini import GeminiClient
from backend.app.repositories.worker import SupabaseWorkerRepository
from backend.app.services.hybrid_rag import HybridRagService

EXPECTED_PROJECT_REF = "gfsetwljirztyxegiets"


def main() -> None:
    settings = get_settings()
    project_ref = (urlparse(settings.supabase_url or "").hostname or "").split(".", 1)[0]
    if project_ref != EXPECTED_PROJECT_REF:
        raise RuntimeError(
            f"Refusing live smoke test for unexpected Supabase project {project_ref!r}"
        )
    if not settings.worker_configured or settings.supabase_secret_key is None:
        raise RuntimeError("The server-only Supabase key is required for this smoke test")
    if not settings.gemini_configured or settings.gemini_api_key is None:
        raise RuntimeError("Gemini is required for query embeddings")

    role_id = "junior_backend_developer"
    competency_id = "api_design"
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
        rag = HybridRagService(client)
        question = rag.retrieve_question(
            repository,
            role_id=role_id,
            competency_id=competency_id,
            selection=NextQuestionResult(
                action="ask_question",
                competency_id=competency_id,
                question_id="api_core_01",
                prompt=(
                    "Design a secure REST API endpoint with validation, ownership "
                    "checks, useful status codes, and automated tests."
                ),
                reason="Live RAG verification.",
            ),
            personalization_context={
                "candidate_skill_terms": ["Python", "FastAPI"],
                "jd_skill_terms": ["REST API", "authentication"],
                "resume_evidence_summaries": [],
            },
        )
        resources = rag.retrieve_resources(
            repository,
            role_id=role_id,
            gaps=[
                SkillGap(
                    skill_gap_node_id="gap:live-rag-api-design",
                    competency_id=competency_id,
                    current_score=0.4,
                    target_score=0.7,
                    severity=0.3,
                    evidence_node_ids=["evidence:live-rag-api-design"],
                )
            ],
            approved_resources=repository.approved_resources(),
        )
    if not resources:
        raise RuntimeError("Hybrid RAG returned no approved roadmap resources")
    result = {
        "status": "passed",
        "project_ref": project_ref,
        "embedding_dimensions": settings.gemini_embedding_dimensions,
        "question_package_id": question.package_model.question_id,
        "question_competency": question.package_model.competency_id,
        "question_hybrid_score": round(question.hybrid_score, 6),
        "resource_ids": [str(item["id"]) for item in resources],
        "resource_scores": [item["retrieval_scores"] for item in resources],
        "writes_performed": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    print("LIVE HYBRID RAG SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
