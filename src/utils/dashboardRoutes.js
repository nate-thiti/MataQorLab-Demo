import { localePath } from './locale.js';
import { PRIVACY_SECTION_ORDER, TERMS_SECTION_ORDER } from '../content/legalSections.js';

export const FILE_VIEWS = new Set(['files', 'sql', 'api', 'cloud', 'schedules']);
export const SETTINGS_SECTIONS = new Set(['plan', 'appearance', 'profile', 'security', 'analysis', 'memory', 'organization']);
export const REGISTER_STEPS = new Set(['1', '2', '3']);
export const PRIVACY_SECTIONS = new Set(PRIVACY_SECTION_ORDER);
export const TERMS_SECTIONS = new Set(TERMS_SECTION_ORDER);

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function isUuid(value) {
  return typeof value === 'string' && UUID_RE.test(value);
}

/** Strip locale prefix from pathname for route matching. */
export function normalizeAppPath(pathname = '', localePrefix = '') {
  const prefix = localePrefix || '';
  if (prefix && pathname.startsWith(prefix)) {
    const rest = pathname.slice(prefix.length);
    return rest.startsWith('/') ? rest : `/${rest}`;
  }
  return pathname.startsWith('/') ? pathname : `/${pathname}`;
}

export function buildChatPath(routing, { conversationId, preset, fileName } = {}) {
  let path = '/chat/new';
  if (conversationId && isUuid(conversationId)) {
    path = `/chat/${conversationId}`;
  }
  const params = new URLSearchParams();
  if (preset) params.set('q', preset);
  if (fileName) params.set('file', fileName);
  const qs = params.toString();
  return localePath(qs ? `${path}?${qs}` : path, routing);
}

export function buildFilesPath(routing, { view = 'files', filter, previewFile } = {}) {
  let path = '/files';
  if (view === 'sql') path = '/files/sql';
  else if (view === 'api') path = '/files/api';
  else if (view === 'cloud') path = '/files/cloud';
  else if (view === 'schedules') path = '/files/schedules';
  else if (previewFile) path = `/files/preview/${encodeURIComponent(previewFile)}`;

  const params = new URLSearchParams();
  if (filter && filter !== 'all' && !previewFile) params.set('filter', filter);
  const qs = params.toString();
  return localePath(qs ? `${path}?${qs}` : path, routing);
}

export function buildSettingsPath(routing, section) {
  if (!section || !SETTINGS_SECTIONS.has(section)) {
    return localePath('/settings', routing);
  }
  return localePath(`/settings/${section}`, routing);
}

export function buildVisualizationPath(routing, reportId) {
  if (reportId && isUuid(reportId)) {
    return localePath(`/visualizations/${reportId}`, routing);
  }
  return localePath('/visualizations', routing);
}

export function buildCustomerCenterPath(routing) {
  return localePath('/customer-center', routing);
}

export function buildRegisterPath(routing, { step = '1', planId } = {}) {
  const stepKey = String(step);
  const safeStep = REGISTER_STEPS.has(stepKey) ? stepKey : '1';
  let path = `/register/step/${safeStep}`;
  if (planId && safeStep === '3' && isUuid(planId)) {
    path += `/plan/${planId}`;
  }
  return localePath(path, routing);
}

export function buildLoginPath(routing, { forgot = false, redirect } = {}) {
  const path = forgot ? '/login/forgot' : '/login';
  const params = new URLSearchParams();
  const safeRedirect = sanitizeRedirectPath(redirect);
  if (safeRedirect) params.set('redirect', safeRedirect);
  const qs = params.toString();
  return localePath(qs ? `${path}?${qs}` : path, routing);
}

export function sanitizeRedirectPath(redirect) {
  if (!redirect || typeof redirect !== 'string') return null;
  const trimmed = redirect.trim();
  if (!trimmed.startsWith('/') || trimmed.startsWith('//')) return null;
  return trimmed;
}

export function buildLegalPath(routing, doc, section) {
  const isTerms = doc === 'terms';
  const base = isTerms ? '/terms-of-service' : '/privacy-policy';
  const allowed = isTerms ? TERMS_SECTIONS : PRIVACY_SECTIONS;
  if (section && allowed.has(section)) {
    return localePath(`${base}/${section}`, routing);
  }
  return localePath(base, routing);
}

export function buildPaymentHistoryPath(routing, paymentId) {
  if (paymentId && isUuid(paymentId)) {
    return localePath(`/payment-history/${paymentId}`, routing);
  }
  return localePath('/payment-history', routing);
}

export function parseRegisterRoute(pathname, localePrefix) {
  const path = normalizeAppPath(pathname, localePrefix);
  const match = path.match(/^\/register\/step\/([123])(?:\/plan\/([^/]+))?$/);
  if (!match) return { step: '1', planId: null };
  return { step: match[1], planId: match[2] || null };
}

export function parseFilesRoute(pathname, localePrefix) {
  const path = normalizeAppPath(pathname, localePrefix);
  const previewMatch = path.match(/^\/files\/preview\/(.+)$/);
  if (previewMatch) {
    return {
      view: 'files',
      previewFile: decodeURIComponent(previewMatch[1]),
      filter: 'all',
    };
  }
  if (path === '/files/sql') return { view: 'sql', filter: 'all' };
  if (path === '/files/api') return { view: 'api', filter: 'all' };
  if (path === '/files/cloud') return { view: 'cloud', filter: 'all' };
  if (path === '/files/schedules') return { view: 'schedules', filter: 'all' };
  return { view: 'files', filter: 'all' };
}

export function isNavActive(currentPath, itemPath, localePrefix) {
  const current = normalizeAppPath(currentPath, localePrefix);
  if (itemPath === '/dashboard') return current === '/dashboard';
  return current === itemPath || current.startsWith(`${itemPath}/`);
}
