import { describe, expect, it } from 'vitest';
import {
  isModelModeAllowed,
  normalizePlanName,
  resolveModelModeForPlan,
} from './modelModeAccess.js';

describe('model mode plan access', () => {
  it('limits Free to Fast mode', () => {
    expect(isModelModeAllowed('fast', 'Free')).toBe(true);
    expect(isModelModeAllowed('auto', 'Free')).toBe(false);
    expect(isModelModeAllowed('deep', 'Free')).toBe(false);
    expect(resolveModelModeForPlan('deep', 'Free')).toBe('fast');
  });

  it('allows Plus to use Fast and Auto', () => {
    expect(isModelModeAllowed('fast', 'Plus')).toBe(true);
    expect(isModelModeAllowed('auto', 'Plus')).toBe(true);
    expect(isModelModeAllowed('deep', 'Plus')).toBe(false);
    expect(resolveModelModeForPlan('deep', 'Plus')).toBe('auto');
  });

  it('allows Pro to use every response mode', () => {
    for (const plan of ['Pro', 'Enterprise']) {
      for (const mode of ['fast', 'auto', 'deep']) {
        expect(isModelModeAllowed(mode, plan)).toBe(true);
        expect(resolveModelModeForPlan(mode, plan)).toBe(mode);
      }
    }
  });

  it('treats missing and unknown plans as Free', () => {
    expect(normalizePlanName()).toBe('free');
    expect(resolveModelModeForPlan('unknown', 'Unknown')).toBe('fast');
  });
});
