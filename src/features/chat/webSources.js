/**
 * Merge web source lists by URL.
 * @param {Array<{ title?: string, url?: string, snippet?: string }>} existing
 * @param {Array<{ title?: string, url?: string, snippet?: string }>} incoming
 */
export function mergeWebSources(existing = [], incoming = []) {
  const seen = new Set(
    existing.map((source) => source?.url).filter(Boolean),
  );
  const merged = [...existing];
  for (const source of incoming) {
    const url = normalizeWebSourceUrl(source?.url);
    if (!url || seen.has(url)) continue;
    seen.add(url);
    merged.push({
      title: source.title || url,
      url,
      snippet: source.snippet || '',
    });
  }
  return merged;
}

export function normalizeWebSourceUrl(value) {
  if (typeof value !== 'string') return '';
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
      ? parsed.toString()
      : '';
  } catch {
    return '';
  }
}
