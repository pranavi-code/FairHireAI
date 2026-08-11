"""Fail-closed readiness audit for the complete local FairHireAI product."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.app.config import PROJECT_ROOT, get_settings
from backend.app.domain.knowledge import load_initial_knowledge_seed
from backend.app.domain.roles import list_role_templates
from ml_service.preprocessing.pipeline import ffmpeg_executable


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    settings = get_settings()
    checkpoint_path, run_name, expected_sha = settings.selected_model
    checks: dict[str, object] = {}
    failures: list[str] = []

    checks["database_public_config"] = settings.supabase_configured
    checks["gemini_backend_config"] = settings.gemini_configured
    checks["worker_server_secret"] = settings.worker_configured
    checks["approved_role_count"] = len(list_role_templates())

    seed = load_initial_knowledge_seed()
    checks["reviewed_document_count"] = len(seed.documents)
    checks["approved_resource_count"] = len(seed.resources)

    validation_path = (
        PROJECT_ROOT / "outputs" / "knowledge" / "question_bank_validation.v1.json"
    )
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    checks["validated_question_count"] = validation.get("validated_count")
    checks["rejected_question_count"] = validation.get("rejected_count")
    if validation.get("validated_count") != validation.get("package_count"):
        failures.append("question bank is not fully validated")
    if validation.get("rejected_count") != 0:
        failures.append("question bank contains rejected packages")
    packages = validation.get("packages", [])
    if not isinstance(packages, list) or any(
        not isinstance(package, dict)
        or len(package.get("embedding", [])) != settings.gemini_embedding_dimensions
        for package in packages
    ):
        failures.append("question packages are not fully embedded")

    knowledge_path = (
        PROJECT_ROOT / "outputs" / "knowledge" / "gemini_embeddings.v1.json"
    )
    knowledge = json.loads(knowledge_path.read_text(encoding="utf-8"))
    checks["embedded_knowledge_chunks"] = len(knowledge.get("knowledge_chunks", []))
    checks["embedded_learning_resources"] = len(
        knowledge.get("learning_resources", [])
    )
    if checks["embedded_knowledge_chunks"] != len(seed.documents):
        failures.append("reviewed knowledge embeddings are incomplete")
    if checks["embedded_learning_resources"] != len(seed.resources):
        failures.append("learning-resource embeddings are incomplete")

    if not checkpoint_path or not run_name or not expected_sha:
        failures.append("selected model manifest is incomplete")
    else:
        checkpoint = Path(checkpoint_path)
        if not checkpoint.is_file():
            failures.append("selected model checkpoint is missing")
        else:
            actual_sha = _sha256(checkpoint)
            checks["selected_model_run"] = run_name
            checks["selected_model_checksum_verified"] = actual_sha == expected_sha
            if actual_sha != expected_sha:
                failures.append("selected model checkpoint checksum does not match")

    openface = Path(settings.openface_root) / "FeatureExtraction.exe"
    checks["openface_ready"] = openface.is_file()
    checks["ffmpeg_ready"] = Path(ffmpeg_executable()).is_file()
    if not checks["openface_ready"]:
        failures.append("OpenFace FeatureExtraction.exe is missing")
    if not checks["ffmpeg_ready"]:
        failures.append("FFmpeg executable is missing")

    checks["status"] = "local_artifacts_ready" if not failures else "blocked"
    checks["live_worker_status"] = (
        "ready" if settings.worker_configured else "server_secret_required"
    )
    checks["blocking_failures"] = failures
    print(json.dumps(checks, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
