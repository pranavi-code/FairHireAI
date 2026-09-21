"""Generate personalized questions only from reviewed local knowledge."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from backend.app.domain.knowledge import (
    QuestionFollowUp,
    QuestionPackage,
    load_initial_knowledge_seed,
)
from backend.app.domain.roles import load_role_template
from backend.app.providers.gemini import GeminiClient
from backend.app.services.question_novelty import (
    NoveltyDecision,
    assess_question_novelty,
    compact_history_themes,
    normalize_question,
)

PROMPT_VERSION = "grounded-adaptive-question-gemini-v2"
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


class GroundedQuestionContentError(ValueError):
    """A model response was reachable but failed the question safety contract."""

    def __init__(
        self,
        message: str,
        *,
        candidate_prompt: str | None = None,
        novelty: NoveltyDecision | None = None,
    ) -> None:
        self.candidate_prompt = candidate_prompt
        self.novelty = novelty
        super().__init__(message)


class PersonalizedQuestionRequest(BaseModel):
    role_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    competency_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    candidate_skill_terms: list[str] = Field(default_factory=list, max_length=20)
    jd_skill_terms: list[str] = Field(default_factory=list, max_length=20)
    resume_evidence_summaries: list[str] = Field(default_factory=list, max_length=8)
    recent_question_prompts: list[str] = Field(default_factory=list, max_length=36)
    recent_question_ids: list[str] = Field(default_factory=list, max_length=36)
    rejected_question_prompts: list[str] = Field(default_factory=list, max_length=12)
    previous_question: str | None = Field(default=None, max_length=2_000)
    previous_answer_excerpt: str | None = Field(default=None, max_length=4_000)
    missing_concepts: list[str] = Field(default_factory=list, max_length=20)
    weakest_criterion: str | None = Field(default=None, max_length=500)
    variation_instruction: str | None = Field(default=None, max_length=300)
    generation_strategy: str = Field(default="preferred_anchor", max_length=80)
    scenario_instruction: str | None = Field(default=None, max_length=300)
    structure_instruction: str | None = Field(default=None, max_length=300)
    omit_anchor_wording: bool = False
    controlled_relaxation: bool = False
    generation_nonce: str | None = Field(default=None, max_length=80)
    is_follow_up: bool = False
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
            *self.recent_question_prompts,
            *self.rejected_question_prompts,
            *self.missing_concepts,
        ):
            if len(value) > 2_000:
                raise ValueError("Personalization items must not exceed 2,000 characters")
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
    novel_against_recent_questions: bool
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
            and self.novel_against_recent_questions
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


def _history_to_avoid(request: PersonalizedQuestionRequest) -> list[str]:
    """Keep a follow-up's parent out of semantic anti-repetition history.

    A legitimate follow-up must remain on the parent scenario and will naturally
    share its terminology. The parent is supplied separately and still receives
    an exact-repeat check.
    """

    if not request.is_follow_up or not request.previous_question:
        return request.recent_question_prompts
    parent = normalize_question(request.previous_question)
    return [
        prompt
        for prompt in request.recent_question_prompts
        if normalize_question(prompt) != parent
    ]


class GroundedQuestionService:
    def __init__(self, client: GeminiClient) -> None:
        self._client = client

    def generate(
        self,
        request: PersonalizedQuestionRequest,
        *,
        anchor_package: QuestionPackage | None = None,
    ) -> QuestionPackage:
        role = load_role_template(request.role_id)
        try:
            competency = next(
                item for item in role.competencies if item.competency_id == request.competency_id
            )
        except StopIteration as exc:
            raise ValueError("The competency is not part of the selected role") from exc
        if anchor_package is not None:
            if (
                anchor_package.role_id != request.role_id
                or anchor_package.competency_id != request.competency_id
                or anchor_package.validation_status
                not in {
                    "generated_validated_for_practice",
                    "faculty_reviewed_research_set",
                }
            ):
                raise ValueError("The RAG anchor is not a validated package for this competency")
        reviewed_context, allowed_source_ids = _reviewed_context(request.competency_id)
        history_to_avoid = _history_to_avoid(request)
        rejected_themes = compact_history_themes(request.rejected_question_prompts)
        history_themes = compact_history_themes(history_to_avoid)
        anchor_context = None
        if anchor_package is not None:
            anchor_context = {
                "question_id": anchor_package.question_id,
                "expected_concepts": anchor_package.expected_concepts,
                "rubric": anchor_package.rubric,
                "follow_ups": [
                    item.model_dump(mode="json") for item in anchor_package.follow_ups
                ],
                "reference_explanation": anchor_package.reference_explanation,
                "source_to_concept_mapping": anchor_package.source_to_concept_mapping,
            }
            if not request.omit_anchor_wording:
                anchor_context["prompt"] = anchor_package.prompt
        prompt = json.dumps(
            {
                "task": (
                    "Create one answer-adaptive follow-up interview question."
                    if request.is_follow_up
                    else "Create one new evidence-seeking junior interview question."
                ),
                "role": role.display_name,
                "competency": competency.name,
                "competency_description": competency.description,
                "difficulty": request.difficulty,
                "candidate_skill_terms": request.candidate_skill_terms,
                "job_description_skill_terms": request.jd_skill_terms,
                "minimized_resume_evidence": request.resume_evidence_summaries,
                "previous_question": request.previous_question,
                "previous_answer_excerpt": request.previous_answer_excerpt,
                "missing_concepts_from_evaluation": request.missing_concepts,
                "weakest_rubric_criterion": request.weakest_criterion,
                "recent_question_themes_to_avoid": history_themes,
                "rejected_candidate_themes_to_avoid": rejected_themes,
                "generation_strategy": request.generation_strategy,
                "scenario_instruction": request.scenario_instruction,
                "question_structure_instruction": request.structure_instruction,
                "retry_diversity_strategy": request.variation_instruction,
                "generation_nonce": request.generation_nonce,
                "reviewed_sources": reviewed_context,
                "approved_assessment_standard": anchor_context,
                "rules": [
                    "Use only the reviewed source summaries.",
                    "Do not ask about protected or personal characteristics.",
                    "Do not invent technologies, experience, URLs, or claims.",
                    "Personalization may change wording, never the assessment standard.",
                    (
                        "Continue the parent scenario when useful, but ask for new evidence and "
                        "never repeat the parent's exact request."
                        if request.is_follow_up
                        else "Create a materially different scenario and wording from every "
                        "recent question."
                    ),
                    "Do not merely paraphrase or reorder words from a recent question.",
                    (
                        "Change the scenario, reasoning task, and structure when the retry "
                        "strategy asks."
                    ),
                    "Generic competency terms may be reused; the underlying question must be new.",
                    (
                        "For a follow-up, respond directly to the supplied previous answer, target "
                        "its missing concepts or weakest criterion, and ask only one focused probe."
                    ),
                    (
                        "For a core question, use the role, JD, resume, reviewed sources, "
                        "and prior "
                        "interview evidence without assuming unverified experience."
                    ),
                    "Map every expected concept to a supplied SOURCE_ID.",
                    "Use exactly rubric levels 1, 2, 3, 4, and 5.",
                    "Provide at most two bounded follow-ups.",
                    (
                        "When an approved assessment standard is supplied, create a new "
                        "question and copy its expected concepts, rubric, "
                        "follow-ups, reference explanation, and source mapping exactly."
                    ),
                    (
                        "The anchor wording is intentionally withheld. Generate from the "
                        "competency, rubric, concepts, and reviewed sources instead."
                        if request.omit_anchor_wording
                        else "Use the anchor only as grounding, not as a paraphrase template."
                    ),
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
            temperature=0.9,
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
        try:
            generated = GeneratedQuestionContent.model_validate(raw_generated)
        except ValidationError as exc:
            raise GroundedQuestionContentError(
                "Gemini returned a question that did not match the required structure."
            ) from exc
        if (
            request.is_follow_up
            and request.previous_question
            and normalize_question(generated.prompt)
            == normalize_question(request.previous_question)
        ):
            raise GroundedQuestionContentError(
                "Gemini repeated the parent question instead of asking a follow-up.",
                candidate_prompt=generated.prompt,
            )
        novelty = assess_question_novelty(
            generated.prompt,
            history_to_avoid,
            controlled_relaxation=request.controlled_relaxation,
        )
        if novelty.is_duplicate:
            raise GroundedQuestionContentError(
                f"Gemini generated a repetitive question ({novelty.reason}).",
                candidate_prompt=generated.prompt,
                novelty=novelty,
            )
        if anchor_package is not None and (
            generated.expected_concepts != anchor_package.expected_concepts
            or generated.rubric != anchor_package.rubric
            or generated.follow_ups != anchor_package.follow_ups
            or generated.reference_explanation != anchor_package.reference_explanation
            or generated.source_to_concept_mapping
            != anchor_package.source_to_concept_mapping
        ):
            raise GroundedQuestionContentError(
                "Gemini changed the approved assessment standard during personalization.",
                candidate_prompt=generated.prompt,
            )
        mapped_sources = set(generated.source_to_concept_mapping)
        if not mapped_sources or not mapped_sources.issubset(allowed_source_ids):
            raise GroundedQuestionContentError(
                "Gemini referenced a source outside the reviewed context."
            )
        if _contains_forbidden_trait(generated.prompt):
            raise GroundedQuestionContentError(
                "Gemini produced a question about a protected trait."
            )

        validation = self._validate(
            generated=generated,
            role_name=role.display_name,
            competency_name=competency.name,
            reviewed_context=reviewed_context,
            recent_question_prompts=history_to_avoid,
            is_follow_up=request.is_follow_up,
            previous_question=request.previous_question,
            previous_answer_excerpt=request.previous_answer_excerpt,
            missing_concepts=request.missing_concepts,
            weakest_criterion=request.weakest_criterion,
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
            question_type=(
                "follow_up"
                if request.is_follow_up
                else ("resume_grounded" if request.resume_evidence_summaries else "coverage")
            ),
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
            recent_question_prompts=[],
            is_follow_up=package.question_type == "follow_up",
            previous_question=None,
            previous_answer_excerpt=None,
            missing_concepts=[],
            weakest_criterion=None,
        )

    def _validate(
        self,
        *,
        generated: GeneratedQuestionContent,
        role_name: str,
        competency_name: str,
        reviewed_context: str,
        recent_question_prompts: list[str],
        is_follow_up: bool,
        previous_question: str | None,
        previous_answer_excerpt: str | None,
        missing_concepts: list[str],
        weakest_criterion: str | None,
    ) -> QuestionValidationReport:
        payload = {
            "role": role_name,
            "competency": competency_name,
            "question_package": generated.model_dump(mode="json"),
            "reviewed_sources": reviewed_context,
            "is_follow_up": is_follow_up,
            "recent_question_themes": compact_history_themes(recent_question_prompts),
            "previous_question": previous_question,
            "previous_answer_excerpt": previous_answer_excerpt,
            "missing_concepts_from_evaluation": missing_concepts,
            "weakest_rubric_criterion": weakest_criterion,
            "validation_rules": [
                "All expected concepts and reference explanations are source-supported.",
                "The question is answerable by a junior candidate.",
                "The question avoids protected traits and irrelevant personal information.",
                "The rubric assesses technical evidence consistently.",
                "The question is materially different from the supplied recent questions.",
                "A follow-up directly probes the supplied answer rather than restarting the topic.",
            ],
        }
        try:
            return QuestionValidationReport.model_validate(
                self._client.generate_json(
                    system_instruction=(
                        "You are an independent grounding and fairness validator. "
                        "Reject unsupported, discriminatory, senior-only, or unanswerable "
                        "questions."
                    ),
                    prompt=json.dumps(payload, ensure_ascii=False),
                    response_schema=QuestionValidationReport.model_json_schema(),
                    temperature=0.1,
                )
            )
        except ValidationError as exc:
            raise GroundedQuestionContentError(
                "Gemini returned an invalid independent-validation result."
            ) from exc
