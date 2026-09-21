"""Fail-closed configuration checks for each FairHireAI deployment component."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from backend.app.config import PROJECT_ROOT, SELECTED_MODEL_MANIFEST, Settings
from ml_service.preprocessing.pipeline import ffmpeg_executable


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_public_https(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
    }


def _read_frontend_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _api_checks(settings: Settings) -> dict[str, bool]:
    origins = settings.allowed_origins
    return {
        "supabase_public_configured": settings.supabase_configured,
        "gemini_backend_configured": settings.gemini_configured,
        "selected_model_metadata_ready": settings.selected_model_metadata_ready,
        "external_worker_explicitly_declared": settings.trusted_worker_available,
        "processing_queue_enabled": settings.processing_ready,
        "public_https_cors_only": bool(origins)
        and all(_is_public_https(origin) for origin in origins),
        "server_secret_absent_from_public_api": not settings.worker_configured,
    }


def _worker_checks(settings: Settings) -> dict[str, bool]:
    checkpoint_value, run_name, expected_sha = settings.selected_model
    checkpoint = Path(checkpoint_value) if checkpoint_value else None
    actual_sha = _sha256(checkpoint) if checkpoint and checkpoint.is_file() else None
    manifest = json.loads(SELECTED_MODEL_MANIFEST.read_text(encoding="utf-8"))
    training_config_path = PROJECT_ROOT / str(manifest.get("training_config_path", ""))
    training_config = (
        json.loads(training_config_path.read_text(encoding="utf-8"))
        if training_config_path.is_file()
        else {}
    )
    bert_model_root = settings.bert_model_root or training_config.get("model_name_or_path")
    scaler_path = (
        settings.scaler_path
        or manifest.get("scaler_path")
        or training_config.get("scaler_path")
    )
    return {
        "supabase_server_secret_configured": settings.worker_configured,
        "gemini_backend_configured": settings.gemini_configured,
        "selected_model_run_configured": bool(run_name),
        "checkpoint_exists": bool(checkpoint and checkpoint.is_file()),
        "checkpoint_checksum_verified": bool(expected_sha and actual_sha == expected_sha),
        "bert_model_root_exists": bool(
            bert_model_root and Path(str(bert_model_root)).is_dir()
        ),
        "standardizer_exists": bool(
            scaler_path and Path(str(scaler_path)).is_file()
        ),
        "openface_models_exist": (
            (Path(settings.openface_root) / "FeatureExtraction.exe").is_file()
            and (Path(settings.openface_root) / "model").is_dir()
        ),
        "ffmpeg_exists": Path(ffmpeg_executable()).is_file(),
    }


def _frontend_checks(path: Path) -> dict[str, bool]:
    values = _read_frontend_env(path)
    api_base = values.get("VITE_API_BASE_URL", "").rstrip("/")
    return {
        "frontend_env_exists": path.is_file(),
        "public_https_api_base": _is_public_https(api_base),
        "api_base_has_no_duplicate_version_path": not api_base.endswith("/api/v1"),
        "supabase_url_is_https": _is_public_https(values.get("VITE_SUPABASE_URL")),
        "publishable_key_present": bool(values.get("VITE_SUPABASE_PUBLISHABLE_KEY")),
        "no_server_secret_in_frontend": not any(
            key in values
            for key in (
                "ROLEREADY_SUPABASE_SECRET_KEY",
                "SUPABASE_SERVICE_ROLE_KEY",
                "ROLEREADY_GEMINI_API_KEY",
            )
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=("api", "worker", "frontend"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--frontend-env",
        type=Path,
        default=Path("frontend/.env"),
    )
    args = parser.parse_args()

    if args.component == "frontend":
        checks = _frontend_checks(args.frontend_env)
    else:
        settings = Settings(_env_file=args.env_file)
        checks = _api_checks(settings) if args.component == "api" else _worker_checks(settings)
    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "component": args.component,
        "status": "ready" if not failures else "blocked",
        "checks": checks,
        "blocking_failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
