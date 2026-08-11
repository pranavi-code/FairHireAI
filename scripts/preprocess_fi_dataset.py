"""Launch resumable First Impressions V2 preprocessing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml_service.preprocessing.pipeline import (
    VERIFIED_MANIFEST_SHA256,
    PipelineConfig,
    load_manifest,
    run_pipeline,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--openface-root", required=True)
    parser.add_argument("--model-root", required=True)
    parser.add_argument("--model", default="small.en")
    parser.add_argument(
        "--splits",
        nargs="+",
        choices=("train", "validation"),
        default=("train", "validation"),
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--keep-intermediates", action="store_true")
    parser.add_argument("--verify-source-hashes", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument(
        "--allow-unverified-manifest",
        action="store_true",
        help="Disable the pinned manifest checksum (intended only for tests).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit must be positive")
    manifest = Path(args.manifest).resolve()
    rows = load_manifest(
        manifest,
        splits=args.splits,
        expected_sha256=(None if args.allow_unverified_manifest else VERIFIED_MANIFEST_SHA256),
    )
    if args.limit is not None:
        rows = rows[: args.limit]
    config = PipelineConfig(
        dataset_root=Path(args.dataset_root).resolve(),
        manifest_path=manifest,
        output_root=Path(args.output_root).resolve(),
        openface_root=Path(args.openface_root).resolve(),
        whisper_model_root=Path(args.model_root).resolve(),
        whisper_model=args.model,
        keep_intermediates=args.keep_intermediates,
        verify_source_hashes=args.verify_source_hashes,
        force=args.force,
        fail_fast=args.fail_fast,
    )
    summary = run_pipeline(config, rows)
    print(json.dumps(summary, indent=2))
    if summary["failed"]:
        raise SystemExit(1)
    print("FI PREPROCESSING PASSED")


if __name__ == "__main__":
    main()
