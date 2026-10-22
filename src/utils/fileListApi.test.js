import { beforeEach, describe, expect, it, vi } from 'vitest';

const authFetch = vi.fn();

vi.mock('./authFetch.js', () => ({ authFetch }));
vi.mock('./env.js', () => ({ getPublicApiUrl: () => 'https://api.example.test' }));

const { fetchFilePage } = await import('./fileListApi.js');

describe('fetchFilePage', () => {
  beforeEach(() => {
    authFetch.mockReset();
  });

  it('maps pagination and search to the owner-scoped backend endpoint', async () => {
    authFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        files: [{ name: 'sales.csv' }],
        has_more: true,
        next_offset: 75,
      }),
    });

    const page = await fetchFilePage({ limit: 25, offset: 50, search: 'sales' });

    expect(authFetch).toHaveBeenCalledWith(
      'https://api.example.test/api/v1/files?limit=25&offset=50&search=sales',
      { method: 'GET' },
    );
    expect(page).toEqual({
      files: [{ name: 'sales.csv' }],
      hasMore: true,
      nextOffset: 75,
    });
  });

  it('surfaces backend list failures', async () => {
    authFetch.mockResolvedValue({
      ok: false,
      json: async () => ({ detail: 'Inventory unavailable' }),
    });

    await expect(fetchFilePage()).rejects.toThrow('Inventory unavailable');
  });
});
