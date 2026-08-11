from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.app.api.dependencies import authenticated_user_id
from backend.app.domain.documents import (
    MAX_DOCUMENT_BYTES,
    DocumentExtractionError,
    ExtractedDocument,
    extract_document,
)
from backend.app.domain.resume import ResumeEvidence, extract_resume_evidence
from backend.app.domain.roles import JDMappingResult, map_supplied_jd

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentError(BaseModel):
    code: str
    message: str


class JDExtractionResult(BaseModel):
    document: ExtractedDocument
    role_mapping: JDMappingResult


class ResumeExtractionResult(BaseModel):
    document: ExtractedDocument
    evidence: ResumeEvidence


async def _read_upload(upload: UploadFile) -> ExtractedDocument:
    try:
        content = await upload.read(MAX_DOCUMENT_BYTES + 1)
        return extract_document(upload.filename or "", content)
    except DocumentExtractionError as exc:
        raise HTTPException(
            status_code=422,
            detail=DocumentError(code=exc.code, message=str(exc)).model_dump(),
        ) from exc
    finally:
        await upload.close()


@router.post("/job-description", response_model=JDExtractionResult)
async def extract_and_detect_job_description(
    file: Annotated[UploadFile, File(description="Optional JD: PDF, DOCX, TXT, or MD")],
    _user_id: Annotated[UUID, Depends(authenticated_user_id)],
    selected_role_id: Annotated[str | None, Form()] = None,
) -> JDExtractionResult:
    document = await _read_upload(file)
    if len(document.text) < 40:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "job_description_too_short",
                "message": "The extracted job description must contain at least 40 characters.",
            },
        )
    return JDExtractionResult(
        document=document,
        role_mapping=map_supplied_jd(
            document.text,
            selected_role_id=selected_role_id,
        ),
    )


@router.post("/resume", response_model=ResumeExtractionResult)
async def extract_resume(
    file: Annotated[UploadFile, File(description="Resume: PDF, DOCX, TXT, or MD")],
    _user_id: Annotated[UUID, Depends(authenticated_user_id)],
) -> ResumeExtractionResult:
    document = await _read_upload(file)
    return ResumeExtractionResult(
        document=document,
        evidence=extract_resume_evidence(document),
    )
