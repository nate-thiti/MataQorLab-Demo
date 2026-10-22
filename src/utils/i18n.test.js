import { describe, expect, it } from 'vitest';
import en from '../locales/en.json';
import th from '../locales/th.json';
import { getMessages, t } from './i18n.js';

describe('i18n helpers', () => {
  it('loads the selected locale', () => {
    expect(getMessages('en').landing.login).toBe(en.landing.login);
    expect(getMessages('th').landing.login).toBe(th.landing.login);
  });

  it('uses a fallback for missing or non-string keys', () => {
    expect(t(en, 'missing.key', 'Fallback')).toBe('Fallback');
    expect(t(en, 'landing', 'Fallback')).toBe('Fallback');
  });

  it('replaces every placeholder without interpreting replacement tokens', () => {
    expect(t({ item: '{value} / {value}' }, 'item', '', { value: '$&' })).toBe(
      '$& / $&',
    );
  });
});
