/**
 * Typed error taxonomy for FairHireAI API calls.
 * Every API caller must handle these explicitly — no silent fallbacks.
 */

export type ApiErrorKind =
  | "not_configured" // VITE_API_BASE_URL missing
  | "unauthorized" // 401
  | "forbidden" // 403
  | "not_found" // 404 (may indicate planned endpoint)
  | "not_implemented" // 501 (planned endpoint, honest unavailable)
  | "validation" // 422
  | "conflict" // 409
  | "unavailable" // 503
  | "server" // 5xx
  | "network" // fetch/network error
  | "unknown";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: string | null;
  readonly details: unknown;

  constructor(
    kind: ApiErrorKind,
    message: string,
    status: number | null = null,
    details: unknown = null,
    code: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.details = details;
    this.code = code;
  }
}

/**
 * Parse a FastAPI-style error body. `detail` may be:
 *   - a string
 *   - an object `{ code, message }`
 *   - a Pydantic validation array (list of `{loc,msg,type,...}`)
 * Returns a safe, user-facing message and an optional structured code.
 * Never surfaces internals such as stack traces or raw exception types.
 */
export function parseFastApiDetail(body: unknown): { message: string | null; code: string | null } {
  if (!body || typeof body !== "object") return { message: null, code: null };
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return { message: detail, code: null };
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const obj = detail as { message?: unknown; code?: unknown };
    const message = typeof obj.message === "string" ? obj.message : null;
    const code = typeof obj.code === "string" ? obj.code : null;
    return { message, code };
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    if (first && typeof first === "object") {
      const msg = (first as { msg?: unknown }).msg;
      if (typeof msg === "string") return { message: msg, code: "validation_error" };
    }
  }
  return { message: null, code: null };
}

/** True when the endpoint is not implemented / not deployed yet. */
export function isUnavailable(error: unknown): boolean {
  return (
    error instanceof ApiError && (error.kind === "not_implemented" || error.kind === "not_found")
  );
}

export function isAuthError(error: unknown): boolean {
  return error instanceof ApiError && (error.kind === "unauthorized" || error.kind === "forbidden");
}

export function friendlyMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const safeUnavailableCodes = new Set([
      "dynamic_interview_unavailable",
      "dynamic_question_generation_failed",
      "dynamic_question_validation_failed",
      "gemini_rate_limited",
      "gemini_temporarily_unavailable",
    ]);
    if (error.kind === "unavailable" && error.code && safeUnavailableCodes.has(error.code)) {
      return error.message;
    }
    // Prefer server-supplied user-facing message when present.
    if (error.message && error.status && error.status < 500 && error.kind !== "not_configured") {
      // A server 4xx typically means the message is actionable (validation, etc.).
      // For 401/403 override with a clearer prompt.
      if (error.kind === "unauthorized") return "Your session has expired. Please sign in again.";
      if (error.kind === "forbidden") return "You do not have permission to perform this action.";
      return error.message;
    }
    switch (error.kind) {
      case "not_configured":
        return "The backend URL is not configured. Set VITE_API_BASE_URL to enable this feature.";
      case "unauthorized":
        return "Your session has expired. Please sign in again.";
      case "forbidden":
        return "You do not have permission to perform this action.";
      case "not_found":
      case "not_implemented":
        return "This feature is not available from the connected backend yet.";
      case "validation":
        return "The request could not be processed. Please review your inputs.";
      case "conflict":
        return "This action conflicts with the current state.";
      case "unavailable":
        return "The service is temporarily unavailable. Please try again shortly.";
      case "server":
        return "The server reported an error. Please try again later.";
      case "network":
        return "Could not reach the server. Check your connection.";
      default:
        return error.message || "An unexpected error occurred.";
    }
  }
  return "An unexpected error occurred.";
}
