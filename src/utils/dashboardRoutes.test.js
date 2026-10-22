import { describe, expect, it } from 'vitest';
import { createLocaleRouting } from './locale.js';
import {
  buildChatPath,
  buildCustomerCenterPath,
  buildFilesPath,
  buildLegalPath,
  buildLoginPath,
  buildPaymentHistoryPath,
  buildRegisterPath,
  buildSettingsPath,
  buildVisualizationPath,
  isNavActive,
  isUuid,
  normalizeAppPath,
  parseFilesRoute,
  parseRegisterRoute,
  sanitizeRedirectPath,
} from './dashboardRoutes.js';

const TH_ROUTING = createLocaleRouting('/', '/th/chat/new');
const EN_ROUTING = createLocaleRouting('/', '/en/dashboard');
const SAMPLE_UUID = 'a1b2c3d4-e5f6-4789-a012-3456789abcde';

describe('isUuid', () => {
  it('accepts valid v4 UUIDs', () => {
    expect(isUuid(SAMPLE_UUID)).toBe(true);
    expect(isUuid('00000000-0000-4000-8000-000000000000')).toBe(true);
  });

  it('rejects invalid values', () => {
    expect(isUuid('not-a-uuid')).toBe(false);
    expect(isUuid('')).toBe(false);
    expect(isUuid(null)).toBe(false);
  });
});

describe('normalizeAppPath', () => {
  it('strips locale prefix', () => {
    expect(normalizeAppPath('/th/chat/new', '/th')).toBe('/chat/new');
    expect(normalizeAppPath('/en/files/sql', '/en')).toBe('/files/sql');
  });

  it('keeps path when prefix does not match', () => {
    expect(normalizeAppPath('/chat/new', '')).toBe('/chat/new');
  });
});

describe('sanitizeRedirectPath', () => {
  it('allows same-origin relative paths', () => {
    expect(sanitizeRedirectPath('/th/dashboard')).toBe('/th/dashboard');
  });

  it('blocks open redirects', () => {
    expect(sanitizeRedirectPath('//evil.com')).toBeNull();
    expect(sanitizeRedirectPath('https://evil.com')).toBeNull();
    expect(sanitizeRedirectPath(null)).toBeNull();
  });
});

describe('deep link builders', () => {
  it('buildChatPath with preset and file', () => {
    const url = buildChatPath(TH_ROUTING, {
      preset: 'สรุปยอดขาย',
      fileName: 'sales.csv',
    });
    expect(url).toBe('/th/chat/new?q=%E0%B8%AA%E0%B8%A3%E0%B8%B8%E0%B8%9B%E0%B8%A2%E0%B8%AD%E0%B8%94%E0%B8%82%E0%B8%B2%E0%B8%A2&file=sales.csv');
  });

  it('buildChatPath with conversation UUID', () => {
    const url = buildChatPath(TH_ROUTING, { conversationId: SAMPLE_UUID });
    expect(url).toBe(`/th/chat/${SAMPLE_UUID}`);
  });

  it('buildChatPath ignores invalid conversation id', () => {
    expect(buildChatPath(TH_ROUTING, { conversationId: 'bad-id' })).toBe('/th/chat/new');
  });

  it('buildFilesPath for sql, api, cloud, schedules, preview, and filter', () => {
    expect(buildFilesPath(TH_ROUTING, { view: 'sql' })).toBe('/th/files/sql');
    expect(buildFilesPath(TH_ROUTING, { view: 'api' })).toBe('/th/files/api');
    expect(buildFilesPath(TH_ROUTING, { view: 'cloud' })).toBe('/th/files/cloud');
    expect(buildFilesPath(TH_ROUTING, { view: 'schedules' })).toBe('/th/files/schedules');
    expect(buildFilesPath(TH_ROUTING, { previewFile: 'data.csv' })).toBe(
      '/th/files/preview/data.csv'
    );
    expect(buildFilesPath(TH_ROUTING, { filter: 'csv' })).toBe('/th/files?filter=csv');
  });

  it('buildSettingsPath for valid and invalid sections', () => {
    expect(buildSettingsPath(TH_ROUTING, 'plan')).toBe('/th/settings/plan');
    expect(buildSettingsPath(TH_ROUTING, 'analysis')).toBe('/th/settings/analysis');
    expect(buildSettingsPath(TH_ROUTING, 'memory')).toBe('/th/settings/memory');
    expect(buildSettingsPath(TH_ROUTING, 'organization')).toBe('/th/settings/organization');
    expect(buildSettingsPath(TH_ROUTING, 'invalid')).toBe('/th/settings');
  });

  it('buildVisualizationPath for library and report detail', () => {
    expect(buildVisualizationPath(TH_ROUTING)).toBe('/th/visualizations');
    expect(buildVisualizationPath(TH_ROUTING, SAMPLE_UUID)).toBe(
      `/th/visualizations/${SAMPLE_UUID}`,
    );
    expect(buildVisualizationPath(TH_ROUTING, 'bad-id')).toBe('/th/visualizations');
  });

  it('buildCustomerCenterPath creates a localized customer route', () => {
    expect(buildCustomerCenterPath(TH_ROUTING)).toBe('/th/customer-center');
    expect(buildCustomerCenterPath(EN_ROUTING)).toBe('/en/customer-center');
  });

  it('buildRegisterPath for steps and plan', () => {
    expect(buildRegisterPath(TH_ROUTING, { step: '2' })).toBe('/th/register/step/2');
    expect(buildRegisterPath(TH_ROUTING, { step: '3', planId: SAMPLE_UUID })).toBe(
      `/th/register/step/3/plan/${SAMPLE_UUID}`
    );
    expect(buildRegisterPath(TH_ROUTING, { step: '9' })).toBe('/th/register/step/1');
  });

  it('buildLoginPath with redirect and forgot', () => {
    expect(buildLoginPath(TH_ROUTING, { redirect: '/th/dashboard' })).toBe(
      '/th/login?redirect=%2Fth%2Fdashboard'
    );
    expect(buildLoginPath(TH_ROUTING, { forgot: true })).toBe('/th/login/forgot');
    expect(buildLoginPath(TH_ROUTING, { redirect: '//evil.com' })).toBe('/th/login');
  });

  it('buildLegalPath and buildPaymentHistoryPath', () => {
    expect(buildLegalPath(TH_ROUTING, 'privacy', 'overview')).toBe(
      '/th/privacy-policy/overview'
    );
    expect(buildLegalPath(TH_ROUTING, 'terms', 'billing')).toBe('/th/terms-of-service/billing');
    expect(buildPaymentHistoryPath(TH_ROUTING, SAMPLE_UUID)).toBe(
      `/th/payment-history/${SAMPLE_UUID}`
    );
    expect(buildPaymentHistoryPath(TH_ROUTING)).toBe('/th/payment-history');
  });
});

describe('route parsers (deep link hydration)', () => {
  it('parseFilesRoute from locale-prefixed paths', () => {
    expect(parseFilesRoute('/th/files/sql', '/th')).toEqual({
      view: 'sql',
      filter: 'all',
    });
    expect(parseFilesRoute('/th/files/api', '/th')).toEqual({
      view: 'api',
      filter: 'all',
    });
    expect(parseFilesRoute('/th/files/cloud', '/th')).toEqual({
      view: 'cloud',
      filter: 'all',
    });
    expect(parseFilesRoute('/th/files/schedules', '/th')).toEqual({
      view: 'schedules',
      filter: 'all',
    });
    expect(parseFilesRoute('/th/files/preview/sales%20Q1.csv', '/th')).toEqual({
      view: 'files',
      previewFile: 'sales Q1.csv',
      filter: 'all',
    });
    expect(parseFilesRoute('/en/files', '/en')).toEqual({
      view: 'files',
      filter: 'all',
    });
  });

  it('parseRegisterRoute', () => {
    expect(parseRegisterRoute('/th/register/step/2', '/th')).toEqual({
      step: '2',
      planId: null,
    });
    expect(parseRegisterRoute(`/th/register/step/3/plan/${SAMPLE_UUID}`, '/th')).toEqual({
      step: '3',
      planId: SAMPLE_UUID,
    });
    expect(parseRegisterRoute('/th/register', '/th')).toEqual({ step: '1', planId: null });
  });
});

describe('isNavActive', () => {
  it('highlights parent routes for nested paths', () => {
    expect(isNavActive('/th/chat/new', '/chat', '/th')).toBe(true);
    expect(isNavActive('/th/files/sql', '/files', '/th')).toBe(true);
    expect(isNavActive(`/th/visualizations/${SAMPLE_UUID}`, '/visualizations', '/th')).toBe(true);
    expect(isNavActive('/th/dashboard', '/dashboard', '/th')).toBe(true);
    expect(isNavActive('/th/customer-center', '/customer-center', '/th')).toBe(true);
    expect(isNavActive('/th/chat/new', '/dashboard', '/th')).toBe(false);
  });
});

describe('locale routing round-trip', () => {
  it('build then parse files path stays consistent', () => {
    const built = buildFilesPath(EN_ROUTING, { view: 'sql' });
    expect(parseFilesRoute(built, EN_ROUTING.localePrefix)).toEqual({
      view: 'sql',
      filter: 'all',
    });
  });
});
