# FairHireAI production deployment runbook

The deployable system has three separate trust boundaries:

1. **Frontend:** Lovable/Cloudflare-hosted React application. It receives only
   the Supabase URL, publishable key, and public HTTPS API URL.
2. **Public API:** the container in `Dockerfile.backend`. It forwards each
   student's JWT so Supabase RLS remains authoritative. It holds the Gemini key
   for consent-gated question retrieval/personalization, but never the Supabase
   server secret or private model files.
3. **Trusted GPU worker:** a supervised Windows CUDA host containing OpenFace,
   Whisper, BERT, the standardizer, selected checkpoint, Gemini key, and
   Supabase server secret. It is not exposed to the public internet.

## 1. Verify the trusted worker

On the RTX host, keep the populated repository-root `.env` private and run:

```powershell
cd D:\FairHireAI
.\.venv\Scripts\python.exe scripts\preflight_deployment.py worker
```

Start it through a Windows service manager or Task Scheduler using:

```powershell
powershell -ExecutionPolicy Bypass -File deployment\run_windows_worker.ps1
```

Configure the supervisor to start at boot and restart after a non-zero exit.
Do not expose a worker port; it claims durable Supabase jobs outbound over HTTPS.

## 2. Deploy the public API

Copy `deployment/backend.env.example` to `deployment/backend.env` only for a
local container check. In production, enter the same variables in the hosting
provider's secret manager. Use the real frontend origin and set
`ROLEREADY_TRUSTED_WORKER_AVAILABLE=true` only after step 1 passes.

The public API must not receive `ROLEREADY_SUPABASE_SECRET_KEY`, the checkpoint,
the dataset, OpenFace, Whisper, or BERT files.

```powershell
docker compose -f deployment\docker-compose.yml up --build
```

After assigning a public HTTPS hostname, run inside the configured deployment
environment:

```powershell
python scripts\preflight_deployment.py api
```

Verify `GET https://<api-host>/api/v1/health` and
`GET https://<api-host>/api/v1/capabilities`.

## 3. Configure and publish the frontend

Set these Lovable build variables:

```text
VITE_API_BASE_URL=https://<api-host>
VITE_SUPABASE_URL=https://gfsetwljirztyxegiets.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=<current publishable key>
```

`VITE_API_BASE_URL` deliberately excludes `/api/v1`; the frontend endpoint
helpers add it. Never add the Gemini key or Supabase secret to a `VITE_*` value.

Before publishing, validate the downloaded production environment locally:

```powershell
python scripts\preflight_deployment.py frontend --frontend-env frontend\.env.production
```

## 4. Finish Supabase Auth configuration

In Authentication URL configuration, set the Site URL to the final frontend
HTTPS origin. Add only the required production callback and password-reset
paths to Redirect URLs. Remove obsolete preview origins after acceptance.

Use a real SMTP provider before a public pilot. Keep private buckets private,
and retain the existing RLS policies and authenticated-only retrieval RPCs.

## 5. Release verification

Run, in order:

```powershell
python scripts\smoke_test_live_rag.py
python scripts\live_product_e2e.py --api-base-url https://<api-host>/api/v1 --i-understand-live-writes
```

Then complete one consenting browser attempt, confirm a report with evidence,
and submit a deletion request. The guarded E2E script creates and deletes only
its own disposable user.
