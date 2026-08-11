/**
 * Pure helpers for the auth surface (URL redirects, validation, guards).
 * Extracted so the recovery/reset/signup contract can be unit-tested without
 * mounting React or a DOM.
 */

export const authSearchModes = ["signin", "signup", "reset", "recovery"] as const;
export type AuthSearchMode = (typeof authSearchModes)[number];

/** Signup confirmation emails must return to the current frontend origin, not localhost. */
export function buildSignUpEmailRedirect(origin: string): string {
  return `${origin}/auth?mode=signin`;
}

/** Password-recovery emails must return to the recovery form on the current origin. */
export function buildRecoveryRedirect(origin: string): string {
  return `${origin}/auth?mode=recovery`;
}

/** Returns null when the new password pair is valid, otherwise an actionable message. */
export function validateNewPasswordPair(pw: string, confirm: string): string | null {
  if (typeof pw !== "string" || pw.length < 8) return "At least 8 characters";
  if (pw.length > 200) return "Password is too long";
  if (pw !== confirm) return "Passwords do not match.";
  return null;
}

/**
 * The auth route auto-redirects signed-in users to /dashboard, EXCEPT while a
 * recovery flow is active — the recovery form must render even though Supabase
 * has already established a session from the recovery link.
 */
export function shouldRedirectAuthedToDashboard(input: {
  ready: boolean;
  hasUser: boolean;
  isRecovery: boolean;
}): boolean {
  return input.ready && input.hasUser && !input.isRecovery;
}

/**
 * Account-neutral feedback for the "send reset email" request.
 *
 * Success case: preserve the existing generic message so the response never
 * reveals whether the email is registered.
 *
 * Failure case: still account-neutral — do NOT surface Supabase/network/rate
 * limit details, because the presence or wording of a backend error can also
 * leak enumeration or infra signal. Instead render a distinct operational
 * message so users understand the request did not go through and can retry.
 */
export const RESET_REQUEST_SUCCESS_MSG = "If that email is registered, a reset link has been sent.";
export const RESET_REQUEST_ERROR_MSG =
  "We couldn't send a reset email right now. Please wait and try again.";

export type ResetRequestFeedback =
  | { kind: "success"; msg: typeof RESET_REQUEST_SUCCESS_MSG }
  | { kind: "error"; msg: typeof RESET_REQUEST_ERROR_MSG };

/**
 * Runs the caller's reset request and maps the outcome to account-neutral
 * feedback. Any thrown error becomes the generic operational message; the
 * raw error is intentionally discarded so backend details never surface.
 */
export async function performResetRequest(
  send: () => Promise<void>,
): Promise<ResetRequestFeedback> {
  try {
    await send();
    return { kind: "success", msg: RESET_REQUEST_SUCCESS_MSG };
  } catch {
    return { kind: "error", msg: RESET_REQUEST_ERROR_MSG };
  }
}
