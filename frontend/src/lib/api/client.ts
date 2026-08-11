import { env, isBackendConfigured } from "../env";
import { getAccessToken } from "../supabase";
import { ApiError, parseFastApiDetail, type ApiErrorKind } from "./errors";

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  formData?: FormData;
  /** Attach a Supabase bearer token. Defaults to true; pass `false` for public endpoints. */
  auth?: boolean;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

function statusToKind(status: number): ApiErrorKind {
  switch (status) {
    case 401:
      return "unauthorized";
    case 403:
      return "forbidden";
    case 404:
      return "not_found";
    case 409:
      return "conflict";
    case 422:
      return "validation";
    case 501:
      return "not_implemented";
    case 503:
      return "unavailable";
    default:
      if (status >= 500) return "server";
      return "unknown";
  }
}

export async function toApiError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    const text = await res.text();
    body = text ? JSON.parse(text) : null;
  } catch {
    // non-JSON body — ignored on purpose
  }
  const { message: detailMessage, code } = parseFastApiDetail(body);
  const message = detailMessage ?? `Request failed with status ${res.status}`;
  return new ApiError(statusToKind(res.status), message, res.status, body, code);
}

export async function apiRequest<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  if (!isBackendConfigured()) {
    throw new ApiError("not_configured", "VITE_API_BASE_URL is not set");
  }
  const method = opts.method ?? (opts.body || opts.formData ? "POST" : "GET");
  const wantAuth = opts.auth ?? true;

  const headers: Record<string, string> = { ...(opts.headers ?? {}) };
  let body: BodyInit | undefined;

  if (opts.formData) {
    body = opts.formData;
    // Do NOT set Content-Type; the browser sets the multipart boundary.
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }

  if (wantAuth) {
    const token = await getAccessToken();
    if (!token) {
      throw new ApiError("unauthorized", "Sign in required for this action.", 401);
    }
    headers["Authorization"] = `Bearer ${token}`;
  }

  const url = `${env.apiBaseUrl!.replace(/\/$/, "")}${path}`;

  let res: Response;
  try {
    res = await fetch(url, { method, headers, body, signal: opts.signal });
  } catch (err) {
    throw new ApiError("network", err instanceof Error ? err.message : "Network error");
  }

  if (!res.ok) throw await toApiError(res);

  if (res.status === 204) return undefined as T;
  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await res.json()) as T;
  }
  return (await res.text()) as unknown as T;
}
