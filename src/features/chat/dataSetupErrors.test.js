import { describe, expect, it } from 'vitest';
import { formatApiError } from './dataSetupErrors.js';

describe('formatApiError', () => {
  it('returns strings as-is', () => {
    expect(formatApiError('boom')).toBe('boom');
  });

  it('flattens FastAPI validation arrays', () => {
    expect(formatApiError([
      { loc: ['body', 'answers', 'domain'], msg: 'field required', type: 'value_error' },
    ])).toBe('answers.domain: field required');
  });

  it('reads message objects instead of [object Object]', () => {
    expect(formatApiError({
      message: 'Contract incomplete',
      issues: ['missing primary key', 'unmapped metric'],
    })).toBe('Contract incomplete: missing primary key; unmapped metric');
  });

  it('falls back when empty', () => {
    expect(formatApiError(null, 'Could not approve')).toBe('Could not approve');
  });
});
