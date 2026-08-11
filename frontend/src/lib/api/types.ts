// Authoritative FastAPI response shapes for FairHireAI.
// Kept strict for the fields the UI reads; extra fields tolerated via [k: string]: unknown.

export interface HealthResponse {
  status?: string;
  [k: string]: unknown;
}

// ---------- Role template (GET /api/v1/roles/junior-backend-developer) ----------

export interface RoleQuestion {
  question_id: string;
  prompt: string;
  expected_evidence: string[];
  [k: string]: unknown;
}

export interface RoleFollowUp {
  question_id: string;
  trigger_criterion: string;
  prompt: string;
  [k: string]: unknown;
}

export interface RoleCompetency {
  competency_id: string;
  name: string;
  base_weight: number;
  description: string;
  approved_skill_terms: string[];
  rubric_criteria: string[];
  core_question: RoleQuestion;
  follow_ups: RoleFollowUp[];
  [k: string]: unknown;
}

export interface RoleTemplate {
  schema_version: string;
  role_id: string;
  display_name: string;
  template_version: string;
  review_status: string;
  supported_title_terms: string[];
  supported_seniority_terms: string[];
  unsupported_title_terms: string[];
  unsupported_seniority_terms: string[];
  competencies: RoleCompetency[];
  [k: string]: unknown;
}

// ---------- Role catalog (GET /api/v1/roles) ----------

export interface RoleSummary {
  role_id: string;
  display_name: string;
  template_version: string;
  review_status: string;
  supported_title_terms: string[];
  competency_names: string[];
  [k: string]: unknown;
}

// ---------- Role detection (POST /api/v1/roles/detect) ----------

export type RoleDetectionStatus = "detected" | "unsupported_role" | "unsupported_seniority";

export interface RoleDetectionRequest {
  job_description: string;
  selected_role_id?: string | null;
}

export interface RoleDetectionResponse {
  status: RoleDetectionStatus;
  mapping_version: string;
  role_id?: string;
  display_name?: string;
  role_template_version?: string;
  role_review_status?: string;
  confidence: number;
  reason: string;
  matched_title_terms: string[];
  matched_seniority_terms: string[];
  matched_skills_by_competency: Record<string, string[]>;
  competency_weights: Record<string, number>;
  [k: string]: unknown;
}

// ---------- Documents ----------

export type DocumentKind = "pdf" | "docx" | "text";

export interface ExtractedPage {
  page: number | null;
  start_character: number;
  end_character: number;
  text: string;
}

export interface ExtractedDocument {
  schema_version: "document-text-v1";
  filename: string;
  document_kind: DocumentKind;
  media_type: string;
  sha256: string;
  extractor_name: string;
  extractor_version: "1.0.0";
  text: string;
  pages: ExtractedPage[];
  [k: string]: unknown;
}

export interface JobDescriptionUploadResponse {
  document: ExtractedDocument;
  role_mapping: RoleDetectionResponse;
  [k: string]: unknown;
}

export type ResumeClaimType = "skill" | "project" | "internship" | "certification" | "achievement";

export interface ResumeClaimSource {
  page: number | null;
  start_character: number;
  end_character: number;
  source_text: string;
}

export interface ResumeClaim {
  claim_id: string;
  claim_type: ResumeClaimType;
  normalized_text: string;
  source: ResumeClaimSource;
  confidence: number;
  normalized_skills: string[];
  [k: string]: unknown;
}

export interface ResumeEvidence {
  schema_version: "resume-evidence-v1";
  document_sha256: string;
  extractor_name: string;
  extractor_version: string;
  claims: ResumeClaim[];
  [k: string]: unknown;
}

export interface ResumeUploadResponse {
  document: ExtractedDocument;
  evidence: ResumeEvidence;
  [k: string]: unknown;
}

// ---------- Attempts ----------

export interface AttemptJobDescription {
  private_jd_storage_key: string;
  jd_sha256: string;
  extracted_job_description: string;
}

export interface CreateAttemptRequest {
  parent_attempt_id?: string | null;
  /** Any role_id from the reviewed backend catalog. */
  role_id: string;
  confirm_role: true;
  job_description: AttemptJobDescription | null;
}

export type AssessmentProfileSource = "approved_role" | "job_description";

export type AttemptStatus =
  "draft" | "role_confirmed" | "interviewing" | "processing" | "completed" | "failed" | "cancelled";

export interface AttemptRecord {
  id: string;
  user_id: string;
  parent_attempt_id: string | null;
  role_id: string;
  role_template_version: string;
  assessment_profile_source: AssessmentProfileSource;
  assessment_profile_version: string;
  status: AttemptStatus;
  competency_weights: Record<string, number>;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  [k: string]: unknown;
}

export interface TransitionRequest {
  next_status: AttemptStatus;
}

// ---------- Privacy: consents ----------

export type ConsentType =
  | "privacy_notice"
  | "resume_processing"
  | "interview_recording"
  | "external_ai_processing"
  | "research_evaluation";

export type ConsentSource = "web" | "mobile";

export type ConsentMetadata = Record<string, string | number | boolean | null>;

export interface ConsentRequest {
  attempt_id?: string | null;
  consent_type: ConsentType;
  policy_version: string;
  granted: boolean;
  source: ConsentSource;
  metadata?: ConsentMetadata;
}

export interface ConsentRecord {
  id: string;
  user_id: string;
  attempt_id: string | null;
  consent_type: ConsentType;
  policy_version: string;
  granted: boolean;
  source: ConsentSource;
  metadata?: ConsentMetadata;
  occurred_at: string;
  [k: string]: unknown;
}

// ---------- Privacy: deletion requests ----------

export type DeletionScope = "account" | "attempt";

export type DeletionRequest =
  { scope: "account"; attempt_id: null } | { scope: "attempt"; attempt_id: string };

export type DeletionStatus = "requested" | "processing" | "completed" | "failed";

export interface DeletionRecord {
  id: string;
  user_id: string;
  scope: DeletionScope;
  attempt_id: string | null;
  status: DeletionStatus;
  requested_at: string;
  completed_at: string | null;
  error_code: string | null;
  [k: string]: unknown;
}

// ---------- Attach resume (POST /attempts/{id}/resume) ----------

export interface AttachResumeRequest {
  private_resume_storage_key: string;
  mime_type: string;
  /** Exact ResumeEvidence returned by POST /documents/resume. */
  evidence: ResumeEvidence;
}

export type ExtractionStatus = "pending" | "completed" | "failed" | string;

export interface AttachResumeResponse {
  resume_document_id: string;
  attempt_id: string;
  claim_count: number;
  extraction_status: ExtractionStatus;
  [k: string]: unknown;
}

// ---------- Interview questions & answers ----------

export interface PersistedInterviewQuestion {
  id: string;
  attempt_id: string;
  question_template_id: string;
  competency_id: string;
  prompt_snapshot: string;
  is_follow_up: boolean;
  sequence_number: number;
  selection_reason: string | null;
  created_at: string;
  [k: string]: unknown;
}

export interface NextQuestionResponse {
  question: PersistedInterviewQuestion | null;
  awaiting_answer: boolean;
  message: string | null;
  [k: string]: unknown;
}

export interface AnswerSubmission {
  question_id: string;
  private_video_storage_key: string;
  video_sha256: string;
  duration_seconds: number;
}

export type AnswerProcessingStatus = "pending" | "queued" | "running" | "complete" | "failed";

export interface AnswerRecord {
  id: string;
  attempt_id: string;
  question_id: string;
  private_video_storage_key: string;
  video_sha256: string;
  duration_seconds: number;
  processing_status: AnswerProcessingStatus;
  submitted_at: string;
  processed_at: string | null;
  [k: string]: unknown;
}

// ---------- Processing (POST /attempts/{id}/process → 202) ----------

export interface StartProcessingResponse {
  attempt_id: string;
  started: true;
  queued_job_count: number;
  message: string;
  [k: string]: unknown;
}

// ---------- Processing jobs (returned directly as an array) ----------

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled" | string;

export interface ProcessingJobView {
  id: string;
  attempt_id: string;
  answer_id: string | null;
  job_type: string;
  status: JobStatus;
  stage: string | null;
  attempt_count: number;
  max_attempts: number;
  error_code: string | null;
  error_detail: string | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
  [k: string]: unknown;
}

// ---------- Report (new nested shape) ----------

export interface EvidenceNode {
  id: string;
  kind: string;
  label?: string;
  competency_id?: string;
  transcript_span?: { text: string; start_ms?: number; end_ms?: number };
  question?: { id: string; prompt_snapshot: string };
  resume_claim_id?: string;
  confidence?: number | null;
  signal_quality?: string | null;
  model_reference?: string | null;
  skill_gap?: {
    current_score?: number | null;
    target_score?: number | null;
    severity?: number | null;
    rationale?: string | null;
  } | null;
  [k: string]: unknown;
}

export interface EvidenceEdge {
  from: string;
  to: string;
  relation?: string;
  weight?: number;
  [k: string]: unknown;
}

export interface ReportCompetencyScore {
  competency_id: string;
  name: string;
  score: number | null;
  weight: number;
  evidence_node_ids?: string[];
  insufficiency_reasons?: string[];
  [k: string]: unknown;
}

export interface Scorecard {
  placement_readiness: number | null;
  insufficiency_reasons?: string[];
  base_multimodal_interview_signal?: number | null;
  delivery_signal?: {
    words_per_minute?: number;
    pause_count?: number;
    filler_rate?: number;
    pace_and_filler_quality?: number;
    voice_energy_consistency?: number;
    head_stability?: number;
    camera_facing_estimate?: number;
    transcript_confidence?: number;
    visual_success_rate?: number;
    note?: string;
  } | null;
  competencies?: ReportCompetencyScore[];
  [k: string]: unknown;
}

export interface RoadmapItem {
  id: string;
  competency_id?: string;
  title: string;
  description?: string;
  reviewer_approved: true;
  resources: Array<{
    id: string;
    title: string;
    url: string;
    provider?: string;
    [k: string]: unknown;
  }>;
  [k: string]: unknown;
}

export interface ReportResponse {
  attempt_id: string;
  status: AttemptStatus;
  scorecard: Scorecard | null;
  evidence_nodes: EvidenceNode[];
  evidence_edges: EvidenceEdge[];
  roadmap_items: RoadmapItem[];
  message: string | null;
  [k: string]: unknown;
}

// ---------- Progress ----------

export interface ProgressAttempt {
  attempt_id: string;
  role_id: string;
  completed_at: string;
  placement_readiness: number | null;
  competency_scores: Array<{ competency_id: string; name?: string; score: number | null }>;
  [k: string]: unknown;
}

export interface ProgressResponse {
  attempts: ProgressAttempt[];
  message: string | null;
  [k: string]: unknown;
}

// ---------- Capabilities ----------

export interface CapabilitiesResponse {
  backend: "ready";
  database_configured: boolean;
  role_catalog_ready: boolean;
  external_llm: "ready" | "not_configured";
  knowledge_embeddings: "gemini-embedding-2-384";
  model_inference: "ready" | "awaiting_trained_checkpoint";
  report_generation: "ready" | "awaiting_trained_checkpoint";
  worker_execution: "ready" | "server_secret_required";
  message: string;
  [k: string]: unknown;
}
