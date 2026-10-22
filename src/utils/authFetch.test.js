import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./supabaseClient.js', () => ({
  supabase: {
    auth: {
      getSession: vi.fn(async () => ({
        data: { session: { access_token: 'test-token' } },
      })),
    },
  },
}));

import { authFetch, getAuthHeaders } from './authFetch.js';

describe('authFetch request methods', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true })));
  });

  it('uses GET for bodyless requests', async () => {
    await authFetch('/api/v1/connections');

    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/connections',
      expect.objectContaining({ method: 'GET', body: undefined }),
    );
  });

  it('sends the active locale to backend endpoints', async () => {
    const headers = await getAuthHeaders();

    expect(headers['Accept-Language']).toBe('th');
    expect(headers['X-User-Locale']).toBe('th');
  });

  it('uses POST when a JSON body is provided', async () => {
    await authFetch('/api/v1/data-setup/scan', { body: { source_type: 'file' } });

    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/data-setup/scan',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ source_type: 'file' }),
      }),
    );
  });

  it('preserves an explicit method', async () => {
    await authFetch('/api/v1/resource', { method: 'DELETE' });

    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/resource',
      expect.objectContaining({ method: 'DELETE' }),
    );
  });
});
