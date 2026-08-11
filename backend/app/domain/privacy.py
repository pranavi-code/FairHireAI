"""Explicit consent history and data-deletion request contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

ConsentType = Literal[
    "privacy_notice",
    "resume_processing",
    "interview_recording",
    "external_ai_processing",
    "research_evaluation",
]


class ConsentRequest(BaseModel):
    attempt_id: UUID | None = None
    consent_type: ConsentType
    policy_version: str = Field(min_length=1, max_length=100)
    granted: bool
    source: Literal["web", "mobile"] = "web"
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ConsentRecord(ConsentRequest):
    id: UUID
    user_id: UUID
    occurred_at: datetime

    @model_validator(mode="after")
    def validate_timestamp(self) -> ConsentRecord:
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        return self


class DeletionRequestCreate(BaseModel):
    scope: Literal["attempt", "account"]
    attempt_id: UUID | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> DeletionRequestCreate:
        if self.scope == "attempt" and self.attempt_id is None:
            raise ValueError("Attempt-scoped deletion requires attempt_id")
        if self.scope == "account" and self.attempt_id is not None:
            raise ValueError("Account-scoped deletion cannot contain attempt_id")
        return self


class DeletionRequestRecord(DeletionRequestCreate):
    id: UUID
    user_id: UUID
    status: Literal["requested", "processing", "completed", "failed"]
    requested_at: datetime
    completed_at: datetime | None = None
    error_code: str | None = None

    @model_validator(mode="after")
    def validate_record(self) -> DeletionRequestRecord:
        if self.requested_at.tzinfo is None:
            raise ValueError("requested_at must include a timezone")
        if self.status == "completed" and self.completed_at is None:
            raise ValueError("Completed deletion requests require completed_at")
        return self
