import { createBrowserClient } from "@supabase/ssr";
import { getSupabaseAnonKey, getSupabaseUrl } from "./env.ts";
import { isInvalidRefreshTokenError } from "./supabaseAuthError.js";

export const supabase = createBrowserClient(getSupabaseUrl(), getSupabaseAnonKey());

export async function recoverInvalidBrowserSession(error) {
  if (!isInvalidRefreshTokenError(error)) return false;
  await supabase.auth.signOut({ scope: "local" });
  return true;
}
