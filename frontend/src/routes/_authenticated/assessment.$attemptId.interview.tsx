import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, PlayCircle, StopCircle, Upload, Video, Radio } from "lucide-react";
import { PageBody, PageHeader } from "@/components/app/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  ErrorState,
  LoadingState,
  UnavailableState,
  SafetyDisclaimer,
} from "@/components/app/StateViews";
import { attemptsApi } from "@/lib/api/endpoints";
import type { NextQuestionResponse, PersistedInterviewQuestion } from "@/lib/api/types";
import { ApiError, isUnavailable } from "@/lib/api/errors";
import { readConsentUiCache } from "@/lib/auth";
import {
  sha256OfBlob,
  uploadInterviewVideo,
  uploadPhaseLabel,
  type UploadPhase,
} from "@/lib/storage";

export const Route = createFileRoute("/_authenticated/assessment/$attemptId/interview")({
  head: () => ({
    meta: [
      { title: "Interview studio — FairHireAI" },
      { name: "description", content: "Answer approved server-issued interview questions." },
      { property: "og:title", content: "Interview studio — FairHireAI" },
      { property: "og:description", content: "Answer approved server-issued interview questions." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: InterviewPage,
});

function InterviewPage() {
  const { attemptId } = Route.useParams();
  const consent = readConsentUiCache();
  const navigate = useNavigate();

  const attempt = useQuery({
    queryKey: ["attempt", attemptId],
    queryFn: () => attemptsApi.get(attemptId),
  });

  const nextQ = useQuery({
    queryKey: ["next-question", attemptId],
    queryFn: ({ signal }) => attemptsApi.nextQuestion(attemptId, signal),
    retry: false,
  });

  const startProcessing = useMutation({
    mutationFn: () => attemptsApi.startProcessing(attemptId),
    onSuccess: () => {
      navigate({ to: "/assessment/$attemptId/processing", params: { attemptId } });
    },
  });

  if (!consent?.requiredComplete) {
    return (
      <>
        <PageHeader title="Interview studio" />
        <PageBody>
          <Alert>
            <AlertTitle>Consent required</AlertTitle>
            <AlertDescription>
              Recording consent has not been granted on this device.{" "}
              <Link to="/consent" className="font-medium underline underline-offset-2">
                Record consent
              </Link>{" "}
              before starting the interview.
            </AlertDescription>
          </Alert>
        </PageBody>
      </>
    );
  }

  const question = resolveCurrentQuestion(nextQ.data, nextQ.isError);

  return (
    <>
      <PageHeader
        eyebrow="Step 4 · Interview"
        title="Interview studio"
        description="Focused recording studio. Questions and follow-ups are supplied by the backend — nothing is generated in your browser."
      />
      <PageBody>
        {attempt.isPending ? (
          <LoadingState label="Loading attempt…" />
        ) : attempt.isError ? (
          <ErrorState error={attempt.error as ApiError} onRetry={() => attempt.refetch()} />
        ) : (
          <div className="grid gap-6 lg:grid-cols-5">
            <div className="space-y-6 lg:col-span-3">
              <Card className="rounded-3xl overflow-hidden">
                <div className="relative bg-aurora">
                  <div className="p-6 sm:p-8">
                    {nextQ.isPending ? (
                      <LoadingState label="Fetching next question…" />
                    ) : nextQ.isError && isUnavailable(nextQ.error) ? (
                      <UnavailableState
                        feature="Adaptive interview"
                        detail="The next-question endpoint is unavailable. The interview cannot proceed until it is deployed."
                      />
                    ) : nextQ.isError ? (
                      <ErrorState error={nextQ.error as ApiError} onRetry={() => nextQ.refetch()} />
                    ) : !question ? (
                      <Alert>
                        <AlertTitle>No further questions</AlertTitle>
                        <AlertDescription>
                          {nextQ.data?.message ??
                            "The backend reports no additional questions. You can submit for processing."}
                        </AlertDescription>
                      </Alert>
                    ) : (
                      <QuestionHeader question={question} />
                    )}
                  </div>
                </div>
                {question && (
                  <CardContent className="pt-6">
                    <QuestionAnswerer
                      attemptId={attemptId}
                      question={question}
                      onSubmitted={() => startProcessing.mutate()}
                    />
                  </CardContent>
                )}
              </Card>

              {startProcessing.isError && <ErrorState error={startProcessing.error as ApiError} />}
            </div>

            <div className="space-y-6 lg:col-span-2">
              <Card className="rounded-3xl">
                <CardHeader>
                  <CardTitle className="text-base">Session</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm text-muted-foreground">
                  <p>
                    Attempt: <span className="font-mono text-xs text-foreground">{attemptId}</span>
                  </p>
                  <p>
                    Status: <Badge variant="secondary">{attempt.data?.status ?? "unknown"}</Badge>
                  </p>
                  {nextQ.isSuccess && nextQ.data?.message && (
                    <p className="text-xs">{nextQ.data.message}</p>
                  )}
                  {nextQ.isSuccess && nextQ.data && !nextQ.data.awaiting_answer && question && (
                    <p className="text-xs">Backend indicates no answer is currently expected.</p>
                  )}
                </CardContent>
              </Card>
              <SafetyDisclaimer />
            </div>
          </div>
        )}
      </PageBody>
    </>
  );
}

export function resolveCurrentQuestion(
  data: NextQuestionResponse | undefined,
  requestFailed: boolean,
): PersistedInterviewQuestion | null {
  // TanStack Query retains the last successful payload when a refetch fails.
  // Never let that stale question remain recordable beneath an error state.
  return requestFailed ? null : (data?.question ?? null);
}

export function QuestionHeader({ question }: { question: PersistedInterviewQuestion }) {
  return (
    <div className="flex items-start gap-4">
      <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-[image:var(--gradient-primary)] text-primary-foreground shadow-elegant">
        <Radio className="h-5 w-5" aria-hidden />
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge variant="secondary">#{question.sequence_number}</Badge>
          <Badge variant="outline">{question.competency_id}</Badge>
          {question.is_follow_up && <Badge variant="outline">Follow-up</Badge>}
        </div>
        <p className="mt-3 text-lg font-semibold leading-relaxed text-foreground">
          {question.prompt_snapshot}
        </p>
      </div>
    </div>
  );
}

function QuestionAnswerer({
  attemptId,
  question,
  onSubmitted,
}: {
  attemptId: string;
  question: PersistedInterviewQuestion;
  onSubmitted: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [recorder, setRecorder] = useState<MediaRecorder | null>(null);
  const [chunks, setChunks] = useState<Blob[]>([]);
  const [recorded, setRecorded] = useState<Blob | null>(null);
  const [recording, setRecording] = useState(false);
  const [deviceError, setDeviceError] = useState<string | null>(null);
  const [uploadPhase, setUploadPhase] = useState<UploadPhase>("idle");
  const [duration, setDuration] = useState<number>(0);
  const startTsRef = useRef<number>(0);

  const enable = useCallback(async () => {
    setDeviceError(null);
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      setStream(s);
      if (videoRef.current) {
        videoRef.current.srcObject = s;
        videoRef.current.muted = true;
        await videoRef.current.play().catch(() => {});
      }
    } catch (err) {
      setDeviceError(err instanceof Error ? err.message : "Could not access camera/microphone");
    }
  }, []);

  useEffect(() => {
    return () => {
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [stream]);

  function start() {
    if (!stream) return;
    const rec = new MediaRecorder(stream, { mimeType: pickMime() });
    const local: Blob[] = [];
    rec.ondataavailable = (e) => {
      if (e.data.size) local.push(e.data);
    };
    rec.onstop = () => {
      setChunks(local);
      setRecorded(new Blob(local, { type: rec.mimeType }));
      setDuration(Math.round((Date.now() - startTsRef.current) / 1000));
    };
    startTsRef.current = Date.now();
    rec.start(1000);
    setRecorder(rec);
    setRecording(true);
  }

  function stop() {
    recorder?.stop();
    setRecording(false);
  }

  function retake() {
    setRecorded(null);
    setChunks([]);
    setDuration(0);
    setUploadPhase("idle");
  }

  const submit = useMutation({
    mutationFn: async () => {
      if (!recorded) throw new Error("Nothing to submit");
      const filename = `q-${question.id}.webm`;
      const [up, sha] = await Promise.all([
        uploadInterviewVideo({
          file: recorded,
          filename,
          attemptOrTempId: attemptId,
          onPhase: setUploadPhase,
        }),
        sha256OfBlob(recorded),
      ]);
      return attemptsApi.submitAnswer(attemptId, {
        question_id: question.id,
        private_video_storage_key: up.path,
        video_sha256: sha,
        duration_seconds: duration,
      });
    },
    onSuccess: () => {
      setRecorded(null);
      setChunks([]);
      setUploadPhase("idle");
      onSubmitted();
    },
  });

  return (
    <div className="grid gap-4 md:grid-cols-5">
      <div className="md:col-span-3">
        <div className="overflow-hidden rounded-2xl border border-border bg-black/90">
          <video
            ref={videoRef}
            className="aspect-video w-full"
            playsInline
            autoPlay
            aria-label="Camera preview"
          />
        </div>
        {recorded && (
          <video
            className="mt-3 w-full rounded-2xl border border-border"
            src={URL.createObjectURL(recorded)}
            controls
            aria-label="Playback of your recording"
          />
        )}
      </div>
      <div className="space-y-3 md:col-span-2">
        {!stream && (
          <Button onClick={enable} className="w-full rounded-full">
            <Video className="mr-2 h-4 w-4" aria-hidden /> Enable camera & microphone
          </Button>
        )}
        {deviceError && (
          <Alert variant="destructive">
            <AlertTitle>Device access denied</AlertTitle>
            <AlertDescription>{deviceError}</AlertDescription>
          </Alert>
        )}
        {stream && !recording && !recorded && (
          <Button onClick={start} className="w-full rounded-full">
            <Mic className="mr-2 h-4 w-4" aria-hidden /> Start recording
          </Button>
        )}
        {recording && (
          <Button onClick={stop} variant="destructive" className="w-full rounded-full">
            <StopCircle className="mr-2 h-4 w-4" aria-hidden /> Stop
          </Button>
        )}
        {recorded && (
          <>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" className="rounded-full" onClick={retake}>
                <PlayCircle className="mr-2 h-4 w-4" aria-hidden /> Retake
              </Button>
              <Button
                className="rounded-full"
                onClick={() => submit.mutate()}
                disabled={submit.isPending || duration < 5}
              >
                <Upload className="mr-2 h-4 w-4" aria-hidden />
                {submit.isPending ? "Uploading…" : "Upload & submit"}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Duration: {duration}s · Size: {(recorded.size / (1024 * 1024)).toFixed(2)} MB ·
              Chunks: {chunks.length}
            </p>
            {duration < 5 && (
              <p className="text-xs text-destructive">
                Record at least 5 seconds before submitting.
              </p>
            )}
            {uploadPhase !== "idle" && (
              <p className="text-xs text-muted-foreground">{uploadPhaseLabel(uploadPhase)}</p>
            )}
            {submit.isError && isUnavailable(submit.error) ? (
              <UnavailableState feature="Answer submission" />
            ) : submit.isError ? (
              <ErrorState error={submit.error as ApiError} />
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}

function pickMime(): string {
  const candidates = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"];
  for (const c of candidates) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(c)) return c;
  }
  return "video/webm";
}
