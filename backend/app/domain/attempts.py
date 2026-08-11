"""Attempt lifecycle contracts shared by the API and persistence adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from backend.app.domain.roles import AssessmentProfile

AttemptStatus = Literal[
    "draft",
    "role_confirmed",
    "interviewing",
    "processing",
    "completed",
    "failed",
    "cancelled",
]

ATTEMPT_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"role_confirmed", "cancelled"},
    "role_confirmed": {"interviewing", "cancelled"},
    "interviewing": {"processing", "failed", "cancelled"},
    "processing": {"completed", "failed", "cancelled"},
    "failed": {"processing", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


class AttemptRecord(BaseModel):
    id: UUID
    user_id: UUID
    parent_attempt_id: UUID | None = None
    role_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    role_template_version: str
    assessment_profile_source: Literal["approved_role", "job_description"]
    assessment_profile_version: str
    status: AttemptStatus
    competency_weights: dict[str, float]
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_record(self) -> AttemptRecord:
        if abs(sum(self.competency_weights.values()) - 1.0) > 1e-6:
            raise ValueError("Attempt competency weights must total 1.0")
        for timestamp in (
            self.started_at,
            self.completed_at,
            self.created_at,
            self.updated_at,
        ):
            if timestamp is not None and timestamp.tzinfo is None:
                raise ValueError("Attempt timestamps must include a timezone")
        if self.status == "completed" and self.completed_at is None:
            raise ValueError("Completed attempts require completed_at")
        expected_profile_version = (
            "approved-role-selection-v2"
            if self.assessment_profile_source == "approved_role"
            else "optional-jd-mapper-v2"
        )
        if self.assessment_profile_version != expected_profile_version:
            raise ValueError("Attempt assessment-profile source and version do not match")
        return self


class AttemptTransitionRequest(BaseModel):
    next_status: AttemptStatus


class JobDescriptionSubmission(BaseModel):
    private_jd_storage_key: str = Field(min_length=3, max_length=1_000)
    jd_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    extracted_job_description: str = Field(min_length=40, max_length=50_000)


class AttemptCreationRequest(BaseModel):
    parent_attempt_id: UUID | None = None
    role_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    confirm_role: Literal[True]
    job_description: JobDescriptionSubmission | None = None


class PreparedAttemptCreation(BaseModel):
    request: AttemptCreationRequest
    assessment_profile: AssessmentProfile


def validate_attempt_transition(current: AttemptStatus, requested: AttemptStatus) -> None:
    if requested not in ATTEMPT_TRANSITIONS[current]:
        raise ValueError(f"Invalid attempt transition: {current} -> {requested}")
