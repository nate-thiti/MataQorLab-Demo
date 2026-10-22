/**
 * Token quota via Supabase RPC (single source of truth in Postgres).
 */

import { ensureProfileTimezone } from './timezone.js';

function mapRpcQuota(data) {
  if (!data || data.status === 'error') return null;
  return {
    tokensUsedToday: Number(data.used_today ?? 0),
    tokensUsedThisWeek: Number(data.used_week ?? 0),
    dailyResetAt: data.daily_reset_at ?? null,
    weeklyResetAt: data.weekly_reset_at ?? null,
    timezone: data.timezone ?? 'UTC',
    limit: data.limit != null ? Number(data.limit) : null,
    used: data.used != null ? Number(data.used) : null,
  };
}

export function formatQuotaResetTime(dateStr, timezone, locale = 'th-TH') {
  if (!dateStr) return null;
  const date = new Date(dateStr);
  return date.toLocaleString(locale === 'en-US' ? 'en-US' : 'th-TH', {
    timeZone: timezone || undefined,
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

export async function applyProfileQuotaReset(supabase, userId, profileData) {
  if (profileData) {
    await ensureProfileTimezone(supabase, userId, profileData);
  }

  const { data, error } = await supabase.rpc('refresh_profile_quota', {
    p_user_id: userId,
  });

  if (error) {
    console.error('refresh_profile_quota RPC failed:', error.message);
    return {
      tokensUsedToday: profileData?.tokens_used_today || 0,
      tokensUsedThisWeek: profileData?.tokens_used_this_week || 0,
      dailyResetAt: profileData?.daily_reset_at || null,
      weeklyResetAt: profileData?.weekly_reset_at || null,
      timezone: profileData?.timezone || 'UTC',
      updateData: null,
    };
  }

  const quota = mapRpcQuota(data);
  if (quota && profileData) {
    profileData.tokens_used_today = quota.tokensUsedToday;
    profileData.tokens_used_this_week = quota.tokensUsedThisWeek;
    profileData.daily_reset_at = quota.dailyResetAt;
    profileData.weekly_reset_at = quota.weeklyResetAt;
    profileData.timezone = quota.timezone;
  }

  return { ...quota, updateData: null };
}

/**
 * Pre-flight quota check before sending chat (same rules as backend).
 * @returns {{ ok: true, quota: object } | { ok: false, exceeded: object } | { ok: false, error: string }}
 */
export async function checkMessageQuota(supabase, userId) {
  const { data, error } = await supabase.rpc('check_user_message_quota', {
    p_user_id: userId,
  });

  if (error) {
    console.error('check_user_message_quota RPC failed:', error.message);
    return { ok: false, error: error.message };
  }

  if (data?.status === 'error') {
    return { ok: false, exceeded: data };
  }

  const quota = mapRpcQuota(data);
  return { ok: true, quota };
}

/** Sync usage from DB after backend recorded tokens (no local increment). */
export async function syncProfileQuotaUsage(supabase, userId) {
  const { data, error } = await supabase.rpc('refresh_profile_quota', {
    p_user_id: userId,
  });

  if (error) {
    console.error('syncProfileQuotaUsage failed:', error.message);
    return null;
  }

  const quota = mapRpcQuota(data);
  if (!quota) return null;

  return {
    usedToday: quota.tokensUsedToday,
    usedWeek: quota.tokensUsedThisWeek,
    dailyResetAt: quota.dailyResetAt,
    weeklyResetAt: quota.weeklyResetAt,
    timezone: quota.timezone,
  };
}

export async function incrementProfileTokenUsage(supabase, userId, totalTokens) {
  const { data, error } = await supabase.rpc('increment_profile_tokens', {
    p_user_id: userId,
    p_tokens: totalTokens,
  });

  if (error) {
    console.error('increment_profile_tokens RPC failed:', error.message);
    return null;
  }

  const quota = mapRpcQuota(data);
  if (!quota) return null;

  return {
    usedToday: quota.tokensUsedToday,
    usedWeek: quota.tokensUsedThisWeek,
    timezone: quota.timezone,
    dailyResetAt: quota.dailyResetAt,
    weeklyResetAt: quota.weeklyResetAt,
  };
}

export { ensureProfileTimezone, getBrowserTimezone } from './timezone.js';
export { mapRpcQuota as parseQuotaRpcPayload };
