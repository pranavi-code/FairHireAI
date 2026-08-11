# Product Foundation Status

## Locked flow

The current product flow supersedes older wording in the original blueprint:

```text
Optional JD
  -> if supplied: deterministic approved-role mapping and adjustment
  -> if omitted: search and select an approved catalog role
  -> confirm exactly one role for the assessment
  -> resume upload and traceable evidence extraction
  -> competency-constrained adaptive interview
  -> real answer processing and Evidence Graph updates
  -> auditable scorecards and roadmap
```

The student may select any active role in the versioned catalog without uploading a JD. If a JD is supplied, it must map to the selected approved role before confirmation. Unsupported and senior JD role families are not assessed, and the application never creates a new rubric at runtime.

## Implemented foundation

### Optional-JD role mapping

- Versioned six-competency templates for the approved role catalog; `Junior Backend Developer` remains the first research-validation role.
- Six competencies whose base weights total 1.0.
- Omitting the JD uses the approved role template and its base weights unchanged.
- Approved title, seniority, and skill terms.
- Explicit rejection of unsupported and senior roles.
- JD adjustments use only approved competency terms and are normalized.
- Mapping response includes matched evidence, confidence, template version, and review status.
- The role template is marked `pending_faculty_review`; the software does not claim that external review has already occurred.

### Resume evidence

- PDF, DOCX, UTF-8 TXT, and MD uploads now use real deterministic extractors.
- File type/content mismatches, files over 5 MiB, encrypted/corrupt files, and
  documents with no extractable text are rejected.
- Original bytes are SHA-256 hashed and extracted page/character spans are preserved.
- The conservative resume parser emits only claims beneath approved section headings;
  it returns no claim when the source does not support one.
- Claims are limited to skill, project, internship, certification, and achievement.
- Every claim requires an exact source text span, character offsets, optional page, extractor version, and confidence.
- Duplicate claim IDs and untraceable claims are rejected.
- Low-confidence claims are identified rather than silently treated as facts.
- Scanned image-only PDFs remain explicitly unsupported until an OCR service is selected.

### Adaptive interview

- Exactly six approved core questions.
- At most one approved follow-up per competency.
- Follow-up rules use coverage, rubric match, answer completeness, evidence confidence, and high-confidence resume contradiction.
- The next core question is the highest-weight uncovered competency.
- No unrestricted LLM question generation is used.

### Competency Evidence Graph

- All node and edge types from the project blueprint are represented.
- Every record requires source, attempt, timestamp, confidence, visibility, normalized text, and raw reference fields.
- Endpoint existence, attempt ownership, unique IDs, timestamps, and strict structural edge types are validated.
- Score inputs must reference existing graph nodes.

### Auditable scorecards

- `Technical Readiness`, `Communication Clarity`, and `Interview Response Quality` use the documented weighted formulas.
- Non-applicable evidence such as an unnecessary follow-up is excluded and remaining weights are transparently renormalized.
- Placement Readiness is `0.50 / 0.25 / 0.25`.
- Missing competency coverage or combined confidence below 0.60 suppresses Placement Readiness instead of inventing certainty.
- Poor signal quality lowers evidence confidence, not student capability scores.
- Delivery Signal is not used in Placement Readiness.
- Every response includes the student-self-improvement/non-hiring safety boundary.

### Durable processing and inference contracts

- Jobs have explicit queued/running/succeeded/failed/cancelled transitions.
- Invalid transitions, missing answer references, unbounded retries, and failed jobs without error codes are rejected.
- Idempotency keys are preserved across retries.
- Base-model results require the model run, checkpoint SHA-256, aligned-input SHA-256, signal quality, timestamp, and graph prediction-node ID.
- The student-visible model field is `Base Multimodal Interview Signal`; no technical-readiness or hiring claim is attached to it.

### Review-gated roadmap

- Skill gaps require graph evidence and a target above the current score.
- Resources require competency tags, canonical URL, difficulty, estimated time, and reviewer status.
- Only reviewer-approved resources are eligible.
- Pending/retired/unmatched resources are excluded.
- Missing resource coverage is returned as unresolved rather than filled with an invented recommendation.

### Persistence and privacy

- Supabase/PostgreSQL migrations define attempts, JDs, resumes/claims, question snapshots, private answer references, jobs, graph records, scorecards, resources, roadmap items, progress metrics, consent history, and deletion requests.
- Row-level security is enabled for every user- or attempt-linked table.
- Authenticated attempt APIs verify the current user with Supabase Auth, forward
  the user access token to PostgREST, and therefore retain RLS scope.
- Attempt creation is atomic with an optional JD record, and lifecycle
  transitions are serialized and validated inside PostgreSQL.
- Private document and interview-video buckets enforce user-ID folder ownership,
  MIME limits, and size limits. Derived artifacts have no direct student policy.
- Interview files are represented by private storage keys, never public video URLs.
- Students can read their own job state, while durable workers control processing transitions.
- Consent is append-only for students; deletion status can only be changed by a trusted worker.

## Implemented API endpoints

```text
GET  /api/v1/health
GET  /api/v1/roles/junior-backend-developer
POST /api/v1/roles/detect
POST /api/v1/documents/job-description
POST /api/v1/documents/resume
POST /api/v1/attempts
GET  /api/v1/attempts/{attempt_id}
POST /api/v1/attempts/{attempt_id}/transitions
POST /api/v1/resume-evidence/validate
POST /api/v1/interviews/next-question
POST /api/v1/evidence/validate
POST /api/v1/evidence/scorecard
POST /api/v1/roadmap/plan
POST /api/v1/privacy/consents
POST /api/v1/privacy/deletion-requests
```

FastAPI also exposes the generated OpenAPI schema and interactive documentation.
Document, attempt, consent, and deletion-request endpoints fail closed without
a valid Supabase user access token. `.env.example` documents the non-secret
configuration names; no live project credential is committed.

## Deliberately not faked

The trained inference worker, constrained Gemini evaluator, evidence graph,
scorecard, approved-resource roadmap, progress comparison, and trusted deletion
worker are implemented. Migrations 0012 through 0014 and the reviewed retrieval
corpus are live; processing runs only after the server-only Supabase key is
configured. That key is now configured locally and the worker is running. A
guarded disposable-user test has completed the real resume/interview/worker/
report/progress/deletion journey. The frontend never simulates these results.

The remaining boundaries are genuinely external:

- malware scanning and OCR for image-only documents;
- one real consenting student's recorded attempt and human evaluation;
- a public HTTPS host for FastAPI and a GPU-capable worker host;
- faculty calibration, consented student/evaluator labels, and the usability
  study.

The software must report an unavailable/insufficient-evidence state while any
required service or evidence is missing. Human research results must never be
fabricated.
