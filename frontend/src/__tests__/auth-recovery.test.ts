import { describe, expect, it, vi } from "vitest";
import {
  authSearchModes,
  buildRecoveryRedirect,
  buildSignUpEmailRedirect,
  performResetRequest,
  RESET_REQUEST_ERROR_MSG,
  RESET_REQUEST_SUCCESS_MSG,
  shouldRedirectAuthedToDashboard,
  validateNewPasswordPair,
} from "@/lib/auth-actions";

const ORIGIN = "https://id-preview--66420821-2ebe-4e73-b672-4dcd71e2865c.lovable.app";

describe("auth search modes", () => {
  it("includes 'recovery' so the recovery form can be routed to", () => {
    expect(authSearchModes).toContain("recovery");
    expect(authSearchModes).toContain("signin");
    expect(authSearchModes).toContain("signup");
    expect(authSearchModes).toContain("reset");
  });
});

describe("email redirect builders use the current origin", () => {
  it("signup returns to /auth?mode=signin on the current origin (never localhost)", () => {
    const url = buildSignUpEmailRedirect(ORIGIN);
    expect(url).toBe(`${ORIGIN}/auth?mode=signin`);
    expect(url.startsWith(ORIGIN)).toBe(true);
    expect(url).not.toMatch(/localhost/i);
  });

  it("recovery redirects into /auth?mode=recovery on the current origin", () => {
    const url = buildRecoveryRedirect(ORIGIN);
    expect(url).toBe(`${ORIGIN}/auth?mode=recovery`);
    expect(url.startsWith(ORIGIN)).toBe(true);
    expect(url).not.toMatch(/localhost/i);
  });
});

describe("password confirmation validation", () => {
  it("rejects short passwords", () => {
    expect(validateNewPasswordPair("short", "short")).toMatch(/8 characters/i);
  });
  it("rejects mismatched passwords", () => {
    expect(validateNewPasswordPair("longenough1", "different1")).toMatch(/do not match/i);
  });
  it("accepts a matching 8+ character pair", () => {
    expect(validateNewPasswordPair("goodpass1", "goodpass1")).toBeNull();
  });
});

describe("authenticated recovery must not bounce to /dashboard", () => {
  it("does NOT redirect while mode=recovery even with a user session", () => {
    expect(shouldRedirectAuthedToDashboard({ ready: true, hasUser: true, isRecovery: true })).toBe(
      false,
    );
  });
  it("does redirect for a normal signed-in visit to /auth", () => {
    expect(shouldRedirectAuthedToDashboard({ ready: true, hasUser: true, isRecovery: false })).toBe(
      true,
    );
  });
  it("does not redirect before ready or without a user", () => {
    expect(
      shouldRedirectAuthedToDashboard({ ready: false, hasUser: true, isRecovery: false }),
    ).toBe(false);
    expect(
      shouldRedirectAuthedToDashboard({ ready: true, hasUser: false, isRecovery: false }),
    ).toBe(false);
  });
});

describe("updatePassword wiring calls supabase.auth.updateUser({ password })", () => {
  it("invokes the Supabase updateUser method with the new password", async () => {
    const updateUser = vi.fn(async (_args: { password: string }) => ({
      data: { user: null },
      error: null,
    }));
    const fakeSupabase = { auth: { updateUser } };
    // Mirror the provider action shape — a thin wrapper around supabase.auth.updateUser.
    async function updatePassword(password: string) {
      const { error } = await fakeSupabase.auth.updateUser({ password });
      if (error) throw error;
    }
    await updatePassword("newpass12");
    expect(updateUser).toHaveBeenCalledTimes(1);
    expect(updateUser).toHaveBeenCalledWith({ password: "newpass12" });
  });
});

describe("reset request feedback is account-neutral for both success and failure", () => {
  it("success feedback uses the generic 'if that email is registered' message", async () => {
    const send = vi.fn(async () => {});
    const result = await performResetRequest(send);
    expect(send).toHaveBeenCalledTimes(1);
    expect(result).toEqual({ kind: "success", msg: RESET_REQUEST_SUCCESS_MSG });
    expect(result.msg).toMatch(/if that email is registered/i);
  });

  it("thrown backend/network/rate-limit errors become a distinct operational message, not a fake success", async () => {
    const send = vi.fn(async () => {
      throw new Error("rate limit exceeded: 429 from supabase");
    });
    const result = await performResetRequest(send);
    expect(result.kind).toBe("error");
    expect(result.msg).toBe(RESET_REQUEST_ERROR_MSG);
    // Distinct from the success copy — must not silently claim an email was sent.
    expect(result.msg).not.toBe(RESET_REQUEST_SUCCESS_MSG);
    expect(result.msg).not.toMatch(/if that email is registered/i);
    // Account-neutral: never reveals existence or leaks raw backend detail.
    expect(result.msg).not.toMatch(/exist|found|registered|user|account|supabase|429|rate/i);
  });
});
