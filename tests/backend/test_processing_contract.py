from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.domain.processing import (
    JobTransition,
    ProcessingJob,
    transition_job,
)


def queued_job() -> ProcessingJob:
    return ProcessingJob(
        job_id=uuid4(),
        attempt_id=uuid4(),
        answer_id=uuid4(),
        job_type="answer_preprocessing",
        idempotency_key="answer:preprocess:fixed-key",
        queued_at=datetime.now(timezone.utc),
    )


def test_job_state_machine_supports_retry_without_duplicate_execution() -> None:
    job = queued_job()
    started = transition_job(
        job,
        JobTransition(
            next_status="running",
            occurred_at=job.queued_at + timedelta(seconds=1),
            stage="normalizing_media",
        ),
    )
    assert started.attempt_count == 1
    failed = transition_job(
        started,
        JobTransition(
            next_status="failed",
            occurred_at=job.queued_at + timedelta(seconds=2),
            stage="normalizing_media",
            error_code="FFMPEG_FAILED",
            error_detail="ffmpeg returned a non-zero code",
        ),
    )
    retried = transition_job(
        failed,
        JobTransition(
            next_status="queued",
            occurred_at=job.queued_at + timedelta(seconds=3),
        ),
    )
    assert retried.status == "queued"
    assert retried.error_code is None
    assert retried.idempotency_key == job.idempotency_key


def test_terminal_jobs_and_invalid_transitions_are_rejected() -> None:
    job = queued_job()
    with pytest.raises(ValueError, match="Invalid job transition"):
        transition_job(
            job,
            JobTransition(
                next_status="succeeded",
                occurred_at=datetime.now(timezone.utc),
            ),
        )
    with pytest.raises(ValidationError, match="requires answer_id"):
        ProcessingJob(
            job_id=uuid4(),
            attempt_id=uuid4(),
            job_type="base_model_inference",
            idempotency_key="model:missing-answer",
            queued_at=datetime.now(timezone.utc),
        )
