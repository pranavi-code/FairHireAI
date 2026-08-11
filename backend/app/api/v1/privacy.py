from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import (
    supabase_repository,
    translate_repository_error,
)
from backend.app.domain.privacy import (
    ConsentRecord,
    ConsentRequest,
    DeletionRequestCreate,
    DeletionRequestRecord,
)
from backend.app.repositories.supabase import (
    SupabaseAttemptRepository,
    SupabaseRepositoryError,
)

router = APIRouter(prefix="/privacy", tags=["privacy"])


@router.post("/consents", response_model=ConsentRecord, status_code=201)
def record_consent(
    request: ConsentRequest,
    repository: Annotated[SupabaseAttemptRepository, Depends(supabase_repository)],
) -> ConsentRecord:
    try:
        user_id = repository.authenticated_user_id()
        return repository.create_consent(user_id, request)
    except SupabaseRepositoryError as exc:
        raise translate_repository_error(exc) from exc
    finally:
        repository.close()


@router.post("/deletion-requests", response_model=DeletionRequestRecord, status_code=202)
def request_deletion(
    request: DeletionRequestCreate,
    repository: Annotated[SupabaseAttemptRepository, Depends(supabase_repository)],
) -> DeletionRequestRecord:
    try:
        user_id = repository.authenticated_user_id()
        return repository.create_deletion_request(user_id, request)
    except SupabaseRepositoryError as exc:
        raise translate_repository_error(exc) from exc
    finally:
        repository.close()
