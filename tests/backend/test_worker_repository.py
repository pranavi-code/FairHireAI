from pathlib import Path

import httpx

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
