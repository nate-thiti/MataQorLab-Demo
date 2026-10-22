/**
 * Frontend chat turn lifecycle — separate from workflow/session state.
 * Composer lock belongs to an active user HTTP/SSE turn only.
 */

/** @typedef {'idle' | 'submitting' | 'streaming'} ChatTurnState */

/**
 * Clear active turn UI (composer unlock). Safe to call multiple times.
 */
export function finishChatTurn({
  setIsGenerating,
  setIsTyping,
  setAnalysisStreamStarted,
  abortControllerRef = null,
}) {
  if (typeof setAnalysisStreamStarted === 'function') {
    setAnalysisStreamStarted(false);
  }
  if (typeof setIsTyping === 'function') {
    setIsTyping(false);
  }
  if (typeof setIsGenerating === 'function') {
    setIsGenerating(false);
  }
  if (abortControllerRef) {
    abortControllerRef.current = null;
  }
}

/**
 * Apply stream orchestration synchronously; reconcile in background (never blocks composer).
 */
export function applyStreamOrchestrationUpdate({
  orchestration,
  applyStreamOrchestration,
  reconcileSetup,
  session,
  resolveSessionId,
}) {
  if (!orchestration) return;
  applyStreamOrchestration(orchestration);
  const sessionId = resolveSessionId(orchestration, session);
  if (sessionId && typeof reconcileSetup === 'function') {
    void reconcileSetup({ sessionId, session });
  }
}

/**
 * Guard against duplicate Send/Enter/option submits for one logical turn boundary.
 * @param {React.MutableRefObject<boolean>} sendInFlightRef
 * @param {() => Promise<void>} fn
 */
export async function runWithSendInFlight(sendInFlightRef, fn) {
  if (sendInFlightRef.current) return;
  sendInFlightRef.current = true;
  try {
    await fn();
  } finally {
    sendInFlightRef.current = false;
  }
}

/**
 * Defensive stale-lock recovery when turn flags are set without an active stream.
 * Skip while a send is still preparing the request (before AbortController exists).
 */
export function recoverStaleChatTurn({
  isGenerating,
  hasActiveStream,
  isSendInFlight = false,
  finishTurn,
  log = console.warn,
}) {
  if (isGenerating && !hasActiveStream && !isSendInFlight) {
    log('[chat-turn] stale lock recovered');
    finishTurn();
  }
}
