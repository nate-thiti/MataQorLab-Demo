import { describe, expect, it } from 'vitest';
import { needsUserApprovedMapping } from './analysisIntent.js';

describe('needsUserApprovedMapping', () => {
  it('blocks a first file or API request without an approved mapping', () => {
    expect(needsUserApprovedMapping({ hasAttachedFile: true })).toBe(true);
    expect(needsUserApprovedMapping({ connectionType: 'api' })).toBe(true);
  });

  it('allows later requests after mapping was confirmed in this conversation', () => {
    const mapping = { sale_date: 'date', net_sales: 'revenue' };
    expect(needsUserApprovedMapping({ hasAttachedFile: true, mapping })).toBe(false);
    expect(needsUserApprovedMapping({ connectionType: 'api', mapping })).toBe(false);
  });

  it('allows a user-approved ETL recipe instead of semantic mapping', () => {
    expect(needsUserApprovedMapping({
      hasAttachedFile: true,
      cleaningRecipe: { apply: true, rules: { dedupe: true } },
    })).toBe(false);
  });

  it('does not gate SQL connections or agent clarification turns', () => {
    expect(needsUserApprovedMapping({ connectionType: 'sql' })).toBe(false);
    expect(needsUserApprovedMapping({
      connectionType: 'api',
      isAgentClarification: true,
    })).toBe(false);
  });
});
