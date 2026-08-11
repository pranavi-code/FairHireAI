"""Align the already-extracted ten-video FI pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml_service.preprocessing.alignment import align_sample, load_aligned_sample


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-root", required=True)
    parser.add_argument("--acoustic-workers", type=int, default=1)
    args = parser.parse_args()

    pilot_root = Path(args.pilot_root).resolve()
    manifest = json.loads((pilot_root / "pilot_10_manifest.json").read_text(encoding="utf-8"))
    output_root = pilot_root / "aligned"
    output_root.mkdir(parents=True, exist_ok=True)

    summaries = []
    schema = None
    for index, item in enumerate(manifest, start=1):
        stem = Path(item["normalized_audio"]).stem
        transcript = pilot_root / "transcripts" / f"{stem}.json"
        visual = pilot_root / "visual" / "openface_parquet" / f"{stem}_openface.parquet"
        output = output_root / f"{stem}_aligned.npz"
        print(f"[{index}/{len(manifest)}] Aligning {item['video_id']}")

        summary = align_sample(
            transcript_path=transcript,
            audio_path=item["normalized_audio"],
            visual_path=visual,
            output_path=output,
            label=float(item["interview_score"]),
            video_id=item["video_id"],
            acoustic_workers=args.acoustic_workers,
        )
        load_aligned_sample(output)
        current_schema = (
            summary.pop("acoustic_feature_names"),
            summary.pop("visual_feature_names"),
        )
        if schema is None:
            schema = current_schema
        elif schema != current_schema:
            raise RuntimeError("Feature column order changed between pilot samples")

        summaries.append(summary)
        print(
            f"  words={summary['words']}, "
            f"A={tuple(summary['acoustic_shape'])}, "
            f"V={tuple(summary['visual_shape'])}, "
            f"visual_success={summary['visual_success_rate']:.4f}, "
            f"max_delta={summary['maximum_visual_time_delta']:.4f}s"
        )

    if schema is None:
        raise RuntimeError("Pilot manifest is empty")

    schema_payload = {
        "schema_version": summaries[0]["schema_version"],
        "alignment": {
            "acoustic": "eGeMAPSv02 functionals on exact Whisper word interval",
            "visual": "nearest OpenFace frame to word midpoint",
        },
        "acoustic_feature_names": list(schema[0]),
        "visual_feature_names": list(schema[1]),
    }
    (output_root / "alignment_schema.json").write_text(
        json.dumps(schema_payload, indent=2), encoding="utf-8"
    )
    (output_root / "alignment_summary.json").write_text(
        json.dumps(summaries, indent=2), encoding="utf-8"
    )

    print()
    print("Recordings aligned:", len(summaries))
    print("Total words:", sum(item["words"] for item in summaries))
    print("Schema:", output_root / "alignment_schema.json")
    print("WORD ALIGNMENT PASSED: 10/10")


if __name__ == "__main__":
    main()
