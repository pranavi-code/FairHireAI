# Repeated-question and 503 interruption fix report

Audit date: 2026-09-14  
Repository: `D:\FairHireAI`  
Verified live Supabase project: `gfsetwljirztyxegiets`  
Public deployment performed: **No**

## 1. Root cause

The interruption was an application-generation failure, not a network, GPU, or
Supabase outage.

At task start, the live Data Analyst attempt selected `data_visualization`, RAG
returned the same single approved anchor, Gemini produced three paraphrases, and the
anti-repetition filter rejected all three. The retry loop changed wording guidance but
kept essentially the same anchor and generation shape. Its content-rejection exception
was a `GeminiProviderError`, so `next_persisted_question()` misclassified exhausted
policy candidates as provider unavailability and returned HTTP 503.

The causes confirmed in code and live data were:

- `HybridRagService` consumed only the first semantic match rather than exposing an
  anchor pool.
- Every Data Analyst competency has only one live validated anchor.
- Recent question history was same-role but not competency-scoped.
- The old duplicate rule was lexical (`SequenceMatcher >= 0.88`) or token-Jaccard
  (`>= 0.86`), so it could reject reasonable shared competency vocabulary without
  distinguishing scenario and reasoning structure.
- Three retries ended immediately; there was no anchor/scenario/structure/rubric
  progression or dynamic final fallback.
- A model content rejection inherited the infrastructure-provider exception type.
- Only accepted prompts were persisted, so rejected candidates were not the source of
  database-history pollution.

## 2. Original execution path

The immediate pre-fix path was:

`select_next_question()` → exact validated package → same-role history → Gemini query
embedding → first RAG match → Gemini candidate → lexical similarity rejection → repeat
three times with the same effective anchor → content exception treated as provider
error → HTTP 503 → frontend error state.

The frontend had `retry: false`; it did not create an automatic retry storm. Its
`resolveCurrentQuestion()` guard also suppresses a stale previously successful
question while a new request is in error.

## 3. Reproduction evidence

Before the fix, the local backend runtime recorded three consecutive
`data_visualization` content rejections followed by:

`GET .../next-question HTTP/1.1 503 Service Unavailable`

The affected live attempt was a Data Analyst interview, and the log explicitly showed
`follow_up=False`, so the failure was the core-question anti-repetition path rather
than video processing. The deterministic regression fixture preserves this condition:
three repetitive Data Analyst visualization candidates are rejected before a fourth,
materially different candidate is returned.

## 4. Changes made

### Runtime code

- `backend/app/services/question_novelty.py`
  - Added normalized lexical, canonical concept, scenario, and question-structure
    analysis.
  - Added a compact, deduplicated history-theme representation for Gemini.
  - Added strict and controlled-final-stage decisions without disabling exact,
    near-verbatim, near-paraphrase, or same-scenario/same-task protection.
- `backend/app/services/adaptive_question_generation.py`
  - Added an eight-stage bounded recovery engine.
  - Carries rejected candidate themes to subsequent attempts.
  - Rotates anchors and generation instructions, uses a per-attempt nonce, and emits
    structured safe diagnostics.
- `backend/app/services/hybrid_rag.py`
  - Added `retrieve_question_candidates()` to validate/deduplicate up to five matches.
  - Recently used anchor IDs are sorted behind unused alternatives.
- `backend/app/services/grounded_questions.py`
  - Made content rejection a domain `ValueError`, not a provider outage.
  - Sends compact historical and rejected themes, strategy/scenario/structure
    instructions, and a generation nonce to Gemini.
  - Uses generation temperature `0.9` and independent validation temperature `0.1`.
  - The rubric, expected concepts, reviewed-source mapping, follow-ups, and reference
    explanation must remain identical to the approved anchor standard.
- `backend/app/providers/gemini.py`
  - Added validated per-call temperature support without changing existing callers.
- `backend/app/repositories/supabase.py`
  - Scoped historical-question reads by authenticated user RLS, same role, selected
    competency, relevant attempt statuses, excluded current attempt, and bounded
    recency.
- `backend/app/api/v1/journey.py`
  - Wires the anchor pool and progressive generation engine into the real endpoint.
  - Keeps current-attempt and relevant previous-attempt history separate from rejected
    in-memory candidates.
  - Maps only genuine Gemini failures to HTTP 503. Exhaustion after all recovery stages
    is a domain 409, and ordinary candidate rejections stay internal.
- `frontend/src/routes/_authenticated/assessment.$attemptId.interview.tsx`
  - Existing behavior was verified: no automatic identical request retries and no
    recordable stale question under an error state.

### Tests and diagnostics

- `tests/backend/test_question_novelty.py`
- `tests/backend/test_adaptive_question_generation.py`
- `tests/backend/test_hybrid_rag.py`
- `tests/backend/test_dynamic_interview.py`
- `tests/backend/test_gemini.py`
- `tests/backend/test_journey_views.py`
- `scripts/smoke_test_dynamic_question_recovery.py`
- `scripts/smoke_test_live_rag.py` (now project-reference guarded)

No migration, live database write, Auth change, Storage change, checkpoint change, or
public deployment was required for this fix.

## 5. New generation algorithm

The endpoint now uses this bounded flow:

1. Retrieve and validate up to five competency-specific RAG anchors.
2. Deprioritize anchors already used by this user for the same role and competency.
3. Generate with the preferred anchor.
4. Generate a meaningfully diverse candidate using a different reasoning operation.
5. Regenerate with explicit rejected-theme and unused-scenario context.
6. Switch to an alternate retrieved anchor when one exists.
7. Switch scenario/domain.
8. Switch question structure/reasoning type.
9. Generate from competency + approved rubric/concepts/sources while withholding anchor
   wording.
10. Use a controlled dynamic fallback with no fixed question text and a unique nonce.
11. For every candidate, enforce schema, competency/role, approved assessment standard,
   reviewed sources, protected-trait exclusion, deterministic novelty, and independent
   Gemini grounding/fairness validation.
12. Persist only the accepted, delivered question.

There are eight generation calls because steps 3–10 are the eight candidate stages.
No stage contains a static fallback interview question.

## 6. Similarity and anti-repetition logic

The comparison uses the final generated question, not its anchor or the answer.

- Text is case-folded, punctuation removed, and common equivalents canonicalized, such
  as `chart`/`graph`/`plot` → `visualization`, `revenue` → `sales`, and
  `month-wise` → `monthly`.
- Exact normalized match: reject.
- Sequence similarity `>= 0.92`: reject as near-verbatim.
- Sequence similarity `>= 0.82` plus concept Jaccard `>= 0.85` and the same recognized
  scenario (or neither prompt having a scenario): reject as a near paraphrase.
- Concept Jaccard `>= 0.72`, overlapping question structure, and overlapping scenario
  (or neither having one): reject as the same scenario/task.
- In normal stages only, sequence `>= 0.78` plus concept Jaccard `>= 0.55` is a
  conservative borderline-paraphrase rejection.
- Controlled fallback relaxes only that last borderline rule. It never relaxes exact,
  near-verbatim, near-paraphrase, or same-scenario/same-task protection.

The competency and rubric are not similarity inputs by themselves. Generic words such
as “explain”, “approach”, “use”, and “which” are excluded from concept overlap. Thus a
placement dashboard and a monthly-sales chart can test the same competency without
being automatically treated as duplicates.

## 7. Historical-question scope

The final anti-repetition history includes:

- the authenticated user's questions only, enforced by the caller JWT and RLS;
- the same role only;
- the currently selected competency only;
- up to four recent prior attempts and 36 questions;
- prior attempts in `interviewing`, `processing`, `completed`, or `failed` state;
- previously delivered current-attempt questions for the same competency.

It excludes:

- the current attempt from the cross-attempt query, preventing join/self duplication;
- unrelated roles and competencies;
- `role_confirmed` attempts that have not entered an interview;
- rejected generation candidates, which remain only in the current in-memory recovery
  cycle;
- the latest parent prompt from semantic history for a follow-up, while still enforcing
  an exact parent-repeat check. This permits a legitimate answer-adaptive follow-up to
  stay in the parent's scenario.

An unanswered but delivered question may remain historical because the user saw it.
Questions never delivered are not persisted and cannot enter this query.

## 8. RAG anchor analysis

Read-only live counts from verified project `gfsetwljirztyxegiets`:

| Data Analyst competency | Validated anchors |
|---|---:|
| `data_analysis_sql` | 1 |
| `statistics_reasoning` | 1 |
| `data_visualization` | 1 |
| `database_reasoning` | 1 |
| `debugging_problem_solving` | 1 |
| `technical_communication` | 1 |
| **Total** | **6** |

All six pools are small. The engine now supports alternate anchors immediately when
the approved corpus is expanded, while scenario/structure/rubric recovery allows the
current one-anchor corpus to continue safely. No fake approved rows were inserted.

## 9. Original Data Analyst scenario result

Deterministic API regression:

- Role: `junior_data_analyst`
- Competency: `data_visualization`
- History: monthly-sales chart, regional revenue comparison, ecommerce funnel, and
  other common visualization themes
- Candidates 1–3: intentionally rejected
- Candidate 4: logistics dashboard with different task/scenario
- Strategy: `alternate_anchor`
- Result: normal question response, attempt remains active, exactly one accepted
  question persisted, zero rejected candidates persisted, no HTTP 503

Read-only live Gemini regression:

- Verified project: `gfsetwljirztyxegiets`
- Live validated anchor count retrieved: 1
- Historical themes supplied: 4
- Real candidates attempted: 6
- Internally rejected: 5
- Successful strategy: `structure_switch`
- Final validation: `generated_validated_for_practice`
- Writes: 0

This live result is especially important: it proves the interview can recover with the
actual one-anchor database rather than relying on a fabricated larger pool.

## 10. Tests

Final executed results:

| Check | Result |
|---|---:|
| Targeted anti-repetition/RAG/Gemini/journey tests | 75 passed, 0 failed |
| Complete Python suite | 211 passed, 0 failed, 1 dependency deprecation warning |
| Python statement coverage (`backend.app`) | 76.56% (2,825 / 3,690) |
| Python branch coverage (`backend.app`) | 53.37% (491 / 920) |
| Frontend tests | 58 passed, 0 failed |
| Frontend statement coverage | 38.74% (191 / 493) |
| Frontend branch coverage | 35.96% (146 / 406) |
| Frontend function coverage | 29.57% (42 / 142) |
| Frontend line coverage | 40.00% (176 / 440) |
| TypeScript | Passed |
| Ruff | Passed |
| ESLint | 0 errors, 13 Fast Refresh warnings |
| Production frontend build | Passed (client, SSR, Nitro/Cloudflare output) |
| Read-only live hybrid RAG smoke | Passed, 384-dimensional embedding, 1 question anchor, 2 resources |
| Read-only live dynamic recovery smoke | Passed after 5 internal rejections |
| Local backend restart and health | Passed, `status=ok`, version `0.2.0` |

The complete Python run includes existing security, Supabase contract, RLS/migration,
worker, document OCR, evidence, roadmap, ML, and deployment-contract tests. Cross-role
and cross-competency coverage exercises all 36 current role/competency packages. The
current catalog has no Java, DSA, or aptitude role, so those nonexistent flows were not
claimed as tested.

## 11. API behavior

- Candidate duplicate/policy rejection: internal recovery; no response yet.
- Recovery succeeds: normal `200` next-question response.
- Strategy/anchor/scenario/fallback switch: internal; no user-facing error.
- All eight validated content strategies fail: domain HTTP `409` with
  `dynamic_question_generation_exhausted`, not 503. This is bounded and was not reached
  in the saturated live smoke.
- Gemini 429: HTTP `503`, code `gemini_rate_limited`.
- Gemini network/5xx after bounded transport retries: HTTP `503`, code
  `gemini_temporarily_unavailable`.
- Non-retryable Gemini/config failure: HTTP `503`, code
  `dynamic_question_generation_failed`.
- Supabase failure: existing repository translation remains an actual infrastructure
  5xx.
- Invalid RAG package/role/competency contract: HTTP `409`, code
  `hybrid_rag_integrity_failed`.

## 12. Live integration verification

Before each live operation, the configured URL was parsed and asserted to have project
reference `gfsetwljirztyxegiets`. The live work was read-only:

- counted validated Data Analyst anchors;
- generated a real 384-dimensional Gemini embedding;
- retrieved a validated question anchor and two approved learning resources;
- ran real Gemini question generation plus independent validation for the saturated
  Data Analyst visualization scenario.

No Auth users, database rows, migrations, Storage objects, configuration, or secrets
were created, modified, printed, or deleted. Therefore no cleanup was required. The
full authenticated browser attempt was not automated because that would require using
the student's live session and writing an actual delivered question; the local backend
has been restarted for the user to continue that test safely.

## 13. Remaining risks

- Every Data Analyst competency still has one approved anchor. Recovery works, but
  expanding the reviewed corpus would improve semantic variety and reduce Gemini calls.
- Gemini is probabilistic; an extreme history can still exhaust all eight validated
  stages. That condition is now correctly a domain conflict rather than false service
  unavailability.
- Each rejected candidate consumes a Gemini generation call; candidates reaching
  independent validation consume a second call. Rate limits and latency can therefore
  increase under saturated history.
- Scenario/entity extraction is a deterministic English taxonomy, not a second
  semantic embedding comparison. It is explainable and passed the required cases, but
  future domains may require taxonomy additions.
- Frontend coverage remains low overall, although the relevant interview request/error
  contract is tested.
- Public deployment remains blocked by local API/CORS URLs, an undeclared external
  worker flag, and a shared local environment containing the worker secret.

## 14. Deployment readiness

The repeated-question interruption fix is ready for continued local acceptance testing:
all relevant automated tests pass, the exact original deterministic case returns a
question rather than 503, real Gemini recovered after five rejections against the
one-anchor live corpus, and the restarted local backend is healthy.

The whole application is **not ready for public deployment**. Preflight still blocks:

- API: local/non-HTTPS CORS, external worker not declared, and server secret present in
  the shared API environment.
- Frontend: `VITE_API_BASE_URL` is local HTTP.

No public deployment was performed.
