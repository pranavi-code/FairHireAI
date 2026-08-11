import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { PageBody, PageHeader } from "@/components/app/AppShell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  UnavailableState,
} from "@/components/app/StateViews";
import { attemptsApi } from "@/lib/api/endpoints";
import { ApiError, isUnavailable } from "@/lib/api/errors";

export const Route = createFileRoute("/_authenticated/assessment/$attemptId/roadmap")({
  head: () => ({
    meta: [
      { title: "Roadmap — FairHireAI" },
      {
        name: "description",
        content: "Reviewer-approved learning resources for your unresolved gaps.",
      },
      { property: "og:title", content: "Roadmap — FairHireAI" },
      {
        property: "og:description",
        content: "Reviewer-approved learning resources for your unresolved gaps.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: RoadmapPage,
});

function RoadmapPage() {
  const { attemptId } = Route.useParams();
  const q = useQuery({
    queryKey: ["roadmap", attemptId],
    queryFn: () => attemptsApi.report(attemptId),
  });

  const items = q.data?.roadmap_items ?? [];

  return (
    <>
      <PageHeader
        eyebrow="Step 7 · Roadmap"
        title="Learning roadmap"
        description="Only reviewer-approved resources returned by the backend are shown. Unresolved competencies are surfaced honestly."
      />
      <PageBody>
        {q.isPending ? (
          <LoadingState label="Loading roadmap…" />
        ) : q.isError && isUnavailable(q.error) ? (
          <UnavailableState feature="Roadmap" />
        ) : q.isError ? (
          <ErrorState error={q.error as ApiError} onRetry={() => q.refetch()} />
        ) : items.length === 0 ? (
          <EmptyState
            title="No confirmed skill gaps"
            description={
              q.data?.message ??
              "This attempt did not produce a sufficiently supported skill gap, so no learning task was invented."
            }
          />
        ) : (
          <ol className="grid gap-4">
            {items.map((item, idx) => (
              <li key={item.id}>
                <Card className="rounded-3xl">
                  <CardHeader>
                    <div className="flex items-start gap-3">
                      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-2xl bg-[image:var(--gradient-primary)] text-sm font-semibold text-primary-foreground">
                        {idx + 1}
                      </div>
                      <div className="min-w-0">
                        <CardTitle className="text-base">{item.title}</CardTitle>
                        <CardDescription>
                          {item.competency_id
                            ? `Competency: ${item.competency_id}`
                            : "Reviewer-approved"}
                        </CardDescription>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {item.description && (
                      <p className="text-sm text-muted-foreground">{item.description}</p>
                    )}
                    {item.resources.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        No approved resources attached to this item yet.
                      </p>
                    ) : (
                      <ul className="divide-y divide-border rounded-2xl border border-border">
                        {item.resources.map((r) => (
                          <li key={r.id} className="flex items-center justify-between px-4 py-3">
                            <div className="min-w-0">
                              <a
                                className="text-sm font-medium text-foreground underline-offset-4 hover:underline"
                                href={r.url}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                {r.title}
                                <ExternalLink className="ml-1 inline h-3 w-3" aria-hidden />
                              </a>
                              {r.provider && (
                                <p className="text-xs text-muted-foreground">{r.provider}</p>
                              )}
                            </div>
                            <Badge variant="secondary">Approved</Badge>
                          </li>
                        ))}
                      </ul>
                    )}
                  </CardContent>
                </Card>
              </li>
            ))}
          </ol>
        )}
      </PageBody>
    </>
  );
}
