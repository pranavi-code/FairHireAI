"""Reproducible training engine with validation, checkpoints, and resume."""

from __future__ import annotations

import csv
import json
import math
import random
import shutil
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader
from transformers import AutoTokenizer, get_linear_schedule_with_warmup

from ml_service.training.data import (
    FeatureStandardizer,
    FIDataset,
    dataset_identity_sha256,
    discover_records,
    fit_train_standardizer,
    write_index,
)
from ml_service.training.models import InterviewSignalModel


@dataclass(frozen=True)
class TrainingConfig:
    run_name: str
    model_type: str
    model_name_or_path: str
    preprocessed_root: str
    output_dir: str
    scaler_path: str
    modalities: str = "text_audio_visual"
    loss: str = "mse"
    max_length: int = 176
    batch_size: int = 2
    epochs: int = 10
    learning_rate: float = 1e-5
    adversary_learning_rate: float = 1e-5
    weight_decay: float = 0.01
    dropout: float = 0.5
    beta_shift: float = 1.0
    warmup_ratio: float = 0.1
    gradient_accumulation_steps: int = 1
    max_grad_norm: float = 1.0
    frozen_bert_layers: int = 0
    arl_pretrain_epochs: int = 6
    arl_virtual_batch_size: int = 128
    early_stopping_patience: int = 5
    num_workers: int = 0
    seed: int = 8
    expected_train_samples: int = 6000
    expected_validation_samples: int = 2000
    decision_threshold: float = 0.5
    amp: bool = True
    preprocessing_audit_path: str | None = None

    @classmethod
    def load(cls, path: str | Path) -> TrainingConfig:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**payload)

    def validate(self) -> None:
        if self.model_type not in {"text", "mag", "arl"}:
            raise ValueError(f"Unsupported model_type: {self.model_type}")
        if self.loss not in {"mse", "bce", "mse_bce"}:
            raise ValueError(f"Unsupported loss: {self.loss}")
        allowed_modalities = {
            "text",
            "text_audio",
            "text_visual",
            "text_audio_visual",
        }
        if self.modalities not in allowed_modalities:
            raise ValueError(f"Unsupported modalities: {self.modalities}")
        if self.model_type == "text" and self.modalities != "text":
            raise ValueError("The text model requires modalities='text'")
        if self.model_type in {"mag", "arl"} and self.modalities == "text":
            raise ValueError("MAG/ARL requires at least one non-text modality")
        if self.model_type == "arl" and self.gradient_accumulation_steps != 1:
            raise ValueError("ARL currently requires gradient_accumulation_steps=1")
        if self.model_type == "arl" and self.arl_virtual_batch_size < 2:
            raise ValueError("ARL requires arl_virtual_batch_size >= 2")
        if self.model_type == "arl" and self.arl_virtual_batch_size % self.batch_size != 0:
            raise ValueError("arl_virtual_batch_size must be divisible by physical batch_size")
        if self.epochs <= 0 or self.batch_size <= 0:
            raise ValueError("epochs and batch_size must be positive")


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def per_sample_loss(
    prediction: torch.Tensor,
    target: torch.Tensor,
    kind: str,
    *,
    logits: torch.Tensor | None = None,
) -> torch.Tensor:
    prediction = prediction.float()
    target = target.float()
    mse = torch.square(prediction - target)
    if kind == "mse":
        return mse
    if logits is None:
        logits = torch.logit(prediction.clamp(1e-6, 1.0 - 1e-6))
    bce = nn.functional.binary_cross_entropy_with_logits(
        logits.float(),
        target,
        reduction="none",
    )
    if kind == "bce":
        return bce
    return mse + bce


def adversarial_weights(scores: torch.Tensor) -> torch.Tensor:
    """Paper ARL weights normalized across one physical or virtual batch."""

    if scores.ndim != 1 or scores.numel() < 2:
        raise ValueError("ARL weights require at least two one-dimensional scores")
    return 1.0 + scores.numel() * scores / scores.sum().clamp_min(1e-6)


def regression_metrics(
    labels: list[float],
    predictions: list[float],
    *,
    threshold: float,
) -> dict[str, float]:
    actual = np.asarray(labels, dtype=np.float64)
    predicted = np.asarray(predictions, dtype=np.float64)
    if actual.size == 0:
        raise ValueError("Cannot calculate metrics for an empty set")
    errors = predicted - actual
    if actual.size > 1 and np.std(actual) > 0 and np.std(predicted) > 0:
        pearson = float(np.corrcoef(actual, predicted)[0, 1])
    else:
        pearson = 0.0
    actual_class = actual >= threshold
    predicted_class = predicted >= threshold
    true_positive = int(np.sum(actual_class & predicted_class))
    false_positive = int(np.sum(~actual_class & predicted_class))
    false_negative = int(np.sum(actual_class & ~predicted_class))
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)
    return {
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(np.square(errors)))),
        "pearson": pearson,
        "threshold_accuracy": float(np.mean(actual_class == predicted_class)),
        "threshold_f1": float(f1),
    }


def _model_batch(batch: dict[str, Any], device: torch.device) -> dict[str, torch.Tensor]:
    return {
        key: value.to(device, non_blocking=True)
        for key, value in batch.items()
        if isinstance(value, torch.Tensor) and key != "label"
    }


def _atomic_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, temporary)
    temporary.replace(path)


class Trainer:
    def __init__(self, config: TrainingConfig) -> None:
        config.validate()
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable; GPU training is required")
        self.config = config
        self.device = torch.device("cuda")
        self.output_dir = Path(config.output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        seed_everything(config.seed)

        records = discover_records(config.preprocessed_root)
        self.train_records = [record for record in records if record.split == "train"]
        self.validation_records = [record for record in records if record.split == "validation"]
        if len(self.train_records) != config.expected_train_samples:
            raise RuntimeError(
                f"Expected {config.expected_train_samples} completed training samples, "
                f"found {len(self.train_records)}"
            )
        if len(self.validation_records) != config.expected_validation_samples:
            raise RuntimeError(
                f"Expected {config.expected_validation_samples} completed validation samples, "
                f"found {len(self.validation_records)}"
            )
        if config.preprocessing_audit_path:
            audit_path = Path(config.preprocessing_audit_path).resolve()
            if not audit_path.is_file():
                raise RuntimeError(f"Preprocessing audit is missing: {audit_path}")
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            if audit.get("passed") is not True:
                raise RuntimeError("Preprocessing audit has not passed")
            audit_complete = audit.get("complete")
            expected_complete = {
                "train": config.expected_train_samples,
                "validation": config.expected_validation_samples,
            }
            if audit_complete != expected_complete:
                raise RuntimeError(
                    "Preprocessing audit split counts do not match the training configuration"
                )
            if audit.get("dataset_identity_sha256") != dataset_identity_sha256(records):
                raise RuntimeError(
                    "Discovered training records do not match the audited dataset identity"
                )
        write_index(records, self.output_dir / "dataset_index.jsonl")

        scaler_path = Path(config.scaler_path).resolve()
        if scaler_path.is_file():
            standardizer = FeatureStandardizer.load(scaler_path)
            if standardizer.fitted_samples != len(self.train_records):
                print("Existing scaler does not match this training set; refitting.", flush=True)
                standardizer = fit_train_standardizer(records)
                standardizer.save(scaler_path)
        else:
            print("Fitting feature standardizer on the training split only.", flush=True)
            standardizer = fit_train_standardizer(records)
            standardizer.save(scaler_path)

        self.tokenizer = AutoTokenizer.from_pretrained(
            config.model_name_or_path,
            use_fast=True,
            local_files_only=True,
        )
        train_dataset = FIDataset(
            self.train_records,
            self.tokenizer,
            standardizer,
            max_length=config.max_length,
        )
        validation_dataset = FIDataset(
            self.validation_records,
            self.tokenizer,
            standardizer,
            max_length=config.max_length,
        )
        generator = torch.Generator().manual_seed(config.seed)
        self.train_loader = DataLoader(
            train_dataset,
            batch_size=config.batch_size,
            shuffle=True,
            num_workers=config.num_workers,
            pin_memory=True,
            drop_last=False,
            generator=generator,
        )
        self.validation_loader = DataLoader(
            validation_dataset,
            batch_size=config.batch_size,
            shuffle=False,
            num_workers=config.num_workers,
            pin_memory=True,
        )

        self.model = InterviewSignalModel.from_pretrained(
            config.model_name_or_path,
            multimodal=config.model_type in {"mag", "arl"},
            beta_shift=config.beta_shift,
            dropout=config.dropout,
            adversarial=config.model_type == "arl",
            use_acoustic=config.modalities in {"text_audio", "text_audio_visual"},
            use_visual=config.modalities in {"text_visual", "text_audio_visual"},
        )
        self.model.freeze_bert_layers(config.frozen_bert_layers)
        self.model.to(self.device)
        self.learner_optimizer = torch.optim.AdamW(
            self.model.learner_parameters(),
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
        )
        if config.model_type == "arl":
            updates_per_epoch = math.ceil(len(train_dataset) / config.arl_virtual_batch_size)
        else:
            updates_per_epoch = math.ceil(
                len(self.train_loader) / config.gradient_accumulation_steps
            )
        total_updates = updates_per_epoch * config.epochs
        warmup_steps = round(total_updates * config.warmup_ratio)
        self.scheduler = get_linear_schedule_with_warmup(
            self.learner_optimizer,
            num_warmup_steps=warmup_steps,
            num_training_steps=total_updates,
        )
        self.adversary_optimizer = (
            torch.optim.AdamW(
                self.model.adversary.parameters(),
                lr=config.adversary_learning_rate,
                weight_decay=config.weight_decay,
            )
            if self.model.adversary is not None
            else None
        )
        self.amp_enabled = bool(config.amp)
        self.grad_scaler = torch.amp.GradScaler("cuda", enabled=self.amp_enabled)

    def _step_learner(self) -> None:
        self.grad_scaler.unscale_(self.learner_optimizer)
        nn.utils.clip_grad_norm_(self.model.learner_parameters(), self.config.max_grad_norm)
        scale_before_step = self.grad_scaler.get_scale()
        self.grad_scaler.step(self.learner_optimizer)
        self.grad_scaler.update()
        self.learner_optimizer.zero_grad(set_to_none=True)
        if self.grad_scaler.get_scale() >= scale_before_step:
            self.scheduler.step()

    def _virtual_groups(self) -> Iterator[list[dict[str, Any]]]:
        group: list[dict[str, Any]] = []
        group_size = 0
        for batch in self.train_loader:
            group.append(batch)
            group_size += int(batch["label"].shape[0])
            if group_size >= self.config.arl_virtual_batch_size:
                yield group
                group = []
                group_size = 0
        if group:
            yield group

    def _train_standard_epoch(self) -> float:
        running_loss = 0.0
        accumulation = self.config.gradient_accumulation_steps
        self.learner_optimizer.zero_grad(set_to_none=True)
        for step, batch in enumerate(self.train_loader, start=1):
            labels = batch["label"].to(self.device, non_blocking=True)
            inputs = _model_batch(batch, self.device)
            with torch.amp.autocast("cuda", enabled=self.amp_enabled):
                output = self.model(**inputs)
                base_losses = per_sample_loss(
                    output.prediction,
                    labels,
                    self.config.loss,
                    logits=output.logits,
                )
                learner_loss = base_losses.mean()
            running_loss += float(learner_loss.detach()) * labels.shape[0]
            self.grad_scaler.scale(learner_loss / accumulation).backward()
            should_step = step % accumulation == 0 or step == len(self.train_loader)
            if should_step:
                self._step_learner()
        return running_loss / max(len(self.train_loader.dataset), 1)

    def _train_arl_epoch(self, *, adversarial: bool) -> float:
        if self.model.adversary is None or self.adversary_optimizer is None:
            raise RuntimeError("ARL heads and optimizer are unavailable")
        running_loss = 0.0
        for group in self._virtual_groups():
            group_size = sum(int(batch["label"].shape[0]) for batch in group)
            self.learner_optimizer.zero_grad(set_to_none=True)

            if not adversarial:
                for batch in group:
                    labels = batch["label"].to(self.device, non_blocking=True)
                    inputs = _model_batch(batch, self.device)
                    with torch.amp.autocast("cuda", enabled=self.amp_enabled):
                        output = self.model(**inputs)
                        losses = per_sample_loss(
                            output.prediction,
                            labels,
                            self.config.loss,
                            logits=output.logits,
                        )
                        objective = losses.sum() / group_size
                    running_loss += float(losses.detach().sum())
                    self.grad_scaler.scale(objective).backward()
                self._step_learner()
                continue

            pooled_parts: list[torch.Tensor] = []
            loss_parts: list[torch.Tensor] = []
            rng_states: list[torch.Tensor] = []
            with torch.no_grad():
                for batch in group:
                    rng_states.append(torch.cuda.get_rng_state(self.device))
                    labels = batch["label"].to(self.device, non_blocking=True)
                    inputs = _model_batch(batch, self.device)
                    with torch.amp.autocast("cuda", enabled=self.amp_enabled):
                        output = self.model(**inputs)
                        losses = per_sample_loss(
                            output.prediction,
                            labels,
                            self.config.loss,
                            logits=output.logits,
                        )
                    pooled_parts.append(output.pooled.detach())
                    loss_parts.append(losses.detach())

            pooled = torch.cat(pooled_parts)
            cached_losses = torch.cat(loss_parts)
            with torch.no_grad():
                scores = self.model.adversary(pooled)
                weights = adversarial_weights(scores)

            offset = 0
            for batch, rng_state in zip(group, rng_states, strict=True):
                torch.cuda.set_rng_state(rng_state, self.device)
                labels = batch["label"].to(self.device, non_blocking=True)
                inputs = _model_batch(batch, self.device)
                with torch.amp.autocast("cuda", enabled=self.amp_enabled):
                    output = self.model(**inputs)
                    losses = per_sample_loss(
                        output.prediction,
                        labels,
                        self.config.loss,
                        logits=output.logits,
                    )
                    batch_size = labels.shape[0]
                    batch_weights = weights[offset : offset + batch_size]
                    weighted_losses = batch_weights * losses
                    objective = weighted_losses.sum() / group_size
                running_loss += float(weighted_losses.detach().sum())
                self.grad_scaler.scale(objective).backward()
                offset += batch_size
            self._step_learner()

            self.adversary_optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=self.amp_enabled):
                scores = self.model.adversary(pooled)
                adversary_weights = adversarial_weights(scores)
                adversary_loss = -(adversary_weights * cached_losses).mean()
            self.grad_scaler.scale(adversary_loss).backward()
            self.grad_scaler.step(self.adversary_optimizer)
            self.grad_scaler.update()
        return running_loss / max(len(self.train_loader.dataset), 1)

    def train_epoch(self, epoch: int) -> float:
        self.model.train()
        if self.model.adversary is None:
            return self._train_standard_epoch()
        return self._train_arl_epoch(adversarial=epoch >= self.config.arl_pretrain_epochs)

    @torch.no_grad()
    def evaluate(self) -> tuple[float, dict[str, float], list[dict[str, Any]]]:
        self.model.eval()
        total_loss = 0.0
        labels: list[float] = []
        predictions: list[float] = []
        rows: list[dict[str, Any]] = []
        for batch in self.validation_loader:
            target = batch["label"].to(self.device, non_blocking=True)
            inputs = _model_batch(batch, self.device)
            with torch.amp.autocast("cuda", enabled=self.amp_enabled):
                output = self.model(**inputs)
                loss = per_sample_loss(
                    output.prediction,
                    target,
                    self.config.loss,
                    logits=output.logits,
                )
            total_loss += float(loss.sum())
            target_values = target.cpu().tolist()
            predicted_values = output.prediction.float().cpu().tolist()
            labels.extend(target_values)
            predictions.extend(predicted_values)
            rows.extend(
                {
                    "video_id": video_id,
                    "label": label,
                    "prediction": prediction,
                }
                for video_id, label, prediction in zip(
                    batch["video_id"], target_values, predicted_values, strict=True
                )
            )
        metrics = regression_metrics(
            labels,
            predictions,
            threshold=self.config.decision_threshold,
        )
        return total_loss / len(labels), metrics, rows

    def _checkpoint_payload(
        self,
        epoch: int,
        best_validation_loss: float,
        patience: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "config": asdict(self.config),
            "epoch": epoch,
            "best_validation_loss": best_validation_loss,
            "patience": patience,
            "model": self.model.state_dict(),
            "learner_optimizer": self.learner_optimizer.state_dict(),
            "scheduler": self.scheduler.state_dict(),
            "grad_scaler": self.grad_scaler.state_dict(),
            "python_random_state": random.getstate(),
            "numpy_random_state": np.random.get_state(),
            "torch_random_state": torch.get_rng_state(),
            "cuda_random_state": torch.cuda.get_rng_state_all(),
        }
        if self.adversary_optimizer is not None:
            payload["adversary_optimizer"] = self.adversary_optimizer.state_dict()
        return payload

    def restore(self, path: str | Path) -> tuple[int, float, int]:
        checkpoint = torch.load(Path(path), map_location=self.device, weights_only=False)
        if checkpoint["config"]["model_type"] != self.config.model_type:
            raise RuntimeError("Checkpoint model type does not match this run")
        self.model.load_state_dict(checkpoint["model"])
        self.learner_optimizer.load_state_dict(checkpoint["learner_optimizer"])
        self.scheduler.load_state_dict(checkpoint["scheduler"])
        self.grad_scaler.load_state_dict(checkpoint["grad_scaler"])
        if self.adversary_optimizer is not None:
            self.adversary_optimizer.load_state_dict(checkpoint["adversary_optimizer"])
        random.setstate(checkpoint["python_random_state"])
        np.random.set_state(checkpoint["numpy_random_state"])
        torch.set_rng_state(checkpoint["torch_random_state"].cpu())
        torch.cuda.set_rng_state_all([state.cpu() for state in checkpoint["cuda_random_state"]])
        return (
            int(checkpoint["epoch"]) + 1,
            float(checkpoint["best_validation_loss"]),
            int(checkpoint["patience"]),
        )

    def fit(self, *, resume: str | Path | None = None) -> dict[str, Any]:
        metrics_path = self.output_dir / "metrics.jsonl"
        latest_path = self.output_dir / "latest.pt"
        if resume is None and (metrics_path.exists() or latest_path.exists()):
            raise RuntimeError(
                "This run directory already contains training state. "
                "Use --resume with latest.pt or choose a new output_dir."
            )
        (self.output_dir / "config.json").write_text(
            json.dumps(asdict(self.config), indent=2), encoding="utf-8"
        )
        start_epoch = 0
        best_validation_loss = math.inf
        patience = 0
        if resume is not None:
            start_epoch, best_validation_loss, patience = self.restore(resume)
            print(f"Resumed at epoch {start_epoch + 1}", flush=True)
        last_epoch = start_epoch
        stopped_early = False
        for epoch in range(start_epoch, self.config.epochs):
            train_loss = self.train_epoch(epoch)
            validation_loss, metrics, prediction_rows = self.evaluate()
            last_epoch = epoch + 1
            row = {
                "epoch": epoch + 1,
                "train_loss": train_loss,
                "validation_loss": validation_loss,
                **metrics,
            }
            with metrics_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
            print(json.dumps(row), flush=True)

            improved = validation_loss < best_validation_loss
            if improved:
                best_validation_loss = validation_loss
                patience = 0
            else:
                patience += 1
            payload = self._checkpoint_payload(epoch, best_validation_loss, patience)
            _atomic_checkpoint(latest_path, payload)
            if improved:
                shutil.copy2(latest_path, self.output_dir / "best.pt")
                with (self.output_dir / "best_validation_predictions.csv").open(
                    "w", newline="", encoding="utf-8"
                ) as handle:
                    writer = csv.DictWriter(handle, fieldnames=("video_id", "label", "prediction"))
                    writer.writeheader()
                    writer.writerows(prediction_rows)
            if patience >= self.config.early_stopping_patience:
                print("Early stopping triggered.", flush=True)
                stopped_early = True
                break
        summary = {
            "run_name": self.config.run_name,
            "best_validation_loss": best_validation_loss,
            "best_checkpoint": str(self.output_dir / "best.pt"),
            "latest_checkpoint": str(self.output_dir / "latest.pt"),
            "completed_epochs": last_epoch,
            "configured_epochs": self.config.epochs,
            "stopped_early": stopped_early,
        }
        (self.output_dir / "training_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        return summary
