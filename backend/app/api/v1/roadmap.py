from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.dependencies import authenticated_user_id
from backend.app.domain.roadmap import (
    RoadmapRequest,
    RoadmapResult,
    build_roadmap,
)

router = APIRouter(prefix="/roadmap", tags=["roadmap"])


@router.post("/plan", response_model=RoadmapResult)
def plan_roadmap(
    request: RoadmapRequest,
    _user_id: Annotated[UUID, Depends(authenticated_user_id)],
) -> RoadmapResult:
    try:
        return build_roadmap(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
