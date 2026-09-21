import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { PageBody, PageHeader } from "@/components/app/AppShell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  UnavailableState,
} from "@/components/app/StateViews";
import { progressApi } from "@/lib/api/endpoints";
import { ApiError, isUnavailable } from "@/lib/api/errors";

export const Route = createFileRoute("/_authenticated/progress")({
  head: () => ({
    meta: [
      { title: "Progress — FairHireAI" },
      { name: "description", content: "Track your placement-readiness across completed attempts." },
      { property: "og:title", content: "Progress — FairHireAI" },
      {
        property: "og:description",
        content: "Track your placement-readiness across completed attempts.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: ProgressPage,
});

function formatPct(v: number | null | undefined, unavailable = "Not calculated"): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return unavailable;
  return `${Math.round(v * 100)}%`;
}

function ProgressPage() {
  const q = useQuery({
    queryKey: ["progress"],
    queryFn: () => progressApi.get(),
  });

  const attempts = q.data?.attempts ?? [];

  return (
    <>
      <PageHeader
        eyebrow="Progress"
        title="Your progress"
        description="Your first completed attempt establishes a baseline. Later attempts add comparisons. Only real backend data is shown."
      />
      <PageBody>
        {q.isPending ? (
          <LoadingState label="Loading progress…" />
        ) : q.isError && isUnavailable(q.error) ? (
          <UnavailableState feature="Progress" />
        ) : q.isError ? (
          <ErrorState error={q.error as ApiError} onRetry={() => q.refetch()} />
        ) : attempts.length === 0 ? (
          <EmptyState
            title="No completed attempts yet"
            description={
              q.data?.message ??
              "Complete one evidence-backed interview to establish your progress baseline."
            }
          />
        ) : (
          <div className="grid gap-6">
            <Card className="rounded-3xl">
              <CardHeader>
                <CardTitle>Completed attempts</CardTitle>
                <CardDescription>
                  {attempts.length} completed {attempts.length === 1 ? "attempt" : "attempts"}
                  {attempts.length === 1
                    ? " · This is your baseline; complete another attempt to compare change."
                    : " · Compare results over time."}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="divide-y divide-border rounded-2xl border border-border">
                  {attempts.map((a) => {
                    const lowCoverage = a.competency_scores.filter(
                      (score) => !score.sufficient_evidence,
                    );
                    return (
                      <li key={a.attempt_id} className="space-y-3 px-4 py-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="font-mono text-xs text-foreground">{a.attempt_id}</p>
                            <p className="text-xs text-muted-foreground">
                              {new Date(a.completed_at).toLocaleString()}
                            </p>
                          </div>
                          <div className="flex flex-wrap items-center gap-3">
                            <Badge variant="outline">{a.role_id}</Badge>
                            <span className="text-sm font-semibold text-foreground">
                              {formatPct(a.placement_readiness)}
                            </span>
                          </div>
                        </div>

                        {a.placement_readiness === null && (
                          <div className="rounded-xl border border-amber-300/60 bg-amber-50/70 p-3 text-sm dark:bg-amber-950/20">
                            <p className="font-medium text-foreground">
                              Why Placement Readiness was not calculated
                            </p>
                            {lowCoverage.length > 0 ? (
                              <p className="mt-1 text-muted-foreground">
                                Evidence covered less than 70% of the reviewed rubric for:{" "}
                                {lowCoverage
                                  .map(
                                    (score) =>
                                      `${score.name ?? score.competency_id} (${formatPct(score.coverage)})`,
                                  )
                                  .join(", ")}
                                . Your competency scores remain visible; another attempt can add the
                                missing evidence.
                              </p>
                            ) : (
                              <ul className="mt-1 list-inside list-disc text-muted-foreground">
                                {(a.insufficiency_reasons ?? []).map((reason) => (
                                  <li key={reason}>{reason.replace(/_/g, " ")}</li>
                                ))}
                              </ul>
                            )}
                            {typeof a.overall_evidence_confidence === "number" && (
                              <p className="mt-1 text-xs text-muted-foreground">
                                Overall evidence confidence:{" "}
                                {formatPct(a.overall_evidence_confidence)}
                              </p>
                            )}
                          </div>
                        )}

                        <div className="flex flex-wrap gap-2">
                          <Button asChild size="sm" variant="outline" className="rounded-full">
                            <Link
                              to="/assessment/$attemptId/report"
                              params={{ attemptId: a.attempt_id }}
                            >
                              View full report
                            </Link>
                          </Button>
                          <Button asChild size="sm" variant="outline" className="rounded-full">
                            <Link
                              to="/assessment/$attemptId/roadmap"
                              params={{ attemptId: a.attempt_id }}
                            >
                              View learning roadmap
                            </Link>
                          </Button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </CardContent>
            </Card>

            <Card className="rounded-3xl">
              <CardHeader>
                <CardTitle>Competency scores</CardTitle>
                <CardDescription>Per-competency values across your attempts.</CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="space-y-4">
                  {attempts.map((a) => (
                    <li key={a.attempt_id}>
                      <p className="text-sm font-medium text-foreground">
                        {new Date(a.completed_at).toLocaleDateString()} · {a.role_id}
                      </p>
                      <ul className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
                        {a.competency_scores.map((s, i) => (
                          <li key={i} className="rounded-full bg-muted px-2.5 py-1">
                            {s.name ?? s.competency_id}:{" "}
                            {s.score === null || s.score === undefined
                              ? "—"
                              : `${Math.round(s.score * 100)}%`}
                            {s.score !== null && ` · evidence ${formatPct(s.coverage)}`}
                          </li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          </div>
        )}
      </PageBody>
    </>
  );
}
