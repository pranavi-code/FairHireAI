"""Load a training checkpoint exactly and infer from one aligned artifact."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
from transformers import AutoTokenizer

from ml_service.preprocessing.alignment import (
    ACOUSTIC_DIM,
    VISUAL_DIM,
    AlignedArrays,
    load_aligned_sample,
)
from ml_service.training.data import FeatureStandardizer
from ml_service.training.engine import TrainingConfig
from ml_service.training.models import InterviewSignalModel


@dataclass(frozen=True)
class InferenceOutput:
    base_multimodal_interview_signal: float
    signal_quality: float
    model_run_name: str
    checkpoint_sha256: str
    input_artifact_sha256: str
    generated_at: datetime


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class CheckpointInferenceRuntime:
    """Inference-only runtime reconstructed from the checkpoint's saved config."""

    def __init__(
        self,
        checkpoint_path: str | Path,
        *,
        expected_sha256: str,
        device: str | None = None,
        model_name_or_path: str | Path | None = None,
        scaler_path: str | Path | None = None,
    ) -> None:
        self.checkpoint_path = Path(checkpoint_path).resolve()
        if not self.checkpoint_path.is_file():
            raise FileNotFoundError(self.checkpoint_path)
        self.checkpoint_sha256 = _sha256(self.checkpoint_path)
        if self.checkpoint_sha256 != expected_sha256:
            raise RuntimeError("Checkpoint SHA-256 does not match the configured model version")

        target_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.device = torch.device(target_device)
        checkpoint = torch.load(
            self.checkpoint_path,
            map_location=self.device,
            weights_only=False,
        )
        if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("config"), dict):
            raise RuntimeError("Checkpoint does not contain a valid training configuration")
        self.config = TrainingConfig(**checkpoint["config"])
        self.config.validate()
        resolved_model_root = str(model_name_or_path or self.config.model_name_or_path)
        resolved_scaler_path = str(scaler_path or self.config.scaler_path)
        self.standardizer = FeatureStandardizer.load(resolved_scaler_path)
        self.tokenizer = AutoTokenizer.from_pretrained(
            resolved_model_root,
            use_fast=True,
            local_files_only=True,
        )
        self.model = InterviewSignalModel.from_pretrained(
            resolved_model_root,
            multimodal=self.config.model_type in {"mag", "arl"},
            beta_shift=self.config.beta_shift,
            dropout=self.config.dropout,
            adversarial=self.config.model_type == "arl",
            use_acoustic=self.config.modalities in {"text_audio", "text_audio_visual"},
            use_visual=self.config.modalities in {"text_visual", "text_audio_visual"},
        )
        self.model.load_state_dict(checkpoint["model"])
        self.model.to(self.device)
        self.model.eval()

    def _batch(self, sample: AlignedArrays) -> dict[str, torch.Tensor]:
        words = sample.words.tolist()
        encoded = self.tokenizer(
            words,
            is_split_into_words=True,
            add_special_tokens=True,
            max_length=self.config.max_length,
            padding="max_length",
            truncation=True,
            return_attention_mask=True,
        )
        word_ids = encoded.word_ids()
        acoustic_words = self.standardizer.transform_acoustic(sample.acoustic)
        visual_words = self.standardizer.transform_visual(sample.visual)
        visual_words = visual_words * sample.visual_success[:, None].astype(np.float32)
        acoustic = np.zeros((self.config.max_length, ACOUSTIC_DIM), dtype=np.float32)
        visual = np.zeros((self.config.max_length, VISUAL_DIM), dtype=np.float32)
        modality_mask = np.zeros(self.config.max_length, dtype=np.float32)
        for token_index, word_index in enumerate(word_ids):
            if word_index is None:
                continue
            acoustic[token_index] = acoustic_words[word_index]
            visual[token_index] = visual_words[word_index]
            modality_mask[token_index] = 1.0
        batch: dict[str, Any] = {
            "input_ids": torch.tensor(encoded["input_ids"], dtype=torch.long),
            "attention_mask": torch.tensor(encoded["attention_mask"], dtype=torch.long),
            "acoustic": torch.from_numpy(acoustic),
            "visual": torch.from_numpy(visual),
            "modality_mask": torch.from_numpy(modality_mask),
        }
        if "token_type_ids" in encoded:
            batch["token_type_ids"] = torch.tensor(
                encoded["token_type_ids"],
                dtype=torch.long,
            )
        return {
            key: value.unsqueeze(0).to(self.device)
            for key, value in batch.items()
        }

    def predict_aligned(self, artifact_path: str | Path) -> InferenceOutput:
        artifact = Path(artifact_path).resolve()
        sample = load_aligned_sample(artifact)
        with torch.inference_mode():
            prediction = float(self.model(**self._batch(sample)).prediction.item())

        transcript_quality = float(np.mean(sample.word_confidence))
        if self.config.modalities in {"text_visual", "text_audio_visual"}:
            visual_quality = float(np.mean(sample.visual_success))
        else:
            visual_quality = 1.0
        signal_quality = max(0.0, min(1.0, transcript_quality * visual_quality))
        return InferenceOutput(
            base_multimodal_interview_signal=max(0.0, min(1.0, prediction)),
            signal_quality=signal_quality,
            model_run_name=self.config.run_name,
            checkpoint_sha256=self.checkpoint_sha256,
            input_artifact_sha256=_sha256(artifact),
            generated_at=datetime.now(timezone.utc),
        )
