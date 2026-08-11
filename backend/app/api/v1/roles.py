from fastapi import APIRouter, HTTPException

from backend.app.domain.roles import (
    JDMappingRequest,
    JDMappingResult,
    RoleSummary,
    RoleTemplate,
    list_role_summaries,
    load_role_template,
    map_supplied_jd,
)

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=list[RoleSummary])
def get_role_catalog() -> list[RoleSummary]:
    return list_role_summaries()


@router.get("/{role_id}", response_model=RoleTemplate)
def get_role(role_id: str) -> RoleTemplate:
    try:
        return load_role_template(role_id.replace("-", "_"))
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/detect", response_model=JDMappingResult)
def detect_role_from_supplied_jd(request: JDMappingRequest) -> JDMappingResult:
    try:
        return map_supplied_jd(
            request.job_description,
            selected_role_id=request.selected_role_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
