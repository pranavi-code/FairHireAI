"""Synthetic one-epoch integration smoke for Trainer and checkpoint restore."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
from transformers import AutoTokenizer, BertConfig, BertModel

from ml_service.preprocessing.alignment import SCHEMA_VERSION
from ml_service.training.engine import Trainer, TrainingConfig


def write_sample(root: Path, split: str, index: int) -> None:
    sample = root / "preprocessed" / split / f"sample_{index}"
    sample.mkdir(parents=True)
    rng = np.random.default_rng(index)
    words = np.asarray(["clear", "backend", "api", "answer"])
    np.savez_compressed(
        sample / "aligned.npz",
        schema_version=np.asarray(SCHEMA_VERSION),
        video_id=np.asarray(f"sample_{index}.mp4"),
        label=np.asarray(0.25 + index * 0.1, dtype=np.float32),
        words=words,
        word_start=np.arange(4, dtype=np.float32),
        word_end=np.arange(4, dtype=np.float32) + 0.5,
        word_confidence=np.ones(4, dtype=np.float32),
        acoustic=rng.normal(size=(4, 88)).astype(np.float32),
        visual=rng.normal(size=(4, 709)).astype(np.float32),
        visual_confidence=np.ones(4, dtype=np.float32),
        visual_success=np.ones(4, dtype=np.uint8),
        visual_time_delta=np.zeros(4, dtype=np.float32),
    )
    status = {
        "state": "complete",
        "video_id": f"sample_{index}.mp4",
        "label": 0.25 + index * 0.1,
        "stages": {"openface": {"quality": "good"}},
    }
    (sample / "status.json").write_text(json.dumps(status), encoding="utf-8")


def main() -> None:
    model_source = Path("D:/FairHireAI-data/models/bert-base-uncased")
    with tempfile.TemporaryDirectory(
        prefix="fairhire_training_smoke_", dir=Path.cwd()
    ) as temporary:
        root = Path(temporary)
        tiny_model_root = root / "tiny_bert"
        tokenizer = AutoTokenizer.from_pretrained(
            model_source, use_fast=True, local_files_only=True
        )
        tokenizer.save_pretrained(tiny_model_root)
        tiny_config = BertConfig(
            vocab_size=tokenizer.vocab_size,
            hidden_size=64,
            num_hidden_layers=2,
            num_attention_heads=4,
            intermediate_size=128,
            max_position_embeddings=256,
        )
        BertModel(tiny_config).save_pretrained(tiny_model_root, safe_serialization=True)
        write_sample(root, "train", 0)
        write_sample(root, "train", 1)
        write_sample(root, "validation", 2)
        write_sample(root, "validation", 3)
        config = TrainingConfig(
            run_name="synthetic_smoke",
            model_type="arl",
            model_name_or_path=str(tiny_model_root),
            preprocessed_root=str(root / "preprocessed"),
            output_dir=str(root / "run"),
            scaler_path=str(root / "preprocessed" / "scaler.npz"),
            modalities="text_audio_visual",
            max_length=16,
            batch_size=2,
            epochs=1,
            arl_pretrain_epochs=0,
            arl_virtual_batch_size=2,
            early_stopping_patience=1,
            expected_train_samples=2,
            expected_validation_samples=2,
        )
        result = Trainer(config).fit()
        latest = root / "run" / "latest.pt"
        best = root / "run" / "best.pt"
        predictions = root / "run" / "best_validation_predictions.csv"
        if not all(path.is_file() for path in (latest, best, predictions)):
            raise RuntimeError("Trainer did not create all required artifacts")
        restored_epoch, _, _ = Trainer(config).restore(latest)
        if restored_epoch != 1:
            raise RuntimeError(f"Unexpected restored epoch: {restored_epoch}")
        print(
            json.dumps(
                {
                    **result,
                    "checkpoint_restore_epoch": restored_epoch,
                    "temporary_artifacts_cleaned": True,
                },
                indent=2,
            )
        )
        print("TRAINING ENGINE SMOKE PASSED")


if __name__ == "__main__":
    main()
