import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation } from "@tanstack/react-query";
import { CheckCircle2, Clock, Loader2, XCircle, PlayCircle } from "lucide-react";
import { PageBody, PageHeader } from "@/components/app/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ErrorState, LoadingState, UnavailableState } from "@/components/app/StateViews";
import { attemptsApi, TRAINED_CHECKPOINT_REQUIRED_CODE } from "@/lib/api/endpoints";
import type { ProcessingJobView } from "@/lib/api/types";
import { ApiError, isUnavailable } from "@/lib/api/errors";
import { summarizeProcessing } from "@/lib/processing";

export const Route = createFileRoute("/_authenticated/assessment/$attemptId/processing")({
  head: () => ({
    meta: [
      { title: "Processing — FairHireAI" },
      { name: "description", content: "Track real backend processing status for your attempt." },
      { property: "og:title", content: "Processing — FairHireAI" },
      {
        property: "og:description",
        content: "Track real backend processing status for your attempt.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: ProcessingPage,
});

const POLL_MS = 3000;

function ProcessingPage() {
  const { attemptId } = Route.useParams();
  const navigate = useNavigate();

  const startProcessing = useMutation({
    mutationFn: () => attemptsApi.startProcessing(attemptId),
    onSettled: () => {
      void jobs.refetch();
      void attempt.refetch();
    },
  });
  const finishInterview = useMutation({
    mutationFn: () => attemptsApi.finishInterview(attemptId),
    onSettled: () => {
      void jobs.refetch();
      void attempt.refetch();
    },
  });

  const jobs = useQuery({
    queryKey: ["jobs", attemptId],
    queryFn: ({ signal }) => attemptsApi.jobs(attemptId, signal),
    refetchInterval: (q) => {
      const data = q.state.data;
      if (!Array.isArray(data)) return POLL_MS;
      const active = data.some(
        (j) =>
          j.status === "running" || (j.status === "queued" && j.attempt_count < j.max_attempts),
      );
      return active ? POLL_MS : false;
    },
  });
  const attempt = useQuery({
    queryKey: ["attempt", attemptId, "processing"],
    queryFn: () => attemptsApi.get(attemptId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "interviewing" || status === "failed"
        ? false
        : POLL_MS;
    },
  });

  const checkpointNotReady =
    startProcessing.isError &&
    startProcessing.error instanceof ApiError &&
    startProcessing.error.code === TRAINED_CHECKPOINT_REQUIRED_CODE;

  const list = jobs.data ?? [];
  const {
    evaluatedAnswerCount,
    hasJobs,
    hasFailed,
    hasExhaustedJob,
    retryableAnswerFailure,
    retryableReportFailure,
    allSucceeded,
    allAnswersSucceeded,
    canFinishInterview,
  } = summarizeProcessing(list, attempt.data?.status);

  return (
    <>
      <PageHeader
        eyebrow="Step 5 · Processing"
        title="Processing timeline"
        description="Real backend job status, polled at bounded intervals. No simulated timers."
        actions={
          allSucceeded && attempt.data?.status === "completed" ? (
            <Button
              className="rounded-full"
              onClick={() =>
                navigate({ to: "/assessment/$attemptId/report", params: { attemptId } })
              }
            >
              View report
            </Button>
          ) : allAnswersSucceeded && attempt.data?.status === "interviewing" ? (
            <div className="flex flex-wrap gap-2">
              <Button
                variant={canFinishInterview ? "outline" : "default"}
                className="rounded-full"
                onClick={() =>
                  navigate({ to: "/assessment/$attemptId/interview", params: { attemptId } })
                }
              >
                Continue interview
              </Button>
              {canFinishInterview && (
                <Button
                  className="rounded-full"
                  onClick={() => finishInterview.mutate()}
                  disabled={finishInterview.isPending}
                >
                  {finishInterview.isPending ? "Submitting…" : "Submit interview & view report"}
                </Button>
              )}
            </div>
          ) : retryableAnswerFailure ? (
            <Button
              className="rounded-full"
              onClick={() => startProcessing.mutate()}
              disabled={startProcessing.isPending}
            >
              {startProcessing.isPending ? "Retrying…" : "Retry failed processing"}
            </Button>
          ) : retryableReportFailure ? (
            <Button
              className="rounded-full"
              onClick={() => finishInterview.mutate()}
              disabled={finishInterview.isPending}
            >
              {finishInterview.isPending ? "Retrying…" : "Retry report generation"}
            </Button>
          ) : undefined
        }
      />
      <PageBody>
        {checkpointNotReady ? (
          <Alert>
            <AlertTitle>Training checkpoint not ready yet</AlertTitle>
            <AlertDescription>
              The backend responded that a trained model checkpoint is required to process this
              attempt and one has not been published yet. Processing has not been faked — please try
              again once the checkpoint is available.
            </AlertDescription>
          </Alert>
        ) : !hasJobs && startProcessing.isError && isUnavailable(startProcessing.error) ? (
          <UnavailableState feature="Processing" />
        ) : !hasJobs &&
          startProcessing.isError &&
          !(
            startProcessing.error instanceof ApiError && startProcessing.error.kind === "conflict"
          ) ? (
          <ErrorState
            error={startProcessing.error as ApiError}
            onRetry={() => startProcessing.mutate()}
          />
        ) : jobs.isPending ? (
          <LoadingState label="Contacting backend…" />
        ) : jobs.isError && isUnavailable(jobs.error) ? (
          <UnavailableState feature="Processing status" />
        ) : jobs.isError ? (
          <ErrorState error={jobs.error as ApiError} onRetry={() => jobs.refetch()} />
        ) : (
          <Card className="rounded-3xl">
            <CardHeader>
              <CardTitle>Jobs</CardTitle>
              <CardDescription>
                Attempt <span className="font-mono text-xs">{attemptId}</span>
                {startProcessing.data && (
                  <span className="ml-2 text-xs text-muted-foreground">
                    · {startProcessing.data.queued_job_count} job
                    {startProcessing.data.queued_job_count === 1 ? "" : "s"} queued
                    {startProcessing.data.message ? ` — ${startProcessing.data.message}` : ""}
                  </span>
                )}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {list.length === 0 ? (
                <div className="flex flex-col items-center gap-3 py-12 text-center">
                  <div className="rounded-full bg-muted p-3 text-muted-foreground">
                    <PlayCircle className="h-6 w-6" aria-hidden />
                  </div>
                  <p className="text-sm text-muted-foreground">
                    The backend has not enqueued any jobs for this attempt yet.
                  </p>
                  <Button
                    className="rounded-full"
                    onClick={() => startProcessing.mutate()}
                    disabled={startProcessing.isPending}
                  >
                    {startProcessing.isPending ? "Starting…" : "Start processing"}
                  </Button>
                </div>
              ) : (
                <>
                  <ol className="relative space-y-4 border-l border-border/70 pl-6">
                    {list.map((job) => (
                      <JobRow key={job.id} job={job} />
                    ))}
                  </ol>
                  {allSucceeded && attempt.data?.status === "interviewing" && (
                    <Alert className="mt-6">
                      <AlertTitle>Answer evaluated</AlertTitle>
                      <AlertDescription>
                        {evaluatedAnswerCount} of at most 12 answers evaluated. The bounded selector
                        can choose a justified follow-up or the next competency.
                      </AlertDescription>
                    </Alert>
                  )}
                  {canFinishInterview && (
                    <Alert className="mt-6">
                      <AlertTitle>You can submit now or continue</AlertTitle>
                      <AlertDescription>
                        The minimum of 6 evaluated answers is complete. Submitting now creates a
                        report only from collected evidence; any unassessed competencies are clearly
                        marked insufficient. You may continue up to question 12 for broader
                        coverage.
                      </AlertDescription>
                    </Alert>
                  )}
                  {allSucceeded && attempt.data?.status === "completed" && (
                    <Alert className="mt-6">
                      <AlertTitle>Evidence-backed report ready</AlertTitle>
                      <AlertDescription>
                        Scoring, skill-gap gating, and approved-resource roadmap generation are
                        complete.
                      </AlertDescription>
                    </Alert>
                  )}
                  {(hasFailed || hasExhaustedJob) && (
                    <Alert variant="destructive" className="mt-6">
                      <AlertTitle>
                        {hasExhaustedJob
                          ? "Processing needs maintenance"
                          : "Processing was interrupted"}
                      </AlertTitle>
                      <AlertDescription>
                        {hasExhaustedJob
                          ? "A job reached its retry limit and cannot remain silently queued. Its persisted error must be inspected before one controlled recovery attempt."
                          : retryableReportFailure
                            ? "Report generation was interrupted. Retry it without repeating the interview or reprocessing successful answers."
                            : "A temporary network or processing problem interrupted an answer. Use “Retry failed processing”; the existing uploaded video will be reused."}
                      </AlertDescription>
                    </Alert>
                  )}
                  {hasFailed && startProcessing.isError && (
                    <div className="mt-6">
                      <ErrorState
                        error={startProcessing.error as ApiError}
                        onRetry={() => startProcessing.mutate()}
                      />
                    </div>
                  )}
                  {finishInterview.isError && (
                    <div className="mt-6">
                      <ErrorState
                        error={finishInterview.error as ApiError}
                        onRetry={() => finishInterview.mutate()}
                      />
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        )}
      </PageBody>
    </>
  );
}

function JobRow({ job }: { job: ProcessingJobView }) {
  const Icon =
    job.status === "succeeded"
      ? CheckCircle2
      : job.status === "failed" || job.status === "cancelled"
        ? XCircle
        : job.status === "running"
          ? Loader2
          : Clock;

  const tone: "default" | "secondary" | "destructive" =
    job.status === "failed" || job.status === "cancelled"
      ? "destructive"
      : job.status === "succeeded"
        ? "default"
        : "secondary";

  const dotBg =
    job.status === "succeeded"
      ? "bg-success text-success-foreground"
      : job.status === "failed" || job.status === "cancelled"
        ? "bg-destructive text-destructive-foreground"
        : "bg-primary/10 text-primary";

  return (
    <li className="relative">
      <span
        className={`absolute -left-[34px] top-1 grid h-6 w-6 place-items-center rounded-full ${dotBg}`}
      >
        <Icon
          className={`h-3.5 w-3.5 ${job.status === "running" ? "animate-spin" : ""}`}
          aria-hidden
        />
      </span>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-foreground">{job.job_type}</p>
          {job.stage && <p className="text-xs text-muted-foreground">Stage: {job.stage}</p>}
          {job.error_code && (
            <p className="text-xs text-destructive">
              {job.error_code}
              {job.error_detail ? ` — ${job.error_detail}` : ""}
            </p>
          )}
          <p className="mt-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            Attempt {job.attempt_count}/{job.max_attempts} · Updated{" "}
            {new Date(job.updated_at).toLocaleTimeString()}
          </p>
        </div>
        <Badge variant={tone}>{job.status}</Badge>
      </div>
    </li>
  );
}
