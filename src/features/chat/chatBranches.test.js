import { describe, expect, it, vi } from 'vitest';
import {
  branchCacheKey,
  generationRequestId,
  isBranchingUnavailable,
  precedingUserMessage,
  retryHistory,
} from './chatBranches.js';

describe('chat branches', () => {
  it('recognizes pre-migration Data API errors', () => {
    expect(isBranchingUnavailable({ code: 'PGRST202' })).toBe(true);
    expect(isBranchingUnavailable({ code: '23505' })).toBe(false);
  });

  it('isolates branch cache keys', () => {
    expect(branchCacheKey('conversation', 'branch-a')).toBe('conversation:branch:branch-a');
    expect(branchCacheKey('conversation')).toBe('conversation');
  });

  it('finds the source prompt immediately before an assistant answer', () => {
    const result = precedingUserMessage([
      { role: 'user', content: 'first' },
      { role: 'ai', content: 'answer' },
      { role: 'user', content: 'second' },
      { role: 'ai', content: 'answer two' },
    ], 3);
    expect(result).toEqual({ message: { role: 'user', content: 'second' }, index: 2 });
  });

  it('rebuilds retry history before the idempotent user request', () => {
    const messages = [
      { role: 'user', content: 'first' },
      { role: 'ai', content: 'answer' },
      { role: 'user', content: 'retry me', clientRequestId: 'request-1' },
      { role: 'ai', failed: true, clientRequestId: 'request-1' },
    ];
    expect(retryHistory(messages, 'request-1')).toHaveLength(2);
  });

  it('uses crypto UUIDs for idempotency when available', () => {
    const original = globalThis.crypto;
    Object.defineProperty(globalThis, 'crypto', {
      configurable: true,
      value: { randomUUID: vi.fn(() => 'request-uuid') },
    });
    expect(generationRequestId()).toBe('request-uuid');
    Object.defineProperty(globalThis, 'crypto', { configurable: true, value: original });
  });
});
