from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.seed_validated_question_bank import _load_validated_packages, _package_row


def test_question_bank_publisher_requires_complete_validation_and_embeddings(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "questions.json"
    package = {
        "id": "role:question:v1",
        "package_key": "role:question",
        "version": "1.0.0",
        "validation_status": "generated_validated_for_practice",
        "embedding": [0.0] * 384,
        "embedding_model": "gemini-embedding-2",
        "source_to_concept_mapping": {"SRC-001": ["concept"]},
    }
    artifact.write_text(
        json.dumps(
            {
                "schema_version": "validated-question-bank-v1",
                "validated_count": 1,
                "rejected_count": 0,
                "packages": [package],
            }
        ),
        encoding="utf-8",
    )
    loaded = _load_validated_packages(artifact)
    assert loaded == [package]
    assert "source_to_concept_mapping" in _package_row(package)

    package["embedding"] = [0.0] * 383
    artifact.write_text(
        json.dumps(
            {
                "schema_version": "validated-question-bank-v1",
                "validated_count": 1,
                "rejected_count": 0,
                "packages": [package],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="not validated and embedded"):
        _load_validated_packages(artifact)
