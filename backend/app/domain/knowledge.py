"""Validated source registry and contracts for the two hybrid-RAG collections."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

from backend.app.domain.roles import list_role_templates

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCES_CSV = PROJECT_ROOT / "docs" / "sources.csv"
SOURCE_POLICIES = PROJECT_ROOT / "configs" / "knowledge" / "source_policies.v1.json"
INITIAL_KNOWLEDGE_SEED = (
    PROJECT_ROOT / "configs" / "knowledge" / "initial_knowledge_seed.v1.json"
)

SourceType = Literal[
    "occupation_taxonomy",
    "curriculum",
    "technical_documentation",
    "research",
    "dataset",
    "software",
    "learning_resource",
]
ContentPolicy = Literal[
    "metadata_only",
    "reviewer_summary",
    "permitted_excerpt",
    "open_content",
]
ReviewStatus = Literal["pending", "approved", "retired"]
QuestionValidationStatus = Literal[
    "draft",
    "pending_automatic_validation",
    "generated_validated_for_practice",
    "faculty_reviewed_research_set",
    "rejected",
    "retired",
]


class KnowledgeSource(BaseModel):
    source_id: str = Field(pattern=r"^SRC-[0-9]{3,}$")
    title: str = Field(min_length=3, max_length=300)
    canonical_url: HttpUrl
    publisher: str = Field(min_length=2, max_length=200)
    source_type: SourceType
    license_id: str = Field(min_length=2, max_length=300)
    license_url: HttpUrl | None = None
    content_policy: ContentPolicy
    accessed_on: date
    used_for: str = Field(min_length=3, max_length=500)
    citation_key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    permitted_use: str = Field(min_length=20, max_length=2000)
    attribution_text: str = Field(min_length=10, max_length=2000)
    retrieval_enabled: bool
    review_status: ReviewStatus
    notes: str = Field(max_length=2000)

    @model_validator(mode="after")
    def validate_retrieval_policy(self) -> KnowledgeSource:
        if self.retrieval_enabled and self.review_status != "approved":
            raise ValueError("Retrieval-enabled sources must be approved")
        if self.content_policy == "open_content" and self.license_url is None:
            raise ValueError("Open-content sources require a licence URL")
        return self

    def database_row(self) -> dict[str, object]:
        return {
            "id": self.source_id,
            "title": self.title,
            "canonical_url": str(self.canonical_url),
            "publisher": self.publisher,
            "source_type": self.source_type,
            "license_id": self.license_id,
            "license_url": str(self.license_url) if self.license_url else None,
            "content_policy": self.content_policy,
            "permitted_use": self.permitted_use,
            "attribution_text": self.attribution_text,
            "accessed_on": self.accessed_on.isoformat(),
            "retrieval_enabled": self.retrieval_enabled,
            "review_status": self.review_status,
            "metadata": {
                "citation_key": self.citation_key,
                "used_for": self.used_for,
                "notes": self.notes,
            },
        }


class QuestionFollowUp(BaseModel):
    question_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9:_-]{2,119}$")
    trigger_criterion: str = Field(min_length=2, max_length=120)
    prompt: str = Field(min_length=15, max_length=1000)


class QuestionPackage(BaseModel):
    question_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9:_-]{2,119}$")
    package_key: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9:_-]{2,119}$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    role_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{2,79}$")
    competency_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    skill_concept_ids: list[str] = Field(default_factory=list, max_length=20)
    seniority: Literal["intern", "junior", "entry_level", "all"]
    difficulty: Literal["beginner", "intermediate"]
    question_type: Literal["core", "follow_up", "coverage", "resume_grounded"]
    prompt: str = Field(min_length=20, max_length=2000)
    expected_concepts: list[str] = Field(min_length=1, max_length=20)
    rubric: dict[Literal["1", "2", "3", "4", "5"], str]
    follow_ups: list[QuestionFollowUp] = Field(default_factory=list, max_length=2)
    reference_explanation: str = Field(min_length=20, max_length=2000)
    source_to_concept_mapping: dict[str, list[str]] = Field(min_length=1)
    author_type: Literal["team_authored", "local_llm_generated", "gemini_generated"]
    model_id: str | None = None
    prompt_version: str | None = None
    validation_status: QuestionValidationStatus
    automatic_validation: dict[str, object] = Field(default_factory=dict)
    reviewer_id: str | None = None

    @model_validator(mode="after")
    def validate_package(self) -> QuestionPackage:
        if set(self.rubric) != {"1", "2", "3", "4", "5"}:
            raise ValueError("Question rubric must contain exactly levels 1 through 5")
        if any(not anchor.strip() for anchor in self.rubric.values()):
            raise ValueError("Question rubric anchors cannot be empty")
        mapped = {
            concept
            for concepts in self.source_to_concept_mapping.values()
            for concept in concepts
        }
        if not set(self.expected_concepts).issubset(mapped):
            raise ValueError("Every expected concept must be supported by a source mapping")
        if self.author_type in {"local_llm_generated", "gemini_generated"} and not (
            self.model_id and self.prompt_version
        ):
            raise ValueError("LLM-generated packages require model and prompt versions")
        if self.validation_status == "faculty_reviewed_research_set" and not self.reviewer_id:
            raise ValueError("Research-set packages require a reviewer identifier")
        return self


class QuestionSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    role_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{2,79}$")
    competency_id: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]{2,79}$",
    )
    seniority: Literal["intern", "junior", "entry_level", "all"] | None = "junior"
    difficulty: Literal["beginner", "intermediate"] | None = None
    query_embedding: list[float] | None = None
    match_count: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def validate_embedding(self) -> QuestionSearchRequest:
        if self.query_embedding is not None and len(self.query_embedding) != 384:
            raise ValueError("Knowledge embeddings must contain exactly 384 values")
        return self


class QuestionSearchResult(BaseModel):
    id: str
    package_key: str
    version: str
    role_id: str | None = None
    competency_id: str
    seniority: str
    difficulty: str
    question_type: str
    prompt: str
    expected_concepts: list[str]
    rubric: dict[str, str]
    follow_ups: list[dict[str, object]]
    reference_explanation: str
    validation_status: str
    keyword_rank: float
    semantic_similarity: float
    hybrid_score: float


class ResourceSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    competency_id: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]{2,79}$",
    )
    difficulty: Literal["beginner", "intermediate"] | None = None
    query_embedding: list[float] | None = None
    match_count: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def validate_embedding(self) -> ResourceSearchRequest:
        if self.query_embedding is not None and len(self.query_embedding) != 384:
            raise ValueError("Knowledge embeddings must contain exactly 384 values")
        return self


class ResourceSearchResult(BaseModel):
    id: str
    title: str
    canonical_url: HttpUrl
    source_organization: str
    competency_ids: list[str]
    difficulty: str
    estimated_minutes: int
    description: str
    resource_type: str
    learning_outcomes: list[str]
    keyword_rank: float
    semantic_similarity: float
    hybrid_score: float


class KnowledgeDocumentSeed(BaseModel):
    document_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9:_-]{2,119}$")
    source_id: str = Field(pattern=r"^SRC-[0-9]{3,}$")
    title: str = Field(min_length=3, max_length=300)
    canonical_url: HttpUrl
    version_label: str = Field(min_length=3, max_length=120)
    rights_basis: str = Field(min_length=20, max_length=1000)
    chunk_key: str = Field(pattern=r"^[a-z0-9][a-z0-9:_-]{2,119}$")
    context_prefix: str = Field(min_length=10, max_length=1000)
    content: str = Field(min_length=20, max_length=12000)
    competency_ids: list[str] = Field(min_length=1, max_length=6)
    primary_question_competencies: list[str] = Field(default_factory=list, max_length=6)
    skill_terms: list[str] = Field(min_length=1, max_length=30)
    technologies: list[str] = Field(default_factory=list, max_length=20)
    difficulty: Literal["beginner", "intermediate"]

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    def document_database_row(self) -> dict[str, object]:
        return {
            "id": self.document_id,
            "source_id": self.source_id,
            "title": self.title,
            "canonical_url": str(self.canonical_url),
            "version_label": self.version_label,
            "document_type": "reviewer_summary",
            "rights_basis": self.rights_basis,
            "content_sha256": self.content_sha256,
            "ingest_status": "ready",
            "review_status": "approved",
            "retrieved_at": "2026-07-28T00:00:00+05:30",
            "metadata": {
                "seed_version": "initial-knowledge-seed-v1",
                "primary_question_competencies": self.primary_question_competencies,
            },
        }

    def chunk_database_row(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "chunk_key": self.chunk_key,
            "context_prefix": self.context_prefix,
            "content": self.content,
            "chunk_type": "reviewer_summary",
            "competency_ids": self.competency_ids,
            "skill_terms": self.skill_terms,
            "technologies": self.technologies,
            "seniority": "junior",
            "difficulty": self.difficulty,
            "content_sha256": self.content_sha256,
        }


class LearningResourceSeed(BaseModel):
    resource_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9:_-]{2,119}$")
    document_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9:_-]{2,119}$")
    title: str = Field(min_length=3, max_length=300)
    canonical_url: HttpUrl
    source_id: str = Field(pattern=r"^SRC-[0-9]{3,}$")
    source_organization: str = Field(min_length=2, max_length=200)
    competency_ids: list[str] = Field(min_length=1, max_length=6)
    skill_terms: list[str] = Field(min_length=1, max_length=30)
    technologies: list[str] = Field(default_factory=list, max_length=20)
    difficulty: Literal["beginner", "intermediate"]
    estimated_minutes: int = Field(gt=0, le=10000)
    description: str = Field(min_length=20, max_length=2000)
    learning_outcomes: list[str] = Field(min_length=1, max_length=10)
    resource_type: Literal[
        "official_documentation",
        "open_tutorial",
        "coding_exercise",
        "safe_lab",
        "mini_project",
        "reattempt_question",
    ]
    license_id: str = Field(min_length=2, max_length=300)
    attribution_text: str = Field(min_length=10, max_length=2000)
    reviewer_id: str = Field(min_length=3, max_length=120)

    def database_row(self, document: KnowledgeDocumentSeed) -> dict[str, object]:
        return {
            "id": self.resource_id,
            "title": self.title,
            "canonical_url": str(self.canonical_url),
            "source_organization": self.source_organization,
            "competency_ids": self.competency_ids,
            "difficulty": self.difficulty,
            "estimated_minutes": self.estimated_minutes,
            "description": self.description,
            "reviewer_status": "approved",
            "reviewed_at": "2026-07-28T00:00:00+05:30",
            "source_id": self.source_id,
            "skill_terms": self.skill_terms,
            "technologies": self.technologies,
            "learning_outcomes": self.learning_outcomes,
            "resource_type": self.resource_type,
            "license_id": self.license_id,
            "attribution_text": self.attribution_text,
            "url_status": "valid",
            "url_verified_at": "2026-07-28T00:00:00+05:30",
            "original_summary": document.content,
            "reviewer_id": self.reviewer_id,
        }

    def chunk_database_row(self, document: KnowledgeDocumentSeed) -> dict[str, object]:
        return {
            "resource_id": self.resource_id,
            "chunk_key": "reviewed-summary",
            "context_prefix": document.context_prefix,
            "content": document.content,
            "content_sha256": document.content_sha256,
        }


class InitialKnowledgeSeed(BaseModel):
    schema_version: Literal["initial-knowledge-seed-v1"]
    documents: list[KnowledgeDocumentSeed] = Field(min_length=1)
    resources: list[LearningResourceSeed] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_relations(self) -> InitialKnowledgeSeed:
        documents = {document.document_id: document for document in self.documents}
        if len(documents) != len(self.documents):
            raise ValueError("Knowledge document identifiers must be unique")
        if len({resource.resource_id for resource in self.resources}) != len(
            self.resources
        ):
            raise ValueError("Learning resource identifiers must be unique")
        registered_sources = {source.source_id for source in load_source_registry()}
        known_competencies = {
            competency.competency_id
            for role in list_role_templates()
            for competency in role.competencies
        }
        for document in self.documents:
            if document.source_id not in registered_sources:
                raise ValueError(f"Unknown document source: {document.source_id}")
            unknown = set(document.competency_ids) - known_competencies
            if unknown:
                raise ValueError(f"Unknown document competencies: {sorted(unknown)}")
        for resource in self.resources:
            document = documents.get(resource.document_id)
            if document is None:
                raise ValueError(f"Unknown resource document: {resource.document_id}")
            if resource.source_id != document.source_id:
                raise ValueError("Resource and document source identifiers must match")
            if str(resource.canonical_url) != str(document.canonical_url):
                raise ValueError("Resource and document canonical URLs must match")
            unknown = set(resource.competency_ids) - known_competencies
            if unknown:
                raise ValueError(f"Unknown resource competencies: {sorted(unknown)}")
        return self


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


@lru_cache
def load_source_registry() -> list[KnowledgeSource]:
    policies_payload = _read_json(SOURCE_POLICIES)
    policies = policies_payload.get("sources")
    if not isinstance(policies, list):
        raise ValueError("Source policies must contain a sources list")
    policy_by_id = {
        str(item["source_id"]): item
        for item in policies
        if isinstance(item, dict) and "source_id" in item
    }
    with SOURCES_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    records: list[KnowledgeSource] = []
    for row in rows:
        policy = policy_by_id.get(row["source_id"])
        if policy is None:
            continue
        records.append(
            KnowledgeSource.model_validate(
                {
                    "source_id": row["source_id"],
                    "title": row["title"],
                    "canonical_url": row["url"],
                    "license_id": row["license"],
                    "accessed_on": row["accessed_date"],
                    "used_for": row["used_for"],
                    "citation_key": row["citation_key"],
                    "notes": row["notes"],
                    **policy,
                }
            )
        )
    missing = set(policy_by_id) - {record.source_id for record in records}
    if missing:
        raise ValueError(f"Source policies reference missing CSV records: {sorted(missing)}")
    return records


@lru_cache
def load_initial_knowledge_seed() -> InitialKnowledgeSeed:
    return InitialKnowledgeSeed.model_validate(_read_json(INITIAL_KNOWLEDGE_SEED))


def resolve_source_document_id(
    source_id: str,
    competency_id: str,
    *,
    concepts: list[str] | None = None,
    seed: InitialKnowledgeSeed | None = None,
) -> str:
    """Resolve a registry source to its competency-specific reviewed document."""

    knowledge_seed = seed or load_initial_knowledge_seed()
    candidates = [
        document
        for document in knowledge_seed.documents
        if document.source_id == source_id
        and competency_id in document.competency_ids
    ]
    primary_candidates = [
        document
        for document in candidates
        if competency_id in document.primary_question_competencies
    ]
    if primary_candidates:
        candidates = primary_candidates
    if len(candidates) > 1 and concepts:
        concept_tokens = {
            token
            for concept in concepts
            for token in re.findall(r"[a-z0-9]+", concept.lower())
            if len(token) >= 3
        }
        scored = []
        for document in candidates:
            searchable = " ".join(
                [
                    document.title,
                    document.context_prefix,
                    document.content,
                    *document.skill_terms,
                    *document.technologies,
                ]
            ).lower()
            searchable_tokens = set(re.findall(r"[a-z0-9]+", searchable))
            scored.append((len(concept_tokens & searchable_tokens), document))
        best_score = max(score for score, _document in scored)
        candidates = [
            document for score, document in scored if score == best_score and score > 0
        ]
    if len(candidates) != 1:
        raise ValueError(
            "Expected exactly one reviewed source document for "
            f"{source_id}/{competency_id}, found {len(candidates)}"
        )
    return candidates[0].document_id


def build_seed_question_packages() -> list[QuestionPackage]:
    """Convert reviewed role templates into versioned, not-yet-grounded bank drafts."""

    source_by_competency: dict[str, str] = {}
    for document in load_initial_knowledge_seed().documents:
        for competency_id in document.competency_ids:
            source_by_competency.setdefault(competency_id, document.source_id)
    # These broad competencies use dedicated CS2023 reviewer summaries instead
    # of narrower technology pages that happen to share the competency label.
    source_by_competency.update(
        {
            "programming_fundamentals": "SRC-012",
            "debugging_problem_solving": "SRC-012",
            "system_design_basics": "SRC-012",
            "frontend_engineering": "SRC-012",
            "data_analysis_sql": "SRC-012",
        }
    )
    packages: list[QuestionPackage] = []
    for role in list_role_templates():
        for competency in role.competencies:
            source_id = source_by_competency[competency.competency_id]
            expected = competency.core_question.expected_evidence
            mapping = {source_id: expected}
            packages.append(
                QuestionPackage(
                    question_id=(
                        f"{role.role_id}:{competency.core_question.question_id}:v1"
                    ),
                    package_key=(
                        f"{role.role_id}:{competency.core_question.question_id}"
                    ),
                    version="1.0.0",
                    role_id=role.role_id,
                    competency_id=competency.competency_id,
                    skill_concept_ids=competency.approved_skill_terms[:10],
                    seniority="junior",
                    difficulty="beginner",
                    question_type="core",
                    prompt=competency.core_question.prompt,
                    expected_concepts=expected,
                    rubric={
                        "1": "No meaningful understanding or an answer unrelated to the question.",
                        "2": "Partial understanding with major omissions or an unsafe sequence.",
                        "3": "Correct basic understanding covering the central expected concepts.",
                        "4": (
                            "Complete practical understanding covering the expected "
                            "concepts, validation, and a workable sequence."
                        ),
                        "5": (
                            "Complete practical understanding plus justified risks, "
                            "alternatives, constraints, or trade-offs."
                        ),
                    },
                    follow_ups=[
                        QuestionFollowUp.model_validate(item.model_dump())
                        for item in competency.follow_ups
                    ],
                    reference_explanation=(
                        f"A junior answer should provide evidence for {competency.name}: "
                        f"{'; '.join(expected)}. The assessment standard is tied to "
                        f"reviewed source {source_id} and remains unavailable until "
                        "independent grounding validation succeeds."
                    ),
                    source_to_concept_mapping=mapping,
                    author_type="team_authored",
                    validation_status="pending_automatic_validation",
                    automatic_validation={
                        "schema_valid": True,
                        "source_ids_registered": True,
                        "grounded_semantic_validation": False,
                        "retrievable": False,
                    },
                )
            )
    return packages
