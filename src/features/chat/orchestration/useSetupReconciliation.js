import { useCallback, useEffect, useRef, useState } from 'react';
import {
  NO_PROGRESS_POLL_THRESHOLD,
  applyCurrentOrchestrationReplacements,
  buildStateFingerprint,
  createEmptyCurrentOrchestrationState,
  payloadToCurrentOrchestrationState,
  pollIntervalMs,
  reconcileSetupState,
  shouldPollSetupState,
} from './reconcileSetupState.js';

/**
 * Canonical live orchestration state — backend session/resume is source of truth.
 * Polling is fallback sync only — never drives workflow execution.
 */
export function useSetupReconciliation({
  authFetch,
  getPublicApiUrl,
  enabled = false,
  session,
  conversationId,
}) {
  const [current, setCurrent] = useState(createEmptyCurrentOrchestrationState);
  const sessionRef = useRef(session);
  const pollStartedRef = useRef(null);
  const pollCountRef = useRef(0);
  const lastFingerprintRef = useRef('');
  const sameFingerprintCountRef = useRef(0);
  sessionRef.current = session;

  const reconcile = useCallback(async (options = {}) => {
    if (!enabled) return null;
    const sessionId = options.sessionId || sessionRef.current?.id;
    if (!sessionId && !sessionRef.current?.source_type) return null;
    setCurrent((prev) => ({ ...prev, reconciling: true, reconcileError: null }));
    try {
      const result = await reconcileSetupState({
        authFetch,
        getPublicApiUrl,
        sessionId,
        session: options.session || sessionRef.current,
        conversationId: options.conversationId || conversationId,
      });
      if (result.stale) return null;
      const nextState = {
        ...result.state,
        sessionId: result.session?.id || result.state?.sessionId || sessionId,
        // Prefer explicit resume/stream session_status over a lagging session row.
        sessionStatus: result.raw?.session_status
          ?? result.state?.sessionStatus
          ?? result.session?.status
          ?? null,
        pollRecommended: Boolean(
          result.raw?.poll_recommended ?? result.state?.pollRecommended,
        ),
        continuationAvailable: Boolean(
          result.raw?.continuation_available ?? result.state?.continuationAvailable,
        ),
        stopReason: result.raw?.stop_reason || result.state?.stopReason || null,
        controllerActivity: result.raw?.controller_activity
          || result.state?.controllerActivity
          || null,
        reconcileError: result.raw?.reconcile_error
          || result.raw?.enrich_error
          || result.state?.reconcileError
          || null,
        reconciling: false,
      };
      const fingerprint = buildStateFingerprint(nextState);
      if (fingerprint && fingerprint === lastFingerprintRef.current) {
        sameFingerprintCountRef.current += 1;
      } else {
        sameFingerprintCountRef.current = 0;
        lastFingerprintRef.current = fingerprint;
      }
      if (sameFingerprintCountRef.current >= NO_PROGRESS_POLL_THRESHOLD) {
        nextState.noProgress = true;
      }
      pollCountRef.current += 1;
      nextState.pollCount = pollCountRef.current;
      setCurrent((prev) => applyCurrentOrchestrationReplacements(prev, nextState));
      return { ...result, session: result.session, state: nextState };
    } catch (err) {
      setCurrent((prev) => ({
        ...prev,
        reconciling: false,
        reconcileError: err?.message || 'reconcile_failed',
      }));
      return null;
    }
  }, [authFetch, conversationId, enabled, getPublicApiUrl]);

  const applyStreamOrchestration = useCallback((orchestration) => {
    if (!orchestration) return;
    pollCountRef.current = 0;
    sameFingerprintCountRef.current = 0;
    lastFingerprintRef.current = '';
    // Stream payload is authoritative for this turn — parent session may lag.
    const partial = payloadToCurrentOrchestrationState({
      session: sessionRef.current,
      workflow: orchestration.workflow || orchestration.workflow_plan,
      source: orchestration.source,
      decision_type: orchestration.decision_type,
      awaiting_user: orchestration.awaiting_user,
      active_decision: orchestration.active_decision,
      incomplete_active_decision: orchestration.incomplete_active_decision,
      worklog_stamps: orchestration.worklog_stamps,
      resolved_decision_key: orchestration.resolved_decision_key,
      session_status: orchestration.session_status ?? sessionRef.current?.status,
      updated_at: orchestration.updated_at ?? sessionRef.current?.updated_at,
      poll_recommended: orchestration.poll_recommended,
      continuation_available: orchestration.continuation_available,
      stop_reason: orchestration.stop_reason || orchestration.audit?.stop_reason,
      controller_activity: orchestration.controller_activity,
    });
    setCurrent((prev) => applyCurrentOrchestrationReplacements(prev, partial));
  }, []);

  const resetPollTracking = useCallback(() => {
    pollCountRef.current = 0;
    sameFingerprintCountRef.current = 0;
    lastFingerprintRef.current = '';
    pollStartedRef.current = null;
    setCurrent((prev) => ({ ...prev, noProgress: false, pollCount: 0 }));
  }, []);

  useEffect(() => {
    if (!enabled || !session?.id) return undefined;
    let cancelled = false;
    (async () => {
      const result = await reconcile({
        sessionId: session.id,
        session: sessionRef.current,
      });
      if (cancelled || !result) return;
    })();
    return () => { cancelled = true; };
  }, [enabled, session?.id, reconcile]);

  useEffect(() => {
    if (!enabled || !session?.id) return undefined;
    if (!shouldPollSetupState(current)) return undefined;
    if (!pollStartedRef.current) pollStartedRef.current = Date.now();
    let cancelled = false;
    let timer = null;

    const schedule = () => {
      const elapsed = Date.now() - (pollStartedRef.current || Date.now());
      const delay = pollIntervalMs(elapsed, pollCountRef.current);
      timer = window.setTimeout(async () => {
        if (cancelled) return;
        await reconcile({ sessionId: session.id, session: sessionRef.current });
        if (!cancelled && shouldPollSetupState(current)) schedule();
      }, delay);
    };
    schedule();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [
    enabled,
    session?.id,
    current.sessionStatus,
    current.activeDecision,
    current.awaitingUser,
    current.pollRecommended,
    current.noProgress,
    current.stopReason,
    reconcile,
    current,
  ]);

  return {
    currentOrchestration: current,
    reconcileSetup: reconcile,
    applyStreamOrchestration,
    resetPollTracking,
    setCurrentOrchestration: setCurrent,
  };
}
