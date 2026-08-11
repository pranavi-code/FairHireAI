// Environment configuration for the FairHireAI frontend.
// Only public/publishable values are read here. Never expose service-role keys.

function readEnv(key: string): string | undefined {
  const v = (import.meta as unknown as { env?: Record<string, string | undefined> }).env?.[key];
  return v && v.length > 0 ? v : undefined;
}

export const env = {
  apiBaseUrl: readEnv("VITE_API_BASE_URL"),
  supabaseUrl: readEnv("VITE_SUPABASE_URL"),
  supabasePublishableKey: readEnv("VITE_SUPABASE_PUBLISHABLE_KEY"),
};

export const DOCUMENTS_BUCKET = "roleready-documents";
export const INTERVIEW_VIDEO_BUCKET = "roleready-interview-video";

export function isBackendConfigured(): boolean {
  return Boolean(env.apiBaseUrl);
}

export function isSupabaseConfigured(): boolean {
  return Boolean(env.supabaseUrl && env.supabasePublishableKey);
}
