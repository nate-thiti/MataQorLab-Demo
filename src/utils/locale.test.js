import { describe, expect, it } from 'vitest';
import {
  DEFAULT_LOCALE,
  getClientLocale,
  getLocaleFromPath,
  replacePathLocale,
} from './locale.js';

describe('locale routing helpers', () => {
  it('detects supported locales from a path', () => {
    expect(getLocaleFromPath('/en/dashboard')).toBe('en');
    expect(getLocaleFromPath('/th/dashboard')).toBe('th');
  });

  it('replaces an existing locale without changing the rest of the path', () => {
    expect(replacePathLocale('/th/files/preview/report.csv', 'en')).toBe(
      '/en/files/preview/report.csv',
    );
  });

  it('adds a locale to an unprefixed path and falls back safely', () => {
    expect(replacePathLocale('/pricing', 'en')).toBe('/en/pricing');
    expect(replacePathLocale('/', 'unsupported')).toBe(`/${DEFAULT_LOCALE}`);
  });

  it('uses the default locale outside a browser document', () => {
    expect(getClientLocale()).toBe(DEFAULT_LOCALE);
  });
});
