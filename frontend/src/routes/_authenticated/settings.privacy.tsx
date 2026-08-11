import { createFileRoute } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { PageBody, PageHeader } from "@/components/app/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ErrorState, SafetyDisclaimer } from "@/components/app/StateViews";
import {
  buildConsentPayload,
  buildDeletionPayload,
  POLICY_VERSION,
  privacyApi,
} from "@/lib/api/endpoints";
import type { DeletionRecord } from "@/lib/api/types";
import {
  clearConsentUiCache,
  readConsentUiCache,
  REQUIRED_CONSENTS,
  writeConsentUiCache,
} from "@/lib/auth";

export const Route = createFileRoute("/_authenticated/settings/privacy")({
  head: () => ({
    meta: [
      { title: "Privacy — FairHireAI" },
      { name: "description", content: "Revoke consent or request account deletion." },
      { property: "og:title", content: "Privacy — FairHireAI" },
      { property: "og:description", content: "Revoke consent or request account deletion." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: PrivacyPage,
});

function PrivacyPage() {
  const [cache, setCache] = useState(readConsentUiCache());
  const [deletionRecord, setDeletionRecord] = useState<DeletionRecord | null>(null);

  const revoke = useMutation({
    mutationFn: async () => {
      // Post one granted:false record per required consent type.
      const records = await Promise.all(
        REQUIRED_CONSENTS.map((consent_type) =>
          privacyApi.saveConsent(buildConsentPayload({ consent_type, granted: false })),
        ),
      );
      return records;
    },
    onSuccess: () => {
      clearConsentUiCache();
      writeConsentUiCache({
        grantedTypes: [],
        requiredComplete: false,
        researchGranted: false,
        externalAiGranted: false,
        at: new Date().toISOString(),
      });
      setCache(readConsentUiCache());
    },
  });

  const deletion = useMutation({
    mutationFn: async () => privacyApi.requestDeletion(buildDeletionPayload({ scope: "account" })),
    onSuccess: (r) => setDeletionRecord(r),
  });

  return (
    <>
      <PageHeader
        title="Privacy"
        description="Manage consent and deletion. Deletion is only marked complete when the backend confirms it."
      />
      <PageBody>
        <div className="grid gap-6 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Consent (UI cache)</CardTitle>
              <CardDescription>
                There is currently no consent-history endpoint, so this reflects only the last
                successful consent write from this browser. The backend remains authoritative.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1 text-sm">
                <p className="text-muted-foreground">
                  Required consents complete:{" "}
                  <span className="font-medium text-foreground">
                    {cache?.requiredComplete ? "yes" : "no"}
                  </span>
                </p>
                <p className="text-muted-foreground">
                  Research and evaluation:{" "}
                  <span className="font-medium text-foreground">
                    {cache?.researchGranted ? "granted" : "not granted"}
                  </span>
                </p>
                {cache?.at && (
                  <p className="text-xs text-muted-foreground">
                    Local record from {new Date(cache.at).toLocaleString()} · Policy{" "}
                    {POLICY_VERSION}
                  </p>
                )}
              </div>
              {revoke.isError && <ErrorState error={revoke.error} />}
              {revoke.isSuccess && (
                <Alert>
                  <AlertTitle>Consent revoked</AlertTitle>
                  <AlertDescription>
                    A granted:false record was written for each required consent type. The backend
                    is now the source of truth for the revocation.
                  </AlertDescription>
                </Alert>
              )}
              <Button
                variant="outline"
                disabled={revoke.isPending || cache?.requiredComplete === false}
                onClick={() => revoke.mutate()}
              >
                {revoke.isPending ? "Revoking…" : "Revoke required consents"}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Delete my account data</CardTitle>
              <CardDescription>
                Submitting queues an account-scope deletion request on the backend. Attempt-scope
                deletion is only offered from within a specific attempt.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {deletion.isError && <ErrorState error={deletion.error} />}
              {deletionRecord && (
                <Alert>
                  <AlertTitle>Deletion request submitted</AlertTitle>
                  <AlertDescription className="space-y-1 text-sm">
                    <p>
                      Backend status: <strong>{deletionRecord.status}</strong>
                      {deletionRecord.completed_at ? " (completed)" : ""}
                    </p>
                    <p>
                      Requested at {new Date(deletionRecord.requested_at).toLocaleString()}.
                      {deletionRecord.error_code
                        ? ` Error code: ${deletionRecord.error_code}.`
                        : ""}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Deletion is only complete when the backend sets completed_at.
                    </p>
                  </AlertDescription>
                </Alert>
              )}
              <Button
                variant="destructive"
                disabled={deletion.isPending}
                onClick={() => deletion.mutate()}
              >
                {deletion.isPending ? "Submitting…" : "Request account deletion"}
              </Button>
            </CardContent>
          </Card>
        </div>

        <div className="mt-8">
          <SafetyDisclaimer />
        </div>
      </PageBody>
    </>
  );
}
