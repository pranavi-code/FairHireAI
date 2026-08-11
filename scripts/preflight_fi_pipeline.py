"""Read-only preflight for the long FI V2 preprocessing/training run."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import opensmile
import pandas
import torch
import transformers

from ml_service.preprocessing.pipeline import (
    VERIFIED_MANIFEST_SHA256,
    load_manifest,
    sha256_file,
)


def version_line(executable: str) -> str:
    path = shutil.which(executable)
    if path is None:
        raise FileNotFoundError(f"{executable} is not on PATH")
    result = subprocess.run([path, "-version"], capture_output=True, text=True, errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"Unable to run {executable}")
    return result.stdout.splitlines()[0]


def check_sources(rows: list[dict[str, str]], dataset_root: Path) -> list[str]:
    errors: list[str] = []
    for row in rows:
        source = dataset_root / row["relative_path"]
        if not source.is_file():
            errors.append(f"missing: {source}")
        elif source.stat().st_size != int(row["size_bytes"]):
            errors.append(f"size mismatch: {source}")
        if len(errors) >= 20:
            break
    return errors


def completed_counts(output_root: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    for split in ("train", "validation"):
        for status_path in (output_root / split).glob("*/status.json"):
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if status.get("state") == "complete" and (status_path.parent / "aligned.npz").is_file():
                counts[split] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--openface-root", required=True)
    parser.add_argument("--whisper-model-root", required=True)
    parser.add_argument("--bert-root", required=True)
    parser.add_argument("--minimum-free-gb", type=float, default=5.0)
    args = parser.parse_args()
    dataset_root = Path(args.dataset_root).resolve()
    manifest_path = Path(args.manifest).resolve()
    output_root = Path(args.output_root).resolve()
    openface_root = Path(args.openface_root).resolve()
    whisper_root = Path(args.whisper_model_root).resolve()
    bert_root = Path(args.bert_root).resolve()
    checks: dict[str, Any] = {}
    failures: list[str] = []

    try:
        rows = load_manifest(
            manifest_path,
            splits=("train", "validation"),
            expected_sha256=VERIFIED_MANIFEST_SHA256,
        )
        split_counts = Counter(row["split"] for row in rows)
        checks["manifest"] = {
            "sha256": sha256_file(manifest_path),
            "total": len(rows),
            "train": split_counts["train"],
            "validation": split_counts["validation"],
        }
        if split_counts != Counter(train=6000, validation=2000):
            failures.append(f"unexpected manifest split counts: {dict(split_counts)}")
        source_errors = check_sources(rows, dataset_root)
        checks["sources"] = {
            "checked": len(rows),
            "errors": source_errors,
        }
        failures.extend(source_errors)
    except Exception as error:
        failures.append(f"manifest/source check: {type(error).__name__}: {error}")

    try:
        checks["ffmpeg"] = version_line("ffmpeg")
        checks["ffprobe"] = version_line("ffprobe")
    except Exception as error:
        failures.append(f"media tools: {type(error).__name__}: {error}")

    openface_files = [
        openface_root / "FeatureExtraction.exe",
        openface_root / "model" / "patch_experts" / "cen_patches_0.25_of.dat",
        openface_root / "model" / "patch_experts" / "cen_patches_0.35_of.dat",
        openface_root / "model" / "patch_experts" / "cen_patches_0.50_of.dat",
        openface_root / "model" / "patch_experts" / "cen_patches_1.00_of.dat",
    ]
    missing_openface = [str(path) for path in openface_files if not path.is_file()]
    checks["openface"] = {
        "root": str(openface_root),
        "required_files": len(openface_files),
        "missing": missing_openface,
    }
    failures.extend(f"missing OpenFace file: {path}" for path in missing_openface)

    whisper_models = list(whisper_root.rglob("small.en.pt"))
    checks["whisper"] = {
        "models": [str(path) for path in whisper_models],
        "cached": len(whisper_models) == 1,
    }
    if len(whisper_models) != 1:
        failures.append(f"expected one cached small.en.pt, found {len(whisper_models)}")

    required_bert = [
        bert_root / "config.json",
        bert_root / "model.safetensors",
        bert_root / "tokenizer.json",
        bert_root / "tokenizer_config.json",
        bert_root / "vocab.txt",
    ]
    missing_bert = [str(path) for path in required_bert if not path.is_file()]
    checks["bert"] = {"root": str(bert_root), "missing": missing_bert}
    failures.extend(f"missing BERT file: {path}" for path in missing_bert)

    checks["python"] = sys.version.split()[0]
    checks["libraries"] = {
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "opensmile": opensmile.__version__,
        "pandas": pandas.__version__,
    }
    checks["cuda"] = {
        "available": torch.cuda.is_available(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "total_memory_gb": (
            torch.cuda.get_device_properties(0).total_memory / 1e9
            if torch.cuda.is_available()
            else 0.0
        ),
    }
    if not torch.cuda.is_available():
        failures.append("CUDA is unavailable")

    output_root.mkdir(parents=True, exist_ok=True)
    disk = shutil.disk_usage(output_root)
    free_gb = disk.free / 1e9
    checks["storage"] = {
        "output_root": str(output_root),
        "free_gb": free_gb,
        "minimum_free_gb": args.minimum_free_gb,
    }
    if free_gb < args.minimum_free_gb:
        failures.append(
            f"only {free_gb:.2f} GB free; at least {args.minimum_free_gb:.2f} GB required"
        )
    checks["already_complete"] = dict(completed_counts(output_root))
    payload = {"ready": not failures, "checks": checks, "failures": failures}
    report_path = output_root / "preflight_report.json"
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"Report: {report_path}")
    if failures:
        raise SystemExit(1)
    print("FI PIPELINE PREFLIGHT PASSED")


if __name__ == "__main__":
    main()
