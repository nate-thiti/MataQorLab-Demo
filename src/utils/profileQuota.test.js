import { describe, expect, it, vi } from 'vitest';
import {
  checkMessageQuota,
  formatQuotaResetTime,
  parseQuotaRpcPayload,
} from './profileQuota.js';

describe('parseQuotaRpcPayload', () => {
  it('maps ok RPC payload', () => {
    const quota = parseQuotaRpcPayload({
      status: 'ok',
      used_today: 100,
      used_week: 500,
      daily_reset_at: '2026-07-02T00:00:00.000Z',
      weekly_reset_at: '2026-07-08T00:00:00.000Z',
      timezone: 'Asia/Bangkok',
      limit: 200000,
      used: 500,
    });
    expect(quota).toEqual({
      tokensUsedToday: 100,
      tokensUsedThisWeek: 500,
      dailyResetAt: '2026-07-02T00:00:00.000Z',
      weeklyResetAt: '2026-07-08T00:00:00.000Z',
      timezone: 'Asia/Bangkok',
      limit: 200000,
      used: 500,
    });
  });

  it('returns null for error status', () => {
    expect(parseQuotaRpcPayload({ status: 'error', message: 'Quota Exceeded' })).toBeNull();
    expect(parseQuotaRpcPayload(null)).toBeNull();
  });
});

describe('formatQuotaResetTime', () => {
  it('formats with timezone and locale', () => {
    const formatted = formatQuotaResetTime(
      '2026-07-02T17:00:00.000Z',
      'Asia/Bangkok',
      'th-TH'
    );
    expect(formatted).toBeTruthy();
    expect(typeof formatted).toBe('string');
  });

  it('returns null for missing date', () => {
    expect(formatQuotaResetTime(null, 'UTC')).toBeNull();
  });
});

describe('checkMessageQuota', () => {
  it('returns ok when RPC succeeds', async () => {
    const supabase = {
      rpc: vi.fn().mockResolvedValue({
        data: {
          status: 'ok',
          used_today: 0,
          used_week: 0,
          timezone: 'UTC',
        },
        error: null,
      }),
    };

    const result = await checkMessageQuota(supabase, 'user-1');
    expect(result.ok).toBe(true);
    expect(result.quota.tokensUsedToday).toBe(0);
    expect(supabase.rpc).toHaveBeenCalledWith('check_user_message_quota', {
      p_user_id: 'user-1',
    });
  });

  it('returns exceeded when RPC reports quota error', async () => {
    const exceeded = {
      status: 'error',
      error: 'Quota Exceeded',
      message: 'Weekly limit reached',
      used: 200000,
      limit: 200000,
    };
    const supabase = {
      rpc: vi.fn().mockResolvedValue({ data: exceeded, error: null }),
    };

    const result = await checkMessageQuota(supabase, 'user-1');
    expect(result.ok).toBe(false);
    expect(result.exceeded).toEqual(exceeded);
  });

  it('returns error when RPC fails', async () => {
    const supabase = {
      rpc: vi.fn().mockResolvedValue({
        data: null,
        error: { message: 'connection failed' },
      }),
    };

    const result = await checkMessageQuota(supabase, 'user-1');
    expect(result.ok).toBe(false);
    expect(result.error).toBe('connection failed');
  });
});
