from fastapi import APIRouter

from backend.app.api.v1.schemas import CapabilityResponse, HealthResponse
from backend.app.config import get_settings
from backend.app.domain.roles import list_role_templates

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="fairhireai-backend",
        version="0.2.0",
    )


@router.get("/capabilities", response_model=CapabilityResponse)
def capabilities() -> CapabilityResponse:
    settings = get_settings()
    model_status = "ready" if settings.processing_ready else "awaiting_trained_checkpoint"
    return CapabilityResponse(
        database_configured=settings.supabase_configured,
        role_catalog_ready=bool(list_role_templates()),
        external_llm="ready" if settings.gemini_configured else "not_configured",
        knowledge_embeddings="gemini-embedding-2-384",
        model_inference=model_status,
        report_generation=model_status,
        worker_execution=(
            "ready" if settings.worker_runtime_ready else "server_secret_required"
        ),
        message=(
            "The API is ready, but processing requires either a verified local worker "
            "or an explicitly declared supervised external worker."
            if not settings.processing_ready
            else (
                "The public API is connected to a separately supervised trusted worker."
                if settings.trusted_worker_available and not settings.model_ready
                else "All configured runtime capabilities are ready."
            )
        ),
    )
