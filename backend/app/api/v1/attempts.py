from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.dependencies import (
    supabase_repository,
    translate_repository_error,
)
from backend.app.domain.attempts import (
    AttemptCreationRequest,
    AttemptRecord,
    AttemptTransitionRequest,
)
from backend.app.domain.roles import build_assessment_profile, map_supplied_jd
from backend.app.repositories.supabase import (
    SupabaseAttemptRepository,
    SupabaseRepositoryError,
)

router = APIRouter(prefix="/attempts", tags=["attempts"])


@router.post("", response_model=AttemptRecord, status_code=201)
def create_attempt(
    request: AttemptCreationRequest,
    repository: Annotated[SupabaseAttemptRepository, Depends(supabase_repository)],
) -> AttemptRecord:
    try:
        jd = request.job_description
        if jd:
            mapping = map_supplied_jd(
                jd.extracted_job_description,
                selected_role_id=request.role_id,
            )
            if mapping.status != "detected":
                raise HTTPException(status_code=422, detail=mapping.model_dump(mode="json"))
            profile = build_assessment_profile(
                role_id=request.role_id,
                job_description=jd.extracted_job_description,
            )
        else:
            profile = build_assessment_profile(role_id=request.role_id)
        user_id = repository.authenticated_user_id()
        if jd and not jd.private_jd_storage_key.startswith(f"{user_id}/"):
            raise HTTPException(
                status_code=422,
                detail="The private JD storage key must be scoped to the authenticated user.",
            )
        return repository.create_attempt(request=request, profile=profile)
    except SupabaseRepositoryError as exc:
        raise translate_repository_error(exc) from exc
    finally:
        repository.close()


@router.get("/{attempt_id}", response_model=AttemptRecord)
def get_attempt(
    attempt_id: UUID,
    repository: Annotated[SupabaseAttemptRepository, Depends(supabase_repository)],
) -> AttemptRecord:
    try:
        return repository.get(attempt_id)
    except SupabaseRepositoryError as exc:
        raise translate_repository_error(exc) from exc
    finally:
        repository.close()


@router.post("/{attempt_id}/transitions", response_model=AttemptRecord)
def transition_attempt(
    attempt_id: UUID,
    request: AttemptTransitionRequest,
    repository: Annotated[SupabaseAttemptRepository, Depends(supabase_repository)],
) -> AttemptRecord:
    try:
        return repository.transition(attempt_id, request.next_status)
    except SupabaseRepositoryError as exc:
        raise translate_repository_error(exc) from exc
    finally:
        repository.close()
