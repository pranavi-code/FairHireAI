# First Impressions V2 permitted fairness and error audit

Schema: `fi-permitted-fairness-error-audit-v1`

## Scope and safety

Permitted robustness and error audit using labels, answer length, Whisper confidence, OpenFace quality/confidence, and model outputs only.

This audit does **not** certify demographic fairness because the permitted validation data used here does not provide audited protected-group labels. No protected attribute was inferred from names, faces, voices, or video.

## Overall ranking by MAE

| Rank | Run | MAE | RMSE | Pearson | Balanced accuracy | F1 |
|---:|---|---:|---:|---:|---:|---:|
| 1 | fi_v2_mag_bert | 0.094888 | 0.119559 | 0.596759 | 0.703627 | 0.737882 |
| 2 | fi_v2_mag_bert_text_visual | 0.097289 | 0.122190 | 0.546667 | 0.678348 | 0.729229 |
| 3 | fi_v2_mag_bert_arl_mse_bce | 0.098022 | 0.123747 | 0.564836 | 0.693055 | 0.712200 |
| 4 | fi_v2_mag_bert_arl_mse | 0.098296 | 0.124073 | 0.564211 | 0.691919 | 0.709005 |
| 5 | fi_v2_mag_bert_arl_bce | 0.098580 | 0.124306 | 0.562220 | 0.688342 | 0.717361 |
| 6 | fi_v2_mag_bert_text_audio | 0.104834 | 0.132300 | 0.462795 | 0.651870 | 0.694840 |
| 7 | fi_v2_text_baseline | 0.109196 | 0.137864 | 0.347892 | 0.616611 | 0.679197 |

## Provisional performance winner

`fi_v2_mag_bert` remains the performance winner with MAE 0.094888, RMSE 0.119559, Pearson 0.596759, and balanced accuracy 0.703627.

Soft expected calibration error is 0.023072. At the fixed 0.5 research threshold there are 350 false positives and 234 false negatives.

## Observable robustness groups for the selected model

| Dimension | Group | N | MAE | Mean error | Balanced accuracy | Caution |
|---|---|---:|---:|---:|---:|---|
| visual_quality | good | 1991 | 0.094677 | +0.015830 | 0.704210 |  |
| visual_quality | low_quality | 8 | 0.147198 | +0.110492 | 0.285714 | small group |
| answer_length | long_61_plus_words | 169 | 0.087689 | +0.033622 | 0.588159 |  |
| answer_length | medium_31_60_words | 1664 | 0.095388 | +0.016319 | 0.687379 |  |
| answer_length | short_1_30_words | 166 | 0.097197 | -0.002629 | 0.642024 |  |
| transcript_confidence | high_0.85_plus | 677 | 0.091725 | +0.012514 | 0.684511 |  |
| transcript_confidence | low_below_0.75 | 195 | 0.100070 | +0.022164 | 0.666045 |  |
| transcript_confidence | medium_0.75_to_0.85 | 1127 | 0.095891 | +0.017398 | 0.700414 |  |
| label_range | high_0.67_to_1.0 | 258 | 0.118328 | -0.116826 | 0.467054 |  |
| label_range | low_0_to_0.33 | 247 | 0.148945 | +0.142307 | 0.427126 |  |
| label_range | middle_0.33_to_0.67 | 1494 | 0.081903 | +0.018335 | 0.638460 |  |

Positive mean error means overprediction; negative mean error means underprediction. The low and high label ranges show regression toward the middle and must be discussed as an error limitation.

## ARL difficult-sample comparison

| ARL run | Overall MAE delta | 95% bootstrap CI | Win rate | Difficult MAE delta | Difficult win rate |
|---|---:|---:|---:|---:|---:|
| fi_v2_mag_bert_arl_bce | +0.003692 | [+0.001588, +0.005830] | 0.471 | -0.016141 | 0.545 |
| fi_v2_mag_bert_arl_mse | +0.003408 | [+0.001131, +0.005715] | 0.474 | -0.020889 | 0.605 |
| fi_v2_mag_bert_arl_mse_bce | +0.003134 | [+0.000883, +0.005440] | 0.479 | -0.019201 | 0.600 |

## Interpretation limits

- Observable groups measure robustness, not demographic fairness.
- Groups below 30 samples are marked with a small-group caution.
- The 0.5 threshold is an evaluation view of a continuous target, not a hiring threshold.
- FI V2 does not contain technical-readiness ground truth.
- Final student-facing validation still requires consented participants and human evaluators.
