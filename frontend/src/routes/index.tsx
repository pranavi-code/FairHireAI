import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, ClipboardCheck, LineChart, ShieldCheck, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { SafetyDisclaimer } from "@/components/app/StateViews";
import { useAuth } from "@/lib/auth";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "FairHireAI — Evidence-backed placement-readiness for students" },
      {
        name: "description",
        content:
          "Practice interviews, get evidence-backed feedback, and build a personalised roadmap. FairHireAI is for student self-improvement — not a hiring or ranking tool.",
      },
      { property: "og:title", content: "FairHireAI — Evidence-backed placement-readiness" },
      {
        property: "og:description",
        content:
          "Evidence-backed placement-readiness feedback for students — not a hiring decision or ranking system.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Landing,
});

function Landing() {
  const { user } = useAuth();
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-30 border-b border-border/60 bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <Link to="/" className="flex items-center gap-2">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-[image:var(--gradient-primary)] text-primary-foreground shadow-elegant">
              <span className="text-sm font-black">F</span>
            </span>
            <span className="text-base font-semibold tracking-tight">FairHireAI</span>
          </Link>
          <div className="flex items-center gap-2">
            {user ? (
              <Button asChild size="sm">
                <Link to="/dashboard">Open dashboard</Link>
              </Button>
            ) : (
              <>
                <Button asChild variant="ghost" size="sm">
                  <Link to="/auth">Sign in</Link>
                </Button>
                <Button asChild size="sm">
                  <Link to="/auth" search={{ mode: "signup" }}>
                    Get started
                  </Link>
                </Button>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Editorial hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-aurora" aria-hidden />
        <div className="absolute inset-0 bg-grid-soft opacity-40" aria-hidden />
        <div className="relative mx-auto grid max-w-7xl gap-12 px-6 py-20 md:grid-cols-[1.15fr_1fr] md:py-28">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-border bg-card/80 px-3 py-1 text-xs font-medium text-evidence backdrop-blur">
              <Sparkles className="h-3.5 w-3.5" aria-hidden />
              For students · self-improvement only
            </span>
            <h1 className="mt-5 text-5xl font-black leading-[1.05] tracking-tight text-foreground md:text-6xl">
              Practice the interview.{" "}
              <span className="bg-[image:var(--gradient-primary)] bg-clip-text text-transparent">
                Own the evidence.
              </span>
            </h1>
            <p className="mt-5 max-w-xl text-lg text-muted-foreground">
              FairHireAI runs a structured mock interview aligned to a reviewed role, then returns
              competency-level feedback grounded in the exact question, transcript span and resume
              claim it was based on. Never a hiring or ranking tool.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild size="lg" className="rounded-full px-6">
                <Link to={user ? "/dashboard" : "/auth"}>
                  {user ? "Open dashboard" : "Get started"}
                  <ArrowRight className="ml-2 h-4 w-4" aria-hidden />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline" className="rounded-full px-6">
                <Link to="/settings/privacy">How we handle your data</Link>
              </Button>
            </div>

            <div className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1.5">
                <ShieldCheck className="h-4 w-4 text-evidence" aria-hidden /> Private storage by
                user
              </span>
              <span className="inline-flex items-center gap-1.5">
                <ClipboardCheck className="h-4 w-4 text-evidence" aria-hidden /> Reviewer-approved
                rubrics
              </span>
              <span className="inline-flex items-center gap-1.5">
                <LineChart className="h-4 w-4 text-evidence" aria-hidden /> No inferred hiring
                outcomes
              </span>
            </div>
          </div>

          {/* Journey preview panel */}
          <div className="relative">
            <div className="rounded-3xl border border-border bg-card/80 p-6 shadow-elegant backdrop-blur">
              <p className="text-xs font-semibold uppercase tracking-wider text-evidence">
                Your journey
              </p>
              <ol className="mt-4 space-y-4">
                {[
                  { n: 1, t: "Choose a reviewed role", d: "Browse the versioned catalog." },
                  {
                    n: 2,
                    t: "Optional: tailor with a JD",
                    d: "Backend adapts approved weights only.",
                  },
                  {
                    n: 3,
                    t: "Structured mock interview",
                    d: "Server-issued questions and rubrics.",
                  },
                  {
                    n: 4,
                    t: "Evidence-first report",
                    d: "Every score cites its evidence — or says unavailable.",
                  },
                ].map((s) => (
                  <li key={s.n} className="flex gap-3">
                    <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-primary/10 text-xs font-bold text-primary">
                      {s.n}
                    </span>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-foreground">{s.t}</p>
                      <p className="text-xs text-muted-foreground">{s.d}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-6 py-16">
        <div className="grid gap-4 md:grid-cols-3">
          {[
            {
              icon: ClipboardCheck,
              title: "Reviewed role catalog",
              body: "Search the versioned catalog and pick the role you're preparing for — weights are approved per role, never invented in the browser.",
            },
            {
              icon: LineChart,
              title: "Evidence-first reports",
              body: "Every score cites the question, transcript span, rubric and resume claim it was based on. If evidence is insufficient, we say so.",
            },
            {
              icon: ShieldCheck,
              title: "Private by default",
              body: "Documents and recordings live in private storage under your user. You can revoke consent or request deletion at any time.",
            },
          ].map((f) => (
            <Card key={f.title} className="rounded-2xl border-border/70">
              <CardContent className="space-y-3 py-6">
                <div className="inline-flex rounded-xl bg-primary/10 p-2 text-primary">
                  <f.icon className="h-5 w-5" aria-hidden />
                </div>
                <h2 className="text-base font-semibold text-foreground">{f.title}</h2>
                <p className="text-sm text-muted-foreground">{f.body}</p>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="mt-14 rounded-2xl border border-border bg-card p-6">
          <SafetyDisclaimer />
        </div>
      </section>

      <footer className="border-t border-border/70">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-2 px-6 py-6 text-xs text-muted-foreground sm:flex-row">
          <span>© FairHireAI · RoleReady AI</span>
          <div className="flex items-center gap-4">
            <Link to="/settings/privacy" className="hover:text-foreground">
              Privacy
            </Link>
            <Link to="/consent" className="hover:text-foreground">
              Consent
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
