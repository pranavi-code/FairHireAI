"""Audit every aligned artifact before allowing FI model training."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from ml_service.preprocessing.alignment import load_aligned_sample
from ml_service.preprocessing.exclusions import (
    load_exclusions,
    validate_excluded_sample,
)
from ml_service.preprocessing.pipeline import (
    VERIFIED_MANIFEST_SHA256,
    atomic_json,
    load_manifest,
    sha256_file,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--processed-root", required=True)
    parser.add_argument(
        "--exclusions",
        help="Versioned exclusions for source-verified, unusable multimodal samples.",
    )
    args = parser.parse_args()
    manifest = Path(args.manifest).resolve()
    processed_root = Path(args.processed_root).resolve()
    rows = load_manifest(
        manifest,
        splits=("train", "validation"),
        expected_sha256=VERIFIED_MANIFEST_SHA256,
    )
    exclusions_path = Path(args.exclusions).resolve() if args.exclusions else None
    exclusions = (
        load_exclusions(exclusions_path, rows) if exclusions_path is not None else {}
    )
    complete: Counter[str] = Counter()
    excluded: Counter[str] = Counter()
    quality: Counter[str] = Counter()
    dataset_identities: list[str] = []
    total_words = 0
    minimum_words: int | None = None
    maximum_words = 0
    errors: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=1):
        stem = Path(row["video_id"]).stem
        sample_root = processed_root / row["split"] / stem
        status_path = sample_root / "status.json"
        aligned_path = sample_root / "aligned.npz"
        try:
            exclusion = exclusions.get((row["split"], row["video_id"]))
            if exclusion is not None:
                validate_excluded_sample(exclusion, sample_root)
                excluded[row["split"]] += 1
                continue
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if status.get("state") != "complete":
                raise RuntimeError(f"state={status.get('state')}")
            if status.get("video_id") != row["video_id"]:
                raise RuntimeError("status video_id mismatch")
            if status.get("source_sha256") != row["sha256"]:
                raise RuntimeError("status source checksum mismatch")
            if not np.isclose(float(status["label"]), float(row["interview"])):
                raise RuntimeError("status label mismatch")
            sample = load_aligned_sample(aligned_path)
            if sample.video_id != row["video_id"]:
                raise RuntimeError("aligned video_id mismatch")
            if not np.isclose(sample.label, float(row["interview"])):
                raise RuntimeError("aligned label mismatch")
            words = len(sample.words)
            if words < 1:
                raise RuntimeError("no aligned words")
            total_words += words
            minimum_words = words if minimum_words is None else min(minimum_words, words)
            maximum_words = max(maximum_words, words)
            complete[row["split"]] += 1
            dataset_identities.append(
                f"{row['split']}|{row['video_id']}|{row['sha256']}"
            )
            quality[
                str(status.get("stages", {}).get("openface", {}).get("quality", "unknown"))
            ] += 1
        except Exception as error:
            errors.append(
                {
                    "split": row["split"],
                    "video_id": row["video_id"],
                    "error": f"{type(error).__name__}: {error}",
                }
            )
        if index % 500 == 0:
            print(f"  audited {index}/{len(rows)}", flush=True)
    manifest_counts = Counter(row["split"] for row in rows)
    expected_complete = manifest_counts - excluded
    dataset_identity_sha256 = hashlib.sha256(
        "\n".join(sorted(dataset_identities)).encode("utf-8")
    ).hexdigest()
    payload: dict[str, Any] = {
        "passed": (
            not errors
            and complete == expected_complete
            and complete + excluded == manifest_counts
        ),
        "manifest_sha256": sha256_file(manifest),
        "manifest_rows": len(rows),
        "complete": dict(complete),
        "excluded": dict(excluded),
        "effective_samples": sum(complete.values()),
        "dataset_identity_sha256": dataset_identity_sha256,
        "exclusions_path": str(exclusions_path) if exclusions_path else None,
        "exclusions_sha256": (
            sha256_file(exclusions_path) if exclusions_path is not None else None
        ),
        "visual_quality": dict(quality),
        "total_words": total_words,
        "average_words": total_words / max(sum(complete.values()), 1),
        "minimum_words": minimum_words,
        "maximum_words": maximum_words,
        "error_count": len(errors),
        "errors": errors,
    }
    report = processed_root / "preprocessing_audit.json"
    atomic_json(report, payload)
    print(json.dumps(payload, indent=2))
    print(f"Report: {report}")
    if not payload["passed"]:
        raise SystemExit(1)
    print("FI PREPROCESSING AUDIT PASSED")


if __name__ == "__main__":
    main()
