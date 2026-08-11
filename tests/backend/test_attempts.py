import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.api.v1.attempts import create_attempt as create_attempt_endpoint
from backend.app.config import get_settings
from backend.app.domain.attempts import (
    AttemptCreationRequest,
    AttemptRecord,
    JobDescriptionSubmission,
    validate_attempt_transition,
)
from backend.app.domain.roles import build_assessment_profile
from backend.app.main import app
from backend.app.repositories.supabase import SupabaseAttemptRepository


class CapturingAttemptRepository:
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id
        self.profile = None
        self.closed = False

    def authenticated_user_id(self) -> UUID:
        return self.user_id

    def create_attempt(self, *, request, profile) -> AttemptRecord:
        self.profile = profile
        return AttemptRecord.model_validate(
            _attempt_payload(
                attempt_id=uuid4(),
                user_id=self.user_id,
                profile_source=profile.source,
            )
        )

    def close(self) -> None:
        self.closed = True


def _attempt_payload(
    *,
    attempt_id: UUID,
    user_id: UUID,
    status: str = "role_confirmed",
    profile_source: str = "approved_role",
) -> dict[str, object]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(attempt_id),
        "user_id": str(user_id),
        "parent_attempt_id": None,
        "role_id": "junior_backend_developer",
        "role_template_version": "1.0.0",
        "assessment_profile_source": profile_source,
        "assessment_profile_version": (
            "approved-role-selection-v2"
            if profile_source == "approved_role"
            else "optional-jd-mapper-v2"
        ),
        "status": status,
        "competency_weights": {
            "programming_fundamentals": 0.2,
            "api_design": 0.2,
            "database_reasoning": 0.2,
            "debugging_problem_solving": 0.15,
            "system_design_basics": 0.15,
            "technical_communication": 0.1,
        },
        "started_at": None,
        "completed_at": now if status == "completed" else None,
        "created_at": now,
        "updated_at": now,
    }


def test_attempt_transition_contract() -> None:
    validate_attempt_transition("role_confirmed", "interviewing")
    validate_attempt_transition("failed", "processing")
    try:
        validate_attempt_transition("completed", "interviewing")
    except ValueError as exc:
        assert "Invalid attempt transition" in str(exc)
    else:
        raise AssertionError("Completed attempts must be terminal")


def test_attempt_record_requires_normalized_weights() -> None:
    payload = _attempt_payload(attempt_id=uuid4(), user_id=uuid4())
    payload["competency_weights"] = {"only": 0.2}
    try:
        AttemptRecord.model_validate(payload)
    except ValueError as exc:
        assert "must total 1.0" in str(exc)
    else:
        raise AssertionError("Invalid weights should be rejected")


def test_attempt_creation_without_jd_uses_approved_base_profile() -> None:
    repository = CapturingAttemptRepository(uuid4())
    request = AttemptCreationRequest(
        role_id="junior_backend_developer",
        confirm_role=True,
    )

    created = create_attempt_endpoint(request, repository)

    assert created.assessment_profile_source == "approved_role"
    assert repository.profile is not None
    assert repository.profile.jd_mapping is None
    assert repository.profile.competency_weights["api_design"] == 0.20
    assert repository.closed


def test_attempt_creation_with_jd_uses_adapted_profile() -> None:
    user_id = uuid4()
    repository = CapturingAttemptRepository(user_id)
    request = AttemptCreationRequest(
        role_id="junior_backend_developer",
        confirm_role=True,
        job_description=JobDescriptionSubmission(
            private_jd_storage_key=f"{user_id}/attempts/input/job.txt",
            jd_sha256="b" * 64,
            extracted_job_description=(
                "Junior Backend Developer using REST API design, authentication, "
                "FastAPI, PostgreSQL, SQL, testing, debugging, Docker, and Git."
            ),
        ),
    )

    created = create_attempt_endpoint(request, repository)

    assert created.assessment_profile_source == "job_description"
    assert repository.profile is not None
    assert repository.profile.jd_mapping is not None
    assert repository.profile.competency_weights["api_design"] > 0.20
    assert repository.closed


def test_partial_optional_jd_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AttemptCreationRequest.model_validate(
            {
                "role_id": "junior_backend_developer",
                "confirm_role": True,
                "job_description": {
                    "private_jd_storage_key": "user/input/job.txt",
                    "jd_sha256": "c" * 64,
                },
            }
        )


def test_unsupported_supplied_jd_closes_repository() -> None:
    user_id = uuid4()
    repository = CapturingAttemptRepository(user_id)
    request = AttemptCreationRequest(
        role_id="junior_backend_developer",
        confirm_role=True,
        job_description=JobDescriptionSubmission(
            private_jd_storage_key=f"{user_id}/attempts/input/job.txt",
            jd_sha256="d" * 64,
            extracted_job_description=(
                "Frontend Developer using React, CSS, browser accessibility, "
                "TypeScript, design systems, component libraries, and testing."
            ),
        ),
    )

    with pytest.raises(HTTPException) as raised:
        create_attempt_endpoint(request, repository)

    assert raised.value.status_code == 422
    assert repository.closed


def test_supabase_repository_creates_attempt_without_jd() -> None:
    user_id = uuid4()
    attempt_id = uuid4()
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        if request.url.path == "/auth/v1/user":
            return httpx.Response(200, json={"id": str(user_id)})
        if request.url.path == "/rest/v1/rpc/create_assessment_attempt":
            return httpx.Response(
                200,
                json=[_attempt_payload(attempt_id=attempt_id, user_id=user_id)],
            )
        raise AssertionError(f"Unexpected request: {request.url}")

    repository = SupabaseAttemptRepository(
        base_url="https://example.supabase.co",
        publishable_key="publishable-key",
        access_token="user-jwt",
        transport=httpx.MockTransport(handler),
    )
    creation = AttemptCreationRequest(
        role_id="junior_backend_developer",
        confirm_role=True,
    )
    assert repository.authenticated_user_id() == user_id
    created = repository.create_attempt(
        request=creation,
        profile=build_assessment_profile(),
    )
    repository.close()

    assert created.id == attempt_id
    assert all(request.headers["authorization"] == "Bearer user-jwt" for request in seen_requests)
    assert all(request.headers["apikey"] == "publishable-key" for request in seen_requests)
    rpc_payload = json.loads(seen_requests[-1].content)
    assert rpc_payload["p_profile_source"] == "approved_role"
    assert rpc_payload["p_storage_key"] is None
    assert rpc_payload["p_mapping_result"] is None


def test_supabase_repository_persists_supplied_jd_profile() -> None:
    user_id = uuid4()
    attempt_id = uuid4()
    seen_rpc_payload: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/rest/v1/rpc/create_assessment_attempt":
            seen_rpc_payload.update(json.loads(request.content))
            return httpx.Response(
                200,
                json=[
                    _attempt_payload(
                        attempt_id=attempt_id,
                        user_id=user_id,
                        profile_source="job_description",
                    )
                ],
            )
        raise AssertionError(f"Unexpected request: {request.url}")

    jd_text = (
        "Junior Backend Developer role using Python, REST APIs, SQL, testing, "
        "debugging, PostgreSQL, Docker, and Git."
    )
    creation = AttemptCreationRequest(
        role_id="junior_backend_developer",
        confirm_role=True,
        job_description=JobDescriptionSubmission(
            private_jd_storage_key=f"{user_id}/attempts/input/job-description.txt",
            jd_sha256="a" * 64,
            extracted_job_description=jd_text,
        ),
    )
    repository = SupabaseAttemptRepository(
        base_url="https://example.supabase.co",
        publishable_key="publishable-key",
        access_token="user-jwt",
        transport=httpx.MockTransport(handler),
    )
    created = repository.create_attempt(
        request=creation,
        profile=build_assessment_profile(job_description=jd_text),
    )
    repository.close()

    assert created.assessment_profile_source == "job_description"
    assert seen_rpc_payload["p_profile_source"] == "job_description"
    assert seen_rpc_payload["p_storage_key"] == (
        f"{user_id}/attempts/input/job-description.txt"
    )
    mapping = seen_rpc_payload["p_mapping_result"]
    assert isinstance(mapping, dict)
    assert mapping["mapping_version"] == "optional-jd-mapper-v2"


def test_attempt_api_fails_closed_without_supabase_configuration(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ROLEREADY_SUPABASE_URL", raising=False)
    monkeypatch.delenv("ROLEREADY_SUPABASE_PUBLISHABLE_KEY", raising=False)
    get_settings.cache_clear()
    client = TestClient(app)
    response = client.get(
        f"/api/v1/attempts/{uuid4()}",
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Supabase is not configured."
    get_settings.cache_clear()
