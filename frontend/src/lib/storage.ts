import { DOCUMENTS_BUCKET, INTERVIEW_VIDEO_BUCKET } from "./env";
import { getSupabase, getUserId } from "./supabase";

export interface UploadResult {
  bucket: string;
  path: string;
}

/**
 * Real upload phase. The Supabase JS client does NOT expose byte-level
 * progress, so we only report the actual state transitions — never a
 * fabricated percentage.
 */
export type UploadPhase = "idle" | "preparing" | "uploading" | "uploaded" | "failed";

function safeName(name: string): string {
  return name.replace(/[^a-zA-Z0-9._-]+/g, "_").slice(0, 120);
}

function randomId(): string {
  const g = (typeof globalThis !== "undefined" ? globalThis : {}) as {
    crypto?: { randomUUID?: () => string };
  };
  if (g.crypto?.randomUUID) return g.crypto.randomUUID().replace(/-/g, "").slice(0, 12);
  // Deterministic-ish fallback: timestamp only (no Math.random for state).
  return Date.now().toString(36);
}

function uniqueName(name: string): string {
  const base = safeName(name || "file");
  const ts = Date.now();
  return `${ts}-${randomId()}-${base}`;
}

async function buildKey(attemptOrTempId: string, filename: string): Promise<string> {
  const userId = await getUserId();
  if (!userId) throw new Error("Not signed in");
  return `${userId}/attempts/${attemptOrTempId}/${uniqueName(filename)}`;
}

async function uploadToBucket(params: {
  file: Blob;
  filename: string;
  attemptOrTempId: string;
  bucket: string;
  contentType?: string;
  onPhase?: (phase: UploadPhase) => void;
}): Promise<UploadResult> {
  const { file, filename, attemptOrTempId, bucket, contentType, onPhase } = params;
  const sb = getSupabase();
  if (!sb) throw new Error("Supabase is not configured");
  onPhase?.("preparing");
  const path = await buildKey(attemptOrTempId, filename);
  onPhase?.("uploading");
  const { error } = await sb.storage.from(bucket).upload(path, file, {
    contentType: contentType || file.type || "application/octet-stream",
    upsert: false,
    cacheControl: "3600",
  });
  if (error) {
    onPhase?.("failed");
    throw error;
  }
  onPhase?.("uploaded");
  return { bucket, path };
}

export function uploadDocument(params: {
  file: File;
  attemptOrTempId: string;
  onPhase?: (phase: UploadPhase) => void;
}): Promise<UploadResult> {
  return uploadToBucket({
    file: params.file,
    filename: params.file.name,
    attemptOrTempId: params.attemptOrTempId,
    bucket: DOCUMENTS_BUCKET,
    contentType: params.file.type,
    onPhase: params.onPhase,
  });
}

export function uploadInterviewVideo(params: {
  file: Blob;
  filename: string;
  attemptOrTempId: string;
  onPhase?: (phase: UploadPhase) => void;
}): Promise<UploadResult> {
  return uploadToBucket({
    file: params.file,
    filename: params.filename,
    attemptOrTempId: params.attemptOrTempId,
    bucket: INTERVIEW_VIDEO_BUCKET,
    contentType: params.file.type || "video/webm",
    onPhase: params.onPhase,
  });
}

/**
 * Compute SHA-256 of a Blob in-browser and return 64-character lowercase hex.
 * Used to build the `jd_sha256` attempt field.
 */
export async function sha256OfBlob(blob: Blob): Promise<string> {
  const buf = await blob.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export function uploadPhaseLabel(phase: UploadPhase): string {
  switch (phase) {
    case "preparing":
      return "Preparing…";
    case "uploading":
      return "Uploading to private storage…";
    case "uploaded":
      return "Uploaded";
    case "failed":
      return "Upload failed";
    default:
      return "";
  }
}
