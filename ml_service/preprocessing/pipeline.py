"""Resumable preprocessing pipeline for First Impressions V2.

The long run deliberately writes only compact, training-ready artifacts by
default. Normalized media and frame-level OpenFace output live in a work
directory and are removed after a sample has been aligned successfully.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import time
import traceback
import wave
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import whisper_timestamped as whisper
from imageio_ffmpeg import get_ffmpeg_exe, read_frames

from ml_service.preprocessing.alignment import align_sample, load_aligned_sample

PIPELINE_SCHEMA_VERSION = "fi-preprocessing-v1"
VERIFIED_MANIFEST_SHA256 = "2f15c2a034c7f0af9adb2b29e7ba2f888abc28fc616add5c853819aaeb4eda2c"


@dataclass(frozen=True)
class PipelineConfig:
    dataset_root: Path
    manifest_path: Path
    output_root: Path
    openface_root: Path
    whisper_model_root: Path
    whisper_model: str = "small.en"
    keep_intermediates: bool = False
    verify_source_hashes: bool = False
    force: bool = False
    fail_fast: bool = False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


def run_checked(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        errors="replace",
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout)[-4000:]
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: {command[0]}\n{detail}"
        )
    return result


def ffmpeg_executable() -> str:
    """Resolve a reproducible FFmpeg binary without relying on a global PATH."""

    configured = os.getenv("ROLEREADY_FFMPEG_PATH")
    if configured:
        path = Path(configured)
        if not path.is_file():
            raise RuntimeError("ROLEREADY_FFMPEG_PATH does not point to a file")
        return str(path)
    system_binary = shutil.which("ffmpeg")
    return system_binary or get_ffmpeg_exe()


def probe_media(path: Path) -> dict[str, Any]:
    result = run_checked(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    return json.loads(result.stdout)


def load_manifest(
    path: Path,
    *,
    splits: Iterable[str],
    expected_sha256: str | None = VERIFIED_MANIFEST_SHA256,
) -> list[dict[str, str]]:
    if expected_sha256 and sha256_file(path) != expected_sha256:
        raise RuntimeError("Manifest checksum differs from the verified 8,000-video manifest")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    required = {"split", "video_id", "relative_path", "size_bytes", "sha256", "interview"}
    missing = required - set(rows[0] if rows else ())
    if missing:
        raise RuntimeError(f"Manifest is missing columns: {sorted(missing)}")
    selected_splits = set(splits)
    selected = [row for row in rows if row["split"] in selected_splits]
    selected.sort(key=lambda row: (row["split"], row["video_id"]))
    if not selected:
        raise RuntimeError(f"No manifest rows selected for splits {sorted(selected_splits)}")
    return selected


def normalize_media(source: Path, video_output: Path, audio_output: Path) -> dict[str, float]:
    video_output.parent.mkdir(parents=True, exist_ok=True)
    audio_output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = ffmpeg_executable()
    run_checked(
        [
            ffmpeg,
            "-nostdin",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            "fps=25,scale=640:-2",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(video_output),
        ]
    )
    run_checked(
        [
            ffmpeg,
            "-nostdin",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(audio_output),
        ]
    )
    reader = read_frames(str(video_output), pix_fmt="rgb24")
    try:
        video_metadata = next(reader)
    finally:
        reader.close()
    with wave.open(str(audio_output), "rb") as audio:
        audio_rate = audio.getframerate()
        audio_channels = audio.getnchannels()
        audio_duration = audio.getnframes() / audio.getframerate()
    video_duration = float(video_metadata["duration"])
    if audio_rate != 16_000 or audio_channels != 1:
        raise RuntimeError("Normalized audio is not 16 kHz mono")
    if video_duration <= 0 or abs(video_duration - audio_duration) > 0.75:
        raise RuntimeError(
            f"Normalized media duration mismatch: {video_duration:.3f}s vs {audio_duration:.3f}s"
        )
    return {
        "video_duration_seconds": video_duration,
        "audio_duration_seconds": audio_duration,
    }


def transcribe_audio(
    model: Any,
    audio_path: Path,
    *,
    video_id: str,
    label: float,
    model_name: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    result = whisper.transcribe(
        model,
        str(audio_path),
        language="en",
        task="transcribe",
        fp16=True,
        temperature=0.0,
        beam_size=5,
        vad=False,
        compute_word_confidence=True,
        remove_empty_words=True,
        verbose=False,
    )
    clean_segments: list[dict[str, Any]] = []
    all_words: list[dict[str, Any]] = []
    previous_start = -1.0
    for segment in result.get("segments", []):
        words: list[dict[str, Any]] = []
        for raw_word in segment.get("words", []):
            word = {
                "text": str(raw_word["text"]).strip(),
                "start": float(raw_word["start"]),
                "end": float(raw_word["end"]),
                "confidence": float(raw_word["confidence"]),
            }
            if not word["text"]:
                continue
            if word["start"] < previous_start - 0.05 or word["end"] <= word["start"]:
                raise RuntimeError(f"Invalid word timestamps in {video_id}")
            if not 0.0 <= word["confidence"] <= 1.0:
                raise RuntimeError(f"Invalid word confidence in {video_id}")
            previous_start = word["start"]
            words.append(word)
            all_words.append(word)
        clean_segments.append(
            {
                "start": float(segment["start"]),
                "end": float(segment["end"]),
                "text": str(segment["text"]).strip(),
                "confidence": float(segment.get("confidence", 0.0)),
                "no_speech_probability": float(segment.get("no_speech_prob", 0.0)),
                "words": words,
            }
        )
    text = str(result.get("text", "")).strip()
    if not text or not all_words:
        raise RuntimeError(f"Whisper returned no words for {video_id}")
    return {
        "video_id": video_id,
        "interview_score": label,
        "model": model_name,
        "language": result.get("language", "en"),
        "text": text,
        "segments": clean_segments,
        "word_count": len(all_words),
        "average_word_confidence": statistics.fmean(word["confidence"] for word in all_words),
        "processing_seconds": time.perf_counter() - started,
    }


def extract_openface(
    video_path: Path,
    output_directory: Path,
    *,
    openface_root: Path,
    expected_duration: float,
) -> tuple[Path, dict[str, Any]]:
    executable = openface_root / "FeatureExtraction.exe"
    if not executable.is_file():
        raise FileNotFoundError(executable)
    output_directory.mkdir(parents=True, exist_ok=True)
    run_checked(
        [
            str(executable),
            "-f",
            str(video_path),
            "-out_dir",
            str(output_directory),
            "-2Dfp",
            "-3Dfp",
            "-pdmparams",
            "-pose",
            "-aus",
            "-gaze",
        ],
        cwd=openface_root,
    )
    csv_path = output_directory / f"{video_path.stem}.csv"
    if not csv_path.is_file():
        raise FileNotFoundError(csv_path)
    frame = pd.read_csv(csv_path, skipinitialspace=True)
    frame.columns = [str(column).strip() for column in frame.columns]
    required = {"frame", "face_id", "timestamp", "confidence", "success"}
    missing = required - set(frame.columns)
    if missing or len(frame.columns) != 714:
        raise RuntimeError(
            f"Invalid OpenFace schema: columns={len(frame.columns)}, missing={sorted(missing)}"
        )
    expected_frames = round(expected_duration * 25)
    if frame.empty or abs(len(frame) - expected_frames) > 3:
        raise RuntimeError(
            f"OpenFace frame count {len(frame)} differs from expected {expected_frames}"
        )
    if not frame["timestamp"].is_monotonic_increasing:
        raise RuntimeError("OpenFace timestamps are not monotonic")
    successful = frame["success"] == 1
    successful_frames = int(successful.sum())
    if successful_frames == 0:
        raise RuntimeError("OpenFace found no successful face frames")
    numeric = frame.loc[successful].select_dtypes(include=[np.number])
    if not np.isfinite(numeric.to_numpy(dtype=np.float64)).all():
        raise RuntimeError("Successful OpenFace frames contain NaN or infinity")
    success_rate = successful_frames / len(frame)
    mean_confidence = float(frame.loc[successful, "confidence"].mean())
    return csv_path, {
        "frames": len(frame),
        "expected_frames": expected_frames,
        "columns": len(frame.columns),
        "successful_frames": successful_frames,
        "success_rate": success_rate,
        "mean_confidence": mean_confidence,
        "quality": ("good" if success_rate >= 0.80 and mean_confidence >= 0.75 else "low_quality"),
    }


class PreprocessingRunner:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        config.output_root.mkdir(parents=True, exist_ok=True)
        config.whisper_model_root.mkdir(parents=True, exist_ok=True)
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable; GPU preprocessing is required")
        self.whisper_model = whisper.load_model(
            config.whisper_model,
            device="cuda",
            download_root=str(config.whisper_model_root),
        )

    def _paths(self, row: dict[str, str]) -> dict[str, Path]:
        stem = Path(row["video_id"]).stem
        sample = self.config.output_root / row["split"] / stem
        work = self.config.output_root / "_work" / row["split"] / stem
        return {
            "sample": sample,
            "work": work,
            "video": work / "normalized.mp4",
            "audio": work / "normalized.wav",
            "openface": work / "openface",
            "transcript": sample / "transcript.json",
            "aligned": sample / "aligned.npz",
            "status": sample / "status.json",
            "visual": sample / "openface.parquet",
            "kept_video": sample / "normalized.mp4",
            "kept_audio": sample / "normalized.wav",
        }

    def process(self, row: dict[str, str]) -> dict[str, Any]:
        paths = self._paths(row)
        label = float(row["interview"])
        base_status: dict[str, Any] = {
            "schema_version": PIPELINE_SCHEMA_VERSION,
            "video_id": row["video_id"],
            "split": row["split"],
            "label": label,
            "source_sha256": row["sha256"],
            "state": "running",
            "stages": {},
        }
        if paths["status"].is_file():
            try:
                existing = json.loads(paths["status"].read_text(encoding="utf-8"))
                if existing.get("source_sha256") == row["sha256"]:
                    base_status = existing
            except (json.JSONDecodeError, OSError):
                pass
        if not self.config.force and paths["aligned"].is_file():
            aligned = load_aligned_sample(paths["aligned"])
            if len(aligned.words) > 0:
                base_status["state"] = "complete"
                base_status["skipped_existing"] = True
                atomic_json(paths["status"], base_status)
                return base_status

        source = self.config.dataset_root / row["relative_path"]
        if not source.is_file():
            raise FileNotFoundError(source)
        if source.stat().st_size != int(row["size_bytes"]):
            raise RuntimeError(f"Source size differs from manifest: {source}")
        if self.config.verify_source_hashes and sha256_file(source) != row["sha256"]:
            raise RuntimeError(f"Source checksum differs from manifest: {source}")

        paths["sample"].mkdir(parents=True, exist_ok=True)
        paths["work"].mkdir(parents=True, exist_ok=True)
        try:
            media = normalize_media(source, paths["video"], paths["audio"])
            base_status["stages"]["normalize"] = media
            atomic_json(paths["status"], base_status)

            transcript = transcribe_audio(
                self.whisper_model,
                paths["audio"],
                video_id=row["video_id"],
                label=label,
                model_name=self.config.whisper_model,
            )
            atomic_json(paths["transcript"], transcript)
            base_status["stages"]["transcribe"] = {
                "words": transcript["word_count"],
                "average_word_confidence": transcript["average_word_confidence"],
                "processing_seconds": transcript["processing_seconds"],
            }
            atomic_json(paths["status"], base_status)

            visual_path, visual = extract_openface(
                paths["video"],
                paths["openface"],
                openface_root=self.config.openface_root,
                expected_duration=media["video_duration_seconds"],
            )
            base_status["stages"]["openface"] = visual
            atomic_json(paths["status"], base_status)

            if self.config.keep_intermediates:
                visual_frame = pd.read_csv(visual_path, skipinitialspace=True)
                visual_frame.columns = [str(column).strip() for column in visual_frame.columns]
                visual_frame.to_parquet(paths["visual"], index=False)
                alignment_visual = paths["visual"]
            else:
                alignment_visual = visual_path

            alignment = align_sample(
                transcript_path=paths["transcript"],
                audio_path=paths["audio"],
                visual_path=alignment_visual,
                output_path=paths["aligned"],
                label=label,
                video_id=row["video_id"],
            )
            schema_path = self.config.output_root / "alignment_schema.json"
            if not schema_path.is_file():
                atomic_json(
                    schema_path,
                    {
                        "schema_version": alignment["schema_version"],
                        "acoustic_dimensions": alignment["acoustic_shape"][1],
                        "visual_dimensions": alignment["visual_shape"][1],
                        "minimum_acoustic_window_seconds": alignment[
                            "minimum_acoustic_window_seconds"
                        ],
                        "acoustic_feature_names": alignment["acoustic_feature_names"],
                        "visual_feature_names": alignment["visual_feature_names"],
                    },
                )
            base_status["stages"]["align"] = {
                key: value
                for key, value in alignment.items()
                if key not in {"acoustic_feature_names", "visual_feature_names"}
            }
            base_status["state"] = "complete"
            base_status["completed_at_unix"] = time.time()

            if self.config.keep_intermediates:
                shutil.copy2(paths["video"], paths["kept_video"])
                shutil.copy2(paths["audio"], paths["kept_audio"])
            atomic_json(paths["status"], base_status)
            if paths["work"].is_dir():
                shutil.rmtree(paths["work"])
            return base_status
        except Exception as error:
            base_status["state"] = "failed"
            base_status["error"] = {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            }
            atomic_json(paths["status"], base_status)
            raise


def run_pipeline(
    config: PipelineConfig,
    rows: list[dict[str, str]],
) -> dict[str, Any]:
    runner = PreprocessingRunner(config)
    completed = 0
    failed = 0
    skipped = 0
    failures: list[dict[str, str]] = []
    started = time.time()
    for index, row in enumerate(rows, start=1):
        print(f"[{index}/{len(rows)}] {row['split']}/{row['video_id']}", flush=True)
        try:
            status = runner.process(row)
            completed += 1
            if status.get("skipped_existing"):
                skipped += 1
            words = status.get("stages", {}).get("align", {}).get("words", "?")
            quality = status.get("stages", {}).get("openface", {}).get("quality", "?")
            print(f"  complete words={words}, visual_quality={quality}", flush=True)
        except Exception as error:
            failed += 1
            failures.append(
                {
                    "video_id": row["video_id"],
                    "split": row["split"],
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            print(f"  FAILED: {type(error).__name__}: {error}", flush=True)
            if config.fail_fast:
                break
    summary = {
        "schema_version": PIPELINE_SCHEMA_VERSION,
        "requested": len(rows),
        "completed": completed,
        "failed": failed,
        "skipped_existing": skipped,
        "elapsed_seconds": time.time() - started,
        "failures": failures,
    }
    atomic_json(config.output_root / "preprocessing_summary.json", summary)
    return summary
