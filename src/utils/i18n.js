import en from '../locales/en.json';
import th from '../locales/th.json';

const isPlainObject = (value) =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

const deepMerge = (base, override) => {
  if (!isPlainObject(base) || !isPlainObject(override)) {
    return override ?? base;
  }

  const merged = { ...base };
  for (const [key, value] of Object.entries(override)) {
    if (isPlainObject(value) && isPlainObject(base[key])) {
      merged[key] = deepMerge(base[key], value);
    } else {
      merged[key] = value;
    }
  }
  return merged;
};

export const getMessages = (locale) => (locale === 'en' ? en : deepMerge(en, th));

export const t = (messages, key, fallback = '', replacements = {}) => {
  const value = key.split('.').reduce((acc, part) => (acc && acc[part] !== undefined ? acc[part] : undefined), messages);
  let result = typeof value === 'string' ? value : fallback;
  if (typeof result !== 'string') return '';
  
  if (replacements && typeof replacements === 'object') {
    Object.entries(replacements).forEach(([placeholder, val]) => {
      result = result.replace(
        new RegExp(`\\{${placeholder}\\}`, 'g'),
        () => String(val ?? ''),
      );
    });
  }
  return result;
};
