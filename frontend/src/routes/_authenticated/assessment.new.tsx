import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ArrowRight, Check, FileText, Search, Sparkles } from "lucide-react";
import { PageBody, PageHeader } from "@/components/app/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  ErrorState,
  InfoNotice,
  LoadingState,
  SafetyDisclaimer,
} from "@/components/app/StateViews";
import {
  attemptsApi,
  buildAttemptJobDescriptionFromDocument,
  buildCreateAttemptPayload,
  documentsApi,
  rolesApi,
  validateDocumentSize,
} from "@/lib/api/endpoints";

import type {
  JobDescriptionUploadResponse,
  RoleCompetency,
  RoleDetectionResponse,
  RoleSummary,
  RoleTemplate,
} from "@/lib/api/types";
import { readConsentUiCache } from "@/lib/auth";
import { uploadDocument, uploadPhaseLabel, type UploadPhase } from "@/lib/storage";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_authenticated/assessment/new")({
  head: () => ({
    meta: [
      { title: "New assessment — FairHireAI" },
      {
        name: "description",
        content:
          "Choose a reviewed role, optionally tailor with a job description, and start a placement-readiness assessment.",
      },
      { property: "og:title", content: "New assessment — FairHireAI" },
      {
        property: "og:description",
        content: "Choose a reviewed role and start a placement-readiness assessment.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: NewAssessment,
});

function NewAssessment() {
  const consent = readConsentUiCache();
  const navigate = useNavigate();

  const roles = useQuery({ queryKey: ["roles"], queryFn: () => rolesApi.list() });
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    const list = roles.data ?? [];
    const q = search.trim().toLowerCase();
    if (!q) return list;
    return list.filter((r) => {
      const hay = [
        r.display_name,
        r.role_id,
        ...(r.competency_names ?? []),
        ...(r.supported_title_terms ?? []),
      ]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [roles.data, search]);

  const template = useQuery({
    queryKey: ["role", selectedRoleId],
    queryFn: () => rolesApi.get(selectedRoleId!),
    enabled: !!selectedRoleId,
  });

  const [jdFile, setJdFile] = useState<File | null>(null);
  const [jdSizeError, setJdSizeError] = useState<string | null>(null);
  const [jdUpload, setJdUpload] = useState<JobDescriptionUploadResponse | null>(null);
  const [uploadPhase, setUploadPhase] = useState<UploadPhase>("idle");
  const [uploadedJd, setUploadedJd] = useState<{
    private_jd_storage_key: string;
    jd_sha256: string;
    extracted_job_description: string;
  } | null>(null);

  const jdExtract = useMutation({
    mutationFn: async (file: File) => {
      // Detection is performed by the backend, honouring the selected role.
      // The JD upload endpoint returns both `document` and `role_mapping`.
      return documentsApi.jobDescription(file);
    },
    onSuccess: async (data, file) => {
      setJdUpload(data);
      setUploadPhase("preparing");
      try {
        const tempId = `temp-${Date.now()}`;
        const up = await uploadDocument({ file, attemptOrTempId: tempId, onPhase: setUploadPhase });
        setUploadedJd(
          buildAttemptJobDescriptionFromDocument({
            document: data.document,
            private_jd_storage_key: up.path,
          }),
        );
      } catch {
        setUploadPhase("failed");
      }
    },
  });

  // Optional server-side second-pass detection scoped to the selected role.
  // Only used if we need to reconcile after the student picks/changes their role.
  const detectWithRole = useMutation({
    mutationFn: (text: string) =>
      rolesApi.detect({ job_description: text, selected_role_id: selectedRoleId ?? undefined }),
  });

  const detection: RoleDetectionResponse | null =
    detectWithRole.data ?? jdUpload?.role_mapping ?? null;

  const create = useMutation({
    mutationFn: () => {
      if (!selectedRoleId) throw new Error("Select a role from the reviewed catalog.");
      const payload = buildCreateAttemptPayload({
        roleId: selectedRoleId,
        jd:
          jdUpload && uploadedJd && detection?.status === "detected"
            ? {
                detection,
                private_jd_storage_key: uploadedJd.private_jd_storage_key,
                jd_sha256: uploadedJd.jd_sha256,
                extracted_job_description: uploadedJd.extracted_job_description,
              }
            : null,
      });
      return attemptsApi.create(payload);
    },
    onSuccess: (attempt) => {
      navigate({ to: "/assessment/$attemptId/resume", params: { attemptId: attempt.id } });
    },
  });

  const blocked =
    (detection && detection.status !== "detected") ||
    (detection?.role_id && selectedRoleId && detection.role_id !== selectedRoleId);

  const canConfirm =
    !!consent?.requiredComplete &&
    !!selectedRoleId &&
    template.isSuccess &&
    (!jdUpload ||
      (detection?.status === "detected" && !blocked && !!uploadedJd && uploadPhase === "uploaded"));

  return (
    <>
      <PageHeader
        title="Start a new assessment"
        description="Pick a reviewed role, optionally tailor with a job description, then confirm to begin."
      />
      <PageBody>
        {!consent?.requiredComplete && (
          <div className="mb-6">
            <InfoNotice>
              Please record{" "}
              <Link to="/consent" className="font-medium underline underline-offset-2">
                required consent
              </Link>{" "}
              before starting.
            </InfoNotice>
          </div>
        )}

        <Stepper current={selectedRoleId ? (jdFile ? 3 : 2) : 1} />

        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <Card className="overflow-hidden">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-evidence" aria-hidden /> Reviewed role catalog
                </CardTitle>
                <CardDescription>
                  Search the versioned catalog and pick the role you're preparing for. Weights are
                  approved per role — never invented in the browser.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="relative">
                  <Search
                    className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
                    aria-hidden
                  />
                  <Input
                    value={search}
                    onChange={(e) => setSearch(e.currentTarget.value)}
                    placeholder="Search by role, competency or title term…"
                    className="pl-9"
                    aria-label="Search roles"
                  />
                </div>
                {roles.isPending ? (
                  <LoadingState label="Loading role catalog…" />
                ) : roles.isError ? (
                  <ErrorState error={roles.error} onRetry={() => roles.refetch()} />
                ) : filtered.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No roles matched “{search}”.</p>
                ) : (
                  <div className="grid gap-3 sm:grid-cols-2">
                    {filtered.map((r) => (
                      <RoleCard
                        key={r.role_id}
                        role={r}
                        selected={selectedRoleId === r.role_id}
                        onSelect={() => {
                          setSelectedRoleId(r.role_id);
                          // Reset JD-dependent state; any prior detection was scoped to a different role.
                          setJdFile(null);
                          setJdUpload(null);
                          setUploadedJd(null);
                          setUploadPhase("idle");
                          detectWithRole.reset();
                        }}
                      />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {selectedRoleId && (
              <Card>
                <CardHeader>
                  <CardTitle>Approved competencies</CardTitle>
                  <CardDescription>
                    Loaded from the backend role template. Weight adjustments only appear when a
                    supported JD is supplied.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {template.isPending ? (
                    <LoadingState label="Loading role template…" />
                  ) : template.isError ? (
                    <ErrorState error={template.error} onRetry={() => template.refetch()} />
                  ) : (
                    <RoleWeights
                      template={template.data}
                      detection={detection?.status === "detected" ? detection : null}
                    />
                  )}
                </CardContent>
              </Card>
            )}

            {selectedRoleId && (
              <Card>
                <CardHeader>
                  <CardTitle>Job description (optional)</CardTitle>
                  <CardDescription>
                    PDF, DOCX, TXT or MD, up to 5 MiB. Extraction, detection, and weight adjustments
                    all run on the backend.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="jd">JD file</Label>
                    <Input
                      id="jd"
                      type="file"
                      accept=".pdf,.docx,.txt,.md,application/pdf,text/plain,text/markdown"
                      onChange={(e) => {
                        const f = e.currentTarget.files?.[0] ?? null;
                        if (!f) return;
                        const sizeError = validateDocumentSize(f);
                        if (sizeError) {
                          e.currentTarget.value = "";
                          setJdFile(null);
                          setJdSizeError(sizeError);
                          return;
                        }
                        setJdSizeError(null);
                        setJdFile(f);
                        setJdUpload(null);
                        setUploadedJd(null);
                        setUploadPhase("idle");
                        detectWithRole.reset();
                        jdExtract.mutate(f, {
                          onSuccess: (data) => {
                            // Re-run detection scoped to the selected role to surface any conflict.
                            if (data.document.text) detectWithRole.mutate(data.document.text);
                          },
                        });
                      }}
                    />
                    {jdSizeError && (
                      <Alert variant="destructive" role="alert">
                        <AlertTitle>File too large</AlertTitle>
                        <AlertDescription>{jdSizeError}</AlertDescription>
                      </Alert>
                    )}
                    {jdFile && (
                      <p className="text-xs text-muted-foreground">
                        <FileText className="mr-1 inline h-3 w-3" aria-hidden />
                        {jdFile.name} · {(jdFile.size / 1024).toFixed(1)} KB
                      </p>
                    )}
                  </div>

                  {jdExtract.isPending && <LoadingState label="Extracting job description…" />}
                  {jdExtract.isError && <ErrorState error={jdExtract.error} />}

                  {uploadPhase !== "idle" && (
                    <p className="text-xs text-muted-foreground">{uploadPhaseLabel(uploadPhase)}</p>
                  )}

                  {detection && (
                    <DetectionSummary
                      detection={detection}
                      selectedRoleId={selectedRoleId}
                      extracted={jdUpload?.document.text ?? ""}
                    />
                  )}
                </CardContent>
              </Card>
            )}
          </div>

          <div className="space-y-6">
            <Card className="border-primary/20 bg-gradient-to-br from-primary/5 to-transparent">
              <CardHeader>
                <CardTitle>Confirm and start</CardTitle>
                <CardDescription>
                  Creates a real attempt on the backend and takes you to the resume step.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {!selectedRoleId && (
                  <p className="text-sm text-muted-foreground">
                    Pick a role from the catalog to continue.
                  </p>
                )}
                {blocked && detection && (
                  <Alert variant="destructive">
                    <AlertTitle>Job description conflict</AlertTitle>
                    <AlertDescription>
                      {detection.status !== "detected"
                        ? `The backend flagged the JD as ${detection.status.replace(/_/g, " ")}.`
                        : `The JD maps to "${detection.role_id}" but you selected "${selectedRoleId}".`}{" "}
                      Remove the JD or change the selected role to continue.
                    </AlertDescription>
                  </Alert>
                )}
                {create.isError && <ErrorState error={create.error} />}
                <Button
                  className="w-full"
                  disabled={!canConfirm || create.isPending}
                  onClick={() => create.mutate()}
                >
                  {create.isPending ? "Creating attempt…" : "Confirm role and start"}
                  <ArrowRight className="ml-2 h-4 w-4" aria-hidden />
                </Button>
                <p className="text-xs text-muted-foreground">
                  {uploadedJd && detection?.status === "detected" && !blocked
                    ? "The attempt will use JD-adapted weights returned by the backend."
                    : "No JD provided — the attempt will use approved base weights for the selected role."}
                </p>
              </CardContent>
            </Card>
            <SafetyDisclaimer />
          </div>
        </div>
      </PageBody>
    </>
  );
}

function Stepper({ current }: { current: 1 | 2 | 3 }) {
  const steps = ["Choose role", "Review competencies", "Confirm & start"];
  return (
    <ol className="flex flex-wrap items-center gap-3" aria-label="Setup progress">
      {steps.map((label, i) => {
        const idx = (i + 1) as 1 | 2 | 3;
        const active = current === idx;
        const done = current > idx;
        return (
          <li key={label} className="flex items-center gap-2">
            <span
              className={cn(
                "grid h-7 w-7 place-items-center rounded-full text-xs font-semibold transition",
                done && "bg-primary text-primary-foreground",
                active && "bg-primary/15 text-primary ring-2 ring-primary/40",
                !done && !active && "bg-muted text-muted-foreground",
              )}
              aria-current={active ? "step" : undefined}
            >
              {done ? <Check className="h-3.5 w-3.5" aria-hidden /> : idx}
            </span>
            <span
              className={cn(
                "text-sm",
                active ? "font-medium text-foreground" : "text-muted-foreground",
              )}
            >
              {label}
            </span>
            {i < steps.length - 1 && (
              <span className="hidden h-px w-8 bg-border sm:inline-block" aria-hidden />
            )}
          </li>
        );
      })}
    </ol>
  );
}

function RoleCard({
  role,
  selected,
  onSelect,
}: {
  role: RoleSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        "group relative flex h-full flex-col rounded-2xl border p-4 text-left transition",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
        selected
          ? "border-primary/50 bg-primary/5 shadow-sm"
          : "border-border bg-card hover:border-primary/30 hover:bg-muted/40",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-foreground">{role.display_name}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            v{role.template_version} · {role.review_status}
          </p>
        </div>
        {selected && (
          <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground">
            <Check className="h-3.5 w-3.5" aria-hidden />
          </span>
        )}
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {(role.competency_names ?? []).slice(0, 4).map((c) => (
          <Badge key={c} variant="secondary" className="text-[10px] font-medium">
            {c}
          </Badge>
        ))}
        {(role.competency_names?.length ?? 0) > 4 && (
          <Badge variant="outline" className="text-[10px]">
            +{(role.competency_names?.length ?? 0) - 4}
          </Badge>
        )}
      </div>
    </button>
  );
}

function RoleWeights({
  template,
  detection,
}: {
  template: RoleTemplate;
  detection: RoleDetectionResponse | null;
}) {
  const competencies: RoleCompetency[] = template.competencies ?? [];
  const detectedWeights = detection?.competency_weights ?? null;
  if (!competencies.length) {
    return (
      <p className="text-sm text-muted-foreground">
        The backend did not return competencies for this role.
      </p>
    );
  }
  return (
    <ul className="divide-y divide-border rounded-md border border-border">
      {competencies.map((c) => {
        const detected = detectedWeights ? detectedWeights[c.competency_id] : undefined;
        const adjusted = typeof detected === "number" && detected !== c.base_weight;
        return (
          <li key={c.competency_id} className="flex items-center justify-between px-4 py-3">
            <div className="min-w-0">
              <p className="text-sm font-medium text-foreground">{c.name}</p>
              {c.description && <p className="text-xs text-muted-foreground">{c.description}</p>}
            </div>
            <div className="text-right">
              <p className="text-sm font-semibold text-foreground">
                {formatPct(typeof detected === "number" ? detected : c.base_weight)}
              </p>
              {adjusted && typeof detected === "number" && (
                <p className="text-xs text-evidence">
                  Adjusted from base {formatPct(c.base_weight)} by the backend
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function DetectionSummary({
  detection,
  selectedRoleId,
  extracted,
}: {
  detection: RoleDetectionResponse;
  selectedRoleId: string;
  extracted: string;
}) {
  const blocked = detection.status !== "detected";
  const conflict =
    detection.status === "detected" && detection.role_id && detection.role_id !== selectedRoleId;
  const matchedByCompetency = Object.entries(detection.matched_skills_by_competency ?? {});
  return (
    <div className="space-y-3 rounded-xl border border-border bg-muted/40 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={blocked || conflict ? "destructive" : "secondary"}>
          {blocked ? detection.status.replace(/_/g, " ") : conflict ? "role conflict" : "Detected"}
        </Badge>
        {detection.display_name && (
          <span className="text-xs text-muted-foreground">
            Backend mapped: {detection.display_name} ({detection.role_id})
          </span>
        )}
        <span className="text-xs text-muted-foreground">
          Confidence: {formatPct(detection.confidence)}
        </span>
      </div>
      {detection.reason && (
        <p className="text-xs text-muted-foreground">Reason: {detection.reason}</p>
      )}
      {detection.matched_title_terms.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Matched title terms: {detection.matched_title_terms.join(", ")}
        </p>
      )}
      {detection.matched_seniority_terms.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Matched seniority terms: {detection.matched_seniority_terms.join(", ")}
        </p>
      )}
      {matchedByCompetency.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground">Matched skills by competency</p>
          <div className="mt-1 space-y-1">
            {matchedByCompetency.map(([cid, skills]) => (
              <div key={cid} className="flex flex-wrap items-center gap-1">
                <span className="text-xs text-muted-foreground">{cid}:</span>
                {skills.map((s) => (
                  <Badge key={s} variant="outline">
                    {s}
                  </Badge>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
      {extracted && (
        <details>
          <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
            View extracted JD text
          </summary>
          <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-background p-3 text-xs text-foreground">
            {extracted}
          </pre>
        </details>
      )}
    </div>
  );
}

function formatPct(n: number): string {
  if (!Number.isFinite(n)) return "—";
  return `${Math.round(n * 100)}%`;
}
