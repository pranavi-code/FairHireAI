from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.config import Settings, get_settings
from backend.app.repositories.supabase import (
    SupabaseAttemptRepository,
    SupabaseRepositoryError,
)

bearer = HTTPBearer(auto_error=False)


def supabase_repository(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SupabaseAttemptRepository:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(status_code=401, detail="A Supabase user access token is required.")
    if not settings.supabase_configured:
        raise HTTPException(status_code=503, detail="Supabase is not configured.")
    return SupabaseAttemptRepository(
        base_url=settings.supabase_url or "",
        publishable_key=settings.supabase_publishable_key or "",
        access_token=credentials.credentials,
        timeout_seconds=settings.supabase_timeout_seconds,
    )


def translate_repository_error(exc: SupabaseRepositoryError) -> HTTPException:
    status = exc.status_code if exc.status_code in {400, 401, 403, 404, 409, 422} else 502
    return HTTPException(status_code=status, detail=str(exc))


def authenticated_user_id(
    repository: Annotated[SupabaseAttemptRepository, Depends(supabase_repository)],
) -> UUID:
    try:
        return repository.authenticated_user_id()
    except SupabaseRepositoryError as exc:
        raise translate_repository_error(exc) from exc
    finally:
        repository.close()
