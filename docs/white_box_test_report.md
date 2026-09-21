# FairHireAI White-Box Test Report

> 2026-09-14 update: the repeated-question/false-503 interruption was redesigned and
> regression-tested. See
> [Repeated-question and 503 interruption fix report](repeated_question_generation_fix_report.md)
> for the root cause, algorithm, exact Data Analyst acceptance result, live read-only
> verification, and updated test totals (211 Python + 58 frontend tests passing).

Audit completed: 2026-09-13  
Repository: `D:\FairHireAI`  
Live Supabase project: `gfsetwljirztyxegiets` (`FairHireAI`, `ACTIVE_HEALTHY`)  
Public deployment performed: **No**

## Scope and safety

The audit covered the blueprint and run guides, backend, frontend, ML preprocessing,
inference and training code, trusted worker, Supabase migrations and policies, tests,
deployment checks, and the complete student flow. Existing datasets, checkpoints,
training runs, production users, and non-test Storage objects were not modified.

Live writes were limited to the two explicitly approved migrations and one uniquely
identified disposable two-user E2E run. The E2E tracked its users, attempt, answers,
jobs, consent rows, and Storage paths and removed only those resources. No secret was
printed, logged, committed, placed in the frontend, or included in this report.

## Execution flow verified in code

1. Supabase Auth issues a user session; the backend resolves the user independently
   from the bearer token.
2. Append-only consent records gate resume processing, recording, and external-AI use.
3. The student selects one of six reviewed roles. A JD is optional; if supplied it is
   parsed and used to adapt only the selected role's reviewed competency weights.
4. The resume is parsed into traceable claims and stored in a private owner path.
5. Hybrid RAG retrieves a validated package as the assessment anchor. With explicit
   external-AI consent, Gemini must generate every core question and follow-up from
   that anchor, minimized resume/JD context, prior answer evidence, and recent
   same-role history. Repeated or independently rejected output fails closed; the
   generated prompt and its model/version are frozen with the anchor rubric.
6. The student uploads an answer video; an idempotent processing job is queued.
7. The trusted worker checksum-verifies and normalizes the media, then runs Whisper,
   OpenFace, eGeMAPS alignment, the selected MAG-BERT checkpoint, and constrained
   Gemini evidence evaluation.
8. The selector asks one core question per competency and at most one justified
   follow-up. Manual submission is allowed after 6 evaluated answers; the hard maximum
   is 12.
9. The authenticated report RPC atomically validates ownership, latest consent,
   completion state, answer count, retry limit, and idempotency before queueing the
   report job.
10. Report generation creates the evidence graph and confidence-gated scorecard.
    Adequately evidenced scores below 0.70 become fixed numeric skill gaps; Gemini
    explains them using answer evidence. Hybrid RAG selects only approved learning
    resources, then Gemini personalizes their sequence and rationale without being
    allowed to change scores, gaps, resource IDs, or URLs. Reports and later-attempt
    comparisons are rendered from persisted backend data.

## Changes made in this phase

### Database migrations

- `deployment/supabase/migrations/0016_authenticated_table_privilege_hardening.sql`
  explicitly scopes default privileges to the `postgres` owner, revokes broad table
  privileges from `anon` and `authenticated`, and re-grants only the intended least
  privileges.
- `deployment/supabase/migrations/0017_authenticated_report_enqueue_rpc.sql` adds:
  - a non-exposed `private.enforce_current_consent()` trigger function;
  - database-enforced latest consent for resume attachment, answer submission, and
    queued answer/report jobs;
  - `public.request_attempt_report(uuid)`, an authenticated, owner-scoped, atomic,
    idempotent report-enqueue RPC with fixed empty `search_path` and explicit ACLs.

### Backend and live-E2E code

- `backend/app/repositories/supabase.py` now calls the authenticated
  `request_attempt_report` RPC using the caller's JWT.
- `backend/app/api/v1/journey.py` no longer constructs a worker/service-role repository
  for public report submission and no longer requires the Supabase server secret on
  that route.
- `scripts/live_two_user_security_e2e.py` performs a project-locked, disposable,
  two-user Auth/RLS/Storage/consent/worker/report/deletion test with exact cleanup.

### Regression tests

- `tests/backend/test_attempts.py`: authenticated report-RPC success and validation
  error mapping.
- `tests/backend/test_consent_enforcement.py`: report submission succeeds without a
  usable service-role secret and remains consent-gated.
- `tests/backend/test_persistence_contract.py`: migration 0017 function, trigger,
  transaction, idempotency, and ACL contract.
- `tests/backend/test_live_two_user_security_e2e_contract.py`: project guard, mutation
  guard, isolation assertions, and cleanup-verification contract.
- `tests/backend/test_live_product_e2e_contract.py`: local API health endpoint contract.
- `tests/backend/test_attempt_reporting.py`: complete evidence-builder regression proving
  adequate-but-low evidence creates skill-gap nodes, invokes resource retrieval, and
  emits hybrid-RAG roadmap items.
- `tests/backend/test_dynamic_interview.py`: every persisted interview prompt is a
  newly generated, auditable Gemini result and static fallback is prohibited.
- `tests/backend/test_gemini.py`: evaluated-answer follow-up context, independent
  grounding validation, and exact/near-duplicate rejection.
- `tests/backend/test_grounded_guidance.py`: evidence-derived gap constraints,
  approved-resource roadmap constraints, and rejection of invented resources.
- `tests/backend/test_journey_views.py`: bounded, RLS-scoped same-role question history.

## Exact live changes applied

Before each approved migration, the active project was re-read and verified as project
reference `gfsetwljirztyxegiets`, name `FairHireAI`, status `ACTIVE_HEALTHY`.

| Live migration version | Name | Result |
|---|---|---|
| `20260913051114` | `authenticated_table_privilege_hardening` | Applied successfully |
| `20260913051803` | `authenticated_report_enqueue_rpc` | Applied successfully |

The live migration history now contains migrations 0001 through 0017. No other live
migration or configuration change was made.

## Final automated verification

| Check | Result | Executed evidence |
|---|---:|---|
| Python unit/integration suite | PASS | 160 passed, 0 failed, 1 Starlette/httpx deprecation warning |
| Python statement coverage | 75.46% | 2,607 / 3,455 statements in `backend.app` |
| Python branch coverage | 51.51% | 443 / 860 branches in `backend.app` |
| Frontend tests | PASS | 58 passed, 0 failed |
| Frontend statement coverage | 37.42% | 183 / 489 statements |
| Frontend branch coverage | 33.24% | 132 / 397 branches |
| Frontend function coverage | 28.36% | 40 / 141 functions |
| Frontend line coverage | 38.53% | 168 / 436 lines |
| TypeScript | PASS | `tsc --noEmit` exited zero |
| Ruff | PASS | zero findings |
| ESLint | PASS with warnings | zero errors; 12 Fast Refresh warnings |
| Production frontend build | PASS | client, SSR, and Cloudflare/Nitro output built |
| Frontend dependency audit | PASS | no known production vulnerabilities |
| Python dependency audit | FAIL/REVIEW | 8 known findings in Transformers 4.57.6; fix requires a 5.x upgrade |
| Bandit | REVIEW | 0 high, 12 medium, 13 low findings |
| Worker deployment preflight | PASS | checkpoint SHA, scaler, BERT, OpenFace, FFmpeg, Gemini, and server key ready |
| API deployment preflight | BLOCKED | local CORS, worker availability flag false, and shared local env still contains server key |
| Frontend deployment preflight | BLOCKED | API base is local HTTP, not public HTTPS |
| Live hybrid RAG smoke test | PASS | 384-d embedding, validated question, 2 approved resources, zero writes |

The frontend coverage/build commands initially encountered Windows sandbox file-lock
errors while creating/removing generated coverage and `.output` files. Both were rerun
with the required local filesystem permission and passed; those were execution-environment
errors, not application-test failures.

## Live two-user E2E result

Final disposable run ID: `7ed0d56ab20a`

| Check | Result |
|---|---:|
| Disposable authenticated users | 2 created and exercised |
| Real interview answers | 6 uploaded and processed |
| Processing chain | Whisper, OpenFace, eGeMAPS, MAG-BERT, Gemini all completed |
| Report enqueue | Authenticated RPC used |
| Idempotency | Repeat finish request created zero duplicate jobs |
| Report jobs | Exactly 1 |
| Resume claims | 15 persisted during the run |
| Evidence nodes | 66 persisted during the run |
| User B access to User A API/report/rows | Denied or empty as required |
| User B download/delete of User A Storage object | Denied; User A object remained unchanged |
| Consent-negative resume/answer/external-AI operations | Rejected as required |
| Report ownership | User A allowed; User B denied |
| Account/deletion flow | Completed for disposable resources |
| Cleanup | Verified successful |

Post-cleanup database verification found zero consent rows tagged with the run ID.
Post-cleanup Auth verification found zero users whose disposable address contained the
run ID, and Storage verification found zero objects containing the run ID. The guarded
harness also verified its tracked users, profiles, attempt-owned rows, jobs, and objects
were absent before returning `cleanup_verified: true`.

### Strengthened owner-write rerun

A subsequent strengthened run added direct owner-write probes for migration 0016. User A
was denied both a direct PostgREST update and direct delete of User A's own trusted
attempt row, and the row survived unchanged. The run then processed one real answer but
stopped when the next disposable Storage upload raised `httpx.WriteTimeout`.

Per the approved stop-on-unexpected-Storage-failure rule, the live test was not retried
and no corrective production change was made. Cleanup ran successfully. A fresh
project-verified query returned zero `fairhireai-e2e-*` Auth users, zero synthetic E2E
consent rows, and zero Storage objects under an `/e2e/` path. The completed six-answer
run above remains the evidence for the full journey; this stopped rerun is additional
evidence that an owner can no longer directly mutate trusted attempt state.

## Live Supabase permission and RLS result

- Every inspected public table has RLS enabled; the query for public tables without RLS
  returned no rows.
- Trusted result/lifecycle tables including attempts, questions, answers, analyses,
  jobs, evidence, scorecards, roadmaps, and progress are `SELECT`-only for
  `authenticated`.
- `consent_records` and `deletion_requests` are `INSERT, SELECT`; `profiles` retains
  owner CRUD. No broad authenticated `TRUNCATE`, `TRIGGER`, or `REFERENCES` grant remains.
- `private.enforce_current_consent()` is not executable by `anon` or `authenticated`;
  it is service-only, SECURITY DEFINER, and has `search_path=""`.
- `public.request_attempt_report(uuid)` is not executable by `anon`; it is executable
  by `authenticated` and `service_role`, is SECURITY DEFINER, and has
  `search_path=""`.

Supabase's security advisor still reports eight authenticated SECURITY DEFINER RPCs.
These are intentional public write boundaries, but each must remain narrow and reviewed.
The advisor also reports leaked-password protection disabled. The performance advisor
reports 30 currently unused indexes at INFO level; no indexes were removed because this
young database has insufficient usage history for a safe deletion decision.

## Public report path and service-secret verification

The public `POST /attempts/{attempt_id}/finish` path now calls
`SupabaseAttemptRepository.request_report_generation()`, which sends the authenticated
user JWT to the validated RPC. It does not instantiate `SupabaseWorkerRepository` and
does not read `supabase_secret_key`.

This is backed by:

- a unit test that executes the route with no usable server secret;
- repository tests that assert the authenticated RPC request and error mapping;
- the live E2E result `report_enqueue_mode: authenticated_rpc`;
- a cross-user live call proving User B cannot enqueue User A's report.

The local `.env` is shared by the API and worker and still contains the server key, so
the API deployment preflight correctly remains blocked. Production must use separate
API and worker environments; the API environment must omit the server secret even
though this report path no longer depends on it.

## Expected versus actual failures and partial results

### Non-empty live roadmap

Expected: a roadmap only when an evaluated competency has coverage at least 0.70 and
score below 0.70. Actual: the disposable six-answer media fixture produced zero roadmap
items because it did not establish adequate technical evidence coverage. This is the
correct fail-closed behavior; lowering the threshold would create unsupported skill-gap
claims. The complete gap-to-roadmap branch passed an executed report-builder regression
test, and live read-only RAG returned approved resources, but a non-empty roadmap from a
natural live interview remains unexecuted.

### Deployment preflights

Expected for public deployment: public HTTPS API URL, production CORS, explicit external
worker availability, and separate secret scopes. Actual: the worker is ready locally,
but API and frontend are intentionally configured for local development. Public
deployment was not authorized and was not attempted.

### Python dependency audit

Expected: no known production vulnerability. Actual: eight advisories remain against
Transformers 4.57.6; available fixes require migration to Transformers 5.x. Torch and
the CUDA-specific torchvision build were not fully auditable through PyPI metadata.

## Hardcoded, fallback, and mock behavior review

- No hardcoded/dummy score, report, progress row, processing timer, or successful ML
  fallback was found. Missing checkpoints/configuration fail closed.
- Role templates, competency weights, the 0.70 evidence/gap thresholds, and validated
  question packages are reviewed/versioned policy configuration, not fabricated output.
- The student journey no longer substitutes a fixed package when Gemini generation,
  grounding, novelty, or independent validation fails. It returns an explicit
  cause-specific retryable error after up to three content-generation attempts,
  preventing the UI from claiming a dynamic question was produced.
- The processing page polls real job state and has no simulated completion timer.
- Test code uses mocks and synthetic/disposable fixtures; those values are not reachable
  as production scoring/report fallbacks.
- The phrase “mock interview” in the UI describes the practice-interview format, not
  mocked backend data.

## Remaining security risks and untested branches

1. **High:** public API and frontend production preflights are blocked until hosted HTTPS
   endpoints, final CORS/Auth redirects, and split API/worker environments exist.
2. **High:** Transformers 4.57.6 has eight known advisories; a controlled 5.x migration
   and real checkpoint regression are required before public deployment.
3. **Medium:** Supabase leaked-password protection is disabled; enabling it is an Auth
   configuration change and was outside the approved migration-only scope.
4. **Medium:** eight authenticated SECURITY DEFINER RPCs remain deliberate trust
   boundaries. The new report RPC was adversarially tested, but older RPC argument and
   concurrency surfaces need continued review/fuzzing.
5. **Medium:** Python branch coverage is 51.51%; worker/provider/repository failure paths,
   process crashes, long network partitions, and concurrent multi-worker leasing are not
   exhaustively executed.
6. **Medium:** frontend branch coverage is 33.24%; full browser interaction/accessibility
   coverage across every route and device is not available.
7. **Medium:** a natural live interview that produces adequate evidence, non-empty skill
   gaps, a persisted RAG roadmap, and a second comparable attempt has not been executed.
8. **Low:** ESLint reports 12 Fast Refresh structure warnings.
9. **Low/operational:** Auth access-token invalidation immediately after account deletion
   was not separately verified; RLS-owned data removal and subsequent protected-resource
   isolation were verified.

## Major-flow classification

| Major flow | Classification | Executed evidence |
|---|---|---|
| Authentication | verified working | Two live disposable users authenticated |
| Cross-user database/API isolation | verified working | User B reads/mutations/enqueue against User A denied or empty |
| Owner trusted-table write isolation | verified working | User A direct update/delete denied live; grants are read-only |
| Storage isolation | verified working | Cross-download and cross-delete denied live |
| Consent enforcement | verified working | Backend plus database rejection paths executed live |
| Role selection | verified working | Six-role domain/API tests pass |
| Optional JD parsing/adaptation | verified working | PDF/DOCX/TXT/image/OCR branches tested; no live OCR call in final E2E |
| Resume upload/claims | verified working | Live private upload and 15 extracted claims |
| Adaptive interview minimum 6 | verified working | Six-question live run and frontend/backend tests |
| Adaptive interview maximum 12 | implemented but not executed live | Selector/database/frontend contract tests pass |
| Answer upload, queue, retry, idempotency | verified working | Six live jobs plus retry/idempotency tests |
| Whisper/OpenFace/eGeMAPS | verified working | Six disposable videos processed by the live local worker |
| Selected MAG-BERT inference | verified working | Live E2E and checksum-verified CUDA inference |
| Gemini answer evaluation | verified working | Six live evaluations plus malformed/429/timeout tests |
| Evidence graph and scorecard | verified working | Live report contained 66 nodes and a real scorecard |
| Insufficient-evidence behavior | verified working | Live low-coverage result correctly withheld unsupported claims |
| Gemini-RAG dynamic core/follow-up questions | implemented but not executed live after change | Local service/journey tests prove answer context, same-role history, novelty rejection, frozen generated IDs, and no fixed fallback; live natural interview rerun remains |
| LLM-grounded skill-gap guidance and resource roadmap | implemented but not executed live after change | Local tests prove fixed evidence-derived gaps, Gemini narratives, reviewed-resource constraints, and rejection of invented resources; non-empty natural live roadmap remains |
| Report ownership and submission | verified working | Authenticated RPC, idempotency, and cross-user denial live |
| One-attempt progress view | verified working | Disposable completed attempt appeared in progress API |
| Reattempt comparison | implemented but not executed live | Domain/repository tests only |
| Account deletion and E2E cleanup | verified working | Tracked disposable resources removed and absence rechecked |
| Public deployment | blocked | API/frontend production preflights fail local-only settings |

## Public-deployment blockers

FairHireAI must not be described as safely public-deployment-ready until all of the
following are resolved and re-tested:

1. deploy FastAPI behind public HTTPS with production CORS and Auth redirect URLs;
2. run a continuously available compatible GPU worker;
3. split API and worker environments and omit the Supabase server secret from the API;
4. point the frontend to the public HTTPS API and rerun both deployment preflights;
5. migrate/risk-accept the remaining Transformers advisories;
6. enable or explicitly risk-accept leaked-password protection;
7. run browser E2E/accessibility tests and a natural adequate-evidence roadmap flow;
8. run a live second-attempt comparison and an intentional worker-crash/recovery test;
9. complete faculty calibration and a consented student evaluation before making
   research-validity or fairness claims.

The current result is a real, functioning, security-hardened local prototype with a
successful adversarial live E2E—not yet a publicly deployed production service.
