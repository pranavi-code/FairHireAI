"""Evidence-only technical evaluation and observable delivery measurements."""

from __future__ import annotations

import math
import wave
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, model_validator

FILLERS = {
    "ah",
    "basically",
    "erm",
    "hmm",
    "like",
    "literally",
    "so",
    "uh",
    "um",
}


class TranscriptCitation(BaseModel):
    text: str = Field(min_length=1, max_length=1_000)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_interval(self) -> TranscriptCitation:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("Transcript citation end must follow its start")
        return self


class CriterionEvidence(BaseModel):
    criterion: str = Field(min_length=2, max_length=500)
    score: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=5, max_length=1_000)
    citations: list[TranscriptCitation] = Field(default_factory=list, max_length=8)


class TechnicalAnswerEvaluation(BaseModel):
    schema_version: Literal["technical-answer-evaluation-v1"] = (
        "technical-answer-evaluation-v1"
    )
    competency_id: str
    competency_rubric_score: float = Field(ge=0, le=1)
    competency_coverage: float = Field(ge=0, le=1)
    answer_depth_and_correctness: float = Field(ge=0, le=1)
    answer_relevance: float = Field(ge=0, le=1)
    answer_structure: float = Field(ge=0, le=1)
    answer_completeness: float = Field(ge=0, le=1)
    resume_project_consistency: float = Field(ge=0, le=1)
    follow_up_responsiveness: float | None = Field(default=None, ge=0, le=1)
    professionalism_rubric: float = Field(ge=0, le=1)
    evidence_confidence: float = Field(ge=0, le=1)
    criterion_evidence: list[CriterionEvidence] = Field(min_length=1, max_length=20)
    missing_concepts: list[str] = Field(default_factory=list, max_length=20)
    weakest_criterion: str | None = Field(default=None, max_length=500)
    high_confidence_resume_contradiction: bool = False
    safety_note: str = Field(min_length=20, max_length=1_000)


class DeliveryMetrics(BaseModel):
    schema_version: Literal["observable-delivery-v1"] = "observable-delivery-v1"
    duration_seconds: float = Field(gt=0)
    word_count: int = Field(ge=0)
    words_per_minute: float = Field(ge=0)
    pause_count: int = Field(ge=0)
    average_pause_seconds: float = Field(ge=0)
    filler_count: int = Field(ge=0)
    filler_rate: float = Field(ge=0, le=1)
    pace_and_filler_quality: float = Field(ge=0, le=1)
    voice_energy_consistency: float | None = Field(default=None, ge=0, le=1)
    head_stability: float | None = Field(default=None, ge=0, le=1)
    camera_facing_estimate: float | None = Field(default=None, ge=0, le=1)
    transcript_confidence: float = Field(ge=0, le=1)
    visual_success_rate: float = Field(ge=0, le=1)
    signal_quality: float = Field(ge=0, le=1)
    note: str = (
        "These are observable delivery measurements only. They do not infer "
        "emotion, personality, confidence, nervousness, or employability."
    )


def _clip(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def _audio_energy_consistency(audio_path: Path) -> float | None:
    with wave.open(str(audio_path), "rb") as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            return None
        rate = source.getframerate()
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype=np.int16)
    if len(samples) < rate // 2:
        return None
    window = max(1, rate // 5)
    usable = samples[: len(samples) - (len(samples) % window)].astype(np.float32)
    if usable.size == 0:
        return None
    frames = usable.reshape(-1, window) / 32768.0
    rms = np.sqrt(np.mean(np.square(frames), axis=1))
    voiced = rms[rms > max(0.003, float(np.percentile(rms, 20)))]
    if voiced.size < 2 or float(np.mean(voiced)) <= 1e-8:
        return None
    coefficient_of_variation = float(np.std(voiced) / np.mean(voiced))
    return _clip(1.0 - coefficient_of_variation / 1.5)


def _visual_delivery(openface_path: Path) -> tuple[float | None, float | None, float]:
    frame = pd.read_csv(openface_path, skipinitialspace=True)
    frame.columns = [str(column).strip() for column in frame.columns]
    successful = frame.loc[frame["success"] == 1]
    success_rate = float(len(successful) / len(frame)) if len(frame) else 0.0
    if successful.empty:
        return None, None, success_rate

    pose_columns = [name for name in ("pose_Rx", "pose_Ry", "pose_Rz") if name in frame]
    head_stability: float | None = None
    if pose_columns:
        pose = successful.loc[:, pose_columns].to_numpy(dtype=np.float64)
        angular_variation = float(np.mean(np.std(pose, axis=0)))
        head_stability = _clip(1.0 - angular_variation / 0.35)

    camera_facing: float | None = None
    if {"pose_Rx", "pose_Ry"}.issubset(successful.columns):
        pitch = successful["pose_Rx"].to_numpy(dtype=np.float64)
        yaw = successful["pose_Ry"].to_numpy(dtype=np.float64)
        camera_facing = float(np.mean((np.abs(pitch) <= 0.35) & (np.abs(yaw) <= 0.35)))
    return head_stability, camera_facing, success_rate


def calculate_delivery_metrics(
    *,
    transcript: dict[str, object],
    audio_path: str | Path,
    openface_path: str | Path,
    duration_seconds: float,
) -> DeliveryMetrics:
    words = [
        raw_word
        for segment in transcript.get("segments", [])
        if isinstance(segment, dict)
        for raw_word in segment.get("words", [])
        if isinstance(raw_word, dict)
    ]
    cleaned = [
        str(word.get("text", "")).strip().casefold().strip(".,!?;:")
        for word in words
    ]
    filler_count = sum(word in FILLERS for word in cleaned)
    filler_rate = filler_count / max(1, len(cleaned))
    pauses = []
    for previous, current in zip(words, words[1:], strict=False):
        try:
            pause = float(current["start"]) - float(previous["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if pause >= 0.8:
            pauses.append(pause)

    words_per_minute = len(words) * 60.0 / max(duration_seconds, 1e-6)
    # A broad 90-180 wpm range avoids penalising accent or deliberate pauses.
    pace_quality = _clip(1.0 - abs(words_per_minute - 135.0) / 135.0)
    filler_quality = _clip(1.0 - filler_rate / 0.15)
    pace_and_filler = 0.65 * pace_quality + 0.35 * filler_quality

    transcript_confidence = float(
        transcript.get("average_word_confidence")
        or (
            np.mean([float(word.get("confidence", 0.0)) for word in words])
            if words
            else 0.0
        )
    )
    energy = _audio_energy_consistency(Path(audio_path))
    head_stability, camera_facing, visual_success = _visual_delivery(Path(openface_path))
    visual_confidence = (
        math.sqrt(max(0.0, head_stability * camera_facing))
        if head_stability is not None and camera_facing is not None
        else visual_success
    )
    signal_quality = _clip(transcript_confidence * visual_success * visual_confidence)
    return DeliveryMetrics(
        duration_seconds=duration_seconds,
        word_count=len(words),
        words_per_minute=round(words_per_minute, 3),
        pause_count=len(pauses),
        average_pause_seconds=round(float(np.mean(pauses)) if pauses else 0.0, 3),
        filler_count=filler_count,
        filler_rate=round(filler_rate, 6),
        pace_and_filler_quality=round(pace_and_filler, 6),
        voice_energy_consistency=round(energy, 6) if energy is not None else None,
        head_stability=(
            round(head_stability, 6) if head_stability is not None else None
        ),
        camera_facing_estimate=(
            round(camera_facing, 6) if camera_facing is not None else None
        ),
        transcript_confidence=round(_clip(transcript_confidence), 6),
        visual_success_rate=round(_clip(visual_success), 6),
        signal_quality=round(signal_quality, 6),
    )
