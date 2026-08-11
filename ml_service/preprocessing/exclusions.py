"""Strict, versioned exclusions for unusable FI multimodal samples."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXCLUSION_SCHEMA_VERSION = "fi-preprocessing-exclusions-v1"
ALLOWED_REASON_CODES = {"whisper_no_words"}


@dataclass(frozen=True)
class PreprocessingExclusion:
    video_id: str
    split: str
    source_sha256: str
    reason_code: str
    official_transcript_available: bool


def load_exclusions(
    path: str | Path,
    manifest_rows: list[dict[str, str]],
) -> dict[tuple[str, str], PreprocessingExclusion]:
    """Load exclusions and prove that every entry matches the pinned manifest."""

    payload: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("The preprocessing exclusion manifest must be an object")
    if payload.get("schema_version") != EXCLUSION_SCHEMA_VERSION:
        raise RuntimeError("Unsupported preprocessing exclusion schema")
    entries = payload.get("entries")
    if not isinstance(entries, list) or len(entries) > 100:
        raise RuntimeError("Preprocessing exclusions must be a list with at most 100 entries")

    manifest_by_key = {
        (str(row["split"]), str(row["video_id"])): row for row in manifest_rows
    }
    exclusions: dict[tuple[str, str], PreprocessingExclusion] = {}
    for raw in entries:
        if not isinstance(raw, dict):
            raise RuntimeError("Every preprocessing exclusion must be an object")
        record = PreprocessingExclusion(
            video_id=str(raw.get("video_id", "")),
            split=str(raw.get("split", "")),
            source_sha256=str(raw.get("source_sha256", "")),
            reason_code=str(raw.get("reason_code", "")),
            official_transcript_available=raw.get("official_transcript_available"),
        )
        key = (record.split, record.video_id)
        if key in exclusions:
            raise RuntimeError(f"Duplicate preprocessing exclusion: {key}")
        manifest_row = manifest_by_key.get(key)
        if manifest_row is None:
            raise RuntimeError(f"Exclusion is not present in the pinned manifest: {key}")
        if record.source_sha256 != manifest_row["sha256"]:
            raise RuntimeError(f"Exclusion source checksum mismatch: {key}")
        if record.reason_code not in ALLOWED_REASON_CODES:
            raise RuntimeError(f"Unsupported preprocessing exclusion reason: {key}")
        if not isinstance(record.official_transcript_available, bool):
            raise RuntimeError(f"Exclusion transcript-availability flag is invalid: {key}")
        exclusions[key] = record
    return exclusions


def validate_excluded_sample(
    exclusion: PreprocessingExclusion,
    sample_root: Path,
) -> None:
    """Ensure an exclusion corresponds to the exact expected failed artifact."""

    aligned_path = sample_root / "aligned.npz"
    if aligned_path.exists():
        raise RuntimeError("An excluded sample unexpectedly has an aligned artifact")
    status_path = sample_root / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if status.get("state") != "failed":
        raise RuntimeError(f"Excluded sample has state={status.get('state')}")
    if status.get("video_id") != exclusion.video_id:
        raise RuntimeError("Excluded sample video_id mismatch")
    if status.get("source_sha256") != exclusion.source_sha256:
        raise RuntimeError("Excluded sample source checksum mismatch")
    error = status.get("error")
    expected_message = f"Whisper returned no words for {exclusion.video_id}"
    if not isinstance(error, dict):
        raise RuntimeError("Excluded sample has no structured error")
    if error.get("type") != "RuntimeError" or error.get("message") != expected_message:
        raise RuntimeError("Excluded sample does not have the approved no-word failure")
