from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.app.api.dependencies import authenticated_repository
from backend.app.config import Settings, get_settings
from backend.app.domain.documents import (
    MAX_DOCUMENT_BYTES,
    DocumentExtractionError,
    ExtractedDocument,
    extract_document,
    media_type_for_document,
)
from backend.app.domain.resume import ResumeEvidence, extract_resume_evidence
from backend.app.domain.roles import JDMappingResult, map_supplied_jd
from backend.app.providers.gemini import GeminiClient, GeminiProviderError
from backend.app.repositories.supabase import SupabaseAttemptRepository

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


async def _read_upload_content(upload: UploadFile) -> tuple[str, bytes]:
    try:
        content = await upload.read(MAX_DOCUMENT_BYTES + 1)
        return upload.filename or "", content
    finally:
        await upload.close()


def _document_error(exc: DocumentExtractionError) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=DocumentError(code=exc.code, message=str(exc)).model_dump(),
    )


def _extract_standard_document(filename: str, content: bytes) -> ExtractedDocument:
    try:
        return extract_document(filename, content)
    except DocumentExtractionError as exc:
        raise _document_error(exc) from exc


def _extract_job_description_document(
    filename: str,
    content: bytes,
    settings: Settings,
    *,
    external_ai_consent: bool,
) -> ExtractedDocument:
    try:
        return extract_document(filename, content)
    except DocumentExtractionError as exc:
        if exc.code not in {"no_extractable_text", "ocr_required"}:
            raise _document_error(exc) from exc
        media_type = media_type_for_document(filename, content)
        if media_type not in {"application/pdf", "image/jpeg", "image/png", "image/webp"}:
            raise _document_error(exc) from exc
        if not external_ai_consent:
            raise HTTPException(
                status_code=403,
                detail=DocumentError(
                    code="external_ai_processing_consent_required",
                    message="External AI processing consent is required before OCR.",
                ).model_dump(),
            ) from exc
        if not settings.gemini_configured:
            raise HTTPException(
                status_code=503,
                detail=DocumentError(
                    code="ocr_unavailable",
                    message=(
                        "This scanned document or image requires OCR, but the backend OCR "
                        "service is not configured. Upload a text-based PDF, DOCX, TXT, or "
                        "MD file instead."
                    ),
                ).model_dump(),
            ) from exc
        try:
            with GeminiClient(
                api_key=settings.gemini_api_key.get_secret_value(),
                generation_model=settings.gemini_generation_model,
                embedding_model=settings.gemini_embedding_model,
                embedding_dimensions=settings.gemini_embedding_dimensions,
                timeout_seconds=settings.gemini_timeout_seconds,
                max_retries=settings.gemini_max_retries,
            ) as client:
                ocr_text = client.extract_text_from_media(
                    content=content,
                    media_type=media_type,
                )
            return extract_document(filename, content, ocr_text=ocr_text)
        except DocumentExtractionError as ocr_document_error:
            raise _document_error(ocr_document_error) from ocr_document_error
        except GeminiProviderError as provider_error:
            raise HTTPException(
                status_code=provider_error.status_code,
                detail=DocumentError(
                    code="ocr_failed",
                    message=str(provider_error),
                ).model_dump(),
            ) from provider_error


@router.post("/job-description", response_model=JDExtractionResult)
async def extract_and_detect_job_description(
    file: Annotated[
        UploadFile,
        File(description="Optional JD: PDF, DOCX, TXT, MD, JPG, JPEG, PNG, or WEBP"),
    ],
    repository: Annotated[SupabaseAttemptRepository, Depends(authenticated_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    selected_role_id: Annotated[str | None, Form()] = None,
) -> JDExtractionResult:
    filename, content = await _read_upload_content(file)
    document = _extract_job_description_document(
        filename,
        content,
        settings,
        external_ai_consent=repository.consent_granted("external_ai_processing"),
    )
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
    file: Annotated[
        UploadFile,
        File(description="Resume: PDF, DOCX, TXT, MD, JPG, JPEG, PNG, or WEBP"),
    ],
    repository: Annotated[SupabaseAttemptRepository, Depends(authenticated_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ResumeExtractionResult:
    if not repository.consent_granted("resume_processing"):
        raise HTTPException(
            status_code=403,
            detail=DocumentError(
                code="resume_processing_consent_required",
                message="Resume processing consent is required before extraction.",
            ).model_dump(),
        )
    filename, content = await _read_upload_content(file)
    document = _extract_job_description_document(
        filename,
        content,
        settings,
        external_ai_consent=repository.consent_granted("external_ai_processing"),
    )
    return ResumeExtractionResult(
        document=document,
        evidence=extract_resume_evidence(document),
    )
