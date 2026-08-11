# Supabase persistence foundation

The migrations define the production persistence and privacy foundation. They
are not applied automatically:

Apply every numbered file in `migrations/` in order. Migrations 0001 through
0014 are present in the connected project. Migration 0012 adds frozen
question/rubric/source snapshots, per-answer analyses, atomic worker claims,
private processing artifacts, and atomic deletion claims. Migration 0013
removes inherited anonymous table privileges from `answer_analyses`. Migration
0014 qualifies processing-RPC columns to avoid PL/pgSQL name ambiguity.

Important operational requirements:

- Apply migrations through a reviewed Supabase development project first.
- Store resumes, JDs, and answer videos in private buckets; database rows contain storage keys, never public URLs.
- Use short-lived signed URLs only after ownership checks.
- The browser must never receive the service-role key.
- Durable workers use the service role for processing-job transitions; students can only read their own job status.
- Row-level security is enabled for every user or attempt-linked table.
- Approved learning resources are globally readable; pending resources are not.
- Backups, retention periods, consent withdrawal, and deletion jobs must be configured before the student pilot.

Private buckets created by migration 0002:

```text
roleready-documents
roleready-interview-video
roleready-derived-artifacts
```

Migration 0012 adds:

```text
roleready-processing-artifacts
```

User uploads are restricted to a top-level folder named with the authenticated
user ID. Derived artifacts have no direct student policy. Migration 0002 also
adds append-only consent records and durable deletion requests.

Do not create a public bucket for interview media.

Migrations 0001 through 0014 were applied to the `FairHireAI` Supabase project
(`gfsetwljirztyxegiets`) after explicit approval. The reviewed
knowledge and question corpus was then published and retrieval-smoke-tested.
Apply the same ordered migration set to any future environment; do not edit the
live schema manually.

The local ignored `.env` contains the project URL and modern publishable key.
Student-facing API calls forward the signed-in user's access token. Only the
trusted processing/deletion worker and seed scripts use
`ROLEREADY_SUPABASE_SECRET_KEY`; it must never appear in frontend `.env`,
browser requests, logs, or source control.
