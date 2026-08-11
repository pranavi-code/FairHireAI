from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.dependencies import (
    authenticated_user_id,
    supabase_repository,
    translate_repository_error,
)
from backend.app.config import Settings, get_settings
from backend.app.domain.knowledge import (
    QuestionPackage,
    QuestionSearchRequest,
    QuestionSearchResult,
    ResourceSearchRequest,
    ResourceSearchResult,
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

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("/questions/generate", response_model=QuestionPackage)
def generate_question(
    request: PersonalizedQuestionRequest,
    _user_id: Annotated[UUID, Depends(authenticated_user_id)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> QuestionPackage:
    if not settings.gemini_configured or settings.gemini_api_key is None:
        raise HTTPException(status_code=503, detail="Gemini is not configured.")
    try:
        with GeminiClient(
            api_key=settings.gemini_api_key.get_secret_value(),
            generation_model=settings.gemini_generation_model,
            embedding_model=settings.gemini_embedding_model,
            embedding_dimensions=settings.gemini_embedding_dimensions,
            timeout_seconds=settings.gemini_timeout_seconds,
            max_retries=settings.gemini_max_retries,
        ) as client:
            return GroundedQuestionService(client).generate(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GeminiProviderError as exc:
        status = exc.status_code if exc.status_code in {400, 401, 403, 429} else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post("/questions/search", response_model=list[QuestionSearchResult])
def search_questions(
    request: QuestionSearchRequest,
    repository: Annotated[SupabaseAttemptRepository, Depends(supabase_repository)],
) -> list[QuestionSearchResult]:
    try:
        return repository.search_question_packages(request)
    except SupabaseRepositoryError as exc:
        raise translate_repository_error(exc) from exc
    finally:
        repository.close()


@router.post("/resources/search", response_model=list[ResourceSearchResult])
def search_resources(
    request: ResourceSearchRequest,
    repository: Annotated[SupabaseAttemptRepository, Depends(supabase_repository)],
) -> list[ResourceSearchResult]:
    try:
        return repository.search_learning_resources(request)
    except SupabaseRepositoryError as exc:
        raise translate_repository_error(exc) from exc
    finally:
        repository.close()
