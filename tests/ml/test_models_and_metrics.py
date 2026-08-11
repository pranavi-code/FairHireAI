from __future__ import annotations

import pytest
import torch
from transformers import BertConfig

from ml_service.explainability.gradient_shap import (
    MultimodalAttributionForward,
    _masked_absolute_total,
)
from ml_service.training.engine import (
    TrainingConfig,
    adversarial_weights,
    per_sample_loss,
    regression_metrics,
)
from ml_service.training.models import InterviewSignalModel


def tiny_config() -> BertConfig:
    return BertConfig(
        vocab_size=100,
        hidden_size=32,
        num_hidden_layers=2,
        num_attention_heads=4,
        intermediate_size=64,
        max_position_embeddings=32,
    )


def batch() -> dict[str, torch.Tensor]:
    return {
        "input_ids": torch.randint(0, 100, (2, 8)),
        "attention_mask": torch.ones((2, 8), dtype=torch.long),
        "token_type_ids": torch.zeros((2, 8), dtype=torch.long),
        "acoustic": torch.randn(2, 8, 88),
        "visual": torch.randn(2, 8, 709),
        "modality_mask": torch.ones(2, 8),
    }


@pytest.mark.parametrize(
    ("multimodal", "adversarial"),
    [(False, False), (True, False), (True, True)],
)
def test_model_variants_forward_and_backward(multimodal: bool, adversarial: bool) -> None:
    model = InterviewSignalModel.from_config(
        tiny_config(),
        multimodal=multimodal,
        adversarial=adversarial,
    )
    output = model(**batch())
    assert output.prediction.shape == (2,)
    assert output.logits.shape == (2,)
    assert output.pooled.shape == (2, 32)
    assert torch.all((0.0 <= output.prediction) & (output.prediction <= 1.0))
    assert torch.allclose(output.prediction, torch.sigmoid(output.logits))
    per_sample_loss(
        output.prediction,
        torch.tensor([0.2, 0.8]),
        "mse_bce",
        logits=output.logits,
    ).mean().backward()
    if adversarial:
        learner_ids = {id(parameter) for parameter in model.learner_parameters()}
        adversary_ids = {id(parameter) for parameter in model.adversary.parameters()}
        assert learner_ids.isdisjoint(adversary_ids)


def test_freeze_bert_layers() -> None:
    model = InterviewSignalModel.from_config(tiny_config(), multimodal=False)
    model.freeze_bert_layers(1)
    assert not next(model.bert.embeddings.parameters()).requires_grad
    assert not next(model.bert.encoder.layer[0].parameters()).requires_grad
    assert next(model.bert.encoder.layer[1].parameters()).requires_grad


def test_disabled_modality_branch_is_fully_bypassed() -> None:
    model = InterviewSignalModel.from_config(
        tiny_config(),
        multimodal=True,
        use_acoustic=False,
        use_visual=True,
    )
    model(**batch()).prediction.mean().backward()
    assert model.mag.acoustic_projection.weight.grad is None
    assert model.mag.acoustic_gate.weight.grad is None
    assert model.mag.visual_projection.weight.grad is not None
    assert model.mag.visual_gate.weight.grad is not None


def test_continuous_multimodal_inputs_support_attribution_gradients() -> None:
    model = InterviewSignalModel.from_config(
        tiny_config(),
        multimodal=True,
        adversarial=True,
    )
    values = batch()
    text = model.bert.embeddings.word_embeddings(values["input_ids"]).detach().requires_grad_(True)
    acoustic = values["acoustic"].requires_grad_(True)
    visual = values["visual"].requires_grad_(True)
    wrapper = MultimodalAttributionForward(
        model,
        input_ids=values["input_ids"],
        attention_mask=values["attention_mask"],
        token_type_ids=values["token_type_ids"],
        modality_mask=values["modality_mask"],
    )
    gradients = torch.autograd.grad(
        wrapper(text, acoustic, visual).sum(),
        (text, acoustic, visual),
    )
    assert all(gradient is not None for gradient in gradients)
    assert all(torch.isfinite(gradient).all() for gradient in gradients)


def test_masked_attribution_total_aligns_mask_device() -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    attribution = torch.tensor(
        [[1.0, -2.0], [3.0, -4.0]],
        device=device,
    )
    mask = torch.tensor([1.0, 0.0])
    assert _masked_absolute_total(attribution, mask) == pytest.approx(3.0)


def test_metrics_and_arl_virtual_batch_constraint() -> None:
    metrics = regression_metrics([0.0, 1.0], [0.1, 0.9], threshold=0.5)
    assert metrics["rmse"] == pytest.approx(0.1)
    assert metrics["pearson"] == pytest.approx(1.0)
    assert metrics["threshold_accuracy"] == 1.0
    config = TrainingConfig(
        run_name="test",
        model_type="arl",
        model_name_or_path="unused",
        preprocessed_root="unused",
        output_dir="unused",
        scaler_path="unused",
        batch_size=1,
        arl_virtual_batch_size=1,
    )
    with pytest.raises(ValueError, match="virtual_batch_size"):
        config.validate()


def test_arl_weights_are_normalized_across_the_complete_batch() -> None:
    weights = adversarial_weights(torch.tensor([1.0, 2.0, 3.0, 4.0]))
    assert weights.sum().item() == pytest.approx(8.0)
    assert weights.mean().item() == pytest.approx(2.0)
    assert weights.tolist() == pytest.approx([1.4, 1.8, 2.2, 2.6])


@pytest.mark.parametrize("kind", ["bce", "mse_bce"])
def test_bce_losses_use_logits_and_keep_gradients(kind: str) -> None:
    logits = torch.tensor([-1.5, 1.5], requires_grad=True)
    prediction = torch.sigmoid(logits)
    target = torch.tensor([0.2, 0.8])
    loss = per_sample_loss(prediction, target, kind, logits=logits)
    assert torch.isfinite(loss).all()
    loss.mean().backward()
    assert logits.grad is not None
    assert torch.isfinite(logits.grad).all()
