import { normalizeOrchestration } from './normalize.js';

/** Monotonic sequence — stale responses must not overwrite newer state. */
let reconcileSequence = 0;

export function resetReconcileSequenceForTests() {
  reconcileSequence = 0;
}

export function createEmptyCurrentOrchestrationState() {
  return {
    sessionId: null,
    sessionStatus: null,
    workflowPlan: null,
    source: null,
    activeDecision: null,
    incompleteActiveDecision: null,
    awaitingUser: null,
    currentBlocker: null,
    worklogStamps: [],
    resolvedDecisionKey: null,
    updatedAt: null,
    reconcileError: null,
    reconciling: false,
    pollRecommended: false,
    continuationAvailable: false,
    stopReason: null,
    controllerActivity: null,
    noProgress: false,
    pollCount: 0,
  };
}

function normalizeActiveDecision(raw, awaitingUser) {
  if (raw === null) return null;
  if (!raw || typeof raw !== 'object') return null;
  const decisionKey = raw.decision_key || raw.decisionKey || null;
  if (!decisionKey) return null;
  const rawOpts = Array.isArray(raw.options) ? raw.options : null;
  const fallbackOpts = awaitingUser?.options || [];
  const options = (rawOpts?.length ? rawOpts : fallbackOpts);
  const freeTextAllowed = raw.free_text_allowed ?? raw.freeTextAllowed;
  const expectedInput = raw.expected_input || raw.expectedInput
    || (options.length ? 'option_or_text' : 'free_text');
  return {
    decisionKey,
    status: raw.status || 'pending',
    question: raw.question || awaitingUser?.question || null,
    stepType: raw.step_type || raw.stepType || awaitingUser?.step_type || null,
    reasonCode: raw.reason_code || raw.reasonCode || awaitingUser?.reason_code || null,
    context: raw.context || awaitingUser?.context || null,
    options,
    expectedInput,
    freeTextAllowed: freeTextAllowed ?? (expectedInput !== 'single_choice'),
  };
}

/** Pending active_decision must have question + valid input mode. */
export function isActiveDecisionComplete(activeDecision) {
  if (!activeDecision || activeDecision.status !== 'pending') return false;
  const question = String(activeDecision.question || '').trim();
  if (!question) return false;
  const opts = activeDecision.options || [];
  const expected = String(activeDecision.expectedInput || '').toLowerCase();
  const freeText = activeDecision.freeTextAllowed !== false;
  if (expected === 'single_choice') return opts.length > 0 || freeText;
  if (expected === 'option_or_text') return opts.length > 0 || freeText;
  if (opts.length > 0) return true;
  return freeText;
}

/**
 * Live question comes ONLY from pending active_decision (backend authority).
 * Historical awaiting_user is used as merge base only — never overrides decision fields.
 */
export function deriveLiveAwaitingUser(activeDecision, awaitingUser) {
  if (!activeDecision || activeDecision.status !== 'pending') return null;
  if (!isActiveDecisionComplete(activeDecision)) return null;
  const base = awaitingUser && typeof awaitingUser === 'object' ? awaitingUser : {};
  return {
    ...base,
    reason_code: activeDecision.reasonCode || base.reason_code,
    reasonCode: activeDecision.reasonCode || base.reasonCode,
    question: activeDecision.question || base.question,
    step_type: activeDecision.stepType || base.step_type,
    stepType: activeDecision.stepType || base.stepType,
    decision_key: activeDecision.decisionKey,
    decisionKey: activeDecision.decisionKey,
    context: activeDecision.context || base.context,
    options: (activeDecision.options?.length ? activeDecision.options : base.options) || [],
    expected_input: activeDecision.expectedInput,
    expectedInput: activeDecision.expectedInput,
    free_text_allowed: activeDecision.freeTextAllowed !== false,
    freeTextAllowed: activeDecision.freeTextAllowed !== false,
  };
}

export function payloadToCurrentOrchestrationState(payload) {
  if (!payload || typeof payload !== 'object') {
    return createEmptyCurrentOrchestrationState();
  }
  const session = payload.session || null;
  const awaitingRaw = payload.awaiting_user ?? payload.awaitingUser ?? null;
  const activeRaw = payload.active_decision ?? payload.activeDecision;
  let activeDecision = null;
  if (activeRaw !== undefined) {
    activeDecision = normalizeActiveDecision(activeRaw, awaitingRaw);
  }
  // Only the current ask_user event may stand in for an immediately stale
  // session read. This does not resurrect historical awaiting_user payloads.
  if (!activeDecision
    && (payload.decision_type || payload.decisionType) === 'ask_user'
    && awaitingRaw?.question) {
    activeDecision = normalizeActiveDecision({
      ...awaitingRaw,
      status: 'pending',
    }, awaitingRaw);
  }
  const progress = session?.processing_progress || payload.processing_progress || {};
  // Explicit payload.session_status (stream/resume) wins over a lagging session object.
  const sessionStatus = payload.session_status
    ?? payload.sessionStatus
    ?? session?.status
    ?? null;
  const incompleteActiveDecision = payload.incomplete_active_decision
    ?? payload.incompleteActiveDecision
    ?? null;
  const view = normalizeOrchestration({
    workflow: payload.workflow,
    source: payload.source,
    awaiting_user: deriveLiveAwaitingUser(activeDecision, awaitingRaw),
    active_decision: payload.active_decision,
    worklog_stamps: payload.worklog_stamps,
    session_status: sessionStatus,
  });
  const stamps = view?.worklogStamps || [];
  return {
    sessionId: session?.id || payload.session_id || null,
    sessionStatus,
    workflowPlan: payload.workflow || null,
    source: payload.source || null,
    activeDecision,
    incompleteActiveDecision: incompleteActiveDecision
      ? String(incompleteActiveDecision)
      : null,
    awaitingUser: view?.awaitingUser || null,
    currentBlocker: view?.errorKind && view.errorKind !== 'awaiting_user'
      ? { kind: view.errorKind, orchestration: view }
      : null,
    worklogStamps: stamps,
    resolvedDecisionKey: payload.resolved_decision_key
      || payload.resolvedDecisionKey
      || progress.resolved_decision_key
      || null,
    updatedAt: payload.updated_at ?? payload.updatedAt ?? session?.updated_at ?? null,
    reconcileError: null,
    reconciling: false,
    pollRecommended: Boolean(payload.poll_recommended ?? payload.pollRecommended),
    continuationAvailable: Boolean(
      payload.continuation_available ?? payload.continuationAvailable,
    ),
    stopReason: payload.stop_reason || payload.stopReason || null,
    controllerActivity: payload.controller_activity || payload.controllerActivity || null,
    noProgress: false,
    pollCount: 0,
  };
}

export function buildStateFingerprint(state) {
  if (!state) return '';
  const steps = state.workflowPlan?.steps || [];
  const stepSig = steps.map((s) => {
    const row = s && typeof s === 'object' ? s : {};
    return [
      row.step_type || row.stepType || '',
      row.status || '',
      row.version ?? '',
    ].join(':');
  }).join('|');
  return [
    state.sessionStatus || '',
    state.updatedAt || '',
    state.activeDecision?.decisionKey || '',
    state.activeDecision?.status || '',
    state.stopReason || '',
    stepSig,
  ].join('::');
}

export function shouldPollSetupState(state) {
  if (!state?.sessionStatus) return false;
  const status = state.sessionStatus;
  if (['ready', 'failed', 'cancelled'].includes(status)) return false;
  if (state.awaitingUser || state.activeDecision?.status === 'pending') return false;
  if (state.stopReason === 'awaiting_user' || state.stopReason === 'action_limit_reached') {
    return false;
  }
  if (state.noProgress) return false;
  if (state.pollRecommended === true) return true;
  const steps = state.workflowPlan?.steps || [];
  const hasRunning = steps.some((s) => s?.status === 'running');
  return hasRunning && status === 'processing';
}

export function pollIntervalMs(elapsedMs, pollCount = 0) {
  if (elapsedMs < 5000) return 2000;
  if (elapsedMs < 20000) return 3000;
  if (elapsedMs < 60000) return 5000;
  if (pollCount >= 12) return 10000;
  return 10000;
}

export function buildResumeParamsFromSession(session, conversationId) {
  if (!session?.source_type) return null;
  const sourceType = session.source_type;
  const sourceRef = session.source_ref || {};
  const params = new URLSearchParams({ source_type: sourceType });
  if (sourceType === 'file' && sourceRef.file_name) {
    params.set('file_name', sourceRef.file_name);
  } else if (sourceRef.connection_id) {
    params.set('connection_id', sourceRef.connection_id);
    if (sourceRef.table_name) params.set('table_name', sourceRef.table_name);
  }
  const convId = conversationId || session.conversation_id;
  if (convId) params.set('conversation_id', convId);
  return params;
}

export const NO_PROGRESS_POLL_THRESHOLD = 4;

/**
 * Fetch authoritative setup state from /data-setup/resume (state retrieval only — no LLM).
 */
export async function reconcileSetupState({
  authFetch,
  getPublicApiUrl,
  session,
  sessionId,
  conversationId,
}) {
  const seq = ++reconcileSequence;
  let workingSession = session;
  if (!workingSession?.source_type && sessionId) {
    const sessionRes = await authFetch(
      `${getPublicApiUrl()}/api/v1/data-setup/${sessionId}`,
    );
    const sessionPayload = await sessionRes.json().catch(() => ({}));
    if (seq !== reconcileSequence) return { stale: true, state: null };
    workingSession = sessionPayload.session || null;
  }
  const params = buildResumeParamsFromSession(workingSession, conversationId);
  if (!params) {
    return {
      stale: false,
      state: createEmptyCurrentOrchestrationState(),
      session: workingSession,
    };
  }
  const resumeRes = await authFetch(
    `${getPublicApiUrl()}/api/v1/data-setup/resume?${params.toString()}`,
  );
  const payload = await resumeRes.json().catch(() => ({}));
  if (seq !== reconcileSequence) return { stale: true, state: null };
  if (!resumeRes.ok) {
    throw new Error(payload.detail || payload.message || 'resume_failed');
  }
  return {
    stale: false,
    state: payloadToCurrentOrchestrationState(payload),
    session: payload.session || workingSession,
    raw: payload,
  };
}

export function applyCurrentOrchestrationReplacements(prev, next) {
  if (!next) return prev;
  const nextStatus = next.sessionStatus;
  // Resume can lag the streamed ask_user write (still "processing" briefly).
  // Keep the live question until a newer decision, resolution, or terminal status.
  const preserveCurrentAsk = Boolean(
    prev?.activeDecision?.status === 'pending'
    && !next.activeDecision
    && !next.resolvedDecisionKey
    && !['ready', 'failed', 'cancelled'].includes(nextStatus)
    && (nextStatus === 'awaiting_answers'
      || nextStatus === 'processing')
    && (next.stopReason == null || next.stopReason === 'awaiting_user'),
  );
  return {
    ...prev,
    ...next,
    workflowPlan: next.workflowPlan ?? null,
    source: next.source ?? null,
    activeDecision: preserveCurrentAsk ? prev.activeDecision : (next.activeDecision ?? null),
    awaitingUser: preserveCurrentAsk ? prev.awaitingUser : (next.awaitingUser ?? null),
    incompleteActiveDecision: next.incompleteActiveDecision ?? null,
    currentBlocker: next.currentBlocker ?? null,
    worklogStamps: next.worklogStamps || [],
    resolvedDecisionKey: next.resolvedDecisionKey ?? null,
    updatedAt: next.updatedAt ?? null,
    reconcileError: next.reconcileError ?? null,
    reconciling: next.reconciling ?? false,
  };
}
