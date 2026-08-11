from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.app.domain.answer_evaluation import calculate_delivery_metrics
from backend.app.services.answer_evaluation import AnswerEvaluationService


class FakeGemini:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result
        self.last_prompt = ""
        self.last_schema: dict[str, object] = {}

    def generate_json(self, **kwargs: object) -> dict[str, object]:
        self.last_prompt = str(kwargs["prompt"])
        self.last_schema = kwargs["response_schema"]  # type: ignore[assignment]
        return self.result


def _write_wave(path: Path) -> None:
    rate = 16_000
    time = np.arange(rate * 2, dtype=np.float32) / rate
    samples = (0.15 * np.sin(2 * np.pi * 220 * time) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(samples.tobytes())


def test_delivery_metrics_are_observable_and_bounded(tmp_path: Path) -> None:
    audio = tmp_path / "answer.wav"
    visual = tmp_path / "answer.csv"
    _write_wave(audio)
    pd.DataFrame(
        {
            "success": [1, 1, 1, 1],
            "pose_Rx": [0.01, 0.02, 0.01, 0.02],
            "pose_Ry": [0.03, 0.02, 0.03, 0.02],
            "pose_Rz": [0.01, 0.01, 0.02, 0.02],
        }
    ).to_csv(visual, index=False)
    transcript = {
        "average_word_confidence": 0.9,
        "segments": [
            {
                "words": [
                    {"text": "So", "start": 0.0, "end": 0.2, "confidence": 0.9},
                    {"text": "I", "start": 1.2, "end": 1.3, "confidence": 0.9},
                    {"text": "validate", "start": 1.3, "end": 1.7, "confidence": 0.9},
                ]
            }
        ],
    }

    result = calculate_delivery_metrics(
        transcript=transcript,
        audio_path=audio,
        openface_path=visual,
        duration_seconds=2,
    )

    assert result.word_count == 3
    assert result.filler_count == 1
    assert result.pause_count == 1
    assert result.visual_success_rate == 1
    assert result.camera_facing_estimate == 1
    assert 0 <= result.signal_quality <= 1
    assert "do not infer emotion" in result.note


def test_evaluator_uses_frozen_evidence_and_rejects_wrong_followup_shape() -> None:
    payload = {
        "competency_id": "api_design",
        "competency_rubric_score": 0.8,
        "competency_coverage": 0.8,
        "answer_depth_and_correctness": 0.8,
        "answer_relevance": 0.9,
        "answer_structure": 0.8,
        "answer_completeness": 0.8,
        "resume_project_consistency": 0.5,
        "follow_up_responsiveness": None,
        "professionalism_rubric": 0.9,
        "evidence_confidence": 0.85,
        "criterion_evidence": [
            {
                "criterion": "authorization",
                "score": 0.8,
                "rationale": "The answer names ownership checks.",
                "citations": [
                    {"text": "check resource ownership", "start_seconds": 1, "end_seconds": 2}
                ],
            }
        ],
        "missing_concepts": [],
        "weakest_criterion": None,
        "high_confidence_resume_contradiction": False,
        "safety_note": "Evidence-only student practice assessment; no hiring decision.",
    }
    gemini = FakeGemini(payload)
    service = AnswerEvaluationService(gemini)  # type: ignore[arg-type]
    result = service.evaluate(
        competency_id="api_design",
        prompt_snapshot="Explain authorization for this profile update endpoint.",
        expected_concepts=["authorization"],
        rubric={"1": "poor", "2": "partial", "3": "basic", "4": "good", "5": "excellent"},
        source_mapping={"SRC-013": ["authorization"]},
        transcript={
            "text": "I check resource ownership.",
            "segments": [],
            "average_word_confidence": 0.9,
        },
        resume_claims=[],
        is_follow_up=False,
    )
    assert result.competency_rubric_score == 0.8
    assert "SRC-013" in gemini.last_prompt
    schema_text = str(gemini.last_schema)
    for unsupported in ("exclusiveMinimum", "const", "title", "default", "anyOf"):
        assert unsupported not in schema_text
    properties = gemini.last_schema["properties"]
    assert isinstance(properties, dict)
    assert "follow_up_responsiveness" not in properties

    payload["safety_note"] = "None"
    normalized = service.evaluate(
        competency_id="api_design",
        prompt_snapshot="Explain authorization for this profile update endpoint.",
        expected_concepts=["authorization"],
        rubric={"1": "poor", "2": "partial", "3": "basic", "4": "good", "5": "excellent"},
        source_mapping={"SRC-013": ["authorization"]},
        transcript={"text": "I check resource ownership.", "segments": []},
        resume_claims=[],
        is_follow_up=False,
    )
    assert "no hiring decision" in normalized.safety_note

    payload["follow_up_responsiveness"] = 0.7
    with pytest.raises(ValueError, match="Core-answer"):
        service.evaluate(
            competency_id="api_design",
            prompt_snapshot="Explain authorization for this profile update endpoint.",
            expected_concepts=["authorization"],
            rubric={
                "1": "poor",
                "2": "partial",
                "3": "basic",
                "4": "good",
                "5": "excellent",
            },
            source_mapping={"SRC-013": ["authorization"]},
            transcript={"text": "I check ownership.", "segments": []},
            resume_claims=[],
            is_follow_up=False,
        )
