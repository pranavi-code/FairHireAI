# FairHireAI completion status

Last verified: 2026-08-04

## Complete locally

- FI V2 manifest and preprocessing: 7,994 usable samples; six silent/no-word
  recordings explicitly excluded.
- Seven planned training experiments and comparison artifacts.
- Selected MAG-BERT checkpoint with checksum verification, metrics, fairness
  audit, ablations, and Gradient SHAP.
- Six approved IT/software roles with six bounded competencies each.
- Optional JD detection/adaptation and mandatory student role confirmation.
- PDF, DOCX, and TXT resume extraction with evidence claims.
- Fourteen reviewed source summaries and seventeen approved learning resources.
- Thirty-six versioned question packages; independently Gemini-validated and
  embedded, with zero rejected packages in the final artifact.
- Question retrieval, validated-package freezing, bounded adaptive follow-ups,
  and consent-gated Gemini wording personalization.
- Per-answer media normalization, Whisper, eGeMAPS, OpenFace, word alignment,
  selected MAG-BERT inference, observable delivery metrics, constrained Gemini
  rubric evaluation, and private derived-artifact handling.
- Competency Evidence Graph, transparent scorecard formulas, confidence gating,
  evidence-backed skill gaps, approved roadmap selection, and reattempt
  progress deltas.
- Trusted durable processing/deletion worker implementation.
- React/Lovable frontend for auth, consent, optional JD, role selection, resume,
  interview recording, processing state, evidence report, skill gaps, roadmap,
  progress, and privacy deletion request.
- Local frontend/API integration and authenticated browser smoke test. The
  launcher writes the API origin without duplicating `/api/v1`, permits both
  localhost and loopback development origins, and normalizes duplicate Windows
  `Path`/`PATH` keys before starting child processes.
- 99 Python tests, 45 frontend tests, Ruff, ESLint, production frontend build,
  product preflight, and FFmpeg media-normalization smoke test.
- Live Supabase migrations through 0014, including frozen assessment evidence,
  worker/deletion claims, private processing artifacts, answer analyses, RLS,
  RPC permission hardening, qualified processing queries, and the reviewed
  knowledge/question corpus.
- Live retrieval smoke tests over 14 source documents, 17 learning resources,
  and 36 validated question packages, all with 384-dimensional embeddings.
- Modern server-only Supabase key stored in the git-ignored backend `.env`;
  product preflight reports the trusted worker ready.
- Local FastAPI, React frontend, and trusted processing/deletion worker running
  with successful health, role-catalog, production-build, and browser checks.
- Free Supabase Auth hardening saved: eight-character password minimum, recent
  login required for password changes, and current-password verification.
- Guarded live end-to-end verification passed with a disposable confirmed Auth
  user: consent records, role selection, 15 extracted resume claims, 12 dynamic
  core/follow-up questions, private video storage, Whisper/eGeMAPS/OpenFace,
  selected MAG-BERT inference, Gemini rubric evaluation, 108 graph nodes,
  scorecard/report, valid zero-confirmed-gap roadmap outcome, progress history,
  deletion worker, and final Auth/account cleanup.
- The live audit fixed and regression-tested worker DELETE headers, worker-loop
  resilience, an ambiguous processing RPC query (migration 0014), Gemini
  structured-output compatibility, score-boundary float drift, and PostgREST
  one-to-one scorecard handling in `/progress`.

## Requires infrastructure or people

- Public HTTPS deployment of the FastAPI backend and a GPU-capable worker;
  production `VITE_API_BASE_URL` is set only after that URL exists.
- Production email redirect/domain configuration in Supabase after the final
  frontend domain exists.
- Upgrade Supabase before a public pilot if leaked-password protection is
  required; the dashboard limits that control to the Pro plan and above.
- Faculty calibration and approval of the research set.
- A real consenting student's recorded attempt, faculty/evaluator labels, and
  usability-study results.
- Optional malware scanning and OCR hardening before accepting untrusted public
  uploads at scale.

These are not replaced with dummy data, static scores, invented links, or
fabricated research results.
