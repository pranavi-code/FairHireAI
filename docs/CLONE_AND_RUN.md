# Clone, configure, and run FairHireAI on another computer

This guide covers the complete Windows development setup. It deliberately
separates version-controlled source code from private credentials, datasets,
downloaded tools, and the trained model bundle.

## 1. What is and is not stored in GitHub

The Git repository contains the application source, frontend, backend, ML
pipeline code, model configuration/checksum, Supabase migrations, tests,
documentation, and small research summaries.

The following stay outside Git:

- `.env` and `frontend/.env` credentials;
- `.venv`, `node_modules`, build output, caches, logs, and PID files;
- First Impressions V2 videos and processed features;
- private resumes, JDs, interview videos, and derived user artifacts;
- OpenFace binaries/model files and downloaded Whisper/BERT model files;
- training runs and PyTorch checkpoints.

The selected `best.pt` is about 1.3 GB, above GitHub's normal single-file
limit. Transfer the runtime bundle privately or publish an access-controlled,
checksummed release artifact if its dataset/model licence permits it. Never put
student data or API keys in that bundle.

The three folders on the original laptop have separate purposes:

```text
D:\FairHireAI        Git repository: source code and small reproducibility artifacts
D:\FairHireAI-data   external datasets, model caches, preprocessing, checkpoints, runtime work
D:\FairHireAI-tools  external OpenFace installation and model files
```

Only `D:\FairHireAI` is pushed to GitHub.

## 2. Prerequisites on the new computer

For the complete GPU worker, use Windows 11 with:

1. Git.
2. Python 3.10 x64. This project requires Python `>=3.10,<3.11`.
3. Node.js 22 and Corepack/pnpm 11.9.0.
4. An NVIDIA GPU, a current driver, and a compatible CUDA-enabled PyTorch
   installation. The worker intentionally fails closed without CUDA.
5. OpenFace 2.2.0 for Windows with all model files downloaded.
6. Access to the FairHireAI Supabase project and a Gemini API key.

The UI, API, tests, and document flow can run without the external training
dataset. Real video-answer processing additionally needs the runtime bundle in
section 6.

## 3. Clone the repository

```powershell
cd D:\
git clone https://github.com/pranavi-code/FairHireAI.git
cd D:\FairHireAI
git switch main
```

Do not clone `FairHireAI-data` or `FairHireAI-tools` from GitHub; recreate or
copy them separately as described below.

## 4. Install Python and frontend dependencies

```powershell
cd D:\FairHireAI
py -3.10 -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

For an NVIDIA worker, install the CUDA-enabled PyTorch build recommended for
that computer first. Then install FairHireAI:

```powershell
python -m pip install -e ".[ml,dev]"

cd D:\FairHireAI\frontend
corepack enable
corepack prepare pnpm@11.9.0 --activate
pnpm install --frozen-lockfile
cd D:\FairHireAI
```

Confirm CUDA before starting the worker:

```powershell
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
```

The final value must be `True` for real answer processing.

## 5. Configure Supabase and Gemini safely

Create local files from the committed templates:

```powershell
Copy-Item .env.example .env
Copy-Item frontend\.env.example frontend\.env
```

Fill `.env` with:

- `ROLEREADY_SUPABASE_URL`;
- `ROLEREADY_SUPABASE_PUBLISHABLE_KEY`;
- `ROLEREADY_SUPABASE_SECRET_KEY` for the trusted worker only;
- `ROLEREADY_GEMINI_API_KEY`;
- the runtime paths from section 6.

Fill `frontend/.env` with only public browser values:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=<publishable-key>
```

Never place the Supabase secret/service-role key or Gemini key in a `VITE_*`
variable. Both real `.env` files are ignored by Git.

When reusing the existing Supabase project, do not reapply migrations or seed
records. For a new Supabase project, apply
`deployment/supabase/migrations/0001...0016` in numeric order, then follow
`deployment/supabase/README.md` to publish and validate the reviewed knowledge
and question corpus.

## 6. Install the external trained-runtime bundle

Copy these verified items from the original development machine or another
approved artifact store:

```text
best.pt
train_only_standardizer.npz
bert-base-uncased\
OpenFace_2.2.0_win_x64\
```

The OpenFace directory must contain `FeatureExtraction.exe` and its downloaded
landmark/patch-expert model files. Whisper `small.en` downloads automatically
on first use when internet access is available, or its cache can be copied.

The files may live anywhere. Example portable layout:

```text
D:\FairHireAI-runtime\selected\best.pt
D:\FairHireAI-runtime\selected\train_only_standardizer.npz
D:\FairHireAI-runtime\models\bert-base-uncased\
D:\FairHireAI-runtime\models\whisper\
D:\FairHireAI-runtime\tools\OpenFace_2.2.0_win_x64\
D:\FairHireAI-runtime\work\
```

Set these values in the root `.env`:

```text
ROLEREADY_MODEL_CHECKPOINT_PATH=D:/FairHireAI-runtime/selected/best.pt
ROLEREADY_MODEL_RUN_NAME=fi_v2_mag_bert
ROLEREADY_MODEL_CHECKPOINT_SHA256=0aaca90769f0541e615fd2cefeb25fb71ce1843e3bde311eda808da8a8d191e2
ROLEREADY_BERT_MODEL_ROOT=D:/FairHireAI-runtime/models/bert-base-uncased
ROLEREADY_SCALER_PATH=D:/FairHireAI-runtime/selected/train_only_standardizer.npz
ROLEREADY_OPENFACE_ROOT=D:/FairHireAI-runtime/tools/OpenFace_2.2.0_win_x64
ROLEREADY_WHISPER_MODEL_ROOT=D:/FairHireAI-runtime/models/whisper
ROLEREADY_WHISPER_MODEL=small.en
ROLEREADY_WORKER_ARTIFACT_ROOT=D:/FairHireAI-runtime/work
```

The checkpoint SHA-256 is verified at startup. A changed or corrupt checkpoint
is rejected.

If the approved runtime bundle is unavailable, reproduce it using
`docs/ml_pipeline_runbook.md`; this requires the properly licensed FI V2 data
and substantial preprocessing/training time.

## 7. Validate the installation

```powershell
cd D:\FairHireAI
.\.venv\Scripts\Activate.ps1
python scripts\preflight_product.py
python -m pytest -q
python -m ruff check backend ml_service scripts tests

cd frontend
pnpm test
pnpm lint
pnpm build
cd ..
```

For the complete installation, `preflight_product.py` must report no blocking
failures, a verified selected-model checksum, OpenFace ready, FFmpeg ready, and
the live worker status ready.

## 8. Start and stop the local product

Start the frontend, FastAPI backend, and trusted GPU worker:

```powershell
cd D:\FairHireAI
.\.venv\Scripts\Activate.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start_local.ps1 -WithWorker
```

Open:

- frontend: `http://127.0.0.1:3000`;
- FastAPI docs: `http://127.0.0.1:8000/docs`;
- health check: `http://127.0.0.1:8000/api/v1/health`.

Stop all three local processes cleanly:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop_local.ps1
```

Runtime logs are written to `outputs/runtime/` and remain ignored by Git.

## 9. Safely push the current repository

From `D:\FairHireAI`:

```powershell
git status --short
git status --ignored --short
git add .
git diff --cached --check
git diff --cached --stat
git status --short
git commit -m "Complete FairHireAI end-to-end platform"
git push origin main
```

Before committing, confirm that `.env`, `frontend/.env`, `.venv`,
`node_modules`, `.output`, runtime logs, datasets, tools, and `best.pt` do not
appear under staged files. To inspect the exact staged names:

```powershell
git diff --cached --name-only
```

This repository is connected to Lovable. Use normal commits and normal pushes;
never use `git push --force`, rebase published history, or amend commits that
have already been pushed.

## 10. Updating an existing clone

```powershell
cd D:\FairHireAI
git pull --ff-only origin main
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[ml,dev]"
cd frontend
pnpm install --frozen-lockfile
cd ..
python scripts\preflight_product.py
```

Local `.env` files and external runtime artifacts remain unchanged by a normal
pull.
