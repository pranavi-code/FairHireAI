import argparse
import json
from importlib.metadata import version
from pathlib import Path

import numpy as np
import opensmile
import pandas as pd


def convert_time_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.reset_index()

    if "file" in frame.columns:
        frame = frame.drop(columns=["file"])

    frame["start_seconds"] = frame["start"].apply(
        lambda value: value.total_seconds()
    )
    frame["end_seconds"] = frame["end"].apply(
        lambda value: value.total_seconds()
    )

    return frame.drop(columns=["start", "end"])


parser = argparse.ArgumentParser()
parser.add_argument("--pilot-root", required=True)
args = parser.parse_args()

pilot_root = Path(args.pilot_root).resolve()
manifest_file = pilot_root / "pilot_10_manifest.json"
output_root = pilot_root / "acoustic"
output_root.mkdir(parents=True, exist_ok=True)

pilot = json.loads(manifest_file.read_text(encoding="utf-8"))

lld_extractor = opensmile.Smile(
    feature_set=opensmile.FeatureSet.eGeMAPSv02,
    feature_level=opensmile.FeatureLevel.LowLevelDescriptors,
)

functional_extractor = opensmile.Smile(
    feature_set=opensmile.FeatureSet.eGeMAPSv02,
    feature_level=opensmile.FeatureLevel.Functionals,
)

lld_names = list(lld_extractor.feature_names)
functional_names = list(functional_extractor.feature_names)

if len(lld_names) != 25:
    raise RuntimeError(
        f"Expected 25 eGeMAPSv02 LLD features, found {len(lld_names)}"
    )

if len(functional_names) != 88:
    raise RuntimeError(
        f"Expected 88 eGeMAPSv02 functionals, found {len(functional_names)}"
    )

summaries = []

for index, item in enumerate(pilot, start=1):
    audio = Path(item["normalized_audio"])
    stem = audio.stem
    expected_duration = float(item["audio_duration_seconds"])

    print(f"[{index}/10] Extracting {audio.name}")

    if not audio.is_file():
        raise FileNotFoundError(audio)

    lld_frame = convert_time_columns(
        lld_extractor.process_file(str(audio))
    )
    functional_frame = convert_time_columns(
        functional_extractor.process_file(str(audio))
    )

    if len(functional_frame) != 1:
        raise RuntimeError(
            f"{audio.name}: expected one functional row, "
            f"found {len(functional_frame)}"
        )

    lld_values = lld_frame[lld_names].to_numpy(dtype=np.float32)
    functional_values = functional_frame[
        functional_names
    ].to_numpy(dtype=np.float32)

    if not np.isfinite(lld_values).all():
        raise RuntimeError(
            f"{audio.name}: LLD features contain NaN or infinity"
        )

    if not np.isfinite(functional_values).all():
        raise RuntimeError(
            f"{audio.name}: functional features contain NaN or infinity"
        )

    if len(lld_frame) == 0:
        raise RuntimeError(f"{audio.name}: no acoustic frames produced")

    final_frame_end = float(lld_frame["end_seconds"].iloc[-1])

    if final_frame_end <= 0:
        raise RuntimeError(f"{audio.name}: invalid acoustic duration")

    if final_frame_end > expected_duration + 0.25:
        raise RuntimeError(
            f"{audio.name}: acoustic frames exceed audio duration"
        )

    lld_output = output_root / f"{stem}_egemaps_lld.parquet"
    functional_output = (
        output_root / f"{stem}_egemaps_functionals.parquet"
    )

    lld_frame.to_parquet(lld_output, index=False)
    functional_frame.to_parquet(functional_output, index=False)

    summary = {
        "video_id": item["video_id"],
        "audio_file": str(audio),
        "feature_set": "eGeMAPSv02",
        "lld_dimensions": len(lld_names),
        "lld_frames": len(lld_frame),
        "functional_dimensions": len(functional_names),
        "functional_rows": len(functional_frame),
        "last_frame_end_seconds": final_frame_end,
        "audio_duration_seconds": expected_duration,
        "lld_file": str(lld_output),
        "functionals_file": str(functional_output),
    }
    summaries.append(summary)

    print(
        f"  LLD shape={lld_values.shape}, "
        f"functionals shape={functional_values.shape}, "
        f"end={final_frame_end:.3f}s"
    )

summary_payload = {
    "opensmile_version": version("opensmile"),
    "feature_set": "eGeMAPSv02",
    "lld_dimensions": len(lld_names),
    "functional_dimensions": len(functional_names),
    "recordings": summaries,
}

summary_file = output_root / "acoustic_summary.json"
summary_file.write_text(
    json.dumps(summary_payload, indent=2),
    encoding="utf-8",
)

print()
print("openSMILE version:", summary_payload["opensmile_version"])
print("Recordings processed:", len(summaries))
print("LLD dimensions:", len(lld_names))
print("Functional dimensions:", len(functional_names))
print("Summary:", summary_file)
print("EGEMAPS EXTRACTION PASSED: 10/10")
