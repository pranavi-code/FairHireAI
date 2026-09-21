"""Service-key Supabase adapter used only by trusted local/deployed workers."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from backend.app.domain.knowledge import (
    QuestionSearchRequest,
    QuestionSearchResult,
    ResourceSearchRequest,
    ResourceSearchResult,
)


class WorkerRepositoryError(RuntimeError):
    pass


class SupabaseWorkerRepository:
    _STORAGE_RETRY_DELAYS_SECONDS = (0.0, 0.25, 1.0)

    def __init__(
        self,
        *,
        base_url: str,
        secret_key: str,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not secret_key:
            raise ValueError("A server-only Supabase secret key is required")
        resilient_transport = transport or httpx.HTTPTransport(retries=3)
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "apikey": secret_key,
                "Authorization": f"Bearer {secret_key}",
            },
            timeout=timeout_seconds,
            transport=resilient_transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SupabaseWorkerRepository:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                return str(payload.get("message") or payload.get("error") or payload)
        except ValueError:
            pass
        return response.text or f"Supabase HTTP {response.status_code}"

    def _check(self, response: httpx.Response) -> httpx.Response:
        if response.is_error:
            raise WorkerRepositoryError(self._message(response))
        return response

    def _rows(
        self,
        table: str,
        *,
        params: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        response = self._check(self._client.get(f"/rest/v1/{table}", params=params))
        payload = response.json()
        if not isinstance(payload, list):
            raise WorkerRepositoryError(f"Invalid {table} response")
        return [item for item in payload if isinstance(item, dict)]

    def claim_processing_job(self, worker_id: str) -> dict[str, Any] | None:
        response = self._check(
            self._client.post(
                "/rest/v1/rpc/claim_next_processing_job",
                json={"p_worker_id": worker_id},
            )
        )
        payload = response.json()
        if not isinstance(payload, list):
            raise WorkerRepositoryError("Invalid processing-job claim response")
        return payload[0] if payload else None

    def update_job(self, job_id: str, **values: object) -> None:
        self._check(
            self._client.patch(
                "/rest/v1/processing_jobs",
                params={"id": f"eq.{job_id}"},
                headers={"Prefer": "return=minimal"},
                json=values,
            )
        )

    def update_answer(self, answer_id: str, **values: object) -> None:
        self._check(
            self._client.patch(
                "/rest/v1/answers",
                params={"id": f"eq.{answer_id}"},
                headers={"Prefer": "return=minimal"},
                json=values,
            )
        )

    def update_attempt(self, attempt_id: str, **values: object) -> None:
        self._check(
            self._client.patch(
                "/rest/v1/attempts",
                params={"id": f"eq.{attempt_id}"},
                headers={"Prefer": "return=minimal"},
                json=values,
            )
        )

    def attempt(self, attempt_id: str) -> dict[str, Any]:
        rows = self._rows(
            "attempts",
            params={"id": f"eq.{attempt_id}", "select": "*", "limit": "1"},
        )
        if len(rows) != 1:
            raise WorkerRepositoryError("Attempt was not found")
        return rows[0]

    def request_report_generation(self, attempt_id: str) -> dict[str, object]:
        """Queue an idempotent early-completion report after six evaluated answers."""

        attempt = self.attempt(attempt_id)
        if attempt.get("status") == "completed":
            return {
                "attempt_id": attempt_id,
                "started": True,
                "queued_job_count": 0,
                "message": "The evidence-backed report is already complete.",
            }
        if attempt.get("status") != "interviewing":
            raise WorkerRepositoryError(
                "Finish the current answer processing before submitting the interview."
            )

        answers = self._rows(
            "answers",
            params={
                "attempt_id": f"eq.{attempt_id}",
                "select": "id,processing_status",
            },
        )
        if any(item.get("processing_status") != "complete" for item in answers):
            raise WorkerRepositoryError(
                "Every submitted answer must finish processing before the "
                "interview can be submitted."
            )
        analyses = self._rows(
            "answer_analyses",
            params={"attempt_id": f"eq.{attempt_id}", "select": "answer_id"},
        )
        analyzed_ids = {str(item["answer_id"]) for item in analyses}
        evaluated_count = sum(
            1 for item in answers if str(item["id"]) in analyzed_ids
        )
        if evaluated_count < 6:
            raise WorkerRepositoryError(
                "At least 6 evaluated answers are required before submitting the interview."
            )

        idempotency_key = f"report-generation:{attempt_id}:manual-v1"
        existing = self._rows(
            "processing_jobs",
            params={
                "idempotency_key": f"eq.{idempotency_key}",
                "select": "*",
                "limit": "1",
            },
        )
        queued_count = 0
        if existing:
            job = existing[0]
            status = str(job.get("status"))
            if status == "failed":
                if int(job.get("attempt_count") or 0) >= int(
                    job.get("max_attempts") or 3
                ):
                    raise WorkerRepositoryError(
                        "Report generation reached its retry limit. A maintainer "
                        "must inspect the persisted error."
                    )
                self.update_job(
                    str(job["id"]),
                    status="queued",
                    stage="waiting_for_worker",
                    error_code=None,
                    error_detail=None,
                    queued_at=datetime.now(timezone.utc).isoformat(),
                    started_at=None,
                    finished_at=None,
                )
                queued_count = 1
            elif status in {"queued", "running"}:
                queued_count = 0
            elif status == "succeeded":
                queued_count = 0
            else:
                raise WorkerRepositoryError("The existing report job cannot be restarted.")
        else:
            response = self._check(
                self._client.post(
                    "/rest/v1/processing_jobs",
                    params={"on_conflict": "idempotency_key"},
                    headers={
                        "Prefer": "resolution=ignore-duplicates,return=representation"
                    },
                    json={
                        "attempt_id": attempt_id,
                        "answer_id": None,
                        "job_type": "report_generation",
                        "status": "queued",
                        "stage": "waiting_for_worker",
                        "idempotency_key": idempotency_key,
                    },
                )
            )
            payload = response.json()
            if not isinstance(payload, list) or len(payload) > 1:
                raise WorkerRepositoryError("Invalid report-generation job response")
            # A concurrent finish request may have inserted the same unique
            # idempotency key after our initial read. PostgREST returns an empty
            # representation for the ignored duplicate; both callers still
            # converge on the one durable report job.
            queued_count = 1 if payload else 0

        self.update_attempt(attempt_id, status="processing")
        return {
            "attempt_id": attempt_id,
            "started": True,
            "queued_job_count": queued_count,
            "message": (
                "Evidence-backed report generation queued from "
                f"{evaluated_count} evaluated answers."
            ),
        }

    def answer_context(self, answer_id: str) -> dict[str, Any]:
        answers = self._rows("answers", params={"id": f"eq.{answer_id}", "select": "*"})
        if len(answers) != 1:
            raise WorkerRepositoryError("Answer was not found")
        answer = answers[0]
        questions = self._rows(
            "interview_questions",
            params={"id": f"eq.{answer['question_id']}", "select": "*"},
        )
        attempts = self._rows(
            "attempts",
            params={"id": f"eq.{answer['attempt_id']}", "select": "*"},
        )
        if len(questions) != 1 or len(attempts) != 1:
            raise WorkerRepositoryError("Answer context is incomplete")
        return {"answer": answer, "question": questions[0], "attempt": attempts[0]}

    def resume_claims(self, attempt_id: str) -> list[dict[str, Any]]:
        return self._rows(
            "resume_claims",
            params={"attempt_id": f"eq.{attempt_id}", "select": "*", "order": "id.asc"},
        )

    def external_ai_consent(self, user_id: str, attempt_id: str) -> bool:
        rows = self._rows(
            "consent_records",
            params={
                "user_id": f"eq.{user_id}",
                "consent_type": "eq.external_ai_processing",
                "or": f"(attempt_id.eq.{attempt_id},attempt_id.is.null)",
                "select": "granted,occurred_at",
                "order": "occurred_at.desc",
                "limit": "1",
            },
        )
        return bool(rows and rows[0].get("granted") is True)

    def download_object(self, bucket: str, storage_key: str, destination: Path) -> None:
        response: httpx.Response | None = None
        last_error: Exception | None = None
        for delay in self._STORAGE_RETRY_DELAYS_SECONDS:
            if delay:
                time.sleep(delay)
            try:
                candidate = self._client.get(
                    f"/storage/v1/object/{bucket}/{storage_key}",
                    timeout=httpx.Timeout(120.0, connect=15.0),
                )
                if candidate.status_code < 500:
                    response = self._check(candidate)
                    break
                last_error = WorkerRepositoryError(self._message(candidate))
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
        if response is None:
            raise WorkerRepositoryError(
                "Private video download failed after three bounded attempts."
            ) from last_error
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)

    def upload_object(
        self,
        bucket: str,
        storage_key: str,
        source: Path,
        *,
        content_type: str,
    ) -> None:
        headers = {
            "Content-Type": content_type,
            "x-upsert": "true",
        }
        self._check(
            self._client.post(
                f"/storage/v1/object/{bucket}/{storage_key}",
                headers=headers,
                content=source.read_bytes(),
            )
        )

    def delete_object(self, bucket: str, storage_key: str) -> None:
        response = self._client.delete(f"/storage/v1/object/{bucket}/{storage_key}")
        if response.status_code not in {200, 204, 404}:
            self._check(response)

    def upsert_answer_analysis(self, row: dict[str, object]) -> dict[str, Any]:
        response = self._check(
            self._client.post(
                "/rest/v1/answer_analyses",
                params={"on_conflict": "answer_id"},
                headers={"Prefer": "resolution=merge-duplicates,return=representation"},
                json=row,
            )
        )
        payload = response.json()
        if not isinstance(payload, list) or len(payload) != 1:
            raise WorkerRepositoryError("Invalid answer-analysis upsert response")
        return payload[0]

    def attempt_material(self, attempt_id: str) -> dict[str, list[dict[str, Any]]]:
        return {
            "questions": self._rows(
                "interview_questions",
                params={
                    "attempt_id": f"eq.{attempt_id}",
                    "select": "*",
                    "order": "sequence_number.asc",
                },
            ),
            "answers": self._rows(
                "answers",
                params={"attempt_id": f"eq.{attempt_id}", "select": "*"},
            ),
            "analyses": self._rows(
                "answer_analyses",
                params={"attempt_id": f"eq.{attempt_id}", "select": "*"},
            ),
            "resume_claims": self.resume_claims(attempt_id),
        }

    def approved_resources(self) -> list[dict[str, Any]]:
        return self._rows(
            "learning_resources",
            params={"reviewer_status": "eq.approved", "select": "*"},
        )

    def search_question_packages(
        self,
        request: QuestionSearchRequest,
    ) -> list[QuestionSearchResult]:
        response = self._check(
            self._client.post(
                "/rest/v1/rpc/match_question_packages",
                json={
                    "p_query": request.query,
                    "p_role_id": request.role_id,
                    "p_competency_id": request.competency_id,
                    "p_seniority": request.seniority,
                    "p_difficulty": request.difficulty,
                    "p_query_embedding": request.query_embedding,
                    "p_match_count": request.match_count,
                },
            )
        )
        payload = response.json()
        if not isinstance(payload, list):
            raise WorkerRepositoryError("Invalid question-package matches response")
        return [QuestionSearchResult.model_validate(item) for item in payload]

    def validated_question_package_by_id(
        self,
        package_id: str,
    ) -> dict[str, Any] | None:
        rows = self._rows(
            "question_packages",
            params={
                "id": f"eq.{package_id}",
                "validation_status": (
                    "in.(generated_validated_for_practice,"
                    "faculty_reviewed_research_set)"
                ),
                "select": "*",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def search_learning_resources(
        self,
        request: ResourceSearchRequest,
    ) -> list[ResourceSearchResult]:
        response = self._check(
            self._client.post(
                "/rest/v1/rpc/match_learning_resources",
                json={
                    "p_query": request.query,
                    "p_competency_id": request.competency_id,
                    "p_difficulty": request.difficulty,
                    "p_query_embedding": request.query_embedding,
                    "p_match_count": request.match_count,
                },
            )
        )
        payload = response.json()
        if not isinstance(payload, list):
            raise WorkerRepositoryError("Invalid learning-resource matches response")
        return [ResourceSearchResult.model_validate(item) for item in payload]

    def replace_attempt_outputs(
        self,
        *,
        attempt_id: str,
        nodes: list[dict[str, object]],
        edges: list[dict[str, object]],
        scorecard: dict[str, object],
        roadmap_items: list[dict[str, object]],
        progress_metric: dict[str, object] | None,
    ) -> None:
        for table in ("roadmap_items", "evidence_edges", "evidence_nodes", "scorecards"):
            self._check(
                self._client.delete(
                    f"/rest/v1/{table}",
                    params={"attempt_id": f"eq.{attempt_id}"},
                )
            )
        if nodes:
            self._check(
                self._client.post(
                    "/rest/v1/evidence_nodes",
                    headers={"Prefer": "return=minimal"},
                    json=nodes,
                )
            )
        if edges:
            self._check(
                self._client.post(
                    "/rest/v1/evidence_edges",
                    headers={"Prefer": "return=minimal"},
                    json=edges,
                )
            )
        self._check(
            self._client.post(
                "/rest/v1/scorecards",
                headers={"Prefer": "return=minimal"},
                json=scorecard,
            )
        )
        if roadmap_items:
            self._check(
                self._client.post(
                    "/rest/v1/roadmap_items",
                    headers={"Prefer": "return=minimal"},
                    json=roadmap_items,
                )
            )
        if progress_metric:
            self._check(
                self._client.post(
                    "/rest/v1/progress_metrics",
                    params={"on_conflict": "earlier_attempt_id,later_attempt_id"},
                    headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
                    json=progress_metric,
                )
            )

    def scorecard(self, attempt_id: str) -> dict[str, Any] | None:
        rows = self._rows(
            "scorecards",
            params={"attempt_id": f"eq.{attempt_id}", "select": "*"},
        )
        return rows[0] if rows else None

    def claim_deletion_request(self, worker_id: str) -> dict[str, Any] | None:
        response = self._check(
            self._client.post(
                "/rest/v1/rpc/claim_next_deletion_request",
                json={"p_worker_id": worker_id},
            )
        )
        payload = response.json()
        if not isinstance(payload, list):
            raise WorkerRepositoryError("Invalid deletion claim response")
        return payload[0] if payload else None

    def deletion_storage_keys(self, request: dict[str, Any]) -> list[tuple[str, str]]:
        user_id = str(request["user_id"])
        attempt_id = request.get("attempt_id")
        attempt_filter = {"id": f"eq.{attempt_id}"} if attempt_id else {
            "user_id": f"eq.{user_id}"
        }
        attempts = self._rows("attempts", params={**attempt_filter, "select": "id"})
        keys: list[tuple[str, str]] = []
        for attempt in attempts:
            identifier = str(attempt["id"])
            for row in self._rows(
                "resume_documents",
                params={"attempt_id": f"eq.{identifier}", "select": "storage_key"},
            ):
                keys.append(("roleready-documents", str(row["storage_key"])))
            for row in self._rows(
                "job_descriptions",
                params={"attempt_id": f"eq.{identifier}", "select": "storage_key"},
            ):
                keys.append(("roleready-documents", str(row["storage_key"])))
            for row in self._rows(
                "answers",
                params={
                    "attempt_id": f"eq.{identifier}",
                    "select": "private_video_storage_key",
                },
            ):
                keys.append(
                    ("roleready-interview-video", str(row["private_video_storage_key"]))
                )
            for row in self._rows(
                "answer_analyses",
                params={
                    "attempt_id": f"eq.{identifier}",
                    "select": "aligned_artifact_storage_key",
                },
            ):
                keys.append(
                    (
                        "roleready-processing-artifacts",
                        str(row["aligned_artifact_storage_key"]),
                    )
                )
        return keys

    def complete_deletion(self, request: dict[str, Any]) -> None:
        request_id = str(request["id"])
        attempt_id = request.get("attempt_id")
        if request["scope"] == "attempt" and attempt_id:
            self._check(
                self._client.patch(
                    "/rest/v1/deletion_requests",
                    params={"id": f"eq.{request_id}"},
                    json={
                        "status": "completed",
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            )
            self._check(
                self._client.delete(
                    "/rest/v1/attempts",
                    params={"id": f"eq.{attempt_id}"},
                )
            )
            return
        self._check(
            self._client.delete(f"/auth/v1/admin/users/{request['user_id']}")
        )

    def fail_deletion(self, request_id: str, error_code: str) -> None:
        self._check(
            self._client.patch(
                "/rest/v1/deletion_requests",
                params={"id": f"eq.{request_id}"},
                json={"status": "failed", "error_code": error_code[:100]},
            )
        )
