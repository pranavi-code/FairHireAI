"""Text, MAG-BERT, and adversarial reweighting models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch
from torch import nn
from transformers import BertConfig, BertModel

from ml_service.preprocessing.alignment import ACOUSTIC_DIM, VISUAL_DIM


@dataclass(frozen=True)
class ModelOutput:
    prediction: torch.Tensor
    logits: torch.Tensor
    pooled: torch.Tensor


class MAGFusion(nn.Module):
    """Multimodal adaptation gate applied to BERT word embeddings."""

    def __init__(
        self,
        hidden_size: int,
        *,
        acoustic_dim: int = ACOUSTIC_DIM,
        visual_dim: int = VISUAL_DIM,
        beta_shift: float = 1.0,
        dropout: float = 0.5,
    ) -> None:
        super().__init__()
        self.beta_shift = beta_shift
        self.acoustic_projection = nn.Linear(acoustic_dim, hidden_size)
        self.visual_projection = nn.Linear(visual_dim, hidden_size)
        self.acoustic_gate = nn.Linear(acoustic_dim + hidden_size, hidden_size)
        self.visual_gate = nn.Linear(visual_dim + hidden_size, hidden_size)
        self.layer_norm = nn.LayerNorm(hidden_size)
        self.dropout = nn.Dropout(dropout)

    def forward(
        self,
        text: torch.Tensor,
        acoustic: torch.Tensor,
        visual: torch.Tensor,
        modality_mask: torch.Tensor,
        *,
        use_acoustic: bool = True,
        use_visual: bool = True,
    ) -> torch.Tensor:
        displacement = torch.zeros_like(text)
        if use_acoustic:
            acoustic_weight = torch.relu(self.acoustic_gate(torch.cat((acoustic, text), dim=-1)))
            displacement = displacement + acoustic_weight * self.acoustic_projection(acoustic)
        if use_visual:
            visual_weight = torch.relu(self.visual_gate(torch.cat((visual, text), dim=-1)))
            displacement = displacement + visual_weight * self.visual_projection(visual)
        displacement = displacement * modality_mask.unsqueeze(-1)
        text_norm = torch.linalg.vector_norm(text, dim=-1)
        displacement_norm = torch.linalg.vector_norm(displacement, dim=-1).clamp_min(1e-6)
        scale = (text_norm / displacement_norm * self.beta_shift).clamp(max=1.0)
        fused = text + scale.unsqueeze(-1) * displacement
        return self.dropout(self.layer_norm(fused))


class ResidualBlock(nn.Module):
    def __init__(self, hidden_size: int, dropout: float) -> None:
        super().__init__()
        self.linear = nn.Linear(hidden_size, hidden_size)
        self.dropout = nn.Dropout(dropout)
        self.layer_norm = nn.LayerNorm(hidden_size)

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        update = self.dropout(torch.relu(self.linear(values)))
        return self.layer_norm(values + update)


class LearnerHead(nn.Module):
    """Three-layer residual learner used by the ARL paper."""

    def __init__(self, hidden_size: int, dropout: float = 0.5) -> None:
        super().__init__()
        self.blocks = nn.Sequential(
            ResidualBlock(hidden_size, dropout),
            ResidualBlock(hidden_size, dropout),
            ResidualBlock(hidden_size, dropout),
        )
        self.output = nn.Linear(hidden_size, 1)

    def logits(self, pooled: torch.Tensor) -> torch.Tensor:
        return self.output(self.blocks(pooled)).squeeze(-1)

    def forward(self, pooled: torch.Tensor) -> torch.Tensor:
        return torch.sigmoid(self.logits(pooled))


class AdversaryHead(nn.Module):
    """Positive one-layer sample scoring network for ARL."""

    def __init__(self, hidden_size: int) -> None:
        super().__init__()
        self.output = nn.Linear(hidden_size, 1)

    def forward(self, pooled: torch.Tensor) -> torch.Tensor:
        return nn.functional.softplus(self.output(pooled)).squeeze(-1) + 1e-6


class InterviewSignalModel(nn.Module):
    def __init__(
        self,
        bert: BertModel,
        *,
        multimodal: bool,
        beta_shift: float = 1.0,
        dropout: float = 0.5,
        adversarial: bool = False,
        use_acoustic: bool = True,
        use_visual: bool = True,
    ) -> None:
        super().__init__()
        self.bert = bert
        self.multimodal = multimodal
        self.use_acoustic = use_acoustic
        self.use_visual = use_visual
        hidden_size = bert.config.hidden_size
        self.mag = (
            MAGFusion(
                hidden_size,
                beta_shift=beta_shift,
                dropout=dropout,
            )
            if multimodal
            else None
        )
        self.learner = LearnerHead(hidden_size, dropout)
        self.adversary = AdversaryHead(hidden_size) if adversarial else None

    @classmethod
    def from_pretrained(
        cls,
        model_name_or_path: str,
        **kwargs: Any,
    ) -> InterviewSignalModel:
        return cls(BertModel.from_pretrained(model_name_or_path), **kwargs)

    @classmethod
    def from_config(cls, config: BertConfig, **kwargs: Any) -> InterviewSignalModel:
        return cls(BertModel(config), **kwargs)

    def freeze_bert_layers(self, layer_count: int) -> None:
        if layer_count < 0 or layer_count > len(self.bert.encoder.layer):
            raise ValueError(f"Invalid frozen BERT layer count: {layer_count}")
        if layer_count > 0:
            for parameter in self.bert.embeddings.parameters():
                parameter.requires_grad = False
        for layer in self.bert.encoder.layer[:layer_count]:
            for parameter in layer.parameters():
                parameter.requires_grad = False

    def encode(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        *,
        token_type_ids: torch.Tensor | None = None,
        acoustic: torch.Tensor | None = None,
        visual: torch.Tensor | None = None,
        modality_mask: torch.Tensor | None = None,
        text_embeddings: torch.Tensor | None = None,
    ) -> torch.Tensor:
        if self.multimodal:
            if acoustic is None or visual is None or modality_mask is None:
                raise ValueError("Multimodal inputs are required")
            word_embeddings = (
                text_embeddings
                if text_embeddings is not None
                else self.bert.embeddings.word_embeddings(input_ids)
            )
            fused = self.mag(
                word_embeddings,
                acoustic,
                visual,
                modality_mask,
                use_acoustic=self.use_acoustic,
                use_visual=self.use_visual,
            )
            output = self.bert(
                inputs_embeds=fused,
                attention_mask=attention_mask,
                token_type_ids=token_type_ids,
                return_dict=True,
            )
        else:
            if text_embeddings is None:
                output = self.bert(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    token_type_ids=token_type_ids,
                    return_dict=True,
                )
            else:
                output = self.bert(
                    inputs_embeds=text_embeddings,
                    attention_mask=attention_mask,
                    token_type_ids=token_type_ids,
                    return_dict=True,
                )
        return output.last_hidden_state[:, 0]

    def forward(self, **batch: torch.Tensor) -> ModelOutput:
        pooled = self.encode(
            batch["input_ids"],
            batch["attention_mask"],
            token_type_ids=batch.get("token_type_ids"),
            acoustic=batch.get("acoustic"),
            visual=batch.get("visual"),
            modality_mask=batch.get("modality_mask"),
        )
        logits = self.learner.logits(pooled)
        return ModelOutput(
            prediction=torch.sigmoid(logits),
            logits=logits,
            pooled=pooled,
        )

    def learner_parameters(self) -> list[nn.Parameter]:
        excluded = set(self.adversary.parameters()) if self.adversary else set()
        return [
            parameter
            for parameter in self.parameters()
            if parameter.requires_grad and parameter not in excluded
        ]
