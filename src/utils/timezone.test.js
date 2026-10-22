import { describe, expect, it } from 'vitest';
import {
  getBrowserTimezone,
  isValidTimezone,
  nextLocalMidnightUtc,
  resolveTimezone,
} from './timezone.js';

describe('timezone helpers', () => {
  it('resolveTimezone returns UTC for invalid zones', () => {
    expect(resolveTimezone('Not/AZone')).toBe('UTC');
    expect(resolveTimezone('')).toBe('UTC');
    expect(resolveTimezone(null)).toBe('UTC');
  });

  it('isValidTimezone accepts IANA zones', () => {
    expect(isValidTimezone('Asia/Bangkok')).toBe(true);
    expect(isValidTimezone('America/New_York')).toBe(true);
    expect(isValidTimezone('Invalid/Zone')).toBe(false);
  });

  it('getBrowserTimezone returns a non-empty string', () => {
    expect(typeof getBrowserTimezone()).toBe('string');
    expect(getBrowserTimezone().length).toBeGreaterThan(0);
  });

  it('nextLocalMidnightUtc returns ISO string in the future', () => {
    const iso = nextLocalMidnightUtc('Asia/Bangkok', 1);
    expect(iso).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(new Date(iso).getTime()).toBeGreaterThan(Date.now() - 60_000);
  });

  it('nextLocalMidnightUtc falls back to UTC for bad timezone', () => {
    const iso = nextLocalMidnightUtc('Bad/Zone', 1);
    expect(new Date(iso).getTime()).toBeGreaterThan(Date.now() - 60_000);
  });

  it('weekly reset is further out than daily reset', () => {
    const daily = new Date(nextLocalMidnightUtc('UTC', 1)).getTime();
    const weekly = new Date(nextLocalMidnightUtc('UTC', 7)).getTime();
    expect(weekly).toBeGreaterThan(daily);
  });
});
