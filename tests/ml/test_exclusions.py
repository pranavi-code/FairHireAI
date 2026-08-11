from __future__ import annotations

import json
from pathlib import Path

import pytest

from ml_service.preprocessing.exclusions import (
    load_exclusions,
    validate_excluded_sample,
)


def test_versioned_exclusion_requires_exact_manifest_and_failure(tmp_path: Path) -> None:
    row = {
        "split": "train",
        "video_id": "silent.001.mp4",
        "sha256": "a" * 64,
    }
    exclusion_path = tmp_path / "exclusions.json"
    exclusion_path.write_text(
        json.dumps(
            {
                "schema_version": "fi-preprocessing-exclusions-v1",
                "entries": [
                    {
                        "split": "train",
                        "video_id": "silent.001.mp4",
                        "source_sha256": "a" * 64,
                        "reason_code": "whisper_no_words",
                        "official_transcript_available": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    exclusions = load_exclusions(exclusion_path, [row])
    sample_root = tmp_path / "sample"
    sample_root.mkdir()
    (sample_root / "status.json").write_text(
        json.dumps(
            {
                "state": "failed",
                "video_id": "silent.001.mp4",
                "source_sha256": "a" * 64,
                "error": {
                    "type": "RuntimeError",
                    "message": "Whisper returned no words for silent.001.mp4",
                },
            }
        ),
        encoding="utf-8",
    )

    validate_excluded_sample(exclusions[("train", "silent.001.mp4")], sample_root)


def test_exclusion_rejects_a_checksum_not_in_the_manifest(tmp_path: Path) -> None:
    path = tmp_path / "exclusions.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "fi-preprocessing-exclusions-v1",
                "entries": [
                    {
                        "split": "train",
                        "video_id": "silent.001.mp4",
                        "source_sha256": "b" * 64,
                        "reason_code": "whisper_no_words",
                        "official_transcript_available": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="checksum"):
        load_exclusions(
            path,
            [{"split": "train", "video_id": "silent.001.mp4", "sha256": "a" * 64}],
        )
