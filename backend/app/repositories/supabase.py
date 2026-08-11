"""Small PostgREST adapter that forwards a verified user's JWT so RLS applies."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from backend.app.domain.attempts import (
    AttemptCreationRequest,
    AttemptRecord,
    AttemptStatus,
)
from backend.app.domain.interviews import NextQuestionResult
from backend.app.domain.journey import (
    AnswerRecord,
    AnswerSubmissionRequest,
    AttemptReport,
    EvidenceEdgeView,
    EvidenceNodeView,
    PersistedQuestion,
    ProcessingJobView,
    ProcessingStartResult,
    ProgressAttempt,
    ProgressView,
    ReportCompetencyScore,
    ResumeAttachmentRequest,
    ResumeAttachmentResult,
    RoadmapItemView,
    RoadmapResourceView,
    ScorecardView,
)
from backend.app.domain.knowledge import (
    QuestionSearchRequest,
    QuestionSearchResult,
    ResourceSearchRequest,
    ResourceSearchResult,
)
from backend.app.domain.privacy import (
    ConsentRecord,
    ConsentRequest,
    DeletionRequestCreate,
    DeletionRequestRecord,
)
from backend.app.domain.roles import AssessmentProfile, RoleTemplate, load_role_template


class SupabaseRepositoryError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class SupabaseAttemptRepository:
    def __init__(
        self,
        *,
        base_url: str,
        publishable_key: str,
        access_token: str,
        timeout_seconds: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "apikey": publishable_key,
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SupabaseAttemptRepository:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                return str(payload.get("message") or payload.get("error_description") or payload)
        except ValueError:
            pass
        return response.text or f"Supabase request failed with HTTP {response.status_code}"

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_error:
            raise SupabaseRepositoryError(response.status_code, self._message(response))

    def authenticated_user_id(self) -> UUID:
        response = self._client.get("/auth/v1/user")
        self._raise_for_status(response)
        try:
            return UUID(response.json()["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SupabaseRepositoryError(502, "Supabase returned an invalid user object.") from exc

    def create_attempt(
        self,
        *,
        request: AttemptCreationRequest,
        profile: AssessmentProfile,
    ) -> AttemptRecord:
        jd = request.job_description
        response = self._client.post(
            "/rest/v1/rpc/create_assessment_attempt",
            json={
                "p_parent_attempt_id": (
                    str(request.parent_attempt_id) if request.parent_attempt_id else None
                ),
                "p_role_id": request.role_id,
                "p_profile_source": profile.source,
                "p_profile_version": profile.profile_version,
                "p_role_template_version": profile.role_template_version,
                "p_competency_weights": profile.competency_weights,
                "p_storage_key": jd.private_jd_storage_key if jd else None,
                "p_sha256": jd.jd_sha256 if jd else None,
                "p_extracted_text": jd.extracted_job_description if jd else None,
                "p_mapping_result": (
                    profile.jd_mapping.model_dump(mode="json")
                    if profile.jd_mapping
                    else None
                ),
            },
        )
        self._raise_for_status(response)
        return self._parse_single_attempt(response.json())

    def get(self, attempt_id: UUID) -> AttemptRecord:
        response = self._client.get(
            "/rest/v1/attempts",
            params={"id": f"eq.{attempt_id}", "select": "*"},
        )
        self._raise_for_status(response)
        return self._parse_single_attempt(response.json())

    def list_attempts(self) -> list[AttemptRecord]:
        response = self._client.get(
            "/rest/v1/attempts",
            params={"select": "*", "order": "created_at.desc"},
        )
        self._raise_for_status(response)
        payload = response.json()
        if not isinstance(payload, list):
            raise SupabaseRepositoryError(502, "Supabase returned invalid attempts.")
        return [AttemptRecord.model_validate(item) for item in payload]

    def transition(self, attempt_id: UUID, next_status: AttemptStatus) -> AttemptRecord:
        response = self._client.post(
            "/rest/v1/rpc/transition_attempt",
            json={"p_attempt_id": str(attempt_id), "p_next_status": next_status},
        )
        self._raise_for_status(response)
        return self._parse_single_attempt(response.json())

    def search_question_packages(
        self,
        request: QuestionSearchRequest,
    ) -> list[QuestionSearchResult]:
        response = self._client.post(
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
        self._raise_for_status(response)
        payload = response.json()
        if not isinstance(payload, list):
            raise SupabaseRepositoryError(502, "Supabase returned invalid question matches.")
        return [QuestionSearchResult.model_validate(item) for item in payload]

    def search_learning_resources(
        self,
        request: ResourceSearchRequest,
    ) -> list[ResourceSearchResult]:
        response = self._client.post(
            "/rest/v1/rpc/match_learning_resources",
            json={
                "p_query": request.query,
                "p_competency_id": request.competency_id,
                "p_difficulty": request.difficulty,
                "p_query_embedding": request.query_embedding,
                "p_match_count": request.match_count,
            },
        )
        self._raise_for_status(response)
        payload = response.json()
        if not isinstance(payload, list):
            raise SupabaseRepositoryError(502, "Supabase returned invalid resource matches.")
        return [ResourceSearchResult.model_validate(item) for item in payload]

    def attach_resume(
        self,
        attempt_id: UUID,
        request: ResumeAttachmentRequest,
    ) -> ResumeAttachmentResult:
        response = self._client.post(
            "/rest/v1/rpc/attach_resume_evidence",
            json={
                "p_attempt_id": str(attempt_id),
                "p_storage_key": request.private_resume_storage_key,
                "p_sha256": request.evidence.document_sha256,
                "p_mime_type": request.mime_type,
                "p_extractor_name": request.evidence.extractor_name,
                "p_extractor_version": request.evidence.extractor_version,
                "p_claims": [
                    {
                        "id": claim.claim_id,
                        "claim_type": claim.claim_type,
                        "normalized_text": claim.normalized_text,
                        "source_page": claim.source.page,
                        "source_start_character": claim.source.start_character,
                        "source_end_character": claim.source.end_character,
                        "source_text": claim.source.source_text,
                        "confidence": claim.confidence,
                        "normalized_skills": claim.normalized_skills,
                    }
                    for claim in request.evidence.claims
                ],
            },
        )
        self._raise_for_status(response)
        return ResumeAttachmentResult.model_validate(
            self._parse_single_row(response.json(), "Resume attachment")
        )

    def list_questions(self, attempt_id: UUID) -> list[PersistedQuestion]:
        response = self._client.get(
            "/rest/v1/interview_questions",
            params={
                "attempt_id": f"eq.{attempt_id}",
                "select": "*",
                "order": "sequence_number.asc",
            },
        )
        self._raise_for_status(response)
        payload = response.json()
        if not isinstance(payload, list):
            raise SupabaseRepositoryError(502, "Supabase returned invalid questions.")
        return [PersistedQuestion.model_validate(item) for item in payload]

    def persist_question(
        self,
        attempt_id: UUID,
        selection: NextQuestionResult,
        *,
        question_package: dict[str, Any],
        prompt_override: str | None = None,
        model_id: str | None = None,
        prompt_version: str | None = None,
    ) -> PersistedQuestion:
        if selection.action != "ask_question":
            raise ValueError("Only ask-question selections can be persisted")
        response = self._client.post(
            "/rest/v1/rpc/record_interview_question",
            json={
                "p_attempt_id": str(attempt_id),
                "p_question_template_id": selection.question_id,
                "p_competency_id": selection.competency_id,
                "p_prompt_snapshot": prompt_override or selection.prompt,
                "p_is_follow_up": selection.is_follow_up,
                "p_selection_reason": selection.reason,
                "p_question_package_id": question_package["id"],
                "p_model_id": model_id,
                "p_prompt_version": prompt_version,
            },
        )
        self._raise_for_status(response)
        return PersistedQuestion.model_validate(
            self._parse_single_row(response.json(), "Interview question")
        )

    def validated_question_package(
        self,
        *,
        role_id: str,
        competency_id: str,
        question_template_id: str,
    ) -> dict[str, Any] | None:
        response = self._client.get(
            "/rest/v1/question_packages",
            params={
                "role_id": f"eq.{role_id}",
                "competency_id": f"eq.{competency_id}",
                "validation_status": (
                    "in.(generated_validated_for_practice,"
                    "faculty_reviewed_research_set)"
                ),
                "select": "*",
                "order": "version.desc",
            },
        )
        self._raise_for_status(response)
        payload = response.json()
        if not isinstance(payload, list):
            raise SupabaseRepositoryError(502, "Supabase returned invalid question packages.")
        preferred_key = f"{role_id}:{question_template_id}"
        return next(
            (item for item in payload if item.get("package_key") == preferred_key),
            payload[0] if payload else None,
        )

    def analysis_for_answer(self, answer_id: UUID) -> dict[str, Any] | None:
        response = self._client.get(
            "/rest/v1/answer_analyses",
            params={"answer_id": f"eq.{answer_id}", "select": "*"},
        )
        self._raise_for_status(response)
        payload = response.json()
        if not isinstance(payload, list):
            raise SupabaseRepositoryError(502, "Supabase returned invalid answer analysis.")
        return payload[0] if payload else None

    def external_ai_consent(self, attempt_id: UUID) -> bool:
        response = self._client.get(
            "/rest/v1/consent_records",
            params={
                "consent_type": "eq.external_ai_processing",
                "or": f"(attempt_id.eq.{attempt_id},attempt_id.is.null)",
                "select": "granted,occurred_at",
                "order": "occurred_at.desc",
                "limit": "1",
            },
        )
        self._raise_for_status(response)
        payload = response.json()
        return bool(
            isinstance(payload, list) and payload and payload[0].get("granted") is True
        )

    def question_personalization_context(self, attempt_id: UUID) -> dict[str, list[str]]:
        claims_response = self._client.get(
            "/rest/v1/resume_claims",
            params={
                "attempt_id": f"eq.{attempt_id}",
                "select": "normalized_text,normalized_skills,confidence",
                "order": "confidence.desc",
                "limit": "20",
            },
        )
        self._raise_for_status(claims_response)
        claims = claims_response.json()
        jd_response = self._client.get(
            "/rest/v1/job_descriptions",
            params={"attempt_id": f"eq.{attempt_id}", "select": "mapping_result"},
        )
        self._raise_for_status(jd_response)
        jd_rows = jd_response.json()
        resume_summaries: list[str] = []
        skills: list[str] = []
        if isinstance(claims, list):
            for claim in claims:
                if not isinstance(claim, dict):
                    continue
                if claim.get("normalized_text"):
                    resume_summaries.append(str(claim["normalized_text"])[:500])
                skills.extend(str(item) for item in claim.get("normalized_skills") or [])
        jd_skills: list[str] = []
        if isinstance(jd_rows, list) and jd_rows:
            mapping = jd_rows[0].get("mapping_result")
            if isinstance(mapping, dict):
                by_competency = mapping.get("matched_skills_by_competency")
                if isinstance(by_competency, dict):
                    for values in by_competency.values():
                        if isinstance(values, list):
                            jd_skills.extend(str(item) for item in values)
        return {
            "candidate_skill_terms": list(dict.fromkeys(skills))[:20],
            "jd_skill_terms": list(dict.fromkeys(jd_skills))[:20],
            "resume_evidence_summaries": resume_summaries[:8],
        }

    def answer_for_question(self, question_id: UUID) -> AnswerRecord | None:
        response = self._client.get(
            "/rest/v1/answers",
            params={"question_id": f"eq.{question_id}", "select": "*"},
        )
        self._raise_for_status(response)
        payload = response.json()
        if not isinstance(payload, list):
            raise SupabaseRepositoryError(502, "Supabase returned invalid answers.")
        if not payload:
            return None
        return AnswerRecord.model_validate(payload[0])

    def submit_answer(
        self,
        attempt_id: UUID,
        request: AnswerSubmissionRequest,
    ) -> AnswerRecord:
        response = self._client.post(
            "/rest/v1/rpc/submit_interview_answer",
            json={
                "p_attempt_id": str(attempt_id),
                "p_question_id": str(request.question_id),
                "p_video_storage_key": request.private_video_storage_key,
                "p_video_sha256": request.video_sha256,
                "p_duration_seconds": request.duration_seconds,
            },
        )
        self._raise_for_status(response)
        return AnswerRecord.model_validate(
            self._parse_single_row(response.json(), "Interview answer")
        )

    def list_jobs(self, attempt_id: UUID) -> list[ProcessingJobView]:
        response = self._client.get(
            "/rest/v1/processing_jobs",
            params={
                "attempt_id": f"eq.{attempt_id}",
                "select": "*",
                "order": "queued_at.asc",
            },
        )
        self._raise_for_status(response)
        payload = response.json()
        if not isinstance(payload, list):
            raise SupabaseRepositoryError(502, "Supabase returned invalid processing jobs.")
        return [ProcessingJobView.model_validate(item) for item in payload]

    def enqueue_processing(self, attempt_id: UUID) -> ProcessingStartResult:
        response = self._client.post(
            "/rest/v1/rpc/enqueue_attempt_processing",
            json={"p_attempt_id": str(attempt_id)},
        )
        self._raise_for_status(response)
        return ProcessingStartResult.model_validate(
            self._parse_single_row(response.json(), "Processing request")
        )

    def report(self, attempt_id: UUID) -> AttemptReport:
        attempt = self.get(attempt_id)
        role = load_role_template(attempt.role_id)

        def rows(table: str, *, order: str | None = None) -> list[dict[str, Any]]:
            params = {"attempt_id": f"eq.{attempt_id}", "select": "*"}
            if order:
                params["order"] = order
            response = self._client.get(f"/rest/v1/{table}", params=params)
            self._raise_for_status(response)
            payload = response.json()
            if not isinstance(payload, list):
                raise SupabaseRepositoryError(502, f"Supabase returned invalid {table}.")
            return payload

        scorecards = rows("scorecards")
        raw_nodes = rows("evidence_nodes", order="created_at.asc")
        raw_edges = rows("evidence_edges", order="created_at.asc")
        raw_roadmap = rows("roadmap_items", order="priority.asc")
        raw_analyses = rows("answer_analyses", order="created_at.asc")
        scorecard = (
            self._scorecard_view(
                scorecards[0],
                role=role,
                competency_weights=attempt.competency_weights,
                evidence_nodes=raw_nodes,
                answer_analyses=raw_analyses,
            )
            if scorecards
            else None
        )
        return AttemptReport(
            attempt_id=attempt_id,
            status=attempt.status,
            scorecard=scorecard,
            evidence_nodes=[self._evidence_node_view(item) for item in raw_nodes],
            evidence_edges=[self._evidence_edge_view(item) for item in raw_edges],
            roadmap_items=[
                self._roadmap_item_view(item, raw_nodes) for item in raw_roadmap
            ],
            message=(
                "Evidence-backed report is complete."
                if scorecards
                else "No scorecard exists yet. Processing requires a verified trained checkpoint."
            ),
        )

    def reattempt(self, attempt_id: UUID) -> AttemptRecord:
        response = self._client.post(
            "/rest/v1/rpc/create_reattempt",
            json={"p_parent_attempt_id": str(attempt_id)},
        )
        self._raise_for_status(response)
        return self._parse_single_attempt(response.json())

    def progress(self) -> ProgressView:
        response = self._client.get(
            "/rest/v1/attempts",
            params={
                "status": "eq.completed",
                "select": (
                    "id,role_id,completed_at,"
                    "scorecards(placement_readiness,competency_scores)"
                ),
                "order": "completed_at.asc",
            },
        )
        self._raise_for_status(response)
        payload = response.json()
        if not isinstance(payload, list):
            raise SupabaseRepositoryError(502, "Supabase returned invalid progress data.")
        attempts: list[ProgressAttempt] = []
        for item in payload:
            raw_scorecards = item.get("scorecards")
            if isinstance(raw_scorecards, dict):
                scorecard = raw_scorecards
            elif (
                isinstance(raw_scorecards, list)
                and raw_scorecards
                and isinstance(raw_scorecards[0], dict)
            ):
                scorecard = raw_scorecards[0]
            else:
                scorecard = {}
            role = load_role_template(item["role_id"])
            attempts.append(
                ProgressAttempt(
                    attempt_id=item["id"],
                    role_id=item["role_id"],
                    completed_at=item["completed_at"],
                    placement_readiness=scorecard.get("placement_readiness"),
                    competency_scores=self._competency_score_views(
                        scorecard.get("competency_scores"),
                        role=role,
                        competency_weights={
                            competency.competency_id: competency.base_weight
                            for competency in role.competencies
                        },
                    ),
                )
            )
        return ProgressView(
            attempts=attempts,
            message=(
                "Completed-attempt progress is available."
                if attempts
                else "Complete at least two evidence-backed attempts to compare progress."
            ),
        )

    @staticmethod
    def _competency_score_views(
        raw_scores: object,
        *,
        role: RoleTemplate,
        competency_weights: dict[str, float],
    ) -> list[ReportCompetencyScore]:
        by_id: dict[str, dict[str, Any]] = {}
        if isinstance(raw_scores, list):
            for item in raw_scores:
                if isinstance(item, dict) and isinstance(item.get("competency_id"), str):
                    by_id[item["competency_id"]] = item
        elif isinstance(raw_scores, dict):
            for competency_id, item in raw_scores.items():
                if isinstance(item, dict):
                    by_id[str(competency_id)] = item
                elif isinstance(item, (int, float)):
                    by_id[str(competency_id)] = {"score": float(item)}

        views: list[ReportCompetencyScore] = []
        for competency in role.competencies:
            raw = by_id.get(competency.competency_id, {})
            value = raw.get("score", raw.get("value"))
            score = (
                float(value)
                if isinstance(value, (int, float)) and 0.0 <= float(value) <= 1.0
                else None
            )
            evidence_ids = raw.get("evidence_node_ids") or []
            reasons = raw.get("insufficiency_reasons") or []
            views.append(
                ReportCompetencyScore(
                    competency_id=competency.competency_id,
                    name=competency.name,
                    score=score,
                    weight=competency_weights[competency.competency_id],
                    evidence_node_ids=[
                        str(item) for item in evidence_ids if isinstance(item, str)
                    ],
                    insufficiency_reasons=[
                        str(item) for item in reasons if isinstance(item, str)
                    ],
                )
            )
        return views

    @classmethod
    def _scorecard_view(
        cls,
        raw: dict[str, Any],
        *,
        role: RoleTemplate,
        competency_weights: dict[str, float],
        evidence_nodes: list[dict[str, Any]],
        answer_analyses: list[dict[str, Any]],
    ) -> ScorecardView:
        base_signals: list[float] = []
        for node in evidence_nodes:
            if node.get("node_type") != "ModelPrediction":
                continue
            attributes = node.get("attributes")
            if not isinstance(attributes, dict):
                continue
            value = attributes.get("base_multimodal_interview_signal")
            if isinstance(value, (int, float)) and 0.0 <= float(value) <= 1.0:
                base_signals.append(float(value))
        base_signal = (
            sum(base_signals) / len(base_signals) if base_signals else None
        )
        delivery_keys = (
            "words_per_minute",
            "pause_count",
            "filler_rate",
            "pace_and_filler_quality",
            "voice_energy_consistency",
            "head_stability",
            "camera_facing_estimate",
            "transcript_confidence",
            "visual_success_rate",
        )
        delivery: dict[str, object] = {}
        for key in delivery_keys:
            values = [
                float(metrics[key])
                for item in answer_analyses
                if isinstance((metrics := item.get("delivery_metrics")), dict)
                and isinstance(metrics.get(key), (int, float))
            ]
            if values:
                delivery[key] = round(sum(values) / len(values), 6)
        if delivery:
            delivery["note"] = (
                "Observable delivery measurements only; no emotion, personality, "
                "confidence, nervousness, or employability inference."
            )
        reasons = raw.get("insufficiency_reasons") or []
        return ScorecardView(
            placement_readiness=raw.get("placement_readiness"),
            insufficiency_reasons=[
                str(item) for item in reasons if isinstance(item, str)
            ],
            base_multimodal_interview_signal=base_signal,
            delivery_signal=delivery or None,
            competencies=cls._competency_score_views(
                raw.get("competency_scores"),
                role=role,
                competency_weights=competency_weights,
            ),
        )

    @staticmethod
    def _evidence_node_view(raw: dict[str, Any]) -> EvidenceNodeView:
        attributes = raw.get("attributes")
        if not isinstance(attributes, dict):
            attributes = {}
        question = attributes.get("question")
        transcript_span = attributes.get("transcript_span")
        skill_gap = None
        if raw.get("node_type") == "SkillGap":
            skill_gap = {
                "current_score": attributes.get("current_score"),
                "target_score": attributes.get("target_score"),
                "severity": attributes.get("severity"),
                "rationale": attributes.get("rationale"),
            }
        return EvidenceNodeView(
            id=str(raw["id"]),
            kind=str(raw.get("node_type") or "EvidenceClaim"),
            label=raw.get("normalized_text"),
            competency_id=(
                str(attributes["competency_id"])
                if attributes.get("competency_id")
                else None
            ),
            transcript_span=(
                transcript_span if isinstance(transcript_span, dict) else None
            ),
            question=question if isinstance(question, dict) else None,
            resume_claim_id=(
                str(attributes["resume_claim_id"])
                if attributes.get("resume_claim_id")
                else None
            ),
            confidence=raw.get("confidence"),
            signal_quality=(
                str(attributes["signal_quality"])
                if attributes.get("signal_quality") is not None
                else None
            ),
            model_reference=(
                str(attributes["model_reference"])
                if attributes.get("model_reference")
                else None
            ),
            skill_gap=skill_gap,
        )

    @staticmethod
    def _evidence_edge_view(raw: dict[str, Any]) -> EvidenceEdgeView:
        return EvidenceEdgeView(
            id=str(raw["id"]),
            from_node_id=str(raw["source_node_id"]),
            to_node_id=str(raw["target_node_id"]),
            relation=str(raw.get("edge_type") or "supports"),
            confidence=raw.get("confidence"),
        )

    def _roadmap_item_view(
        self,
        raw: dict[str, Any],
        evidence_nodes: list[dict[str, Any]],
    ) -> RoadmapItemView:
        resource_response = self._client.get(
            "/rest/v1/learning_resources",
            params={
                "id": f"eq.{raw['resource_id']}",
                "reviewer_status": "eq.approved",
                "select": "*",
            },
        )
        self._raise_for_status(resource_response)
        resources = resource_response.json()
        resource = resources[0] if isinstance(resources, list) and resources else None

        competency_id: str | None = None
        gap_id = raw.get("skill_gap_node_id")
        for node in evidence_nodes:
            if node.get("id") != gap_id:
                continue
            attributes = node.get("attributes")
            if isinstance(attributes, dict) and attributes.get("competency_id"):
                competency_id = str(attributes["competency_id"])
            break

        resource_views = (
            [
                RoadmapResourceView(
                    id=str(resource["id"]),
                    title=str(resource["title"]),
                    url=str(resource["canonical_url"]),
                    provider=str(resource["source_organization"]),
                )
            ]
            if resource
            else []
        )
        return RoadmapItemView(
            id=str(raw["id"]),
            competency_id=competency_id,
            title=str(resource["title"]) if resource else "Learning action",
            description=raw.get("rationale"),
            resources=resource_views,
        )

    def create_consent(self, user_id: UUID, request: ConsentRequest) -> ConsentRecord:
        response = self._client.post(
            "/rest/v1/consent_records",
            headers={"Prefer": "return=representation"},
            json={
                "user_id": str(user_id),
                **request.model_dump(mode="json"),
            },
        )
        self._raise_for_status(response)
        payload = self._parse_single_row(response.json(), "Consent record")
        return ConsentRecord.model_validate(payload)

    def create_deletion_request(
        self,
        user_id: UUID,
        request: DeletionRequestCreate,
    ) -> DeletionRequestRecord:
        response = self._client.post(
            "/rest/v1/deletion_requests",
            headers={"Prefer": "return=representation"},
            json={
                "user_id": str(user_id),
                **request.model_dump(mode="json"),
            },
        )
        self._raise_for_status(response)
        payload = self._parse_single_row(response.json(), "Deletion request")
        return DeletionRequestRecord.model_validate(payload)

    @staticmethod
    def _parse_single_attempt(payload: Any) -> AttemptRecord:
        return AttemptRecord.model_validate(
            SupabaseAttemptRepository._parse_single_row(payload, "Attempt")
        )

    @staticmethod
    def _parse_single_row(payload: Any, label: str) -> dict[str, Any]:
        if isinstance(payload, list):
            if len(payload) != 1:
                raise SupabaseRepositoryError(404, f"{label} was not found.")
            payload = payload[0]
        if not isinstance(payload, dict):
            raise SupabaseRepositoryError(502, f"Supabase returned an invalid {label.lower()}.")
        return payload
