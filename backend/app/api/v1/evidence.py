from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.dependencies import authenticated_user_id
from backend.app.domain.evidence_graph import (
    EvidenceGraph,
    ScorecardRequest,
    ScorecardResult,
    calculate_scorecard,
)

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.post("/validate", response_model=EvidenceGraph)
def validate_graph(
    graph: EvidenceGraph,
    _user_id: Annotated[UUID, Depends(authenticated_user_id)],
) -> EvidenceGraph:
    return graph


@router.post("/scorecard", response_model=ScorecardResult)
def scorecard(
    request: ScorecardRequest,
    _user_id: Annotated[UUID, Depends(authenticated_user_id)],
) -> ScorecardResult:
    try:
        return calculate_scorecard(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
