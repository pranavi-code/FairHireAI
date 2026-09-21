from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.dependencies import authenticated_user_id
from backend.app.domain.interviews import (
    NextQuestionRequest,
    NextQuestionResult,
    select_next_question,
)

router = APIRouter(prefix="/interviews", tags=["interviews"])


@router.post("/next-question", response_model=NextQuestionResult)
def next_question(
    request: NextQuestionRequest,
    _user_id: Annotated[UUID, Depends(authenticated_user_id)],
) -> NextQuestionResult:
    try:
        return select_next_question(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
