from fastapi import APIRouter, HTTPException

from backend.app.domain.interviews import (
    NextQuestionRequest,
    NextQuestionResult,
    select_next_question,
)

router = APIRouter(prefix="/interviews", tags=["interviews"])


@router.post("/next-question", response_model=NextQuestionResult)
def next_question(request: NextQuestionRequest) -> NextQuestionResult:
    try:
        return select_next_question(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
