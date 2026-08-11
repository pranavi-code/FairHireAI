from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ml_service.preprocessing.alignment import SCHEMA_VERSION
from ml_service.training.data import (
    FIDataset,
    discover_records,
    fit_train_standardizer,
)


class FakeEncoding(dict):
    def word_ids(self) -> list[int | None]:
        return [None, 0, 0, 1, None, None]


class FakeTokenizer:
    is_fast = True

    def __call__(self, words: list[str], **_: object) -> FakeEncoding:
        assert words == ["hello", "world"]
        return FakeEncoding(
            input_ids=[101, 10, 11, 12, 102, 0],
            attention_mask=[1, 1, 1, 1, 1, 0],
            token_type_ids=[0, 0, 0, 0, 0, 0],
        )


def write_sample(root: Path, split: str, stem: str, label: float, offset: float) -> None:
    sample_root = root / split / stem
    sample_root.mkdir(parents=True)
    acoustic = np.stack(
        (
            np.full(88, offset, dtype=np.float32),
            np.full(88, offset + 2.0, dtype=np.float32),
        )
    )
    visual = np.stack(
        (
            np.full(709, offset, dtype=np.float32),
            np.full(709, offset + 2.0, dtype=np.float32),
        )
    )
    np.savez_compressed(
        sample_root / "aligned.npz",
        schema_version=np.asarray(SCHEMA_VERSION),
        video_id=np.asarray(f"{stem}.mp4"),
        label=np.asarray(label, dtype=np.float32),
        words=np.asarray(["hello", "world"]),
        word_start=np.asarray([0.0, 0.5], dtype=np.float32),
        word_end=np.asarray([0.4, 0.9], dtype=np.float32),
        word_confidence=np.ones(2, dtype=np.float32),
        acoustic=acoustic,
        visual=visual,
        visual_confidence=np.ones(2, dtype=np.float32),
        visual_success=np.asarray([1, 0], dtype=np.uint8),
        visual_time_delta=np.zeros(2, dtype=np.float32),
    )
    status = {
        "state": "complete",
        "video_id": f"{stem}.mp4",
        "label": label,
        "stages": {"openface": {"quality": "good"}},
    }
    (sample_root / "status.json").write_text(json.dumps(status), encoding="utf-8")


def test_standardizer_uses_training_split_only_and_maps_subwords(tmp_path: Path) -> None:
    write_sample(tmp_path, "train", "train_one", 0.4, 0.0)
    write_sample(tmp_path, "validation", "validation_one", 0.8, 100.0)
    records = discover_records(tmp_path)
    standardizer = fit_train_standardizer(records)

    assert standardizer.fitted_samples == 1
    assert standardizer.fitted_words == 2
    assert standardizer.fitted_visual_words == 1
    np.testing.assert_allclose(standardizer.acoustic_mean, 1.0)
    np.testing.assert_allclose(standardizer.visual_mean, 0.0)

    dataset = FIDataset(
        [record for record in records if record.split == "train"],
        FakeTokenizer(),
        standardizer,
        max_length=6,
    )
    item = dataset[0]
    assert item["acoustic"].shape == (6, 88)
    assert item["visual"].shape == (6, 709)
    np.testing.assert_allclose(item["acoustic"][1].numpy(), -1.0)
    np.testing.assert_allclose(item["acoustic"][2].numpy(), -1.0)
    np.testing.assert_allclose(item["acoustic"][3].numpy(), 1.0)
    np.testing.assert_allclose(item["visual"][3].numpy(), 0.0)
    assert item["modality_mask"].tolist() == [0.0, 1.0, 1.0, 1.0, 0.0, 0.0]
