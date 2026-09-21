import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.dependencies import supabase_repository, translate_repository_error
from backend.app.config import get_settings
from backend.app.domain.attempts import AttemptRecord
from backend.app.domain.interviews import (
    CompetencyProgress,
    NextQuestionRequest,
    select_next_question,
)
from backend.app.domain.journey import (
    AnswerRecord,
    AnswerSubmissionRequest,
    AttemptReport,
    ModelUnavailableDetail,
    NextPersistedQuestion,
    ProcessingJobView,
    ProcessingStartResult,
    ProgressView,
    ResumeAttachmentRequest,
    ResumeAttachmentResult,
)
from backend.app.providers.gemini import GeminiClient, GeminiProviderError
from backend.app.repositories.supabase import (
    SupabaseAttemptRepository,
    SupabaseRepositoryError,
)
from backend.app.services.adaptive_question_generation import (
    AdaptiveQuestionGenerationService,
    QuestionGenerationExhaustedError,
)
from backend.app.services.grounded_questions import (
    GroundedQuestionService,
    PersonalizedQuestionRequest,
)
from backend.app.services.hybrid_rag import (
    HybridRagService,
    RetrievedQuestion,
    question_package_from_database_row,
    selection_from_package,
)

router = APIRouter(tags=["student journey"])
logger = logging.getLogger(__name__)


@router.get("/attempts", response_model=list[AttemptRecord])
def list_attempts(
    repository: Annotated[SupabaseAttemptRepository, Depends(supabase_repository)],
) -> list[AttemptRecord]:
    try:
        return repository.list_attempts()
    except SupabaseRepositoryError as exc:
        raise translate_repository_error(exc) from exc
    finally:
        repository.close()


@router.post(
    "/attempts/{attempt_id}/resume",
    response_model=ResumeAttachmentResult,
    status_code=201,
)
def attach_resume(
    attempt_id: UUID,
    request: ResumeAttachmentRequest,
    repository: Annotated[SupabaseAttemptRepository, Depends(supabase_repository)],
) -> ResumeAttachmentResult:
    try:
        user_id = repository.authenticated_user_id()
        if not repository.consent_granted("resume_processing", attempt_id):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "resume_processing_consent_required",
                    "message": "Resume processing consent is required before attaching a resume.",
                },
            )
        if not request.private_resume_storage_key.startswith(f"{user_id}/"):
            raise HTTPException(
                status_code=422,
                detail="The private resume storage key must be scoped to the authenticated user.",
            )
        return repository.attach_resume(attempt_id, request)
    except SupabaseRepositoryError as exc:
        raise translate_repository_error(exc) from exc
    finally:
        repository.close()


@router.get(
    "/attempts/{attempt_id}/next-question",
    response_model=NextPersistedQuestion,
)
def next_persisted_question(
    attempt_id: UUID,
    repository: Annotated[SupabaseAttemptRepository, Depends(supabase_repository)],
) -> NextPersistedQuestion:
    try:
        attempt = repository.get(attempt_id)
        if attempt.status == "completed":
            return NextPersistedQuestion(
                question=None,
                awaiting_answer=False,
                message="The evidence-backed assessment is complete.",
            )
        questions = repository.list_questions(attempt_id)
        current_competency_id: str | None = None
        latest_evaluation: dict[str, object] | None = None
        latest_answer_excerpt: str | None = None
        latest_question_prompt: str | None = None
        if questions:
            latest = questions[-1]
            answer = repository.answer_for_question(latest.id)
            if answer is None:
                return NextPersistedQuestion(
                    question=latest,
                    awaiting_answer=True,
                    message="Answer this persisted approved question before requesting another.",
                )
            current_competency_id = latest.competency_id
            answered_by_question = {
                question.id: repository.answer_for_question(question.id)
                for question in questions
            }
            progress_by_competency: dict[str, CompetencyProgress] = {}
            for question in questions:
                if answered_by_question[question.id] is None:
                    continue
                progress = progress_by_competency.setdefault(
                    question.competency_id,
                    CompetencyProgress(competency_id=question.competency_id),
                )
                if question.is_follow_up:
                    progress.follow_up_used = True
                else:
                    progress.core_answered = True
                answer_record = answered_by_question[question.id]
                if answer_record is None:
                    continue
                analysis = repository.analysis_for_answer(answer_record.id)
                if analysis is None:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "answer_evaluation_pending",
                            "message": (
                                "Process the submitted answer before the bounded "
                                "selector chooses the next question."
                            ),
                        },
                    )
                evaluation = analysis.get("technical_evaluation")
                if not isinstance(evaluation, dict):
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "answer_evaluation_invalid",
                            "message": "The persisted answer evaluation is invalid.",
                        },
                    )
                progress.competency_coverage = float(
                    evaluation["competency_coverage"]
                )
                progress.rubric_match = float(
                    evaluation["competency_rubric_score"]
                )
                progress.answer_completeness = float(
                    evaluation["answer_completeness"]
                )
                progress.evidence_confidence = float(
                    evaluation["evidence_confidence"]
                )
                progress.high_confidence_resume_contradiction = bool(
                    evaluation.get("high_confidence_resume_contradiction", False)
                )
                progress.weakest_criterion = evaluation.get("weakest_criterion")
                if question.id == latest.id:
                    latest_evaluation = evaluation
                    latest_question_prompt = question.prompt_snapshot
                    transcript_text = analysis.get("transcript_text")
                    if isinstance(transcript_text, str) and transcript_text.strip():
                        latest_answer_excerpt = transcript_text.strip()[:4_000]
        else:
            progress_by_competency = {}
        selection = select_next_question(
            NextQuestionRequest(
                attempt_id=attempt.id,
                role_id=attempt.role_id,
                role_template_version=attempt.role_template_version,
                competency_weights=attempt.competency_weights,
                progress=list(progress_by_competency.values()),
                current_competency_id=current_competency_id,
                answered_question_ids=[
                    question.question_template_id for question in questions
                ],
            )
        )
        if selection.action == "complete":
            return NextPersistedQuestion(
                question=None,
                awaiting_answer=False,
                message="The bounded adaptive interview is complete.",
            )
        package = repository.validated_question_package(
            role_id=attempt.role_id,
            competency_id=selection.competency_id or "",
            question_template_id=selection.question_id or "",
        )
        if package is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "validated_question_package_required",
                    "message": (
                        "A source-grounded validated question package is required. "
                        "No static or unreviewed question was substituted."
                    ),
                },
            )
        try:
            package_model = question_package_from_database_row(package)
            selection = selection_from_package(
                selection,
                package_model,
                retrieval_note="Exact approved-corpus fallback",
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "validated_question_package_invalid",
                    "message": str(exc),
                },
            ) from exc
        settings = get_settings()
        external_ai_consent = repository.external_ai_consent(attempt_id)
        if not external_ai_consent:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "external_ai_processing_consent_required",
                    "message": (
                        "External AI processing consent is required for the adaptive "
                        "Gemini interview. No fixed question was substituted."
                    ),
                },
            )
        if not settings.gemini_configured or settings.gemini_api_key is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "dynamic_interview_unavailable",
                    "message": (
                        "Gemini is required for adaptive interview questions and is not configured."
                    ),
                },
            )

        context = repository.question_personalization_context(attempt_id)
        try:
            recent_history = repository.recent_same_role_questions(
                role_id=attempt.role_id,
                competency_id=selection.competency_id or "",
                exclude_attempt_id=attempt_id,
            )
        except SupabaseRepositoryError as exc:
            if exc.status_code not in {502, 503, 504}:
                raise
            # Cross-attempt history improves diversity but is not required to safely
            # continue the current interview. Current-attempt prompts remain enforced.
            logger.warning(
                "Recent same-role question history unavailable; continuing with current "
                "attempt history only: role=%s status=%s",
                attempt.role_id,
                exc.status_code,
            )
            recent_history = []
        competency_id = selection.competency_id or ""
        current_history = [
            question for question in questions if question.competency_id == competency_id
        ]
        anchor_history = [*recent_history, *current_history]
        delivered_history = [*recent_history[:24], *current_history]
        if selection.is_follow_up and questions:
            delivered_history = [
                question for question in delivered_history if question.id != questions[-1].id
            ]
        delivered_history = delivered_history[-36:]
        recent_prompts = [question.prompt_snapshot for question in delivered_history]
        recent_question_ids = [str(question.id) for question in delivered_history]
        used_anchor_ids = {
            question.question_package_id
            for question in anchor_history
            if question.question_package_id
        }
        try:
            with GeminiClient(
                api_key=settings.gemini_api_key.get_secret_value(),
                generation_model=settings.gemini_generation_model,
                embedding_model=settings.gemini_embedding_model,
                embedding_dimensions=settings.gemini_embedding_dimensions,
                timeout_seconds=settings.gemini_timeout_seconds,
                max_retries=settings.gemini_max_retries,
            ) as client:
                retrieved_anchors = HybridRagService(client).retrieve_question_candidates(
                    repository,
                    role_id=attempt.role_id,
                    competency_id=competency_id,
                    selection=selection,
                    personalization_context=context,
                    deprioritized_package_ids=used_anchor_ids,
                )
                if not any(
                    item.package_model.question_id == package_model.question_id
                    for item in retrieved_anchors
                ):
                    retrieved_anchors.append(
                        RetrievedQuestion(
                            package=package,
                            package_model=package_model,
                            selection=selection,
                            query="approved role-template anchor",
                            hybrid_score=-1.0,
                        )
                    )
                question_request = PersonalizedQuestionRequest(
                    role_id=attempt.role_id,
                    competency_id=selection.competency_id or "",
                    **context,
                    recent_question_prompts=recent_prompts,
                    recent_question_ids=recent_question_ids,
                    previous_question=latest_question_prompt,
                    previous_answer_excerpt=latest_answer_excerpt,
                    missing_concepts=(
                        [str(item) for item in latest_evaluation.get("missing_concepts", [])]
                        if latest_evaluation
                        and isinstance(latest_evaluation.get("missing_concepts"), list)
                        else []
                    ),
                    weakest_criterion=(
                        str(latest_evaluation["weakest_criterion"])
                        if latest_evaluation and latest_evaluation.get("weakest_criterion")
                        else None
                    ),
                    is_follow_up=selection.is_follow_up,
                    difficulty="beginner",
                    external_ai_processing_consent=True,
                )
                generation = AdaptiveQuestionGenerationService(
                    GroundedQuestionService(client)
                ).generate(
                    question_request,
                    anchors=retrieved_anchors,
                    correlation_id=str(attempt_id),
                )
                generated = generation.generated
                package = generation.anchor.package
                selection = generation.anchor.selection
        except GeminiProviderError as exc:
            logger.warning(
                "Dynamic question provider failure: role=%s competency=%s "
                "follow_up=%s status=%s retryable=%s reason=%s",
                attempt.role_id,
                selection.competency_id,
                selection.is_follow_up,
                exc.status_code,
                exc.retryable,
                str(exc),
            )
            if exc.status_code == 429:
                error_code = "gemini_rate_limited"
                error_message = (
                    "Gemini is temporarily rate-limited. Wait briefly, then request the next "
                    "question again."
                )
            elif exc.retryable:
                error_code = "gemini_temporarily_unavailable"
                error_message = (
                    "Gemini could not be reached after bounded retries. Check the internet "
                    "connection and try again."
                )
            else:
                error_code = "dynamic_question_generation_failed"
                error_message = (
                    "Gemini rejected the question-generation request. Check the configured "
                    "Gemini model and API key."
                )
            raise HTTPException(
                status_code=503,
                detail={
                    "code": error_code,
                    "message": error_message,
                },
            ) from exc
        except QuestionGenerationExhaustedError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "dynamic_question_generation_exhausted",
                    "message": (
                        "The dynamic generator could not produce a validated question after "
                        "progressive anchor, scenario, structure, rubric, and fallback recovery."
                    ),
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "hybrid_rag_integrity_failed", "message": str(exc)},
            ) from exc

        selection = selection.model_copy(
            update={
                "question_id": generated.question_id,
                "prompt": generated.prompt,
                "reason": (
                    f"{selection.reason} Gemini generated and independently validated an "
                    "answer-adaptive, history-aware question from the retrieved RAG anchor."
                ),
            }
        )
        question = repository.persist_question(
            attempt_id,
            selection,
            question_package=package,
            prompt_override=generated.prompt,
            model_id=generated.model_id,
            prompt_version=generated.prompt_version,
        )
        if attempt.status == "role_confirmed":
            repository.transition(attempt_id, "interviewing")
        return NextPersistedQuestion(
            question=question,
            awaiting_answer=True,
            message="A new grounded Gemini-RAG adaptive question is ready.",
        )
    except SupabaseRepositoryError as exc:
        raise translate_repository_error(exc) from exc
    finally:
        repository.close()


@router.post(
    "/attempts/{attempt_id}/answers",
    response_model=AnswerRecord,
    status_code=201,
)
def submit_answer(
    attempt_id: UUID,
    request: AnswerSubmissionRequest,
    repository: Annotated[SupabaseAttemptRepository, Depends(supabase_repository)],
) -> AnswerRecord:
    try:
        user_id = repository.authenticated_user_id()
        if not repository.consent_granted("interview_recording", attempt_id):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "interview_recording_consent_required",
                    "message": "Interview recording consent is required before submitting video.",
                },
            )
        if not request.private_video_storage_key.startswith(f"{user_id}/"):
            raise HTTPException(
                status_code=422,
                detail="The private video storage key must be scoped to the authenticated user.",
            )
        return repository.submit_answer(attempt_id, request)
    except SupabaseRepositoryError as exc:
        raise translate_repository_error(exc) from exc
    finally:
        repository.close()


@router.post(
    "/attempts/{attempt_id}/process",
    response_model=ProcessingStartResult,
    status_code=202,
)
def start_processing(
    attempt_id: UUID,
    repository: Annotated[SupabaseAttemptRepository, Depends(supabase_repository)],
) -> ProcessingStartResult:
    settings = get_settings()
    if not settings.processing_ready:
        repository.close()
        raise HTTPException(
            status_code=409,
            detail=ModelUnavailableDetail(
                message=(
                    "A verified local worker or explicitly declared supervised "
                    "external worker is required before answer processing can start."
                )
            ).model_dump(),
        )
    try:
        if not repository.external_ai_consent(attempt_id):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "external_ai_processing_consent_required",
                    "message": "External AI processing consent is required before evaluation.",
                },
            )
        return repository.enqueue_processing(attempt_id)
    except SupabaseRepositoryError as exc:
        raise translate_repository_error(exc) from exc
    finally:
        repository.close()


@router.post(
    "/attempts/{attempt_id}/finish",
    response_model=ProcessingStartResult,
    status_code=202,
)
def finish_interview(
    attempt_id: UUID,
    repository: Annotated[SupabaseAttemptRepository, Depends(supabase_repository)],
) -> ProcessingStartResult:
    """Submit an adaptive interview after at least six fully evaluated answers."""

    settings = get_settings()
    if not settings.processing_ready:
        repository.close()
        raise HTTPException(status_code=503, detail="The trusted report worker is unavailable.")
    try:
        # The database RPC repeats ownership, consent, answer-count, retry,
        # and state validation atomically under this caller's Supabase JWT.
        repository.get(attempt_id)
        if not repository.external_ai_consent(attempt_id):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "external_ai_processing_consent_required",
                    "message": "External AI processing consent is required before reporting.",
                },
            )
        return repository.request_report_generation(attempt_id)
    except SupabaseRepositoryError as exc:
        raise translate_repository_error(exc) from exc
    finally:
        repository.close()


@router.get(
    "/attempts/{attempt_id}/jobs",
    response_model=list[ProcessingJobView],
)
def get_jobs(
    attempt_id: UUID,
    repository: Annotated[SupabaseAttemptRepository, Depends(supabase_repository)],
) -> list[ProcessingJobView]:
    try:
        repository.get(attempt_id)
        return repository.list_jobs(attempt_id)
    except SupabaseRepositoryError as exc:
        raise translate_repository_error(exc) from exc
    finally:
        repository.close()


@router.get("/attempts/{attempt_id}/report", response_model=AttemptReport)
def get_report(
    attempt_id: UUID,
    repository: Annotated[SupabaseAttemptRepository, Depends(supabase_repository)],
) -> AttemptReport:
    try:
        return repository.report(attempt_id)
    except SupabaseRepositoryError as exc:
        raise translate_repository_error(exc) from exc
    finally:
        repository.close()


@router.post(
    "/attempts/{attempt_id}/reattempt",
    response_model=AttemptRecord,
    status_code=201,
)
def create_reattempt(
    attempt_id: UUID,
    repository: Annotated[SupabaseAttemptRepository, Depends(supabase_repository)],
) -> AttemptRecord:
    try:
        return repository.reattempt(attempt_id)
    except SupabaseRepositoryError as exc:
        raise translate_repository_error(exc) from exc
    finally:
        repository.close()


@router.get("/progress", response_model=ProgressView)
def get_progress(
    repository: Annotated[SupabaseAttemptRepository, Depends(supabase_repository)],
) -> ProgressView:
    try:
        return repository.progress()
    except SupabaseRepositoryError as exc:
        raise translate_repository_error(exc) from exc
    finally:
        repository.close()
