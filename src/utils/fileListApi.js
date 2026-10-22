import { authFetch } from './authFetch.js';
import { getPublicApiUrl } from './env.js';

export async function fetchFilePage({
  limit = 50,
  offset = 0,
  search = '',
} = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (search.trim()) params.set('search', search.trim());
  const response = await authFetch(
    `${getPublicApiUrl()}/api/v1/files?${params.toString()}`,
    { method: 'GET' },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || 'Could not load files');
  }
  return {
    files: payload.files || [],
    hasMore: Boolean(payload.has_more),
    nextOffset: payload.next_offset ?? null,
  };
}
