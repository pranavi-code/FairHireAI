import type { ReactNode } from "react";
import {
  AlertCircle,
  AlertTriangle,
  Inbox,
  Loader2,
  ShieldAlert,
  WifiOff,
  Wrench,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, friendlyMessage, isUnavailable } from "@/lib/api/errors";

/** Honest loading — never combined with fabricated progress. */
export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex min-h-[160px] flex-col items-center justify-center gap-2 text-sm text-muted-foreground"
    >
      <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  icon,
  action,
}: {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
        <div className="rounded-full bg-muted p-3 text-muted-foreground">
          {icon ?? <Inbox className="h-6 w-6" aria-hidden />}
        </div>
        <div>
          <h3 className="text-base font-semibold text-foreground">{title}</h3>
          {description && (
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">{description}</p>
          )}
        </div>
        {action}
      </CardContent>
    </Card>
  );
}

/**
 * The honest "not available yet" state. Rendered whenever the backend
 * returns 404 or 501 for a planned endpoint.
 */
export function UnavailableState({ feature, detail }: { feature: string; detail?: string }) {
  return (
    <Alert>
      <Wrench className="h-4 w-4" aria-hidden />
      <AlertTitle>{feature} is not available yet</AlertTitle>
      <AlertDescription>
        {detail ?? "This feature is not available from the connected backend yet."}
      </AlertDescription>
    </Alert>
  );
}

export function ErrorState({
  error,
  onRetry,
  retryLabel = "Try again",
}: {
  error: unknown;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  if (isUnavailable(error)) {
    return <UnavailableState feature="This feature" />;
  }
  const kind = error instanceof ApiError ? error.kind : "unknown";
  const Icon =
    kind === "network"
      ? WifiOff
      : kind === "unauthorized" || kind === "forbidden"
        ? ShieldAlert
        : kind === "validation"
          ? AlertTriangle
          : AlertCircle;

  return (
    <Alert variant="destructive" role="alert">
      <Icon className="h-4 w-4" aria-hidden />
      <AlertTitle>Something went wrong</AlertTitle>
      <AlertDescription className="space-y-3">
        <p>{friendlyMessage(error)}</p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center justify-center rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium text-foreground transition hover:bg-muted"
          >
            {retryLabel}
          </button>
        )}
      </AlertDescription>
    </Alert>
  );
}

export function InfoNotice({ children }: { children: ReactNode }) {
  return (
    <Alert>
      <AlertCircle className="h-4 w-4" aria-hidden />
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  );
}

export function SafetyDisclaimer() {
  return (
    <p className="text-xs leading-relaxed text-muted-foreground">
      FairHireAI provides evidence-backed placement-readiness feedback for student self-improvement.
      It is not a hiring decision or student-ranking system.
    </p>
  );
}
