"""One real-size MAG-BERT-ARL optimizer step for GPU memory validation."""

from __future__ import annotations

import argparse
import json
import time

import torch

from ml_service.training.engine import per_sample_loss
from ml_service.training.models import InterviewSignalModel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-root", required=True)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--max-length", type=int, default=176)
    parser.add_argument("--steps", type=int, default=1)
    args = parser.parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable")
    device = torch.device("cuda")
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    model = InterviewSignalModel.from_pretrained(
        args.model_root,
        multimodal=True,
        adversarial=True,
        beta_shift=1.0,
        dropout=0.5,
    ).to(device)
    model.train()
    learner_optimizer = torch.optim.AdamW(model.learner_parameters(), lr=1e-5)
    adversary_optimizer = torch.optim.AdamW(model.adversary.parameters(), lr=1e-5)
    batch_size = args.batch_size
    length = args.max_length
    batch = {
        "input_ids": torch.randint(
            0, model.bert.config.vocab_size, (batch_size, length), device=device
        ),
        "attention_mask": torch.ones((batch_size, length), dtype=torch.long, device=device),
        "token_type_ids": torch.zeros((batch_size, length), dtype=torch.long, device=device),
        "acoustic": torch.randn(batch_size, length, 88, device=device),
        "visual": torch.randn(batch_size, length, 709, device=device),
        "modality_mask": torch.ones((batch_size, length), device=device),
    }
    labels = torch.linspace(0.25, 0.75, batch_size, device=device)
    scaler = torch.amp.GradScaler("cuda")
    torch.cuda.synchronize()
    started = time.perf_counter()
    for _ in range(args.steps):
        learner_optimizer.zero_grad(set_to_none=True)
        with torch.amp.autocast("cuda"):
            output = model(**batch)
            base_losses = per_sample_loss(output.prediction, labels, "mse")
            with torch.no_grad():
                scores = model.adversary(output.pooled.detach())
                weights = 1.0 + batch_size * scores / scores.sum().clamp_min(1e-6)
            learner_loss = (weights * base_losses).mean()
        scaler.scale(learner_loss).backward()
        scaler.step(learner_optimizer)
        scaler.update()

        adversary_optimizer.zero_grad(set_to_none=True)
        with torch.amp.autocast("cuda"):
            scores = model.adversary(output.pooled.detach())
            weights = 1.0 + batch_size * scores / scores.sum().clamp_min(1e-6)
            adversary_loss = -(weights * base_losses.detach()).mean()
        scaler.scale(adversary_loss).backward()
        scaler.step(adversary_optimizer)
        scaler.update()
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - started
    summary = {
        "gpu": torch.cuda.get_device_name(0),
        "batch_size": batch_size,
        "max_length": length,
        "steps": args.steps,
        "seconds_per_step": elapsed / args.steps,
        "prediction_shape": list(output.prediction.shape),
        "learner_loss": float(learner_loss.detach()),
        "adversary_loss": float(adversary_loss.detach()),
        "peak_allocated_gb": torch.cuda.max_memory_allocated() / 1e9,
        "peak_reserved_gb": torch.cuda.max_memory_reserved() / 1e9,
    }
    print(json.dumps(summary, indent=2))
    print("GPU TRAINING SMOKE PASSED")


if __name__ == "__main__":
    main()
