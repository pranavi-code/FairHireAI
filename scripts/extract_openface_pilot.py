import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument("--pilot-root", required=True)
parser.add_argument("--openface-root", required=True)
args = parser.parse_args()

pilot_root = Path(args.pilot_root).resolve()
openface_root = Path(args.openface_root).resolve()
executable = openface_root / "FeatureExtraction.exe"

if not executable.is_file():
    raise FileNotFoundError(executable)

manifest_file = pilot_root / "pilot_10_manifest.json"
pilot = json.loads(manifest_file.read_text(encoding="utf-8"))

raw_root = pilot_root / "visual" / "openface_raw"
parquet_root = pilot_root / "visual" / "openface_parquet"

raw_root.mkdir(parents=True, exist_ok=True)
parquet_root.mkdir(parents=True, exist_ok=True)

required_columns = {
    "frame",
    "face_id",
    "timestamp",
    "confidence",
    "success",
    "pose_Tx",
    "pose_Ty",
    "pose_Tz",
    "pose_Rx",
    "pose_Ry",
    "pose_Rz",
}

summaries = []

for index, item in enumerate(pilot, start=1):
    video = Path(item["normalized_video"])
    expected_frames = round(
        float(item["video_duration_seconds"]) * 25
    )

    print(f"[{index}/10] Processing {video.name}")

    command = [
        str(executable),
        "-f", str(video),
        "-out_dir", str(raw_root),
        "-2Dfp",
        "-3Dfp",
        "-pdmparams",
        "-pose",
        "-aus",
        "-gaze",
    ]

    result = subprocess.run(
        command,
        cwd=openface_root,
        capture_output=True,
        text=True,
        errors="replace",
    )

    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise RuntimeError(
            f"OpenFace failed for {video.name}: "
            f"exit code {result.returncode}"
        )

    csv_file = raw_root / f"{video.stem}.csv"

    if not csv_file.is_file():
        raise FileNotFoundError(
            f"OpenFace CSV was not created: {csv_file}"
        )

    frame = pd.read_csv(csv_file, skipinitialspace=True)
    frame.columns = [column.strip() for column in frame.columns]

    missing = required_columns - set(frame.columns)

    if missing:
        raise RuntimeError(
            f"{video.name}: missing columns {sorted(missing)}"
        )

    if len(frame) == 0:
        raise RuntimeError(f"{video.name}: no frames generated")

    if not frame["timestamp"].is_monotonic_increasing:
        raise RuntimeError(
            f"{video.name}: timestamps are not monotonic"
        )

    frame_difference = abs(len(frame) - expected_frames)

    if frame_difference > 3:
        raise RuntimeError(
            f"{video.name}: expected approximately "
            f"{expected_frames} frames, found {len(frame)}"
        )

    successful_mask = frame["success"] == 1
    successful_frames = int(successful_mask.sum())

    if successful_frames == 0:
        raise RuntimeError(
            f"{video.name}: no successful face detections"
        )

    numeric_successful = frame.loc[
        successful_mask
    ].select_dtypes(include=[np.number])

    if not np.isfinite(
        numeric_successful.to_numpy(dtype=np.float64)
    ).all():
        raise RuntimeError(
            f"{video.name}: successful frames contain NaN or infinity"
        )

    success_rate = successful_frames / len(frame)
    mean_confidence = float(
        frame.loc[successful_mask, "confidence"].mean()
    )

    landmark_columns = [
        column for column in frame.columns
        if column.startswith("x_") or column.startswith("y_")
    ]

    gaze_columns = [
        column for column in frame.columns
        if column.startswith("gaze_")
    ]

    action_unit_columns = [
        column for column in frame.columns
        if column.startswith("AU")
    ]

    pose_columns = [
        column for column in frame.columns
        if column.startswith("pose_")
    ]

    if len(landmark_columns) != 136:
        raise RuntimeError(
            f"{video.name}: expected 136 2D landmark columns, "
            f"found {len(landmark_columns)}"
        )

    if len(gaze_columns) != 8:
        raise RuntimeError(
            f"{video.name}: expected 8 gaze columns, "
            f"found {len(gaze_columns)}"
        )

    if len(action_unit_columns) != 35:
        raise RuntimeError(
            f"{video.name}: expected 35 action-unit columns, "
            f"found {len(action_unit_columns)}"
        )

    quality = (
        "good"
        if success_rate >= 0.80 and mean_confidence >= 0.75
        else "low_quality"
    )

    parquet_file = (
        parquet_root / f"{video.stem}_openface.parquet"
    )
    frame.to_parquet(parquet_file, index=False)

    summary = {
        "video_id": item["video_id"],
        "frames": len(frame),
        "expected_frames": expected_frames,
        "columns": len(frame.columns),
        "successful_frames": successful_frames,
        "success_rate": success_rate,
        "mean_confidence": mean_confidence,
        "landmark_columns": len(landmark_columns),
        "gaze_columns": len(gaze_columns),
        "pose_columns": len(pose_columns),
        "action_unit_columns": len(action_unit_columns),
        "quality": quality,
        "raw_csv": str(csv_file),
        "parquet_file": str(parquet_file),
    }
    summaries.append(summary)

    print(
        f"  frames={len(frame)}, "
        f"success={success_rate:.4f}, "
        f"confidence={mean_confidence:.4f}, "
        f"columns={len(frame.columns)}, "
        f"quality={quality}"
    )

summary_payload = {
    "openface_version": "2.2.0",
    "recordings": summaries,
    "good_quality_recordings": sum(
        item["quality"] == "good" for item in summaries
    ),
    "low_quality_recordings": sum(
        item["quality"] == "low_quality" for item in summaries
    ),
}

summary_file = pilot_root / "visual" / "visual_summary.json"
summary_file.write_text(
    json.dumps(summary_payload, indent=2),
    encoding="utf-8",
)

print()
print("Recordings processed:", len(summaries))
print(
    "Good-quality recordings:",
    summary_payload["good_quality_recordings"],
)
print(
    "Low-quality recordings:",
    summary_payload["low_quality_recordings"],
)
print("Summary:", summary_file)
print("OPENFACE EXTRACTION PASSED: 10/10")
