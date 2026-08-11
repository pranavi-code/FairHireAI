import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { FileText, UploadCloud, CheckCircle2 } from "lucide-react";
import { PageBody, PageHeader } from "@/components/app/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ErrorState, SafetyDisclaimer, UnavailableState } from "@/components/app/StateViews";
import {
  attemptsApi,
  documentsApi,
  groupResumeClaims,
  isLowConfidence,
  RESUME_CLAIM_TYPES,
  validateDocumentSize,
} from "@/lib/api/endpoints";
import type { AttachResumeResponse, ResumeClaim, ResumeUploadResponse } from "@/lib/api/types";
import { ApiError, isUnavailable } from "@/lib/api/errors";
import { uploadDocument, uploadPhaseLabel, type UploadPhase } from "@/lib/storage";

export const Route = createFileRoute("/_authenticated/assessment/$attemptId/resume")({
  head: () => ({
    meta: [
      { title: "Resume evidence — FairHireAI" },
      {
        name: "description",
        content: "Upload a resume and review real extracted evidence claims.",
      },
      { property: "og:title", content: "Resume evidence — FairHireAI" },
      {
        property: "og:description",
        content: "Upload a resume and review real extracted evidence claims.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: ResumePage,
});

function ResumePage() {
  const { attemptId } = Route.useParams();
  const [file, setFile] = useState<File | null>(null);
  const [sizeError, setSizeError] = useState<string | null>(null);
  const [resume, setResume] = useState<ResumeUploadResponse | null>(null);
  const [uploadPhase, setUploadPhase] = useState<UploadPhase>("idle");
  const [attached, setAttached] = useState<AttachResumeResponse | null>(null);

  const upload = useMutation({
    mutationFn: async (resumeFile: File) => {
      setAttached(null);
      setResume(null);
      const extracted = await documentsApi.resume(resumeFile);
      setResume(extracted);
      const stored = await uploadDocument({
        file: resumeFile,
        attemptOrTempId: attemptId,
        onPhase: setUploadPhase,
      });
      return attemptsApi.attachResume(attemptId, {
        private_resume_storage_key: stored.path,
        mime_type: resumeFile.type || "application/octet-stream",
        evidence: extracted.evidence,
      });
    },
    onSuccess: (res) => setAttached(res),
    onError: () => setAttached(null),
  });

  return (
    <>
      <PageHeader
        eyebrow="Step 3 · Resume"
        title="Resume evidence workspace"
        description="Backend extraction only — this workspace displays real claims and exact source text returned by the API."
      />
      <PageBody>
        <div className="grid gap-6 lg:grid-cols-5">
          <div className="space-y-6 lg:col-span-3">
            <Card className="rounded-3xl overflow-hidden">
              <div className="relative bg-aurora">
                <div className="p-6 sm:p-8">
                  <div className="flex items-start gap-4">
                    <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-[image:var(--gradient-primary)] text-primary-foreground shadow-elegant">
                      <UploadCloud className="h-5 w-5" aria-hidden />
                    </div>
                    <div className="min-w-0">
                      <h2 className="text-lg font-semibold text-foreground">Upload your resume</h2>
                      <p className="mt-1 text-sm text-muted-foreground">
                        PDF, DOCX, TXT or MD, up to 5 MiB. The backend extracts evidence claims;
                        upload state uses discrete phases because byte progress is unavailable from
                        the storage client.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
              <CardContent className="space-y-4 pt-6">
                <div className="space-y-2">
                  <Label htmlFor="resume">Resume file</Label>
                  <Input
                    id="resume"
                    type="file"
                    accept=".pdf,.docx,.txt,.md,application/pdf,text/plain,text/markdown"
                    onChange={(e) => {
                      const selected = e.currentTarget.files?.[0] ?? null;
                      if (!selected) return;
                      const err = validateDocumentSize(selected);
                      if (err) {
                        e.currentTarget.value = "";
                        setFile(null);
                        setSizeError(err);
                        return;
                      }
                      setSizeError(null);
                      setFile(selected);
                      setUploadPhase("idle");
                      upload.mutate(selected);
                    }}
                  />
                  {sizeError && (
                    <Alert variant="destructive" role="alert">
                      <AlertTitle>File too large</AlertTitle>
                      <AlertDescription>{sizeError}</AlertDescription>
                    </Alert>
                  )}
                  {file && (
                    <p className="text-xs text-muted-foreground">
                      <FileText className="mr-1 inline h-3 w-3" aria-hidden />
                      {file.name} · {(file.size / 1024).toFixed(1)} KB
                    </p>
                  )}
                </div>

                {upload.isPending && (
                  <p className="text-sm text-muted-foreground">
                    {uploadPhase === "idle"
                      ? "Extracting resume evidence…"
                      : uploadPhaseLabel(uploadPhase)}
                  </p>
                )}
                {uploadPhase !== "idle" && !upload.isPending && (
                  <p className="text-xs text-muted-foreground">{uploadPhaseLabel(uploadPhase)}</p>
                )}

                {upload.isError && isUnavailable(upload.error) ? (
                  <UnavailableState
                    feature="Resume attach"
                    detail="The backend extracted resume evidence, but the attempt attach endpoint is unavailable. Persistence is not claimed until that endpoint accepts the resume metadata."
                  />
                ) : upload.isError ? (
                  <ErrorState error={upload.error as ApiError} />
                ) : null}

                {attached && (
                  <Alert>
                    <CheckCircle2 className="h-4 w-4" aria-hidden />
                    <AlertTitle>Resume attached to attempt</AlertTitle>
                    <AlertDescription className="space-y-1 text-sm">
                      <p>
                        Backend accepted <strong>{attached.claim_count}</strong> claim(s).
                        Extraction status: <strong>{attached.extraction_status}</strong>.
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Resume document ID:{" "}
                        <span className="font-mono">{attached.resume_document_id}</span>
                      </p>
                    </AlertDescription>
                  </Alert>
                )}
              </CardContent>
            </Card>

            {resume && <ResumeEvidenceView claims={resume.evidence.claims ?? []} />}
          </div>

          <div className="space-y-6 lg:col-span-2">
            <Card className="rounded-3xl border-primary/20 bg-gradient-to-br from-primary/5 to-transparent">
              <CardHeader>
                <CardTitle>Continue to interview</CardTitle>
                <CardDescription>
                  Available after the backend accepts and persists the resume metadata.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <Button asChild className="w-full rounded-full" disabled={!attached}>
                  <Link to="/assessment/$attemptId/interview" params={{ attemptId }}>
                    Continue to interview
                  </Link>
                </Button>
                {!attached && (
                  <p className="text-xs text-muted-foreground">
                    No persistence is claimed until the backend attach endpoint succeeds.
                  </p>
                )}
              </CardContent>
            </Card>
            <SafetyDisclaimer />
          </div>
        </div>
      </PageBody>
    </>
  );
}

function ResumeEvidenceView({ claims }: { claims: ResumeClaim[] }) {
  if (claims.length === 0) {
    return (
      <Card className="rounded-3xl">
        <CardHeader>
          <CardTitle>Extracted evidence</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            The backend did not return resume evidence claims.
          </p>
        </CardContent>
      </Card>
    );
  }

  const grouped = groupResumeClaims(claims);

  return (
    <Card className="rounded-3xl">
      <CardHeader>
        <CardTitle>Extracted evidence</CardTitle>
        <CardDescription>
          Grouped for display by claim type. Each row shows the exact returned source text, page and
          confidence.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {RESUME_CLAIM_TYPES.map((type) => {
          const groupClaims = grouped[type];
          return (
            <section key={type} className="space-y-2">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold capitalize text-foreground">{type}</h2>
                <Badge variant="outline" className="text-[10px]">
                  {groupClaims.length}
                </Badge>
              </div>
              {groupClaims.length === 0 ? (
                <p className="text-xs text-muted-foreground">No claims returned for this group.</p>
              ) : (
                <ul className="space-y-2">
                  {groupClaims.map((claim) => (
                    <ClaimRow key={claim.claim_id} claim={claim} />
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </CardContent>
    </Card>
  );
}

function ClaimRow({ claim }: { claim: ResumeClaim }) {
  const low = isLowConfidence(claim);
  return (
    <li className="space-y-2 rounded-2xl border border-border/70 bg-card/60 p-4">
      <p className="text-sm font-medium text-foreground">{claim.normalized_text}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={low ? "destructive" : "secondary"}>
          Confidence {formatPct(claim.confidence)}
        </Badge>
        {low && <Badge variant="outline">Low confidence</Badge>}
        {claim.source.page !== null && claim.source.page !== undefined && (
          <span className="text-xs text-muted-foreground">Page {claim.source.page}</span>
        )}
      </div>
      <p className="whitespace-pre-wrap rounded-lg bg-muted/60 p-3 text-sm text-foreground">
        {claim.source.source_text || "Source text unavailable from backend."}
      </p>
    </li>
  );
}

function formatPct(v: number): string {
  if (!Number.isFinite(v)) return "—";
  return `${Math.round(v * 100)}%`;
}
