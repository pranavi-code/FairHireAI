import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Info, Target } from "lucide-react";
import { PageBody, PageHeader } from "@/components/app/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  ErrorState,
  LoadingState,
  UnavailableState,
  SafetyDisclaimer,
} from "@/components/app/StateViews";
import { attemptsApi } from "@/lib/api/endpoints";
import {
  normalizedEvidenceKind,
  resolveEvidenceBundles,
  type EvidenceBundle,
} from "@/lib/api/evidence";
import type { EvidenceNode, ReportResponse, Scorecard } from "@/lib/api/types";
import { ApiError, isUnavailable } from "@/lib/api/errors";

export const Route = createFileRoute("/_authenticated/assessment/$attemptId/report")({
  head: () => ({
    meta: [
      { title: "Report — FairHireAI" },
      { name: "description", content: "Your evidence-backed placement-readiness report." },
      { property: "og:title", content: "Report — FairHireAI" },
      { property: "og:description", content: "Your evidence-backed placement-readiness report." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: ReportPage,
});

function ReportPage() {
  const { attemptId } = Route.useParams();
  const report = useQuery({
    queryKey: ["report", attemptId],
    queryFn: () => attemptsApi.report(attemptId),
  });
  const [openIds, setOpenIds] = useState<string[]>([]);

  return (
    <>
      <PageHeader
        eyebrow="Step 6 · Report"
        title="Placement-readiness report"
        description="Rendered directly from backend output. No values are calculated or invented in your browser."
        actions={
          <Button asChild variant="outline" className="rounded-full">
            <Link to="/assessment/$attemptId/roadmap" params={{ attemptId }}>
              View roadmap
            </Link>
          </Button>
        }
      />
      <PageBody>
        {report.isPending ? (
          <LoadingState label="Loading report…" />
        ) : report.isError && isUnavailable(report.error) ? (
          <UnavailableState feature="Report" />
        ) : report.isError ? (
          <ErrorState error={report.error as ApiError} onRetry={() => report.refetch()} />
        ) : (
          <ReportView
            data={report.data}
            onOpenEvidence={(ids) => setOpenIds(Array.isArray(ids) ? ids : [ids])}
          />
        )}

        <EvidenceDrawer data={report.data} openIds={openIds} onClose={() => setOpenIds([])} />

        <div className="mt-10">
          <SafetyDisclaimer />
        </div>
      </PageBody>
    </>
  );
}

function ReportView({
  data,
  onOpenEvidence,
}: {
  data: ReportResponse;
  onOpenEvidence: (ids: string | string[]) => void;
}) {
  const sc: Scorecard | null = data.scorecard ?? null;
  const readiness = sc?.placement_readiness ?? null;
  const insufficiency = sc?.insufficiency_reasons ?? [];
  const base = sc?.base_multimodal_interview_signal ?? null;
  const competencies = sc?.competencies ?? [];
  const delivery = sc?.delivery_signal ?? null;
  const skillGaps = data.evidence_nodes.filter(
    (node) => node.kind.replace(/[_\s-]/g, "").toLowerCase() === "skillgap",
  );
  const competencyNames = new Map(
    competencies.map((competency) => [competency.competency_id, competency.name]),
  );

  if (!sc) {
    return (
      <Alert>
        <AlertTitle>Report not ready</AlertTitle>
        <AlertDescription>
          {data.message ??
            "The backend has not produced a scorecard for this attempt yet. Nothing has been fabricated."}
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        <Card className="rounded-3xl">
          <CardHeader>
            <CardTitle>Placement readiness</CardTitle>
            <CardDescription>
              A single readiness value if the backend has enough evidence. Otherwise, insufficiency
              reasons are shown honestly.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {readiness === null ? (
              <Alert>
                <AlertTitle>Placement readiness is unavailable</AlertTitle>
                <AlertDescription>
                  <p className="mb-2">
                    The backend reported insufficient evidence to compute a readiness value.
                  </p>
                  {insufficiency.length > 0 && (
                    <ul className="list-inside list-disc space-y-1 text-sm">
                      {insufficiency.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  )}
                </AlertDescription>
              </Alert>
            ) : (
              <div className="flex items-baseline gap-3">
                <span className="text-5xl font-semibold tracking-tight text-foreground">
                  {formatPct(readiness)}
                </span>
                <span className="text-sm text-muted-foreground">
                  Not a hiring or ranking outcome — for self-improvement only.
                </span>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="rounded-3xl">
          <CardHeader>
            <CardTitle>Competency breakdown</CardTitle>
            <CardDescription>
              Server-provided weights and scores. Open evidence to inspect the backing artefacts.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {competencies.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No per-competency scores were returned by the backend.
              </p>
            ) : (
              <ul className="divide-y divide-border rounded-2xl border border-border">
                {competencies.map((c) => (
                  <li key={c.competency_id} className="px-4 py-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-foreground">{c.name}</p>
                        <p className="text-xs text-muted-foreground">
                          Weight {formatPct(c.weight)}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Evidence coverage {formatPct(c.coverage)}
                          {!c.sufficient_evidence && " · needs at least 70%"}
                        </p>
                      </div>
                      <div className="text-right">
                        {c.score === null || c.score === undefined ? (
                          <Badge variant="secondary">Insufficient evidence</Badge>
                        ) : (
                          <span className="text-lg font-semibold text-foreground">
                            {formatPct(c.score)}
                          </span>
                        )}
                      </div>
                    </div>
                    {c.insufficiency_reasons && c.insufficiency_reasons.length > 0 && (
                      <ul className="mt-2 list-inside list-disc text-xs text-muted-foreground">
                        {c.insufficiency_reasons.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    )}
                    {c.evidence_node_ids && c.evidence_node_ids.length > 0 && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="mt-2 h-7 rounded-full border-evidence/40 text-evidence hover:bg-evidence/10"
                        onClick={() => onOpenEvidence(c.evidence_node_ids ?? [])}
                      >
                        View evidence ({c.evidence_node_ids.length} answer
                        {c.evidence_node_ids.length === 1 ? "" : "s"})
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card className="rounded-3xl">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Target className="h-5 w-5 text-evidence" aria-hidden />
              Skill gaps
            </CardTitle>
            <CardDescription>
              Improvement areas identified by the backend from competency evidence. No gaps are
              guessed in your browser.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {skillGaps.length === 0 ? (
              <Alert>
                <AlertTitle>No skill-gap evidence available</AlertTitle>
                <AlertDescription>
                  The backend has not returned any SkillGap evidence nodes for this attempt. They
                  will appear here after the trained model and competency evaluator finish
                  processing.
                </AlertDescription>
              </Alert>
            ) : (
              <ul className="grid gap-3">
                {skillGaps.map((gap) => {
                  const details = gap.skill_gap;
                  const supportingEvidenceIds = data.evidence_nodes
                    .filter(
                      (node) =>
                        normalizedEvidenceKind(node) === "evidenceclaim" &&
                        node.competency_id === gap.competency_id,
                    )
                    .map((node) => node.id);
                  const title =
                    (gap.competency_id && competencyNames.get(gap.competency_id)) ||
                    gap.label ||
                    gap.competency_id ||
                    "Skill gap";
                  return (
                    <li key={gap.id} className="rounded-2xl border border-border bg-muted/30 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="font-semibold text-foreground">{title}</p>
                          {gap.label && gap.label !== title && (
                            <p className="mt-1 text-sm text-muted-foreground">{gap.label}</p>
                          )}
                          {details?.rationale && (
                            <p className="mt-1 text-sm text-muted-foreground">
                              {details.rationale}
                            </p>
                          )}
                        </div>
                        {typeof details?.severity === "number" && (
                          <Badge variant="secondary">
                            Gap severity {formatPct(details.severity)}
                          </Badge>
                        )}
                      </div>
                      {(typeof details?.current_score === "number" ||
                        typeof details?.target_score === "number") && (
                        <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted-foreground">
                          <span>Current evidence: {formatPct(details?.current_score)}</span>
                          <span>Target: {formatPct(details?.target_score)}</span>
                        </div>
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        className="mt-3 h-8 rounded-full border-evidence/40 text-evidence hover:bg-evidence/10"
                        onClick={() =>
                          onOpenEvidence(
                            supportingEvidenceIds.length > 0 ? supportingEvidenceIds : gap.id,
                          )
                        }
                      >
                        View supporting evidence
                        {supportingEvidenceIds.length > 0
                          ? ` (${supportingEvidenceIds.length} answer${supportingEvidenceIds.length === 1 ? "" : "s"})`
                          : ""}
                      </Button>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="space-y-6">
        <Card className="rounded-3xl">
          <CardHeader>
            <CardTitle className="text-base">Base Multimodal Interview Signal</CardTitle>
            <CardDescription>Separate from Placement Readiness.</CardDescription>
          </CardHeader>
          <CardContent>
            {base === null ? (
              <p className="text-sm text-muted-foreground">Not returned by the backend.</p>
            ) : (
              <p className="text-3xl font-semibold text-foreground">{formatPct(base)}</p>
            )}
          </CardContent>
        </Card>

        {delivery && (
          <Card className="rounded-3xl">
            <CardHeader>
              <CardTitle className="text-base">Observable delivery</CardTitle>
              <CardDescription>
                Separate measurements; not used in Placement Readiness.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <DeliveryMetric
                  label="Speaking pace"
                  value={
                    typeof delivery.words_per_minute === "number"
                      ? `${Math.round(delivery.words_per_minute)} wpm`
                      : "Unavailable"
                  }
                />
                <DeliveryMetric label="Fillers" value={formatPct(delivery.filler_rate)} />
                <DeliveryMetric
                  label="Pace + filler quality"
                  value={formatPct(delivery.pace_and_filler_quality)}
                />
                <DeliveryMetric
                  label="Voice-energy consistency"
                  value={formatPct(delivery.voice_energy_consistency)}
                />
                <DeliveryMetric label="Head stability" value={formatPct(delivery.head_stability)} />
                <DeliveryMetric
                  label="Camera-facing estimate"
                  value={formatPct(delivery.camera_facing_estimate)}
                />
              </dl>
              {delivery.note && (
                <p className="mt-1 text-xs text-muted-foreground">{delivery.note}</p>
              )}
            </CardContent>
          </Card>
        )}

        <Alert>
          <Info className="h-4 w-4" aria-hidden />
          <AlertTitle>How to read confidence</AlertTitle>
          <AlertDescription>
            Poor media quality lowers evidence confidence — not your capability. If evidence is
            missing for a competency, we say so instead of estimating.
          </AlertDescription>
        </Alert>
      </div>
    </div>
  );
}

function DeliveryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-muted/50 p-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-1 font-semibold text-foreground">{value}</dd>
    </div>
  );
}

function EvidenceDrawer({
  data,
  openIds,
  onClose,
}: {
  data: ReportResponse | undefined;
  openIds: string[];
  onClose: () => void;
}) {
  const bundles = resolveEvidenceBundles(data, openIds);
  return (
    <Sheet open={openIds.length > 0} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>Evidence</SheetTitle>
          <SheetDescription>
            Questions, transcript spans, rubric findings, and model references persisted by the
            backend for this competency.
          </SheetDescription>
        </SheetHeader>
        <div className="mt-4 space-y-5 text-sm">
          {bundles.length === 0 ? (
            <p className="text-muted-foreground">This evidence item is unavailable.</p>
          ) : (
            bundles.map((bundle, index) => (
              <EvidenceBundleView
                key={bundle.primary.id}
                bundle={bundle}
                position={index + 1}
                total={bundles.length}
              />
            ))
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function EvidenceBundleView({
  bundle,
  position,
  total,
}: {
  bundle: EvidenceBundle;
  position: number;
  total: number;
}) {
  const { primary, question, transcript, prediction } = bundle;
  const isGap = normalizedEvidenceKind(primary) === "skillgap";
  return (
    <section className="space-y-4 rounded-2xl border border-border bg-muted/20 p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-semibold text-foreground">
          {isGap ? "Skill-gap evidence" : `Answer evidence ${position}`}
        </h3>
        {total > 1 && (
          <Badge variant="secondary">
            {position} of {total}
          </Badge>
        )}
      </div>

      <EvidenceField label="Competency">{primary.competency_id ?? "Not tagged"}</EvidenceField>

      {isGap ? (
        <>
          <EvidenceField label="Current evidence score">
            {formatPct(primary.skill_gap?.current_score)}
          </EvidenceField>
          <EvidenceField label="Target score">
            {formatPct(primary.skill_gap?.target_score)}
          </EvidenceField>
          <EvidenceField label="Gap severity">
            {formatPct(primary.skill_gap?.severity)}
          </EvidenceField>
          {primary.skill_gap?.rationale && (
            <EvidenceField label="Why this is a gap">{primary.skill_gap.rationale}</EvidenceField>
          )}
        </>
      ) : (
        <>
          {question?.question?.prompt_snapshot && (
            <EvidenceField label="Question">{question.question.prompt_snapshot}</EvidenceField>
          )}
          {transcript?.transcript_span?.text && (
            <EvidenceField label="Transcript">
              <span>{transcript.transcript_span.text}</span>
              {(transcript.transcript_span.start_ms !== undefined ||
                transcript.transcript_span.end_ms !== undefined) && (
                <span className="mt-1 block text-xs text-muted-foreground">
                  {formatMs(transcript.transcript_span.start_ms)} –{" "}
                  {formatMs(transcript.transcript_span.end_ms)}
                </span>
              )}
            </EvidenceField>
          )}
          {primary.label && <EvidenceField label="Finding">{primary.label}</EvidenceField>}
          {primary.criterion_evidence && primary.criterion_evidence.length > 0 && (
            <RubricEvidence items={primary.criterion_evidence} />
          )}
          {primary.missing_concepts && primary.missing_concepts.length > 0 && (
            <EvidenceField label="Missing concepts">
              {primary.missing_concepts.join(", ")}
            </EvidenceField>
          )}
          {typeof primary.confidence === "number" && (
            <EvidenceField label="Evidence confidence">
              {formatPct(primary.confidence)}
            </EvidenceField>
          )}
          {prediction?.signal_quality && (
            <EvidenceField label="Signal quality">
              {formatStoredScore(prediction.signal_quality)}
            </EvidenceField>
          )}
          {prediction?.model_reference && (
            <EvidenceField label="Model reference">
              <span className="break-all font-mono text-xs">{prediction.model_reference}</span>
            </EvidenceField>
          )}
        </>
      )}
    </section>
  );
}

function RubricEvidence({ items }: { items: NonNullable<EvidenceNode["criterion_evidence"]> }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Rubric evidence
      </p>
      <ul className="mt-2 space-y-3">
        {items.map((item, index) => (
          <li key={`${item.criterion}-${index}`} className="rounded-xl bg-background p-3">
            <div className="flex items-start justify-between gap-3">
              <p className="font-medium text-foreground">{item.criterion}</p>
              <Badge variant="outline">{formatPct(item.score)}</Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{item.rationale}</p>
            {item.citations && item.citations.length > 0 && (
              <ul className="mt-2 space-y-1 border-l-2 border-evidence/40 pl-3 text-xs">
                {item.citations.map((citation, citationIndex) => (
                  <li key={citationIndex}>
                    “{citation.text}” ({formatSeconds(citation.start_seconds)}–
                    {formatSeconds(citation.end_seconds)})
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function EvidenceField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <div className="mt-0.5 whitespace-pre-wrap text-foreground">{children}</div>
    </div>
  );
}

function formatPct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${Math.round(v * 100)}%`;
}

function formatMs(ms: number | undefined): string {
  if (!ms && ms !== 0) return "—";
  const s = Math.floor(ms / 1000);
  const mm = Math.floor(s / 60)
    .toString()
    .padStart(2, "0");
  const ss = (s % 60).toString().padStart(2, "0");
  return `${mm}:${ss}`;
}

function formatSeconds(seconds: number): string {
  return `${seconds.toFixed(1)}s`;
}

function formatStoredScore(value: string): string {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 && parsed <= 1 ? formatPct(parsed) : value;
}
