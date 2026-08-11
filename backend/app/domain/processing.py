"""Durable job transitions and real-model inference artifact contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

JobType = Literal[
    "resume_extraction",
    "answer_preprocessing",
    "base_model_inference",
    "graph_update",
    "report_generation",
]
JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "cancelled"},
    "running": {"succeeded", "failed", "cancelled"},
    "failed": {"queued"},
    "succeeded": set(),
    "cancelled": set(),
}


class ProcessingJob(BaseModel):
    job_id: UUID
    attempt_id: UUID
    answer_id: UUID | None = None
    job_type: JobType
    status: JobStatus = "queued"
    stage: str | None = Field(default=None, max_length=100)
    idempotency_key: str = Field(min_length=8, max_length=200)
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1, le=10)
    error_code: str | None = Field(default=None, max_length=100)
    error_detail: str | None = Field(default=None, max_length=4_000)
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @model_validator(mode="after")
    def validate_job(self) -> ProcessingJob:
        if self.queued_at.tzinfo is None:
            raise ValueError("queued_at must include a timezone")
        if self.job_type in {"answer_preprocessing", "base_model_inference"}:
            if self.answer_id is None:
                raise ValueError(f"{self.job_type} requires answer_id")
        if self.status == "failed" and not self.error_code:
            raise ValueError("Failed jobs require error_code")
        if self.status == "succeeded" and self.error_code:
            raise ValueError("Succeeded jobs cannot retain an error")
        return self


class JobTransition(BaseModel):
    next_status: JobStatus
    occurred_at: datetime
    stage: str | None = Field(default=None, max_length=100)
    error_code: str | None = Field(default=None, max_length=100)
    error_detail: str | None = Field(default=None, max_length=4_000)

    @model_validator(mode="after")
    def validate_transition(self) -> JobTransition:
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        if self.next_status == "failed" and not self.error_code:
            raise ValueError("Failed transitions require error_code")
        if self.next_status != "failed" and (
            self.error_code is not None or self.error_detail is not None
        ):
            raise ValueError("Only failed transitions can contain error details")
        return self


def transition_job(job: ProcessingJob, transition: JobTransition) -> ProcessingJob:
    if transition.next_status not in ALLOWED_TRANSITIONS[job.status]:
        raise ValueError(f"Invalid job transition: {job.status} -> {transition.next_status}")
    if job.status == "failed" and transition.next_status == "queued":
        if job.attempt_count >= job.max_attempts:
            raise ValueError("Job retry limit has been reached")
    update: dict[str, object] = {
        "status": transition.next_status,
        "stage": transition.stage,
        "error_code": transition.error_code,
        "error_detail": transition.error_detail,
    }
    if transition.next_status == "running":
        if job.attempt_count >= job.max_attempts:
            raise ValueError("Job retry limit has been reached")
        update["attempt_count"] = job.attempt_count + 1
        update["started_at"] = transition.occurred_at
        update["finished_at"] = None
    if transition.next_status in {"succeeded", "failed", "cancelled"}:
        update["finished_at"] = transition.occurred_at
    if transition.next_status == "queued":
        update["queued_at"] = transition.occurred_at
        update["started_at"] = None
        update["finished_at"] = None
    return job.model_copy(update=update)


class AlignedArtifactReference(BaseModel):
    schema_version: Literal["fi-word-alignment-v1"]
    private_storage_key: str = Field(min_length=3, max_length=1_000)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    words: int = Field(gt=0, le=176)
    acoustic_dimensions: Literal[88] = 88
    visual_dimensions: Literal[709] = 709


class BaseModelInferenceRequest(BaseModel):
    attempt_id: UUID
    answer_id: UUID
    artifact: AlignedArtifactReference
    model_run_name: str = Field(min_length=3, max_length=200)
    checkpoint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class BaseModelInferenceResult(BaseModel):
    schema_version: Literal["base-interview-signal-v1"] = "base-interview-signal-v1"
    attempt_id: UUID
    answer_id: UUID
    base_multimodal_interview_signal: float = Field(ge=0.0, le=1.0)
    model_run_name: str
    checkpoint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    signal_quality: float = Field(ge=0.0, le=1.0)
    generated_at: datetime
    prediction_node_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9:_-]{2,119}$")

    @model_validator(mode="after")
    def validate_timestamp(self) -> BaseModelInferenceResult:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must include a timezone")
        return self
