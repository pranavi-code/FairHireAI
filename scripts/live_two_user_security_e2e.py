"""Guarded two-user live security and product E2E for FairHireAI.

The test is locked to the intended Supabase project, creates only uniquely
named disposable users/resources, verifies cross-user isolation and consent
gates, runs six real answer evaluations, requests a report through the
authenticated RPC-backed API, and removes only resources it created.
"""

from __future__ import annotations

import argparse
import hashlib
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from live_product_e2e import SYNTHETIC_RESUME

from backend.app.config import get_settings

PROJECT_REF = "gfsetwljirztyxegiets"
DOCUMENT_BUCKET = "roleready-documents"
VIDEO_BUCKET = "roleready-interview-video"
ARTIFACT_BUCKET = "roleready-processing-artifacts"
ROLE_ID = "junior_backend_developer"
POLICY_VERSION = "v1"


@dataclass
class Identity:
    label: str
    user_id: str
    access_token: str


@dataclass
class CreatedResources:
    users: list[Identity] = field(default_factory=list)
    attempt_ids: list[str] = field(default_factory=list)
    answer_ids: list[str] = field(default_factory=list)
    storage_objects: list[tuple[str, str]] = field(default_factory=list)
    job_ids: list[str] = field(default_factory=list)


def _assert_project_url(base_url: str) -> None:
    expected_host = f"{PROJECT_REF}.supabase.co"
    if urlparse(base_url).hostname != expected_host:
        raise RuntimeError(
            f"Live-write guard stopped: expected project {PROJECT_REF}."
        )


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


def _mutating_post(
    client: httpx.Client,
    base_url: str,
    path: str,
    **kwargs: object,
) -> httpx.Response:
    _assert_project_url(base_url)
    return client.post(path, **kwargs)


def _create_identity(
    admin: httpx.Client,
    public: httpx.Client,
    *,
    base_url: str,
    run_id: str,
    label: str,
) -> Identity:
    password = f"Fh!{secrets.token_urlsafe(24)}"
    email = f"fairhireai-e2e-{run_id}-{label}@example.com"
    created = _json(
        _mutating_post(
            admin,
            base_url,
            "/auth/v1/admin/users",
            json={
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {
                    "display_name": f"FairHireAI E2E {label}",
                    "synthetic_test_account": True,
                    "test_run_id": run_id,
                },
            },
        ),
        f"Create disposable user {label}",
    )
    signed_in = _json(
        public.post(
            "/auth/v1/token",
            params={"grant_type": "password"},
            json={"email": email, "password": password},
        ),
        f"Sign in disposable user {label}",
    )
    return Identity(
        label=label,
        user_id=str(created["id"]),
        access_token=str(signed_in["access_token"]),
    )


def _user_headers(publishable_key: str, identity: Identity) -> dict[str, str]:
    return {
        "apikey": publishable_key,
        "Authorization": f"Bearer {identity.access_token}",
    }


def _api_headers(identity: Identity) -> dict[str, str]:
    return {"Authorization": f"Bearer {identity.access_token}"}


def _expect_rejected(response: httpx.Response, label: str) -> None:
    if response.status_code < 400:
        raise RuntimeError(f"{label} unexpectedly succeeded")


def _expect_empty_or_rejected(response: httpx.Response, label: str) -> None:
    if response.is_error:
        return
    payload = _json(response, label)
    if payload not in ([], None):
        raise RuntimeError(f"{label} exposed or changed another user's data")


def _storage_object_is_missing(response: httpx.Response) -> bool:
    if response.status_code == 404:
        return True
    if response.status_code != 400:
        return False
    body = response.text.casefold().replace("_", " ")
    return "not found" in body or '"statuscode":"404"' in body.replace(" ", "")


def _upload(
    client: httpx.Client,
    *,
    base_url: str,
    bucket: str,
    path: str,
    content: bytes,
    content_type: str,
) -> None:
    encoded = quote(path, safe="/")
    response = _mutating_post(
        client,
        base_url,
        f"/storage/v1/object/{bucket}/{encoded}",
        headers={"Content-Type": content_type, "x-upsert": "false"},
        content=content,
    )
    _json(response, f"Upload exact test object to {bucket}")


def _wait_for_answer(
    api: httpx.Client,
    *,
    attempt_id: str,
    answer_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        jobs = _json(api.get(f"/attempts/{attempt_id}/jobs"), "List answer jobs")
        job = next((row for row in jobs if row.get("answer_id") == answer_id), None)
        if job and job.get("status") == "succeeded":
            return job
        if job and job.get("status") == "failed":
            raise RuntimeError(
                f"Answer worker failed: {job.get('error_code')}: {job.get('error_detail')}"
            )
        time.sleep(2)
    raise TimeoutError(f"Answer {answer_id} did not finish within the test timeout")


def _wait_for_completion(
    api: httpx.Client,
    *,
    attempt_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        attempt = _json(api.get(f"/attempts/{attempt_id}"), "Read report attempt")
        if attempt.get("status") == "completed":
            return attempt
        jobs = _json(api.get(f"/attempts/{attempt_id}/jobs"), "List report jobs")
        report_job = next(
            (row for row in jobs if row.get("job_type") == "report_generation"),
            None,
        )
        if report_job and report_job.get("status") == "failed":
            raise RuntimeError(
                "Report worker failed: "
                f"{report_job.get('error_code')}: {report_job.get('error_detail')}"
            )
        time.sleep(2)
    raise TimeoutError("Evidence-backed report did not finish within the test timeout")


def _user_exists(admin: httpx.Client, user_id: str) -> bool:
    response = admin.get(f"/auth/v1/admin/users/{user_id}")
    if response.status_code == 404:
        return False
    _json(response, "Check disposable user")
    return True


def _wait_for_user_deletion(
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
    raise TimeoutError(f"Disposable user {user_id} was not deleted in time")


def _cleanup_exact_resources(
    admin: httpx.Client,
    *,
    base_url: str,
    resources: CreatedResources,
) -> list[str]:
    failures: list[str] = []
    for bucket, path in reversed(resources.storage_objects):
        _assert_project_url(base_url)
        response = admin.delete(
            f"/storage/v1/object/{bucket}/{quote(path, safe='/')}"
        )
        if response.status_code not in {200, 204} and not _storage_object_is_missing(
            response
        ):
            failures.append(
                f"storage cleanup {bucket}/{path}: HTTP {response.status_code}"
            )
    for identity in reversed(resources.users):
        if not _user_exists(admin, identity.user_id):
            continue
        _assert_project_url(base_url)
        response = admin.delete(f"/auth/v1/admin/users/{identity.user_id}")
        if response.status_code not in {200, 204, 404}:
            failures.append(
                f"auth cleanup {identity.user_id}: HTTP {response.status_code}"
            )
    for identity in resources.users:
        if _user_exists(admin, identity.user_id):
            failures.append(f"auth user remains: {identity.user_id}")
    for bucket, path in resources.storage_objects:
        response = admin.get(
            f"/storage/v1/object/{bucket}/{quote(path, safe='/')}"
        )
        if not _storage_object_is_missing(response):
            failures.append(f"storage object remains: {bucket}/{path}")
    for identity in resources.users:
        for table in ("profiles", "attempts", "consent_records", "deletion_requests"):
            column = "user_id"
            response = admin.get(
                f"/rest/v1/{table}",
                params={column: f"eq.{identity.user_id}", "select": "*"},
            )
            if response.is_error or response.json() != []:
                failures.append(f"database cleanup incomplete: {table}/{identity.user_id}")
    return failures


def run(args: argparse.Namespace) -> dict[str, Any]:
    if not args.i_understand_live_writes:
        raise RuntimeError(
            "Refusing live writes. Pass --i-understand-live-writes to run the "
            "guarded disposable-user test."
        )
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise RuntimeError("Supabase public configuration is missing")
    if not settings.worker_configured or settings.supabase_secret_key is None:
        raise RuntimeError("The trusted Supabase worker key is not configured")
    _assert_project_url(settings.supabase_url)
    fixture = Path(args.video_fixture).resolve()
    if not fixture.is_file():
        raise FileNotFoundError(f"Public FI video fixture is missing: {fixture}")
    video = fixture.read_bytes()
    if not video:
        raise RuntimeError("The public FI video fixture is empty")

    run_id = secrets.token_hex(6)
    resources = CreatedResources()
    test_error: BaseException | None = None
    result: dict[str, Any] | None = None
    secret_key = settings.supabase_secret_key.get_secret_value()
    admin_headers = {"apikey": secret_key, "Authorization": f"Bearer {secret_key}"}
    public_headers = {"apikey": settings.supabase_publishable_key}

    with (
        httpx.Client(
            base_url=settings.supabase_url.rstrip("/"),
            headers=admin_headers,
            timeout=120,
            transport=httpx.HTTPTransport(retries=3),
        ) as admin,
        httpx.Client(
            base_url=settings.supabase_url.rstrip("/"),
            headers=public_headers,
            timeout=120,
            transport=httpx.HTTPTransport(retries=3),
        ) as public,
    ):
        try:
            user_a = _create_identity(
                admin,
                public,
                base_url=settings.supabase_url,
                run_id=run_id,
                label="a",
            )
            resources.users.append(user_a)
            user_b = _create_identity(
                admin,
                public,
                base_url=settings.supabase_url,
                run_id=run_id,
                label="b",
            )
            resources.users.append(user_b)
            print("Created and authenticated two disposable users.", flush=True)

            with (
                httpx.Client(
                    base_url=settings.supabase_url.rstrip("/"),
                    headers=_user_headers(settings.supabase_publishable_key, user_a),
                    timeout=120,
                ) as supabase_a,
                httpx.Client(
                    base_url=settings.supabase_url.rstrip("/"),
                    headers=_user_headers(settings.supabase_publishable_key, user_b),
                    timeout=120,
                ) as supabase_b,
                httpx.Client(
                    base_url=args.api_base_url.rstrip("/"),
                    headers=_api_headers(user_a),
                    timeout=240,
                ) as api_a,
                httpx.Client(
                    base_url=args.api_base_url.rstrip("/"),
                    headers=_api_headers(user_b),
                    timeout=120,
                ) as api_b,
            ):
                health = _json(
                    httpx.get(
                        f"{args.api_base_url.rstrip('/')}/health",
                        timeout=20,
                    ),
                    "Backend health",
                )
                if health.get("status") != "ok":
                    raise RuntimeError("Backend health did not return ok")
                if _json(supabase_a.get("/auth/v1/user"), "Verify user A")["id"] != user_a.user_id:
                    raise RuntimeError("User A token identity mismatch")
                if _json(supabase_b.get("/auth/v1/user"), "Verify user B")["id"] != user_b.user_id:
                    raise RuntimeError("User B token identity mismatch")

                _json(
                    _mutating_post(
                        api_a,
                        settings.supabase_url,
                        "/privacy/consents",
                        json={
                            "attempt_id": None,
                            "consent_type": "privacy_notice",
                            "policy_version": POLICY_VERSION,
                            "granted": True,
                            "source": "web",
                            "metadata": {"synthetic": True, "test_run_id": run_id},
                        },
                    ),
                    "Record privacy consent",
                )
                attempt = _json(
                    _mutating_post(
                        api_a,
                        settings.supabase_url,
                        "/attempts",
                        json={"role_id": ROLE_ID, "confirm_role": True},
                    ),
                    "Create disposable attempt",
                )
                attempt_id = str(attempt["id"])
                resources.attempt_ids.append(attempt_id)
                print("Created User A's disposable assessment attempt.", flush=True)

                # Least-privilege hardening must prevent even the owner from
                # bypassing validated RPCs to mutate trusted lifecycle rows.
                _assert_project_url(settings.supabase_url)
                _expect_rejected(
                    supabase_a.patch(
                        "/rest/v1/attempts",
                        params={"id": f"eq.{attempt_id}"},
                        headers={"Prefer": "return=representation"},
                        json={"status": "cancelled"},
                    ),
                    "User A direct trusted-attempt update",
                )
                _assert_project_url(settings.supabase_url)
                _expect_rejected(
                    supabase_a.delete(
                        "/rest/v1/attempts",
                        params={"id": f"eq.{attempt_id}"},
                        headers={"Prefer": "return=representation"},
                    ),
                    "User A direct trusted-attempt delete",
                )

                _expect_empty_or_rejected(
                    supabase_b.get(
                        "/rest/v1/attempts",
                        params={"id": f"eq.{attempt_id}", "select": "*"},
                    ),
                    "User B cross-read attempt",
                )
                _assert_project_url(settings.supabase_url)
                _expect_empty_or_rejected(
                    supabase_b.patch(
                        "/rest/v1/attempts",
                        params={"id": f"eq.{attempt_id}"},
                        headers={"Prefer": "return=representation"},
                        json={"status": "cancelled"},
                    ),
                    "User B cross-update attempt",
                )
                _assert_project_url(settings.supabase_url)
                _expect_empty_or_rejected(
                    supabase_b.delete(
                        "/rest/v1/attempts",
                        params={"id": f"eq.{attempt_id}"},
                        headers={"Prefer": "return=representation"},
                    ),
                    "User B cross-delete attempt",
                )
                _json(
                    api_a.get(f"/attempts/{attempt_id}"),
                    "Verify attempt survived isolation tests",
                )

                _expect_rejected(
                    _mutating_post(
                        api_a,
                        settings.supabase_url,
                        "/documents/resume",
                        files={"file": ("resume.txt", SYNTHETIC_RESUME, "text/plain")},
                    ),
                    "Resume extraction without consent",
                )
                _json(
                    _mutating_post(
                        api_a,
                        settings.supabase_url,
                        "/privacy/consents",
                        json={
                            "attempt_id": None,
                            "consent_type": "resume_processing",
                            "policy_version": POLICY_VERSION,
                            "granted": True,
                            "source": "web",
                            "metadata": {"synthetic": True, "test_run_id": run_id},
                        },
                    ),
                    "Record resume consent",
                )
                resume = _json(
                    _mutating_post(
                        api_a,
                        settings.supabase_url,
                        "/documents/resume",
                        files={"file": ("resume.txt", SYNTHETIC_RESUME, "text/plain")},
                    ),
                    "Extract synthetic resume",
                )
                resume_path = f"{user_a.user_id}/e2e/{run_id}/resume.txt"
                _upload(
                    supabase_a,
                    base_url=settings.supabase_url,
                    bucket=DOCUMENT_BUCKET,
                    path=resume_path,
                    content=SYNTHETIC_RESUME,
                    content_type="text/plain",
                )
                resources.storage_objects.append((DOCUMENT_BUCKET, resume_path))
                attached = _json(
                    _mutating_post(
                        api_a,
                        settings.supabase_url,
                        f"/attempts/{attempt_id}/resume",
                        json={
                            "private_resume_storage_key": resume_path,
                            "mime_type": "text/plain",
                            "evidence": resume["evidence"],
                        },
                    ),
                    "Attach resume with consent",
                )

                # Storage ownership must reject B and leave A's object intact.
                _expect_rejected(
                    supabase_b.get(
                        f"/storage/v1/object/{DOCUMENT_BUCKET}/{quote(resume_path, safe='/')}"
                    ),
                    "User B cross-download",
                )
                _assert_project_url(settings.supabase_url)
                _expect_rejected(
                    supabase_b.delete(
                        f"/storage/v1/object/{DOCUMENT_BUCKET}/{quote(resume_path, safe='/')}"
                    ),
                    "User B cross-delete storage",
                )
                owned_resume = supabase_a.get(
                    f"/storage/v1/object/{DOCUMENT_BUCKET}/{quote(resume_path, safe='/')}"
                )
                if owned_resume.content != SYNTHETIC_RESUME:
                    raise RuntimeError("User A resume changed during isolation tests")

                question_count = 0
                external_consent_granted = False
                recording_consent_granted = False
                while question_count < 6:
                    _assert_project_url(settings.supabase_url)
                    next_result = _json(
                        api_a.get(f"/attempts/{attempt_id}/next-question"),
                        "Request grounded interview question",
                    )
                    question = next_result.get("question")
                    if not question:
                        raise RuntimeError("Interview ended before six evaluated answers")
                    question_count += 1
                    video_path = (
                        f"{user_a.user_id}/e2e/{run_id}/answers/{question['id']}.mp4"
                    )
                    _upload(
                        supabase_a,
                        base_url=settings.supabase_url,
                        bucket=VIDEO_BUCKET,
                        path=video_path,
                        content=video,
                        content_type="video/mp4",
                    )
                    resources.storage_objects.append((VIDEO_BUCKET, video_path))
                    answer_payload = {
                        "question_id": question["id"],
                        "private_video_storage_key": video_path,
                        "video_sha256": _sha256(video),
                        "duration_seconds": args.video_duration_seconds,
                    }
                    if not recording_consent_granted:
                        _expect_rejected(
                            _mutating_post(
                                api_a,
                                settings.supabase_url,
                                f"/attempts/{attempt_id}/answers",
                                json=answer_payload,
                            ),
                            "Answer submission without recording consent",
                        )
                        _json(
                            _mutating_post(
                                api_a,
                                settings.supabase_url,
                                "/privacy/consents",
                                json={
                                    "attempt_id": attempt_id,
                                    "consent_type": "interview_recording",
                                    "policy_version": POLICY_VERSION,
                                    "granted": True,
                                    "source": "web",
                                    "metadata": {"synthetic": True, "test_run_id": run_id},
                                },
                            ),
                            "Record recording consent",
                        )
                        recording_consent_granted = True
                    answer = _json(
                        _mutating_post(
                            api_a,
                            settings.supabase_url,
                            f"/attempts/{attempt_id}/answers",
                            json=answer_payload,
                        ),
                        "Submit interview answer",
                    )
                    answer_id = str(answer["id"])
                    resources.answer_ids.append(answer_id)
                    artifact_path = (
                        f"{user_a.user_id}/attempts/{attempt_id}/answers/"
                        f"{answer_id}/aligned.npz"
                    )
                    resources.storage_objects.append((ARTIFACT_BUCKET, artifact_path))
                    if not external_consent_granted:
                        _expect_rejected(
                            _mutating_post(
                                api_a,
                                settings.supabase_url,
                                f"/attempts/{attempt_id}/process",
                            ),
                            "Processing without external-AI consent",
                        )
                        _json(
                            _mutating_post(
                                api_a,
                                settings.supabase_url,
                                "/privacy/consents",
                                json={
                                    "attempt_id": attempt_id,
                                    "consent_type": "external_ai_processing",
                                    "policy_version": POLICY_VERSION,
                                    "granted": True,
                                    "source": "web",
                                    "metadata": {"synthetic": True, "test_run_id": run_id},
                                },
                            ),
                            "Record external-AI consent",
                        )
                        external_consent_granted = True
                    _json(
                        _mutating_post(
                            api_a,
                            settings.supabase_url,
                            f"/attempts/{attempt_id}/process",
                        ),
                        "Queue answer processing",
                    )
                    job = _wait_for_answer(
                        api_a,
                        attempt_id=attempt_id,
                        answer_id=answer_id,
                        timeout_seconds=args.worker_timeout_seconds,
                    )
                    resources.job_ids.append(str(job["id"]))
                    print(
                        f"Evaluated disposable answer {question_count}/6.",
                        flush=True,
                    )

                before_finish = _json(
                    api_a.get(f"/attempts/{attempt_id}"),
                    "Read attempt before report request",
                )
                _assert_project_url(settings.supabase_url)
                finish = _json(
                    api_a.post(f"/attempts/{attempt_id}/finish"),
                    "Authenticated report enqueue",
                )
                if finish.get("started") is not True:
                    raise RuntimeError("Authenticated report RPC did not start")
                _wait_for_completion(
                    api_a,
                    attempt_id=attempt_id,
                    timeout_seconds=args.worker_timeout_seconds,
                )
                # Repeat must be idempotent and must not create a second job.
                _assert_project_url(settings.supabase_url)
                repeated_finish = _json(
                    api_a.post(f"/attempts/{attempt_id}/finish"),
                    "Idempotent report request",
                )
                if repeated_finish.get("queued_job_count") != 0:
                    raise RuntimeError("Repeated report request queued a duplicate job")
                print("Report completed and repeat submission was idempotent.", flush=True)

                jobs = _json(api_a.get(f"/attempts/{attempt_id}/jobs"), "List final jobs")
                resources.job_ids = list(
                    dict.fromkeys(resources.job_ids + [str(row["id"]) for row in jobs])
                )
                report_jobs = [row for row in jobs if row.get("job_type") == "report_generation"]
                if len(report_jobs) > 1:
                    raise RuntimeError("More than one report-generation job exists")
                report = _json(
                    api_a.get(f"/attempts/{attempt_id}/report"),
                    "Read completed evidence report",
                )
                if report.get("status") != "completed" or not report.get("scorecard"):
                    raise RuntimeError("Completed attempt has no real scorecard")
                if not report.get("evidence_nodes"):
                    raise RuntimeError("Completed attempt has no evidence graph")
                if not isinstance(report.get("roadmap_items"), list):
                    raise RuntimeError("Completed attempt has no valid roadmap list")
                progress = _json(api_a.get("/progress"), "Read one-attempt progress")
                if attempt_id not in {
                    str(item.get("attempt_id")) for item in progress.get("attempts", [])
                }:
                    raise RuntimeError("Completed attempt is missing from progress")

                _expect_rejected(
                    api_b.get(f"/attempts/{attempt_id}/report"),
                    "User B API report access",
                )
                for table in (
                    "answers",
                    "processing_jobs",
                    "answer_analyses",
                    "evidence_nodes",
                    "scorecards",
                    "roadmap_items",
                ):
                    _expect_empty_or_rejected(
                        supabase_b.get(
                            f"/rest/v1/{table}",
                            params={"attempt_id": f"eq.{attempt_id}", "select": "*"},
                        ),
                        f"User B cross-read {table}",
                    )
                _expect_rejected(
                    _mutating_post(
                        supabase_b,
                        settings.supabase_url,
                        "/rest/v1/rpc/request_attempt_report",
                        json={"p_attempt_id": attempt_id},
                    ),
                    "User B cross-user report enqueue",
                )

                # Exercise user-facing deletion for both disposable accounts.
                for identity, api in ((user_a, api_a), (user_b, api_b)):
                    _json(
                        _mutating_post(
                            api,
                            settings.supabase_url,
                            "/privacy/deletion-requests",
                            json={"scope": "account", "attempt_id": None},
                        ),
                        f"Request account deletion for user {identity.label}",
                    )

            for identity in resources.users:
                _wait_for_user_deletion(
                    admin,
                    user_id=identity.user_id,
                    timeout_seconds=args.deletion_timeout_seconds,
                )
            print("User-facing deletion removed both disposable users.", flush=True)
            result = {
                "status": "passed",
                "project_ref": PROJECT_REF,
                "run_id": run_id,
                "disposable_users": len(resources.users),
                "questions_processed": question_count,
                "answers_processed": len(resources.answer_ids),
                "report_enqueue_mode": (
                    "already_complete"
                    if before_finish.get("status") == "completed"
                    else "authenticated_rpc"
                ),
                "report_jobs": len(report_jobs),
                "resume_claims": int(attached.get("claim_count", 0)),
                "evidence_nodes": len(report["evidence_nodes"]),
                "roadmap_items": len(report["roadmap_items"]),
                "cross_user_isolation": True,
                "owner_trusted_table_write_blocked": True,
                "consent_enforcement": True,
                "account_deletion": True,
            }
        except BaseException as exc:
            test_error = exc
        finally:
            cleanup_failures = _cleanup_exact_resources(
                admin,
                base_url=settings.supabase_url,
                resources=resources,
            )

    if cleanup_failures:
        detail = "; ".join(cleanup_failures)
        if test_error is not None:
            raise RuntimeError(f"E2E failed ({test_error}); cleanup also failed: {detail}")
        raise RuntimeError(f"E2E cleanup verification failed: {detail}")
    if test_error is not None:
        raise test_error
    if result is None:
        raise RuntimeError("E2E produced no result")
    result["cleanup_verified"] = True
    return result


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
    parser.add_argument("--worker-timeout-seconds", type=float, default=480)
    parser.add_argument("--deletion-timeout-seconds", type=float, default=240)
    parser.add_argument("--i-understand-live-writes", action="store_true")
    args = parser.parse_args()
    print(run(args), flush=True)


if __name__ == "__main__":
    main()
