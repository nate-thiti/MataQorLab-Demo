/**
 * A newly-created conversation becomes active before Next.js finishes replacing
 * `/chat/new` with `/chat/:id`. During that short window the new-chat cleanup
 * must not clear the optimistic user message or abort its response stream.
 */
export function shouldResetConversationOnNewRoute(
  activeConversationId,
  promotedConversationId,
) {
  return Boolean(
    activeConversationId
    && activeConversationId !== promotedConversationId,
  );
}
