import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { PageBody, PageHeader } from "@/components/app/AppShell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
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

function formatPct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "Insufficient evidence";
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
        description="Progress becomes meaningful after at least two completed attempts. Only real backend data is shown."
      />
      <PageBody>
        {q.isPending ? (
          <LoadingState label="Loading progress…" />
        ) : q.isError && isUnavailable(q.error) ? (
          <UnavailableState feature="Progress" />
        ) : q.isError ? (
          <ErrorState error={q.error as ApiError} onRetry={() => q.refetch()} />
        ) : attempts.length < 2 ? (
          <EmptyState
            title="Not enough attempts yet"
            description={
              q.data?.message ??
              "Complete at least two attempts to see meaningful progress. Single-attempt trends would be misleading."
            }
          />
        ) : (
          <div className="grid gap-6">
            <Card className="rounded-3xl">
              <CardHeader>
                <CardTitle>Completed attempts</CardTitle>
                <CardDescription>{attempts.length} attempts</CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="divide-y divide-border rounded-2xl border border-border">
                  {attempts.map((a) => (
                    <li key={a.attempt_id} className="flex items-center justify-between px-4 py-3">
                      <div className="min-w-0">
                        <p className="font-mono text-xs text-foreground">{a.attempt_id}</p>
                        <p className="text-xs text-muted-foreground">
                          {new Date(a.completed_at).toLocaleString()}
                        </p>
                      </div>
                      <div className="flex items-center gap-3">
                        <Badge variant="outline">{a.role_id}</Badge>
                        <span className="text-sm font-semibold text-foreground">
                          {formatPct(a.placement_readiness)}
                        </span>
                      </div>
                    </li>
                  ))}
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
