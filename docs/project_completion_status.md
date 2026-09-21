# FairHireAI completion status

Last verified: 2026-09-14

## Complete locally

- FI V2 manifest and preprocessing: 7,994 usable samples; six silent/no-word
  recordings explicitly excluded.
- Seven planned training experiments and comparison artifacts.
- Selected MAG-BERT checkpoint with checksum verification, metrics, fairness
  audit, ablations, and Gradient SHAP.
- Six approved IT/software roles with six bounded competencies each.
- Optional JD detection/adaptation and mandatory student role confirmation.
- PDF, DOCX, TXT/MD, JPG/JPEG, PNG, and WEBP resume extraction with evidence
  claims; scanned/image OCR is consent-gated and performed only by the backend.
- Fourteen reviewed source summaries and seventeen approved learning resources.
- Thirty-six versioned question packages used as independently Gemini-validated,
  embedded grounding/rubric anchors, with zero rejected packages in the final artifact.
- The student journey now requires consent-gated Gemini generation for every core
  question and follow-up. Hybrid RAG retrieves a reviewed anchor; Gemini receives
  minimized resume/JD context, prior evaluated-answer evidence, and recent same-role
  question history. Exact/near-verbatim repetition and an independent semantic
  validation failure are rejected instead of silently showing a fixed question.
  Generated prompts are frozen in `interview_questions` with a unique generated ID,
  model ID, prompt version, selection reason, anchor package, rubric, concepts, and
  source mapping for audit and future anti-repetition.
- Per-answer media normalization, Whisper, eGeMAPS, OpenFace, word alignment,
  selected MAG-BERT inference, observable delivery metrics, constrained Gemini
  rubric evaluation, and private derived-artifact handling.
- Competency Evidence Graph, transparent scorecard formulas, confidence gating,
  evidence-backed skill gaps, Gemini-generated gap explanations/practice focuses,
  graph-guided semantic/keyword retrieval of only approved roadmap resources, and
  Gemini-personalized roadmap order/rationales constrained to those retrieved
  resources, plus reattempt progress deltas. Gemini cannot alter numeric scores,
  create gaps without adequate evidence, or introduce unreviewed resources.
- Trusted durable processing/deletion worker implementation.
- React/Lovable frontend for auth, consent, optional JD, role selection, resume,
  interview recording, processing state, evidence report, skill gaps, roadmap,
  progress, and privacy deletion request.
- Local frontend/API integration and authenticated browser smoke test. The
  launcher writes the API origin without duplicating `/api/v1`, permits both
  localhost and loopback development origins, and normalizes duplicate Windows
  `Path`/`PATH` keys before starting child processes.
- 160 Python tests and 58 frontend tests pass. Measured backend application coverage is
  75.46% Python statements / 51.51% Python branches and measured frontend coverage is
  37.42% statements / 33.24% branches. Ruff and TypeScript pass; ESLint has
  zero errors and twelve non-blocking fast-refresh warnings; the production
  frontend build passes.
- Live Supabase migrations through 0015, including frozen assessment evidence,
  worker/deletion claims, private processing artifacts, answer analyses, RLS,
  RPC permission hardening, qualified processing queries, and the reviewed
  knowledge/question corpus.
- Live retrieval smoke tests over 14 source documents, 17 learning resources,
  and 36 validated question packages, all with 384-dimensional embeddings. A
  deliberate API-design skill gap retrieved MDN and OWASP resources with no
  database writes.
- Modern server-only Supabase key stored in the git-ignored backend `.env`;
  product preflight reports the trusted worker ready.
- Local FastAPI, React frontend, and trusted processing/deletion worker running
  with successful health, role-catalog, production-build, and browser checks.
- Deployment package separates the public FastAPI container from the private
  GPU worker, keeps the Supabase secret and ML runtime out of the public image,
  provides API/worker environment templates and Windows worker supervision,
  and includes component-specific preflight checks. The backend Docker image
  builds successfully and its built-in health check reports healthy.
- Free Supabase Auth hardening saved: eight-character password minimum, recent
  login required for password changes, and current-password verification.
- Guarded live end-to-end verification passed with a disposable confirmed Auth
  user under the preceding question-personalization flow: consent records, role
  selection, 15 extracted resume claims, 12 bounded core/follow-up questions,
  private video storage, Whisper/eGeMAPS/OpenFace,
  selected MAG-BERT inference, Gemini rubric evaluation, 108 graph nodes,
  scorecard/report, valid zero-confirmed-gap roadmap outcome, progress history,
  deletion worker, and final Auth/account cleanup.
- The newer all-Gemini question generation, cross-attempt anti-repetition, answer-adaptive
  follow-ups, grounded gap narratives, and constrained roadmap personalization pass local
  regression tests but still require a fresh live natural-interview E2E before being
  classified as live verified.
- Supabase clients use bounded connection retries so brief DNS/TLS connection
  failures do not immediately abort API or worker requests. Interrupted smoke
  tests were fully cleaned; live verification confirmed zero leftover users,
  attempts, or storage objects.
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

## Approval-gated security work found by white-box audit

- The live `authenticated` database role currently retains broad table-level
  write privileges. RLS prevents cross-user access, but owner policies make
  worker-owned rows mutable by their owner through direct PostgREST calls.
  Migration 0016 is prepared and regression-checked locally but has not been
  applied to the live project.
- The public API preflight is blocked because the current early-finish endpoint
  uses the Supabase server secret. Moving report enqueueing into a validated,
  authenticated database RPC is required before a public API deployment.
- A current disposable-user, two-user RLS, Storage, Auth, and deletion E2E was
  not executed during the 2026-09-12 audit because it writes and deletes live
  Supabase resources and requires explicit approval.
- Python dependency auditing is clean except for the pinned Transformers 4.x
  runtime. Available fixes require a major Transformers upgrade and real
  checkpoint compatibility validation; the production path mitigates exposure
  by loading the vetted BERT copy locally and checksum-verifying the selected
  checkpoint before deserialization.

These are not replaced with dummy data, static scores, invented links, or
fabricated research results.
