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
from backend.app.services.grounded_questions import (
    GroundedQuestionService,
    PersonalizedQuestionRequest,
)

router = APIRouter(tags=["student journey"])


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
        prompt_override: str | None = None
        model_id: str | None = None
        prompt_version: str | None = None
        settings = get_settings()
        if (
            not selection.is_follow_up
            and repository.external_ai_consent(attempt_id)
            and settings.gemini_configured
            and settings.gemini_api_key is not None
        ):
            context = repository.question_personalization_context(attempt_id)
            try:
                with GeminiClient(
                    api_key=settings.gemini_api_key.get_secret_value(),
                    generation_model=settings.gemini_generation_model,
                    embedding_model=settings.gemini_embedding_model,
                    embedding_dimensions=settings.gemini_embedding_dimensions,
                    timeout_seconds=settings.gemini_timeout_seconds,
                    max_retries=settings.gemini_max_retries,
                ) as client:
                    generated = GroundedQuestionService(client).generate(
                        PersonalizedQuestionRequest(
                            role_id=attempt.role_id,
                            competency_id=selection.competency_id or "",
                            **context,
                            difficulty="beginner",
                            external_ai_processing_consent=True,
                        )
                    )
                if generated.validation_status == "generated_validated_for_practice":
                    prompt_override = generated.prompt
                    model_id = generated.model_id
                    prompt_version = generated.prompt_version
            except (GeminiProviderError, ValueError):
                prompt_override = None
        question = repository.persist_question(
            attempt_id,
            selection,
            question_package=package,
            prompt_override=prompt_override,
            model_id=model_id,
            prompt_version=prompt_version,
        )
        if attempt.status == "role_confirmed":
            repository.transition(attempt_id, "interviewing")
        return NextPersistedQuestion(
            question=question,
            awaiting_answer=True,
            message="The first approved core question is ready.",
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
    if not settings.model_ready:
        repository.close()
        raise HTTPException(
            status_code=409,
            detail=ModelUnavailableDetail(
                message=(
                    "A verified trained checkpoint is required before answer "
                    "processing and evidence-backed scoring can start."
                )
            ).model_dump(),
        )
    try:
        return repository.enqueue_processing(attempt_id)
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
