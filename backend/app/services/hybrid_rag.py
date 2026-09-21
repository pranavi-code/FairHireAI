"""Graph-guided hybrid retrieval for interview questions and roadmaps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from backend.app.domain.interviews import NextQuestionResult
from backend.app.domain.knowledge import (
    QuestionPackage,
    QuestionSearchRequest,
    QuestionSearchResult,
    ResourceSearchRequest,
    ResourceSearchResult,
)
from backend.app.domain.roadmap import SkillGap
from backend.app.providers.gemini import GeminiClient


class QuestionRagRepository(Protocol):
    def search_question_packages(
        self,
        request: QuestionSearchRequest,
    ) -> list[QuestionSearchResult]: ...

    def validated_question_package_by_id(
        self,
        package_id: str,
    ) -> dict[str, Any] | None: ...


class ResourceRagRepository(Protocol):
    def search_learning_resources(
        self,
        request: ResourceSearchRequest,
    ) -> list[ResourceSearchResult]: ...


@dataclass(frozen=True)
class RetrievedQuestion:
    package: dict[str, Any]
    package_model: QuestionPackage
    selection: NextQuestionResult
    query: str
    hybrid_score: float


def question_package_from_database_row(row: dict[str, Any]) -> QuestionPackage:
    """Validate a PostgREST question row against the versioned domain contract."""

    payload = dict(row)
    payload["question_id"] = payload.pop("id")
    return QuestionPackage.model_validate(payload)


def build_question_retrieval_query(
    *,
    role_id: str,
    competency_id: str,
    selection: NextQuestionResult,
    personalization_context: dict[str, list[str]],
) -> str:
    parts = [
        f"role {role_id.replace('_', ' ')}",
        f"competency {competency_id.replace('_', ' ')}",
        f"question intent {selection.prompt or ''}",
    ]
    candidate_skills = personalization_context.get("candidate_skill_terms") or []
    jd_skills = personalization_context.get("jd_skill_terms") or []
    evidence = personalization_context.get("resume_evidence_summaries") or []
    if candidate_skills:
        parts.append("candidate skills " + ", ".join(candidate_skills[:20]))
    if jd_skills:
        parts.append("job description skills " + ", ".join(jd_skills[:20]))
    if evidence:
        parts.append("resume evidence " + " | ".join(evidence[:3]))
    return ". ".join(part.strip() for part in parts if part.strip())[:4_000]


def selection_from_package(
    selection: NextQuestionResult,
    package: QuestionPackage,
    *,
    retrieval_note: str,
) -> NextQuestionResult:
    if selection.action != "ask_question" or not selection.question_id:
        raise ValueError("Only an ask-question selection can be grounded")
    if selection.is_follow_up:
        follow_up = next(
            (
                item
                for item in package.follow_ups
                if item.question_id == selection.question_id
            ),
            None,
        )
        # A retrieved variant can have different stored fallback follow-up IDs.
        # The live journey generates the actual follow-up from the latest answer,
        # so the package is used as the reviewed rubric/source anchor here.
        prompt = follow_up.prompt if follow_up is not None else selection.prompt
    else:
        prompt = package.prompt
    return selection.model_copy(
        update={
            "prompt": prompt,
            "reason": (
                f"{selection.reason} {retrieval_note} selected validated package "
                f"{package.question_id}."
            ),
        }
    )


def build_resource_retrieval_query(*, role_id: str, gap: SkillGap) -> str:
    return (
        f"learning roadmap for {role_id.replace('_', ' ')}; "
        f"improve {gap.competency_id.replace('_', ' ')} from "
        f"{gap.current_score:.3f} to {gap.target_score:.3f}; "
        "beginner-friendly official explanation, practice, and evidence-building task"
    )


class HybridRagService:
    """Use Gemini query embeddings with the RLS-protected Supabase RPCs."""

    def __init__(self, client: GeminiClient) -> None:
        self._client = client

    def retrieve_question(
        self,
        repository: QuestionRagRepository,
        *,
        role_id: str,
        competency_id: str,
        selection: NextQuestionResult,
        personalization_context: dict[str, list[str]],
    ) -> RetrievedQuestion:
        candidates = self.retrieve_question_candidates(
            repository,
            role_id=role_id,
            competency_id=competency_id,
            selection=selection,
            personalization_context=personalization_context,
        )
        if not candidates:
            raise ValueError(
                "Hybrid RAG found no validated question package for the selected competency"
            )
        return candidates[0]

    def retrieve_question_candidates(
        self,
        repository: QuestionRagRepository,
        *,
        role_id: str,
        competency_id: str,
        selection: NextQuestionResult,
        personalization_context: dict[str, list[str]],
        deprioritized_package_ids: set[str] | None = None,
    ) -> list[RetrievedQuestion]:
        """Return a validated, diverse anchor pool with recently used anchors last."""

        query = build_question_retrieval_query(
            role_id=role_id,
            competency_id=competency_id,
            selection=selection,
            personalization_context=personalization_context,
        )
        embedding = self._client.embed(query, task_type="RETRIEVAL_QUERY")
        matches = repository.search_question_packages(
            QuestionSearchRequest(
                query=query,
                role_id=role_id,
                competency_id=competency_id,
                seniority="junior",
                query_embedding=embedding,
                match_count=5,
            )
        )
        seen: set[str] = set()
        retrieved: list[RetrievedQuestion] = []
        for match in matches:
            if match.id in seen:
                continue
            seen.add(match.id)
            row = repository.validated_question_package_by_id(match.id)
            if row is None:
                continue
            package = question_package_from_database_row(row)
            if package.role_id != role_id or package.competency_id != competency_id:
                raise ValueError(
                    "Hybrid RAG returned a package outside the selected role competency"
                )
            if package.validation_status not in {
                "generated_validated_for_practice",
                "faculty_reviewed_research_set",
            }:
                raise ValueError("Hybrid RAG returned an unvalidated question package")
            retrieved.append(
                RetrievedQuestion(
                    package=row,
                    package_model=package,
                    selection=selection_from_package(
                        selection,
                        package,
                        retrieval_note=f"Hybrid RAG (score={match.hybrid_score:.6f})",
                    ),
                    query=query,
                    hybrid_score=match.hybrid_score,
                )
            )
        deprioritized = deprioritized_package_ids or set()
        retrieved.sort(
            key=lambda item: (
                item.package_model.question_id in deprioritized,
                -item.hybrid_score,
                item.package_model.question_id,
            )
        )
        return retrieved

    def retrieve_resources(
        self,
        repository: ResourceRagRepository,
        *,
        role_id: str,
        gaps: list[SkillGap],
        approved_resources: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        scores_by_resource: dict[str, dict[str, float]] = {}
        for gap in gaps:
            query = build_resource_retrieval_query(role_id=role_id, gap=gap)
            embedding = self._client.embed(query, task_type="RETRIEVAL_QUERY")
            matches = repository.search_learning_resources(
                ResourceSearchRequest(
                    query=query,
                    competency_id=gap.competency_id,
                    query_embedding=embedding,
                    match_count=3,
                )
            )
            for match in matches:
                scores_by_resource.setdefault(match.id, {})[gap.competency_id] = float(
                    match.hybrid_score
                )

        resources_by_id = {
            str(resource.get("id")): resource
            for resource in approved_resources
            if resource.get("id")
        }
        retrieved: list[dict[str, Any]] = []
        for resource_id, scores in scores_by_resource.items():
            resource = resources_by_id.get(resource_id)
            if resource is None:
                raise ValueError(
                    f"RAG returned unknown or unapproved learning resource {resource_id}"
                )
            enriched = dict(resource)
            enriched["retrieval_scores"] = scores
            retrieved.append(enriched)
        retrieved.sort(
            key=lambda item: (
                -max(item["retrieval_scores"].values()),
                str(item["id"]),
            )
        )
        return retrieved
