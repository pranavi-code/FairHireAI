import { describe, expect, it, vi, afterEach } from "vitest";
import {
  buildAttemptJobDescriptionFromDocument,
  buildConsentPayload,
  buildCreateAttemptPayload,
  buildDeletionPayload,
  groupResumeClaims,
  isLowConfidence,
  LOW_CONFIDENCE_THRESHOLD,
  MAX_DOCUMENT_BYTES,
  POLICY_VERSION,
  privacyApi,
  validateDocumentSize,
} from "@/lib/api/endpoints";

import { ApiError, parseFastApiDetail } from "@/lib/api/errors";
import type {
  AnswerRecord,
  ExtractedDocument,
  ProcessingJobView,
  ResumeClaim,
  ResumeEvidence,
  RoleDetectionResponse,
  StartProcessingResponse,
} from "@/lib/api/types";

const SHA = "a".repeat(64);
const REAL_KEY = "11111111-1111-1111-1111-111111111111/attempts/temp-abc/job.pdf";
const REAL_JD = "We are hiring a Junior Backend Developer with Python, FastAPI and SQL experience.";

function detection(status: RoleDetectionResponse["status"]): RoleDetectionResponse {
  return {
    status,
    mapping_version: "m-1",
    role_id: "junior_backend_developer",
    display_name: "Junior Backend Developer",
    role_template_version: "t-1",
    role_review_status: "approved",
    confidence: 0.9,
    reason: "ok",
    matched_title_terms: [],
    matched_seniority_terms: [],
    matched_skills_by_competency: {},
    competency_weights: {},
  };
}

function extractedDoc(): ExtractedDocument {
  return {
    schema_version: "document-text-v1",
    filename: "job.pdf",
    document_kind: "pdf",
    media_type: "application/pdf",
    sha256: SHA,
    extractor_name: "pdf",
    extractor_version: "1.0.0",
    text: REAL_JD,
    pages: [{ page: 1, start_character: 0, end_character: REAL_JD.length, text: REAL_JD }],
  };
}

const ROLE = "junior_backend_developer";

describe("buildCreateAttemptPayload", () => {
  it("requires a role_id from the backend catalog", () => {
    // @ts-expect-error missing roleId
    expect(() => buildCreateAttemptPayload({})).toThrow(/role_id/);
  });

  it("builds the no-JD payload exactly per contract, honouring the selected role", () => {
    expect(buildCreateAttemptPayload({ roleId: ROLE })).toEqual({
      role_id: ROLE,
      confirm_role: true,
      job_description: null,
    });
    expect(buildCreateAttemptPayload({ roleId: "junior_data_analyst", jd: null })).toEqual({
      role_id: "junior_data_analyst",
      confirm_role: true,
      job_description: null,
    });
  });

  it("includes parent_attempt_id when provided", () => {
    const p = buildCreateAttemptPayload({ roleId: ROLE, parentAttemptId: "att-1" });
    expect(p.parent_attempt_id).toBe("att-1");
  });

  it("uses document.text and document.sha256 with an independently supplied bucket-relative key", () => {
    const doc = extractedDoc();
    const jd = buildAttemptJobDescriptionFromDocument({
      document: doc,
      private_jd_storage_key: REAL_KEY,
    });
    expect(jd).toEqual({
      private_jd_storage_key: REAL_KEY,
      jd_sha256: doc.sha256,
      extracted_job_description: doc.text,
    });
    const p = buildCreateAttemptPayload({
      roleId: ROLE,
      jd: { detection: detection("detected"), ...jd },
    });
    expect(p.job_description).toEqual({
      private_jd_storage_key: REAL_KEY,
      jd_sha256: SHA,
      extracted_job_description: REAL_JD,
    });
    expect(REAL_JD.length).toBeGreaterThanOrEqual(40);
  });

  it("blocks a JD whose detected role differs from the selected role", () => {
    const det = detection("detected");
    det.role_id = "junior_frontend_developer";
    expect(() =>
      buildCreateAttemptPayload({
        roleId: ROLE,
        jd: {
          detection: det,
          private_jd_storage_key: REAL_KEY,
          jd_sha256: SHA,
          extracted_job_description: REAL_JD,
        },
      }),
    ).toThrow(/blocked/i);
  });

  it("blocks unsupported_role and never falls back to a no-JD payload", () => {
    expect(() =>
      buildCreateAttemptPayload({
        roleId: ROLE,
        jd: {
          detection: detection("unsupported_role"),
          private_jd_storage_key: REAL_KEY,
          jd_sha256: SHA,
          extracted_job_description: REAL_JD,
        },
      }),
    ).toThrow(/unsupported/i);
  });

  it("blocks unsupported_seniority and never falls back to a no-JD payload", () => {
    expect(() =>
      buildCreateAttemptPayload({
        roleId: ROLE,
        jd: {
          detection: detection("unsupported_seniority"),
          private_jd_storage_key: REAL_KEY,
          jd_sha256: SHA,
          extracted_job_description: REAL_JD,
        },
      }),
    ).toThrow(/unsupported/i);
  });

  it("rejects a storage key prefixed with the bucket name", () => {
    expect(() =>
      buildCreateAttemptPayload({
        roleId: ROLE,
        jd: {
          detection: detection("detected"),
          private_jd_storage_key: `roleready-documents/${REAL_KEY}`,
          jd_sha256: SHA,
          extracted_job_description: REAL_JD,
        },
      }),
    ).toThrow(/bucket-relative/i);
  });

  it("rejects a storage key that is not user-scoped", () => {
    expect(() =>
      buildCreateAttemptPayload({
        roleId: ROLE,
        jd: {
          detection: detection("detected"),
          private_jd_storage_key: "not-user-scoped.pdf",
          jd_sha256: SHA,
          extracted_job_description: REAL_JD,
        },
      }),
    ).toThrow(/attempts/);
  });

  it("rejects a too-short extracted_job_description", () => {
    expect(() =>
      buildCreateAttemptPayload({
        roleId: ROLE,
        jd: {
          detection: detection("detected"),
          private_jd_storage_key: REAL_KEY,
          jd_sha256: SHA,
          extracted_job_description: "short",
        },
      }),
    ).toThrow(/40 chars/);
  });

  it("throws when jd_sha256 is not lowercase hex 64", () => {
    expect(() =>
      buildCreateAttemptPayload({
        roleId: ROLE,
        jd: {
          detection: detection("detected"),
          private_jd_storage_key: REAL_KEY,
          jd_sha256: "NOTHEX",
          extracted_job_description: REAL_JD,
        },
      }),
    ).toThrow(/jd_sha256/);
  });
});

describe("groupResumeClaims", () => {
  it("groups a flat backend claims array by claim_type", () => {
    const claims: ResumeClaim[] = [
      {
        claim_id: "c1",
        claim_type: "skill",
        normalized_text: "Python",
        source: { page: 1, start_character: 0, end_character: 6, source_text: "Python" },
        confidence: 0.9,
        normalized_skills: ["python"],
      },
      {
        claim_id: "c2",
        claim_type: "project",
        normalized_text: "Payments service",
        source: {
          page: 2,
          start_character: 10,
          end_character: 26,
          source_text: "Payments service",
        },
        confidence: 0.55,
        normalized_skills: [],
      },
      {
        claim_id: "c3",
        claim_type: "skill",
        normalized_text: "SQL",
        source: { page: 1, start_character: 20, end_character: 23, source_text: "SQL" },
        confidence: 0.8,
        normalized_skills: ["sql"],
      },
    ];
    const grouped = groupResumeClaims(claims);
    expect(grouped.skill.map((c) => c.claim_id)).toEqual(["c1", "c3"]);
    expect(grouped.project.map((c) => c.claim_id)).toEqual(["c2"]);
    expect(grouped.internship).toEqual([]);
    expect(grouped.certification).toEqual([]);
    expect(grouped.achievement).toEqual([]);
    expect(isLowConfidence(claims[1])).toBe(true);
    expect(isLowConfidence(claims[0])).toBe(false);
    expect(LOW_CONFIDENCE_THRESHOLD).toBe(0.6);
  });

  it("works against a real ResumeEvidence shape with only a flat claims array", () => {
    const evidence: ResumeEvidence = {
      schema_version: "resume-evidence-v1",
      document_sha256: SHA,
      extractor_name: "pdf",
      extractor_version: "1.0.0",
      claims: [
        {
          claim_id: "a1",
          claim_type: "achievement",
          normalized_text: "Won ACM regional",
          source: {
            page: null,
            start_character: 0,
            end_character: 16,
            source_text: "Won ACM regional",
          },
          confidence: 0.95,
          normalized_skills: [],
        },
      ],
    };
    const grouped = groupResumeClaims(evidence.claims);
    expect(grouped.achievement).toHaveLength(1);
  });
});

describe("buildConsentPayload", () => {
  it("posts exactly the contract shape (no categories)", () => {
    const payload = buildConsentPayload({
      consent_type: "privacy_notice",
      granted: true,
    });
    expect(payload).toEqual({
      consent_type: "privacy_notice",
      policy_version: POLICY_VERSION,
      granted: true,
      source: "web",
      attempt_id: null,
    });
    expect(payload).not.toHaveProperty("categories");
  });

  it("supports research_evaluation as independent", () => {
    const p = buildConsentPayload({
      consent_type: "research_evaluation",
      granted: false,
      attempt_id: "att-1",
      metadata: { origin: "settings" },
    });
    expect(p.consent_type).toBe("research_evaluation");
    expect(p.attempt_id).toBe("att-1");
    expect(p.metadata).toEqual({ origin: "settings" });
    expect(p.granted).toBe(false);
  });
});

describe("buildDeletionPayload", () => {
  it("account scope forces attempt_id null (no reason field)", () => {
    const p = buildDeletionPayload({ scope: "account" });
    expect(p).toEqual({ scope: "account", attempt_id: null });
    expect(p).not.toHaveProperty("reason");
  });

  it("attempt scope requires a non-empty attempt_id", () => {
    expect(() => buildDeletionPayload({ scope: "attempt", attempt_id: "" })).toThrow(/attempt_id/);
    expect(buildDeletionPayload({ scope: "attempt", attempt_id: "att-9" })).toEqual({
      scope: "attempt",
      attempt_id: "att-9",
    });
  });
});

describe("parseFastApiDetail", () => {
  it("parses string detail", () => {
    expect(parseFastApiDetail({ detail: "nope" })).toEqual({ message: "nope", code: null });
  });

  it("parses {code, message} detail", () => {
    expect(
      parseFastApiDetail({ detail: { code: "unsupported_role", message: "not allowed" } }),
    ).toEqual({
      message: "not allowed",
      code: "unsupported_role",
    });
  });

  it("parses pydantic validation array", () => {
    expect(
      parseFastApiDetail({
        detail: [{ msg: "field required", loc: ["body", "role_id"], type: "value_error.missing" }],
      }),
    ).toEqual({ message: "field required", code: "validation_error" });
  });

  it("returns nulls when no detail is present", () => {
    expect(parseFastApiDetail({})).toEqual({ message: null, code: null });
    expect(parseFastApiDetail(null)).toEqual({ message: null, code: null });
  });
});

vi.mock("@/lib/env", async () => {
  const actual = await vi.importActual<typeof import("@/lib/env")>("@/lib/env");
  return {
    ...actual,
    env: { ...actual.env, apiBaseUrl: "https://api.example.test" },
    isBackendConfigured: () => true,
  };
});
vi.mock("@/lib/supabase", () => ({
  getAccessToken: async () => "test-token",
}));

describe("apiRequest — 404/501 → honest unavailable via ApiError", () => {
  const originalFetch = globalThis.fetch;
  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("maps 404 to ApiError(not_found)", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "no such route" }), {
          status: 404,
          headers: { "content-type": "application/json" },
        }),
    ) as unknown as typeof fetch;
    const { apiRequest } = await import("@/lib/api/client");
    const err = (await apiRequest("/api/v1/health", { auth: false }).catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.kind).toBe("not_found");
    expect(err.status).toBe(404);
  });

  it("maps 501 to ApiError(not_implemented)", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: { code: "not_ready", message: "planned" } }), {
          status: 501,
          headers: { "content-type": "application/json" },
        }),
    ) as unknown as typeof fetch;
    const { apiRequest } = await import("@/lib/api/client");
    const err = (await apiRequest("/api/v1/attempts/x/report").catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.kind).toBe("not_implemented");
    expect(err.code).toBe("not_ready");
    expect(err.message).toBe("planned");
  });

  it("saveConsent sends exactly one consent record without categories", async () => {
    const payload = buildConsentPayload({ consent_type: "interview_recording", granted: false });
    let body: unknown = null;
    globalThis.fetch = vi.fn(async (_url, init) => {
      body = JSON.parse(String(init?.body));
      return new Response(
        JSON.stringify({
          id: "c1",
          user_id: "u1",
          attempt_id: null,
          consent_type: "interview_recording",
          policy_version: POLICY_VERSION,
          granted: false,
          source: "web",
          occurred_at: "2026-01-01T00:00:00Z",
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }) as unknown as typeof fetch;

    await privacyApi.saveConsent(payload);

    expect(body).toEqual({
      attempt_id: null,
      consent_type: "interview_recording",
      policy_version: POLICY_VERSION,
      granted: false,
      source: "web",
    });
    expect(body).not.toHaveProperty("categories");
  });

  it("requestDeletion sends the scope schema without reason", async () => {
    const payload = buildDeletionPayload({ scope: "account" });
    let body: unknown = null;
    globalThis.fetch = vi.fn(async (_url, init) => {
      body = JSON.parse(String(init?.body));
      return new Response(
        JSON.stringify({
          id: "d1",
          user_id: "u1",
          scope: "account",
          attempt_id: null,
          status: "requested",
          requested_at: "2026-01-01T00:00:00Z",
          completed_at: null,
          error_code: null,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }) as unknown as typeof fetch;

    await privacyApi.requestDeletion(payload);

    expect(body).toEqual({ scope: "account", attempt_id: null });
    expect(body).not.toHaveProperty("reason");
  });

  it("rolesApi.list fetches the reviewed catalog with auth:false", async () => {
    let capturedUrl: string | undefined;
    let capturedAuth: string | null | undefined;
    globalThis.fetch = vi.fn(async (url, init) => {
      capturedUrl = String(url);
      capturedAuth =
        (init?.headers as Record<string, string> | undefined)?.["Authorization"] ?? null;
      return new Response(
        JSON.stringify([
          {
            role_id: "junior_frontend_developer",
            display_name: "Junior Frontend Developer",
            template_version: "1",
            review_status: "approved",
            supported_title_terms: [],
            competency_names: ["JavaScript"],
          },
        ]),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }) as unknown as typeof fetch;
    const { rolesApi } = await import("@/lib/api/endpoints");
    const list = await rolesApi.list();
    expect(list).toHaveLength(1);
    expect(capturedUrl).toMatch(/\/api\/v1\/roles$/);
    expect(capturedAuth).toBeNull();
  });

  it("rolesApi.detect includes selected_role_id in the request body", async () => {
    let body: unknown = null;
    globalThis.fetch = vi.fn(async (_url, init) => {
      body = JSON.parse(String(init?.body));
      return new Response(
        JSON.stringify({
          status: "detected",
          mapping_version: "m-1",
          role_id: "junior_backend_developer",
          confidence: 0.9,
          reason: "ok",
          matched_title_terms: [],
          matched_seniority_terms: [],
          matched_skills_by_competency: {},
          competency_weights: {},
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }) as unknown as typeof fetch;
    const { rolesApi } = await import("@/lib/api/endpoints");
    await rolesApi.detect({
      job_description: REAL_JD,
      selected_role_id: "junior_backend_developer",
    });
    expect(body).toEqual({
      job_description: REAL_JD,
      selected_role_id: "junior_backend_developer",
    });
  });
});

describe("document size limits", () => {
  it("MAX_DOCUMENT_BYTES matches backend 5 MiB limit", () => {
    expect(MAX_DOCUMENT_BYTES).toBe(5 * 1024 * 1024);
  });

  it("validateDocumentSize accepts files at or below 5 MiB", () => {
    expect(validateDocumentSize({ name: "ok.pdf", size: 5 * 1024 * 1024 })).toBeNull();
    expect(validateDocumentSize({ name: "small.pdf", size: 1024 })).toBeNull();
  });

  it("validateDocumentSize returns an actionable message above 5 MiB", () => {
    const msg = validateDocumentSize({ name: "big.pdf", size: 5 * 1024 * 1024 + 1 });
    expect(msg).not.toBeNull();
    expect(msg).toContain("big.pdf");
    expect(msg).toContain("5.0 MiB");
  });

  describe("processing contract shapes", () => {
    it("StartProcessingResponse carries queued_job_count and message", () => {
      const r: StartProcessingResponse = {
        attempt_id: "att-1",
        started: true,
        queued_job_count: 3,
        message: "queued",
      };
      expect(r.queued_job_count).toBe(3);
      expect(r.started).toBe(true);
    });

    it("ProcessingJobView uses job_type/stage and no progress field", () => {
      const j: ProcessingJobView = {
        id: "j1",
        attempt_id: "att-1",
        answer_id: null,
        job_type: "transcribe",
        status: "running",
        stage: "downloading",
        attempt_count: 1,
        max_attempts: 3,
        error_code: null,
        error_detail: null,
        queued_at: "2026-01-01T00:00:00Z",
        started_at: "2026-01-01T00:00:01Z",
        finished_at: null,
        updated_at: "2026-01-01T00:00:02Z",
      };
      expect(j.job_type).toBe("transcribe");
      expect(j.stage).toBe("downloading");
      expect("progress" in j).toBe(false);
      expect("kind" in j).toBe(false);
    });

    it("AnswerRecord uses processing_status/submitted_at/processed_at (no created_at)", () => {
      const a: AnswerRecord = {
        id: "a1",
        attempt_id: "att-1",
        question_id: "q1",
        private_video_storage_key: "u/attempts/att-1/q1.webm",
        video_sha256: "b".repeat(64),
        duration_seconds: 42,
        processing_status: "queued",
        submitted_at: "2026-01-01T00:00:00Z",
        processed_at: null,
      };
      expect(a.processing_status).toBe("queued");
      expect(a.processed_at).toBeNull();
      expect("created_at" in a).toBe(false);
    });
  });
});
