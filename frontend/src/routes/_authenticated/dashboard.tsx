import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Activity,
  CircleAlert,
  CircleCheck,
  Compass,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { PageBody, PageHeader } from "@/components/app/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { InfoNotice, SafetyDisclaimer } from "@/components/app/StateViews";
import { healthApi, rolesApi } from "@/lib/api/endpoints";
import { isBackendConfigured } from "@/lib/env";
import { readConsentUiCache, useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_authenticated/dashboard")({
  head: () => ({
    meta: [
      { title: "Dashboard — FairHireAI" },
      {
        name: "description",
        content: "Your placement-readiness assessments, progress and privacy at a glance.",
      },
      { property: "og:title", content: "Dashboard — FairHireAI" },
      {
        property: "og:description",
        content: "Your placement-readiness assessments and progress at a glance.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: Dashboard,
});

function Dashboard() {
  const { user } = useAuth();
  const consent = readConsentUiCache();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => healthApi.get(),
    enabled: isBackendConfigured(),
    retry: false,
  });
  const roles = useQuery({
    queryKey: ["roles"],
    queryFn: () => rolesApi.list(),
    enabled: isBackendConfigured(),
    retry: false,
  });

  const backendOnline = isBackendConfigured() && health.isSuccess;
  const backendStatus: StatusKind = !isBackendConfigured()
    ? "pending"
    : health.isPending
      ? "pending"
      : backendOnline
        ? "ok"
        : "down";

  const firstName = user?.email?.split("@")[0] ?? "there";

  return (
    <>
      <PageHeader
        eyebrow="Your workspace"
        title={`Hello, ${firstName}`}
        description="Start a new assessment, revisit progress, or manage privacy — all grounded in real backend data."
        actions={
          <Button asChild size="lg" className="rounded-full px-6">
            <Link to="/assessment/new">
              New assessment
              <ArrowRight className="ml-2 h-4 w-4" aria-hidden />
            </Link>
          </Button>
        }
      />
      <PageBody>
        {/* Compact signal row — never a full-page red error */}
        <div className="mb-6 grid gap-3 sm:grid-cols-3">
          <StatusPill
            kind={backendStatus}
            icon={Activity}
            label="Backend"
            hint={
              !isBackendConfigured()
                ? "Not configured"
                : backendOnline
                  ? `Reachable · ${health.data?.status ?? "ok"}`
                  : health.isPending
                    ? "Checking…"
                    : "Unreachable"
            }
          />
          <StatusPill
            kind={consent?.requiredComplete ? "ok" : "pending"}
            icon={ShieldCheck}
            label="Consent"
            hint={
              consent?.requiredComplete
                ? "Required consents recorded (UI cache)"
                : "Required consents not yet complete"
            }
            action={consent?.requiredComplete ? undefined : { to: "/consent", label: "Record" }}
          />
          <StatusPill
            kind={roles.isSuccess ? "ok" : isBackendConfigured() ? "pending" : "pending"}
            icon={Compass}
            label="Role catalog"
            hint={
              roles.isSuccess
                ? `${roles.data?.length ?? 0} reviewed roles available`
                : roles.isError
                  ? "Unavailable — try again from the wizard"
                  : "Loading…"
            }
          />
        </div>

        {!consent?.requiredComplete && (
          <div className="mb-6">
            <InfoNotice>
              Before recording an interview, please review and record your{" "}
              <Link to="/consent" className="font-medium underline underline-offset-2">
                consent preferences
              </Link>
              .
            </InfoNotice>
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Journey rail */}
          <Card className="rounded-2xl lg:col-span-2">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-evidence" aria-hidden /> Your assessment journey
              </CardTitle>
              <CardDescription>
                Every step is grounded in real backend data. No fake attempts, scores, or timers.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ol className="space-y-4">
                {[
                  { n: 1, t: "Choose a reviewed role", d: "Browse the versioned catalog." },
                  {
                    n: 2,
                    t: "Optional: tailor with a JD",
                    d: "Backend adapts approved weights only.",
                  },
                  { n: 3, t: "Upload your resume", d: "Extracted claims are shown with evidence." },
                  {
                    n: 4,
                    t: "Structured mock interview",
                    d: "Server-issued questions and rubrics.",
                  },
                  {
                    n: 5,
                    t: "Skill-gap report + roadmap",
                    d: "Shows evidence-backed gaps and approved learning resources.",
                  },
                ].map((s) => (
                  <li key={s.n} className="flex gap-3">
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-primary/10 text-sm font-bold text-primary">
                      {s.n}
                    </span>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-foreground">{s.t}</p>
                      <p className="text-xs text-muted-foreground">{s.d}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>

          {/* Role explorer preview */}
          <Card className="rounded-2xl">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Compass className="h-4 w-4 text-evidence" aria-hidden /> Reviewed roles
              </CardTitle>
              <CardDescription>Straight from the backend catalog.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {roles.isPending && <p className="text-sm text-muted-foreground">Loading catalog…</p>}
              {roles.isError && (
                <p className="text-sm text-muted-foreground">
                  Catalog is unavailable right now — you can retry from the new-assessment wizard.
                </p>
              )}
              {roles.isSuccess && (
                <>
                  <ul className="space-y-2">
                    {roles.data.slice(0, 5).map((r) => (
                      <li
                        key={r.role_id}
                        className="flex items-center justify-between rounded-xl border border-border/70 bg-card px-3 py-2"
                      >
                        <span className="truncate text-sm font-medium text-foreground">
                          {r.display_name}
                        </span>
                        <Badge variant="secondary" className="text-[10px]">
                          v{r.template_version}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                  <Button asChild size="sm" variant="outline" className="w-full rounded-full">
                    <Link to="/assessment/new">
                      Browse full catalog
                      <ArrowRight className="ml-2 h-3.5 w-3.5" aria-hidden />
                    </Link>
                  </Button>
                </>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="mt-10">
          <SafetyDisclaimer />
        </div>
      </PageBody>
    </>
  );
}

type StatusKind = "ok" | "pending" | "down";

function StatusPill({
  kind,
  icon: Icon,
  label,
  hint,
  action,
}: {
  kind: StatusKind;
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  label: string;
  hint: string;
  action?: { to: string; label: string };
}) {
  const dot =
    kind === "ok"
      ? "bg-success text-success-foreground"
      : kind === "down"
        ? "bg-destructive text-destructive-foreground"
        : "bg-warning text-warning-foreground";
  const StatusIcon = kind === "ok" ? CircleCheck : kind === "down" ? CircleAlert : Activity;
  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-2xl border border-border/70 bg-card px-4 py-3",
      )}
    >
      <span className={cn("grid h-9 w-9 shrink-0 place-items-center rounded-xl", dot)}>
        <Icon className="h-4 w-4" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
          {label}
          <StatusIcon className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
        </div>
        <p className="truncate text-xs text-muted-foreground">{hint}</p>
      </div>
      {action && (
        <Button asChild size="sm" variant="ghost" className="shrink-0">
          <Link to={action.to}>{action.label}</Link>
        </Button>
      )}
    </div>
  );
}
