from types import MethodType

import pytest

from backend.app.workers.runtime import FairHireWorker


class QueueRepository:
    def __init__(self, *, job=None, deletion=None) -> None:  # type: ignore[no-untyped-def]
        self.job = job
        self.deletion = deletion
        self.completed: list[dict[str, object]] = []
        self.failed: list[tuple[str, str]] = []
        self.deleted: list[tuple[str, str]] = []

    def claim_processing_job(self, _worker_id: str):  # type: ignore[no-untyped-def]
        job, self.job = self.job, None
        return job

    def claim_deletion_request(self, _worker_id: str):  # type: ignore[no-untyped-def]
        deletion, self.deletion = self.deletion, None
        return deletion

    def deletion_storage_keys(self, _request):  # type: ignore[no-untyped-def]
        return [("private", "owner/object.mp4")]

    def delete_object(self, bucket: str, storage_key: str) -> None:
        self.deleted.append((bucket, storage_key))

    def complete_deletion(self, request: dict[str, object]) -> None:
        self.completed.append(request)

    def fail_deletion(self, request_id: str, error: str) -> None:
        self.failed.append((request_id, error))


def worker_with(repository: QueueRepository) -> FairHireWorker:
    worker = object.__new__(FairHireWorker)
    worker.repository = repository  # type: ignore[assignment]
    worker.worker_id = "test-worker"
    return worker


def test_run_once_prioritizes_processing_jobs_over_deletions() -> None:
    repository = QueueRepository(job={"id": "job-1"}, deletion={"id": "delete-1"})
    worker = worker_with(repository)
    processed: list[dict[str, str]] = []
    worker._process_job = MethodType(lambda _self, job: processed.append(job), worker)  # type: ignore[method-assign]

    assert worker.run_once() is True
    assert processed == [{"id": "job-1"}]
    assert repository.deletion == {"id": "delete-1"}


def test_run_once_handles_deletion_and_then_reports_idle() -> None:
    request = {"id": "delete-1"}
    repository = QueueRepository(deletion=request)
    worker = worker_with(repository)

    assert worker.run_once() is True
    assert repository.deleted == [("private", "owner/object.mp4")]
    assert repository.completed == [request]
    assert worker.run_once() is False


def test_deletion_failure_is_persisted_before_being_raised() -> None:
    class FailingRepository(QueueRepository):
        def delete_object(self, bucket: str, storage_key: str) -> None:
            raise TimeoutError(f"timeout deleting {bucket}/{storage_key}")

    request = {"id": "delete-1"}
    repository = FailingRepository()
    worker = worker_with(repository)

    with pytest.raises(TimeoutError):
        worker._process_deletion(request)

    assert repository.failed == [("delete-1", "TimeoutError")]
    assert repository.completed == []
