import argparse
import csv
import json
import subprocess
from pathlib import Path


def run(command):
    subprocess.run(command, check=True)

def probe(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)

parser = argparse.ArgumentParser()
parser.add_argument("--dataset-root", required=True)
parser.add_argument("--manifest", required=True)
parser.add_argument("--output-root", required=True)
args = parser.parse_args()

dataset_root = Path(args.dataset_root).resolve()
output_root = Path(args.output_root).resolve()
video_root = output_root / "video"
audio_root = output_root / "audio"
video_root.mkdir(parents=True, exist_ok=True)
audio_root.mkdir(parents=True, exist_ok=True)

with open(args.manifest, newline="", encoding="utf-8") as handle:
    rows = [r for r in csv.DictReader(handle) if r["split"] == "train"]

rows.sort(key=lambda r: (float(r["interview"]), r["video_id"]))

# Select one deterministic sample from the middle of each score decile.
selected = [rows[int((i + 0.5) * len(rows) / 10)] for i in range(10)]
results = []

for index, row in enumerate(selected, start=1):
    source = dataset_root / row["relative_path"]
    stem = source.stem
    video_output = video_root / f"{stem}.mp4"
    audio_output = audio_root / f"{stem}.wav"

    print(f"[{index}/10] {source.name} | interview={row['interview']}")

    run([
        "ffmpeg", "-nostdin", "-y", "-loglevel", "error",
        "-i", str(source),
        "-map", "0:v:0", "-an",
        "-vf", "fps=25,scale=640:-2",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(video_output),
    ])

    run([
        "ffmpeg", "-nostdin", "-y", "-loglevel", "error",
        "-i", str(source),
        "-map", "0:a:0", "-vn",
        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(audio_output),
    ])

    video_info = probe(video_output)
    audio_info = probe(audio_output)
    video_duration = float(video_info["format"]["duration"])
    audio_duration = float(audio_info["format"]["duration"])
    audio_stream = audio_info["streams"][0]

    if audio_stream["sample_rate"] != "16000" or audio_stream["channels"] != 1:
        raise RuntimeError(f"Invalid audio format for {source.name}")
    if video_duration <= 0 or abs(video_duration - audio_duration) > 0.75:
        raise RuntimeError(f"Duration mismatch for {source.name}")

    results.append({
        "video_id": row["video_id"],
        "interview_score": float(row["interview"]),
        "source_sha256": row["sha256"],
        "normalized_video": str(video_output),
        "normalized_audio": str(audio_output),
        "video_duration_seconds": video_duration,
        "audio_duration_seconds": audio_duration,
    })

pilot_manifest = output_root / "pilot_10_manifest.json"
pilot_manifest.write_text(json.dumps(results, indent=2), encoding="utf-8")

print("\nSelected scores:", [round(r["interview_score"], 4) for r in results])
print("Pilot manifest:", pilot_manifest)
print("MEDIA NORMALIZATION PASSED: 10/10")
