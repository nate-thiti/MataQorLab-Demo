export const DEFAULT_CONVERSATION_LIST_LIMIT = 50;

/**
 * Put a newly persisted conversation into the visible sidebar immediately.
 * The database remains authoritative, but a fresh read cache must not hide a
 * row that the same client has just inserted.
 */
export function upsertConversationList(
  conversations,
  conversation,
  limit = DEFAULT_CONVERSATION_LIST_LIMIT,
) {
  const current = Array.isArray(conversations) ? conversations : [];
  if (!conversation?.id) return current;
  const existing = current.find((item) => item?.id === conversation.id);
  const row = existing ? { ...existing, ...conversation } : conversation;
  return [
    row,
    ...current.filter((item) => item?.id !== conversation.id),
  ].slice(0, Math.max(1, limit));
}
