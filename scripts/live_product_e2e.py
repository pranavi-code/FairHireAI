"""Guarded live end-to-end smoke test for the complete FairHireAI product.

This script creates a disposable confirmed Supabase user, runs the real local
API and trusted worker against a public FI fixture, verifies the report and
roadmap, then requests account deletion and confirms cleanup. It never uses or
mutates the signed-in human account.
"""

from __future__ import annotations

import argparse
import hashlib
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from backend.app.config import get_settings

PROJECT_REF = "gfsetwljirztyxegiets"
DOCUMENT_BUCKET = "roleready-documents"
VIDEO_BUCKET = "roleready-interview-video"
ROLE_ID = "junior_backend_developer"
POLICY_VERSION = "v1"
REQUIRED_CONSENTS = (
    "privacy_notice",
    "resume_processing",
    "interview_recording",
    "external_ai_processing",
)
RETRYABLE_READ_STATUS_CODES = {500, 502, 503, 504}
SYNTHETIC_RESUME = b"""FairHireAI Live Integration Candidate

Summary
Junior backend developer with project experience building Python and FastAPI APIs.

Skills
Python, FastAPI, REST APIs, SQL, PostgreSQL, Git, pytest, Docker, authentication,
input validation, exception handling, database indexing, and API documentation.

Projects
Built a placement-readiness API with authenticated endpoints, PostgreSQL storage,
automated tests, structured logging, and documented privacy controls.
"""


def _json(response: httpx.Response, label: str) -> Any:
    if response.is_error:
        body = response.text.replace("\n", " ")[:1_000]
        raise RuntimeError(f"{label} failed with HTTP {response.status_code}: {body}")
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"{label} returned non-JSON data") from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_with_retries(
    client: httpx.Client,
    path: str,
    *,
    attempts: int = 5,
) -> httpx.Response:
    """Retry idempotent live-test reads across brief DNS/TLS interruptions."""

    last_error: httpx.TransportError | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = client.get(path)
        except httpx.TransportError as exc:
            last_error = exc
        else:
            last_error = None
            if response.status_code not in RETRYABLE_READ_STATUS_CODES:
                return response
        if attempt < attempts:
            time.sleep(float(attempt))
    if last_error is not None:
        raise last_error
    return response


def _upload(
    client: httpx.Client,
    *,
    bucket: str,
    path: str,
    content: bytes,
    content_type: str,
) -> None:
    encoded_path = quote(path, safe="/")
    response = client.post(
        f"/storage/v1/object/{bucket}/{encoded_path}",
        headers={"Content-Type": content_type, "x-upsert": "false"},
        content=content,
    )
    _json(response, f"Upload to {bucket}")


def _wait_for_answer_job(
    api: httpx.Client,
    *,
    attempt_id: str,
    answer_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_stage = "waiting_for_worker"
    while time.monotonic() < deadline:
        jobs = _json(
            _read_with_retries(api, f"/attempts/{attempt_id}/jobs"),
            "List jobs",
        )
        job = next((item for item in jobs if item.get("answer_id") == answer_id), None)
        if job:
            stage = str(job.get("stage") or job.get("status") or "unknown")
            if stage != last_stage:
                print(f"  worker stage: {stage}", flush=True)
                last_stage = stage
            if job.get("status") == "succeeded":
                return job
            if job.get("status") == "failed":
                raise RuntimeError(
                    "Worker job failed: "
                    f"{job.get('error_code')}: {job.get('error_detail')}"
                )
        time.sleep(2)
    raise TimeoutError(f"Worker did not finish answer {answer_id} in time")


def _user_exists(admin: httpx.Client, user_id: str) -> bool:
    response = _read_with_retries(admin, f"/auth/v1/admin/users/{user_id}")
    if response.status_code == 404:
        return False
    _json(response, "Check disposable user")
    return True


def _wait_for_account_deletion(
    admin: httpx.Client,
    *,
    user_id: str,
    timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _user_exists(admin, user_id):
            return
        time.sleep(2)
    raise TimeoutError("Trusted deletion worker did not remove the disposable account")


def run(args: argparse.Namespace) -> dict[str, Any]:
    if not args.i_understand_live_writes:
        raise RuntimeError(
            "Refusing live writes. Pass --i-understand-live-writes to create and "
            "delete a disposable test account."
        )
    settings = get_settings()
    if not settings.worker_configured or settings.supabase_secret_key is None:
        raise RuntimeError("The trusted Supabase worker key is not configured")
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise RuntimeError("Supabase public configuration is missing")
    if PROJECT_REF not in settings.supabase_url:
        raise RuntimeError(
            f"This smoke test is locked to Supabase project {PROJECT_REF}"
        )
    fixture = Path(args.video_fixture).resolve()
    if not fixture.is_file():
        raise FileNotFoundError(f"Public FI video fixture is missing: {fixture}")
    video = fixture.read_bytes()
    if not video:
        raise RuntimeError("The public FI video fixture is empty")

    secret_key = settings.supabase_secret_key.get_secret_value()
    email = f"fairhireai-e2e-{secrets.token_hex(8)}@example.com"
    password = f"Fh!{secrets.token_urlsafe(24)}"
    user_id: str | None = None
    access_token: str | None = None
    deletion_requested = False
    completed_attempt_id: str | None = None

    admin_headers = {"apikey": secret_key, "Authorization": f"Bearer {secret_key}"}
    public_headers = {"apikey": settings.supabase_publishable_key}
    with (
        httpx.Client(
            base_url=settings.supabase_url.rstrip("/"),
            headers=admin_headers,
            timeout=60,
            transport=httpx.HTTPTransport(retries=3),
        ) as admin,
        httpx.Client(
            base_url=settings.supabase_url.rstrip("/"),
            headers=public_headers,
            timeout=60,
            transport=httpx.HTTPTransport(retries=3),
        ) as public,
    ):
        try:
            created = _json(
                admin.post(
                    "/auth/v1/admin/users",
                    json={
                        "email": email,
                        "password": password,
                        "email_confirm": True,
                        "user_metadata": {
                            "display_name": "FairHireAI Live E2E",
                            "synthetic_test_account": True,
                        },
                    },
                ),
                "Create disposable user",
            )
            user_id = str(created["id"])
            signed_in = _json(
                public.post(
                    "/auth/v1/token",
                    params={"grant_type": "password"},
                    json={"email": email, "password": password},
                ),
                "Sign in disposable user",
            )
            access_token = str(signed_in["access_token"])
            user_headers = {
                "apikey": settings.supabase_publishable_key,
                "Authorization": f"Bearer {access_token}",
            }
            with (
                httpx.Client(
                    base_url=settings.supabase_url.rstrip("/"),
                    headers=user_headers,
                    timeout=120,
                ) as storage,
                httpx.Client(
                    base_url=args.api_base_url.rstrip("/"),
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=180,
                ) as api,
            ):
                health = _json(
                    httpx.get(
                        f"{args.api_base_url.rstrip('/')}/health",
                        timeout=15,
                    ),
                    "Backend health",
                )
                if health.get("status") != "ok":
                    raise RuntimeError("Backend health check did not return ok")

                for consent_type in REQUIRED_CONSENTS:
                    _json(
                        api.post(
                            "/privacy/consents",
                            json={
                                "attempt_id": None,
                                "consent_type": consent_type,
                                "policy_version": POLICY_VERSION,
                                "granted": True,
                                "source": "web",
                                "metadata": {
                                    "purpose": "automated_live_e2e",
                                    "synthetic": True,
                                },
                            },
                        ),
                        f"Record {consent_type} consent",
                    )
                _json(
                    api.post(
                        "/privacy/consents",
                        json={
                            "attempt_id": None,
                            "consent_type": "research_evaluation",
                            "policy_version": POLICY_VERSION,
                            "granted": False,
                            "source": "web",
                            "metadata": {
                                "purpose": "automated_live_e2e",
                                "synthetic": True,
                            },
                        },
                    ),
                    "Record optional research opt-out",
                )

                attempt = _json(
                    api.post(
                        "/attempts",
                        json={"role_id": ROLE_ID, "confirm_role": True},
                    ),
                    "Create assessment attempt",
                )
                completed_attempt_id = str(attempt["id"])
                resume_result = _json(
                    api.post(
                        "/documents/resume",
                        files={
                            "file": (
                                "synthetic_resume.txt",
                                SYNTHETIC_RESUME,
                                "text/plain",
                            )
                        },
                    ),
                    "Extract resume evidence",
                )
                resume_path = (
                    f"{user_id}/attempts/{completed_attempt_id}/synthetic_resume.txt"
                )
                _upload(
                    storage,
                    bucket=DOCUMENT_BUCKET,
                    path=resume_path,
                    content=SYNTHETIC_RESUME,
                    content_type="text/plain",
                )
                attached = _json(
                    api.post(
                        f"/attempts/{completed_attempt_id}/resume",
                        json={
                            "private_resume_storage_key": resume_path,
                            "mime_type": "text/plain",
                            "evidence": resume_result["evidence"],
                        },
                    ),
                    "Attach resume evidence",
                )
                if attached.get("claim_count", 0) < 1:
                    raise RuntimeError("Synthetic resume produced no evidence claims")

                question_count = 0
                while question_count < 12:
                    current = _json(
                        _read_with_retries(api, f"/attempts/{completed_attempt_id}"),
                        "Read attempt",
                    )
                    if current.get("status") == "completed":
                        break
                    next_result = _json(
                        _read_with_retries(
                            api,
                            f"/attempts/{completed_attempt_id}/next-question",
                        ),
                        "Request approved question",
                    )
                    question = next_result.get("question")
                    if not question:
                        raise RuntimeError(
                            "Interview returned no question before report completion"
                        )
                    question_count += 1
                    kind = "follow-up" if question.get("is_follow_up") else "core"
                    print(
                        f"[{question_count}/12 max] {kind} question for "
                        f"{question['competency_id']}",
                        flush=True,
                    )
                    video_path = (
                        f"{user_id}/attempts/{completed_attempt_id}/answers/"
                        f"{question['id']}.mp4"
                    )
                    _upload(
                        storage,
                        bucket=VIDEO_BUCKET,
                        path=video_path,
                        content=video,
                        content_type="video/mp4",
                    )
                    answer = _json(
                        api.post(
                            f"/attempts/{completed_attempt_id}/answers",
                            json={
                                "question_id": question["id"],
                                "private_video_storage_key": video_path,
                                "video_sha256": _sha256(video),
                                "duration_seconds": args.video_duration_seconds,
                            },
                        ),
                        "Submit interview answer",
                    )
                    _json(
                        api.post(f"/attempts/{completed_attempt_id}/process"),
                        "Queue answer processing",
                    )
                    _wait_for_answer_job(
                        api,
                        attempt_id=completed_attempt_id,
                        answer_id=str(answer["id"]),
                        timeout_seconds=args.worker_timeout_seconds,
                    )
                current = _json(
                    _read_with_retries(api, f"/attempts/{completed_attempt_id}"),
                    "Confirm interview completion",
                )
                if current.get("status") != "completed":
                    raise RuntimeError("Interview exceeded its hard 12-question bound")

                report = _json(
                    _read_with_retries(
                        api,
                        f"/attempts/{completed_attempt_id}/report",
                    ),
                    "Read evidence-backed report",
                )
                if report.get("status") != "completed" or not report.get("scorecard"):
                    raise RuntimeError("Completed attempt has no scorecard")
                if not report.get("evidence_nodes"):
                    raise RuntimeError("Completed attempt has no evidence nodes")
                roadmap = report.get("roadmap_items")
                if not isinstance(roadmap, list):
                    raise RuntimeError("Completed attempt has an invalid roadmap payload")
                if any(item.get("reviewer_approved") is not True for item in roadmap):
                    raise RuntimeError("Roadmap contains an unapproved item")
                progress = _json(_read_with_retries(api, "/progress"), "Read progress")
                if completed_attempt_id not in {
                    str(item.get("attempt_id")) for item in progress.get("attempts", [])
                }:
                    raise RuntimeError("Completed attempt is missing from progress")

                _json(
                    api.post(
                        "/privacy/deletion-requests",
                        json={"scope": "account", "attempt_id": None},
                    ),
                    "Request disposable-account deletion",
                )
                deletion_requested = True

            _wait_for_account_deletion(
                admin,
                user_id=user_id,
                timeout_seconds=args.deletion_timeout_seconds,
            )
            return {
                "status": "passed",
                "role_id": ROLE_ID,
                "questions_processed": question_count,
                "resume_claims": int(attached["claim_count"]),
                "evidence_nodes": len(report["evidence_nodes"]),
                "roadmap_items": len(roadmap),
                "account_deleted": True,
            }
        finally:
            if user_id and _user_exists(admin, user_id):
                if access_token and not deletion_requested:
                    try:
                        with httpx.Client(
                            base_url=args.api_base_url.rstrip("/"),
                            headers={"Authorization": f"Bearer {access_token}"},
                            timeout=30,
                        ) as cleanup_api:
                            cleanup_api.post(
                                "/privacy/deletion-requests",
                                json={"scope": "account", "attempt_id": None},
                            )
                        _wait_for_account_deletion(
                            admin,
                            user_id=user_id,
                            timeout_seconds=args.deletion_timeout_seconds,
                        )
                    except Exception:
                        pass
                if _user_exists(admin, user_id):
                    response = admin.delete(f"/auth/v1/admin/users/{user_id}")
                    if response.status_code not in {200, 204, 404}:
                        print(
                            "WARNING: disposable user cleanup requires attention; "
                            f"admin delete returned HTTP {response.status_code}",
                            flush=True,
                        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-base-url",
        default="http://127.0.0.1:8000/api/v1",
    )
    parser.add_argument(
        "--video-fixture",
        default=(
            "D:/FairHireAI-data/raw/FirstImpressionsV2/train/"
            "mIQnQ8Nmj-c.005.mp4"
        ),
    )
    parser.add_argument("--video-duration-seconds", type=float, default=15.3)
    parser.add_argument("--worker-timeout-seconds", type=float, default=420)
    parser.add_argument("--deletion-timeout-seconds", type=float, default=180)
    parser.add_argument("--i-understand-live-writes", action="store_true")
    args = parser.parse_args()
    result = run(args)
    print(result, flush=True)


if __name__ == "__main__":
    main()
