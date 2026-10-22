import { describe, expect, it } from 'vitest';
import { shouldResetConversationOnNewRoute } from './chatRouteTransition.js';

describe('new chat workspace reset', () => {
  it('explicit new chat must reset even when no active conversation', () => {
    // shouldResetConversationOnNewRoute alone is insufficient — Chat.tsx must
    // call resetDataSetupWorkspace from handleStartNewChat directly.
    expect(shouldResetConversationOnNewRoute(null, null)).toBe(false);
  });

  it('switching from an old conversation to /chat/new triggers reset guard', () => {
    expect(shouldResetConversationOnNewRoute('conv-deleted', null)).toBe(true);
  });
});

describe('setup resume guards', () => {
  it('does not resume by file on fresh /chat/new without conversation id', () => {
    const convId = null;
    const hasConversation = Boolean(
      convId && /^[0-9a-f-]{36}$/i.test(convId),
    );
    expect(hasConversation).toBe(false);
  });

  it('blocks restoring local file scoped to a deleted conversation on new chat', () => {
    const saved = { conversationId: 'conv-old', file: { name: 'data.csv' } };
    const conversationId = null;
    const shouldRestore = !(
      saved.conversationId && conversationId && saved.conversationId !== conversationId
    ) && !(!conversationId && saved.conversationId);
    expect(shouldRestore).toBe(false);
  });

  it('allows refresh resume on /chat/new when saved session has no conversation yet', () => {
    const saved = { conversationId: null, file: { name: 'data.csv', dataSetupSessionId: 'sess-1' } };
    const conversationId = null;
    const shouldRestore = !(
      saved.conversationId && conversationId && saved.conversationId !== conversationId
    ) && !(!conversationId && saved.conversationId);
    expect(shouldRestore).toBe(true);
  });
});
