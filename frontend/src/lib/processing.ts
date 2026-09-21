import type { AttemptStatus, ProcessingJobView } from "@/lib/api/types";

export interface ProcessingSummary {
  answerJobCount: number;
  evaluatedAnswerCount: number;
  hasJobs: boolean;
  hasFailed: boolean;
  hasExhaustedJob: boolean;
  retryableAnswerFailure: boolean;
  retryableReportFailure: boolean;
  allSucceeded: boolean;
  allAnswersSucceeded: boolean;
  canFinishInterview: boolean;
}

export function summarizeProcessing(
  jobs: ProcessingJobView[],
  attemptStatus: AttemptStatus | undefined,
): ProcessingSummary {
  const answerJobs = jobs.filter((job) => job.job_type === "answer_preprocessing");
  const evaluatedAnswerCount = answerJobs.filter((job) => job.status === "succeeded").length;
  const allAnswersSucceeded =
    answerJobs.length > 0 && answerJobs.every((job) => job.status === "succeeded");
  return {
    answerJobCount: answerJobs.length,
    evaluatedAnswerCount,
    hasJobs: jobs.length > 0,
    hasFailed: jobs.some((job) => job.status === "failed"),
    hasExhaustedJob: jobs.some(
      (job) =>
        (job.status === "failed" || job.status === "queued") &&
        job.attempt_count >= job.max_attempts,
    ),
    retryableAnswerFailure: answerJobs.some(
      (job) => job.status === "failed" && job.attempt_count < job.max_attempts,
    ),
    retryableReportFailure: jobs.some(
      (job) =>
        job.job_type === "report_generation" &&
        job.status === "failed" &&
        job.attempt_count < job.max_attempts,
    ),
    allSucceeded: jobs.length > 0 && jobs.every((job) => job.status === "succeeded"),
    allAnswersSucceeded,
    canFinishInterview:
      attemptStatus === "interviewing" && allAnswersSucceeded && evaluatedAnswerCount >= 6,
  };
}
