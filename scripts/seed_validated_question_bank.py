"""Publish independently validated, embedded question packages to Supabase."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import httpx

from backend.app.domain.knowledge import (
    load_initial_knowledge_seed,
    resolve_source_document_id,
)

VALIDATED_STATUS = "generated_validated_for_practice"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("outputs/knowledge/question_bank_validation.v1.json"),
    )
    parser.add_argument("--supabase-url", default=os.getenv("ROLEREADY_SUPABASE_URL"))
    parser.add_argument(
        "--secret-key",
        default=os.getenv("ROLEREADY_SUPABASE_SECRET_KEY"),
        help="Server-only Supabase secret/service key. Never expose it to Vite.",
    )
    return parser.parse_args()


def _upsert(
    client: httpx.Client,
    table: str,
    rows: list[dict[str, object]],
    *,
    conflict: str,
) -> None:
    if not rows:
        return
    response = client.post(
        f"/rest/v1/{table}",
        params={"on_conflict": conflict},
        headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        json=rows,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or len(payload) != len(rows):
        raise RuntimeError(f"Supabase returned an incomplete {table} upsert")


def _load_validated_packages(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    packages = payload.get("packages")
    if (
        payload.get("schema_version") != "validated-question-bank-v1"
        or not isinstance(packages, list)
        or not packages
    ):
        raise RuntimeError("Question-bank validation artifact is missing or invalid")
    if payload.get("rejected_count") != 0 or payload.get("validated_count") != len(packages):
        raise RuntimeError("Refusing to publish a partially validated question bank")
    for package in packages:
        if not isinstance(package, dict):
            raise RuntimeError("Question package must be an object")
        vector = package.get("embedding")
        if (
            package.get("validation_status") != VALIDATED_STATUS
            or not isinstance(vector, list)
            or len(vector) != 384
            or not package.get("embedding_model")
        ):
            raise RuntimeError(
                f"Package {package.get('package_key')} is not validated and embedded"
            )
    return packages


def _package_row(package: dict[str, Any]) -> dict[str, object]:
    allowed = {
        "id",
        "package_key",
        "version",
        "role_id",
        "competency_id",
        "skill_concept_ids",
        "seniority",
        "difficulty",
        "question_type",
        "prompt",
        "expected_concepts",
        "rubric",
        "follow_ups",
        "reference_explanation",
        "source_to_concept_mapping",
        "author_type",
        "model_id",
        "prompt_version",
        "validation_status",
        "automatic_validation",
        "reviewer_id",
        "embedding",
        "embedding_model",
    }
    return {key: value for key, value in package.items() if key in allowed}


def main() -> None:
    args = parse_args()
    if not args.supabase_url or not args.secret_key:
        raise RuntimeError(
            "ROLEREADY_SUPABASE_URL and ROLEREADY_SUPABASE_SECRET_KEY are required"
        )
    packages = _load_validated_packages(args.input)
    seed = load_initial_knowledge_seed()
    package_rows = [_package_row(package) for package in packages]
    source_rows = [
        {
            "question_package_id": package["id"],
            "source_document_id": resolve_source_document_id(
                source_id,
                str(package["competency_id"]),
                concepts=[str(concept) for concept in concepts],
                seed=seed,
            ),
            "supported_concepts": concepts,
        }
        for package in packages
        for source_id, concepts in package["source_to_concept_mapping"].items()
    ]
    with httpx.Client(
        base_url=str(args.supabase_url).rstrip("/"),
        headers={
            "apikey": args.secret_key,
            "Authorization": f"Bearer {args.secret_key}",
            "Content-Type": "application/json",
        },
        timeout=60.0,
    ) as client:
        _upsert(client, "question_packages", package_rows, conflict="package_key,version")
        _upsert(
            client,
            "question_package_sources",
            source_rows,
            conflict="question_package_id,source_document_id",
        )
    print(
        "VALIDATED QUESTION BANK PUBLISHED: "
        f"{len(package_rows)} packages, {len(source_rows)} source mappings"
    )


if __name__ == "__main__":
    main()
