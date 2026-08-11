import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SELECTED_MODEL_MANIFEST = PROJECT_ROOT / "configs" / "fi_v2" / "selected_model.v1.json"


def _selected_model_manifest() -> dict[str, Any]:
    if not SELECTED_MODEL_MANIFEST.is_file():
        return {}
    try:
        payload = json.loads(SELECTED_MODEL_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ROLEREADY_",
        extra="ignore",
    )

    supabase_url: str | None = Field(default=None)
    supabase_publishable_key: str | None = Field(default=None)
    # Trusted backend/worker only. This must never be sent to the browser.
    supabase_secret_key: SecretStr | None = Field(default=None)
    supabase_timeout_seconds: float = Field(default=15.0, gt=0.0, le=60.0)
    gemini_api_key: SecretStr | None = Field(default=None)
    gemini_generation_model: str = Field(
        default="gemini-3.5-flash-lite",
        pattern=r"^[a-zA-Z0-9._-]+$",
    )
    gemini_embedding_model: str = Field(
        default="gemini-embedding-2",
        pattern=r"^[a-zA-Z0-9._-]+$",
    )
    gemini_embedding_dimensions: int = Field(default=384, ge=128, le=3072)
    gemini_timeout_seconds: float = Field(default=45.0, gt=0.0, le=120.0)
    gemini_max_retries: int = Field(default=3, ge=0, le=6)
    cors_allowed_origins: str = Field(
        default=(
            "http://localhost:3000,http://127.0.0.1:3000,"
            "http://localhost:5173,http://127.0.0.1:5173,"
            "https://id-preview--66420821-2ebe-4e73-b672-4dcd71e2865c.lovable.app"
        )
    )
    model_checkpoint_path: str | None = Field(default=None)
    model_run_name: str | None = Field(default=None)
    model_checkpoint_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    # Runtime overrides make a trained checkpoint portable even though its
    # frozen training config records the original machine's local paths.
    bert_model_root: str | None = Field(default=None)
    scaler_path: str | None = Field(default=None)
    openface_root: str = "D:/FairHireAI-tools/OpenFace_2.2.0_win_x64"
    whisper_model_root: str = "D:/FairHireAI-data/models/whisper"
    whisper_model: str = "small.en"
    worker_artifact_root: str = "D:/FairHireAI-data/runtime"

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_publishable_key)

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_api_key.get_secret_value())

    @property
    def worker_configured(self) -> bool:
        return bool(
            self.supabase_configured
            and self.supabase_secret_key
            and self.supabase_secret_key.get_secret_value()
        )

    @property
    def allowed_origins(self) -> list[str]:
        return [
            origin.strip().rstrip("/")
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

    @property
    def model_ready(self) -> bool:
        checkpoint_path, run_name, checkpoint_sha256 = self.selected_model
        return bool(
            checkpoint_path
            and run_name
            and checkpoint_sha256
            and Path(checkpoint_path).is_file()
        )

    @property
    def selected_model(self) -> tuple[str | None, str | None, str | None]:
        """Return explicit settings or the version-controlled selected-model manifest."""

        manifest = _selected_model_manifest()
        checkpoint_path = self.model_checkpoint_path or manifest.get("checkpoint_path")
        run_name = self.model_run_name or manifest.get("run_name")
        checkpoint_sha256 = (
            self.model_checkpoint_sha256 or manifest.get("checkpoint_sha256")
        )
        return (
            str(checkpoint_path) if checkpoint_path else None,
            str(run_name) if run_name else None,
            str(checkpoint_sha256) if checkpoint_sha256 else None,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
