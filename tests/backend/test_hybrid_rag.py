from __future__ import annotations

from typing import Any
from uuid import uuid4

from backend.app.domain.interviews import NextQuestionResult
from backend.app.domain.knowledge import (
    QuestionSearchRequest,
    QuestionSearchResult,
    ResourceSearchRequest,
    ResourceSearchResult,
    build_seed_question_packages,
)
from backend.app.domain.roadmap import SkillGap
from backend.app.services.hybrid_rag import HybridRagService


class FakeEmbeddingClient:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed(self, text: str, *, task_type: str) -> list[float]:
        assert task_type == "RETRIEVAL_QUERY"
        self.queries.append(text)
        return [0.01] * 384


class FakeQuestionRepository:
    def __init__(self, row: dict[str, Any]) -> None:
        self.row = row
        self.request: QuestionSearchRequest | None = None

    def search_question_packages(
        self,
        request: QuestionSearchRequest,
    ) -> list[QuestionSearchResult]:
        self.request = request
        return [
            QuestionSearchResult(
                id=str(self.row["id"]),
                package_key=str(self.row["package_key"]),
                version=str(self.row["version"]),
                role_id=str(self.row["role_id"]),
                competency_id=str(self.row["competency_id"]),
                seniority=str(self.row["seniority"]),
                difficulty=str(self.row["difficulty"]),
                question_type=str(self.row["question_type"]),
                prompt=str(self.row["prompt"]),
                expected_concepts=list(self.row["expected_concepts"]),
                rubric=dict(self.row["rubric"]),
                follow_ups=list(self.row["follow_ups"]),
                reference_explanation=str(self.row["reference_explanation"]),
                validation_status=str(self.row["validation_status"]),
                keyword_rank=0.5,
                semantic_similarity=0.9,
                hybrid_score=0.68,
            )
        ]

    def validated_question_package_by_id(
        self,
        package_id: str,
    ) -> dict[str, Any] | None:
        return self.row if package_id == self.row["id"] else None


class FakeResourceRepository:
    def __init__(self) -> None:
        self.requests: list[ResourceSearchRequest] = []

    def search_learning_resources(
        self,
        request: ResourceSearchRequest,
    ) -> list[ResourceSearchResult]:
        self.requests.append(request)
        return [
            ResourceSearchResult(
                id="RES-API",
                title="API design guide",
                canonical_url="https://example.org/api",
                source_organization="Example",
                competency_ids=["api_design"],
                difficulty="beginner",
                estimated_minutes=30,
                description="A reviewed guide to API contracts and validation.",
                resource_type="official_documentation",
                learning_outcomes=["Design a validated API contract"],
                keyword_rank=0.4,
                semantic_similarity=0.8,
                hybrid_score=0.58,
            )
        ]


def _validated_package_row() -> dict[str, Any]:
    package = build_seed_question_packages()[0].model_copy(
        update={
            "validation_status": "generated_validated_for_practice",
            "automatic_validation": {"retrievable": True},
        }
    )
    row = package.model_dump(mode="json")
    row["id"] = row.pop("question_id")
    return row


def _question_search_result(
    row: dict[str, Any], *, hybrid_score: float
) -> QuestionSearchResult:
    return QuestionSearchResult(
        id=str(row["id"]),
        package_key=str(row["package_key"]),
        version=str(row["version"]),
        role_id=str(row["role_id"]),
        competency_id=str(row["competency_id"]),
        seniority=str(row["seniority"]),
        difficulty=str(row["difficulty"]),
        question_type=str(row["question_type"]),
        prompt=str(row["prompt"]),
        expected_concepts=list(row["expected_concepts"]),
        rubric=dict(row["rubric"]),
        follow_ups=list(row["follow_ups"]),
        reference_explanation=str(row["reference_explanation"]),
        validation_status=str(row["validation_status"]),
        keyword_rank=0.5,
        semantic_similarity=0.9,
        hybrid_score=hybrid_score,
    )


def test_question_rag_embeds_context_and_grounds_the_selected_prompt() -> None:
    row = _validated_package_row()
    repository = FakeQuestionRepository(row)
    client = FakeEmbeddingClient()
    result = HybridRagService(client).retrieve_question(
        repository,
        role_id=str(row["role_id"]),
        competency_id=str(row["competency_id"]),
        selection=NextQuestionResult(
            action="ask_question",
            competency_id=str(row["competency_id"]),
            question_id=str(row["package_key"]).split(":", 1)[1],
            prompt="Template wording that must be replaced by the retrieved package.",
            reason="Selected the next competency.",
        ),
        personalization_context={
            "candidate_skill_terms": ["Python"],
            "jd_skill_terms": ["algorithms"],
            "resume_evidence_summaries": ["Improved an endpoint."],
        },
    )

    assert result.selection.prompt == row["prompt"]
    assert "Hybrid RAG" in result.selection.reason
    assert repository.request is not None
    assert len(repository.request.query_embedding or []) == 384
    assert "Python" in client.queries[0]
    assert result.package["id"] == row["id"]


def test_question_rag_returns_multiple_anchors_and_deprioritizes_recently_used() -> None:
    preferred = _validated_package_row()
    alternate = dict(preferred)
    alternate.update(
        {
            "id": "alternate-anchor",
            "package_key": "alternate-anchor",
            "prompt": "Use a different reviewed scenario while assessing the same competency.",
        }
    )

    class MultipleAnchorRepository:
        def search_question_packages(
            self, _request: QuestionSearchRequest
        ) -> list[QuestionSearchResult]:
            # The duplicate preferred result exercises retrieval deduplication.
            return [
                _question_search_result(preferred, hybrid_score=0.95),
                _question_search_result(preferred, hybrid_score=0.94),
                _question_search_result(alternate, hybrid_score=0.80),
            ]

        def validated_question_package_by_id(
            self, package_id: str
        ) -> dict[str, Any] | None:
            return {
                str(preferred["id"]): preferred,
                str(alternate["id"]): alternate,
            }.get(package_id)

    selection = NextQuestionResult(
        action="ask_question",
        competency_id=str(preferred["competency_id"]),
        question_id=str(preferred["package_key"]).split(":", 1)[-1],
        prompt="Selected competency intent.",
        reason="Selected the next competency.",
    )
    results = HybridRagService(FakeEmbeddingClient()).retrieve_question_candidates(
        MultipleAnchorRepository(),
        role_id=str(preferred["role_id"]),
        competency_id=str(preferred["competency_id"]),
        selection=selection,
        personalization_context={},
        deprioritized_package_ids={str(preferred["id"])},
    )

    assert [item.package_model.question_id for item in results] == [
        "alternate-anchor",
        str(preferred["id"]),
    ]


def test_resource_rag_returns_only_semantically_retrieved_approved_rows() -> None:
    client = FakeEmbeddingClient()
    repository = FakeResourceRepository()
    gap = SkillGap(
        skill_gap_node_id=f"gap:{uuid4()}",
        competency_id="api_design",
        current_score=0.4,
        target_score=0.7,
        severity=0.3,
        evidence_node_ids=["evidence:api"],
    )
    approved = [
        {
            "id": "RES-API",
            "title": "API design guide",
            "reviewer_status": "approved",
        },
        {
            "id": "RES-UNRELATED",
            "title": "Unrelated guide",
            "reviewer_status": "approved",
        },
    ]
    result = HybridRagService(client).retrieve_resources(
        repository,
        role_id="junior_backend_developer",
        gaps=[gap],
        approved_resources=approved,
    )

    assert [item["id"] for item in result] == ["RES-API"]
    assert result[0]["retrieval_scores"] == {"api_design": 0.58}
    assert len(repository.requests[0].query_embedding or []) == 384
    assert "api design" in client.queries[0]
