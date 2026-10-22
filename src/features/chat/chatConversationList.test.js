import { describe, expect, it } from 'vitest';
import { upsertConversationList } from './chatConversationList.js';

describe('chat conversation sidebar list', () => {
  it('shows a newly persisted conversation immediately', () => {
    expect(upsertConversationList([], {
      id: 'conversation-1',
      title: 'New analysis',
      created_at: '2026-08-22T10:00:00Z',
    })).toEqual([{
      id: 'conversation-1',
      title: 'New analysis',
      created_at: '2026-08-22T10:00:00Z',
    }]);
  });

  it('updates and moves an existing conversation without duplicating it', () => {
    const result = upsertConversationList([
      { id: 'conversation-2', title: 'Older' },
      { id: 'conversation-1', title: 'Draft', is_pinned: true },
    ], {
      id: 'conversation-1',
      title: 'Updated',
    });

    expect(result).toEqual([
      { id: 'conversation-1', title: 'Updated', is_pinned: true },
      { id: 'conversation-2', title: 'Older' },
    ]);
  });

  it('keeps the sidebar page bounded', () => {
    const current = Array.from({ length: 50 }, (_, index) => ({ id: `old-${index}` }));
    const result = upsertConversationList(current, { id: 'new-conversation' });

    expect(result).toHaveLength(50);
    expect(result[0].id).toBe('new-conversation');
    expect(result.some((item) => item.id === 'old-49')).toBe(false);
  });
});
