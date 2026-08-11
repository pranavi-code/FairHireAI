from fastapi import APIRouter

from backend.app.api.v1.attempts import router as attempts_router
from backend.app.api.v1.documents import router as documents_router
from backend.app.api.v1.evidence import router as evidence_router
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.interviews import router as interviews_router
from backend.app.api.v1.journey import router as journey_router
from backend.app.api.v1.knowledge import router as knowledge_router
from backend.app.api.v1.privacy import router as privacy_router
from backend.app.api.v1.resume import router as resume_router
from backend.app.api.v1.roadmap import router as roadmap_router
from backend.app.api.v1.roles import router as roles_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(documents_router)
api_router.include_router(attempts_router)
api_router.include_router(journey_router)
api_router.include_router(privacy_router)
api_router.include_router(roles_router)
api_router.include_router(resume_router)
api_router.include_router(interviews_router)
api_router.include_router(knowledge_router)
api_router.include_router(evidence_router)
api_router.include_router(roadmap_router)
