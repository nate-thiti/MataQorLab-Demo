import { afterEach, describe, expect, it, vi } from 'vitest';

const readXlsxFile = vi.fn();

vi.mock('read-excel-file/browser', () => ({ default: readXlsxFile }));
vi.mock('../../utils/authFetch.js', () => ({ authFetch: vi.fn() }));
vi.mock('../../utils/env.js', () => ({ getPublicApiUrl: () => 'https://api.example.test' }));

const { parseFileSample } = await import('./parseFileSample.js');

describe('parseFileSample Excel parsing', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    readXlsxFile.mockReset();
  });

  it('selects the strongest sheet and maps its detected header', async () => {
    readXlsxFile.mockResolvedValue([
      { sheet: 'Notes', data: [['notes'], [null]] },
      {
        sheet: 'Sales',
        data: [
          ['Monthly sales report'],
          ['month', 'revenue'],
          ['2026-01', 120],
          ['2026-02', 150],
        ],
      },
    ]);
    const supabase = {
      storage: {
        from: () => ({
          createSignedUrl: async () => ({
            data: { signedUrl: 'https://storage.example.test/sales.xlsx' },
            error: null,
          }),
        }),
      },
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      arrayBuffer: async () => new ArrayBuffer(8),
    }));

    const rows = await parseFileSample(supabase, 'user-1', 'sales.xlsx');

    expect(rows).toEqual([
      { month: '2026-01', revenue: 120 },
      { month: '2026-02', revenue: 150 },
    ]);
  });
});
