# FairHireAI: Complete Implementation and Research Blueprint

## 1. Final project definition

**FairHireAI is a student-facing placement-readiness platform.** A student optionally uploads a job description (JD), selects or confirms the approved target role, uploads a resume, completes a structured adaptive mock interview, and receives evidence-backed readiness, skill-gap feedback, a learning roadmap, and progress across reattempts. When a JD is supplied, the assessment and interview are adapted to its approved role requirements.

It does **not** decide whether a recruiter should hire someone. It does **not** rank students. It does **not** claim to know a specific company's hiring process. A selected company name is optional motivational context only; assessment is based on the selected role and JD.

### One-sentence research statement

FairHireAI reproduces the fair multimodal MAG-BERT-ARL interview-assessment model and extends it with a Competency Evidence Graph that converts model evidence into role-specific, auditable placement-readiness dimensions and RAG-grounded learning feedback.

### First-release scope

The application supports a **versioned catalog of approved student/early-career roles**. A student searches the catalog and confirms one role per assessment. Junior Backend Developer remains the first research-validation and evaluator-study role; additional catalog roles must use the same six-competency, reviewer-controlled template contract and must never create an uncontrolled rubric at runtime.

## 2. Abstract draft

Placement preparation tools often give generic advice and do not show why a student is considered ready or unready for a role. FairHireAI is a student-facing, explainable placement-readiness platform for structured mock interviews. The system reproduces MAG-BERT-ARL, a fairness-aware multimodal video-interview assessment architecture that fuses textual, acoustic, and visual evidence without using sensitive attributes as training inputs. FairHireAI extends this base model through a Competency Evidence Graph that connects role/JD requirements, resume claims, interview questions, timestamped answer evidence, model predictions, and explanations. The graph produces evidence-backed scores for Technical Readiness, Communication Clarity, and Interview Response Quality, which are aggregated into a role-specific Placement Readiness score. Detected competency gaps are used to retrieve curated learning material and create a personalized roadmap. Evaluation separates base-model reproduction on First Impressions V2 from a consented mock-interview study that measures graph quality, evidence retrieval, agreement with faculty rubric ratings, and feedback usefulness. The system is intended for student self-improvement and not automated hiring decisions.

## 3. Problem, objective, and boundaries

### Problem

Students preparing for placement interviews need feedback that is role-specific, actionable, and traceable to what they actually said. Existing generic feedback does not reliably connect a weak score to a competency, answer, or learning action.

### Objectives

1. Reproduce the MAG-BERT-ARL multimodal assessment pipeline.
2. Convert a target role/JD into a competency rubric.
3. Conduct a competency-constrained adaptive mock interview.
4. Create a graph of evidence connecting questions, answers, model outputs, and competencies.
5. Give separate, explainable readiness dimensions and a final role-readiness score.
6. Generate a grounded skill-gap roadmap and allow reattempt/progress comparison.

### Explicit non-goals

- Recruiter portal, applicant tracking, job posting, or company workflow.
- Hire/reject recommendation or student ranking.
- Claiming that an emotion, personality, or facial expression is objectively detected.
- Claiming an assessment is company-specific merely because the student selected a company.
- Training a technical-skill neural model on labels that do not exist.

## 4. Base paper reproduction: what must be implemented

The source paper is *MAG-BERT-ARL for Fair Automated Video Interview Assessment* (IEEE Access, 2024). The project must make a clear distinction between its base implementation and its extensions.

### 4.1 Base-paper pipeline

```text
Labeled interview video
  -> Whisper-timestamped: transcript, word times, confidence
  -> openSMILE/eGeMAPS: 88 acoustic features aligned to words
  -> OpenFace: visual features aligned to words
  -> BERT embeddings + MAG fusion of acoustic and visual inputs
  -> BERT encoder
  -> CLS representation
  -> ARL learner predicts interview score
  -> ARL adversary assigns high-loss weights during training
  -> Gradient SHAP explains text, acoustic, visual contribution
```

### 4.2 MAG-BERT

MAG-BERT starts with BERT text embeddings. The Multimodal Adaptation Gate (MAG) combines each word's text representation with aligned audio and visual feature vectors before the BERT encoder. The model therefore learns from what was said and associated non-verbal signals.

Inputs per word/token:

- `T`: tokenized transcript / BERT embedding;
- `A`: aligned eGeMAPS acoustic vector (88 dimensions);
- `V`: aligned OpenFace visual vector (use the paper's selected feature subset or documented full vector);
- `y`: dataset interview-score label during training only.

### 4.3 ARL

ARL contains a learner and an adversary.

- The **learner** predicts the target score from the MAG-BERT `CLS` representation.
- The **adversary** assigns larger weights to samples/regions with high loss.
- After a pretraining stage, training alternates so the learner reduces weighted loss while the adversary tries to expose high-loss regions.

Conceptually:

```text
weighted loss = sum(adversary_weight_i * prediction_loss_i)
```

The paper evaluates MSE, BCE, and combined MSE+BCE variants. For First Impressions V2, implement all three if time permits; otherwise document one faithful main variant plus the MAG-BERT baseline.

### 4.4 Base-paper output and fairness wording

The base model is trained on the available **interview-score label**. In the student application, rename its displayed output to **Base Multimodal Interview Signal**. Do not tell a student the model predicts whether they will be hired.

Sensitive attributes must not be used as normal training inputs. If First Impressions V2 provides demographic annotations, they may be used only in an offline research fairness audit. Do not infer a student's gender from video for the application.

### 4.5 Required base-model experiments

| Experiment | Purpose |
|---|---|
| MAG-BERT without ARL | Baseline |
| MAG-BERT-ARL MSE | Paper reproduction variant |
| MAG-BERT-ARL BCE | Paper reproduction variant |
| MAG-BERT-ARL MSE+BCE | Paper reproduction variant |
| Text only | Modality ablation |
| Text + audio | Modality ablation |
| Text + visual | Modality ablation |
| Text + audio + visual | Full model |
| Gradient SHAP on sample answers | Explainability reproduction |

Report Pearson correlation and RMSE for continuous labels. If thresholding into classification is clearly defined, also report accuracy, precision, recall, and F1. Run demographic parity, equalized odds, and equal accuracy only when protected-attribute labels are legitimately available for offline evaluation.

## 5. Final FairHireAI system flow

```text
Student
  -> Optionally upload JD
  -> Detect or select approved target role
  -> Student confirms role
  -> Upload resume
  -> Role/JD competency extraction (JD-specific when supplied)
  -> Resume claim extraction
  -> Competency-constrained adaptive mock interview
  -> Video answers
  -> MAG-BERT-ARL base-paper engine
  -> Competency Evidence Graph
  -> Explainable scorecards + Placement Readiness
  -> Skill-gap detection
  -> RAG-grounded learning roadmap
  -> Reattempt interview
  -> Progress comparison
```

### Role/JD matching

The system should use the confirmed target role and optional JD to create an assessment profile, not to decide whether a resume is accepted. If no JD is supplied, use the approved role template. If a JD is supplied, map it only to an approved role and adapt the interview using its approved skills and competency-weight adjustments.

Example: Junior Backend Developer

| Competency | Suggested role weight |
|---|---:|
| Programming fundamentals | 0.20 |
| API design | 0.20 |
| Database reasoning | 0.20 |
| Debugging/problem solving | 0.15 |
| System-design basics | 0.15 |
| Technical communication | 0.10 |

Use O*NET/ESCO as a taxonomy starting point, then have a faculty or industry reviewer validate the final six competencies and rubrics. A JD can adjust weights or add approved skills, but must not create an uncontrolled new rubric at runtime.

## 6. Final novelties

### Novelty 1: Competency Evidence Graph and explainable audit

Gradient SHAP itself is in the base paper. Your novelty is not simply showing SHAP. It is a graph-driven audit that makes every role-readiness result traceable.

The graph links:

```text
Role/JD -> Competency -> Resume claim -> Question -> Answer segment
        -> Transcript/audio/visual evidence -> MAG-BERT-ARL prediction
        -> SHAP attribution -> competency judgment -> skill gap -> roadmap item
```

Each report claim must link to evidence such as a transcript span, video timestamp, rubric item, model attribution, or resume claim.

#### Novelty 1A: multidimensional auditable readiness scorecard

The graph must produce separate student-facing dimensions, not only one unexplained overall score. This is part of Novelty 1, not a separate black-box model for every dimension. Each score is calculated from named, inspectable evidence and each shown reason must link to a graph record.

| Score shown to student | Valid calculation inputs | Used in Placement Readiness? | Safe UI label |
|---|---|---:|---|
| Technical | Role-rubric concept match, answer correctness/depth, code or solution explanation, resume-project consistency, technical follow-up quality | Yes, high weight | Technical Readiness |
| Communication | Answer structure, relevance, completeness, speech pace, filler rate, transcript confidence | Yes, medium weight | Communication Clarity |
| Behavior | Answer completeness, responsiveness to follow-ups, consistency, preparation, professionalism rubric | Yes, low-medium weight | Interview Response Quality |
| Emotion | Audio prosody and facial-expression signals, if technically usable | No; display only as experimental feedback | Delivery Signal |

The individual dimensions are valid only if they are built from a written rubric and evaluated against human ratings in the student study. Do not claim to have trained four independent neural predictors when no corresponding labels exist.

##### Dimension formulas

```text
TechnicalReadiness =
  0.35 * technical_rubric_match
+ 0.25 * answer_depth_and_correctness
+ 0.20 * technical_follow_up_quality
+ 0.20 * resume_project_consistency

CommunicationClarity =
  0.30 * answer_relevance
+ 0.25 * answer_structure
+ 0.20 * answer_completeness
+ 0.15 * pace_and_filler_quality
+ 0.10 * transcript_confidence

InterviewResponseQuality =
  0.35 * follow_up_responsiveness
+ 0.30 * answer_completeness
+ 0.20 * resume_answer_consistency
+ 0.15 * professionalism_rubric
```

Initial weights are expert-calibrated, not learned facts. Ask the rubric reviewers to validate them, record this in the paper, and tune only on a validation/pilot set.

##### Delivery/Emotion policy

Do not show an "Emotion Score," "Confidence Score," or personality diagnosis. The project does not have reliable ground truth to make those claims, and facial/voice signals can be unfairly affected by accent, disability, camera position, culture, and temporary stress.

If the team implements audio-prosody or visual-expression features, show them as a separate **Delivery Signal** panel with these safeguards:

- never subtract it from Placement Readiness;
- never label emotion as fact;
- allow the student to hide it;
- show signal quality and an optional student self-reflection instead;
- present it as experimental feedback only.

Example:

```text
Delivery Signal (experimental; not used in readiness)
- Audio clarity: good
- Long pauses: low
- Speaking-energy variation: moderate
- Your self-reflection: "I felt nervous in the first two answers."
```

##### Example final report output

```text
Placement Readiness: 71/100 - Developing

Technical Readiness: 74/100
  Strength: Explained REST API validation and authentication clearly.
  Improve: Explain SQL indexing and query execution plans in more depth.
  Evidence: Database follow-up, 03:18-03:54; rubric item DB-04.

Communication Clarity: 69/100
  Strength: Answers were relevant and understandable.
  Improve: Use a clearer Situation-Task-Action-Result structure for project answers.
  Evidence: Project question, 01:10-01:58; completeness 0.62.

Interview Response Quality: 70/100
  Strength: Responded consistently to follow-up questions.
  Improve: State measurable outcomes when describing resume projects.
  Evidence: Resume claim RC-03 linked to answer 02:15-02:48.

Delivery Signal: Experimental; not used in readiness
  Audio clarity: good. Optional self-reflection recorded.

Next three roadmap tasks
  1. Practice SQL EXPLAIN and indexing exercises.
  2. Rewrite one project explanation using STAR.
  3. Reattempt the Database Reasoning interview after one week.
```

### Novelty 2: RAG-grounded skill-gap feedback and roadmap

Do not ask an LLM to invent generic advice. Detect the gap from the graph first, retrieve material from a curated knowledge base, then generate a structured plan.

```text
Weak competency from graph
  -> retrieve approved resources/tasks for that competency
  -> generate a time-bounded roadmap
  -> show the evidence that caused the recommendation
```

Use a local, curated resource database initially. It may include official documentation, selected courses, practice tasks, and mini-projects. Store source URL, title, competency tags, difficulty, estimated time, and quality/reviewer status.

### Supporting feature: adaptive questioning

Adaptive questions are not an unrestricted chatbot. The system selects the next question using fixed competency coverage rules.

```text
If coverage < threshold OR rubric match is weak OR answer is incomplete:
    ask a follow-up within the current competency
Else:
    advance to the next competency
```

An LLM may rephrase an approved follow-up using resume context, but must not change the competency, difficulty, evaluation rubric, or safety constraints.

## 7. Separate student scorecards

Do not create four separate opaque models or four separate "agents." Generate evidence-backed dimensions from the common pipeline and graph.

| Student-visible score | Evidence used | Weight in final score |
|---|---|---:|
| Technical Readiness | Competency-rubric match, depth/correctness, project explanation, follow-up answer | High |
| Communication Clarity | Answer relevance, structure, completeness, speech pace, filler count, transcript quality | Medium |
| Interview Response Quality | Follow-up responsiveness, resume-answer consistency, coverage, professional response structure | Medium |
| Delivery Signal | Audio/video signal indicators and optional student self-reflection | Not used to reduce readiness |

Avoid naming a score "Emotion Score." The system has no reliable emotion ground truth and should not diagnose the student. If desired, show an optional self-reflection prompt after the interview: "How confident did you feel?" This is student-owned information, not an AI emotion judgment.

### Readiness formula

For the Junior Backend Developer research-validation template:

```text
PlacementReadiness =
  0.50 * TechnicalReadiness
+ 0.25 * CommunicationClarity
+ 0.25 * InterviewResponseQuality
```

Each dimension is itself calculated from competency evidence. A transparent competency score can be:

```text
CompetencyScore(c) =
  weighted_mean(base_model_signal(answer),
                relevance * rubric_match * evidence_confidence * signal_quality)
```

Use the graph to apply the role weights. Low-quality audio/video must lower confidence, not automatically lower student capability. Missing evidence should trigger a follow-up or be reported as insufficient evidence.

## 8. Competency Evidence Graph design

### Node types

`Student`, `Attempt`, `TargetRole`, `JobDescription`, `Competency`, `ResumeClaim`, `Question`, `AnswerSegment`, `TranscriptSpan`, `AudioEvidence`, `VisualEvidence`, `ModelPrediction`, `ShapAttribution`, `EvidenceClaim`, `SkillGap`, `RoadmapItem`, `ProgressMetric`.

### Edge types

`requires`, `claims`, `tests`, `answered_by`, `transcribed_as`, `has_audio_evidence`, `has_visual_evidence`, `predicted_by`, `explained_by`, `supports`, `contradicts`, `indicates_gap`, `recommends`, `improves_over`.

### Minimum fields on every node/edge

```text
id, type, source, attempt_id, created_at,
confidence, visibility, normalized_text, raw_reference
```

### Practical storage decision

For 10–12 weeks, use PostgreSQL tables or JSONB for graph records plus a graph traversal service in Python. Do not spend weeks installing a graph database. Neo4j is optional only if the team already knows it.

## 9. Interview and scoring algorithm

### Interview procedure

1. Map an optional JD to an approved role, or use the selected approved role when no JD is supplied; then have the student confirm the role.
2. Load the confirmed role rubric and parse the resume; when a JD is supplied, apply its approved skills and competency-weight adjustments to the interview profile.
3. Select one core question for the highest-priority uncovered competency.
4. Record/upload the student's answer.
5. Run transcript, feature extraction, base-model inference, rubric matching, and graph update.
6. Calculate coverage/confidence.
7. Ask one bounded follow-up if evidence is insufficient; otherwise move on.
8. Stop after all critical competencies have sufficient evidence or maximum question count is reached.

### Suggested initial interview limits

- 6 competencies;
- 1 core question each;
- maximum 1 follow-up each;
- maximum 10–12 questions;
- 60–120 seconds per answer;
- one confirmed catalog role per assessment.

### Follow-up trigger

```text
follow_up = (
  competency_coverage < 0.70
  OR rubric_match < 0.60
  OR answer_completeness < 0.60
  OR evidence_confidence < 0.60
  OR high_confidence_resume_contradiction == true
)
```

These are initial thresholds; calibrate them after a small pilot with faculty review.

## 10. Data plan

### A. Base-model research data

Use First Impressions V2 for base-model reproduction. It provides short speaking-video segments, transcripts, apparent-personality data, an interview-score variable, and some demographic annotations.

Use it to prove only:

- MAG-BERT-ARL model performance on its available interview-score label;
- modality ablations;
- offline fairness analysis where valid;
- Gradient SHAP implementation.

Do not claim it measures programming, databases, or actual placement selection.

### B. FairHireAI novelty data

Collect a small consented mock-interview dataset:

- 30–60 student volunteers;
- Junior Backend Developer rubric;
- 6 core competency questions and limited follow-ups;
- three faculty/industry evaluators;
- evaluator rubric scores per competency and overall readiness.

This data is for graph/readiness evaluation, not for training a large deep model from scratch.

### Consent and privacy minimum

- Participant receives a simple explanation and agrees before recording.
- Store `P001`, `P002`, etc., instead of names in research exports.
- State a deletion date for raw video.
- No actual placement or hiring decision is made.
- Limit access to the team and guide.

## 11. Annotation rubric

Each of the three evaluators independently gives a 1–5 score for each competency and a final readiness rating. Give them written anchors.

Example: Database Reasoning

| Rating | Rubric anchor |
|---:|---|
| 1 | Cannot explain basic database choices or queries |
| 2 | Knows terms but gives incorrect/incomplete reasoning |
| 3 | Explains basic schema/query choice correctly |
| 4 | Explains indexing, trade-offs, and a realistic example |
| 5 | Explains query plans, bottlenecks, trade-offs, and alternatives accurately |

Record agreement between evaluators (for example, weighted kappa or intraclass correlation) before treating their average as the reference score.

## 12. Evaluation and paper experiments

### Base-paper experiments

- Pearson correlation and RMSE on the FI interview-score task.
- Optional classification metrics only with a documented threshold.
- Text / text+audio / text+visual / text+audio+visual ablation.
- MAG-BERT versus MAG-BERT-ARL variants.
- Fairness audit only on permitted labels.
- Gradient SHAP examples.

### FairHireAI extension experiments

| Question | Metric |
|---|---|
| Is the graph constructed correctly? | Node/edge precision, recall, F1 on manually checked samples |
| Does evidence support a claimed gap? | Top-k evidence precision judged by evaluators |
| Does graph readiness match human judgment? | Correlation/MAE against aggregated evaluator readiness ratings |
| Does the graph add value beyond raw base score? | Ablation comparison |
| Is the roadmap useful? | Evaluator/student relevance, specificity, actionability rating |
| Are reports understandable? | Small usability questionnaire |

### Essential ablation

```text
A. MAG-BERT baseline
B. MAG-BERT-ARL base model
C. MAG-BERT-ARL + SHAP presentation only
D. MAG-BERT-ARL + Competency Evidence Graph + readiness aggregation
```

For the extension study, compare C and D against evaluator readiness scores. D must improve agreement, traceability, or evidence relevance to justify your novelty.

## 13. System architecture

```text
Frontend (React/Next.js)
  - student onboarding, interview, reports, roadmap, progress

Backend (FastAPI or Node/NestJS)
  - auth, attempts, uploads, resume/JD parsing, orchestration, report APIs

ML service (Python/FastAPI)
  - preprocessing, MAG-BERT-ARL inference/training, SHAP, graph scoring

Storage
  - PostgreSQL: users, attempts, graph records, roadmaps
  - object storage/local protected volume: raw videos, audio, features

Deployment
  - Docker Compose; Nginx only after local development works
```

### Recommended stack

- Python, PyTorch, Hugging Face Transformers, Captum;
- whisper-timestamped, openSMILE/eGeMAPS, OpenFace;
- FastAPI for ML APIs;
- PostgreSQL + SQLAlchemy;
- React/Next.js and a component library;
- Docker Compose.

### Core API endpoints

```text
POST /attempts                         create assessment attempt
POST /attempts/{id}/resume             upload/parse resume
POST /attempts/{id}/job-description    submit optional JD
GET  /attempts/{id}/next-question      select next approved question
POST /attempts/{id}/answers             upload answer/video metadata
POST /attempts/{id}/process             run ML pipeline asynchronously
GET  /attempts/{id}/report              scores/evidence/roadmap
POST /attempts/{id}/reattempt           create next attempt
GET  /progress                          compare completed attempts
```

## 14. Repository layout

```text
fairhireai/
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

Never commit raw videos, private resumes, secrets, API keys, or huge datasets to Git.

## 15. Team-of-four work split

| Member | Primary work | Must deliver |
|---|---|---|
| A | ML/base paper | preprocessing, MAG-BERT-ARL training, metrics, checkpoints |
| B | Multimodal pipeline | Whisper/openSMILE/OpenFace alignment, signal-quality checks |
| C | Research novelty | rubric, graph, readiness equations, evaluator study, ablations |
| D | Application | backend/frontend, upload flow, report, roadmap, Docker |

All members: paper writing, experiment review, code review, documentation, and final presentation.

## 16. Twelve-week execution plan

| Week | Outcome |
|---:|---|
| 1 | Freeze scope; role rubric; dataset access; GPU/Docker feasibility; consent/rubric drafts |
| 2 | Run 10 videos end-to-end through transcript, audio, visual extraction and alignment |
| 3 | MAG-BERT baseline on a small data subset |
| 4 | ARL integration; base metrics; modality ablation pilot |
| 5 | Stabilize base pipeline; SHAP output; experiment logging |
| 6 | Evidence Graph v1 and transparent scoring formula |
| 7 | Resume/JD mapping, question bank, adaptive-follow-up logic |
| 8 | Backend/frontend video upload and student report |
| 9 | RAG resource database, skill gaps, roadmap, reattempt data model |
| 10 | Consent-based pilot interviews and evaluator annotations |
| 11 | Extension ablations, usability study, Docker/demo, paper figures |
| 12 | Final paper, reproducibility package, presentation, contingency fixes |

Write the paper from week 3. Do not wait until the final week.

## 17. First-week checklist

- [ ] Confirm First Impressions V2 access and storage footprint.
- [ ] Verify one NVIDIA GPU or a usable cloud/college machine.
- [ ] Install and test Python, PyTorch/CUDA, ffmpeg, Docker, Whisper, openSMILE, and OpenFace.
- [ ] Process exactly 10 video samples; save a manifest of failures.
- [ ] Finalize Junior Backend Developer competency list and question rubric.
- [ ] Ask one faculty/industry reviewer to validate the rubric.
- [ ] Prepare participant consent and evaluator scoring form.
- [ ] Create the repository, issue board, experiment log, and weekly demo schedule.

## 18. Risks and prevention

| Risk | Prevention / fallback |
|---|---|
| FI download or preprocessing is too large | Work with a documented subset first; retain manifests and features, not duplicated raw files |
| OpenFace installation fails | Time-box it in week 1; use text+audio MVP and report visual module as a documented limitation only if needed |
| GPU is unavailable | Use a small subset/pre-extracted features; do not attempt full training on CPU |
| No technical labels in public data | Use public data only for base model; use human rubric study for role readiness |
| LLM generates unsafe/off-topic questions | Question bank + competency/rubric constraint + maximum one follow-up |
| RAG gives invented advice | Retrieve only from a curated local resource collection; show source links |
| Scores appear arbitrary | Save formulas, thresholds, evidence confidence, and every report claim's source |
| Team spends too long on UI | Freeze UI until the base pipeline and graph work end-to-end |
| Paper has no evidence of novelty | Prioritize evaluator study and ablation D vs C |

## 19. Paper outline

1. Introduction: student placement-readiness problem and need for auditable feedback.
2. Related Work: automated video interviews, MAG-BERT, ARL fairness, explainability, skill-gap systems.
3. Base Model: faithful MAG-BERT-ARL reproduction.
4. Proposed FairHireAI: role/JD competency model, graph, aggregation, adaptive interview, RAG roadmap.
5. Experimental Setup: datasets, preprocessing, participants, annotation protocol, metrics.
6. Results: base reproduction, fairness audit, ablations, graph/readiness evaluation, usability.
7. Discussion: limits of public data, no real hiring use, bias/quality limitations.
8. Conclusion: evidence-backed student self-improvement and future work.

## 20. Final presentation statement

FairHireAI is a placement-readiness platform for students. It uses a reproduced MAG-BERT-ARL multimodal interview engine and extends it with a Competency Evidence Graph to deliver role-specific, auditable readiness, explainable skill gaps, grounded learning roadmaps, and measurable progress across mock-interview attempts.

## 21. Complete tool checklist

Install the **required-now** tools first. Do not install every optional tool in week 1.

### A. Hardware and accounts

| Item | Requirement | Purpose |
|---|---|---|
| Development machine | Windows with WSL2/Ubuntu recommended, or native Ubuntu | Stable Python, CUDA, OpenFace, Docker workflow |
| NVIDIA GPU | Preferred: 12 GB+ VRAM; 16 GB+ is more comfortable | Training/inference for BERT and video processing |
| Disk | 470 GB can work; keep 80-100 GB free | Data, extracted features, Docker images, checkpoints |
| RAM | 16 GB minimum; 32 GB preferred | Feature extraction and Docker services |
| GitHub account | One organization/repository | Version control and code review |
| Hugging Face account | Free | Model downloads if required |
| Kaggle account | Optional | Only for safe synthetic resume/JD demo data |

### B. Required-now development tools

| Tool | What it does | Owner | Source |
|---|---|---|---|
| Git + GitHub | Code/version control | Everyone | https://git-scm.com/ and https://github.com/ |
| VS Code | Editor/debugging | Everyone | https://code.visualstudio.com/ |
| Python 3.10 or 3.11 | ML/backend runtime | A, B, C | https://www.python.org/ |
| Conda or `venv` | Isolated Python environments | A, B, C | https://docs.conda.io/ or Python `venv` |
| PyTorch + CUDA | Deep learning training/inference | A | https://pytorch.org/ |
| NVIDIA driver + CUDA-compatible PyTorch build | GPU access | A | https://pytorch.org/get-started/locally/ |
| ffmpeg | Audio/video conversion | B | https://ffmpeg.org/ |
| Docker Desktop + WSL2 | Reproducible local services | D | https://www.docker.com/products/docker-desktop/ |
| PostgreSQL | Users, attempts, graph records, reports | D | https://www.postgresql.org/ |
| Postman or Insomnia | Test backend APIs | D | https://www.postman.com/ or https://insomnia.rest/ |

### C. Required ML/research libraries

| Tool/library | Exact role in FairHireAI | Required? | Source / citation |
|---|---|---:|---|
| Hugging Face `transformers` | BERT tokenizer/model and training utilities | Yes | https://github.com/huggingface/transformers |
| PyTorch | MAG-BERT-ARL implementation | Yes | https://pytorch.org/ |
| MAG reference implementation | Starting point for MAG integration into BERT | Yes | https://github.com/WasifurRahman/BERT_multimodal_transformer |
| ARL reference paper/implementation | Learner/adversary weighting design | Yes | https://proceedings.neurips.cc/paper/2020/hash/07fc15c9d169ee48573edd749d25945d-Abstract.html |
| `whisper-timestamped` | Transcript, word timestamps, word/segment confidence | Yes | https://github.com/linto-ai/whisper-timestamped |
| openSMILE / `opensmile` Python | eGeMAPS acoustic features | Yes | https://github.com/audeering/opensmile-python |
| OpenFace 2.0 | Face landmarks, gaze, pose, action units | Yes, but time-box installation | https://github.com/TadasBaltrusaitis/OpenFace |
| Captum | Gradient SHAP implementation for PyTorch | Yes | https://captum.ai/ |
| pandas, NumPy, scikit-learn | Data manifests, metrics, preprocessing | Yes | https://pandas.pydata.org/, https://numpy.org/, https://scikit-learn.org/ |
| MLflow or Weights & Biases | Experiment logs, parameters, metrics, model versions | Recommended | https://mlflow.org/ or https://wandb.ai/ |
| DVC | Large-data/version manifest management | Optional | https://dvc.org/ |

### D. Required application tools

| Tool/library | Exact role | Required? |
|---|---|---:|
| FastAPI | Python ML service and/or backend APIs | Yes |
| Uvicorn | Runs FastAPI locally | Yes |
| SQLAlchemy + Alembic | Database mapping and migrations | Yes |
| React + Vite or Next.js | Student web UI | Yes |
| Tailwind CSS or Material UI | Fast consistent UI | Recommended |
| Browser MediaRecorder API | Record student video in browser | Later; start with upload first |
| MinIO/S3-compatible storage | Video/object storage | Optional locally; useful for deployment |
| Nginx | Reverse proxy in final Docker deployment | Final week only |

### E. Required graph/RAG tools

| Tool/library | Exact role | Required? |
|---|---|---:|
| PostgreSQL JSONB or ordinary relational tables | Store graph nodes/edges in the first release | Yes |
| NetworkX | Internal graph construction, validation, traversal | Recommended |
| pgvector | Store embeddings for resource retrieval | Recommended |
| sentence-transformers | Embed skills, rubric text, resources, and resume/JD chunks | Recommended |
| Chroma/FAISS | Alternative local vector search | Optional; choose only one, not both |
| LLM API or local LLM | Rephrase approved questions and turn retrieved resources into feedback | Optional; use only after core system works |

**RAG rule:** use a small curated resource table first. Do not depend on live web search during a student assessment. Store approved resource title, URL, source, competency tag, difficulty, estimated duration, and short description.

### F. Tool installation order for week 1

```text
1. Git, VS Code, Python environment, NVIDIA/PyTorch check
2. ffmpeg + whisper-timestamped
3. openSMILE Python
4. OpenFace feasibility test (time-box: two days)
5. Docker Desktop/WSL2, PostgreSQL
6. FastAPI and React skeleton
7. Captum, experiment tracker, graph/RAG utilities
```

If OpenFace does not process a test video reliably by the end of week 1, continue with text+audio while keeping the visual branch isolated. Do not let one dependency stop the entire project.

## 22. Sources and datasets to collect

### A. Research and implementation sources

| Source | Use it for | How it should appear in your work |
|---|---|---|
| MAG-BERT-ARL base paper (provided PDF) | Model architecture, ARL integration, metrics, experiment design | Primary base-paper citation |
| MAG paper: *Integrating Multimodal Information in Large Pretrained Transformers* | MAG mechanism and implementation | Method citation |
| ARL paper: *Fairness Without Demographics Through Adversarially Reweighted Learning* | ARL objective and fairness framing | Method citation |
| First Impressions V2 official page | Dataset, labels, splits, transcripts, demographics for offline audit | Dataset citation |
| Whisper paper/repository | ASR model | Tool/method citation |
| whisper-timestamped repository | Word alignment/timestamps/confidence | Tool citation |
| openSMILE/eGeMAPS paper/repository | Acoustic features | Tool/method citation |
| OpenFace 2.0 paper/repository | Facial behavior features | Tool/method citation |
| Captum paper/docs | Gradient SHAP | Explainability citation |
| O*NET and/or ESCO | Seed occupation-to-skill taxonomy | Data-source citation and attribution |

### B. Data sources

| Data | What it contains | Use in the project | Do not use it for |
|---|---|---|---|
| First Impressions V2 | 10,000 short English speaking videos; transcript; five apparent-trait labels; [0,1] interview variable; gender/ethnicity annotations | Base MAG-BERT-ARL reproduction and offline fairness audit | Claiming technical competence or actual hiring success |
| Consented mock-interview study | Your role questions, student answers, resumes if permitted, faculty rubric labels | Competency graph, scorecard validity, role readiness, feedback evaluation | Training a large deep model from scratch |
| O*NET database | Occupations, skills, tasks, knowledge | Initial role/competency definitions | Automatic ground truth for interview skill |
| ESCO dataset/API | Occupation and skill relationships | Alternative/additional competency mapping | Company-specific hiring criteria |
| Curated learning-resource table | Approved docs, practice tasks, courses, mini-projects | RAG retrieval and roadmap generation | Unverified live internet recommendations |
| Synthetic resume/JD data | Non-identifying sample resumes and JDs | Demo/test of parsing and matching | Evidence of real selection accuracy |

### C. Authoritative links

- [First Impressions V2 dataset](https://chalearnlap.cvc.uab.cat/dataset/24/description/) — the official page describes professional transcripts, a [0,1] interview variable, and available gender/ethnicity annotations.  
- [O*NET license and data](https://www.onetcenter.org/license_agreements.html) — most O*NET information is CC BY 4.0; follow attribution and data-license conditions.  
- [ESCO API and downloadable classification](https://esco.ec.europa.eu/en/use-esco/use-esco-services-api) — intended for job matching, skills intelligence, and career guidance.  
- [Whisper](https://github.com/openai/whisper) — code and model weights use the MIT License.  
- [whisper-timestamped](https://github.com/linto-ai/whisper-timestamped) — provides word timestamps/confidence; it requires Python and ffmpeg and should be cited along with Whisper.  
- [openSMILE Python](https://github.com/audeering/opensmile-python), [OpenFace](https://github.com/TadasBaltrusaitis/OpenFace), and [Captum](https://captum.ai/) — feature extraction and explanation tools.

### D. Source-record template

Create `docs/sources.csv` on day one with:

```text
source_id, title, url, license, accessed_date, used_for, citation_key, notes
```

This prevents lost citations and accidental use of material with unclear rights.

## 23. Weekly assignment plan for four members

Use these temporary role names and replace them with your actual names.

- **Member A: ML lead** - MAG-BERT-ARL, experiments, metrics.
- **Member B: multimodal lead** - video/audio/text preprocessing and alignment.
- **Member C: research/graph lead** - rubric, graph, scorecard, annotation study, RAG data.
- **Member D: platform lead** - backend, frontend, storage, deployment.

Every Friday: 20-minute demo, commit/push, update issue board, record blockers, and save a one-page experiment/result note.

| Week | Member A - ML | Member B - Multimodal | Member C - Graph/research | Member D - Platform | Team checkpoint |
|---:|---|---|---|---|---|
| 1 | Set up PyTorch/CUDA; clone/read MAG and ARL code; run GPU test | Install ffmpeg, Whisper, openSMILE, OpenFace; process one video | Finalize 6 Backend competencies, rubrics, questions, consent/evaluator forms | Create monorepo, Git workflow, Docker/PostgreSQL skeleton | Go/no-go: one video must produce transcript + feature files; role rubric approved |
| 2 | Define FI data loader, target label, baseline config | Process 10 FI videos; validate word-time alignment; log failures | Define graph schema, score fields, initial thresholds; collect O*NET/ESCO mapping | Create upload endpoint and attempt database tables | Demonstrate 10-video preprocessing manifest |
| 3 | Train small MAG-BERT text-only baseline; save reproducible config | Build audio and visual feature caching scripts | Draft graph construction algorithm and faculty annotation guide | Build student onboarding: role/JD/resume form | Text-only baseline metric and working UI form |
| 4 | Integrate audio into MAG-BERT; run T vs T+A pilot | Complete eGeMAPS alignment; time-box/fix OpenFace | Implement technical-rubric and communication feature scoring on sample answers | Resume/JD parser and question-bank APIs | T+A result; API returns a selected question |
| 5 | Integrate visual features; run full T+A+V pilot | Stabilize preprocessing containers; document dimensions/versions | Implement graph node/edge creation and evidence links | Video upload, job queue, protected file storage | One video flows into a graph record |
| 6 | Implement ARL learner/adversary; run pretrain + ARL experiment | Quality flags: no speech, poor transcript, no face, short answer | Implement competency aggregation and three scorecards | Report API and first dashboard cards | Base MAG-BERT vs MAG-BERT-ARL comparison |
| 7 | Implement Gradient SHAP; save explanation artifacts | Build timestamp-to-video evidence helper | Implement adaptive follow-up trigger and graph update rules | Interview page: core question, answer upload, next-question flow | Full internal demo: question -> answer -> score -> evidence |
| 8 | Run paper variants/ablations on planned FI subset | Optimize/caching; document processing time per minute of video | Build skill-gap rules and curated resource table; implement retrieval | Student report: evidence panels, roadmap screen | Complete student journey without reattempt |
| 9 | Freeze model version for pilot; prepare inference API | Test 20 different recording conditions; verify fallback messages | Recruit consented participants; train evaluators; create annotation sheets | Add reattempt and progress tables/charts | Pilot protocol approved; 5 internal test attempts |
| 10 | Run inference for collected attempts; export predictions | Monitor failed processing and repair/retry pipeline | Collect evaluator scores; annotate graph/evidence subset; roadmap ratings | Usability test, bug fixes, progress UI | At least 10 pilot attempts and evaluator feedback |
| 11 | Run final base-model and extension ablations; create tables/figures | Reproduce preprocessing on clean machine/container | Calculate graph/evidence/readiness metrics; write methods/results | Docker Compose, README, demo video, final UI polish | Reproducible end-to-end demo and paper result tables |
| 12 | Verify every result can be regenerated; package configs/checkpoints | Final data manifest, deletion/retention action, pipeline docs | Complete paper novelty/evaluation/discussion sections | Deploy final demo locally; prepare presentation/screenshots | Final rehearsal, paper, report, code handover |

## 24. Definition of done per subsystem

### Base-model done

- A fixed First Impressions V2 subset runs without manual editing.
- Text/audio/visual arrays have aligned sequence lengths and documented shapes.
- MAG-BERT baseline and MAG-BERT-ARL use saved configurations and seeds.
- Metrics and fairness audit scripts run from one command.
- At least one Gradient SHAP explanation can be rendered and traced to input tokens/features.

### Graph/scorecard done

- Every score has a formula and evidence links.
- A reviewer can click a report claim and see its question, answer timestamp, rubric item, and confidence.
- Poor signal quality becomes "insufficient evidence," not an unexplained low score.
- Delivery Signal is separate and non-decisive.

### RAG/roadmap done

- Every recommendation comes from a stored curated source.
- Each roadmap task links to a detected competency gap.
- The user sees why a task was recommended and how long it should take.

### Platform done

- Student can create an attempt, provide role/JD/resume, answer/upload video, process it, view report, and start a reattempt.
- Raw videos are not public and are not committed to Git.
- Docker Compose starts the frontend, backend, ML service, and database with documented commands.
