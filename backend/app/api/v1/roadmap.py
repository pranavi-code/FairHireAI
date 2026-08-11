from fastapi import APIRouter, HTTPException

from backend.app.domain.roadmap import (
    RoadmapRequest,
    RoadmapResult,
    build_roadmap,
)

router = APIRouter(prefix="/roadmap", tags=["roadmap"])


@router.post("/plan", response_model=RoadmapResult)
def plan_roadmap(request: RoadmapRequest) -> RoadmapResult:
    try:
        return build_roadmap(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
