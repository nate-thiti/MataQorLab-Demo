const UNAVAILABLE_CODES = new Set([
  '42P01',
  '42703',
  '42883',
  'PGRST202',
  'PGRST204',
  'PGRST205',
]);

export function isBranchingUnavailable(error) {
  return UNAVAILABLE_CODES.has(String(error?.code || ''));
}

export function branchCacheKey(conversationId, branchId = null) {
  return branchId ? `${conversationId}:branch:${branchId}` : conversationId;
}

export function generationRequestId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `generation-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function precedingUserMessage(messages, assistantIndex) {
  const end = Number.isInteger(assistantIndex) ? assistantIndex - 1 : messages.length - 1;
  for (let index = end; index >= 0; index -= 1) {
    if (messages[index]?.role === 'user') return { message: messages[index], index };
  }
  return null;
}

export function retryHistory(messages, clientRequestId) {
  const userIndex = messages.findIndex(
    (message) => message.role === 'user' && message.clientRequestId === clientRequestId,
  );
  return userIndex < 0 ? [] : messages.slice(0, userIndex);
}
