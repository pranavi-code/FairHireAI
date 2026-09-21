"""Curated, review-gated gap-to-resource roadmap selection."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

from backend.app.domain.roles import load_role_template


class SkillGap(BaseModel):
    skill_gap_node_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9:_-]{2,119}$")
    competency_id: str
    current_score: float = Field(ge=0.0, le=1.0)
    target_score: float = Field(ge=0.0, le=1.0)
    severity: float = Field(ge=0.0, le=1.0)
    evidence_node_ids: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_gap(self) -> SkillGap:
        if self.target_score <= self.current_score:
            raise ValueError("A skill gap target must exceed the current score")
        return self


class LearningResource(BaseModel):
    resource_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9:_-]{2,119}$")
    title: str = Field(min_length=3, max_length=300)
    canonical_url: HttpUrl
    source_organization: str = Field(min_length=2, max_length=200)
    competency_ids: list[str] = Field(min_length=1, max_length=6)
    difficulty: Literal["beginner", "intermediate"]
    estimated_minutes: int = Field(gt=0, le=10_000)
    description: str = Field(min_length=10, max_length=2_000)
    reviewer_status: Literal["pending", "approved", "retired"]
    reviewer_id: str | None = Field(default=None, max_length=120)
    retrieval_scores: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_review(self) -> LearningResource:
        if self.reviewer_status == "approved" and not self.reviewer_id:
            raise ValueError("Approved resources require reviewer_id")
        return self


class RoadmapRequest(BaseModel):
    role_id: str = Field(
        default="junior_backend_developer",
        pattern=r"^[a-z][a-z0-9_]{2,79}$",
    )
    gaps: list[SkillGap] = Field(min_length=1, max_length=6)
    resources: list[LearningResource] = Field(max_length=1_000)
    maximum_resources_per_gap: int = Field(default=2, ge=1, le=3)


class RoadmapItem(BaseModel):
    skill_gap_node_id: str
    competency_id: str
    resource_id: str
    priority: int = Field(ge=1)
    rationale: str


class RoadmapResult(BaseModel):
    policy_version: Literal[
        "curated-roadmap-v1",
        "grounded-dynamic-roadmap-gemini-v1",
    ] = "curated-roadmap-v1"
    items: list[RoadmapItem]
    unresolved_skill_gap_node_ids: list[str]
    safety_note: str


def build_roadmap(request: RoadmapRequest) -> RoadmapResult:
    role = load_role_template(request.role_id)
    competency_ids = {item.competency_id for item in role.competencies}
    unknown_gaps = {gap.competency_id for gap in request.gaps} - competency_ids
    if unknown_gaps:
        raise ValueError(f"Unknown gap competencies: {sorted(unknown_gaps)}")
    approved = [
        resource
        for resource in request.resources
        if resource.reviewer_status == "approved"
        # The reviewed knowledge base is shared by every supported role. Ignore
        # resources that do not target this attempt's role instead of treating
        # their valid cross-role competency tags as corrupt input.
        and set(resource.competency_ids) & competency_ids
    ]
    used_resources: set[str] = set()
    items: list[RoadmapItem] = []
    unresolved: list[str] = []
    ordered_gaps = sorted(
        request.gaps,
        key=lambda gap: (-gap.severity, gap.competency_id),
    )
    for priority, gap in enumerate(ordered_gaps, start=1):
        candidates = [
            resource
            for resource in approved
            if gap.competency_id in resource.competency_ids
            and resource.resource_id not in used_resources
        ]
        candidates.sort(
            key=lambda resource: (
                -resource.retrieval_scores.get(gap.competency_id, 0.0),
                0 if resource.difficulty == "beginner" else 1,
                resource.estimated_minutes,
                resource.resource_id,
            )
        )
        selected = candidates[: request.maximum_resources_per_gap]
        if not selected:
            unresolved.append(gap.skill_gap_node_id)
            continue
        for resource in selected:
            used_resources.add(resource.resource_id)
            items.append(
                RoadmapItem(
                    skill_gap_node_id=gap.skill_gap_node_id,
                    competency_id=gap.competency_id,
                    resource_id=resource.resource_id,
                    priority=priority,
                    rationale=(
                        f"Hybrid RAG retrieved this approved resource for the "
                        f"{gap.competency_id} gap "
                        f"(current {gap.current_score:.2f}, target "
                        f"{gap.target_score:.2f})."
                    ),
                )
            )
    return RoadmapResult(
        items=items,
        unresolved_skill_gap_node_ids=unresolved,
        safety_note=(
            "Only reviewer-approved curated resources are selected. Missing "
            "coverage is reported instead of generating an unverified recommendation."
        ),
    )
