"""Memory-safe Gradient SHAP for full multimodal FI checkpoints."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from captum.attr import GradientShap
from torch import nn
from transformers import AutoTokenizer

from ml_service.training.data import (
    FeatureStandardizer,
    FIDataset,
    discover_records,
)
from ml_service.training.engine import TrainingConfig
from ml_service.training.models import InterviewSignalModel


@dataclass(frozen=True)
class ExplanationArtifacts:
    summary_path: Path
    arrays_path: Path


class MultimodalAttributionForward(nn.Module):
    """Expose continuous text/audio/visual inputs to Captum."""

    def __init__(
        self,
        model: InterviewSignalModel,
        *,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        token_type_ids: torch.Tensor | None,
        modality_mask: torch.Tensor,
    ) -> None:
        super().__init__()
        self.model = model
        self.input_ids = input_ids
        self.attention_mask = attention_mask
        self.token_type_ids = token_type_ids
        self.modality_mask = modality_mask

    def forward(
        self,
        text_embeddings: torch.Tensor,
        acoustic: torch.Tensor,
        visual: torch.Tensor,
    ) -> torch.Tensor:
        pooled = self.model.encode(
            self.input_ids,
            self.attention_mask,
            token_type_ids=self.token_type_ids,
            acoustic=acoustic,
            visual=visual,
            modality_mask=self.modality_mask,
            text_embeddings=text_embeddings,
        )
        return self.model.learner(pooled)


def _top_features(
    attribution: torch.Tensor,
    feature_names: list[str],
    *,
    limit: int = 15,
) -> list[dict[str, Any]]:
    importance = attribution.detach().abs().sum(dim=(0, 1)).cpu().numpy()
    order = np.argsort(importance)[::-1][:limit]
    return [
        {
            "feature": feature_names[int(index)],
            "absolute_attribution": float(importance[index]),
        }
        for index in order
    ]


def _masked_absolute_total(
    attribution: torch.Tensor,
    mask: torch.Tensor,
) -> float:
    importance = attribution.detach().abs().sum(dim=-1)
    aligned_mask = mask.to(device=importance.device, dtype=importance.dtype)
    return float((importance * aligned_mask).sum().cpu())


def explain_checkpoint_sample(
    *,
    config_path: str | Path,
    checkpoint_path: str | Path,
    video_id: str,
    output_root: str | Path,
    samples: int = 16,
    noise_standard_deviation: float = 0.01,
    seed: int = 8,
) -> ExplanationArtifacts:
    if samples < 1:
        raise ValueError("samples must be positive")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; explanation requires the GPU")
    config = TrainingConfig.load(config_path)
    if config.model_type not in {"mag", "arl"}:
        raise ValueError("Gradient SHAP requires a multimodal MAG/ARL checkpoint")
    if config.modalities != "text_audio_visual":
        raise ValueError("This explanation requires the full text/audio/visual model")

    records = discover_records(config.preprocessed_root)
    matches = [record for record in records if record.video_id == video_id]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one completed record for {video_id}, found {len(matches)}")
    standardizer = FeatureStandardizer.load(config.scaler_path)
    tokenizer = AutoTokenizer.from_pretrained(
        config.model_name_or_path,
        use_fast=True,
        local_files_only=True,
    )
    item = FIDataset(
        matches,
        tokenizer,
        standardizer,
        max_length=config.max_length,
    )[0]
    device = torch.device("cuda")
    tensor_item = {
        key: value.unsqueeze(0).to(device)
        for key, value in item.items()
        if isinstance(value, torch.Tensor) and key != "label"
    }
    model = InterviewSignalModel.from_pretrained(
        config.model_name_or_path,
        multimodal=True,
        beta_shift=config.beta_shift,
        dropout=config.dropout,
        adversarial=config.model_type == "arl",
        use_acoustic=True,
        use_visual=True,
    ).to(device)
    checkpoint = torch.load(
        Path(checkpoint_path).resolve(),
        map_location=device,
        weights_only=False,
    )
    checkpoint_config = checkpoint.get("config", {})
    if checkpoint_config.get("run_name") != config.run_name:
        raise RuntimeError("Checkpoint run_name does not match the explanation config")
    model.load_state_dict(checkpoint["model"])
    model.eval()
    model.requires_grad_(False)

    input_ids = tensor_item["input_ids"]
    attention_mask = tensor_item["attention_mask"]
    token_type_ids = tensor_item.get("token_type_ids")
    acoustic = tensor_item["acoustic"].detach()
    visual = tensor_item["visual"].detach()
    modality_mask = tensor_item["modality_mask"]
    text_embeddings = model.bert.embeddings.word_embeddings(input_ids).detach()
    wrapper = MultimodalAttributionForward(
        model,
        input_ids=input_ids,
        attention_mask=attention_mask,
        token_type_ids=token_type_ids,
        modality_mask=modality_mask,
    )
    explainer = GradientShap(wrapper)
    baselines = (
        torch.zeros_like(text_embeddings),
        torch.zeros_like(acoustic),
        torch.zeros_like(visual),
    )
    totals = [
        torch.zeros_like(text_embeddings),
        torch.zeros_like(acoustic),
        torch.zeros_like(visual),
    ]
    for draw in range(samples):
        torch.manual_seed(seed + draw)
        torch.cuda.manual_seed_all(seed + draw)
        attributions = explainer.attribute(
            (text_embeddings, acoustic, visual),
            baselines=baselines,
            n_samples=1,
            stdevs=(
                noise_standard_deviation,
                noise_standard_deviation,
                noise_standard_deviation,
            ),
        )
        totals = [
            total + attribution.detach()
            for total, attribution in zip(totals, attributions, strict=True)
        ]
    text_attribution, acoustic_attribution, visual_attribution = [
        total / samples for total in totals
    ]
    with torch.no_grad():
        prediction = float(wrapper(text_embeddings, acoustic, visual).item())

    schema_path = Path(config.preprocessed_root) / "alignment_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    acoustic_names = list(schema["acoustic_feature_names"])
    visual_names = list(schema["visual_feature_names"])
    token_strings = tokenizer.convert_ids_to_tokens(input_ids[0].cpu().tolist())
    token_mask = attention_mask[0].float().cpu()
    word_mask = modality_mask[0].float().cpu()
    text_per_token = text_attribution[0].sum(dim=-1).cpu()
    acoustic_per_token = acoustic_attribution[0].sum(dim=-1).cpu()
    visual_per_token = visual_attribution[0].sum(dim=-1).cpu()
    token_rows = [
        {
            "position": index,
            "token": token_strings[index],
            "is_word_token": bool(word_mask[index].item()),
            "text_attribution": float(text_per_token[index]),
            "acoustic_attribution": float(acoustic_per_token[index]),
            "visual_attribution": float(visual_per_token[index]),
        }
        for index in range(config.max_length)
        if token_mask[index].item() == 1
    ]
    modality_totals = {
        "text": _masked_absolute_total(text_attribution[0], token_mask),
        "acoustic": _masked_absolute_total(acoustic_attribution[0], word_mask),
        "visual": _masked_absolute_total(visual_attribution[0], word_mask),
    }
    total_importance = max(sum(modality_totals.values()), 1e-12)
    modality_share = {name: value / total_importance for name, value in modality_totals.items()}
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    safe_stem = Path(video_id).stem
    arrays_path = output_root / f"{safe_stem}_gradient_shap.npz"
    np.savez_compressed(
        arrays_path,
        input_ids=input_ids.cpu().numpy(),
        attention_mask=attention_mask.cpu().numpy(),
        modality_mask=modality_mask.cpu().numpy(),
        text_attribution=text_attribution.cpu().numpy(),
        acoustic_attribution=acoustic_attribution.cpu().numpy(),
        visual_attribution=visual_attribution.cpu().numpy(),
    )
    summary = {
        "method": "GradientShap",
        "video_id": video_id,
        "label": matches[0].label,
        "prediction": prediction,
        "samples": samples,
        "noise_standard_deviation": noise_standard_deviation,
        "seed": seed,
        "config": str(Path(config_path).resolve()),
        "checkpoint": str(Path(checkpoint_path).resolve()),
        "modality_absolute_attribution": modality_totals,
        "modality_share": modality_share,
        "top_acoustic_features": _top_features(acoustic_attribution, acoustic_names),
        "top_visual_features": _top_features(visual_attribution, visual_names),
        "tokens": token_rows,
        "safety_note": (
            "Visual/audio attribution explains the base interview signal only; "
            "it is not an emotion, personality, technical-readiness, or hiring judgment."
        ),
        "arrays": str(arrays_path),
    }
    summary_path = output_root / f"{safe_stem}_gradient_shap.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return ExplanationArtifacts(summary_path=summary_path, arrays_path=arrays_path)
