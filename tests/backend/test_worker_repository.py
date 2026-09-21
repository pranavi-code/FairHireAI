from pathlib import Path
from uuid import uuid4

import httpx

from backend.app.domain.knowledge import ResourceSearchRequest
from backend.app.repositories.worker import SupabaseWorkerRepository


def test_worker_daemon_keeps_polling_after_a_persisted_job_failure() -> None:
    runtime = __import__("backend.app.workers.runtime", fromlist=["run_worker"])
    source = Path(runtime.__file__).read_text(encoding="utf-8")
    assert "except Exception:" in source
    assert "if once:" in source
    assert "traceback.print_exc()" in source
    assert "continue" in source


def test_storage_delete_does_not_send_an_empty_json_body_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/storage/v1/object/private/user/file.mp4"
        assert "content-type" not in request.headers
        assert request.content == b""
        return httpx.Response(204)

    repository = SupabaseWorkerRepository(
        base_url="https://example.supabase.co",
        secret_key="sb_secret_test_only_not_a_real_secret",
        transport=httpx.MockTransport(handler),
    )
    try:
        repository.delete_object("private", "user/file.mp4")
    finally:
        repository.close()


def test_private_video_download_retries_a_transient_read_timeout(tmp_path: Path) -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        assert request.url.path == "/storage/v1/object/private/user/answer.webm"
        if requests == 1:
            raise httpx.ReadTimeout("temporary storage timeout", request=request)
        return httpx.Response(200, content=b"real-video-bytes")

    repository = SupabaseWorkerRepository(
        base_url="https://example.supabase.co",
        secret_key="sb_secret_test_only_not_a_real_secret",
        transport=httpx.MockTransport(handler),
    )
    destination = tmp_path / "answer.webm"
    try:
        repository.download_object("private", "user/answer.webm", destination)
    finally:
        repository.close()

    assert requests == 2
    assert destination.read_bytes() == b"real-video-bytes"


def test_worker_calls_the_hybrid_resource_rpc_with_a_query_embedding() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/rest/v1/rpc/match_learning_resources"
        payload = __import__("json").loads(request.read())
        assert payload["p_competency_id"] == "api_design"
        assert len(payload["p_query_embedding"]) == 384
        return httpx.Response(
            200,
            json=[
                {
                    "id": "RES-API",
                    "title": "API guide",
                    "canonical_url": "https://example.org/api",
                    "source_organization": "Example",
                    "competency_ids": ["api_design"],
                    "difficulty": "beginner",
                    "estimated_minutes": 30,
                    "description": "A reviewed API design learning resource.",
                    "resource_type": "official_documentation",
                    "learning_outcomes": ["Design an API"],
                    "keyword_rank": 0.4,
                    "semantic_similarity": 0.8,
                    "hybrid_score": 0.58,
                }
            ],
        )

    repository = SupabaseWorkerRepository(
        base_url="https://example.supabase.co",
        secret_key="sb_secret_test_only_not_a_real_secret",
        transport=httpx.MockTransport(handler),
    )
    try:
        result = repository.search_learning_resources(
            ResourceSearchRequest(
                query="API design",
                competency_id="api_design",
                query_embedding=[0.01] * 384,
            )
        )
    finally:
        repository.close()

    assert [item.id for item in result] == ["RES-API"]


def test_manual_completion_queues_report_after_six_evaluated_answers() -> None:
    attempt_id = str(uuid4())
    answer_ids = [str(uuid4()) for _ in range(6)]
    inserted: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/rest/v1/attempts":
            return httpx.Response(
                200,
                json=[{"id": attempt_id, "status": "interviewing"}],
            )
        if request.method == "GET" and request.url.path == "/rest/v1/answers":
            return httpx.Response(
                200,
                json=[
                    {"id": answer_id, "processing_status": "complete"}
                    for answer_id in answer_ids
                ],
            )
        if request.method == "GET" and request.url.path == "/rest/v1/answer_analyses":
            return httpx.Response(
                200,
                json=[{"answer_id": answer_id} for answer_id in answer_ids],
            )
        if request.method == "GET" and request.url.path == "/rest/v1/processing_jobs":
            return httpx.Response(200, json=[])
        if request.method == "POST" and request.url.path == "/rest/v1/processing_jobs":
            payload = __import__("json").loads(request.read())
            inserted.update(payload)
            return httpx.Response(201, json=[{"id": str(uuid4()), **payload}])
        if request.method == "PATCH" and request.url.path == "/rest/v1/attempts":
            assert __import__("json").loads(request.read()) == {"status": "processing"}
            return httpx.Response(204)
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    repository = SupabaseWorkerRepository(
        base_url="https://example.supabase.co",
        secret_key="sb_secret_test_only_not_a_real_secret",
        transport=httpx.MockTransport(handler),
    )
    try:
        result = repository.request_report_generation(attempt_id)
    finally:
        repository.close()

    assert result["queued_job_count"] == 1
    assert inserted["job_type"] == "report_generation"
    assert inserted["answer_id"] is None


def test_manual_completion_rejects_fewer_than_six_evaluated_answers() -> None:
    attempt_id = str(uuid4())
    answer_ids = [str(uuid4()) for _ in range(5)]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/rest/v1/attempts":
            return httpx.Response(200, json=[{"id": attempt_id, "status": "interviewing"}])
        if request.url.path == "/rest/v1/answers":
            return httpx.Response(
                200,
                json=[
                    {"id": answer_id, "processing_status": "complete"}
                    for answer_id in answer_ids
                ],
            )
        if request.url.path == "/rest/v1/answer_analyses":
            return httpx.Response(
                200,
                json=[{"answer_id": answer_id} for answer_id in answer_ids],
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    repository = SupabaseWorkerRepository(
        base_url="https://example.supabase.co",
        secret_key="sb_secret_test_only_not_a_real_secret",
        transport=httpx.MockTransport(handler),
    )
    try:
        try:
            repository.request_report_generation(attempt_id)
        except RuntimeError as exc:
            assert "At least 6 evaluated answers" in str(exc)
        else:
            raise AssertionError("Expected the six-answer server-side guard to reject")
    finally:
        repository.close()


def test_concurrent_manual_completion_converges_on_one_report_job() -> None:
    attempt_id = str(uuid4())
    answer_ids = [str(uuid4()) for _ in range(6)]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/rest/v1/attempts":
            return httpx.Response(200, json=[{"id": attempt_id, "status": "interviewing"}])
        if request.method == "GET" and request.url.path == "/rest/v1/answers":
            return httpx.Response(
                200,
                json=[
                    {"id": answer_id, "processing_status": "complete"}
                    for answer_id in answer_ids
                ],
            )
        if request.method == "GET" and request.url.path == "/rest/v1/answer_analyses":
            return httpx.Response(
                200,
                json=[{"answer_id": answer_id} for answer_id in answer_ids],
            )
        if request.method == "GET" and request.url.path == "/rest/v1/processing_jobs":
            return httpx.Response(200, json=[])
        if request.method == "POST" and request.url.path == "/rest/v1/processing_jobs":
            assert request.url.params["on_conflict"] == "idempotency_key"
            assert request.headers["prefer"] == (
                "resolution=ignore-duplicates,return=representation"
            )
            # Simulate another request winning the unique-key race.
            return httpx.Response(201, json=[])
        if request.method == "PATCH" and request.url.path == "/rest/v1/attempts":
            return httpx.Response(204)
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    repository = SupabaseWorkerRepository(
        base_url="https://example.supabase.co",
        secret_key="sb_secret_test_only_not_a_real_secret",
        transport=httpx.MockTransport(handler),
    )
    try:
        result = repository.request_report_generation(attempt_id)
    finally:
        repository.close()

    assert result["started"] is True
    assert result["queued_job_count"] == 0
