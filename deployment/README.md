# FairHireAI deployment

The student frontend is hosted by Lovable, authentication/private storage and
PostgreSQL are hosted by Supabase, and this directory packages the FastAPI and
model-inference boundary.

Copy `deployment/backend.env.example` to `deployment/backend.env`, set the
Supabase public project values, Gemini key, external-worker declaration, and
CORS origin, then run:

```powershell
docker compose -f deployment/docker-compose.yml up --build
```

The container exposes `/api/v1/health`, `/api/v1/capabilities`, and OpenAPI at
`/openapi.json`. The public API does not need the private checkpoint or
Supabase server secret. It may enqueue jobs only after
`ROLEREADY_TRUSTED_WORKER_AVAILABLE=true` declares that the separate worker has
passed its own deployment preflight.

`POST /api/v1/attempts/{id}/process` fails closed until those checkpoint
settings verify a real file. Once configured, it uses the authenticated,
idempotent `enqueue_attempt_processing` RPC to create durable jobs. A separate
service-role worker must claim and execute those jobs; the API container never
pretends that queueing is completed inference.

For a hosted Lovable preview, deploy this container to a public HTTPS service
and set its URL as `VITE_API_BASE_URL`. A browser-hosted frontend cannot use a
private laptop-only `localhost` backend.

Follow `PRODUCTION_RUNBOOK.md` for the complete API, worker, frontend, Auth,
secret-separation, and release-verification sequence.
