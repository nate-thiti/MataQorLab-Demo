/** Normalize FastAPI / fetch error payloads into a readable string. */
export function formatApiError(detail, fallback = 'Request failed') {
  if (detail == null || detail === '') return fallback;
  if (typeof detail === 'string') return detail;
  if (typeof detail === 'number' || typeof detail === 'boolean') return String(detail);
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (typeof item === 'string') return item;
      if (item?.msg) {
        const path = Array.isArray(item.loc)
          ? item.loc.filter((part) => part !== 'body').join('.')
          : '';
        return path ? `${path}: ${item.msg}` : item.msg;
      }
      return formatApiError(item, '');
    }).filter(Boolean);
    return parts.join('; ') || fallback;
  }
  if (typeof detail === 'object') {
    if (detail.message || detail.detail || detail.error) {
      const base = formatApiError(detail.message || detail.detail || detail.error, '');
      const issues = detail.issues || detail.errors;
      if (Array.isArray(issues) && issues.length) {
        const issueText = issues.map((item) => (
          typeof item === 'string'
            ? item
            : (item?.message || item?.msg || formatApiError(item, ''))
        )).filter(Boolean).join('; ');
        return issueText ? `${base || fallback}: ${issueText}` : (base || fallback);
      }
      return base || fallback;
    }
    try {
      return JSON.stringify(detail);
    } catch {
      return fallback;
    }
  }
  return fallback;
}
