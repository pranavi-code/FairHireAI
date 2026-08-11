"""Resumably validate every team-authored question against reviewed sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.config import get_settings
from backend.app.domain.knowledge import (
    build_seed_question_packages,
    load_initial_knowledge_seed,
)
from backend.app.providers.gemini import GeminiClient
from backend.app.services.grounded_questions import GroundedQuestionService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/knowledge/question_bank_validation.v1.json"),
    )
    return parser.parse_args()


def _load_completed(path: Path) -> dict[str, dict[str, object]]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    packages = payload.get("packages") if isinstance(payload, dict) else None
    if not isinstance(packages, list):
        return {}
    return {
        str(item["id"]): item
        for item in packages
        if isinstance(item, dict) and item.get("id")
    }


def _write(
    path: Path,
    packages: dict[str, dict[str, object]],
    sources: list[dict[str, object]],
    *,
    model: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "validated-question-bank-v1",
        "model": model,
        "package_count": len(packages),
        "validated_count": sum(
            item.get("validation_status") == "generated_validated_for_practice"
            for item in packages.values()
        ),
        "rejected_count": sum(
            item.get("validation_status") == "rejected"
            for item in packages.values()
        ),
        "packages": [packages[key] for key in sorted(packages)],
        "package_sources": sources,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    args = parse_args()
    settings = get_settings()
    if not settings.gemini_configured or settings.gemini_api_key is None:
        raise RuntimeError("ROLEREADY_GEMINI_API_KEY is required")
    drafts = build_seed_question_packages()
    completed = _load_completed(args.output)
    seed = load_initial_knowledge_seed()
    document_by_source_and_competency = {
        (document.source_id, competency_id): document.document_id
        for document in seed.documents
        for competency_id in document.competency_ids
    }
    package_sources: list[dict[str, object]] = []
    with GeminiClient(
        api_key=settings.gemini_api_key.get_secret_value(),
        generation_model=settings.gemini_generation_model,
        embedding_model=settings.gemini_embedding_model,
        embedding_dimensions=settings.gemini_embedding_dimensions,
        timeout_seconds=settings.gemini_timeout_seconds,
        max_retries=settings.gemini_max_retries,
    ) as client:
        service = GroundedQuestionService(client)
        for index, package in enumerate(drafts, start=1):
            for source_id, concepts in package.source_to_concept_mapping.items():
                document_id = document_by_source_and_competency[
                    (source_id, package.competency_id)
                ]
                package_sources.append(
                    {
                        "question_package_id": package.question_id,
                        "source_document_id": document_id,
                        "supported_concepts": concepts,
                    }
                )
            existing_passed = (
                package.question_id in completed
                and completed[package.question_id].get("validation_status")
                == "generated_validated_for_practice"
            )
            existing_embedding = (
                completed.get(package.question_id, {}).get("embedding")
                if existing_passed
                else None
            )
            if existing_passed and isinstance(existing_embedding, list):
                print(f"[{index}/{len(drafts)}] existing {package.question_id}", flush=True)
                continue
            if existing_passed:
                print(f"[{index}/{len(drafts)}] embedding {package.question_id}", flush=True)
                row = completed[package.question_id]
            else:
                print(f"[{index}/{len(drafts)}] validating {package.question_id}", flush=True)
                report = service.validate_team_package(package)
                row = package.model_dump(mode="json")
                row["id"] = row.pop("question_id")
                row["validation_status"] = (
                    "generated_validated_for_practice" if report.passed else "rejected"
                )
                row["automatic_validation"] = {
                    "schema_valid": True,
                    "source_ids_registered": True,
                    "deterministic_fairness_check": True,
                    "grounded_semantic_validation": report.model_dump(mode="json"),
                    "retrievable": report.passed,
                    "validator_model": settings.gemini_generation_model,
                }
            if row["validation_status"] == "generated_validated_for_practice":
                row["embedding"] = client.embed(
                    (
                        f"{row['prompt']}\n"
                        f"{' | '.join(str(item) for item in row['expected_concepts'])}\n"
                        f"{row['reference_explanation']}"
                    ),
                    task_type="RETRIEVAL_DOCUMENT",
                )
                row["embedding_model"] = settings.gemini_embedding_model
            completed[str(row["id"])] = row
            _write(
                args.output,
                completed,
                package_sources,
                model=settings.gemini_generation_model,
            )
    _write(
        args.output,
        completed,
        package_sources,
        model=settings.gemini_generation_model,
    )
    passed = sum(
        item["validation_status"] == "generated_validated_for_practice"
        for item in completed.values()
    )
    print(f"QUESTION BANK VALIDATION COMPLETE: {passed}/{len(drafts)} passed")


if __name__ == "__main__":
    main()
