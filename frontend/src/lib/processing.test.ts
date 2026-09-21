import { describe, expect, it } from "vitest";
import { summarizeProcessing } from "@/lib/processing";
import type { ProcessingJobView } from "@/lib/api/types";

function answerJob(
  index: number,
  status: ProcessingJobView["status"] = "succeeded",
  attemptCount = 1,
): ProcessingJobView {
  return {
    id: `job-${index}`,
    attempt_id: "attempt-1",
    answer_id: `answer-${index}`,
    job_type: "answer_preprocessing",
    status,
    stage: status === "succeeded" ? "complete" : "waiting_for_worker",
    attempt_count: attemptCount,
    max_attempts: 3,
    error_code: null,
    error_detail: null,
    queued_at: "2026-09-12T00:00:00Z",
    started_at: null,
    finished_at: null,
    updated_at: "2026-09-12T00:00:00Z",
  };
}

describe("processing summary", () => {
  it("does not allow submission after only five evaluated answers", () => {
    const result = summarizeProcessing(
      Array.from({ length: 5 }, (_, i) => answerJob(i)),
      "interviewing",
    );
    expect(result.evaluatedAnswerCount).toBe(5);
    expect(result.canFinishInterview).toBe(false);
  });

  it("allows submission from six through twelve evaluated answers only while interviewing", () => {
    for (const count of [6, 9, 12]) {
      expect(
        summarizeProcessing(
          Array.from({ length: count }, (_, i) => answerJob(i)),
          "interviewing",
        ).canFinishInterview,
      ).toBe(true);
    }
    expect(
      summarizeProcessing(
        Array.from({ length: 6 }, (_, i) => answerJob(i)),
        "processing",
      ).canFinishInterview,
    ).toBe(false);
  });

  it("distinguishes retryable and exhausted answer failures", () => {
    const retryable = summarizeProcessing([answerJob(1, "failed", 2)], "failed");
    expect(retryable.retryableAnswerFailure).toBe(true);
    expect(retryable.hasExhaustedJob).toBe(false);

    const exhausted = summarizeProcessing([answerJob(1, "queued", 3)], "failed");
    expect(exhausted.retryableAnswerFailure).toBe(false);
    expect(exhausted.hasExhaustedJob).toBe(true);
  });

  it("requires every answer job to succeed before submission", () => {
    const jobs = Array.from({ length: 6 }, (_, i) => answerJob(i));
    jobs[5] = answerJob(5, "running");
    const result = summarizeProcessing(jobs, "interviewing");
    expect(result.evaluatedAnswerCount).toBe(5);
    expect(result.allAnswersSucceeded).toBe(false);
    expect(result.canFinishInterview).toBe(false);
  });
});
