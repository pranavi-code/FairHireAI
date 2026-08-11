# FairHireAI

FairHireAI is a student-facing placement-readiness platform for structured mock interviews. A student optionally supplies a job description (JD), selects or confirms the approved target role, uploads a resume, completes an adaptive interview, and receives evidence-backed readiness feedback, skill gaps, a learning roadmap, and progress across reattempts. When a JD is supplied, the interview profile is adapted only through approved skills and competency-weight adjustments.

This project is not a recruiter portal, applicant tracking system, student ranking system, or hire/reject automation tool. It is for student self-improvement.

## Final Project Decision

The finalized first release is:

```text
Optional JD upload
  -> when supplied, parse and map only to an approved role template
  -> otherwise search and select an approved catalog role
  -> confirm exactly one target role for the assessment
Resume upload
  -> extract Skills, Projects, Achievements, Internships, Certifications
  -> convert those items into resume evidence
  -> supplied JD adjusts only approved competency weights/skills
  -> structured adaptive mock interview
  -> questions remember earlier answers and resume evidence
  -> video/text/audio processing through the base MAG-BERT-ARL pipeline
  -> Competency Evidence Graph
  -> Technical Readiness, Communication Clarity, Interview Response Quality
  -> RAG-grounded roadmap
  -> reattempt and progress comparison
```

The earlier resume flow that only considered skills and projects is superseded. Achievements, internships, and certifications are part of the evidence layer.

See [docs/final_major_project_pdf.md](docs/final_major_project_pdf.md) for the full project and research blueprint. JD upload is optional: without one, the approved role template is used unchanged; with one, the system detects an approved role and adapts only its approved interview profile before the student confirms it.

## Approved Role Scope

- Versioned, searchable role catalog; Junior Backend Developer remains the first research-validation role.
- Every catalog role has exactly six reviewer-controlled competencies and bounded questions.
- Competency identities are role-specific; the Junior Backend Developer validation template uses programming fundamentals, API design, database reasoning, debugging/problem solving, system-design basics, and technical communication.
- One core question per competency, with at most one bounded follow-up.
- MAG-BERT-ARL is reproduced as the base research model.
- The project novelty is the Competency Evidence Graph plus auditable scorecards and grounded roadmap.

## Safety Boundaries

- Do not claim to predict hiring success.
- Do not rank students.
- Do not use sensitive attributes as normal model inputs.
- Do not infer gender, personality, or emotion from video.
- If delivery signals are shown, they stay experimental and are not used to reduce readiness.
- Every recommendation must come from a detected graph gap and a curated source.

## Intended Repository Layout

```text
frontend/
backend/
ml_service/
  training/
  inference/
  preprocessing/
  graph/
  explainability/
datasets/
  metadata_only/
configs/
docs/
tests/
deployment/
scripts/
```

Raw videos, private resumes, secrets, API keys, and large datasets must never be committed.

## ML Pipeline

The repository contains the validated FI V2 preprocessing and training stack: Whisper word timestamps, per-word 88-dimensional eGeMAPS features, 709-dimensional OpenFace alignment, train-only scaling, text/MAG modality ablations, ARL loss variants, validation metrics, and resumable checkpoints.

See [docs/ml_pipeline_runbook.md](docs/ml_pipeline_runbook.md) for paths, safeguards, experiment configs, and recovery procedures.

See [docs/product_foundation.md](docs/product_foundation.md) for the implemented
optional-JD mapping, document extraction, adaptive interview, trained-model
worker, frozen-rubric evaluation, Evidence Graph, scorecard, roadmap, privacy,
and frontend integration. See
[docs/project_completion_status.md](docs/project_completion_status.md) for the
exact local/live/human-research boundary.

For a safe GitHub push and a clean setup on another Windows computer, follow
[docs/CLONE_AND_RUN.md](docs/CLONE_AND_RUN.md). It explains why datasets,
credentials, OpenFace, model caches, and the 1.3 GB checkpoint remain outside
Git and how to configure their portable paths.

## Run the complete local product

```powershell
cd D:\FairHireAI
.\.venv\Scripts\Activate.ps1
python scripts\preflight_product.py
powershell -ExecutionPolicy Bypass -File .\scripts\start_local.ps1
```

The frontend opens at `http://127.0.0.1:3000`; FastAPI documentation is at
`http://127.0.0.1:8000/docs`. After the Supabase server secret has been stored,
pass `-WithWorker` to start real answer processing and deletion execution.

The selected model is read automatically from
`configs/fi_v2/selected_model.v1.json`; no checkpoint path needs to be copied
into `.env`.
