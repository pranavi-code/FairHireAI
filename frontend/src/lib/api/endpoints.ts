import { apiRequest } from "./client";
import type {
  AnswerRecord,
  AnswerSubmission,
  AttachResumeRequest,
  AttachResumeResponse,
  AttemptJobDescription,
  AttemptRecord,
  CapabilitiesResponse,
  ConsentRecord,
  ConsentRequest,
  CreateAttemptRequest,
  DeletionRecord,
  DeletionRequest,
  ExtractedDocument,
  HealthResponse,
  JobDescriptionUploadResponse,
  NextQuestionResponse,
  ProcessingJobView,
  ProgressResponse,
  ReportResponse,
  ResumeClaim,
  ResumeClaimType,
  ResumeUploadResponse,
  RoleDetectionRequest,
  RoleDetectionResponse,
  RoleSummary,
  RoleTemplate,
  StartProcessingResponse,
  TransitionRequest,
} from "./types";

// ---------- Current endpoints ----------

export const healthApi = {
  get: () => apiRequest<HealthResponse>("/api/v1/health", { auth: false }),
};

export const capabilitiesApi = {
  get: () => apiRequest<CapabilitiesResponse>("/api/v1/capabilities", { auth: false }),
};

export const rolesApi = {
  list: () => apiRequest<RoleSummary[]>("/api/v1/roles", { auth: false }),
  get: (roleId: string) =>
    apiRequest<RoleTemplate>(`/api/v1/roles/${encodeURIComponent(roleId)}`, { auth: false }),
  detect: (payload: RoleDetectionRequest) =>
    apiRequest<RoleDetectionResponse>("/api/v1/roles/detect", {
      method: "POST",
      body: payload,
      auth: false,
    }),
};

function documentForm(file: File, extras?: Record<string, string>): FormData {
  const fd = new FormData();
  fd.append("file", file, file.name);
  if (extras) for (const [k, v] of Object.entries(extras)) fd.append(k, v);
  return fd;
}

export const documentsApi = {
  /**
   * Upload a JD. When `selectedRoleId` is provided, the backend scopes the
   * extraction response's role mapping to that role. `roles/detect` is still
   * available for a second-pass reconciliation.
   */
  jobDescription: (file: File, selectedRoleId?: string | null) =>
    apiRequest<JobDescriptionUploadResponse>("/api/v1/documents/job-description", {
      method: "POST",
      formData: documentForm(
        file,
        selectedRoleId ? { selected_role_id: selectedRoleId } : undefined,
      ),
    }),
  resume: (file: File) =>
    apiRequest<ResumeUploadResponse>("/api/v1/documents/resume", {
      method: "POST",
      formData: documentForm(file),
    }),
};

export const attemptsApi = {
  list: () => apiRequest<AttemptRecord[]>("/api/v1/attempts"),
  create: (payload: CreateAttemptRequest) =>
    apiRequest<AttemptRecord>("/api/v1/attempts", { method: "POST", body: payload }),
  get: (attemptId: string) => apiRequest<AttemptRecord>(`/api/v1/attempts/${attemptId}`),
  transition: (attemptId: string, next: TransitionRequest) =>
    apiRequest<AttemptRecord>(`/api/v1/attempts/${attemptId}/transitions`, {
      method: "POST",
      body: next,
    }),

  // Journey endpoints
  attachResume: (attemptId: string, payload: AttachResumeRequest) =>
    apiRequest<AttachResumeResponse>(`/api/v1/attempts/${attemptId}/resume`, {
      method: "POST",
      body: payload,
    }),
  nextQuestion: (attemptId: string, signal?: AbortSignal) =>
    apiRequest<NextQuestionResponse>(`/api/v1/attempts/${attemptId}/next-question`, { signal }),
  submitAnswer: (attemptId: string, payload: AnswerSubmission) =>
    apiRequest<AnswerRecord>(`/api/v1/attempts/${attemptId}/answers`, {
      method: "POST",
      body: payload,
    }),
  startProcessing: (attemptId: string) =>
    apiRequest<StartProcessingResponse>(`/api/v1/attempts/${attemptId}/process`, {
      method: "POST",
    }),
  jobs: (attemptId: string, signal?: AbortSignal) =>
    apiRequest<ProcessingJobView[]>(`/api/v1/attempts/${attemptId}/jobs`, { signal }),
  report: (attemptId: string) => apiRequest<ReportResponse>(`/api/v1/attempts/${attemptId}/report`),
  reattempt: (attemptId: string) =>
    apiRequest<AttemptRecord>(`/api/v1/attempts/${attemptId}/reattempt`, { method: "POST" }),
};

export const progressApi = {
  get: () => apiRequest<ProgressResponse>("/api/v1/progress"),
};

export const privacyApi = {
  saveConsent: (payload: ConsentRequest) =>
    apiRequest<ConsentRecord>("/api/v1/privacy/consents", { method: "POST", body: payload }),
  requestDeletion: (payload: DeletionRequest) =>
    apiRequest<DeletionRecord>("/api/v1/privacy/deletion-requests", {
      method: "POST",
      body: payload,
    }),
};

/**
 * The `trained_checkpoint_required` conflict code from POST /process indicates
 * the ML checkpoint has not been published yet. Callers should render an honest
 * unavailable state rather than fake processing.
 */
export const TRAINED_CHECKPOINT_REQUIRED_CODE = "trained_checkpoint_required";

// ---------- Helper builders (typed, tested) ----------

export const POLICY_VERSION = "v1";

/**
 * Map the actual document-text-v1 response plus the separate private storage
 * upload result into the exact JD object accepted by POST /api/v1/attempts.
 */
export function buildAttemptJobDescriptionFromDocument(input: {
  document: ExtractedDocument;
  private_jd_storage_key: string;
}): AttemptJobDescription {
  return {
    private_jd_storage_key: input.private_jd_storage_key,
    jd_sha256: input.document.sha256,
    extracted_job_description: input.document.text,
  };
}

/**
 * Build a strict CreateAttempt payload. `role_id` must come from the reviewed
 * backend role catalog (GET /api/v1/roles). Rejects a JD if role detection did
 * not return `status: "detected"` — never silently falls back.
 */
export function buildCreateAttemptPayload(input: {
  roleId: string;
  parentAttemptId?: string | null;
  jd?: {
    detection: RoleDetectionResponse;
    private_jd_storage_key: string;
    jd_sha256: string;
    extracted_job_description: string;
  } | null;
}): CreateAttemptRequest {
  if (!input.roleId || typeof input.roleId !== "string") {
    throw new Error("role_id is required and must come from the backend role catalog");
  }
  const base: CreateAttemptRequest = {
    role_id: input.roleId,
    confirm_role: true,
    job_description: null,
  };
  if (input.parentAttemptId) base.parent_attempt_id = input.parentAttemptId;
  if (input.jd === undefined || input.jd === null) return base;
  if (input.jd.detection.status !== "detected") {
    throw new Error(
      `Unsupported job description: backend returned status "${input.jd.detection.status}". Attempt creation is blocked.`,
    );
  }
  // If the backend detected a different role than the student selected, block —
  // this is a JD/role conflict the student must resolve explicitly.
  if (input.jd.detection.role_id && input.jd.detection.role_id !== input.roleId) {
    throw new Error(
      `Job description maps to "${input.jd.detection.role_id}" but the selected role is "${input.roleId}". Attempt creation is blocked.`,
    );
  }
  const { private_jd_storage_key, jd_sha256, extracted_job_description } = input.jd;
  if (!/^[a-f0-9]{64}$/.test(jd_sha256)) {
    throw new Error("jd_sha256 must be 64-character lowercase hexadecimal");
  }
  if (!private_jd_storage_key || private_jd_storage_key.startsWith("roleready-documents/")) {
    throw new Error(
      "private_jd_storage_key must be the bucket-relative key beginning `<user-id>/attempts/...`, not prefixed with the bucket name",
    );
  }
  if (!/^[^/]+\/attempts\//.test(private_jd_storage_key)) {
    throw new Error("private_jd_storage_key must begin `<user-id>/attempts/...`");
  }
  if (!extracted_job_description || extracted_job_description.length < 40) {
    throw new Error("extracted_job_description must be the backend-returned text (>=40 chars)");
  }
  return {
    ...base,
    job_description: {
      private_jd_storage_key,
      jd_sha256,
      extracted_job_description,
    },
  };
}

// ---------- Resume grouping (client-side display only) ----------

export type GroupedResumeClaims = Record<ResumeClaimType, ResumeClaim[]>;

export const RESUME_CLAIM_TYPES: ResumeClaimType[] = [
  "skill",
  "project",
  "internship",
  "certification",
  "achievement",
];

export const LOW_CONFIDENCE_THRESHOLD = 0.6;

/** Group the flat `evidence.claims` array by `claim_type` for display only. */
export function groupResumeClaims(claims: ResumeClaim[]): GroupedResumeClaims {
  const out: GroupedResumeClaims = {
    skill: [],
    project: [],
    internship: [],
    certification: [],
    achievement: [],
  };
  for (const c of claims) {
    if (c && out[c.claim_type]) out[c.claim_type].push(c);
  }
  return out;
}

export function isLowConfidence(claim: ResumeClaim): boolean {
  return typeof claim.confidence === "number" && claim.confidence < LOW_CONFIDENCE_THRESHOLD;
}

/** Build a consent payload for a single consent type. */
export function buildConsentPayload(input: {
  consent_type: ConsentRequest["consent_type"];
  granted: boolean;
  policy_version?: string;
  attempt_id?: string | null;
  metadata?: ConsentRequest["metadata"];
}): ConsentRequest {
  return {
    consent_type: input.consent_type,
    policy_version: input.policy_version ?? POLICY_VERSION,
    granted: input.granted,
    source: "web",
    attempt_id: input.attempt_id ?? null,
    ...(input.metadata ? { metadata: input.metadata } : {}),
  };
}

/** Build a deletion payload. Attempt scope requires a non-empty attempt id. */
export function buildDeletionPayload(
  input: { scope: "account" } | { scope: "attempt"; attempt_id: string },
): DeletionRequest {
  if (input.scope === "account") return { scope: "account", attempt_id: null };
  if (!input.attempt_id) throw new Error("attempt scope requires an attempt_id");
  return { scope: "attempt", attempt_id: input.attempt_id };
}

// ---------- Document size limits (mirrors backend MAX_DOCUMENT_BYTES) ----------

/** Backend MAX_DOCUMENT_BYTES: 5 MiB for JD and resume uploads. */
export const MAX_DOCUMENT_BYTES = 5 * 1024 * 1024;

export function formatMebibytes(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

/**
 * Validate an uploaded document against the shared 5 MiB backend limit.
 * Returns an actionable error message when rejected, or null when accepted.
 */
export function validateDocumentSize(file: { name: string; size: number }): string | null {
  if (file.size > MAX_DOCUMENT_BYTES) {
    return `${file.name} is ${formatMebibytes(file.size)}. The backend limit is ${formatMebibytes(
      MAX_DOCUMENT_BYTES,
    )}. Please upload a smaller file.`;
  }
  return null;
}
