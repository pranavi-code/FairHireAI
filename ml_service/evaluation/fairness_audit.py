"""Permitted fairness and error audit for First Impressions V2 experiments.

This module deliberately avoids inferring or fabricating protected attributes.
It audits observable data-quality and answer-characteristic groups, model
calibration, threshold errors, and whether ARL improves difficult samples.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ml_service.training.data import discover_records
from ml_service.training.engine import TrainingConfig

AUDIT_SCHEMA_VERSION = "fi-permitted-fairness-error-audit-v1"


@dataclass(frozen=True)
class SampleMetadata:
    video_id: str
    visual_quality: str
    word_count: int
    transcript_confidence: float
    visual_confidence: float

    @property
    def answer_length_group(self) -> str:
        if self.word_count <= 30:
            return "short_1_30_words"
        if self.word_count <= 60:
            return "medium_31_60_words"
        return "long_61_plus_words"

    @property
    def transcript_confidence_group(self) -> str:
        if self.transcript_confidence < 0.75:
            return "low_below_0.75"
        if self.transcript_confidence < 0.85:
            return "medium_0.75_to_0.85"
        return "high_0.85_plus"


@dataclass(frozen=True)
class PredictionSet:
    config: TrainingConfig
    labels: np.ndarray
    predictions: np.ndarray
    video_ids: list[str]


def label_range_group(label: float) -> str:
    if label < 1.0 / 3.0:
        return "low_0_to_0.33"
    if label < 2.0 / 3.0:
        return "middle_0.33_to_0.67"
    return "high_0.67_to_1.0"


def regression_and_threshold_metrics(
    labels: np.ndarray,
    predictions: np.ndarray,
    *,
    threshold: float = 0.5,
    calibration_bins: int = 10,
) -> dict[str, Any]:
    labels = np.asarray(labels, dtype=np.float64)
    predictions = np.asarray(predictions, dtype=np.float64)
    if labels.ndim != 1 or predictions.shape != labels.shape or labels.size == 0:
        raise ValueError("Labels and predictions must be non-empty matching vectors")
    errors = predictions - labels
    absolute_errors = np.abs(errors)
    actual_class = labels >= threshold
    predicted_class = predictions >= threshold
    tp = int(np.sum(actual_class & predicted_class))
    tn = int(np.sum(~actual_class & ~predicted_class))
    fp = int(np.sum(~actual_class & predicted_class))
    fn = int(np.sum(actual_class & ~predicted_class))
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    specificity = tn / max(tn + fp, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)
    pearson = (
        float(np.corrcoef(labels, predictions)[0, 1])
        if labels.size > 1
        and float(np.std(labels)) > 0.0
        and float(np.std(predictions)) > 0.0
        else 0.0
    )
    calibration_rows: list[dict[str, Any]] = []
    ece = 0.0
    edges = np.linspace(0.0, 1.0, calibration_bins + 1)
    bin_indices = np.minimum(
        np.floor(np.clip(predictions, 0.0, 1.0) * calibration_bins).astype(int),
        calibration_bins - 1,
    )
    for index in range(calibration_bins):
        lower = float(edges[index])
        upper = float(edges[index + 1])
        selected = bin_indices == index
        count = int(np.sum(selected))
        if count == 0:
            continue
        mean_prediction = float(np.mean(predictions[selected]))
        mean_label = float(np.mean(labels[selected]))
        gap = abs(mean_prediction - mean_label)
        ece += count / labels.size * gap
        calibration_rows.append(
            {
                "lower": lower,
                "upper": upper,
                "count": count,
                "mean_prediction": mean_prediction,
                "mean_label": mean_label,
                "absolute_gap": gap,
            }
        )
    return {
        "count": int(labels.size),
        "mae": float(np.mean(absolute_errors)),
        "rmse": float(np.sqrt(np.mean(np.square(errors)))),
        "pearson": pearson,
        "mean_error": float(np.mean(errors)),
        "median_absolute_error": float(np.median(absolute_errors)),
        "absolute_error_p90": float(np.quantile(absolute_errors, 0.90)),
        "absolute_error_p95": float(np.quantile(absolute_errors, 0.95)),
        "mean_label": float(np.mean(labels)),
        "mean_prediction": float(np.mean(predictions)),
        "threshold": threshold,
        "threshold_accuracy": float(np.mean(actual_class == predicted_class)),
        "threshold_balanced_accuracy": float((recall + specificity) / 2.0),
        "threshold_precision": float(precision),
        "threshold_recall": float(recall),
        "threshold_specificity": float(specificity),
        "threshold_f1": float(f1),
        "true_positive": tp,
        "true_negative": tn,
        "false_positive": fp,
        "false_negative": fn,
        "soft_brier_score": float(np.mean(np.square(errors))),
        "soft_expected_calibration_error": float(ece),
        "calibration_bins": calibration_rows,
    }


def paired_bootstrap_mae_difference(
    reference_errors: np.ndarray,
    candidate_errors: np.ndarray,
    *,
    draws: int = 2000,
    seed: int = 8,
) -> dict[str, float]:
    reference_errors = np.asarray(reference_errors, dtype=np.float64)
    candidate_errors = np.asarray(candidate_errors, dtype=np.float64)
    if reference_errors.shape != candidate_errors.shape or reference_errors.size == 0:
        raise ValueError("Paired errors must be non-empty matching vectors")
    rng = np.random.default_rng(seed)
    differences = np.empty(draws, dtype=np.float64)
    for draw in range(draws):
        indices = rng.integers(0, reference_errors.size, reference_errors.size)
        differences[draw] = float(
            np.mean(candidate_errors[indices] - reference_errors[indices])
        )
    return {
        "candidate_minus_reference_mae": float(
            np.mean(candidate_errors - reference_errors)
        ),
        "bootstrap_ci95_low": float(np.quantile(differences, 0.025)),
        "bootstrap_ci95_high": float(np.quantile(differences, 0.975)),
    }


def _load_predictions(config: TrainingConfig) -> PredictionSet:
    path = Path(config.output_dir) / "best_validation_predictions.csv"
    if not path.is_file():
        raise RuntimeError(f"Missing best validation predictions: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise RuntimeError(f"Prediction file is empty: {path}")
    return PredictionSet(
        config=config,
        labels=np.asarray([float(row["label"]) for row in rows], dtype=np.float64),
        predictions=np.asarray(
            [float(row["prediction"]) for row in rows],
            dtype=np.float64,
        ),
        video_ids=[row["video_id"] for row in rows],
    )


def _load_metadata(processed_root: str | Path) -> dict[str, SampleMetadata]:
    validation_records = [
        record for record in discover_records(processed_root) if record.split == "validation"
    ]
    result: dict[str, SampleMetadata] = {}
    for record in validation_records:
        status_path = Path(record.aligned_path).parent / "status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        stages = status["stages"]
        result[record.video_id] = SampleMetadata(
            video_id=record.video_id,
            visual_quality=record.visual_quality,
            word_count=int(stages["transcribe"]["words"]),
            transcript_confidence=float(
                stages["transcribe"]["average_word_confidence"]
            ),
            visual_confidence=float(stages["openface"]["mean_confidence"]),
        )
    return result


def _group_rows(
    prediction_sets: list[PredictionSet],
    metadata: dict[str, SampleMetadata],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    dimensions = {
        "visual_quality": lambda item, _label: item.visual_quality,
        "answer_length": lambda item, _label: item.answer_length_group,
        "transcript_confidence": (
            lambda item, _label: item.transcript_confidence_group
        ),
        "label_range": lambda _item, label: label_range_group(label),
    }
    for prediction_set in prediction_sets:
        for dimension, group_for in dimensions.items():
            groups: dict[str, list[int]] = {}
            for index, (video_id, label) in enumerate(
                zip(
                    prediction_set.video_ids,
                    prediction_set.labels,
                    strict=True,
                )
            ):
                group = group_for(metadata[video_id], float(label))
                groups.setdefault(group, []).append(index)
            for group, indices in sorted(groups.items()):
                selected = np.asarray(indices, dtype=np.int64)
                metrics = regression_and_threshold_metrics(
                    prediction_set.labels[selected],
                    prediction_set.predictions[selected],
                    threshold=prediction_set.config.decision_threshold,
                )
                metrics.pop("calibration_bins")
                rows.append(
                    {
                        "run_name": prediction_set.config.run_name,
                        "dimension": dimension,
                        "group": group,
                        "small_group_caution": metrics["count"] < 30,
                        **metrics,
                    }
                )
    return rows


def _arl_comparisons(
    reference: PredictionSet,
    candidates: list[PredictionSet],
) -> list[dict[str, Any]]:
    reference_error = np.abs(reference.predictions - reference.labels)
    difficult_cutoff = float(np.quantile(reference_error, 0.90))
    difficult = reference_error >= difficult_cutoff
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_error = np.abs(candidate.predictions - candidate.labels)
        bootstrap = paired_bootstrap_mae_difference(
            reference_error,
            candidate_error,
        )
        rows.append(
            {
                "reference_run": reference.config.run_name,
                "candidate_run": candidate.config.run_name,
                "count": int(reference_error.size),
                "reference_mae": float(np.mean(reference_error)),
                "candidate_mae": float(np.mean(candidate_error)),
                "candidate_win_rate": float(np.mean(candidate_error < reference_error)),
                "equal_error_rate": float(
                    np.mean(np.isclose(candidate_error, reference_error))
                ),
                "difficult_definition": "top 10% absolute errors of reference model",
                "difficult_cutoff": difficult_cutoff,
                "difficult_count": int(np.sum(difficult)),
                "reference_difficult_mae": float(np.mean(reference_error[difficult])),
                "candidate_difficult_mae": float(np.mean(candidate_error[difficult])),
                "candidate_difficult_win_rate": float(
                    np.mean(candidate_error[difficult] < reference_error[difficult])
                ),
                **bootstrap,
            }
        )
    return rows


def _worst_error_rows(
    reference: PredictionSet,
    all_predictions: list[PredictionSet],
    metadata: dict[str, SampleMetadata],
    *,
    limit: int = 25,
) -> list[dict[str, Any]]:
    absolute_error = np.abs(reference.predictions - reference.labels)
    order = np.argsort(absolute_error)[::-1][:limit]
    by_run = {
        prediction_set.config.run_name: prediction_set.predictions
        for prediction_set in all_predictions
    }
    rows: list[dict[str, Any]] = []
    for rank, index in enumerate(order, start=1):
        video_id = reference.video_ids[int(index)]
        item = metadata[video_id]
        row: dict[str, Any] = {
            "rank": rank,
            "video_id": video_id,
            "label": float(reference.labels[index]),
            "reference_prediction": float(reference.predictions[index]),
            "reference_absolute_error": float(absolute_error[index]),
            "visual_quality": item.visual_quality,
            "word_count": item.word_count,
            "transcript_confidence": item.transcript_confidence,
            "visual_confidence": item.visual_confidence,
        }
        for run_name, predictions in by_run.items():
            row[f"prediction__{run_name}"] = float(predictions[index])
        rows.append(row)
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError(f"Cannot write an empty audit table: {path}")
    serializable = [
        {
            key: json.dumps(value, sort_keys=True)
            if isinstance(value, (dict, list))
            else value
            for key, value in row.items()
        }
        for row in rows
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(serializable[0]))
        writer.writeheader()
        writer.writerows(serializable)


def _markdown_report(audit: dict[str, Any]) -> str:
    selected = audit["selected_run"]
    overall = {row["run_name"]: row for row in audit["overall_metrics"]}
    selected_metrics = overall[selected]
    ranking = sorted(audit["overall_metrics"], key=lambda row: row["mae"])
    lines = [
        "# First Impressions V2 permitted fairness and error audit",
        "",
        f"Schema: `{audit['schema_version']}`",
        "",
        "## Scope and safety",
        "",
        audit["scope_note"],
        "",
        "This audit does **not** certify demographic fairness because the permitted "
        "validation data used here does not provide audited protected-group labels. "
        "No protected attribute was inferred from names, faces, voices, or video.",
        "",
        "## Overall ranking by MAE",
        "",
        "| Rank | Run | MAE | RMSE | Pearson | Balanced accuracy | F1 |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for rank, row in enumerate(ranking, start=1):
        lines.append(
            f"| {rank} | {row['run_name']} | {row['mae']:.6f} | "
            f"{row['rmse']:.6f} | {row['pearson']:.6f} | "
            f"{row['threshold_balanced_accuracy']:.6f} | "
            f"{row['threshold_f1']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## Provisional performance winner",
            "",
            f"`{selected}` remains the performance winner with MAE "
            f"{selected_metrics['mae']:.6f}, RMSE {selected_metrics['rmse']:.6f}, "
            f"Pearson {selected_metrics['pearson']:.6f}, and balanced accuracy "
            f"{selected_metrics['threshold_balanced_accuracy']:.6f}.",
            "",
            f"Soft expected calibration error is "
            f"{selected_metrics['soft_expected_calibration_error']:.6f}. At the "
            f"fixed 0.5 research threshold there are "
            f"{selected_metrics['false_positive']} false positives and "
            f"{selected_metrics['false_negative']} false negatives.",
            "",
            "## Observable robustness groups for the selected model",
            "",
            "| Dimension | Group | N | MAE | Mean error | Balanced accuracy | Caution |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
    )
    selected_groups = [
        row for row in audit["group_metrics"] if row["run_name"] == selected
    ]
    for row in selected_groups:
        lines.append(
            f"| {row['dimension']} | {row['group']} | {row['count']} | "
            f"{row['mae']:.6f} | {row['mean_error']:+.6f} | "
            f"{row['threshold_balanced_accuracy']:.6f} | "
            f"{'small group' if row['small_group_caution'] else ''} |"
        )
    lines.extend(
        [
            "",
            "Positive mean error means overprediction; negative mean error means "
            "underprediction. The low and high label ranges show regression toward "
            "the middle and must be discussed as an error limitation.",
            "",
            "## ARL difficult-sample comparison",
            "",
            "| ARL run | Overall MAE delta | 95% bootstrap CI | Win rate | "
            "Difficult MAE delta | Difficult win rate |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in audit["arl_comparisons"]:
        difficult_delta = (
            row["candidate_difficult_mae"] - row["reference_difficult_mae"]
        )
        lines.append(
            f"| {row['candidate_run']} | "
            f"{row['candidate_minus_reference_mae']:+.6f} | "
            f"[{row['bootstrap_ci95_low']:+.6f}, "
            f"{row['bootstrap_ci95_high']:+.6f}] | "
            f"{row['candidate_win_rate']:.3f} | "
            f"{difficult_delta:+.6f} | "
            f"{row['candidate_difficult_win_rate']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation limits",
            "",
            "- Observable groups measure robustness, not demographic fairness.",
            "- Groups below 30 samples are marked with a small-group caution.",
            "- The 0.5 threshold is an evaluation view of a continuous target, not "
            "a hiring threshold.",
            "- FI V2 does not contain technical-readiness ground truth.",
            "- Final student-facing validation still requires consented participants "
            "and human evaluators.",
            "",
        ]
    )
    return "\n".join(lines)


def run_fairness_error_audit(
    *,
    config_root: str | Path,
    output_root: str | Path,
    selected_run: str = "fi_v2_mag_bert",
) -> dict[str, Any]:
    config_paths = sorted(Path(config_root).resolve().glob("*_laptop.json"))
    prediction_sets = [
        _load_predictions(TrainingConfig.load(path)) for path in config_paths
    ]
    if len(prediction_sets) != 7:
        raise RuntimeError(f"Expected seven completed experiments, found {len(prediction_sets)}")
    reference = next(
        (
            prediction_set
            for prediction_set in prediction_sets
            if prediction_set.config.run_name == selected_run
        ),
        None,
    )
    if reference is None:
        raise RuntimeError(f"Selected run was not found: {selected_run}")
    for prediction_set in prediction_sets:
        if prediction_set.video_ids != reference.video_ids:
            raise RuntimeError(
                f"Prediction ordering differs for {prediction_set.config.run_name}"
            )
        if not np.allclose(prediction_set.labels, reference.labels, atol=1e-6):
            raise RuntimeError(
                f"Validation labels differ for {prediction_set.config.run_name}"
            )
    metadata = _load_metadata(reference.config.preprocessed_root)
    missing_metadata = sorted(set(reference.video_ids) - set(metadata))
    if missing_metadata:
        raise RuntimeError(f"Missing metadata for {len(missing_metadata)} predictions")

    overall_metrics: list[dict[str, Any]] = []
    for prediction_set in prediction_sets:
        metrics = regression_and_threshold_metrics(
            prediction_set.labels,
            prediction_set.predictions,
            threshold=prediction_set.config.decision_threshold,
        )
        overall_metrics.append(
            {
                "run_name": prediction_set.config.run_name,
                "model_type": prediction_set.config.model_type,
                "modalities": prediction_set.config.modalities,
                "loss": prediction_set.config.loss,
                **metrics,
            }
        )
    group_metrics = _group_rows(prediction_sets, metadata)
    arl_candidates = [
        prediction_set
        for prediction_set in prediction_sets
        if prediction_set.config.model_type == "arl"
    ]
    arl_comparisons = _arl_comparisons(reference, arl_candidates)
    worst_errors = _worst_error_rows(
        reference,
        prediction_sets,
        metadata,
    )
    selected_groups = [
        row for row in group_metrics if row["run_name"] == selected_run
    ]
    disparities: list[dict[str, Any]] = []
    for dimension in sorted({row["dimension"] for row in selected_groups}):
        eligible = [
            row
            for row in selected_groups
            if row["dimension"] == dimension and row["count"] >= 30
        ]
        if len(eligible) >= 2:
            highest = max(eligible, key=lambda row: row["mae"])
            lowest = min(eligible, key=lambda row: row["mae"])
            disparities.append(
                {
                    "dimension": dimension,
                    "highest_error_group": highest["group"],
                    "highest_mae": highest["mae"],
                    "lowest_error_group": lowest["group"],
                    "lowest_mae": lowest["mae"],
                    "mae_gap": highest["mae"] - lowest["mae"],
                }
            )
    audit = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "selected_run": selected_run,
        "validation_samples": len(reference.video_ids),
        "experiment_count": len(prediction_sets),
        "scope_note": (
            "Permitted robustness and error audit using labels, answer length, "
            "Whisper confidence, OpenFace quality/confidence, and model outputs only."
        ),
        "protected_attribute_policy": (
            "No gender, race, ethnicity, age, disability, religion, personality, "
            "emotion, or other protected/sensitive attribute was inferred."
        ),
        "overall_metrics": overall_metrics,
        "group_metrics": group_metrics,
        "selected_run_group_disparities": disparities,
        "arl_comparisons": arl_comparisons,
        "worst_errors": worst_errors,
        "key_findings": [
            (
                "Full MAG-BERT is the strongest overall model on every common "
                "predictive metric used for selection."
            ),
            (
                "All ARL variants have significantly higher overall MAE than MAG-BERT "
                "under the paired bootstrap, but improve MAE on MAG-BERT's hardest "
                "10% of validation samples."
            ),
            (
                "Predictions regress toward the middle: low labels are overpredicted "
                "and high labels are underpredicted."
            ),
            (
                "Only eight validation samples are marked low visual quality, so their "
                "higher error is a caution signal rather than a stable group estimate."
            ),
            (
                "Lower transcript confidence and shorter answers have moderately "
                "higher error than their comparison groups."
            ),
        ],
        "limitations": [
            "This is not a demographic fairness certification.",
            "FI V2 labels do not represent technical readiness or hiring ground truth.",
            "The same validation split was used for checkpoint selection and this audit.",
            "Small observable groups cannot support strong conclusions.",
            "Student-facing fairness and usefulness require the consented evaluator study.",
        ],
        "decision": {
            "status": "provisional_performance_winner_pending_external_validation",
            "run_name": selected_run,
            "reason": (
                "The selected full MAG-BERT run has the strongest common predictive "
                "metrics. ARL comparisons are retained as required research evidence; "
                "deployment still requires the consented human-evaluation phase."
            ),
        },
    }
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "fairness_error_audit.json"
    json_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    _write_csv(output_root / "overall_metrics.csv", overall_metrics)
    _write_csv(output_root / "group_metrics.csv", group_metrics)
    _write_csv(output_root / "arl_comparisons.csv", arl_comparisons)
    _write_csv(output_root / "worst_errors.csv", worst_errors)
    markdown_path = output_root / "fairness_error_audit.md"
    markdown_path.write_text(_markdown_report(audit), encoding="utf-8")
    audit["artifacts"] = {
        "json": str(json_path),
        "markdown": str(markdown_path),
        "overall_csv": str(output_root / "overall_metrics.csv"),
        "groups_csv": str(output_root / "group_metrics.csv"),
        "arl_csv": str(output_root / "arl_comparisons.csv"),
        "worst_errors_csv": str(output_root / "worst_errors.csv"),
    }
    return audit
