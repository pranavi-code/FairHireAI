from __future__ import annotations

import numpy as np
import pytest

from ml_service.evaluation.fairness_audit import (
    label_range_group,
    paired_bootstrap_mae_difference,
    regression_and_threshold_metrics,
)


def test_regression_threshold_and_calibration_metrics() -> None:
    labels = np.asarray([0.1, 0.4, 0.6, 0.9])
    predictions = np.asarray([0.2, 0.3, 0.7, 0.8])
    metrics = regression_and_threshold_metrics(labels, predictions)
    assert metrics["count"] == 4
    assert metrics["mae"] == pytest.approx(0.1)
    assert metrics["rmse"] == pytest.approx(0.1)
    assert metrics["threshold_accuracy"] == 1.0
    assert metrics["threshold_balanced_accuracy"] == 1.0
    assert metrics["threshold_f1"] == 1.0
    assert metrics["soft_expected_calibration_error"] == pytest.approx(0.1)


def test_paired_bootstrap_reports_candidate_direction() -> None:
    reference = np.asarray([0.2, 0.3, 0.4, 0.5])
    candidate = np.asarray([0.1, 0.2, 0.3, 0.4])
    result = paired_bootstrap_mae_difference(
        reference,
        candidate,
        draws=200,
        seed=8,
    )
    assert result["candidate_minus_reference_mae"] == pytest.approx(-0.1)
    assert result["bootstrap_ci95_high"] < 0.0


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        (0.0, "low_0_to_0.33"),
        (1.0 / 3.0, "middle_0.33_to_0.67"),
        (2.0 / 3.0, "high_0.67_to_1.0"),
        (1.0, "high_0.67_to_1.0"),
    ],
)
def test_label_range_groups(label: float, expected: str) -> None:
    assert label_range_group(label) == expected
