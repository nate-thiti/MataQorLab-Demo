export const SUPPORTED_LOCALES = ['th', 'en'];
export const DEFAULT_LOCALE = 'th';
export const LOCALE_COOKIE = 'mataqor_locale';

/** Display labels for locale pickers (native names where possible). */
export const LOCALE_LABELS = Object.freeze({
  th: { short: 'TH', name: 'ไทย', nameEn: 'Thai' },
  en: { short: 'EN', name: 'English', nameEn: 'English' },
});

const LOCALE_SEGMENTS = new Set(SUPPORTED_LOCALES);

export function isSupportedLocale(locale) {
  return LOCALE_SEGMENTS.has(locale);
}

export function getClientLocale() {
  if (typeof document === 'undefined') return DEFAULT_LOCALE;
  return isSupportedLocale(document.documentElement.lang)
    ? document.documentElement.lang
    : DEFAULT_LOCALE;
}

export const getLocaleFromPath = (pathname = '', basename = '/') => {
  const baseSegment = (basename || '/').replace(/\/$/, '').split('/').filter(Boolean)[0];
  if (LOCALE_SEGMENTS.has(baseSegment)) {
    return baseSegment;
  }

  const first = pathname.split('/').filter(Boolean)[0];
  return first === 'en' ? 'en' : 'th';
};

/** Paths for React Router <Link> / navigate (respects basename). */
export const createLocaleRouting = (basename = '/', pathname = '/') => {
  const normalizedBase = (basename || '/').replace(/\/$/, '') || '';
  const baseSegment = normalizedBase.split('/').filter(Boolean)[0];
  const hasLocaleInBasename = LOCALE_SEGMENTS.has(baseSegment);
  const locale = getLocaleFromPath(pathname, basename);
  const localePrefix = hasLocaleInBasename ? '' : `/${locale}`;
  const absolutePrefix = hasLocaleInBasename ? normalizedBase : `/${locale}`;

  return { locale, localePrefix, absolutePrefix };
};

export const localePath = (relativePath, { localePrefix }) => {
  const path = relativePath.startsWith('/') ? relativePath : `/${relativePath}`;
  return `${localePrefix}${path}`;
};

export const absoluteLocaleUrl = (origin, relativePath, { absolutePrefix }) => {
  const path = relativePath.startsWith('/') ? relativePath : `/${relativePath}`;
  return `${origin}${absolutePrefix}${path}`;
};

export const replacePathLocale = (pathname = '/', locale = DEFAULT_LOCALE) => {
  const targetLocale = isSupportedLocale(locale) ? locale : DEFAULT_LOCALE;
  const segments = pathname.split('/');
  const firstSegment = segments.findIndex(Boolean);

  if (firstSegment >= 0 && LOCALE_SEGMENTS.has(segments[firstSegment])) {
    segments[firstSegment] = targetLocale;
    return segments.join('/') || `/${targetLocale}`;
  }

  const normalizedPath = pathname.startsWith('/') ? pathname : `/${pathname}`;
  return `/${targetLocale}${normalizedPath === '/' ? '' : normalizedPath}`;
};
