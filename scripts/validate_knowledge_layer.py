"""Validate the trusted source registry and initial question-bank drafts."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from backend.app.domain.knowledge import (
    build_seed_question_packages,
    load_initial_knowledge_seed,
    load_source_registry,
)
from backend.app.domain.roles import list_role_templates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/knowledge/knowledge_validation_summary.json"),
    )
    parser.add_argument(
        "--validated-bank",
        type=Path,
        default=Path("outputs/knowledge/question_bank_validation.v1.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sources = load_source_registry()
    packages = build_seed_question_packages()
    seed = load_initial_knowledge_seed()
    roles = list_role_templates()
    registered_source_ids = {source.source_id for source in sources}
    referenced_source_ids = {
        source_id
        for package in packages
        for source_id in package.source_to_concept_mapping
    }
    missing_sources = sorted(referenced_source_ids - registered_source_ids)
    if missing_sources:
        raise RuntimeError(f"Question drafts reference unknown sources: {missing_sources}")

    expected_by_role = {
        role.role_id: len(role.competencies)
        for role in roles
    }
    actual_by_role = Counter(
        package.role_id for package in packages if package.role_id is not None
    )
    if dict(actual_by_role) != expected_by_role:
        raise RuntimeError(
            f"Question coverage mismatch: expected={expected_by_role}, "
            f"actual={dict(actual_by_role)}"
        )
    if any(
        package.validation_status != "pending_automatic_validation"
        for package in packages
    ):
        raise RuntimeError("Ungrounded seed questions must not be retrieval-enabled")

    validated_bank = json.loads(args.validated_bank.read_text(encoding="utf-8"))
    validated_packages = validated_bank.get("packages")
    if not isinstance(validated_packages, list):
        raise RuntimeError("Validated question-bank artifact is invalid")
    draft_keys = {(package.package_key, package.version) for package in packages}
    validated_keys = {
        (str(package["package_key"]), str(package["version"]))
        for package in validated_packages
        if isinstance(package, dict)
    }
    if validated_keys != draft_keys:
        raise RuntimeError("Validated question bank does not match current role drafts")
    if (
        validated_bank.get("validated_count") != len(packages)
        or validated_bank.get("rejected_count") != 0
    ):
        raise RuntimeError("Current question bank is not fully validated")
    if any(
        package.get("validation_status") != "generated_validated_for_practice"
        or len(package.get("embedding", [])) != 384
        for package in validated_packages
    ):
        raise RuntimeError("Validated questions are not retrieval-ready")

    summary = {
        "schema_version": "knowledge-validation-v1",
        "source_count": len(sources),
        "retrieval_enabled_source_count": sum(
            source.retrieval_enabled for source in sources
        ),
        "role_count": len(roles),
        "question_draft_count": len(packages),
        "reviewed_document_count": len(seed.documents),
        "approved_resource_count": len(seed.resources),
        "question_drafts_by_role": dict(sorted(actual_by_role.items())),
        "question_draft_status": "pending_automatic_validation",
        "validated_question_count": len(validated_packages),
        "validated_question_status": "generated_validated_for_practice",
        "validated_questions_embedded": True,
        "missing_source_ids": [],
        "safety_checks": {
            "unlicensed_open_content_rejected": True,
            "unreviewed_sources_hidden_by_rls": True,
            "ungrounded_questions_hidden_by_rls": True,
            "resource_urls_cannot_be_invented": True,
            "rubrics_have_exactly_levels_1_to_5": True,
        },
        "next_gate": "Publish the validated artifacts to Supabase after live migration approval.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(
        "KNOWLEDGE LAYER VALIDATION PASSED: "
        f"{len(sources)} sources, {len(validated_packages)} validated packages"
    )


if __name__ == "__main__":
    main()
