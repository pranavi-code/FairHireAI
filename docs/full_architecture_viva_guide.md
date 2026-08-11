# FairHireAI / RoleReady AI: Beginner-Friendly Full Architecture and Viva Guide

## 0. Read this first: what is real, what is planned, and what must not be claimed

FairHireAI is a student-facing mock-interview and placement-readiness system.
It is intended to help a student practise for an IT or software role, understand
the evidence behind the feedback, study the identified gaps, and reattempt the
interview.

The project must not be described as a hiring system. It does not:

- rank students;
- predict whether a company will hire a student;
- make hire or reject decisions;
- diagnose personality or emotion;
- claim that a public video dataset contains technical-skill labels.

There are three different maturity levels in the project:

1. **Implemented and pilot-tested:** First Impressions V2 verification,
   ten-video preprocessing, Whisper, openSMILE, OpenFace, word alignment,
   MAG-BERT/ARL training code, experiment configurations, and GPU smoke tests.
2. **Designed but still to be implemented end to end:** JD/resume processing,
   local LLM integration, question retrieval, Evidence Graph, readiness
   scoring, roadmap RAG, backend/frontend integration, and reattempt flow.
3. **Still requiring research validation:** final trained checkpoint, final
   metrics, fairness audit, faculty-approved rubrics, LLM-to-human agreement,
   technical-readiness calibration, roadmap usefulness, and consented student
   evaluation.

Always distinguish these levels in a viva. Do not say that a designed component
is already working unless it has actually been implemented and tested.

## 1. The whole project in simple language

Imagine a student uploads a resume and a job description for a backend
developer position.

FairHireAI should:

1. Read the JD and identify what the job expects.
2. Read the resume and identify what the student claims to know.
3. Convert the JD into a small set of interview competencies.
4. Retrieve suitable questions from a reviewed question bank.
5. Personalize those questions using the resume and previous answers.
6. Record the student's video answer.
7. convert the video into text, audio features, and visual features.
8. Evaluate technical content using a fixed rubric and a constrained LLM.
9. Store every requirement, question, answer, score, and explanation in an
   Evidence Graph.
10. Create a skill gap only when sufficient supporting evidence exists.
11. Retrieve approved learning resources for that exact gap.
12. Use the LLM to arrange those resources into a readable roadmap.
13. Let the student reattempt and compare evidence-backed progress.

The simplest mental model is:

```text
JD tells us WHAT to assess.
Resume tells us WHAT to verify.
Question bank provides TRUSTED questions.
RAG finds the most relevant approved question or resource.
LLM adapts and explains within strict rules.
Multimodal ML analyses the recorded answer.
Backend code calculates transparent scores.
Evidence Graph records WHY every result exists.
```

## 2. A simple analogy for the confusing technical terms

Think of the project as a college assessment process.

- **Question bank:** a cupboard containing reviewed question papers.
- **RAG retriever:** a librarian who finds the correct question or textbook
  section for a specific need.
- **LLM:** a teaching assistant who can rewrite a question naturally, evaluate
  an answer using the supplied rubric, or arrange supplied resources into a
  schedule.
- **Rubric:** the answer key and marking scheme.
- **Embedding model:** a tool that converts meanings into numbers so similar
  meanings can be found.
- **Vector database:** a searchable store of those numerical meanings.
- **Evidence Graph:** an audit notebook connecting the requirement, question,
  answer, mark, reason, gap, resource, and later improvement.
- **MAG-BERT-ARL:** the research model that processes the text, audio, and
  observable visual signals from the interview video.

The librarian does not write the textbook. The teaching assistant does not
invent the marking scheme. Similarly, RAG retrieves approved data, and the LLM
works only with the retrieved data and approved rubric.

## 3. Final scope: IT roles or every occupation?

### What O*NET and ESCO can cover

O*NET and ESCO contain occupation and skill terminology for many fields,
including software, healthcare, finance, manufacturing, sales, administration,
engineering, and other occupations.

### What our first product can validly assess

Our first reliable scope should be:

**IT and software roles.**

Examples include:

- Backend Developer;
- Frontend Developer;
- Full-Stack Developer;
- Data Analyst;
- Machine Learning Engineer;
- QA Automation Engineer;
- DevOps or Cloud Engineer;
- Cybersecurity Analyst.

Junior Backend Developer is the main role for research validation because its
competencies, questions, rubrics, and evaluator study can be controlled.

### Why we should not claim every occupation

Although O*NET and ESCO can identify skills for a nurse, accountant, mechanical
engineer, teacher, or salesperson, FairHireAI does not yet contain validated
domain rubrics and trusted question sources for all those occupations.

The software may technically create a JD-derived practice interview for an
unknown role, but it must be labelled:

```text
JD-derived practice profile - not faculty validated
```

Therefore, the honest answer is:

> The architecture can be extended to other occupations, but the first
> validated release focuses on IT/software roles. Junior Backend Developer is
> the primary research-validation role.

## 4. What exactly is "role and skill data"?

Role and skill data is not interview video and not an interview-question
dataset.

It is structured information such as:

```text
Occupation: Software Developer
Task: Design and develop software solutions
Skill: Programming
Knowledge: Computer systems
Technology: Java
Related skill: Database management
```

It helps the system understand that different phrases may refer to the same
general competency.

Example:

```text
"REST development"
"web-service development"
"backend API implementation"
        |
        v
Normalized competency: API Design and Development
```

### O*NET

O*NET provides occupation titles, tasks, work activities, skills, knowledge,
abilities, technology skills, and relationships between them. It helps answer:

- What activities are normally associated with this occupation?
- What general skills and knowledge areas are relevant?
- Which software technologies are associated with the occupation?

It does not tell us whether a student deserves 4 out of 5 for an answer.

### ESCO

ESCO provides occupation-to-skill relationships and multilingual preferred and
alternative skill labels. It helps answer:

- Which skills are associated with an occupation?
- Are two differently worded skills semantically related?
- What standardized name should be used for the skill?

It also does not provide a technical interview score.

### CS2023

CS2023 provides computer-science curriculum knowledge areas such as:

- Software Development Fundamentals;
- Data Management;
- Software Engineering;
- Security;
- Networking and Communication;
- Operating Systems;
- Parallel and Distributed Computing.

It helps the team organize technical learning objectives. It does not provide a
ready-made student interview or score.

### The exact relationship between role data and the question bank

The following distinction is essential:

```text
O*NET / ESCO:
What skills are related to the occupation?

CS2023 / college syllabus:
What broad computing knowledge should a student learn?

Official technical documentation:
What are the technically correct concepts and practices?

RAG + local LLM:
Retrieve the relevant technical context and automatically generate a structured
question, expected concepts, rubric, and bounded follow-ups.

Automatic validators:
Check schema, source support, competency, seniority, duplication, and safety.

Faculty or industry reviewer:
Review the fixed research question set or a sample of generated outputs. The
reviewer does not manually write every question.

Question bank:
Store the approved result for later retrieval.
```

O*NET, ESCO, and CS2023 are therefore input references for question-bank
authoring. They are not the question bank itself.

### Complete example: from JD to question bank

Suppose the JD says:

```text
The candidate should build secure REST APIs using Spring Boot and JWT.
```

1. The JD parser extracts `REST APIs`, `Spring Boot`, and `JWT`.
2. O*NET/ESCO terminology helps associate these with software development,
   web-service development, and security skills.
3. The local dictionary groups them under the competency `API Design and
   Security`.
4. CS2023 Security and Software Engineering areas confirm that security and
   software-design reasoning are suitable learning areas.
5. Question-generation RAG retrieves relevant MDN and OWASP context about HTTP
   methods, authentication, authorization, input validation, and API-security
   risks.
6. The local LLM generates a structured question:

```text
How would you design and secure a Spring Boot REST API that uses JWT?
```

7. The same structured response includes expected concepts:

```text
password hashing
token creation
token validation
authentication versus authorization
HTTPS
input validation
token expiration
```

8. The response also contains a 1-5 rubric and bounded follow-ups.
9. Code automatically validates the schema, sources, competency, difficulty,
   duplication, and safety.
10. The validated record is stored in the question bank. For the fixed research
    set, faculty reviews the generated set before it is frozen.

At interview time, the system does not repeat all ten authoring steps. It simply
retrieves the already approved question and rubric from the bank.

## 5. Exact sources and what we take from each one

The project should maintain `docs/sources.csv` with:

```text
source_id,title,url,license,accessed_date,used_for,citation_key,notes
```

The source categories are:

### Occupation and skill sources

- O*NET: occupation, task, knowledge, skill, and technology relationships.
- ESCO: occupation and skill labels and relationships.
- Student JD: actual role requirements and priorities.
- Student resume: source-linked claims to verify.

### Curriculum sources

- ACM/IEEE-CS/AAAI CS2023: computing knowledge areas and learning objectives.
- Faculty-approved college syllabus: course-level learning outcomes.

These are used to define what should be assessed, not copied as interview
questions.

### Official technical sources for question and rubric authoring

Examples for IT roles:

- MDN: HTTP, JavaScript, browser APIs, and web fundamentals.
- OWASP: web and API security risks and controls.
- PostgreSQL documentation: SQL, indexes, query plans, and transactions.
- Python documentation: language behaviour and standard-library concepts.
- Oracle/OpenJDK documentation: Java language and runtime concepts.
- Spring documentation: Spring and Spring Boot concepts.
- Docker documentation: containers, images, networking, and deployment.
- Git documentation: version-control concepts.

Question-generation RAG retrieves relevant passages from these sources, and the
local LLM generates structured question packages containing the question,
expected concepts, rubric, and follow-ups. Automatic validation checks the
result before storage. We do not copy random interview websites.

### Textbooks

Copyrighted textbooks should not be copied into the retrieval corpus unless
permission or a suitable licence exists.

Faculty may use standard textbooks as human references while reviewing a rubric.
The software should store only:

- a normal bibliographic reference;
- a short reviewer-authored summary;
- permitted excerpts;
- or open-licensed material.

### Roadmap sources

Roadmap material should come from:

- official documentation;
- open-licensed tutorials;
- faculty-approved courses;
- team/faculty-authored exercises;
- reviewed mini-project tasks;
- valid canonical URLs.

There is no unrestricted live Google search while generating a student report.

### Exact starting source registry

These are the first concrete sources to register in `docs/sources.csv`:

| Source | Official URL | Exact use in FairHireAI |
|---|---|---|
| O*NET Database | https://www.onetcenter.org/database.html | Occupation titles, tasks, skills, knowledge, and technology relationships |
| ESCO services | https://esco.ec.europa.eu/en/use-esco | Occupation-skill terminology and relationships |
| ESCO API | https://esco.ec.europa.eu/en/use-esco/use-esco-services-api | Programmatic or local access to ESCO concepts |
| CS2023 knowledge areas | https://csed.acm.org/knowledge-areas/ | Computing learning areas used to organize IT competencies |
| MDN HTTP guide | https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Overview | HTTP/API learning objectives, question concepts, and roadmap resources |
| OWASP API Security | https://owasp.org/API-Security/ | API-security concepts, expected answers, and secure-development resources |
| PostgreSQL documentation | https://www.postgresql.org/docs/current/ | SQL, indexing, transactions, and query-plan sources |
| PostgreSQL EXPLAIN | https://www.postgresql.org/docs/current/using-explain.html | Query-plan rubric concepts and roadmap material |
| Python documentation | https://docs.python.org/3/ | Python-language and standard-library sources |
| Spring guides | https://spring.io/guides | Spring and Spring Boot learning sources |
| Oracle Java documentation | https://docs.oracle.com/en/java/ | Java-language and platform sources |
| Docker Get Started | https://docs.docker.com/get-started/ | Container concepts and learning resources |
| Git documentation | https://git-scm.com/doc | Version-control concepts and resources |
| pgvector | https://github.com/pgvector/pgvector | PostgreSQL vector storage and similarity search |
| BGE small embedding model | https://huggingface.co/BAAI/bge-small-en-v1.5 | Local text embeddings for semantic retrieval |
| Ollama structured output | https://docs.ollama.com/capabilities/structured-outputs | Local LLM JSON-schema enforcement |
| Qwen2.5 in Ollama | https://ollama.com/library/qwen2.5 | Candidate local instruction LLM family |

Before distributing or deploying the product, record and verify the licence and
permitted use for every ingested source and selected model. Linking to an
official page is not the same as having permission to copy the entire page into
the local corpus.

### Are these sources free to download and use?

Most are publicly accessible, but `free to read` is not identical to `free to
copy, modify, and redistribute`. The ingestion process must enforce the exact
licence of each source.

| Source | Practical treatment in this project |
|---|---|
| O*NET | Download the official structured database and retain CC BY 4.0 attribution |
| ESCO | Download the official free dataset and follow European Commission reuse and attribution terms |
| MDN | Store permitted selected content with MDN/Mozilla attribution and the applicable CC BY-SA notice |
| OWASP | Store selected project content with the applicable CC BY-SA attribution |
| Spring | Use selected documentation source under its applicable Apache 2.0 notices |
| PostgreSQL | Use selected documentation under the permissive PostgreSQL licence and retain notices |
| Python | Use selected documentation under the PSF licence; record separate code-example terms |
| Docker | Use selected documentation source under the Docker docs repository's Apache 2.0 licence |
| Git/Pro Git | Treat Pro Git's CC BY-NC-SA terms carefully because they include a non-commercial restriction |
| CS2023 | Use it as a cited curriculum framework and store our own competency summaries unless broader reuse is confirmed |
| Oracle Java documentation | Link and store our own attributed summaries or permitted short extracts; do not bulk-copy it |

The project does not need complete website copies. It should ingest only the
sections required for the supported competencies. Where reuse terms are
restrictive or unclear, store:

- source title and canonical URL;
- topic and competency metadata;
- our own factual summary;
- a bibliographic citation;
- no copied full text.

Every ingested record must retain:

```text
source ID
title and canonical URL
publisher
licence and attribution
retrieval date
content version or hash
permitted-use note
```

Roadmap records often need only metadata and a verified official URL. The
student reads the material on the publisher's website; RoleReady AI does not
need to republish the entire resource.

## 6. How a competency is selected from a JD

This is a multi-step process. The LLM does not simply guess six competencies.

### Example JD

```text
We need a junior developer with Java and Spring Boot experience.
The candidate should design REST APIs, work with PostgreSQL,
debug production issues, use Git, and understand Docker.
```

### Step 1: deterministic text extraction

Code first extracts the exact text and its character or page positions.

### Step 2: LLM structured extraction

The local LLM receives the extracted text and a JSON schema. It returns:

```json
{
  "role_title": "Junior Backend Developer",
  "seniority": "junior",
  "skills": [
    {"name": "Java", "source_text": "Java"},
    {"name": "Spring Boot", "source_text": "Spring Boot"},
    {"name": "REST APIs", "source_text": "design REST APIs"},
    {"name": "PostgreSQL", "source_text": "work with PostgreSQL"},
    {"name": "Debugging", "source_text": "debug production issues"},
    {"name": "Git", "source_text": "use Git"},
    {"name": "Docker", "source_text": "understand Docker"}
  ]
}
```

### Step 3: normalize terms

The system compares these terms with O*NET, ESCO, the local skill dictionary,
and existing competency definitions.

```text
Java + Spring Boot
    -> Programming and Framework Fundamentals

REST APIs
    -> API Design

PostgreSQL
    -> Database Reasoning

Production issues
    -> Debugging and Problem Solving

Docker
    -> Deployment and Container Fundamentals
```

Git may become supporting evidence inside Software Development Practices rather
than a full competency by itself.

### Step 4: group skills into assessable competencies

A competency must be broad enough for meaningful assessment but narrow enough
for a clear rubric.

Bad competency:

```text
Technology
```

Too narrow:

```text
Java ArrayList remove method
```

Suitable:

```text
Programming Fundamentals
API Design
Database Reasoning
Debugging and Problem Solving
Deployment Fundamentals
Technical Communication
```

### Step 5: calculate initial importance

Importance is based on:

- whether the JD says required or preferred;
- repetition in the JD;
- placement in responsibilities;
- relationship to the role's core work;
- approved role-template defaults.

Example:

```text
Programming Fundamentals     0.20
API Design                  0.20
Database Reasoning          0.20
Debugging                   0.15
Deployment Fundamentals     0.15
Technical Communication     0.10
Total                       1.00
```

### Step 6: validate with code

Code checks:

- five to eight competencies;
- every competency has JD evidence;
- no duplicates;
- weights total 1.0;
- seniority is consistent;
- protected characteristics are excluded;
- no company-confidential requirement is introduced.

### Step 7: student confirmation

The student sees the derived role and competencies before the interview and can
report an incorrect mapping.

### If the student does not upload a JD

A JD is preferred because it allows vacancy-specific assessment, but it is not
mandatory. The system uses this ordered fallback:

```text
Uploaded JD
    -> use JD-specific role, responsibilities, skills, and weights

No JD
    -> ask the student to select or enter a target role and seniority
    -> retrieve the standard competency profile for that role
    -> use the resume to personalize questions

No JD and no confirmed role
    -> do not start the interview
    -> suggest possible roles from the resume
    -> require the student to confirm one
```

For example, if the student selects `Backend Developer - Fresher`, the system
retrieves the standard role competencies from the local O*NET, ESCO, CS2023,
and reviewed technical-source index. These may include programming
fundamentals, API development, databases, debugging, security fundamentals,
basic system design, and technical communication.

The resume then provides personalization evidence such as skills, projects,
internships, certifications, and achievements. If it mentions Spring Boot,
MySQL, REST APIs, and a project using JWT, the interview can ask about that
project while still covering competencies expected for the selected role.

Question selection without a JD therefore follows:

```text
Confirmed target role and seniority
    -> standard role competencies
    -> resume claims and project evidence
    -> reviewed question/RAG context
    -> uncovered competencies
    -> previous-answer context
    -> next question or adaptive follow-up
```

The interview contains four question types:

- role-core questions from the confirmed role profile;
- resume-grounded questions about claimed evidence;
- adaptive follow-ups based on earlier answers;
- coverage questions for important competencies not yet assessed.

A resume alone cannot define the assessment target. It describes what the
student has done, but not the job for which readiness should be measured. The
system may recommend likely roles from the resume, but the student must confirm
the target role before question generation begins.

The report records the assessment basis:

```text
With JD:    JD-specific placement readiness
Without JD: Role-based placement readiness
```

It also records whether a JD was uploaded, the confirmed target role and
seniority, and the source of each competency. This prevents a general
role-based result from being misrepresented as readiness for a specific job
vacancy.

## 7. How the question bank is generated automatically

The question bank is not manually written question by question and is not
downloaded as one dataset. It is generated from the JD, normalized competencies,
retrieved official technical context, and a local LLM. Validated generated
records are stored and reused as the bank.

### The simplest mental model

Think of question authoring like a teacher preparing an examination:

```text
RAG brings the trusted study material.
The question-authoring LLM drafts the question and marking package.
Validation checks the complete package.
The question bank stores it.
The evaluator later applies the same frozen marking package.
```

The LLM does not generate only a rubric. When no suitable validated question
already exists, it drafts the complete package:

```text
question
expected concepts
1-5 question-specific rubric
bounded follow-ups and their trigger conditions
short reference explanation
source-to-concept mapping
```

If a matching validated package already exists, the interview retrieves it
instead of generating it again.

### Step 1: create a competency specification

Example:

```text
Competency ID: API_DESIGN
Level: Junior
Purpose: Assess whether the student can design and reason about a basic REST API
```

### Step 2: list learning objectives

Using the JD, CS2023, MDN, OWASP, and faculty input:

```text
The student should be able to:
- identify resources and endpoints;
- choose suitable HTTP methods;
- use status codes;
- validate input;
- distinguish authentication and authorization;
- explain error handling;
- discuss basic security risks.
```

### Step 3: retrieve official technical context

Question-generation RAG searches the approved technical-source collection for
the competency, skill, seniority, and expected learning area.

Example retrieved context:

```text
MDN: HTTP methods and response codes
OWASP: authentication, authorization, and common API-security risks
Spring documentation: Spring Security and request handling
```

### Step 4: local LLM generates a structured question package

The LLM receives only the JD evidence, normalized competency, seniority,
retrieved context, general rubric template, and JSON schema. It generates the
entire draft package, beginning with:

```text
How would you design and secure an API endpoint that returns a user's order
history?
```

### Step 5: generate expected concepts

Expected concepts are not copied from one model-answer paragraph. They are
derived from:

1. the competency definition and learning objectives;
2. concepts supported by retrieved official technical passages;
3. the JD and resume technology context;
4. the required seniority and depth.

This allows different correct wording. For example, a student can satisfy
`ownership authorization` by explaining that the logged-in user must own the
requested order even without using that exact phrase.

```json
[
  "GET endpoint",
  "resource-oriented URL",
  "authentication",
  "ownership authorization",
  "pagination",
  "input validation",
  "appropriate error responses"
]
```

### Step 6: generate a 1-5 rubric

The question-specific rubric combines a stable general template with the
expected concepts:

```text
1 = incorrect or no meaningful understanding
2 = partial understanding with major omissions
3 = correct basic understanding
4 = complete practical understanding
5 = deeper reasoning, risks, alternatives, or trade-offs
```

The LLM converts those general levels into measurable anchors for this exact
question:

```text
1: Cannot describe an API endpoint.
2: Mentions an endpoint but gives an incomplete flow.
3: Correctly explains method, response, and authentication.
4: Adds authorization, validation, pagination, and error handling.
5: Explains security threats, trade-offs, and alternatives.
```

### Step 7: generate bounded follow-ups

```text
If authentication is mentioned without authorization:
    How would you ensure one user cannot access another user's orders?

If a large result is returned without pagination:
    How would the endpoint handle one million orders?
```

### Step 8: attach sources and provenance

```json
{
  "question_id": "API-001",
  "author_type": "local_llm_generated",
  "model_id": "pinned-local-model",
  "prompt_version": "question-generator-v1",
  "source_ids": ["MDN-HTTP-001", "OWASP-API-001"],
  "validation_status": "pending_automatic_validation",
  "version": "1.0"
}
```

### Step 9: automatic validation

Validation has three different layers. They must not be confused.

Deterministic code checks:

- valid JSON schema and required fields;
- scores 1 through 5 are present and non-empty;
- source IDs exist in the approved registry;
- competency, level, and question type are valid;
- duplicate similarity;
- protected or unsafe content;
- length, allowed values, and policy constraints.

A grounded validator LLM checks:

- technical consistency against the retrieved passages;
- whether expected concepts are supported by those passages;
- question-to-competency relevance;
- seniority and difficulty suitability;
- alignment between the question, concepts, rubric, and follow-ups.

Ordinary code cannot genuinely understand all technical correctness. It remains
responsible for deterministic schema and policy checks, while the grounded
validator checks semantic consistency.

For the fixed research set, a faculty or technically qualified reviewer checks
the accepted packages or a defined representative sample. This supplies human
evidence for question and rubric quality.

### Step 10: store, reuse, and optionally review

If automatic validation passes, the record becomes:

```text
generated_validated_for_practice
```

It is stored in the question bank and can be reused for a later matching JD.

For the research-validation role, a fixed generated set is reviewed by faculty
and then marked:

```text
faculty_reviewed_research_set
```

Faculty reviews the generated set or a representative sample. Faculty does not
have to manually author every question.

### Step 11: version and freeze

When a student starts an attempt, the exact question and rubric version are
copied into the attempt. The expected concepts, follow-up rules, source IDs, and
prompt/model versions are frozen with them. Later edits to the bank do not
change old interviews, and the evaluator cannot create a different rubric after
seeing the student's answer.

### Practical first bank size

The local LLM can generate an initial batch for the Junior Backend Developer
validation role:

```text
6 competencies
x 5 core questions per competency
= 30 core questions

Each core question can have 1-2 bounded follow-ups. The project team runs the
generation and validation script instead of manually writing all records.
```

The research interview still uses only one selected core question per
competency and at most one follow-up.

## 8. What RAG means from zero

RAG means **Retrieval-Augmented Generation**.

In simple language, RAG is a smart search step in front of the LLM:

```text
RoleReady AI's approved local library
        -> search for relevant records
        -> send only those records to the LLM
        -> generate a grounded question, judgment, or roadmap
```

RAG does not automatically know MDN, OWASP, Spring, or PostgreSQL. The project
must first register, licence-check, ingest, tag, embed, and index selected
material from those sources. During an interview it searches this local
collection; it does not perform unrestricted live Google searches.

Without RAG:

```text
Ask LLM:
"Give this student a database roadmap."

Risk:
The LLM may give generic advice, invent a URL, or ignore the actual gap.
```

With RAG:

```text
1. Find the student's verified gap.
2. Search our approved repository.
3. Give only the retrieved records to the LLM.
4. Ask the LLM to organize those records.
5. Verify that every output source ID exists.
```

RAG is not a separate magical model. It is an application workflow around a
search system and an LLM.

### The three local collections RAG searches

#### 1. Role and competency collection

This stores:

```text
occupation and role names
role-to-skill relationships
normalized competency definitions
seniority expectations
JD-derived requirements
```

Its principal sources are the uploaded JD, O*NET, ESCO, CS2023, and reviewed
project competency definitions. It answers:

```text
What should be assessed for this role?
```

It does not contain detailed answers about JWT, indexes, or Spring Security.

#### 2. Technical knowledge and question collection

The technical part stores selected, licence-compliant passages or
reviewer-authored summaries from sources such as MDN, OWASP, Spring,
PostgreSQL, Python, Docker, and Git. It answers:

```text
Which trusted technical concepts should ground this question and rubric?
```

The question part stores complete validated packages containing the question,
expected concepts, fixed rubric, follow-ups, provenance, and embedding. It
answers:

```text
Do we already have a suitable validated question package?
```

#### 3. Approved learning-resource collection

This is a structured catalogue of real learning material:

```text
official documentation
official or open-licensed tutorials
reviewed coding exercises
safe practical labs
reviewed mini-project tasks
practice and reattempt questions
```

It answers:

```text
Which verified resource can address this exact evidence-backed skill gap?
```

It is not another ML dataset. Developers create the initial catalogue by
registering real resources, checking their URLs and licences, tagging them by
competency, technology, level, resource type, duration, and learning outcome,
and marking their review status.

## 9. Which type of RAG are we using?

The selected type is:

**Graph-guided contextual hybrid RAG.**

### Graph-guided

The Evidence Graph tells RAG exactly why retrieval is required.

Example graph facts:

```text
Role: Backend Developer
Competency: Database Reasoning
Question: SQL optimization
Missing rubric criterion: Explain query plans
Evidence: Answer 4, 01:12-01:43
Confidence: 0.86
```

These facts become the retrieval query.

### Contextual

Each stored chunk includes context before its content.

```text
Source: PostgreSQL documentation
Competency: Database Reasoning
Topic: Query-plan inspection
Difficulty: Intermediate
Type: Official documentation
Content: EXPLAIN displays the query plan...
```

This helps retrieval understand what the passage is about even if the passage
alone is short.

This is the practical contextual-RAG idea used in this project. We are not
claiming a separate contextual-embedding research contribution.

### Hybrid

We combine two searches:

1. **Keyword/full-text search** finds exact words such as `JWT`, `EXPLAIN`,
   `ACID`, or `Docker`.
2. **Semantic/vector search** finds similar meanings such as:

```text
"query execution analysis"
similar to
"query-plan inspection"
```

Combining them is safer than relying on only one search method.

### What the Evidence Graph does not do

The Evidence Graph does not replace the vector database.

- Evidence Graph: explains why the student needs something.
- PostgreSQL/pgvector: searches for the relevant approved record.
- LLM: adapts or organizes the retrieved records.

## 10. The two retrieval pipelines, explained step by step

We use the same search infrastructure but keep two separate collections.

### A. Question retrieval pipeline

The question collection stores complete structured question records:

```text
question
competency
skill
seniority
difficulty
expected concepts
rubric ID
follow-ups
source IDs
review status
embedding
```

#### Exact flow

Suppose the profile requires:

```text
Competency: API Design
Skill: Authentication
Seniority: Junior
Resume claim: Implemented JWT authentication
```

The complete decision flow is:

```text
JD or confirmed role
    -> select required competency
    -> build query with seniority, resume, coverage, and exclusions
    -> filter and search the validated question bank
    -> is a suitable package found?

YES:
    load complete question package
    -> optionally personalize wording with a constrained LLM
    -> verify that competency, difficulty, concepts, and rubric did not change
    -> freeze package with the attempt
    -> ask student

NO:
    retrieve approved technical-source chunks
    -> question-generation LLM creates a complete draft package
    -> deterministic and grounded validation
    -> store accepted package with its validation status
    -> freeze package with the attempt
    -> ask student
```

The detailed retrieval steps are:

1. Filter questions:

```text
review_status = approved
competency = API Design
seniority = Junior
question_type = core
```

2. Create a search sentence:

```text
Junior API authentication question involving JWT and authorization
```

3. Keyword search finds questions containing JWT, token, authentication, or
   authorization.
4. Vector search finds semantically related questions even when wording differs.
5. Combine the rankings.
6. Select the highest-ranked question with an unused question ID.
7. Load its fixed rubric and expected concepts.
8. Give the selected question and resume claim to the LLM.
9. The optional personalization LLM may personalize only the wording:

```text
Bank:
Explain authentication and authorization for a REST API.

Adapted:
Your resume mentions JWT authentication. Explain how you implemented
authentication and authorization for your REST API.
```

10. Code verifies that the competency, difficulty, and rubric ID did not change.
11. Save the exact adapted question with the attempt.

If personalization is unnecessary, the retrieved validated question is asked
directly. An LLM call is not required for every question.

#### If no approved question is found

The system searches the technical-source collection using the competency,
seniority, JD technology, and expected learning objective. It gives only the
retrieved approved chunks to the question-generation LLM, which creates:

- core question;
- expected concepts;
- 1-5 rubric;
- bounded follow-ups and trigger conditions;
- short reference explanation;
- source-to-concept mapping.

Deterministic code validates the schema, IDs, allowed values, duplicates, and
policies. A grounded validator checks technical consistency, source support,
difficulty, and alignment between the question, concepts, rubric, and
follow-ups. The stored status reflects the validation level, for example:

```text
generated_validated_for_practice
```

The fixed research set requires the additional defined human-review procedure
before it is treated as research-validated evidence.

#### Where the LLM appears in adaptive follow-ups

After an answer, the engine first checks for a stored validated follow-up linked
to the missing rubric criterion. If one exists, it asks that question directly.
If none exists, a constrained follow-up LLM receives:

```text
original question
previous answer
missing frozen rubric criterion
permitted technical context
follow-up schema and limits
```

It may generate one bounded follow-up. Backend code verifies that the
competency, difficulty, and rubric remain unchanged before the question is
asked.

#### What does not use an LLM

Normal backend and database code performs:

```text
metadata filtering
keyword/full-text search
vector similarity search
rank fusion
duplicate removal
previously-used question exclusion
schema and source-ID validation
```

The LLM operates after retrieval; it does not perform PostgreSQL or pgvector
search.

#### LLM locations across the complete workflow

```text
1. Profile-extraction LLM:
   extracted JD/resume text -> candidate structured facts

2. Question-personalization LLM:
   retrieved package + resume/previous context -> controlled wording

3. Question-generation LLM:
   retrieved technical chunks -> missing complete question package

4. Follow-up LLM:
   previous answer + missing criterion -> one bounded follow-up

5. Evaluator LLM:
   transcript + frozen package -> criterion judgments and evidence

6. Roadmap LLM:
   retrieved approved resources -> organized learning plan
```

### B. Roadmap retrieval pipeline

The roadmap collection stores approved learning resources and chunks:

```text
resource ID
resource title
canonical URL
publisher
competency
skill
detailed learning outcomes
technology
difficulty
estimated time
resource type
licence and attribution
review status
URL verification date
content chunk
embedding
```

Typical records include:

- MDN or framework documentation for a concept;
- OWASP security guidance or a safe educational lab such as crAPI;
- PostgreSQL documentation plus an `EXPLAIN` practice task;
- an official Spring, Python, or Docker tutorial;
- a reviewed coding exercise created for one competency;
- a reviewed mini-project task;
- a reattempt question linked to the same missing criterion.

For many roadmap records, only metadata, an original summary, and the verified
official URL are stored. The complete external tutorial does not need to be
copied into the database.

#### Exact flow

Suppose the graph identifies:

```text
Gap: SQL query-plan analysis
Missing criterion: Could not explain EXPLAIN
Difficulty: Junior
Available time: Five days
```

1. Create a retrieval request from the graph.
2. Filter:

```text
review_status = approved
competency = Database Reasoning
difficulty IN (beginner, intermediate)
url_status = valid
```

3. Keyword search looks for `EXPLAIN`, `query plan`, `index scan`.
4. Vector search looks for semantically related passages.
5. Combine both rankings.
6. Return the best three to five resources.
7. Give only these resources to the LLM.
8. Ask the LLM to create a five-day plan.
9. Require resource IDs for every roadmap item.
10. Backend code rejects unknown resource IDs or URLs.
11. If nothing suitable is found, return:

```text
Verified gap exists, but no reviewed learning resource is available.
```

The LLM is never allowed to invent a URL.

#### How a resource becomes approved

Deterministic checks verify:

- the URL uses an allowed protocol and currently resolves;
- the publisher/domain is allowed;
- required metadata and licence notes are present;
- competency, skill, difficulty, and resource type are valid;
- the resource is not a duplicate.

A developer, grounded validator, or reviewer verifies that the material really
teaches the tagged learning outcome and is suitable for the stated level. A
faculty member may review the initial research catalogue or a representative
sample; faculty does not need to author every resource.

Example for an `authentication versus authorization` gap:

```text
1. MDN HTTP authentication explanation
2. Spring Security authorization documentation
3. OWASP object-level authorization guidance
4. reviewed ownership-check coding exercise
5. API-security reattempt question
```

The LLM may arrange those five retrieved records into a day-by-day sequence.
It cannot insert an unregistered course or make up a URL.

## 11. How the RAG database is created

### Resource ingestion

A reviewer or authorised team member adds a resource:

```json
{
  "resource_id": "PG-EXPLAIN-001",
  "title": "Using EXPLAIN",
  "url": "https://www.postgresql.org/docs/current/using-explain.html",
  "publisher": "PostgreSQL",
  "competency": "database_reasoning",
  "skills": ["query_plans", "indexing"],
  "difficulty": "intermediate",
  "estimated_minutes": 45,
  "review_status": "approved"
}
```

### Chunking

Long permitted content or reviewer-authored summaries are divided into smaller
passages, for example 300-500 tokens with a small overlap.

### Context prefix

Each passage receives the source, competency, topic, and difficulty context.

### Embedding

A small local embedding model converts the passage into a numerical vector.

Example:

```text
[0.021, -0.184, 0.307, ...]
```

The numbers do not have a human-readable meaning individually. Similar passages
have vectors located closer together.

### Storage

PostgreSQL stores normal fields, text, approval status, and source information.
The `pgvector` extension stores embeddings.

PostgreSQL full-text search provides keyword retrieval. pgvector provides
semantic retrieval.

## 12. LLM provider: final implemented decision

### Primary design

Use the **Gemini API through a backend-only provider adapter**. The pinned
generation model is `gemini-3.5-flash-lite`; embeddings use
`gemini-embedding-2` with 384 dimensions.

Reasons:

- it is fast enough for live question wording and rubric evaluation on the
  available laptop;
- the model and prompt versions are frozen on each question and analysis;
- structured JSON output can be enforced.
- it avoids the high latency observed with local Ollama models on the RTX 3050.

### Privacy boundary

External-AI processing has its own required consent record. Raw video and audio
are never sent to Gemini. The backend sends only the frozen question/rubric,
reviewed source mapping, transcript, and the minimum relevant resume/JD text.
The API key stays in the backend's git-ignored environment and is never placed
in any `VITE_*` variable.

### Why not run both for every student?

Using both would:

- increase latency;
- create inconsistent outputs;
- increase privacy exposure;
- complicate score reproducibility.

Use one pinned provider for a production or research run. Ollama remains a
possible future offline comparison, not the implemented default.

### What the LLM does

The LLM is allowed to:

1. extract structured JD information from already extracted text;
2. form a controlled competency profile;
3. personalize an approved question;
4. generate an unreviewed draft when the bank has no coverage;
5. evaluate a transcript against a supplied rubric;
6. organize retrieved resources into a cited roadmap.

### What the LLM does not do

It does not:

- directly read binary files;
- decide whether someone is hired;
- invent the final score formula;
- change an approved rubric;
- use facial features to judge technical correctness;
- invent links;
- freely choose unlimited questions;
- write directly to the database without schema validation.

## 13. Complete internal architecture flow

The complete architecture has four planes:

1. offline knowledge preparation;
2. offline ML development;
3. online student interview;
4. storage, privacy, and audit.

## 14. Plane 1: offline knowledge preparation

This happens before students use the system.

```text
O*NET/ESCO/CS2023
+ official technical sources
+ RAG-grounded LLM question generation
+ automatic validation
+ faculty review of the fixed research set
        |
        v
role and competency catalogue
question bank and rubrics
learning-resource repository
embeddings and search indexes
```

Outputs:

- normalized role/skill dictionary;
- competency definitions;
- approved questions;
- fixed rubrics;
- approved follow-ups;
- reviewed learning resources;
- question embeddings;
- resource embeddings.

Why it is needed:

- prevents the live LLM from inventing the whole interview;
- gives reproducible questions and scoring criteria;
- gives RAG something trusted to search.

## 15. Plane 2: offline multimodal-model development

This also happens before the live interview.

```text
First Impressions V2 videos and labels
        |
        v
Whisper + openSMILE + OpenFace preprocessing
        |
        v
word-level text/audio/visual alignment
        |
        v
MAG-BERT baseline and MAG-BERT-ARL training
        |
        v
performance, ablation, fairness, and SHAP evaluation
        |
        v
selected model checkpoint
```

### What FI V2 supplies

- speaking videos;
- interview-variable labels;
- data for the base multimodal experiment.

### What FI V2 does not supply

- technical interview questions;
- technical rubrics;
- technical-readiness labels;
- roadmap resources;
- backend-skill ground truth.

### Why this offline block is necessary

It proves:

- where the deployed model came from;
- which data trained it;
- which preprocessing was used;
- whether ARL improved the selected metrics;
- whether text/audio/visual modalities contributed;
- how the model was selected.

## 16. Plane 3: online student interview

### Stage 1: authentication and consent

The student signs in and accepts the stated recording and processing purpose.
Consent is stored with a version and timestamp.

### Stage 2: JD and resume upload

Files are checked for:

- type;
- size;
- corruption;
- encryption;
- file hash.

PDF/DOCX/TXT text is extracted deterministically with source positions.

### Stage 3: role and competency profile

A deterministic parser first extracts plain text and source positions from the
JD and resume. A schema-constrained local LLM then converts that text into
candidate structured facts:

```text
JD: role, seniority, required/preferred skills, and responsibilities
Resume: skills, projects, internships, certifications, and achievements
```

The LLM must return the original source span for each candidate fact. Backend
code verifies that the span exists, rejects unsupported claims, normalizes
terminology with the approved role/skill catalogue, removes duplicates and
protected information, and asks the student to confirm the final profile. The
LLM does not directly read an unchecked binary file and its output is not
trusted without validation.

### Stage 4: question plan

Question retrieval selects an approved core question and rubric for each
competency. The LLM may personalize the wording. Missing-bank coverage produces
an unreviewed controlled draft.

Core questions and possible follow-ups are cached before the interview.

### Stage 5: adaptive question selection

Code selects the highest-priority uncovered competency.

After each answer it checks:

```text
competency coverage
rubric match
correctness and depth
completeness
evidence confidence
resume consistency
follow-up already used or not
```

Decision:

```text
if no core answer:
    ask the core question
else if evidence is insufficient and follow-up is unused:
    ask one bounded follow-up
else:
    move to the next uncovered competency
```

### Stage 6: video recording and normalization

The student records or uploads an answer.

FFmpeg creates a stable format such as:

- 25 FPS video;
- standard width;
- 16 kHz mono audio.

### Two parallel answer-analysis pipelines

After normalization, the same answer enters two separate pipelines:

```text
Technical-content pipeline:
transcript + frozen question package + retrieved technical context
    -> constrained LLM rubric judgment
    -> technical evidence, score inputs, and skill gaps

Multimodal research and delivery pipeline:
aligned text + acoustic features + visual features
    -> MAG-BERT-ARL Base Multimodal Interview Signal
    -> Gradient SHAP attribution
    -> supporting model evidence and observable delivery indicators
```

RAG and the LLM handle technical knowledge, question evaluation, gap reasoning,
and roadmap organization. MAG-BERT-ARL handles synchronized text/audio/visual
patterns. Neither pipeline replaces the other, and the multimodal signal does
not determine technical correctness.

### Stage 7: Whisper transcription

Whisper-timestamped returns:

- transcript;
- word start time;
- word end time;
- word confidence;
- segment confidence.

Whisper does not produce technical scores.

Whisper timestamps also allow backend code to calculate:

```text
speaking pace = transcribed words / answer duration
pause duration = next word start - previous word end
filler count = context-checked filler expressions in the transcript
```

These become observable delivery indicators, not nervousness or personality
labels.

### Stage 8: acoustic extraction

openSMILE/eGeMAPS produces 88 measurable acoustic features for each word
interval.

These may describe pitch, loudness, spectrum, voice quality, energy, and timing.
They are not direct emotion or personality truth.

Backend code may summarize permitted acoustic measurements as:

```text
voice-energy consistency
long-pause count
audio availability and quality
```

For example, the report may state `four pauses longer than 1.5 seconds`; it must
not transform that observation into `the student was nervous`.

### Stage 9: visual extraction

OpenFace produces frame-level landmarks, gaze estimates, head pose, face shape,
facial action units, tracking confidence, and success.

The selected visual payload is 709 values after metadata columns are excluded.
These are observable measurements, not emotion labels.

Backend code may summarize:

```text
head-movement stability
camera-facing/gaze estimate
valid face-tracking percentage
```

Camera placement, note-taking, disability, culture, and tracking errors can
affect these values. They should initially be descriptive and should not
strongly penalize readiness.

### Stage 10: word-level alignment

For each word:

```text
word text
+ 88 acoustic values from its audio interval
+ 709 visual values from the nearest valid face frame
```

This prevents the model from combining a word with audio or visual evidence
from a different time.

### Stage 11: BERT token alignment

BERT may split one word into several WordPiece tokens. The corresponding audio
and visual vector is copied to those subword tokens.

CLS, SEP, and padding receive zero modality vectors.

### Stage 12: MAG-BERT

MAG starts with the BERT text representation and learns how much aligned audio
and visual information should modify each word.

BERT processes the fused sequence and produces a CLS representation of the
answer.

### Stage 13: ARL

During training:

- the learner minimizes prediction loss;
- the adversary gives more weight to high-loss examples;
- the learner is forced to improve on difficult regions.

During the live interview, the trained learner produces the prediction. The
adversary is not used as a student-facing decision maker.

The safe output name is:

```text
Base Multimodal Interview Signal
```

It is not technical readiness, personality, emotion, or hiring probability.

First Impressions V2 contains an `interview` variable and apparent-personality
annotations, not ground-truth nervousness, genuine confidence, or technical
competence. Therefore, the deployed output cannot be renamed `confidence`,
`nervousness`, `employability`, or `technical readiness`.

The reason for retaining MAG-BERT-ARL is specific:

1. it is the trained multimodal research component of the project;
2. it tests whether synchronized text/audio/visual fusion improves prediction
   of the FI V2 interview label;
3. ARL tests whether reweighting difficult training examples improves the
   selected metrics;
4. it supplies a separate supporting signal and model-attribution artefacts;
5. it does not replace rubric-grounded technical assessment.

### Stage 14: Gradient SHAP

Gradient SHAP estimates which text, acoustic, and visual inputs influenced the
base-model prediction.

Its exact flow is:

```text
aligned text/audio/visual features
    -> MAG-BERT-ARL prediction
    -> Gradient SHAP attribution values
    -> aggregate by modality, word, and time interval
    -> store in the Evidence Graph
    -> show a simplified attribution in the report
```

Example:

```text
Base Multimodal Interview Signal: 0.64
Approximate model influence: text 61%, audio 26%, visual 13%
Influential text/time span: 12.4-15.1 seconds
```

These are model-influence values, not percentages of ability or confidence.

It explains model influence. It does not prove:

- technical correctness;
- causality;
- fairness;
- hiring suitability.

RoleReady AI therefore has two different explanations:

```text
Technical explanation:
Rubric + transcript evidence explain why a technical score or gap was produced.

Multimodal explanation:
Gradient SHAP explains which inputs influenced the MAG-BERT-ARL signal.
```

SHAP does not explain the LLM's technical judgment, and the rubric explanation
does not explain MAG-BERT's internal prediction.

### Stage 15: LLM rubric evaluation

The local LLM receives:

- role;
- competency;
- exact question;
- expected concepts;
- fixed rubric;
- transcript with timestamps;
- relevant resume claim;
- previous-answer evidence;
- permitted official technical context.

The question, expected concepts, rubric, follow-up rules, and source IDs were
generated and validated together before the student answered. They are loaded
from the frozen attempt record. The evaluator does not regenerate or rewrite
them after seeing the answer.

The evaluator performs:

```text
identify covered expected concepts
identify missing concepts
quote timestamped evidence from the transcript
apply the frozen rubric anchors
apply the fixed communication rubric for relevance and structure
return criterion judgments and confidence
```

It returns schema-validated JSON:

```json
{
  "rubric_match": 0.82,
  "correctness_and_depth": 0.76,
  "completeness": 0.80,
  "resume_consistency": 0.85,
  "evidence_confidence": 0.88,
  "satisfied_criteria": ["..."],
  "missing_criteria": ["..."],
  "evidence_spans": [
    {
      "start_seconds": 14.2,
      "end_seconds": 18.6,
      "text": "..."
    }
  ]
}
```

The LLM must return insufficient evidence rather than guess.

### Stage 16: backend score calculation

The LLM does not calculate the final arithmetic.

Before arithmetic, backend code validates that:

- the LLM output matches the required JSON schema;
- score values are in the allowed range;
- every quoted evidence span exists in the transcript;
- covered and missing concepts belong to the frozen rubric;
- timestamps are valid;
- question, rubric, prompt, and model versions match the attempt.

Invalid output is retried or marked failed; it never becomes a placeholder
score.

Backend code then applies versioned formulas:

```text
Technical Readiness =
0.35 * competency rubric match
+ 0.25 * correctness and depth
+ 0.20 * technical follow-up quality
+ 0.20 * resume/project consistency
```

```text
Communication Clarity =
0.30 * relevance
+ 0.25 * structure
+ 0.20 * completeness
+ 0.15 * pace/filler quality
+ 0.10 * transcript confidence
```

```text
Interview Response Quality =
0.35 * follow-up responsiveness
+ 0.30 * completeness
+ 0.20 * resume-answer consistency
+ 0.15 * professionalism rubric
```

```text
Placement Readiness =
0.50 * Technical Readiness
+ 0.25 * Communication Clarity
+ 0.25 * Interview Response Quality
```

These initial weights are expert-defined and require later calibration. They are
not learned truths.

The Base Multimodal Interview Signal is not an input to Technical Readiness.
It remains a separate research/supporting output unless a consented student
study, human ratings, calibration, and fairness analysis later justify a
specific contribution to a communication-related score.

The student-facing delivery indicators are produced across Stages 7-16:

| Indicator | Source and calculation stage |
|---|---|
| Speaking pace | Whisper word count and answer duration, Stage 7 |
| Number and duration of pauses | Whisper timestamps plus audio silence, Stages 7-8 |
| Filler words | Context-checked transcript expressions, Stage 7 |
| Voice-energy consistency | openSMILE energy variation, Stage 8 |
| Head-movement stability | OpenFace head-pose variation, Stage 9 |
| Camera-facing/gaze estimate | OpenFace gaze and head pose over valid frames, Stage 9 |
| Answer relevance | Fixed communication rubric applied to transcript, Stage 15 |
| Answer structure | Fixed communication rubric applied to transcript, Stage 15 |
| Presentation/Communication Delivery | Versioned backend formula, Stage 16 |

The initial `Communication Clarity` formula is the transparent
Presentation/Communication Delivery score. Voice energy, head movement, and
gaze should initially be shown as descriptive observations rather than used as
strong penalties. Their contribution to a score requires separate validation.

Example student-facing observations:

```text
Speaking pace: 120 words per minute
Long pauses: 4
Filler words: 6
Voice-energy consistency: moderate
Head-movement stability: stable
Camera-facing estimate: 74% of valid frames
Answer relevance: 4/5
Answer structure: 3/5
Presentation/Communication Delivery: 75/100
```

`Evidence confidence` means confidence in the reliability of the transcript,
media, and cited evidence. It never means the student's self-confidence.

### Stage 17: confidence gating

Score and confidence are different.

Example:

```text
Answer quality appears good.
Audio is badly corrupted.
```

Correct result:

```text
Technical evidence may be positive, but overall evidence confidence is low.
Request a follow-up or report insufficient evidence.
```

Incorrect result:

```text
Low audio quality means low technical capability.
```

Placement Readiness is suppressed when critical coverage or evidence confidence
is below the configured threshold.

### Stage 18: Evidence Graph update

The graph stores nodes such as:

- Student;
- Attempt;
- JobDescription;
- TargetRole;
- Competency;
- ResumeClaim;
- Question;
- AnswerSegment;
- TranscriptSpan;
- AudioEvidence;
- VisualEvidence;
- ModelPrediction;
- ShapAttribution;
- DeliveryObservation;
- RubricJudgment;
- SkillGap;
- RoadmapItem;
- ProgressMetric.

Example chain:

```text
JD requires database reasoning
-> Database Reasoning competency
-> SQL optimization question
-> answer at 01:12-01:43
-> rubric criterion DB-04 missing
-> query-plan gap
-> approved PostgreSQL EXPLAIN resource
-> database reattempt
```

For delivery and model explainability, the graph separately records:

```text
Answer
-> speaking pace, pauses, and fillers
-> acoustic and visual availability
-> head/gaze descriptive observations
-> Base Multimodal Interview Signal
-> Gradient SHAP modality/time attribution
```

These nodes are not allowed to create a technical skill gap.

### Stage 19: follow-up or next competency

The graph sends evidence coverage to the adaptive engine.

The engine asks one bounded follow-up or advances to the next competency.

### Stage 20: skill-gap detection

A missing word is not automatically a skill gap. A confirmed gap requires:

1. the competency is important for the confirmed role or JD;
2. the concept is part of the question's frozen rubric;
3. the answer does not demonstrate the concept;
4. a bounded follow-up does not resolve it, when a follow-up is appropriate;
5. transcript and evaluation confidence are sufficient;
6. evidence IDs and timestamps support the conclusion.

For example:

```text
Question: Secure an order-history API
Covered: GET endpoint and JWT authentication
Missing: ownership authorization
Follow-up: How would you prevent access to another user's orders?
Follow-up result: Ownership checking still not explained
Confirmed gap: Object-level authorization
```

Related missing criteria such as ownership checking, permission verification,
and the correct forbidden response may be grouped into one useful gap instead
of three tiny gaps.

The backend stores:

```json
{
  "competency": "API_SECURITY",
  "skill_gap": "object_level_authorization",
  "technology": "Spring Boot",
  "severity": "major",
  "evidence": "Authentication was explained, but ownership checking was not.",
  "confidence": 0.87,
  "status": "confirmed"
}
```

If audio, transcription, or answer evidence is unreliable, the result is
`insufficient_evidence`, not a confirmed weakness. The system requests a
re-recording or another question.

### Stage 21: roadmap RAG

The Evidence Graph converts the confirmed gap into a structured retrieval
request:

```json
{
  "role": "Junior Backend Developer",
  "competency": "API_SECURITY",
  "skill_gap": "object_level_authorization",
  "technology": "Spring Boot",
  "difficulty": "beginner",
  "severity": "major",
  "available_days": 5
}
```

This is the graph-guided part: the query contains the exact missing skill, its
evidence, the relevant technology, and the required level.

Roadmap RAG searches only the approved learning-resource collection. It first
filters by competency, skill, difficulty, technology, review status, and valid
URL. Keyword search finds exact terms such as `authorization`, `ownership`, and
`Spring Security`; vector search finds equivalent meanings such as `prevent one
user from accessing another user's data`. Their rankings are combined.

For the example gap, retrieval may return:

```text
1. MDN HTTP authentication material
2. Spring Security authorization documentation
3. OWASP object-level authorization guidance
4. reviewed ownership-check coding exercise
5. different API-security reattempt question
```

RAG retrieves existing approved records; it does not write the roadmap. The
roadmap LLM receives only the confirmed gap, student level, available time, and
retrieved resource records. It arranges them from concept learning to practical
application:

```text
Day 1: Review authentication fundamentals.
Day 2: Learn authentication versus authorization.
Day 3: Study object-level authorization.
Day 4: Implement and test an ownership check with two users.
Day 5: Complete a different reattempt question.
```

Every step must cite a supplied resource ID. Backend code verifies that:

- every resource ID exists and is approved;
- every URL matches the stored canonical URL;
- the difficulty and workload are suitable;
- the activities address the confirmed gap;
- the sequence includes practice and a measurable reattempt.

The LLM may organize and explain retrieved resources, but it cannot invent a
course, URL, or resource ID. If no suitable approved resource exists, the
system reports a resource-coverage gap instead of fabricating one.

### Stage 22: report

The student receives:

- Technical Readiness;
- Communication Clarity;
- Interview Response Quality;
- evidence confidence;
- strengths;
- missing criteria;
- timestamps and rubric links;
- verified gaps;
- approved learning tasks;
- reattempt suggestion.

The report keeps technical, delivery, and model-research outputs visibly
separate:

```text
TECHNICAL ASSESSMENT
API Security score, strengths, missing criteria, transcript evidence, gap

PRESENTATION AND COMMUNICATION
speaking pace, pauses, fillers, voice-energy consistency,
head-movement stability, camera-facing estimate, relevance, structure,
Presentation/Communication Delivery score

MULTIMODAL MODEL EXPLANATION
Base Multimodal Interview Signal, evidence availability,
Gradient SHAP modality and time-span attribution

ROADMAP AND PROGRESS
approved resources, exercises, reattempt, before/after evidence
```

The report must not display `nervousness`, `anxiety`, `actual confidence`,
`personality`, or `hiring probability`. Those labels are not supported by the
current data and validation.

### Stage 23: reattempt and progress

After study, the student takes another assessment.

The graph connects old and new evidence with `improves_over`. Progress is based
on comparable competency evidence, not only two unexplained percentages. The
reattempt uses a different validated question for the same competency so that
the student must demonstrate learning rather than repeat a memorized response.

Example:

```text
Before roadmap: object-level authorization = 1/5
After roadmap:  object-level authorization = 4/5
Status: improved
```

Completing or clicking roadmap items alone does not prove improvement; new
interview evidence does.

## 17. Plane 4: storage, privacy, and audit

### PostgreSQL

Stores:

- users and consent;
- roles and competencies;
- question bank;
- rubrics;
- attempts and answers;
- scores and confidence;
- resources and metadata;
- graph nodes and edges;
- source provenance.

### pgvector

Stores:

- question embeddings;
- resource-chunk embeddings.

### Private object storage

Stores:

- resumes;
- videos;
- normalized media;
- extracted features;
- SHAP artefacts;
- model checkpoints.

No raw video should have a public URL.

### Why not Neo4j initially?

The research novelty is the evidence relationship design, not the graph-database
brand. PostgreSQL graph-node and graph-edge tables are sufficient for the first
release. Neo4j can be added later if complex traversal requires it.

## 18. Backend, frontend, and worker responsibilities

### Frontend

Lovable can help generate the React interface:

- login and consent;
- JD/resume upload;
- profile confirmation;
- recording;
- question display;
- processing status;
- report;
- roadmap;
- reattempt progress.

Lovable does not create the ML model, RAG logic, Evidence Graph, or backend.

### FastAPI backend

Responsible for:

- API validation;
- orchestration;
- LLM schema validation;
- question selection;
- score arithmetic;
- graph updates;
- retrieval calls;
- report creation;
- access control.

### Background worker

Long operations run outside the web request:

- video normalization;
- Whisper;
- OpenFace;
- feature extraction;
- MAG-BERT inference;
- SHAP.

The frontend polls a job:

```text
queued -> transcribing -> extracting -> evaluating -> complete
```

## 19. Performance on the RTX 3050 6 GB laptop

Do not load all models on the GPU simultaneously.

Recommended order:

```text
load Whisper
-> transcribe
-> release memory

run openSMILE/OpenFace
-> cache features

load MAG-BERT learner
-> infer
-> release memory

load local LLM
-> return rubric JSON or roadmap
-> release memory
```

Other controls:

- pre-generate question plans;
- cache JD/resume extraction;
- cache embeddings;
- cache transcripts and features;
- process videos asynchronously;
- use a quantized LLM;
- use small training batches and gradient accumulation.

The system is not expected to produce an instant report immediately after a
video is submitted. The UI should show honest processing states.

## 20. Validation plan

### Base-model evaluation

On First Impressions V2:

- Pearson correlation;
- RMSE;
- text/audio/visual ablations;
- MAG-BERT versus ARL variants;
- permitted fairness metrics;
- Gradient SHAP samples.

### Question retrieval evaluation

Create test cases:

```text
JD competency -> expected approved question IDs
```

Measure:

- top-1 and top-k retrieval relevance;
- wrong-seniority retrieval;
- duplicate questions;
- reviewer approval rate.

### Roadmap retrieval evaluation

For known gaps, reviewers judge:

- resource relevance;
- difficulty suitability;
- source trustworthiness;
- citation correctness;
- roadmap usefulness.

### LLM rubric evaluation

Compare LLM rubric scores against three human evaluators.

Measure:

- weighted kappa or ICC;
- criterion-level agreement;
- unsupported evidence rate;
- score stability across repeated runs.

### System usability evaluation

Students rate:

- explanation clarity;
- perceived usefulness;
- roadmap relevance;
- trust;
- reattempt usefulness.

## 21. Failure handling

The system must fail safely.

### Unsupported or unclear JD

Return:

```text
The role or seniority could not be determined. Please confirm or edit the role.
```

### No approved question

Generate a controlled unreviewed practice question or report missing coverage.

### Poor audio

Lower evidence confidence and request re-recording or a follow-up.

### No valid face frames

Continue with available text/audio evidence and mark visual evidence missing.

### LLM invalid JSON

Retry once with the schema. If still invalid, mark evaluation failed. Do not
parse arbitrary prose into a score.

### No roadmap resource

Report an unresolved resource gap. Do not invent a URL.

### Model unavailable

Report processing unavailable. Never return a placeholder score.

## 22. Privacy and ethical rules

- explicit consent before recording;
- private storage;
- participant IDs in research exports;
- retention and deletion policy;
- no protected attributes as normal inputs;
- demographic labels only for permitted offline audit;
- no facial gender inference;
- no emotion or personality diagnosis;
- no candidate ranking;
- no hiring prediction;
- source and confidence for every conclusion;
- de-identification and consent before optional API use.

## 23. Current truthful implementation status

Recorded completed work:

- 6,000 FI training and 2,000 validation videos matched with labels;
- 7,994 usable videos fully preprocessed; six silent/no-word recordings were
  logged and excluded without stopping the run;
- Whisper timestamps, 88-dimensional eGeMAPS, 709-dimensional OpenFace
  alignment, BERT cache, manifest, checksums, and resumable preprocessing;
- seven completed training experiments: text baseline, MAG-BERT, MAG-BERT-ARL
  MSE, text+audio, text+visual, ARL BCE, and ARL MSE+BCE;
- selected MAG-BERT checkpoint with frozen SHA-256 and validation metrics;
- validation comparison, modality ablations, fairness audit, and Gradient SHAP;
- versioned multi-role catalogue with six competencies per role;
- 14 reviewed source summaries, 17 approved learning resources, and embeddings;
- 36 question packages independently validated and embedded; all 36 passed;
- optional-JD role detection and approved-weight adaptation;
- real PDF/DOCX/TXT resume extraction and evidence claims;
- bounded adaptive question selection with frozen question/rubric/source
  snapshots and optional Gemini personalization;
- per-answer Whisper/openSMILE/OpenFace/MAG-BERT worker and constrained Gemini
  rubric evaluator;
- observable delivery measures that never infer emotion or personality;
- Competency Evidence Graph, transparent scorecard, confidence gating,
  evidence-backed skill gaps, approved-resource roadmap, and reattempt progress;
- Supabase Auth/RLS/private-storage/privacy schema live through migration 0014,
  including frozen evidence, answer analyses, worker/deletion claims,
  processing artifacts, qualified processing queries, and anonymous-privilege
  hardening;
- React/Lovable frontend connected to the real API contract, including auth,
  optional JD, role catalogue, consent, resume, interview, processing, report,
  skill gaps, roadmap, progress, and deletion request pages;
- 99 Python tests, 45 frontend tests, Ruff, ESLint, and production frontend
  build passing.
- guarded real-service E2E passed with a disposable confirmed user, 15 resume
  claims, 12 processed core/follow-up answers, 108 evidence nodes, scorecard,
  progress history, and verified account deletion.

Recorded pending work:

- one real consenting student's recorded attempt plus faculty/evaluator review;
  the server-only worker key is configured locally and never exposed to the
  browser;
- deployment of the FastAPI service and GPU worker to public HTTPS
  infrastructure, followed by updating the production `VITE_API_BASE_URL`;
- real faculty calibration and the consented student/usability study. These are
  human-research tasks and are never fabricated by the software.

## 24. Direct answers to likely viva questions

### Which type of RAG are you using?

> We plan to use graph-guided contextual hybrid RAG. The Evidence Graph provides
> a verified competency or skill-gap context. Each stored question or resource
> has contextual metadata such as role, competency, difficulty, source, and
> review status. PostgreSQL full-text search finds exact terms, while pgvector
> semantic search finds equivalent meanings. We combine both rankings and allow
> only approved records. A local LLM then adapts the selected question or
> organizes the selected resources.

### What is Question RAG, exactly?

> Question RAG means searching our versioned question bank before asking the
> LLM to generate anything. We filter by competency, seniority, difficulty, and
> review status, then combine keyword and semantic search. We load the selected
> question's complete fixed package. If useful, a constrained LLM personalizes
> only its wording with resume or previous-answer context, and code verifies
> that the competency, expected concepts, difficulty, and rubric do not change.
> If no suitable package exists, Question RAG retrieves approved technical
> passages and a question-generation LLM drafts the complete package for
> validation. PostgreSQL, pgvector, and backend code perform the search; the LLM
> operates after retrieval.

### What is Roadmap RAG, exactly?

> The Evidence Graph first identifies a supported skill gap. The system searches
> a separate repository of approved official documentation, exercises, and
> courses using metadata, keywords, and semantic similarity. The LLM receives
> only the retrieved records and organizes them into a time-bounded roadmap.
> Every roadmap item must cite an existing resource ID.

### From where does RAG retrieve?

> RAG retrieves from RoleReady AI's pre-built local collections, not from an
> unrestricted live internet search. We first register and ingest
> licence-compliant O*NET/ESCO role data, selected official technical passages
> or our summaries from sources such as MDN, OWASP, Spring, PostgreSQL, Python,
> Docker, and Git, validated question packages, and verified learning-resource
> records. PostgreSQL and pgvector index those records. RAG searches the
> relevant collection and sends only the retrieved records to the LLM.

### Are all those sources free to download?

> Most are publicly accessible, but free access does not automatically permit
> bulk copying or redistribution. Each source is registered with its URL,
> licence, attribution, version, and permitted use. Open structured sources
> such as O*NET and ESCO can be downloaded under their stated terms. For
> restrictive or unclear documentation, we store metadata, links, citations,
> and our own summaries instead of copying the complete work.

### What is the approved learning-resource collection?

> It is a local structured catalogue of real official documentation,
> open-licensed tutorials, reviewed exercises, safe practical labs,
> mini-project tasks, and reattempt questions. Each record has a resource ID,
> verified URL, publisher, competency, skill, technology, difficulty, learning
> outcomes, estimated time, licence, and review status. Roadmap RAG retrieves
> records matching the exact Evidence Graph gap. The LLM arranges them but
> cannot invent a link.

### Where do interview questions come from?

> They do not come from First Impressions V2. Question-generation RAG retrieves
> relevant context from JD competencies, O*NET/ESCO terminology, CS2023
> learning areas, and official technical documentation. The local LLM
> automatically generates the question, expected concepts, 1-5 rubric, bounded
> follow-ups, and source IDs in JSON. Code validates and stores the result.
> Faculty reviews the fixed research set or representative samples rather than
> manually writing every question.

### Does the LLM generate only expected concepts and a rubric?

> No. If no matching validated package exists, the question-authoring LLM
> drafts the complete package: question, expected concepts, 1-5 rubric, bounded
> follow-ups, reference explanation, and source-to-concept mapping. RAG supplies
> trusted context, deterministic code checks schema and policies, a grounded
> validator checks semantic consistency, and the accepted package is stored.
> If a validated package already exists, the system retrieves it instead.

### Where do the expected concepts and rubric come from?

> They are created with the question before the student answers. Expected
> concepts come from the competency objectives, retrieved official technical
> passages, JD/resume technology context, and required seniority. A stable
> general 1-5 template is converted into question-specific measurable anchors.
> The package is validated and frozen with the interview attempt. During
> evaluation, the LLM applies those stored criteria and may not create a new
> rubric after reading the student's answer.

### What happens if the student does not upload a JD?

> The student must select or enter a target role and seniority. The system
> retrieves that role's standard competency profile and uses resume projects,
> skills, internships, certifications, achievements, and previous answers to
> personalize the interview. If neither a JD nor a confirmed target role is
> available, the interview does not start. The final result is labelled
> role-based readiness rather than JD-specific readiness.

### How is a competency selected?

> The JD is parsed into role, seniority, responsibilities, skills, and tools.
> These terms are normalized using O*NET, ESCO, a local skill dictionary, and
> existing templates. Related skills are grouped into five to eight assessable
> competencies. Initial weights depend on required-versus-preferred status,
> repetition, responsibility importance, and template defaults. Code validates
> the result, and the student confirms it.

### Will it work for every occupation?

> O*NET and ESCO cover many occupations, so the mapping architecture is
> extensible. However, our first validated question, rubric, scoring, and
> resource collection is for IT/software roles. Junior Backend Developer is the
> main research role. An unknown role may receive a JD-derived practice profile,
> but it is labelled unvalidated until domain experts review it.

### Are you using a local LLM or an API?

> The implemented provider is Gemini through a backend-only adapter. Question
> wording uses a validated frozen package, and transcript evaluation uses its
> frozen rubric and reviewed source mapping. External-AI consent is recorded;
> raw video/audio are never sent; resume/JD context is minimized; the provider,
> model, and prompt version are stored. Ollama is not used in the current build
> because it was too slow on the available laptop.

### Does the LLM give the final Technical Readiness score?

> No. The LLM returns criterion-level rubric judgments and timestamped evidence
> in validated JSON. Backend code calculates Technical Readiness using a
> versioned formula. Faculty ratings are required to validate and calibrate the
> LLM-assisted judgments.

### Why use a standard bank and an LLM?

> The bank provides reviewed technical correctness, stable rubrics, and
> reproducibility. The LLM provides controlled JD/resume personalization and
> coverage for new competencies. Retrieval always tries the trusted bank first.

### Why is the Evidence Graph needed?

> It connects the full audit chain from JD requirement to competency, resume
> claim, question, answer timestamp, multimodal evidence, prediction, rubric
> judgment, score, gap, resource, roadmap, and later improvement. RAG uses the
> graph's verified context rather than a vague prompt.

### If RAG and the LLM do the technical work, why use MAG-BERT-ARL?

> They solve different problems. RAG and the constrained LLM work with
> technical text: questions, trusted context, rubric judgments, gaps, and
> roadmap resources. MAG-BERT-ARL is the trained multimodal research component.
> It fuses synchronized BERT text, openSMILE acoustic, and OpenFace visual
> features and predicts the First Impressions interview label. ARL tests whether
> emphasizing difficult training examples improves the selected metrics. Its
> output remains a separate Base Multimodal Interview Signal and does not decide
> technical correctness or readiness.

### Where is SHAP explainability used?

> Gradient SHAP is applied after MAG-BERT-ARL inference. It attributes the base
> multimodal prediction to text, acoustic, and visual inputs and to influential
> words or time intervals. Those attribution records are stored in the Evidence
> Graph and may be shown as a simplified modality/time explanation. SHAP
> explains the multimodal model, not the LLM technical score. Technical scores
> are explained separately using the frozen rubric and transcript evidence.

### Does the system detect confidence or nervousness?

> No validated psychological label is claimed. First Impressions V2 does not
> provide ground-truth nervousness or genuine self-confidence. The product
> reports observable delivery indicators such as speaking pace, pauses, filler
> words, voice-energy consistency, head-movement stability, camera-facing/gaze
> estimate, relevance, and answer structure. `Evidence confidence` means
> reliability of the media and evidence, not student self-confidence.

### When does the student receive presentation feedback?

> Whisper timestamps provide pace, pauses, and filler counts in Stage 7;
> openSMILE provides acoustic observations in Stage 8; OpenFace provides
> descriptive head/gaze observations in Stage 9; the constrained LLM applies a
> fixed relevance and structure rubric in Stage 15; and backend code calculates
> the versioned Presentation/Communication Delivery score in Stage 16. The
> Evidence Graph stores the observations in Stage 18, and the student sees them
> in the separate presentation section of the Stage 22 report.

### Why is offline model development shown?

> It explains where the live MAG-BERT-ARL checkpoint comes from. FI V2 is
> preprocessed, models and ablations are trained, metrics and fairness are
> evaluated, SHAP is checked, and only the selected checkpoint is promoted to
> live inference. This work does not happen during the student's interview.

## 25. Complete architecture presentation script

> The architecture begins with offline preparation. We create a trusted
> knowledge layer from O*NET and ESCO occupation skills, CS2023 learning areas,
> official technical documentation, RAG-grounded LLM-generated questions,
> automatically validated rubrics, faculty review of the fixed research set,
> and reviewed learning resources. Questions and resources are stored
> separately with metadata, source IDs, validation status, and vector
> embeddings.
>
> Separately, the base multimodal model is developed offline using First
> Impressions V2. Whisper creates word-timestamped transcripts, openSMILE
> extracts 88 acoustic values, and OpenFace supplies 709 visual values. These
> modalities are aligned at word level and used to train MAG-BERT and
> MAG-BERT-ARL variants. The selected checkpoint produces only a Base
> Multimodal Interview Signal, not technical readiness or hiring probability.
>
> In the online flow, the student authenticates, gives consent, and uploads a JD
> and resume. Deterministic parsers preserve the original source spans. A local
> LLM converts the extracted text into candidate structured role, seniority,
> skill, project, internship, certification, achievement, and resume-claim
> records. Code verifies each source span, normalizes terms using the skill
> catalogue, rejects unsupported facts, groups skills into assessable
> competencies, validates the weights, and asks the student to confirm the
> profile.
>
> Question retrieval then searches the approved question bank using competency,
> seniority, difficulty, resume context, and review status. Keyword search finds
> exact terms and vector search finds similar meanings. The selected question's
> fixed rubric is loaded. The local LLM may personalize the wording using a
> traceable resume claim or previous answer. If no approved question exists, it
> can generate a schema-validated draft that is clearly marked unreviewed.
>
> During the interview, the adaptive engine asks one core question per
> competency. Each answer enters two parallel pipelines. The technical pipeline
> gives the transcript, fixed rubric, expected concepts, and retrieved official
> context to a constrained LLM, which returns timestamped criterion evidence.
> The multimodal pipeline processes aligned Whisper text, openSMILE acoustic,
> and OpenFace visual features with MAG-BERT-ARL. It produces only a separate
> Base Multimodal Interview Signal. Gradient SHAP attributes that model signal
> to modalities and time spans. Backend code also derives observable delivery
> indicators such as pace, pauses, fillers, voice-energy consistency,
> head-movement stability, and a camera-facing estimate. It calculates
> transparent readiness and communication dimensions while keeping evidence
> confidence separate from student self-confidence.
>
> Every requirement, claim, question, answer, feature, prediction, attribution,
> rubric judgment, and confidence value is connected in the Competency Evidence
> Graph. The graph determines whether evidence is sufficient for a follow-up or
> the next competency. A skill gap is created only when a target exists, the
> evidence-backed score is low, supporting evidence IDs exist, and confidence
> is sufficient.
>
> For an approved gap, graph-guided contextual hybrid RAG searches the separate
> learning-resource repository. Metadata filters remove unapproved or
> unsuitable resources, keyword search finds exact concepts, and vector search
> finds semantic equivalents. The local LLM receives only the retrieved
> resources and organizes them into a cited plan. Unknown resource IDs are
> rejected, and missing resources are reported rather than invented.
>
> The student report separates technical assessment, observable presentation
> and communication feedback, multimodal model attribution, and the roadmap.
> It does not claim nervousness, anxiety, personality, or genuine confidence.
> After studying, the student reattempts the interview. The Evidence Graph
> connects old and new evidence so progress is measured from comparable
> competency evidence. Throughout the system, video remains private, consent
> and provenance are stored, protected attributes are not normal inputs, and no
> ranking or hiring decision is produced.

## 26. Final one-minute answer

> FairHireAI is an evidence-backed placement-readiness system for
> IT/software interview practice. The JD defines the competencies, the resume
> provides claims to verify, and a reviewed question bank supplies the trusted
> questions and rubrics. We retrieve approved questions first and use Gemini
> only for controlled personalization and frozen-rubric transcript evaluation.
> Video answers enter two parallel pipelines: a constrained LLM applies the
> frozen technical rubric to the transcript, while MAG-BERT-ARL processes
> synchronized text, acoustic, and visual features as a separate multimodal
> research signal. Gradient SHAP explains only that model signal, and backend
> code produces observable delivery indicators without claiming nervousness or
> genuine confidence. The Evidence Graph connects every result to its source.
> For verified gaps, graph-guided contextual hybrid RAG combines metadata
> filtering, keyword search, and pgvector semantic search to retrieve approved
> learning resources. The LLM organizes only those resources into a cited
> roadmap, and a reattempt measures improvement. The system supports student
> self-improvement and never makes a hiring decision.

## 27. Final completed product and outputs

This is the target output after the entire planned project is implemented and
validated. It is separate from the truthful current status in Section 23.

### 27.1 Working student software

The completed product is a usable web application with private local/GPU media
processing and a consent-gated backend Gemini integration:

```text
student account and consent
    -> upload JD and resume or confirm a selected role
    -> confirm extracted role and competency profile
    -> complete an adaptive video interview
    -> receive an evidence-backed report
    -> complete a verified learning roadmap
    -> take a different reattempt
    -> view evidence-backed progress
```

The frontend may be designed using Lovable and exported as React, but it must
call the real FastAPI, model, RAG, and database services. It must not display
dummy model outputs.

### 27.2 Adaptive interview output

The completed interview:

- selects questions using the JD or confirmed role;
- personalizes questions using resume skills, projects, internships,
  certifications, and achievements;
- remembers earlier answers;
- asks bounded follow-ups for missing or unclear evidence;
- covers important competencies without unnecessary repetition;
- freezes every question package used in an attempt.

Example:

```text
Earlier, you mentioned JWT authentication.
How would you manage authentication and authorization across microservices?
```

### 27.3 Final student report

The report begins with:

```text
Assessment basis: uploaded JD or confirmed role
Target role: Junior Backend Developer
Seniority: Junior
Competencies assessed: 6
Questions answered: 8
Evidence confidence: high
```

It presents versioned:

```text
Technical Readiness
Communication Clarity / Presentation Delivery
Interview Response Quality
Placement Readiness
```

Every result retains its formula version, competency coverage, evidence
confidence, and insufficient-evidence warnings.

### 27.4 Competency evidence and skill gaps

For every competency, the report shows:

```text
score and confidence
satisfied and missing rubric criteria
timestamped transcript evidence
core-question and follow-up results
explanation of the judgment
```

Example:

```text
Competency: API Security
Demonstrated: JWT authentication
Missing: object-level authorization
Evidence: "I would validate the JWT before returning the orders."
Gap status: confirmed after bounded follow-up
Gap confidence: 0.87
```

Poor media or transcription quality produces `insufficient_evidence` and a
re-recording request, not a false weakness.

### 27.5 Presentation and communication feedback

The student sees:

```text
speaking pace
number and duration of pauses
context-checked filler words
voice-energy consistency
head-movement stability
camera-facing/gaze estimate
answer relevance
answer structure
Presentation/Communication Delivery score
```

The report does not claim nervousness, anxiety, genuine confidence, personality,
emotion, or hiring probability.

### 27.6 Multimodal model and SHAP output

MAG-BERT-ARL produces a separate research/supporting output:

```text
Base Multimodal Interview Signal
model-evidence availability
Gradient SHAP attribution by modality
influential words and time intervals
```

Example:

```text
Base Multimodal Interview Signal: 0.64
Approximate model influence: text 61%, audio 26%, visual 13%
Influential interval: 12.4-15.1 seconds
```

SHAP explains the MAG-BERT-ARL prediction only. Rubric criteria and transcript
evidence separately explain the technical score.

### 27.7 Personalized roadmap output

For every confirmed skill gap, graph-guided Roadmap RAG retrieves approved
resources. The roadmap LLM arranges only those records:

```text
verified title, canonical URL, resource ID, and publisher
difficulty, estimated time, and learning outcome
practical completion task
different reattempt question
```

Example:

```text
Day 1: review authentication fundamentals
Day 2: learn authentication versus authorization
Day 3: study object-level authorization
Day 4: implement and test an ownership check
Day 5: complete a different API-security reattempt
```

Backend code rejects unknown resource IDs and invented URLs.

### 27.8 Reattempt and progress output

A different validated question assesses the same competency after study:

```text
Before roadmap: object-level authorization = 1/5
After roadmap:  object-level authorization = 4/5
Progress status: improved
```

Clicking a roadmap item as completed does not prove learning. Progress requires
new comparable competency evidence.

### 27.9 Completed technical system

The working system includes:

- React/Lovable student interface;
- FastAPI backend;
- PostgreSQL and pgvector;
- Question RAG and Roadmap RAG;
- Gemini backend provider with schema-constrained prompts and explicit consent;
- FFmpeg and Whisper transcription;
- openSMILE and OpenFace feature extraction;
- MAG-BERT and MAG-BERT-ARL inference;
- Gradient SHAP;
- Competency Evidence Graph;
- background job worker;
- private media and model storage;
- versioned scoring, provenance, consent, and audit records.

### 27.10 Trained ML and research artefacts

The completed research package contains:

```text
validated First Impressions V2 manifest
processed text/audio/visual features and BERT cache
trained MAG-BERT and MAG-BERT-ARL checkpoints
training configurations and histories
validation/test metrics
text/audio/visual ablations
MAG-BERT versus ARL comparison
fairness analysis
Gradient SHAP examples
reproducibility metadata
```

The study compares at least text-only BERT, MAG-BERT, and MAG-BERT-ARL. It also
evaluates question/resource retrieval, LLM-to-human rubric agreement, roadmap
relevance, and student usability.

### 27.11 Final submission deliverables

1. Working local software product.
2. Real trained checkpoints and inference pipeline.
3. Two functioning RAG pipelines.
4. Local constrained LLM integration.
5. Auditable Competency Evidence Graph.
6. Evidence-backed student report.
7. Verified personalized roadmaps.
8. Reattempt-based progress tracking.
9. Model, retrieval, scoring, and usability results.
10. Research paper, architecture diagram, presentation, and documentation.

The final product is:

> An evidence-backed, role-aware adaptive interview system that assesses
> technical answers, provides observable presentation feedback, explains its
> judgments, identifies verified competency gaps, retrieves approved learning
> resources, and measures improvement through reattempts without ranking
> candidates or making hiring decisions.
