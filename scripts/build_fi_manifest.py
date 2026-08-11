import argparse
import csv
import hashlib
import json
import runpy
from pathlib import Path

from tqdm import tqdm

TRAITS = [
    "interview", "agreeableness", "conscientiousness",
    "extraversion", "neuroticism", "openness",
]

def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

parser = argparse.ArgumentParser()
parser.add_argument("--dataset-root", required=True)
parser.add_argument("--annotation-root", required=True)
parser.add_argument("--output-root", required=True)
args = parser.parse_args()

dataset_root = Path(args.dataset_root).resolve()
annotation_root = Path(args.annotation_root).resolve()
output_root = Path(args.output_root).resolve()
output_root.mkdir(parents=True, exist_ok=True)

audit = runpy.run_path("scripts/audit_fi_annotations.py")
safe_load = audit["safe_load"]

train_file = annotation_root / "annotation_training.pkl"
validation_files = list(annotation_root.rglob("annotation_validation.pkl"))

if not train_file.is_file():
    raise FileNotFoundError(train_file)
if len(validation_files) != 1:
    raise RuntimeError(f"Expected one validation annotation, found {validation_files}")

annotations = {
    "train": safe_load(train_file),
    "validation": safe_load(validation_files[0]),
}

rows = []
all_names = set()

for split, labels in annotations.items():
    videos = sorted((dataset_root / split).glob("*.mp4"))
    video_names = {video.name for video in videos}

    missing_traits = set(TRAITS) - set(labels)
    if missing_traits:
        raise RuntimeError(f"{split}: missing traits {missing_traits}")

    label_names = set(labels["interview"])
    missing_labels = video_names - label_names
    missing_videos = label_names - video_names

    print(f"{split.upper()} videos: {len(video_names)}")
    print(f"{split.upper()} labels: {len(label_names)}")
    print(f"{split.upper()} missing labels: {len(missing_labels)}")
    print(f"{split.upper()} missing videos: {len(missing_videos)}")

    if missing_labels or missing_videos:
        raise RuntimeError(f"{split}: video-label mismatch")

    for trait in TRAITS:
        if set(labels[trait]) != label_names:
            raise RuntimeError(f"{split}: inconsistent filenames for {trait}")

    duplicates = all_names.intersection(video_names)
    if duplicates:
        raise RuntimeError(f"Cross-split duplicate: {next(iter(duplicates))}")
    all_names.update(video_names)

    for video in tqdm(videos, desc=f"Hashing {split}"):
        row = {
            "split": split,
            "video_id": video.name,
            "relative_path": video.relative_to(dataset_root).as_posix(),
            "size_bytes": video.stat().st_size,
            "sha256": sha256(video),
        }
        row.update({trait: float(labels[trait][video.name]) for trait in TRAITS})
        rows.append(row)

manifest = output_root / "first_impressions_v2_manifest.csv"
fields = ["split", "video_id", "relative_path", "size_bytes", "sha256"] + TRAITS

with manifest.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

summary = {
    "total_rows": len(rows),
    "training_rows": sum(r["split"] == "train" for r in rows),
    "validation_rows": sum(r["split"] == "validation" for r in rows),
    "target_label": "interview",
    "manifest_sha256": sha256(manifest),
}

summary_file = output_root / "first_impressions_v2_summary.json"
summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

print(json.dumps(summary, indent=2))
print("DATASET MANIFEST PASSED")
