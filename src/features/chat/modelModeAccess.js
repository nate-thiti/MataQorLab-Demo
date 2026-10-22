export const MODEL_MODE_PLAN = Object.freeze({
  fast: 'Free',
  auto: 'Plus',
  deep: 'Pro',
});

const DEFAULT_MODE_BY_PLAN = Object.freeze({
  free: 'fast',
  plus: 'auto',
  pro: 'auto',
});

export function normalizePlanName(planName) {
  const normalized = String(planName || 'Free').trim().toLowerCase();
  if (normalized.includes('pro') || normalized.includes('enterprise')) return 'pro';
  if (normalized.includes('plus')) return 'plus';
  return 'free';
}

export function isModelModeAllowed(modelMode, planName) {
  const plan = normalizePlanName(planName);
  if (modelMode === 'fast') return true;
  if (modelMode === 'auto') return plan === 'plus' || plan === 'pro';
  if (modelMode === 'deep') return plan === 'pro';
  return false;
}

export function resolveModelModeForPlan(modelMode, planName) {
  const plan = normalizePlanName(planName);
  return isModelModeAllowed(modelMode, plan)
    ? modelMode
    : DEFAULT_MODE_BY_PLAN[plan];
}
