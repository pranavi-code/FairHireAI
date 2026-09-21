from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import authenticated_user_id
from backend.app.domain.resume import (
    ResumeEvidence,
    ResumeEvidenceValidation,
    summarize_resume_evidence,
)

router = APIRouter(prefix="/resume-evidence", tags=["resume evidence"])


@router.post("/validate", response_model=ResumeEvidenceValidation)
def validate_resume_evidence(
    evidence: ResumeEvidence,
    _user_id: Annotated[UUID, Depends(authenticated_user_id)],
) -> ResumeEvidenceValidation:
    return summarize_resume_evidence(evidence)
