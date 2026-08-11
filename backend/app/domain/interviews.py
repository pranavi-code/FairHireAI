"""Deterministic competency-constrained adaptive interview selection."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from backend.app.domain.roles import CompetencyTemplate, RoleTemplate, load_role_template

FOLLOW_UP_THRESHOLD = {
    "competency_coverage": 0.70,
    "rubric_match": 0.60,
    "answer_completeness": 0.60,
    "evidence_confidence": 0.60,
}


class CompetencyProgress(BaseModel):
    competency_id: str
    core_answered: bool = False
    follow_up_used: bool = False
    competency_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    rubric_match: float = Field(default=0.0, ge=0.0, le=1.0)
    answer_completeness: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    high_confidence_resume_contradiction: bool = False
    weakest_criterion: str | None = Field(default=None, max_length=100)

    def needs_follow_up(self) -> bool:
        return (
            self.core_answered
            and not self.follow_up_used
            and (
                self.competency_coverage < FOLLOW_UP_THRESHOLD["competency_coverage"]
                or self.rubric_match < FOLLOW_UP_THRESHOLD["rubric_match"]
                or self.answer_completeness < FOLLOW_UP_THRESHOLD["answer_completeness"]
                or self.evidence_confidence < FOLLOW_UP_THRESHOLD["evidence_confidence"]
                or self.high_confidence_resume_contradiction
            )
        )


class NextQuestionRequest(BaseModel):
    attempt_id: UUID
    role_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    role_template_version: str
    competency_weights: dict[str, float]
    progress: list[CompetencyProgress] = Field(default_factory=list, max_length=6)
    current_competency_id: str | None = None
    answered_question_ids: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_weights(self) -> NextQuestionRequest:
        if abs(sum(self.competency_weights.values()) - 1.0) > 1e-6:
            raise ValueError("competency_weights must total 1.0")
        identifiers = [item.competency_id for item in self.progress]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Progress competency identifiers must be unique")
        return self


class NextQuestionResult(BaseModel):
    action: Literal["ask_question", "complete"]
    competency_id: str | None = None
    question_id: str | None = None
    prompt: str | None = None
    is_follow_up: bool = False
    reason: str
    selection_policy: Literal["bounded-adaptive-v1"] = "bounded-adaptive-v1"


def _follow_up_for(
    competency: CompetencyTemplate,
    progress: CompetencyProgress,
) -> NextQuestionResult:
    selected = next(
        (
            follow_up
            for follow_up in competency.follow_ups
            if progress.weakest_criterion
            and follow_up.trigger_criterion == progress.weakest_criterion
        ),
        competency.follow_ups[0],
    )
    return NextQuestionResult(
        action="ask_question",
        competency_id=competency.competency_id,
        question_id=selected.question_id,
        prompt=selected.prompt,
        is_follow_up=True,
        reason=(
            "A single approved follow-up is required because coverage, rubric "
            "match, completeness, confidence, or resume consistency is insufficient."
        ),
    )


def select_next_question(
    request: NextQuestionRequest,
    *,
    template: RoleTemplate | None = None,
) -> NextQuestionResult:
    role = template or load_role_template(request.role_id)
    if request.role_id != role.role_id:
        raise ValueError("The request role does not match the loaded role template")
    if request.role_template_version != role.template_version:
        raise ValueError("The attempt role-template version is unsupported")
    competency_ids = {item.competency_id for item in role.competencies}
    if set(request.competency_weights) != competency_ids:
        raise ValueError("competency_weights must contain exactly the role competencies")
    progress_by_id = {item.competency_id: item for item in request.progress}
    unknown = set(progress_by_id) - competency_ids
    if unknown:
        raise ValueError(f"Unknown progress competencies: {sorted(unknown)}")

    if request.current_competency_id:
        if request.current_competency_id not in competency_ids:
            raise ValueError("current_competency_id is not part of the role")
        current_progress = progress_by_id.get(request.current_competency_id)
        if current_progress and current_progress.needs_follow_up():
            current_competency = next(
                item
                for item in role.competencies
                if item.competency_id == request.current_competency_id
            )
            return _follow_up_for(current_competency, current_progress)

    unanswered = [
        competency
        for competency in role.competencies
        if not progress_by_id.get(
            competency.competency_id,
            CompetencyProgress(competency_id=competency.competency_id),
        ).core_answered
    ]
    if unanswered:
        selected = max(
            unanswered,
            key=lambda item: (
                request.competency_weights[item.competency_id],
                -role.competencies.index(item),
            ),
        )
        return NextQuestionResult(
            action="ask_question",
            competency_id=selected.competency_id,
            question_id=selected.core_question.question_id,
            prompt=selected.core_question.prompt,
            is_follow_up=False,
            reason="Selected the highest-weight competency without a core answer.",
        )

    pending_follow_ups = [
        (
            competency,
            progress_by_id[competency.competency_id],
        )
        for competency in role.competencies
        if competency.competency_id in progress_by_id
        and progress_by_id[competency.competency_id].needs_follow_up()
    ]
    if pending_follow_ups:
        competency, progress = max(
            pending_follow_ups,
            key=lambda pair: (
                request.competency_weights[pair[0].competency_id]
                * (1.0 - pair[1].competency_coverage)
            ),
        )
        return _follow_up_for(competency, progress)

    return NextQuestionResult(
        action="complete",
        reason=("Every competency has a core answer and no unused approved follow-up is required."),
    )
