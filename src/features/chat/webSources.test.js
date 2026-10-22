import { describe, expect, it } from 'vitest';
import { getStepLabel } from './reasoningProgress.js';
import { mergeWebSources, normalizeWebSourceUrl } from './webSources.js';

const t = (_key, fallback) => fallback;

describe('mergeWebSources', () => {
  it('dedupes by url', () => {
    const merged = mergeWebSources(
      [{ title: 'A', url: 'https://example.com/a', snippet: 'one' }],
      [
        { title: 'A duplicate', url: 'https://example.com/a', snippet: 'two' },
        { title: 'B', url: 'https://example.com/b', snippet: 'three' },
      ],
    );
    expect(merged).toHaveLength(2);
    expect(merged.map((source) => source.url)).toEqual([
      'https://example.com/a',
      'https://example.com/b',
    ]);
  });

  it('rejects non-http source URLs', () => {
    expect(normalizeWebSourceUrl('javascript:alert(1)')).toBe('');
    expect(mergeWebSources([], [
      { title: 'unsafe', url: 'javascript:alert(1)' },
    ])).toEqual([]);
  });
});

describe('getStepLabel web search', () => {
  it('renders web search stage label', () => {
    const label = getStepLabel(
      'web_search',
      { hint: 'Thailand GDP', step: 2, total: 3 },
      true,
      t,
    );
    expect(label).toContain('Searching web');
    expect(label).toContain('Thailand GDP');
  });

  it('renders web search done label', () => {
    const label = getStepLabel(
      'web_search_done',
      { source_count: 3 },
      false,
      t,
    );
    expect(label).toContain('3');
  });

  it('renders the sealed tool evidence stage', () => {
    const label = getStepLabel(
      'tools_ready',
      {
        satisfied: true,
        calls: [{ tool: 'dataset_query', status: 'completed' }],
      },
      false,
      t,
    );
    expect(label).toContain('1');
    expect(label).toContain('ล็อกหลักฐาน');
  });
});
