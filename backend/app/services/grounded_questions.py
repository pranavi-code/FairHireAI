"""Generate personalized questions only from reviewed local knowledge."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.app.domain.knowledge import (
    QuestionFollowUp,
    QuestionPackage,
    load_initial_knowledge_seed,
)
from backend.app.domain.roles import load_role_template
from backend.app.providers.gemini import GeminiClient, GeminiProviderError

PROMPT_VERSION = "grounded-question-gemini-v1"
FORBIDDEN_PERSONAL_TRAITS = {
    "age",
    "caste",
    "ethnicity",
    "gender",
    "marital status",
    "nationality",
    "pregnancy",
    "race",
    "religion",
    "sexual orientation",
}


class PersonalizedQuestionRequest(BaseModel):
    role_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    competency_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    candidate_skill_terms: list[str] = Field(default_factory=list, max_length=20)
    jd_skill_terms: list[str] = Field(default_factory=list, max_length=20)
    resume_evidence_summaries: list[str] = Field(default_factory=list, max_length=8)
    difficulty: Literal["beginner", "intermediate"] = "beginner"
    external_ai_processing_consent: bool

    @model_validator(mode="after")
    def validate_external_processing(self) -> PersonalizedQuestionRequest:
        if not self.external_ai_processing_consent:
            raise ValueError("Explicit consent is required before sending context to Gemini")
        for value in (
            *self.candidate_skill_terms,
            *self.jd_skill_terms,
            *self.resume_evidence_summaries,
        ):
            if len(value) > 500:
                raise ValueError("Personalization items must not exceed 500 characters")
        return self


class GeneratedQuestionContent(BaseModel):
    prompt: str = Field(min_length=20, max_length=2000)
    expected_concepts: list[str] = Field(min_length=1, max_length=12)
    rubric: dict[Literal["1", "2", "3", "4", "5"], str]
    follow_ups: list[QuestionFollowUp] = Field(default_factory=list, max_length=2)
    reference_explanation: str = Field(min_length=20, max_length=2000)
    source_to_concept_mapping: dict[str, list[str]] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_rubric(self) -> GeneratedQuestionContent:
        if set(self.rubric) != {"1", "2", "3", "4", "5"}:
            raise ValueError("The generated rubric must contain exactly levels 1 through 5")
        return self


class QuestionValidationReport(BaseModel):
    grounded: bool
    fair: bool
    junior_level: bool
    answerable_from_sources: bool
    unsupported_claims: list[str] = Field(default_factory=list, max_length=10)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=10, max_length=1000)

    @property
    def passed(self) -> bool:
        return (
            self.grounded
            and self.fair
            and self.junior_level
            and self.answerable_from_sources
            and not self.unsupported_claims
            and self.confidence >= 0.80
        )


def _reviewed_context(competency_id: str) -> tuple[str, set[str]]:
    documents = [
        document
        for document in load_initial_knowledge_seed().documents
        if competency_id in document.competency_ids
    ]
    if not documents:
        raise ValueError(f"No reviewed knowledge is available for competency {competency_id}")
    context = "\n\n".join(
        (
            f"SOURCE_ID: {document.source_id}\n"
            f"TITLE: {document.title}\n"
            f"CONTEXT: {document.context_prefix}\n"
            f"REVIEWED_SUMMARY: {document.content}"
        )
        for document in documents
    )
    return context, {document.source_id for document in documents}


def _contains_forbidden_trait(text: str) -> bool:
    lowered = text.casefold()
    return any(
        re.search(rf"(?<!\w){re.escape(trait)}(?!\w)", lowered)
        for trait in FORBIDDEN_PERSONAL_TRAITS
    )


class GroundedQuestionService:
    def __init__(self, client: GeminiClient) -> None:
        self._client = client

    def generate(self, request: PersonalizedQuestionRequest) -> QuestionPackage:
        role = load_role_template(request.role_id)
        try:
            competency = next(
                item for item in role.competencies if item.competency_id == request.competency_id
            )
        except StopIteration as exc:
            raise ValueError("The competency is not part of the selected role") from exc
        reviewed_context, allowed_source_ids = _reviewed_context(request.competency_id)
        prompt = json.dumps(
            {
                "task": "Create one evidence-seeking junior interview question.",
                "role": role.display_name,
                "competency": competency.name,
                "competency_description": competency.description,
                "difficulty": request.difficulty,
                "candidate_skill_terms": request.candidate_skill_terms,
                "job_description_skill_terms": request.jd_skill_terms,
                "minimized_resume_evidence": request.resume_evidence_summaries,
                "reviewed_sources": reviewed_context,
                "rules": [
                    "Use only the reviewed source summaries.",
                    "Do not ask about protected or personal characteristics.",
                    "Do not invent technologies, experience, URLs, or claims.",
                    "Personalization may change wording, never the assessment standard.",
                    "Map every expected concept to a supplied SOURCE_ID.",
                    "Use exactly rubric levels 1, 2, 3, 4, and 5.",
                    "Provide at most two bounded follow-ups.",
                ],
            },
            ensure_ascii=False,
        )
        response_schema = GeneratedQuestionContent.model_json_schema()
        response_schema["properties"]["rubric"] = {
            "type": "object",
            "properties": {str(level): {"type": "string"} for level in range(1, 6)},
            "required": [str(level) for level in range(1, 6)],
            "additionalProperties": False,
        }
        raw_generated = self._client.generate_json(
            system_instruction=(
                "You create fair, grounded, entry-level technical interview questions. "
                "Return only data matching the supplied JSON schema."
            ),
            prompt=prompt,
            response_schema=response_schema,
        )
        rubric = raw_generated.get("rubric")
        if isinstance(rubric, dict) and set(rubric) == {
            "level_1",
            "level_2",
            "level_3",
            "level_4",
            "level_5",
        }:
            raw_generated["rubric"] = {
                key.removeprefix("level_"): value for key, value in rubric.items()
            }
        generated = GeneratedQuestionContent.model_validate(raw_generated)
        mapped_sources = set(generated.source_to_concept_mapping)
        if not mapped_sources or not mapped_sources.issubset(allowed_source_ids):
            raise GeminiProviderError("Gemini referenced a source outside the reviewed context.")
        if _contains_forbidden_trait(generated.prompt):
            raise GeminiProviderError("Gemini produced a question about a protected trait.")

        validation = self._validate(
            generated=generated,
            role_name=role.display_name,
            competency_name=competency.name,
            reviewed_context=reviewed_context,
        )
        content_hash = hashlib.sha256(
            (
                request.role_id
                + request.competency_id
                + generated.prompt
                + self._client.generation_model
            ).encode("utf-8")
        ).hexdigest()[:16]
        status = "generated_validated_for_practice" if validation.passed else "rejected"
        return QuestionPackage(
            question_id=f"gemini:{request.role_id}:{request.competency_id}:{content_hash}",
            package_key=f"gemini:{request.role_id}:{request.competency_id}:{content_hash}",
            version="1.0.0",
            role_id=request.role_id,
            competency_id=request.competency_id,
            skill_concept_ids=sorted(set(request.candidate_skill_terms + request.jd_skill_terms))[
                :20
            ],
            seniority="junior",
            difficulty=request.difficulty,
            question_type=("resume_grounded" if request.resume_evidence_summaries else "coverage"),
            **generated.model_dump(),
            author_type="gemini_generated",
            model_id=self._client.generation_model,
            prompt_version=PROMPT_VERSION,
            validation_status=status,
            automatic_validation={
                "schema_valid": True,
                "source_ids_registered": True,
                "deterministic_fairness_check": True,
                "grounded_semantic_validation": validation.model_dump(),
                "retrievable": validation.passed,
            },
        )

    def validate_team_package(
        self,
        package: QuestionPackage,
    ) -> QuestionValidationReport:
        if package.role_id is None:
            raise ValueError("A role-specific package is required")
        role = load_role_template(package.role_id)
        competency = next(
            (item for item in role.competencies if item.competency_id == package.competency_id),
            None,
        )
        if competency is None:
            raise ValueError("The package competency is not part of its role")
        reviewed_context, allowed_source_ids = _reviewed_context(package.competency_id)
        if not set(package.source_to_concept_mapping).issubset(allowed_source_ids):
            raise ValueError("The package maps concepts to an unrelated reviewed source")
        generated = GeneratedQuestionContent(
            prompt=package.prompt,
            expected_concepts=package.expected_concepts,
            rubric=package.rubric,
            follow_ups=package.follow_ups,
            reference_explanation=package.reference_explanation,
            source_to_concept_mapping=package.source_to_concept_mapping,
        )
        if _contains_forbidden_trait(generated.prompt):
            raise ValueError("The package contains a protected trait")
        return self._validate(
            generated=generated,
            role_name=role.display_name,
            competency_name=competency.name,
            reviewed_context=reviewed_context,
        )

    def _validate(
        self,
        *,
        generated: GeneratedQuestionContent,
        role_name: str,
        competency_name: str,
        reviewed_context: str,
    ) -> QuestionValidationReport:
        payload = {
            "role": role_name,
            "competency": competency_name,
            "question_package": generated.model_dump(mode="json"),
            "reviewed_sources": reviewed_context,
            "validation_rules": [
                "All expected concepts and reference explanations are source-supported.",
                "The question is answerable by a junior candidate.",
                "The question avoids protected traits and irrelevant personal information.",
                "The rubric assesses technical evidence consistently.",
            ],
        }
        return QuestionValidationReport.model_validate(
            self._client.generate_json(
                system_instruction=(
                    "You are an independent grounding and fairness validator. "
                    "Reject unsupported, discriminatory, senior-only, or unanswerable questions."
                ),
                prompt=json.dumps(payload, ensure_ascii=False),
                response_schema=QuestionValidationReport.model_json_schema(),
            )
        )
