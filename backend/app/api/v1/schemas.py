from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class CapabilityResponse(BaseModel):
    backend: Literal["ready"] = "ready"
    database_configured: bool
    role_catalog_ready: bool
    external_llm: Literal["ready", "not_configured"]
    knowledge_embeddings: Literal["gemini-embedding-2-384"]
    model_inference: Literal["ready", "awaiting_trained_checkpoint"]
    report_generation: Literal["ready", "awaiting_trained_checkpoint"]
    worker_execution: Literal["ready", "server_secret_required"]
    message: str
