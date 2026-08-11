"""Paper-faithful word-level multimodal alignment.

The MAG-BERT-ARL paper segments audio at Whisper word boundaries and
extracts one 88-dimensional eGeMAPSv02 functional vector per word. It
extracts 709 OpenFace payload values per frame and selects the frame
corresponding to each word. This module implements that contract and keeps
quality indicators separate from capability features.
"""

from __future__ import annotations

import json
import wave
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import opensmile
import pandas as pd

ACOUSTIC_DIM = 88
VISUAL_DIM = 709
MIN_ACOUSTIC_WINDOW_SECONDS = 0.10
SCHEMA_VERSION = "fi-word-alignment-v1"
OPENFACE_METADATA_COLUMNS = (
    "frame",
    "face_id",
    "timestamp",
    "confidence",
    "success",
)


@dataclass(frozen=True)
class WordEvidence:
    """Timestamped word emitted by whisper-timestamped."""

    text: str
    start: float
    end: float
    confidence: float


@dataclass(frozen=True)
class AlignedArrays:
    """Numerical arrays for one interview segment."""

    video_id: str
    label: float
    words: np.ndarray
    word_start: np.ndarray
    word_end: np.ndarray
    word_confidence: np.ndarray
    acoustic: np.ndarray
    visual: np.ndarray
    visual_confidence: np.ndarray
    visual_success: np.ndarray
    visual_time_delta: np.ndarray
    acoustic_feature_names: tuple[str, ...]
    visual_feature_names: tuple[str, ...]


def load_words(transcript_path: str | Path) -> tuple[dict[str, Any], list[WordEvidence]]:
    """Load and validate the word sequence from a transcript artifact."""

    path = Path(transcript_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    words: list[WordEvidence] = []
    previous_start = -1.0

    for segment in payload.get("segments", []):
        for raw_word in segment.get("words", []):
            text = str(raw_word["text"]).strip()
            start = float(raw_word["start"])
            end = float(raw_word["end"])
            confidence = float(raw_word["confidence"])

            if not text:
                continue
            if start < previous_start - 0.05:
                raise ValueError(f"Non-monotonic word timestamps in {path}")
            if start < 0 or end <= start:
                raise ValueError(f"Invalid word interval {start}-{end} in {path}")
            if not 0.0 <= confidence <= 1.0:
                raise ValueError(f"Invalid word confidence {confidence} in {path}")

            words.append(WordEvidence(text, start, end, confidence))
            previous_start = start

    if not words:
        raise ValueError(f"Transcript contains no timestamped words: {path}")

    return payload, words


def extract_word_acoustic(
    audio_path: str | Path,
    words: Sequence[WordEvidence],
    *,
    num_workers: int = 1,
) -> tuple[np.ndarray, tuple[str, ...], int]:
    """Extract one eGeMAPSv02 vector per word.

    Whisper can emit extremely short word intervals (for example, 20 ms for
    the word ``I``).  That is shorter than the analysis context needed by
    some eGeMAPS functionals.  Such intervals are symmetrically expanded to
    100 ms, while the original Whisper timestamps remain unchanged in the
    aligned artifact and continue to drive visual alignment.
    """

    audio_path = Path(audio_path).resolve()
    if not audio_path.is_file():
        raise FileNotFoundError(audio_path)

    extractor = opensmile.Smile(
        feature_set=opensmile.FeatureSet.eGeMAPSv02,
        feature_level=opensmile.FeatureLevel.Functionals,
        num_workers=num_workers,
    )
    feature_names = tuple(extractor.feature_names)
    if len(feature_names) != ACOUSTIC_DIM:
        raise RuntimeError(
            f"Expected {ACOUSTIC_DIM} eGeMAPSv02 functionals, found {len(feature_names)}"
        )

    with wave.open(str(audio_path), "rb") as audio:
        audio_duration = audio.getnframes() / audio.getframerate()

    starts: list[float] = []
    ends: list[float] = []
    expanded_windows = 0
    for word in words:
        start = word.start
        end = min(word.end, audio_duration)
        if end - start < MIN_ACOUSTIC_WINDOW_SECONDS:
            expanded_windows += 1
            midpoint = (start + end) / 2.0
            start = max(0.0, midpoint - MIN_ACOUSTIC_WINDOW_SECONDS / 2.0)
            end = min(audio_duration, start + MIN_ACOUSTIC_WINDOW_SECONDS)
            start = max(0.0, end - MIN_ACOUSTIC_WINDOW_SECONDS)
        starts.append(start)
        ends.append(end)

    frame = extractor.process_files(
        [str(audio_path)] * len(words),
        starts=starts,
        ends=ends,
    )
    values = frame.loc[:, list(feature_names)].to_numpy(dtype=np.float32)

    if values.shape != (len(words), ACOUSTIC_DIM):
        raise RuntimeError(
            f"Unexpected acoustic shape {values.shape}; expected {(len(words), ACOUSTIC_DIM)}"
        )
    if not np.isfinite(values).all():
        raise RuntimeError(f"Non-finite acoustic values for {audio_path}")

    return values, feature_names, expanded_windows


def _normalise_columns(columns: Iterable[object]) -> list[str]:
    return [str(column).strip() for column in columns]


def select_word_visual(
    visual_path: str | Path,
    words: Sequence[WordEvidence],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, tuple[str, ...]]:
    """Select the OpenFace frame nearest each word midpoint.

    The five OpenFace metadata fields are retained as quality evidence and
    excluded from the 709-dimensional model payload, matching Table 4 of the
    MAG-BERT-ARL paper.
    """

    visual_path = Path(visual_path)
    if not visual_path.is_file():
        raise FileNotFoundError(visual_path)

    if visual_path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(visual_path)
    elif visual_path.suffix.lower() == ".csv":
        frame = pd.read_csv(visual_path, skipinitialspace=True)
    else:
        raise ValueError(f"Unsupported OpenFace artifact: {visual_path}")

    frame.columns = _normalise_columns(frame.columns)
    missing = set(OPENFACE_METADATA_COLUMNS) - set(frame.columns)
    if missing:
        raise RuntimeError(f"Missing OpenFace metadata columns: {sorted(missing)}")
    if frame.empty:
        raise RuntimeError(f"OpenFace artifact contains no frames: {visual_path}")

    timestamps = frame["timestamp"].to_numpy(dtype=np.float64)
    if not np.isfinite(timestamps).all() or np.any(np.diff(timestamps) < 0):
        raise RuntimeError(f"Invalid OpenFace timestamps: {visual_path}")

    feature_names = tuple(
        column for column in frame.columns if column not in OPENFACE_METADATA_COLUMNS
    )
    if len(feature_names) != VISUAL_DIM:
        raise RuntimeError(
            f"Expected {VISUAL_DIM} OpenFace payload columns, "
            f"found {len(feature_names)} in {visual_path}"
        )

    payload = frame.loc[:, list(feature_names)].to_numpy(dtype=np.float32)
    confidence = frame["confidence"].to_numpy(dtype=np.float32)
    success = frame["success"].to_numpy(dtype=np.uint8)

    selected_indices = np.asarray(
        [int(np.argmin(np.abs(timestamps - ((word.start + word.end) / 2.0)))) for word in words],
        dtype=np.int64,
    )
    selected = payload[selected_indices]
    selected_confidence = confidence[selected_indices]
    selected_success = success[selected_indices]
    midpoints = np.asarray([(word.start + word.end) / 2.0 for word in words], dtype=np.float64)
    selected_delta = np.abs(timestamps[selected_indices] - midpoints).astype(np.float32)

    if selected.shape != (len(words), VISUAL_DIM):
        raise RuntimeError(f"Unexpected visual shape: {selected.shape}")
    if not np.isfinite(selected).all():
        raise RuntimeError(f"Non-finite OpenFace payload: {visual_path}")
    if not np.isfinite(selected_confidence).all():
        raise RuntimeError(f"Non-finite OpenFace confidence: {visual_path}")

    return (
        selected,
        selected_confidence,
        selected_success,
        selected_delta,
        feature_names,
    )


def align_sample(
    *,
    transcript_path: str | Path,
    audio_path: str | Path,
    visual_path: str | Path,
    output_path: str | Path,
    label: float,
    video_id: str,
    acoustic_workers: int = 1,
) -> dict[str, Any]:
    """Create and validate one compressed word-aligned training artifact."""

    if not 0.0 <= float(label) <= 1.0:
        raise ValueError(f"Label must be in [0, 1], received {label}")

    transcript, words = load_words(transcript_path)
    acoustic, acoustic_names, expanded_acoustic_windows = extract_word_acoustic(
        audio_path,
        words,
        num_workers=acoustic_workers,
    )
    (
        visual,
        visual_confidence,
        visual_success,
        visual_time_delta,
        visual_names,
    ) = select_word_visual(visual_path, words)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_path,
        schema_version=np.asarray(SCHEMA_VERSION),
        video_id=np.asarray(video_id),
        label=np.asarray(float(label), dtype=np.float32),
        words=np.asarray([word.text for word in words], dtype=np.str_),
        word_start=np.asarray([word.start for word in words], dtype=np.float32),
        word_end=np.asarray([word.end for word in words], dtype=np.float32),
        word_confidence=np.asarray([word.confidence for word in words], dtype=np.float32),
        acoustic=acoustic,
        visual=visual,
        visual_confidence=visual_confidence,
        visual_success=visual_success,
        visual_time_delta=visual_time_delta,
    )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "video_id": video_id,
        "label": float(label),
        "words": len(words),
        "acoustic_shape": list(acoustic.shape),
        "visual_shape": list(visual.shape),
        "average_word_confidence": float(np.mean([word.confidence for word in words])),
        "visual_success_rate": float(np.mean(visual_success)),
        "average_visual_confidence": float(np.mean(visual_confidence)),
        "maximum_visual_time_delta": float(np.max(visual_time_delta)),
        "expanded_acoustic_windows": expanded_acoustic_windows,
        "minimum_acoustic_window_seconds": MIN_ACOUSTIC_WINDOW_SECONDS,
        "transcript_model": transcript.get("model"),
        "output_path": str(output_path.resolve()),
        "acoustic_feature_names": list(acoustic_names),
        "visual_feature_names": list(visual_names),
    }
    return summary


def load_aligned_sample(path: str | Path) -> AlignedArrays:
    """Load an aligned NPZ without allowing pickled Python objects."""

    with np.load(Path(path), allow_pickle=False) as archive:
        schema = str(archive["schema_version"].item())
        if schema != SCHEMA_VERSION:
            raise RuntimeError(f"Unsupported alignment schema: {schema}")

        acoustic = archive["acoustic"].astype(np.float32, copy=False)
        visual = archive["visual"].astype(np.float32, copy=False)
        video_id = str(archive["video_id"].item())
        label = float(archive["label"].item())
        words = archive["words"].astype(np.str_, copy=False)
        word_start = archive["word_start"].astype(np.float32, copy=False)
        word_end = archive["word_end"].astype(np.float32, copy=False)
        word_confidence = archive["word_confidence"].astype(np.float32, copy=False)
        visual_confidence = archive["visual_confidence"].astype(np.float32, copy=False)
        visual_success = archive["visual_success"].astype(np.uint8, copy=False)
        visual_time_delta = archive["visual_time_delta"].astype(np.float32, copy=False)

    expected_words = len(words)
    if acoustic.shape != (expected_words, ACOUSTIC_DIM):
        raise RuntimeError(f"Invalid acoustic array in {path}: {acoustic.shape}")
    if visual.shape != (expected_words, VISUAL_DIM):
        raise RuntimeError(f"Invalid visual array in {path}: {visual.shape}")
    word_arrays = {
        "word_start": word_start,
        "word_end": word_end,
        "word_confidence": word_confidence,
        "visual_confidence": visual_confidence,
        "visual_success": visual_success,
        "visual_time_delta": visual_time_delta,
    }
    for name, values in word_arrays.items():
        if values.shape != (expected_words,):
            raise RuntimeError(f"Invalid {name} array in {path}: {values.shape}")
    numeric_arrays = (
        acoustic,
        visual,
        word_start,
        word_end,
        word_confidence,
        visual_confidence,
        visual_time_delta,
    )
    if not all(np.isfinite(values).all() for values in numeric_arrays):
        raise RuntimeError(f"Non-finite value in aligned artifact: {path}")
    if not video_id or not 0.0 <= label <= 1.0:
        raise RuntimeError(f"Invalid identity or label in aligned artifact: {path}")
    if np.any(word_end <= word_start) or np.any(np.diff(word_start) < -0.05):
        raise RuntimeError(f"Invalid word timestamps in aligned artifact: {path}")
    if np.any((word_confidence < 0.0) | (word_confidence > 1.0)):
        raise RuntimeError(f"Invalid word confidence in aligned artifact: {path}")
    if np.any((visual_success != 0) & (visual_success != 1)):
        raise RuntimeError(f"Invalid visual success flag in aligned artifact: {path}")

    return AlignedArrays(
        video_id=video_id,
        label=label,
        words=words,
        word_start=word_start,
        word_end=word_end,
        word_confidence=word_confidence,
        acoustic=acoustic,
        visual=visual,
        visual_confidence=visual_confidence,
        visual_success=visual_success,
        visual_time_delta=visual_time_delta,
        acoustic_feature_names=(),
        visual_feature_names=(),
    )
