import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { env, isSupabaseConfigured } from "./env";

let client: SupabaseClient | null = null;

/**
 * Returns the browser Supabase client, or null if the project has not been
 * configured with VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY.
 * Consumers must handle the null case with an honest unavailable state.
 */
export function getSupabase(): SupabaseClient | null {
  if (!isSupabaseConfigured()) return null;
  if (client) return client;
  client = createClient(env.supabaseUrl!, env.supabasePublishableKey!, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
      storageKey: "fairhireai-auth",
    },
  });
  return client;
}

export async function getAccessToken(): Promise<string | null> {
  const sb = getSupabase();
  if (!sb) return null;
  const { data } = await sb.auth.getSession();
  return data.session?.access_token ?? null;
}

export async function getUserId(): Promise<string | null> {
  const sb = getSupabase();
  if (!sb) return null;
  const { data } = await sb.auth.getUser();
  return data.user?.id ?? null;
}
