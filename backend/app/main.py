from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1.router import api_router
from backend.app.config import get_settings


def create_app() -> FastAPI:
    application = FastAPI(
        title="FairHireAI API",
        version="0.2.0",
        description="Evidence-backed placement-readiness platform.",
    )
    settings = get_settings()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
    )
    application.include_router(api_router, prefix="/api/v1")
    return application


app = create_app()
