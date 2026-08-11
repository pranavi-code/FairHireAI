from fastapi import APIRouter, HTTPException

from backend.app.domain.evidence_graph import (
    EvidenceGraph,
    ScorecardRequest,
    ScorecardResult,
    calculate_scorecard,
)

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.post("/validate", response_model=EvidenceGraph)
def validate_graph(graph: EvidenceGraph) -> EvidenceGraph:
    return graph


@router.post("/scorecard", response_model=ScorecardResult)
def scorecard(request: ScorecardRequest) -> ScorecardResult:
    try:
        return calculate_scorecard(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
