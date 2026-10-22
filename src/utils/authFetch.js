import { supabase } from './supabaseClient.js';
import { correlationHeaders } from './correlation.js';
import { getClientLocale } from './locale.js';

/** Authorization header for authenticated backend fetch calls. */
export async function getAuthHeaders(extra = {}) {
  const { data: { session } } = await supabase.auth.getSession();
  const locale = getClientLocale();
  const headers = {
    'Content-Type': 'application/json',
    'Accept-Language': locale,
    'X-User-Locale': locale,
    ...correlationHeaders(extra),
  };
  if (session?.access_token) {
    headers.Authorization = `Bearer ${session.access_token}`;
  }
  return headers;
}

/** Authenticated backend request; bodyless calls default to GET, JSON bodies to POST. */
export async function authFetch(url, { method, body, headers: extraHeaders = {}, ...init } = {}) {
  const headers = await getAuthHeaders(extraHeaders);
  return fetch(url, {
    method: method || (body == null ? 'GET' : 'POST'),
    headers,
    body: body != null ? JSON.stringify(body) : undefined,
    ...init,
  });
}
