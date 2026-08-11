from fastapi import APIRouter

from backend.app.domain.resume import (
    ResumeEvidence,
    ResumeEvidenceValidation,
    summarize_resume_evidence,
)

router = APIRouter(prefix="/resume-evidence", tags=["resume evidence"])


@router.post("/validate", response_model=ResumeEvidenceValidation)
def validate_resume_evidence(
    evidence: ResumeEvidence,
) -> ResumeEvidenceValidation:
    return summarize_resume_evidence(evidence)
