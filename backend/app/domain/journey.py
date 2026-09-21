"""Persistent student-journey request and response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from backend.app.domain.resume import ResumeEvidence


class ResumeAttachmentRequest(BaseModel):
    private_resume_storage_key: str = Field(min_length=3, max_length=1_000)
    mime_type: str = Field(min_length=3, max_length=200)
    evidence: ResumeEvidence


class ResumeAttachmentResult(BaseModel):
    resume_document_id: UUID
    attempt_id: UUID
    claim_count: int = Field(ge=0, le=300)
    extraction_status: Literal["complete"]


class PersistedQuestion(BaseModel):
    id: UUID
    attempt_id: UUID
    question_template_id: str
    competency_id: str
    prompt_snapshot: str
    is_follow_up: bool
    sequence_number: int = Field(ge=1, le=12)
    selection_reason: str
    question_package_id: str | None = None
    question_package_version: str | None = None
    expected_concepts_snapshot: list[str] = Field(default_factory=list)
    rubric_snapshot: dict[str, str] = Field(default_factory=dict)
    source_mapping_snapshot: dict[str, list[str]] = Field(default_factory=dict)
    model_id: str | None = None
    prompt_version: str | None = None
    created_at: datetime


class NextPersistedQuestion(BaseModel):
    question: PersistedQuestion | None = None
    awaiting_answer: bool
    message: str


class AnswerSubmissionRequest(BaseModel):
    question_id: UUID
    private_video_storage_key: str = Field(min_length=3, max_length=1_000)
    video_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    duration_seconds: float = Field(ge=5.0, le=600.0)


class AnswerRecord(BaseModel):
    id: UUID
    attempt_id: UUID
    question_id: UUID
    private_video_storage_key: str
    video_sha256: str
    duration_seconds: float
    processing_status: Literal["pending", "queued", "running", "complete", "failed"]
    submitted_at: datetime
    processed_at: datetime | None = None


class ProcessingJobView(BaseModel):
    id: UUID
    attempt_id: UUID
    answer_id: UUID | None = None
    job_type: str
    status: str
    stage: str | None = None
    attempt_count: int
    max_attempts: int
    error_code: str | None = None
    error_detail: str | None = None
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime


class ProcessingStartResult(BaseModel):
    attempt_id: UUID
    started: Literal[True] = True
    queued_job_count: int = Field(ge=0)
    message: str


class ReportCompetencyScore(BaseModel):
    competency_id: str
    name: str
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    sufficient_evidence: bool = False
    weight: float = Field(ge=0.0, le=1.0)
    evidence_node_ids: list[str] = Field(default_factory=list)
    insufficiency_reasons: list[str] = Field(default_factory=list)


class ScorecardView(BaseModel):
    placement_readiness: float | None = Field(default=None, ge=0.0, le=1.0)
    insufficiency_reasons: list[str] = Field(default_factory=list)
    base_multimodal_interview_signal: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    delivery_signal: dict[str, object] | None = None
    competencies: list[ReportCompetencyScore] = Field(default_factory=list)


class SkillGapEvidenceView(BaseModel):
    current_score: float | None = Field(default=None, ge=0.0, le=1.0)
    target_score: float | None = Field(default=None, ge=0.0, le=1.0)
    severity: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str | None = None


class EvidenceNodeView(BaseModel):
    id: str
    kind: str
    label: str | None = None
    competency_id: str | None = None
    transcript_span: dict[str, object] | None = None
    question: dict[str, object] | None = None
    resume_claim_id: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    signal_quality: str | None = None
    model_reference: str | None = None
    criterion_evidence: list[dict[str, object]] = Field(default_factory=list)
    missing_concepts: list[str] = Field(default_factory=list)
    skill_gap: SkillGapEvidenceView | None = None


class EvidenceEdgeView(BaseModel):
    id: str
    from_node_id: str = Field(serialization_alias="from")
    to_node_id: str = Field(serialization_alias="to")
    relation: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class RoadmapResourceView(BaseModel):
    id: str
    title: str
    url: str
    provider: str | None = None


class RoadmapItemView(BaseModel):
    id: str
    competency_id: str | None = None
    title: str
    description: str | None = None
    reviewer_approved: Literal[True] = True
    resources: list[RoadmapResourceView] = Field(default_factory=list)


class AttemptReport(BaseModel):
    attempt_id: UUID
    status: str
    scorecard: ScorecardView | None = None
    evidence_nodes: list[EvidenceNodeView] = Field(default_factory=list)
    evidence_edges: list[EvidenceEdgeView] = Field(default_factory=list)
    roadmap_items: list[RoadmapItemView] = Field(default_factory=list)
    message: str


class ProgressAttempt(BaseModel):
    attempt_id: UUID
    role_id: str
    completed_at: datetime
    placement_readiness: float | None
    sufficient_evidence: bool = False
    overall_evidence_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    insufficiency_reasons: list[str] = Field(default_factory=list)
    competency_scores: list[ReportCompetencyScore]


class ProgressView(BaseModel):
    attempts: list[ProgressAttempt]
    message: str


class ModelUnavailableDetail(BaseModel):
    code: Literal["trained_checkpoint_required"] = "trained_checkpoint_required"
    message: str
    training_or_preprocessing_running: bool = True

    @model_validator(mode="after")
    def validate_message(self) -> ModelUnavailableDetail:
        if "checkpoint" not in self.message.casefold():
            raise ValueError("Model-unavailable messages must mention the checkpoint")
        return self
