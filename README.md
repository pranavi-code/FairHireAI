# FairHireAI

FairHireAI is an evidence-backed placement-readiness platform for students. It combines
role-aware adaptive interviews, traceable resume evidence, multimodal answer processing,
auditable competency scoring, and RAG-grounded learning recommendations in one private,
consent-driven workflow.

FairHireAI is designed for student self-improvement. It is **not** a recruiter portal,
applicant-tracking system, student-ranking system, personality detector, or automated
hire/reject tool.

## System Architecture

![FairHireAI system architecture](docs/Architecture%20Diagram.png)

> The diagram uses MAG-BERT-ARL as the researched model-family label. The repository
> implements and evaluates MAG-BERT and MAG-BERT-ARL variants, while the currently
> promoted runtime checkpoint is the full text-audio-visual MAG-BERT model because it
> achieved the best overall validation performance.

## What the System Does

1. Authenticates the student with Supabase Auth and records versioned consent.
2. Lets the student select an approved junior role and optionally upload a job
   description (JD).
3. Maps a supplied JD only to approved roles, skills, and competency-weight adjustments.
4. Extracts traceable resume claims from skills, projects, internships,
   certifications, and achievements.
5. Runs a six-competency adaptive interview with one core question per competency and
   at most one evidence-justified follow-up.
6. Uses hybrid RAG to retrieve reviewed question anchors and Gemini to generate a new,
   validated, history-aware question for each interview step.
7. Processes private video answers through FFmpeg, Whisper, openSMILE/eGeMAPS,
   OpenFace, word-level alignment, BERT, and the selected MAG-BERT checkpoint.
8. Applies a constrained Gemini rubric evaluator to the frozen question, transcript,
   expected concepts, rubric, source mapping, and relevant resume evidence.
9. Builds a Competency Evidence Graph and auditable scorecards for Technical
   Readiness, Communication Clarity, and Interview Response Quality.
10. Detects evidence-backed skill gaps, retrieves only approved learning resources,
    builds a personalized roadmap, and compares progress across reattempts.

## Key Features

- Six versioned junior-role templates with six competencies per role.
- Optional JD-based profile adaptation without creating runtime rubrics.
- PDF, DOCX, text, Markdown, and consent-gated image/OCR document processing.
- Source-span-preserving resume evidence with confidence and provenance.
- Dynamic Gemini-RAG question generation with frozen assessment standards.
- Cross-attempt anti-repetition checks and bounded recovery strategies.
- Durable, idempotent processing and report-generation jobs.
- Private media and derived-artifact storage.
- Multimodal inference with checkpoint and input-artifact checksum verification.
- Evidence-linked rubric judgments, graph nodes, graph edges, scores, and gaps.
- Confidence gating that withholds Placement Readiness when evidence is insufficient.
- RAG-grounded roadmap generation restricted to reviewed resources.
- Reattempt linking and per-competency progress deltas.
- Consent history, account/attempt deletion requests, RLS, and ownership-scoped storage.

## Approved Role Scope

The current catalog contains:

- Junior Backend Developer
- Junior Frontend Developer
- Junior Full-Stack Developer
- Junior Data Analyst
- Junior Machine Learning Engineer
- Junior DevOps / Cloud Engineer

Every role has exactly six reviewer-controlled competencies. The system does not invent
new roles, competencies, rubrics, or learning resources during a student assessment.

## Dynamic Interview Design

The interview is dynamic but constrained:

- deterministic backend logic chooses the next uncovered competency;
- hybrid semantic/keyword retrieval selects validated question anchors;
- Gemini generates fresh wording from the selected role, competency, approved sources,
  resume/JD context, earlier evaluated answers, and recent same-role history;
- expected concepts, rubric levels, source mapping, follow-up rules, and reference
  explanation must remain identical to the approved anchor;
- deterministic novelty rules reject exact repeats, near-verbatim questions,
  near-paraphrases, and repeated scenario/task combinations;
- an independent Gemini validation call checks grounding and fairness;
- only an accepted question is frozen and persisted;
- no static fallback question is shown when all bounded generation stages fail.

## Multimodal Model

The repository reproduces and compares seven FI V2 experiments: text-only BERT,
text-audio and text-visual ablations, full MAG-BERT, and three MAG-BERT-ARL loss
variants. The promoted model is defined in
[`configs/fi_v2/selected_model.v1.json`](configs/fi_v2/selected_model.v1.json).

| Selected run | MAE | RMSE | Pearson | Threshold F1 |
|---|---:|---:|---:|---:|
| `fi_v2_mag_bert` | 0.094888 | 0.119559 | 0.596759 | 0.737882 |

This output is called the **Base Multimodal Interview Signal**. It is experimental
supporting evidence only and is not treated as technical readiness, personality,
emotion, employability, or a hiring prediction. MAG-BERT-ARL remains an implemented
and evaluated research comparison; it was not promoted because its overall validation
error was higher than MAG-BERT's.

## Architecture and Trust Boundaries

| Boundary | Responsibility | Sensitive material |
|---|---|---|
| React student portal | Authentication UI, uploads, interview recording, reports and privacy controls | Supabase publishable configuration only |
| Public FastAPI service | Domain validation, RAG orchestration, Gemini calls and JWT-scoped API access | Gemini key; never the Supabase secret or checkpoint |
| Supabase | Auth, PostgreSQL, pgvector retrieval, private Storage, RLS and durable queues | User-owned application data |
| Trusted CUDA worker | Media processing, model inference, rubric evaluation, reports and deletion execution | Supabase secret, checkpoint, Whisper/BERT/OpenFace assets |

The frontend passes the student's Supabase access token to FastAPI. FastAPI forwards
that token to PostgREST so database RLS remains authoritative. The trusted worker is
not publicly exposed and claims jobs outbound over HTTPS.

## Technology Stack

- **Frontend:** React, TypeScript, Vite, TanStack Router, TanStack Query, Tailwind CSS,
  shadcn/ui, Supabase JS
- **Backend:** Python 3.10, FastAPI, Pydantic, HTTPX
- **Data platform:** Supabase Auth, PostgreSQL, pgvector, PostgREST, private Storage,
  RLS and PostgreSQL RPCs
- **AI and retrieval:** Gemini structured generation and embeddings, hybrid
  semantic/keyword retrieval
- **Multimodal processing:** FFmpeg, Whisper `small.en`, openSMILE/eGeMAPSv02,
  OpenFace 2.2, BERT, MAG fusion, PyTorch
- **Explainability and evaluation:** Gradient SHAP, regression metrics, observable
  robustness audits
- **Deployment:** Dockerized public API and separately supervised Windows CUDA worker

## Repository Structure

```text
backend/                  FastAPI routes, domain contracts, services and repositories
configs/                  Role, knowledge and model configuration
deployment/               Docker, Supabase migrations and production runbooks
docs/                     Complete guide, diagrams, sources and operational notes
frontend/                 React student portal
ml_service/               Preprocessing, training, inference, fairness and SHAP
outputs/                  Versioned research and knowledge-validation results
scripts/                  Setup, preprocessing, training, seeding and verification tools
tests/                    Backend, ML, security and contract tests
```

Raw videos, resumes, credentials, model caches, external tools, datasets, and large
checkpoints must remain outside Git.

## Local Setup

### Prerequisites

- Python `>=3.10,<3.11`
- Node.js and npm/pnpm
- A configured Supabase project
- A Gemini API key
- FFmpeg
- CUDA, OpenFace, Whisper/BERT caches, scaler, and selected checkpoint when running
  the trusted worker

### Environment

Use the templates without committing populated copies:

- `.env.example`
- `frontend/.env.example`
- `deployment/backend.env.example`
- `deployment/worker.env.example`

Never place a Supabase secret, Gemini key, or private model path in a browser-exposed
`VITE_*` variable.

### Start the Local Product

```powershell
cd C:\Users\Pranavi\Documents\FairHireAI
.\.venv\Scripts\Activate.ps1
python scripts\preflight_product.py
powershell -ExecutionPolicy Bypass -File .\scripts\start_local.ps1
```

Use `-WithWorker` only on the configured trusted GPU host:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local.ps1 -WithWorker
```

Default development URLs:

- Student portal: `http://127.0.0.1:3000`
- FastAPI: `http://127.0.0.1:8000`
- API documentation: `http://127.0.0.1:8000/docs`

Detailed setup and portable-path instructions are in
[`docs/CLONE_AND_RUN.md`](docs/CLONE_AND_RUN.md).

## Verification

```powershell
pytest
ruff check backend ml_service scripts tests
cd frontend
npm test
npm run build
```

Deployment-specific checks and guarded live E2E commands are documented in
[`deployment/PRODUCTION_RUNBOOK.md`](deployment/PRODUCTION_RUNBOOK.md). Live scripts
use explicit safety flags because they create and delete real Supabase resources.

## Privacy and Safety

- Consent is checked again on the server before resume processing, recording,
  external-AI processing, and reporting.
- Storage keys are user-scoped and buckets are private.
- User-facing requests use JWT-scoped RLS access.
- Worker-only writes require the trusted server credential.
- Sensitive attributes are not normal model inputs.
- Audio/video processing does not claim emotion, gender, personality, nervousness,
  confidence, or employability inference.
- Delivery measurements remain separate from Placement Readiness.
- Missing evidence produces an unavailable or insufficient-evidence state rather than
  fabricated certainty.
- Recommendations are restricted to graph-supported gaps and reviewed resources.

## Current Boundaries

The repository contains the full local implementation, model experiments, migrations,
worker, frontend, RAG corpus, automated tests, and deployment package. A public pilot
still requires production HTTPS hosting, a supervised GPU worker, final Auth/email
configuration, faculty calibration, consenting student participation, human evaluator
labels, and usability-study results. Those external results must not be fabricated.

## Complete Documentation

The authoritative A-to-Z description of the product, research, architecture,
algorithms, data contracts, scoring, security, deployment, testing, limitations, and
viva material is:

**[`docs/full_architecture_viva_guide.md`](docs/full_architecture_viva_guide.md)**

Additional operational references:

- [`docs/CLONE_AND_RUN.md`](docs/CLONE_AND_RUN.md)
- [`docs/ml_pipeline_runbook.md`](docs/ml_pipeline_runbook.md)
- [`deployment/PRODUCTION_RUNBOOK.md`](deployment/PRODUCTION_RUNBOOK.md)
- [`docs/sources.csv`](docs/sources.csv)

## Research and Ethical Position

FairHireAI evaluates whether evidence-backed, role-specific feedback can make mock
interview preparation more transparent and actionable. It does not establish hiring
validity, employment success, demographic fairness, or psychological interpretation.
Any such claim requires separate consented research, qualified human evaluation, and
appropriate institutional review.
