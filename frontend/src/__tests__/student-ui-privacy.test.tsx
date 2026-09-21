import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  QuestionHeader,
  resolveCurrentQuestion,
} from "@/routes/_authenticated/assessment.$attemptId.interview";
import { resolveEvidenceBundles } from "@/lib/api/evidence";
import { summarizeProcessing } from "@/lib/processing";
import type { PersistedInterviewQuestion, ReportResponse } from "@/lib/api/types";

describe("student interview question", () => {
  it("does not expose the internal question-selection reason", () => {
    const question: PersistedInterviewQuestion = {
      id: "11111111-1111-1111-1111-111111111111",
      attempt_id: "22222222-2222-2222-2222-222222222222",
      question_template_id: "da_core_01",
      competency_id: "data_analysis_sql",
      prompt_snapshot: "Explain how you would investigate a drop in monthly active users.",
      is_follow_up: false,
      sequence_number: 1,
      selection_reason: "INTERNAL HYBRID RAG AUDIT DETAILS",
      created_at: "2026-09-11T00:00:00Z",
    };

    const html = renderToStaticMarkup(<QuestionHeader question={question} />);

    expect(html).toContain(question.prompt_snapshot);
    expect(html).not.toContain("INTERNAL HYBRID RAG AUDIT DETAILS");
    expect(html).not.toContain("Why:");
  });

  it("does not keep a stale recordable question visible after next-question fails", () => {
    const question: PersistedInterviewQuestion = {
      id: "11111111-1111-1111-1111-111111111111",
      attempt_id: "22222222-2222-2222-2222-222222222222",
      question_template_id: "gemini:data_analysis_sql:example",
      competency_id: "data_analysis_sql",
      prompt_snapshot: "Explain how you would verify whether a metric drop is real.",
      is_follow_up: true,
      sequence_number: 2,
      selection_reason: "Internal audit details",
      created_at: "2026-09-14T00:00:00Z",
    };
    const cached = {
      question,
      awaiting_answer: true,
      message: "A new grounded Gemini-RAG adaptive question is ready.",
    };

    expect(resolveCurrentQuestion(cached, false)).toBe(question);
    expect(resolveCurrentQuestion(cached, true)).toBeNull();
  });

  it("offers evidence-backed submission only after the six-answer threshold", () => {
    const routeSource = readFileSync(
      new URL("../routes/_authenticated/assessment.$attemptId.processing.tsx", import.meta.url),
      "utf8",
    );

    const jobs = Array.from({ length: 6 }, (_, index) => ({
      id: `job-${index}`,
      attempt_id: "22222222-2222-2222-2222-222222222222",
      answer_id: `answer-${index}`,
      job_type: "answer_preprocessing" as const,
      status: "succeeded" as const,
      stage: "complete",
      attempt_count: 1,
      max_attempts: 3,
      error_code: null,
      error_detail: null,
      queued_at: "2026-09-11T00:00:00Z",
      started_at: "2026-09-11T00:00:01Z",
      finished_at: "2026-09-11T00:00:02Z",
      updated_at: "2026-09-11T00:00:00Z",
    }));

    expect(routeSource).not.toContain("Finish and process");
    expect(summarizeProcessing(jobs.slice(0, 5), "interviewing").canFinishInterview).toBe(false);
    expect(summarizeProcessing(jobs, "interviewing").canFinishInterview).toBe(true);
    expect(routeSource).toContain("Submit interview & view report");
    expect(routeSource).toContain("any unassessed competencies are clearly");
  });

  it("groups duplicate competency evidence into complete persisted answer bundles", () => {
    const report = {
      attempt_id: "22222222-2222-2222-2222-222222222222",
      status: "completed",
      scorecard: null,
      evidence_nodes: [
        {
          id: "evidence:answer-1",
          kind: "EvidenceClaim",
          competency_id: "api_design",
          label: "Explained input validation",
          criterion_evidence: [
            {
              criterion: "Validation",
              score: 0.75,
              rationale: "The answer describes schema validation.",
            },
          ],
          missing_concepts: ["idempotency"],
        },
        {
          id: "question:answer-1",
          kind: "Question",
          question: { id: "question-1", prompt_snapshot: "How do you validate an API?" },
        },
        {
          id: "transcript:answer-1",
          kind: "TranscriptSpan",
          transcript_span: { text: "I validate the request body.", start_ms: 0, end_ms: 2500 },
        },
        {
          id: "prediction:answer-1",
          kind: "ModelPrediction",
          signal_quality: "0.92",
          model_reference: "fi_v2_mag_bert",
        },
      ],
      evidence_edges: [],
      roadmap_items: [],
      message: null,
    } satisfies ReportResponse;

    const bundles = resolveEvidenceBundles(report, ["evidence:answer-1", "evidence:answer-1"]);

    expect(bundles).toHaveLength(1);
    expect(bundles[0].question?.question?.prompt_snapshot).toContain("validate an API");
    expect(bundles[0].transcript?.transcript_span?.text).toContain("request body");
    expect(bundles[0].prediction?.model_reference).toBe("fi_v2_mag_bert");
    expect(bundles[0].primary.missing_concepts).toEqual(["idempotency"]);
  });

  it("shows progress after the first completed attempt", () => {
    const routeSource = readFileSync(
      new URL("../routes/_authenticated/progress.tsx", import.meta.url),
      "utf8",
    );

    expect(routeSource).toContain("attempts.length === 0");
    expect(routeSource).not.toContain("attempts.length < 2");
    expect(routeSource).toContain("first completed attempt establishes a baseline");
    expect(routeSource).toContain("View full report");
    expect(routeSource).toContain("View learning roadmap");
    expect(routeSource).toContain("less than 70% of the reviewed rubric");
  });

  it("does not render a navigable interview link before resume persistence succeeds", () => {
    const routeSource = readFileSync(
      new URL("../routes/_authenticated/assessment.$attemptId.resume.tsx", import.meta.url),
      "utf8",
    );

    expect(routeSource).toContain("{attached ? (");
    expect(routeSource).toContain('<Button className="w-full rounded-full" disabled>');
    expect(routeSource).not.toContain(
      '<Button asChild className="w-full rounded-full" disabled={!attached}>',
    );
  });

  it("keeps polling active jobs and offers a distinct report retry", () => {
    const routeSource = readFileSync(
      new URL("../routes/_authenticated/assessment.$attemptId.processing.tsx", import.meta.url),
      "utf8",
    );

    expect(routeSource).not.toContain("MAX_POLLS");
    expect(routeSource).toContain("return active ? POLL_MS : false");
    expect(routeSource).toContain("Retry report generation");
    expect(routeSource).toContain("without repeating the interview");
  });
});
