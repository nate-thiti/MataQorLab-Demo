import { useState, useCallback } from 'react';
import { supabase } from '../../../utils/supabaseClient.js';
import {
  applyProfileQuotaReset,
  syncProfileQuotaUsage,
  formatQuotaResetTime,
} from '../../../utils/profileQuota.js';
import { t } from '../../../utils/i18n.js';

const INITIAL_PROFILE_USAGE = {
  used_today: 0,
  used_week: 0,
  daily_reset_at: null,
  weekly_reset_at: null,
  timezone: 'UTC',
};

function usageForPlan(planName, usedToday, usedWeek) {
  const planNameLower = (planName || 'Free').toLowerCase();
  return planNameLower.includes('plus') || planNameLower.includes('pro') || planNameLower.includes('enterprise')
    ? usedToday
    : usedWeek;
}

/**
 * Plan, token usage, and quota-exceeded modal state for the chat page.
 * @param {{ m: object, isEn: boolean }} options
 */
export function useChatQuota({ m, isEn }) {
  const [plan, setPlan] = useState({ name: 'Free', message_limit: 200000 });
  const [isPlanLoading, setIsPlanLoading] = useState(true);
  const [messageUsage, setMessageUsage] = useState(0);
  const [profileUsage, setProfileUsage] = useState(INITIAL_PROFILE_USAGE);
  const [quotaModal, setQuotaModal] = useState({
    show: false,
    message: '',
    used: null,
    limit: null,
    resetAt: null,
  });

  const applySyncedUsage = useCallback((synced) => {
    if (!synced) return;
    setProfileUsage({
      used_today: synced.usedToday,
      used_week: synced.usedWeek,
      daily_reset_at: synced.dailyResetAt ?? null,
      weekly_reset_at: synced.weeklyResetAt ?? null,
      timezone: synced.timezone ?? 'UTC',
    });
    setMessageUsage(usageForPlan(plan.name, synced.usedToday, synced.usedWeek));
  }, [plan.name]);

  const openQuotaExceededModal = useCallback(
    (payload, tz = profileUsage.timezone) => {
      setQuotaModal({
        show: true,
        message:
          payload.message
          || t(m, 'chat.quota_exceeded_body', 'You have reached your token quota for this period.'),
        used: payload.used ?? null,
        limit: payload.limit ?? null,
        resetAt: payload.reset_at
          ? formatQuotaResetTime(payload.reset_at, tz, isEn ? 'en-US' : 'th-TH')
          : null,
      });
    },
    [m, isEn, profileUsage.timezone],
  );

  const fetchPlanAndUsage = useCallback(async (userId) => {
    setIsPlanLoading(true);
    try {
      let usedToday = 0;
      let usedWeek = 0;
      let planData = { name: 'Free', message_limit: 200000 };

      const { data: profileData, error: profileError } = await supabase
        .from('profiles')
        .select(`
          tokens_used_today,
          tokens_used_this_week,
          daily_reset_at,
          weekly_reset_at,
          timezone,
          plans (
            name,
            message_limit
          )
        `)
        .eq('id', userId)
        .maybeSingle();

      if (!profileError && profileData) {
        if (profileData.plans) {
          planData = Array.isArray(profileData.plans)
            ? profileData.plans[0]
            : profileData.plans;
        }
        const quota = await applyProfileQuotaReset(supabase, userId, profileData);
        usedToday = quota.tokensUsedToday;
        usedWeek = quota.tokensUsedThisWeek;
        setProfileUsage({
          used_today: usedToday,
          used_week: usedWeek,
          daily_reset_at: quota.dailyResetAt,
          weekly_reset_at: quota.weeklyResetAt,
          timezone: quota.timezone || 'UTC',
        });
      } else {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const { data: usageData } = await supabase
          .from('chat_messages')
          .select('total_tokens')
          .eq('user_id', userId)
          .gte('created_at', today.toISOString());
        usedToday = usageData
          ? usageData.reduce((acc, curr) => acc + (curr.total_tokens || 0), 0)
          : 0;
        usedWeek = usedToday;
        setProfileUsage((prev) => ({
          ...prev,
          used_today: usedToday,
          used_week: usedWeek,
        }));
      }

      setPlan(planData);
      setMessageUsage(usageForPlan(planData.name, usedToday, usedWeek));
    } catch (err) {
      console.error('Error fetching plan/usage:', err);
    } finally {
      setIsPlanLoading(false);
    }
  }, []);

  const applyQuotaCheckResult = useCallback(
    (quotaCheck) => {
      if (!quotaCheck?.quota) return;
      setProfileUsage({
        used_today: quotaCheck.quota.tokensUsedToday,
        used_week: quotaCheck.quota.tokensUsedThisWeek,
        daily_reset_at: quotaCheck.quota.dailyResetAt,
        weekly_reset_at: quotaCheck.quota.weeklyResetAt,
        timezone: quotaCheck.quota.timezone || profileUsage.timezone,
      });
      setMessageUsage(
        usageForPlan(plan.name, quotaCheck.quota.tokensUsedToday, quotaCheck.quota.tokensUsedThisWeek),
      );
    },
    [plan.name, profileUsage.timezone],
  );

  const syncAfterMessage = useCallback(
    async (userId) => {
      applySyncedUsage(await syncProfileQuotaUsage(supabase, userId));
    },
    [applySyncedUsage],
  );

  return {
    plan,
    isPlanLoading,
    messageUsage,
    profileUsage,
    quotaModal,
    setQuotaModal,
    fetchPlanAndUsage,
    applySyncedUsage,
    openQuotaExceededModal,
    applyQuotaCheckResult,
    syncAfterMessage,
  };
}
