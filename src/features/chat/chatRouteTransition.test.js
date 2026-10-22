import { describe, expect, it } from 'vitest';
import { shouldResetConversationOnNewRoute } from './chatRouteTransition.js';

describe('shouldResetConversationOnNewRoute', () => {
  it('preserves a conversation while its newly-created route is being promoted', () => {
    expect(shouldResetConversationOnNewRoute('conv-new', 'conv-new')).toBe(false);
  });

  it('resets a previously active conversation when the user opens a real new chat', () => {
    expect(shouldResetConversationOnNewRoute('conv-old', null)).toBe(true);
    expect(shouldResetConversationOnNewRoute('conv-old', 'conv-new')).toBe(true);
  });

  it('does nothing when no conversation is active', () => {
    expect(shouldResetConversationOnNewRoute(null, null)).toBe(false);
  });
});
