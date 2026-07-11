# FairHireAI

FairHireAI is a student-facing placement-readiness platform for structured mock interviews. It helps a student upload a resume, choose a target role, optionally add a job description, complete an adaptive interview, and receive evidence-backed readiness feedback, skill gaps, a learning roadmap, and progress across reattempts.

This project is not a recruiter portal, applicant tracking system, student ranking system, or hire/reject automation tool. It is for student self-improvement.

## Final Project Decision

The finalized first release is:

```text
Resume upload
  -> extract Skills, Projects, Achievements, Internships, Certifications
  -> convert those items into resume evidence
  -> select target role: Junior Backend Developer
  -> optional JD adjusts approved role weights
  -> structured adaptive mock interview
  -> questions remember earlier answers and resume evidence
  -> video/text/audio processing through the base MAG-BERT-ARL pipeline
  -> Competency Evidence Graph
  -> Technical Readiness, Communication Clarity, Interview Response Quality
  -> RAG-grounded roadmap
  -> reattempt and progress comparison
```

The earlier resume flow that only considered skills and projects is superseded. Achievements, internships, and certifications are part of the evidence layer.

See [docs/final_project_decision.md](docs/final_project_decision.md) for the locked product and research direction.

## First-Release Scope

- One role only: Junior Backend Developer.
- Six competencies: programming fundamentals, API design, database reasoning, debugging/problem solving, system-design basics, and technical communication.
- One core question per competency, with at most one bounded follow-up.
- MAG-BERT-ARL is reproduced as the base research model.
- The project novelty is the Competency Evidence Graph plus auditable scorecards and grounded roadmap.

## Safety Boundaries

- Do not claim to predict hiring success.
- Do not rank students.
- Do not use sensitive attributes as normal model inputs.
- Do not infer gender, personality, or emotion from video.
- If delivery signals are shown, they stay experimental and are not used to reduce readiness.
- Every recommendation must come from a detected graph gap and a curated source.

## Intended Repository Layout

```text
frontend/
backend/
ml_service/
  training/
  inference/
  preprocessing/
  graph/
  explainability/
datasets/
  metadata_only/
configs/
docs/
tests/
deployment/
scripts/
```

Raw videos, private resumes, secrets, API keys, and large datasets must never be committed.
