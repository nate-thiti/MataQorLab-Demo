/** Normalize FastAPI / gateway error payloads into a readable string. */
export function formatApiErrorDetail(payload, fallback = 'Request failed') {
  if (payload == null) return fallback;
  if (typeof payload === 'string') {
    const trimmed = payload.trim();
    return trimmed || fallback;
  }
  const detail = payload.detail ?? payload.message ?? payload.error;
  if (detail == null) return fallback;
  if (typeof detail === 'string') {
    const trimmed = detail.trim();
    return trimmed || fallback;
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object') {
          return item.msg || item.message || item.detail || null;
        }
        return null;
      })
      .filter(Boolean);
    return parts.length ? parts.join('; ') : fallback;
  }
  if (typeof detail === 'object') {
    return (
      detail.message
      || detail.error
      || detail.code
      || fallback
    );
  }
  return String(detail);
}
