"""Leakage-safe FI V2 feature scaling and PyTorch datasets."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import Dataset

from ml_service.preprocessing.alignment import (
    ACOUSTIC_DIM,
    VISUAL_DIM,
    load_aligned_sample,
)

SCALER_SCHEMA_VERSION = "fi-train-only-standardizer-v2"


@dataclass(frozen=True)
class SampleRecord:
    video_id: str
    split: str
    label: float
    aligned_path: str
    visual_quality: str
    source_sha256: str


@dataclass(frozen=True)
class FeatureStandardizer:
    acoustic_mean: np.ndarray
    acoustic_scale: np.ndarray
    visual_mean: np.ndarray
    visual_scale: np.ndarray
    fitted_words: int
    fitted_visual_words: int
    fitted_samples: int

    def transform_acoustic(self, values: np.ndarray) -> np.ndarray:
        return ((values - self.acoustic_mean) / self.acoustic_scale).astype(np.float32, copy=False)

    def transform_visual(self, values: np.ndarray) -> np.ndarray:
        return ((values - self.visual_mean) / self.visual_scale).astype(np.float32, copy=False)

    def save(self, path: str | Path) -> None:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            output,
            schema_version=np.asarray(SCALER_SCHEMA_VERSION),
            acoustic_mean=self.acoustic_mean,
            acoustic_scale=self.acoustic_scale,
            visual_mean=self.visual_mean,
            visual_scale=self.visual_scale,
            fitted_words=np.asarray(self.fitted_words, dtype=np.int64),
            fitted_visual_words=np.asarray(self.fitted_visual_words, dtype=np.int64),
            fitted_samples=np.asarray(self.fitted_samples, dtype=np.int64),
        )

    @classmethod
    def load(cls, path: str | Path) -> FeatureStandardizer:
        with np.load(Path(path), allow_pickle=False) as archive:
            schema = str(archive["schema_version"].item())
            if schema != SCALER_SCHEMA_VERSION:
                raise RuntimeError(f"Unsupported scaler schema: {schema}")
            return cls(
                acoustic_mean=archive["acoustic_mean"].astype(np.float32),
                acoustic_scale=archive["acoustic_scale"].astype(np.float32),
                visual_mean=archive["visual_mean"].astype(np.float32),
                visual_scale=archive["visual_scale"].astype(np.float32),
                fitted_words=int(archive["fitted_words"].item()),
                fitted_visual_words=int(archive["fitted_visual_words"].item()),
                fitted_samples=int(archive["fitted_samples"].item()),
            )


def discover_records(preprocessed_root: str | Path) -> list[SampleRecord]:
    root = Path(preprocessed_root).resolve()
    records: list[SampleRecord] = []
    for split in ("train", "validation"):
        for status_path in sorted((root / split).glob("*/status.json")):
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if status.get("state") != "complete":
                continue
            aligned_path = status_path.parent / "aligned.npz"
            if not aligned_path.is_file():
                continue
            label = float(status["label"])
            if not 0.0 <= label <= 1.0:
                raise RuntimeError(f"Invalid label in {status_path}")
            records.append(
                SampleRecord(
                    video_id=str(status["video_id"]),
                    split=split,
                    label=label,
                    aligned_path=str(aligned_path),
                    visual_quality=str(
                        status.get("stages", {}).get("openface", {}).get("quality", "unknown")
                    ),
                    source_sha256=str(status.get("source_sha256", "")),
                )
            )
    records.sort(key=lambda record: (record.split, record.video_id))
    return records


def dataset_identity_sha256(records: list[SampleRecord]) -> str:
    """Bind a training run to the exact audited split/video/source identities."""

    identities = [
        f"{record.split}|{record.video_id}|{record.source_sha256}"
        for record in records
    ]
    return hashlib.sha256(
        "\n".join(sorted(identities)).encode("utf-8")
    ).hexdigest()


def write_index(records: list[SampleRecord], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(asdict(record), sort_keys=True) for record in records]
    output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def fit_train_standardizer(records: list[SampleRecord]) -> FeatureStandardizer:
    train_records = [record for record in records if record.split == "train"]
    if not train_records:
        raise RuntimeError("No completed training samples were found")
    acoustic_sum = np.zeros(ACOUSTIC_DIM, dtype=np.float64)
    acoustic_square_sum = np.zeros(ACOUSTIC_DIM, dtype=np.float64)
    visual_sum = np.zeros(VISUAL_DIM, dtype=np.float64)
    visual_square_sum = np.zeros(VISUAL_DIM, dtype=np.float64)
    word_count = 0
    visual_word_count = 0
    for index, record in enumerate(train_records, start=1):
        sample = load_aligned_sample(record.aligned_path)
        acoustic = sample.acoustic.astype(np.float64)
        visual = sample.visual[sample.visual_success == 1].astype(np.float64)
        acoustic_sum += acoustic.sum(axis=0)
        acoustic_square_sum += np.square(acoustic).sum(axis=0)
        visual_sum += visual.sum(axis=0)
        visual_square_sum += np.square(visual).sum(axis=0)
        word_count += len(sample.words)
        visual_word_count += len(visual)
        if index % 500 == 0:
            print(f"  scaler: {index}/{len(train_records)} training samples", flush=True)
    if word_count < 1 or visual_word_count < 1:
        raise RuntimeError("Training samples contain no aligned words")

    def moments(
        total: np.ndarray, squares: np.ndarray, count: int
    ) -> tuple[np.ndarray, np.ndarray]:
        mean = total / count
        variance = np.maximum(squares / count - np.square(mean), 0.0)
        scale = np.sqrt(variance)
        scale[scale < 1e-8] = 1.0
        return mean.astype(np.float32), scale.astype(np.float32)

    acoustic_mean, acoustic_scale = moments(acoustic_sum, acoustic_square_sum, word_count)
    visual_mean, visual_scale = moments(visual_sum, visual_square_sum, visual_word_count)
    return FeatureStandardizer(
        acoustic_mean=acoustic_mean,
        acoustic_scale=acoustic_scale,
        visual_mean=visual_mean,
        visual_scale=visual_scale,
        fitted_words=word_count,
        fitted_visual_words=visual_word_count,
        fitted_samples=len(train_records),
    )


class FIDataset(Dataset[dict[str, Any]]):
    def __init__(
        self,
        records: list[SampleRecord],
        tokenizer: Any,
        standardizer: FeatureStandardizer,
        *,
        max_length: int = 176,
    ) -> None:
        if not getattr(tokenizer, "is_fast", False):
            raise ValueError("A fast tokenizer is required for word/subword alignment")
        self.records = records
        self.tokenizer = tokenizer
        self.standardizer = standardizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, Any]:
        record = self.records[index]
        sample = load_aligned_sample(record.aligned_path)
        if sample.video_id != record.video_id or not np.isclose(sample.label, record.label):
            raise RuntimeError(f"Aligned identity/label mismatch for {record.video_id}")
        words = sample.words.tolist()
        encoded = self.tokenizer(
            words,
            is_split_into_words=True,
            add_special_tokens=True,
            max_length=self.max_length,
            padding="max_length",
            truncation=True,
            return_attention_mask=True,
        )
        word_ids = encoded.word_ids()
        acoustic_words = self.standardizer.transform_acoustic(sample.acoustic)
        visual_words = self.standardizer.transform_visual(sample.visual)
        visual_words = visual_words * sample.visual_success[:, None].astype(np.float32)
        acoustic = np.zeros((self.max_length, ACOUSTIC_DIM), dtype=np.float32)
        visual = np.zeros((self.max_length, VISUAL_DIM), dtype=np.float32)
        modality_mask = np.zeros(self.max_length, dtype=np.float32)
        for token_index, word_index in enumerate(word_ids):
            if word_index is None:
                continue
            acoustic[token_index] = acoustic_words[word_index]
            visual[token_index] = visual_words[word_index]
            modality_mask[token_index] = 1.0
        result: dict[str, Any] = {
            "input_ids": torch.tensor(encoded["input_ids"], dtype=torch.long),
            "attention_mask": torch.tensor(encoded["attention_mask"], dtype=torch.long),
            "acoustic": torch.from_numpy(acoustic),
            "visual": torch.from_numpy(visual),
            "modality_mask": torch.from_numpy(modality_mask),
            "label": torch.tensor(record.label, dtype=torch.float32),
            "video_id": record.video_id,
        }
        if "token_type_ids" in encoded:
            result["token_type_ids"] = torch.tensor(encoded["token_type_ids"], dtype=torch.long)
        return result
