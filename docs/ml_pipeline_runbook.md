# FI V2 Preprocessing and Training Runbook

## Scope and output wording

This pipeline reproduces the MAG-BERT-ARL base model on First Impressions V2. Its application-facing output must be called **Base Multimodal Interview Signal**. It is not Technical Readiness, a personality/emotion inference, a hire/reject decision, or a student-ranking score.

The later Competency Evidence Graph, Junior Backend Developer rubric, consented human-rated study, and learning roadmap remain separate project layers.

## Verified environment

- Code: `D:\FairHireAI`
- Raw FI V2: `D:\FairHireAI-data\raw\FirstImpressionsV2`
- Verified manifest: `D:\FairHireAI-data\manifests\first_impressions_v2_manifest.csv`
- Full processed output: `D:\FairHireAI-data\processed\fi_v2_full`
- Whisper cache: `D:\FairHireAI-data\models\whisper`
- BERT cache: `D:\FairHireAI-data\models\bert-base-uncased`
- OpenFace: `D:\FairHireAI-tools\OpenFace_2.2.0_win_x64`
- GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU

The manifest is pinned to SHA-256 `2f15c2a034c7f0af9adb2b29e7ba2f888abc28fc616add5c853819aaeb4eda2c`: 6,000 training and 2,000 validation videos.

## Proven pilot results

- Media normalization: 25 FPS video, 640-pixel width, 16 kHz mono PCM audio.
- Whisper `small.en`: 10/10 pilot recordings, 472 timestamped words.
- eGeMAPSv02: one 88-dimensional functional vector per word.
- OpenFace 2.2.0: 10/10, 383 frames each, 714 columns, 100% successful pilot frames.
- Word alignment: 10/10; one 709-dimensional visual vector per word and no more than 20 ms nearest-frame error.
- Unified source-video smoke: all stages passed in 33.5 seconds.
- Real MAG-BERT-ARL GPU smoke: batch 2, length 176, 2.29 GB peak allocated and 2.58 GB peak reserved.
- Three-step ARL benchmark: 0.308 seconds per training batch after model load.
- Synthetic Trainer integration: train, validate, checkpoint, and restore passed.

## Preflight

The preflight command is implemented in `scripts/preflight_fi_pipeline.py`. It verifies:

- all 8,000 source paths and sizes;
- manifest checksum and split counts;
- FFmpeg and FFprobe;
- CUDA and GPU memory;
- the four required OpenFace CEN model files;
- cached Whisper `small.en` and local BERT files;
- free storage and already-completed sample counts.

Its current report is `D:\FairHireAI-data\processed\fi_v2_full\preflight_report.json` and passes with 499.3 GB free.

## Full preprocessing

The launcher is `scripts/preprocess_fi_dataset.py`. The production invocation uses the verified paths above, both splits, and no `--limit`.

For every recording it:

1. normalizes video/audio;
2. transcribes with one GPU-loaded Whisper model reused for the run;
3. extracts and validates OpenFace output;
4. extracts exact word-level eGeMAPS, expanding only sub-100 ms analysis windows around their midpoint when openSMILE requires more context;
5. aligns the nearest video frame to each original Whisper word midpoint;
6. writes `transcript.json`, `aligned.npz`, and `status.json` atomically;
7. removes successful intermediate media/frame files to limit storage.

It is resumable per sample. Re-running the identical command validates and skips completed `aligned.npz` artifacts. Failed/in-progress samples are retried, and failure tracebacks remain in their `status.json` files. `--force` must not be used during a normal resume.

The one-video smoke implies roughly 74.5 hours for 8,000 videos if throughput remains constant. Treat 2–4 days as the operational estimate. The laptop must be plugged in, cooled, and configured not to sleep while the process is active.

## Pre-training audit

After preprocessing, `scripts/audit_fi_preprocessing.py` validates every manifest row. Six source-verified clips for which Whisper returned no timestamped words are recorded in `configs/fi_v2/preprocessing_exclusions.v1.json`; official transcript text is not substituted because synthetic word timing is forbidden. Training must not begin until the audit reports 5,995 complete training samples, 1,999 complete validation samples, all six exact exclusions, and zero unexpected identity, label, checksum, shape, timestamp, or finite-value errors.

The Trainer independently refuses any incomplete split.

## Leakage controls and token alignment

- Acoustic and visual means/scales are fitted only on the 6,000 training samples.
- The resulting `train_only_standardizer.npz` is reused unchanged for validation.
- BERT fast-tokenizer word IDs copy each word vector to its subword tokens.
- `[CLS]`, `[SEP]`, and padding positions receive zero modality vectors.
- OpenFace `success=0` word vectors are zeroed after scaling; quality remains separate evidence and is never interpreted as capability.

## Experiment configs

All configs use local `bert-base-uncased`, maximum length 176, seed 8, learning rate `1e-5`, beta shift 1.0, dropout 0.5, batch size 2, validation every epoch, AMP, gradient clipping, and early stopping.

| Config | Experiment |
|---|---|
| `text_baseline_laptop.json` | Text only |
| `mag_bert_audio_ablation_laptop.json` | Text + audio |
| `mag_bert_visual_ablation_laptop.json` | Text + visual |
| `mag_bert_laptop.json` | Text + audio + visual MAG-BERT |
| `mag_bert_arl_laptop.json` | Full MAG-BERT-ARL, MSE |
| `mag_bert_arl_bce_laptop.json` | Full MAG-BERT-ARL, BCE |
| `mag_bert_arl_mse_bce_laptop.json` | Full MAG-BERT-ARL, MSE+BCE |

ARL uses six learner-only pretraining epochs and then alternates learner minimization with adversary maximization. Batch size cannot be one because normalized adversarial weights would be constant.

The RTX 3050 physically loads two videos at once. ARL uses a two-pass virtual batch of 128: the first pass gathers detached CLS/loss evidence and normalizes adversarial weights across all 128 samples; the second pass recomputes microbatches with identical dropout RNG states and backpropagates the fixed virtual-batch weights. This preserves the paper's large-batch ARL behavior without retaining 128 BERT graphs in VRAM.

At 3,000 physical batches per epoch, the measured GPU-only lower bound is about 15.4 minutes per ARL epoch before the two-pass virtual-batch correction. Allow approximately 30–60 minutes per adversarial epoch after its second pass, NPZ loading/tokenization, validation, and checkpoint I/O. A 25-epoch ARL run may take 12–25 hours before early stopping; each experiment must run separately.

`paper_reference_mag_bert_arl_mse.json` is a separate 200-epoch MSE schedule for the final paper-comparison run. It is the same model as the laptop MSE experiment, not an eighth model.

Recommended execution order is: text baseline, full MAG-BERT, ARL-MSE, audio/visual ablations, ARL-BCE, ARL-MSE+BCE, then the optional 200-epoch paper-reference schedule. `scripts/summarize_fi_experiments.py` creates the final CSV/JSON comparison from completed runs.

## Training outputs and recovery

Each run writes:

- immutable copied configuration;
- dataset index;
- train-only scaler (shared across runs);
- epoch metrics JSONL;
- best validation predictions CSV;
- atomic `latest.pt` checkpoint for resume;
- `best.pt` checkpoint for evaluation/deployment.
- final `training_summary.json`.

Only `latest.pt` and `best.pt` are retained, preventing dozens of multi-gigabyte duplicate checkpoints. A non-resume launch refuses a run directory that already contains state. Resume must explicitly point to that run's `latest.pt`.

Reported metrics are MAE, RMSE, Pearson correlation, and clearly thresholded accuracy/F1 at 0.5. The continuous metrics remain primary for the continuous FI interview-score label.

## Gradient SHAP

After selecting the best full multimodal checkpoint, `scripts/explain_fi_checkpoint.py` performs memory-safe sequential Gradient SHAP draws over continuous BERT word embeddings, acoustic inputs, and visual inputs. It saves raw NPZ attribution arrays, per-token contributions, modality shares, and top acoustic/visual features. The output explicitly describes only the Base Multimodal Interview Signal and must not be presented as emotion, personality, technical readiness, or a hiring judgment.
