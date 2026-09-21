"""Progressive, history-aware recovery for grounded interview generation."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from backend.app.domain.knowledge import QuestionPackage
from backend.app.services.grounded_questions import (
    GroundedQuestionContentError,
    GroundedQuestionService,
    PersonalizedQuestionRequest,
)
from backend.app.services.hybrid_rag import RetrievedQuestion
from backend.app.services.question_novelty import compact_history_themes

logger = logging.getLogger(__name__)

SCENARIO_FAMILIES = (
    "education or campus operations",
    "logistics or delivery operations",
    "healthcare service operations",
    "ecommerce or customer operations",
    "public-service operations",
    "internal product or reliability operations",
)

QUESTION_STRUCTURES = (
    "solution design with justification",
    "diagnose a flawed result or failure",
    "compare alternatives and explain a trade-off",
    "interpret evidence and state a defensible conclusion",
    "communicate a recommendation to a non-technical stakeholder",
    "propose verification tests and success criteria",
)


@dataclass(frozen=True)
class GenerationStage:
    name: str
    anchor_offset: int
    variation: str
    scenario: str | None = None
    structure: str | None = None
    omit_anchor_wording: bool = False
    controlled_relaxation: bool = False


@dataclass(frozen=True)
class AdaptiveGenerationResult:
    generated: QuestionPackage
    anchor: RetrievedQuestion
    strategy: str
    attempted_candidates: int
    rejected_candidates: int


class QuestionGenerationExhaustedError(ValueError):
    """All bounded dynamic recovery strategies produced invalid content."""

    def __init__(self, attempted_candidates: int, rejection_reasons: list[str]) -> None:
        self.attempted_candidates = attempted_candidates
        self.rejection_reasons = rejection_reasons
        super().__init__(
            "Dynamic question generation exhausted all validated recovery strategies."
        )


def _unused_dimension(
    values: tuple[str, ...],
    used: set[str],
    *,
    offset: int,
) -> str:
    for index in range(len(values)):
        value = values[(offset + index) % len(values)]
        if not any(token in value for token in used):
            return value
    return values[offset % len(values)]


def build_generation_stages(request: PersonalizedQuestionRequest) -> tuple[GenerationStage, ...]:
    themes = compact_history_themes(request.recent_question_prompts, maximum=12)
    used_scenarios = {
        value for theme in themes for value in theme.get("scenarios", [])
    }
    used_structures = {
        value for theme in themes for value in theme.get("structures", [])
    }
    seed = int(
        hashlib.sha256(
            (
                request.role_id
                + request.competency_id
                + str(len(request.recent_question_prompts))
            ).encode("utf-8")
        ).hexdigest()[:8],
        16,
    )
    scenario_one = _unused_dimension(
        SCENARIO_FAMILIES, used_scenarios, offset=seed % len(SCENARIO_FAMILIES)
    )
    scenario_two = _unused_dimension(
        SCENARIO_FAMILIES,
        used_scenarios | {scenario_one.split()[0]},
        offset=(seed + 2) % len(SCENARIO_FAMILIES),
    )
    structure_one = _unused_dimension(
        QUESTION_STRUCTURES, used_structures, offset=seed % len(QUESTION_STRUCTURES)
    )
    structure_two = _unused_dimension(
        QUESTION_STRUCTURES,
        used_structures | {structure_one.split()[0]},
        offset=(seed + 2) % len(QUESTION_STRUCTURES),
    )
    if request.is_follow_up:
        scenario_one = "Remain in the supplied parent scenario and probe a missing detail."
        scenario_two = "Remain answer-adaptive; introduce an edge case within the parent scenario."
    return (
        GenerationStage(
            "preferred_anchor",
            0,
            "Generate a direct evidence-seeking question without reusing an avoided theme.",
        ),
        GenerationStage(
            "diverse_candidate",
            0,
            "Change the reasoning operation, not merely the wording.",
            structure=structure_one,
        ),
        GenerationStage(
            "rejection_aware",
            0,
            "Use the rejected-candidate themes to avoid their scenario and underlying task.",
            scenario=scenario_one,
            structure=structure_two,
        ),
        GenerationStage(
            "alternate_anchor",
            1,
            "Use a different retrieved assessment anchor when one is available.",
            scenario=scenario_two,
            structure=structure_one,
        ),
        GenerationStage(
            "scenario_switch",
            2,
            "Switch to a business domain absent from the supplied history.",
            scenario=scenario_two,
            structure=structure_two,
        ),
        GenerationStage(
            "structure_switch",
            3,
            "Switch from the rejected task family to a different reasoning structure.",
            scenario=scenario_one,
            structure="Choose a question structure absent from the history themes.",
        ),
        GenerationStage(
            "rubric_guided",
            4,
            "Generate from the competency, expected concepts, rubric, and reviewed sources.",
            scenario=scenario_two,
            structure="Ask for verification, trade-offs, or interpretation rather than recall.",
            omit_anchor_wording=True,
        ),
        GenerationStage(
            "controlled_dynamic_fallback",
            5,
            (
                "Create a fresh dynamic question from the assessment standard; "
                "never use fixed wording."
            ),
            scenario="Select any safe scenario not represented in the avoided themes.",
            structure="Select any valid reasoning structure not represented in the avoided themes.",
            omit_anchor_wording=True,
            controlled_relaxation=True,
        ),
    )


class AdaptiveQuestionGenerationService:
    def __init__(self, question_service: GroundedQuestionService) -> None:
        self._question_service = question_service

    def generate(
        self,
        request: PersonalizedQuestionRequest,
        *,
        anchors: list[RetrievedQuestion],
        correlation_id: str,
    ) -> AdaptiveGenerationResult:
        if not anchors:
            raise ValueError("At least one validated question anchor is required")
        stages = build_generation_stages(request)
        rejected_prompts: list[str] = []
        rejection_reasons: list[str] = []
        previous_anchor: str | None = None
        for attempt_number, stage in enumerate(stages, start=1):
            anchor = anchors[stage.anchor_offset % len(anchors)]
            anchor_id = anchor.package_model.question_id
            if previous_anchor is not None and anchor_id != previous_anchor:
                logger.info(
                    "question_generation_anchor_switch correlation_id=%s role=%s "
                    "competency=%s from_anchor=%s to_anchor=%s strategy=%s",
                    correlation_id,
                    request.role_id,
                    request.competency_id,
                    previous_anchor,
                    anchor_id,
                    stage.name,
                )
            previous_anchor = anchor_id
            if stage.name == "controlled_dynamic_fallback":
                logger.info(
                    "question_generation_fallback_activated correlation_id=%s role=%s "
                    "competency=%s history_count=%s rejection_count=%s",
                    correlation_id,
                    request.role_id,
                    request.competency_id,
                    len(request.recent_question_prompts),
                    len(rejected_prompts),
                )
            staged_request = request.model_copy(
                update={
                    "generation_strategy": stage.name,
                    "variation_instruction": stage.variation,
                    "scenario_instruction": stage.scenario,
                    "structure_instruction": stage.structure,
                    "rejected_question_prompts": rejected_prompts[-12:],
                    "omit_anchor_wording": stage.omit_anchor_wording,
                    "controlled_relaxation": stage.controlled_relaxation,
                    "generation_nonce": hashlib.sha256(
                        f"{correlation_id}:{attempt_number}:{stage.name}".encode()
                    ).hexdigest()[:16],
                }
            )
            try:
                generated = self._question_service.generate(
                    staged_request,
                    anchor_package=anchor.package_model,
                )
                if generated.validation_status != "generated_validated_for_practice":
                    raise GroundedQuestionContentError(
                        "Independent grounding and fairness validation rejected the candidate.",
                        candidate_prompt=generated.prompt,
                    )
            except GroundedQuestionContentError as exc:
                rejection_reasons.append(str(exc))
                if exc.candidate_prompt:
                    rejected_prompts.append(exc.candidate_prompt)
                novelty = exc.novelty
                matched_id = None
                if (
                    novelty is not None
                    and novelty.matched_index is not None
                    and novelty.matched_index < len(request.recent_question_ids)
                ):
                    matched_id = request.recent_question_ids[novelty.matched_index]
                logger.info(
                    "question_generation_candidate_rejected correlation_id=%s role=%s "
                    "competency=%s history_count=%s anchor_count=%s anchor_id=%s "
                    "strategy=%s attempt=%s reason=%s matched_history_id=%s "
                    "sequence_similarity=%.4f concept_similarity=%.4f",
                    correlation_id,
                    request.role_id,
                    request.competency_id,
                    len(request.recent_question_prompts),
                    len(anchors),
                    anchor_id,
                    stage.name,
                    attempt_number,
                    str(exc),
                    matched_id,
                    novelty.sequence_similarity if novelty else 0.0,
                    novelty.concept_similarity if novelty else 0.0,
                )
                continue
            logger.info(
                "question_generation_candidate_accepted correlation_id=%s role=%s "
                "competency=%s history_count=%s anchor_count=%s anchor_id=%s "
                "strategy=%s attempt=%s rejected_candidates=%s question_id=%s",
                correlation_id,
                request.role_id,
                request.competency_id,
                len(request.recent_question_prompts),
                len(anchors),
                anchor_id,
                stage.name,
                attempt_number,
                len(rejected_prompts),
                generated.question_id,
            )
            return AdaptiveGenerationResult(
                generated=generated,
                anchor=anchor,
                strategy=stage.name,
                attempted_candidates=attempt_number,
                rejected_candidates=len(rejected_prompts),
            )
        logger.warning(
            "question_generation_exhausted correlation_id=%s role=%s competency=%s "
            "history_count=%s anchor_count=%s attempts=%s",
            correlation_id,
            request.role_id,
            request.competency_id,
            len(request.recent_question_prompts),
            len(anchors),
            len(stages),
        )
        raise QuestionGenerationExhaustedError(len(stages), rejection_reasons)
