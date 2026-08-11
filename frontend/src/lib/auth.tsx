import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Session, User } from "@supabase/supabase-js";
import { getSupabase } from "./supabase";
import { isSupabaseConfigured } from "./env";
import { buildRecoveryRedirect, buildSignUpEmailRedirect } from "./auth-actions";
import type { ConsentType } from "./api/types";

interface AuthContextValue {
  ready: boolean;
  configured: boolean;
  session: Session | null;
  user: User | null;
  /** True once Supabase has emitted a PASSWORD_RECOVERY event in this tab. */
  passwordRecoveryActive: boolean;
  signInWithPassword: (email: string, password: string) => Promise<void>;
  signUpWithPassword: (
    email: string,
    password: string,
  ) => Promise<{ needsEmailConfirmation: boolean }>;
  signOut: () => Promise<void>;
  resetPassword: (email: string) => Promise<void>;
  /** Updates the password for the current (recovery) session. */
  updatePassword: (password: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const [passwordRecoveryActive, setPasswordRecoveryActive] = useState(false);
  const configured = isSupabaseConfigured();

  useEffect(() => {
    const sb = getSupabase();
    if (!sb) {
      setReady(true);
      return;
    }
    let mounted = true;
    sb.auth.getSession().then(({ data }) => {
      if (!mounted) return;
      setSession(data.session);
      setReady(true);
    });
    const { data: sub } = sb.auth.onAuthStateChange((event, s) => {
      setSession(s);
      if (event === "PASSWORD_RECOVERY") setPasswordRecoveryActive(true);
    });
    return () => {
      mounted = false;
      sub.subscription.unsubscribe();
    };
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      ready,
      configured,
      session,
      user: session?.user ?? null,
      passwordRecoveryActive,
      async signInWithPassword(email, password) {
        const sb = getSupabase();
        if (!sb) throw new Error("Authentication is not configured.");
        const { error } = await sb.auth.signInWithPassword({ email, password });
        if (error) throw error;
      },
      async signUpWithPassword(email, password) {
        const sb = getSupabase();
        if (!sb) throw new Error("Authentication is not configured.");
        const { data, error } = await sb.auth.signUp({
          email,
          password,
          options: {
            emailRedirectTo:
              typeof window !== "undefined"
                ? buildSignUpEmailRedirect(window.location.origin)
                : undefined,
          },
        });
        if (error) throw error;
        return { needsEmailConfirmation: !data.session };
      },
      async signOut() {
        const sb = getSupabase();
        if (!sb) return;
        setPasswordRecoveryActive(false);
        await sb.auth.signOut();
      },
      async resetPassword(email) {
        const sb = getSupabase();
        if (!sb) throw new Error("Authentication is not configured.");
        const { error } = await sb.auth.resetPasswordForEmail(email, {
          redirectTo:
            typeof window !== "undefined"
              ? buildRecoveryRedirect(window.location.origin)
              : undefined,
        });
        if (error) throw error;
      },
      async updatePassword(password) {
        const sb = getSupabase();
        if (!sb) throw new Error("Authentication is not configured.");
        const { error } = await sb.auth.updateUser({ password });
        if (error) throw error;
      },
    }),
    [ready, configured, session, passwordRecoveryActive],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

/**
 * UI cache for the required consent set. Gates navigation only AFTER successful
 * backend writes. This is NEVER treated as authoritative consent history —
 * there is currently no GET /privacy/consents endpoint. The backend is the
 * only source of truth.
 */
const CONSENT_CACHE_KEY = "fairhireai-consent-ui-cache";

export interface ConsentUiCache {
  /** Consent types recorded as granted during the last successful session. */
  grantedTypes: ConsentType[];
  /** Whether the required set (privacy_notice, resume_processing, interview_recording) is complete. */
  requiredComplete: boolean;
  /** Optional research_evaluation consent state, when the user opted in. */
  researchGranted: boolean;
  /** Required consent for minimized Gemini question/evaluation processing. */
  externalAiGranted: boolean;
  /** Local timestamp — for UX only. Not authoritative. */
  at: string;
}

export const REQUIRED_CONSENTS: ConsentType[] = [
  "privacy_notice",
  "resume_processing",
  "interview_recording",
  "external_ai_processing",
];

export function readConsentUiCache(): ConsentUiCache | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(CONSENT_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ConsentUiCache>;
    if (!parsed || !Array.isArray(parsed.grantedTypes)) return null;
    return {
      grantedTypes: parsed.grantedTypes as ConsentType[],
      requiredComplete: Boolean(parsed.requiredComplete),
      researchGranted: Boolean(parsed.researchGranted),
      externalAiGranted: Boolean(parsed.externalAiGranted),
      at: typeof parsed.at === "string" ? parsed.at : new Date().toISOString(),
    };
  } catch {
    return null;
  }
}

export function writeConsentUiCache(cache: ConsentUiCache): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(CONSENT_CACHE_KEY, JSON.stringify(cache));
}

export function clearConsentUiCache(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(CONSENT_CACHE_KEY);
}
