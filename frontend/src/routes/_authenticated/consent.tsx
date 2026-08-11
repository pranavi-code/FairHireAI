import { createFileRoute, useNavigate, useRouter } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { PageBody, PageHeader } from "@/components/app/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ErrorState, SafetyDisclaimer } from "@/components/app/StateViews";
import { buildConsentPayload, POLICY_VERSION, privacyApi } from "@/lib/api/endpoints";
import type { ConsentType } from "@/lib/api/types";
import { readConsentUiCache, REQUIRED_CONSENTS, writeConsentUiCache } from "@/lib/auth";

export const Route = createFileRoute("/_authenticated/consent")({
  head: () => ({
    meta: [
      { title: "Consent — FairHireAI" },
      { name: "description", content: "Record required consent before starting an assessment." },
      { property: "og:title", content: "Consent — FairHireAI" },
      {
        property: "og:description",
        content: "Record required consent before starting an assessment.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: ConsentPage,
});

interface ConsentItem {
  type: ConsentType;
  label: string;
  description: string;
  required: boolean;
}

const ITEMS: ConsentItem[] = [
  {
    type: "privacy_notice",
    label: "Privacy notice",
    description:
      "I have read the privacy notice describing what FairHireAI collects, stores, and processes.",
    required: true,
  },
  {
    type: "resume_processing",
    label: "Resume processing",
    description:
      "Process my resume to extract evidence claims used solely for my own placement-readiness feedback.",
    required: true,
  },
  {
    type: "interview_recording",
    label: "Interview recording",
    description:
      "Record my audio and video responses during the assessment so the backend can generate evidence-backed feedback.",
    required: true,
  },
  {
    type: "external_ai_processing",
    label: "Grounded AI question and answer processing",
    description:
      "Send the transcript, frozen rubric, and only minimized resume/JD evidence to Gemini. Raw video is not sent to Gemini. This is required for the current evidence evaluator.",
    required: true,
  },
  {
    type: "research_evaluation",
    label: "Research and evaluation (optional)",
    description:
      "Allow anonymised data from my attempts to help improve rubric quality and platform evaluation. Optional and independent of the required consents.",
    required: false,
  },
];

function ConsentPage() {
  const cache = readConsentUiCache();
  const [checked, setChecked] = useState<Set<ConsentType>>(() => {
    const initial = new Set<ConsentType>(REQUIRED_CONSENTS);
    if (cache?.researchGranted) initial.add("research_evaluation");
    return initial;
  });
  const router = useRouter();
  const navigate = useNavigate();

  const mutation = useMutation({
    mutationFn: async () => {
      // Post one truthful record per consent type — including a granted:false
      // record for research_evaluation when the user did not opt in. No batching,
      // no fabricated categories array.
      const results = await Promise.all(
        ITEMS.map((item) =>
          privacyApi.saveConsent(
            buildConsentPayload({
              consent_type: item.type,
              granted: checked.has(item.type),
            }),
          ),
        ),
      );
      return results;
    },
    onSuccess: (records) => {
      const grantedTypes = records.filter((r) => r.granted).map((r) => r.consent_type);
      const requiredComplete = REQUIRED_CONSENTS.every((t) => grantedTypes.includes(t));
      writeConsentUiCache({
        grantedTypes,
        requiredComplete,
        researchGranted: grantedTypes.includes("research_evaluation"),
        externalAiGranted: grantedTypes.includes("external_ai_processing"),
        at: new Date().toISOString(),
      });
      router.invalidate();
      if (requiredComplete) navigate({ to: "/assessment/new" });
    },
  });

  const requiredAllChecked = REQUIRED_CONSENTS.every((t) => checked.has(t));

  return (
    <>
      <PageHeader
        title="Consent"
        description="One truthful record is written to the backend per consent type. Policy version is transmitted with every record. This UI never assumes prior server state."
      />
      <PageBody>
        <div className="grid gap-6 md:grid-cols-3">
          <Card className="md:col-span-2">
            <CardHeader>
              <CardTitle>Required consents</CardTitle>
              <CardDescription>
                All required consents must be granted to start an assessment. Research and
                evaluation is independent and optional.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {ITEMS.map((item) => (
                <div key={item.type} className="flex items-start gap-3">
                  <Checkbox
                    id={item.type}
                    checked={checked.has(item.type)}
                    onCheckedChange={(v) => {
                      setChecked((prev) => {
                        const next = new Set(prev);
                        if (v) next.add(item.type);
                        else next.delete(item.type);
                        return next;
                      });
                    }}
                  />
                  <div className="min-w-0">
                    <Label htmlFor={item.type} className="text-sm font-medium">
                      {item.label}
                      {!item.required && (
                        <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-xs font-normal text-muted-foreground">
                          optional
                        </span>
                      )}
                    </Label>
                    <p className="mt-1 text-sm text-muted-foreground">{item.description}</p>
                  </div>
                </div>
              ))}

              {mutation.isError && <ErrorState error={mutation.error} />}

              {cache?.requiredComplete && (
                <Alert>
                  <AlertTitle>UI cache only</AlertTitle>
                  <AlertDescription>
                    A previous grant was recorded on this device at{" "}
                    {new Date(cache.at).toLocaleString()}. This is a local UI cache used to gate
                    navigation — the backend remains the sole source of truth. Saving again writes
                    fresh consent records.
                  </AlertDescription>
                </Alert>
              )}

              <div className="flex flex-wrap gap-3 pt-2">
                <Button
                  onClick={() => mutation.mutate()}
                  disabled={!requiredAllChecked || mutation.isPending}
                >
                  {mutation.isPending ? "Recording…" : "Record consent and continue"}
                </Button>
                <Button variant="outline" onClick={() => navigate({ to: "/dashboard" })}>
                  Not now
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">Policy version: {POLICY_VERSION}</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Your control</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              <p>
                Documents and recordings are stored in private buckets under your user account only.
              </p>
              <p>You can revoke any consent or request data deletion from the Privacy page.</p>
              <SafetyDisclaimer />
            </CardContent>
          </Card>
        </div>
      </PageBody>
    </>
  );
}
