import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useAuth } from "@/lib/auth";
import { isSupabaseConfigured } from "@/lib/env";
import { UnavailableState } from "@/components/app/StateViews";
import { performResetRequest } from "@/lib/auth-actions";

const searchSchema = z.object({
  mode: z.enum(["signin", "signup", "reset", "recovery"]).optional(),
});

export const Route = createFileRoute("/auth")({
  validateSearch: searchSchema,
  head: () => ({
    meta: [
      { title: "Sign in — FairHireAI" },
      { name: "description", content: "Sign in or create your FairHireAI student account." },
      { property: "og:title", content: "Sign in — FairHireAI" },
      { property: "og:description", content: "Sign in or create your FairHireAI student account." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: AuthPage,
});

const emailSchema = z.string().trim().email("Enter a valid email").max(255);
const passwordSchema = z.string().min(8, "At least 8 characters").max(200);

/** Extract a safe error label from the URL fragment (e.g. #error=access_denied&error_code=otp_expired). */
function readHashError(): { code: string | null; description: string | null } {
  if (typeof window === "undefined") return { code: null, description: null };
  const hash = window.location.hash.startsWith("#")
    ? window.location.hash.slice(1)
    : window.location.hash;
  if (!hash) return { code: null, description: null };
  const params = new URLSearchParams(hash);
  const code = params.get("error_code") ?? params.get("error");
  const rawDesc = params.get("error_description");
  const description = rawDesc ? rawDesc.replace(/\+/g, " ") : null;
  // Never surface tokens; only labelled error fields.
  return { code, description };
}

function AuthPage() {
  const { mode = "signin" } = Route.useSearch();
  const {
    user,
    ready,
    configured,
    passwordRecoveryActive,
    signInWithPassword,
    signUpWithPassword,
    resetPassword,
    updatePassword,
    signOut,
  } = useAuth();
  const navigate = useNavigate();
  const isRecovery = mode === "recovery";
  const [tab, setTab] = useState<"signin" | "signup" | "reset">(
    mode === "recovery" ? "signin" : mode,
  );
  useEffect(() => {
    if (mode !== "recovery") setTab(mode);
  }, [mode]);

  const hashError = useMemo(() => readHashError(), []);

  useEffect(() => {
    // Do NOT auto-navigate away while a recovery flow is active — the form needs to render.
    if (isRecovery) return;
    if (ready && user) navigate({ to: "/dashboard" });
  }, [ready, user, navigate, isRecovery]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <Link to="/" className="text-lg font-semibold tracking-tight text-foreground">
            FairHireAI
          </Link>
        </div>

        {!configured ? (
          <UnavailableState
            feature="Authentication"
            detail="Authentication is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY to enable sign in."
          />
        ) : isRecovery ? (
          <RecoveryForm
            hashError={hashError}
            hasRecoverySession={passwordRecoveryActive || Boolean(user)}
            ready={ready}
            onUpdatePassword={updatePassword}
            onSignOut={signOut}
            onRequestFreshReset={() => navigate({ to: "/auth", search: { mode: "reset" } })}
            onReturnToSignIn={() => navigate({ to: "/auth", search: { mode: "signin" } })}
          />
        ) : (
          <>
            {hashError.code && (
              <Alert variant="destructive" className="mb-4">
                <AlertDescription>
                  {friendlyHashError(hashError)}{" "}
                  <button
                    type="button"
                    className="underline"
                    onClick={() => navigate({ to: "/auth", search: { mode: "reset" } })}
                  >
                    Request a fresh reset email
                  </button>
                  .
                </AlertDescription>
              </Alert>
            )}
            <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="signin">Sign in</TabsTrigger>
                <TabsTrigger value="signup">Sign up</TabsTrigger>
                <TabsTrigger value="reset">Reset</TabsTrigger>
              </TabsList>
              <TabsContent value="signin">
                <SignInForm onSubmit={signInWithPassword} />
              </TabsContent>
              <TabsContent value="signup">
                <SignUpForm onSubmit={signUpWithPassword} />
              </TabsContent>
              <TabsContent value="reset">
                <ResetForm onSubmit={resetPassword} />
              </TabsContent>
            </Tabs>
          </>
        )}
      </div>
    </div>
  );
}

function friendlyHashError(h: { code: string | null; description: string | null }): string {
  if (h.code === "otp_expired" || h.code === "access_denied") {
    return "This link has expired or is no longer valid.";
  }
  if (h.description) return h.description;
  return "This authentication link could not be used.";
}

interface Feedback {
  kind: "error" | "success";
  msg: string;
}

function useFormFeedback() {
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  return { feedback, setFeedback };
}

function RecoveryForm({
  hashError,
  hasRecoverySession,
  ready,
  onUpdatePassword,
  onSignOut,
  onRequestFreshReset,
  onReturnToSignIn,
}: {
  hashError: { code: string | null; description: string | null };
  hasRecoverySession: boolean;
  ready: boolean;
  onUpdatePassword: (password: string) => Promise<void>;
  onSignOut: () => Promise<void>;
  onRequestFreshReset: () => void;
  onReturnToSignIn: () => void;
}) {
  const { feedback, setFeedback } = useFormFeedback();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  if (done) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Password updated</CardTitle>
          <CardDescription>
            Your password has been changed. Sign in with your new password.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button className="w-full" onClick={onReturnToSignIn}>
            Return to sign in
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (hashError.code) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Recovery link problem</CardTitle>
          <CardDescription>{friendlyHashError(hashError)}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button className="w-full" onClick={onRequestFreshReset}>
            Request a fresh reset email
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (ready && !hasRecoverySession) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Recovery link required</CardTitle>
          <CardDescription>
            No active recovery session was found. Open this page from the reset email link, or
            request a new one.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button className="w-full" onClick={onRequestFreshReset}>
            Request a fresh reset email
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Set a new password</CardTitle>
        <CardDescription>Enter and confirm a new password to complete recovery.</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            const fd = new FormData(e.currentTarget);
            const password = passwordSchema.safeParse(fd.get("password"));
            const confirm = String(fd.get("confirm") ?? "");
            if (!password.success)
              return setFeedback({ kind: "error", msg: password.error.issues[0].message });
            if (password.data !== confirm)
              return setFeedback({ kind: "error", msg: "Passwords do not match." });
            setBusy(true);
            setFeedback(null);
            try {
              await onUpdatePassword(password.data);
              await onSignOut();
              setDone(true);
            } catch (err) {
              setFeedback({
                kind: "error",
                msg: err instanceof Error ? err.message : "Could not update password.",
              });
            } finally {
              setBusy(false);
            }
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="password">New password</Label>
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete="new-password"
              minLength={8}
              maxLength={200}
              required
            />
            <p className="text-xs text-muted-foreground">At least 8 characters.</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="confirm">Confirm password</Label>
            <Input
              id="confirm"
              name="confirm"
              type="password"
              autoComplete="new-password"
              minLength={8}
              maxLength={200}
              required
            />
          </div>
          {feedback && (
            <Alert variant={feedback.kind === "error" ? "destructive" : "default"}>
              <AlertDescription>{feedback.msg}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Updating…" : "Update password"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function SignInForm({
  onSubmit,
}: {
  onSubmit: (email: string, password: string) => Promise<void>;
}) {
  const { feedback, setFeedback } = useFormFeedback();
  const [busy, setBusy] = useState(false);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Welcome back</CardTitle>
        <CardDescription>Sign in with your student email and password.</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            const fd = new FormData(e.currentTarget);
            const email = emailSchema.safeParse(fd.get("email"));
            const password = passwordSchema.safeParse(fd.get("password"));
            if (!email.success)
              return setFeedback({ kind: "error", msg: email.error.issues[0].message });
            if (!password.success)
              return setFeedback({ kind: "error", msg: password.error.issues[0].message });
            setBusy(true);
            setFeedback(null);
            try {
              await onSubmit(email.data, password.data);
            } catch (err) {
              setFeedback({
                kind: "error",
                msg: err instanceof Error ? err.message : "Sign-in failed.",
              });
            } finally {
              setBusy(false);
            }
          }}
        >
          <FieldEmail />
          <FieldPassword autoComplete="current-password" />
          {feedback && (
            <Alert variant={feedback.kind === "error" ? "destructive" : "default"}>
              <AlertDescription>{feedback.msg}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function SignUpForm({
  onSubmit,
}: {
  onSubmit: (email: string, password: string) => Promise<{ needsEmailConfirmation: boolean }>;
}) {
  const { feedback, setFeedback } = useFormFeedback();
  const [busy, setBusy] = useState(false);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Create your account</CardTitle>
        <CardDescription>
          Use your student email. You may need to confirm it depending on your project settings.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            const fd = new FormData(e.currentTarget);
            const email = emailSchema.safeParse(fd.get("email"));
            const password = passwordSchema.safeParse(fd.get("password"));
            if (!email.success)
              return setFeedback({ kind: "error", msg: email.error.issues[0].message });
            if (!password.success)
              return setFeedback({ kind: "error", msg: password.error.issues[0].message });
            setBusy(true);
            setFeedback(null);
            try {
              const { needsEmailConfirmation } = await onSubmit(email.data, password.data);
              if (needsEmailConfirmation) {
                setFeedback({
                  kind: "success",
                  msg: "Check your inbox to confirm your email before signing in.",
                });
              } else {
                setFeedback({ kind: "success", msg: "Account created." });
              }
            } catch (err) {
              setFeedback({
                kind: "error",
                msg: err instanceof Error ? err.message : "Sign-up failed.",
              });
            } finally {
              setBusy(false);
            }
          }}
        >
          <FieldEmail />
          <FieldPassword autoComplete="new-password" />
          {feedback && (
            <Alert variant={feedback.kind === "error" ? "destructive" : "default"}>
              <AlertDescription>{feedback.msg}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Creating…" : "Create account"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function ResetForm({ onSubmit }: { onSubmit: (email: string) => Promise<void> }) {
  const { feedback, setFeedback } = useFormFeedback();
  const [busy, setBusy] = useState(false);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Reset your password</CardTitle>
        <CardDescription>We'll email a reset link if the address is registered.</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            const fd = new FormData(e.currentTarget);
            const email = emailSchema.safeParse(fd.get("email"));
            if (!email.success)
              return setFeedback({ kind: "error", msg: email.error.issues[0].message });
            setBusy(true);
            setFeedback(null);
            const result = await performResetRequest(() => onSubmit(email.data));
            setFeedback(result);
            setBusy(false);
          }}
        >
          <FieldEmail />
          {feedback && (
            <Alert variant={feedback.kind === "error" ? "destructive" : "default"}>
              <AlertDescription>{feedback.msg}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Sending…" : "Send reset link"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function FieldEmail() {
  return (
    <div className="space-y-1.5">
      <Label htmlFor="email">Email</Label>
      <Input id="email" name="email" type="email" autoComplete="email" required maxLength={255} />
    </div>
  );
}

function FieldPassword({ autoComplete }: { autoComplete: string }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor="password">Password</Label>
      <Input
        id="password"
        name="password"
        type="password"
        autoComplete={autoComplete}
        minLength={8}
        maxLength={200}
        required
      />
      <p className="text-xs text-muted-foreground">At least 8 characters.</p>
    </div>
  );
}

// used to indicate the auth surface even when supabase not configured
export { isSupabaseConfigured };
