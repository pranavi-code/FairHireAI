from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from backend.app.api.v1.journey import (
    attach_resume,
    finish_interview,
    start_processing,
    submit_answer,
)
from backend.app.config import Settings
from backend.app.domain.journey import (
    AnswerSubmissionRequest,
    ProcessingStartResult,
    ResumeAttachmentRequest,
)
from backend.app.domain.resume import ResumeEvidence


class ConsentRepository:
    def __init__(self, user_id: UUID, granted: set[str]) -> None:
        self.user_id = user_id
        self.granted = granted
        self.closed = False

    def authenticated_user_id(self) -> UUID:
        return self.user_id

    def consent_granted(self, consent_type: str, _attempt_id: UUID) -> bool:
        return consent_type in self.granted

    def external_ai_consent(self, _attempt_id: UUID) -> bool:
        return "external_ai_processing" in self.granted

    def get(self, _attempt_id: UUID) -> object:
        return object()

    def request_report_generation(self, attempt_id: UUID) -> ProcessingStartResult:
        return ProcessingStartResult(
            attempt_id=attempt_id,
            queued_job_count=1,
            message="Evidence-backed report generation queued.",
        )

    def close(self) -> None:
        self.closed = True


def empty_resume_request(user_id: UUID) -> ResumeAttachmentRequest:
    return ResumeAttachmentRequest(
        private_resume_storage_key=f"{user_id}/attempt/resume.txt",
        mime_type="text/plain",
        evidence=ResumeEvidence(
            document_sha256="a" * 64,
            extractor_name="test",
            extractor_version="1.0.0",
            claims=[],
        ),
    )


def test_resume_attachment_rechecks_latest_consent_server_side() -> None:
    user_id = uuid4()
    repository = ConsentRepository(user_id, granted=set())

    with pytest.raises(HTTPException) as raised:
        attach_resume(uuid4(), empty_resume_request(user_id), repository)  # type: ignore[arg-type]

    assert raised.value.status_code == 403
    assert raised.value.detail["code"] == "resume_processing_consent_required"
    assert repository.closed


def test_video_submission_rechecks_latest_recording_consent_server_side() -> None:
    user_id = uuid4()
    repository = ConsentRepository(user_id, granted={"resume_processing"})
    request = AnswerSubmissionRequest(
        question_id=uuid4(),
        private_video_storage_key=f"{user_id}/attempt/answer.webm",
        video_sha256="b" * 64,
        duration_seconds=30,
    )

    with pytest.raises(HTTPException) as raised:
        submit_answer(uuid4(), request, repository)  # type: ignore[arg-type]

    assert raised.value.status_code == 403
    assert raised.value.detail["code"] == "interview_recording_consent_required"
    assert repository.closed


def test_processing_rechecks_external_ai_consent_before_queueing(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    repository = ConsentRepository(uuid4(), granted=set())
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="publishable-test-key",
        trusted_worker_available=True,
    )
    monkeypatch.setattr("backend.app.api.v1.journey.get_settings", lambda: settings)

    with pytest.raises(HTTPException) as raised:
        start_processing(uuid4(), repository)  # type: ignore[arg-type]

    assert raised.value.status_code == 403
    assert raised.value.detail["code"] == "external_ai_processing_consent_required"
    assert repository.closed


def test_early_finish_rechecks_external_ai_consent_before_report_queue(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    repository = ConsentRepository(uuid4(), granted=set())
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="publishable-test-key",
        supabase_secret_key="sb_secret_test_only_not_a_real_secret",
        gemini_api_key="test-gemini-key",
        trusted_worker_available=True,
    )
    monkeypatch.setattr("backend.app.api.v1.journey.get_settings", lambda: settings)

    with pytest.raises(HTTPException) as raised:
        finish_interview(uuid4(), repository)  # type: ignore[arg-type]

    assert raised.value.status_code == 403
    assert raised.value.detail["code"] == "external_ai_processing_consent_required"
    assert repository.closed


def test_early_finish_uses_authenticated_report_rpc_without_server_secret(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    attempt_id = uuid4()
    repository = ConsentRepository(
        uuid4(),
        granted={"external_ai_processing"},
    )
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="publishable-test-key",
        trusted_worker_available=True,
    )
    monkeypatch.setattr("backend.app.api.v1.journey.get_settings", lambda: settings)

    result = finish_interview(attempt_id, repository)  # type: ignore[arg-type]

    assert result.attempt_id == attempt_id
    assert result.queued_job_count == 1
    assert repository.closed
