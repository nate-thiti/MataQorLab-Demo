import { describe, expect, it } from 'vitest';
import { formatApiErrorDetail } from './formatApiErrorDetail.js';

describe('formatApiErrorDetail', () => {
  it('reads FastAPI string detail', () => {
    expect(formatApiErrorDetail({ detail: 'Quick Scan failed: boom' }))
      .toBe('Quick Scan failed: boom');
  });

  it('joins validation error arrays', () => {
    expect(formatApiErrorDetail({
      detail: [{ msg: 'field required' }, { msg: 'invalid type' }],
    })).toBe('field required; invalid type');
  });

  it('falls back when payload is empty', () => {
    expect(formatApiErrorDetail({}, 'Quick Scan failed')).toBe('Quick Scan failed');
  });
});
