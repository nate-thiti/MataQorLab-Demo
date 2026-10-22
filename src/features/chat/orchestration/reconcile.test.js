import { describe, expect, it, vi, beforeEach } from 'vitest';
import {
  applyCurrentOrchestrationReplacements,
  createEmptyCurrentOrchestrationState,
  deriveLiveAwaitingUser,
  isActiveDecisionComplete,
  payloadToCurrentOrchestrationState,
  reconcileSetupState,
  resetReconcileSequenceForTests,
  shouldPollSetupState,
  buildStateFingerprint,
  pollIntervalMs,
} from './reconcileSetupState.js';

describe('deriveLiveAwaitingUser', () => {
  it('clears live awaiting when active_decision is null', () => {
    expect(deriveLiveAwaitingUser(null, { question: 'old?' })).toBeNull();
  });

  it('returns awaiting only for pending active decision', () => {
    const active = {
      decisionKey: 'row_grain',
      status: 'pending',
      question: 'grain?',
      options: [{ value: 'yes', label: 'Yes' }],
      freeTextAllowed: true,
    };
    const live = deriveLiveAwaitingUser(active, null);
    expect(live.decision_key).toBe('row_grain');
    expect(live.question).toBe('grain?');
  });

  it('active_decision overrides stale awaiting_user question', () => {
    const active = {
      decisionKey: 'row_grain',
      status: 'pending',
      question: 'ข้อมูล 1 แถวคือสินค้า 1 รายการในแต่ละบิลใช่ไหม?',
      options: [{ id: 'invoice_line', label: 'ใช่ — รายการในบิล', value: 'invoice_line' }],
      freeTextAllowed: true,
    };
    const live = deriveLiveAwaitingUser(active, {
      question: 'Validate ต้องการการยืนยัน',
      decision_key: 'confirmation',
    });
    expect(live.question).toContain('แถว');
    expect(live.decision_key).toBe('row_grain');
  });

  it('returns null for incomplete pending decision', () => {
    expect(isActiveDecisionComplete({
      decisionKey: 'row_grain',
      status: 'pending',
      question: '',
      options: [],
      freeTextAllowed: false,
    })).toBe(false);
    expect(deriveLiveAwaitingUser({
      decisionKey: 'row_grain',
      status: 'pending',
      question: '',
      options: [{ value: 'x', label: 'X' }],
    }, null)).toBeNull();
  });

  it('clears when active decision is resolved', () => {
    expect(deriveLiveAwaitingUser(
      { decisionKey: 'row_grain', status: 'resolved', question: 'grain?' },
      { question: 'grain?' },
    )).toBeNull();
  });
});

describe('payloadToCurrentOrchestrationState', () => {
  it('replaces workflow plan from backend payload', () => {
    const state = payloadToCurrentOrchestrationState({
      session: { id: 's1', status: 'processing', updated_at: 't1' },
      workflow: { session_id: 's1', steps: [{ step_type: 'inspect', status: 'completed' }] },
      active_decision: null,
      awaiting_user: null,
    });
    expect(state.sessionId).toBe('s1');
    expect(state.workflowPlan.steps).toHaveLength(1);
    expect(state.awaitingUser).toBeNull();
    expect(state.activeDecision).toBeNull();
  });

  it('maps next active decision after answer', () => {
    const state = payloadToCurrentOrchestrationState({
      session: { id: 's1', status: 'awaiting_answers' },
      workflow: { session_id: 's1', steps: [] },
      active_decision: {
        decision_key: 'primary_metric',
        status: 'pending',
        question: 'metric?',
        options: [{ value: 'sales', label: 'Sales' }],
      },
      resolved_decision_key: 'row_grain',
    });
    expect(state.activeDecision.decisionKey).toBe('primary_metric');
    expect(state.resolvedDecisionKey).toBe('row_grain');
    expect(state.awaitingUser.decisionKey).toBe('primary_metric');
  });

  it('keeps the current streamed ask_user answerable when active_decision refresh lags', () => {
    const state = payloadToCurrentOrchestrationState({
      session: { id: 's1', status: 'awaiting_answers' },
      decision_type: 'ask_user',
      workflow: { session_id: 's1', steps: [{ step_type: 'validate', status: 'awaiting_user' }] },
      active_decision: null,
      awaiting_user: {
        decision_key: 'confirmation',
        question: 'ขั้นตอน validate ต้องการอนุมัติหรือไม่?',
        expected_input: 'option_or_text',
        options: [
          { id: 'approve', label: 'ดำเนินการต่อ' },
          { id: 'reject', label: 'ไม่ดำเนินการ' },
        ],
      },
    });

    expect(state.activeDecision.decisionKey).toBe('confirmation');
    expect(state.awaitingUser.options).toHaveLength(2);
  });

  it('prefers explicit stream session_status over a lagging session object', () => {
    const state = payloadToCurrentOrchestrationState({
      session: { id: 's1', status: 'processing', updated_at: 't0' },
      session_status: 'awaiting_answers',
      updated_at: 't1',
      decision_type: 'ask_user',
      active_decision: {
        decision_key: 'confirmation',
        status: 'pending',
        question: 'อนุมัติหรือไม่?',
        options: [{ value: 'approve', label: 'OK' }],
      },
    });
    expect(state.sessionStatus).toBe('awaiting_answers');
    expect(state.updatedAt).toBe('t1');
  });

  it('surfaces incomplete_active_decision from the backend payload', () => {
    const state = payloadToCurrentOrchestrationState({
      session: { id: 's1', status: 'awaiting_answers' },
      active_decision: null,
      incomplete_active_decision: 'missing_question',
      awaiting_user: null,
    });
    expect(state.activeDecision).toBeNull();
    expect(state.incompleteActiveDecision).toBe('missing_question');
  });

  it('does not resurrect resolved row_grain from stale awaiting_user', () => {
    const state = payloadToCurrentOrchestrationState({
      session: { id: 's1', status: 'processing' },
      workflow: { session_id: 's1', steps: [] },
      active_decision: null,
      awaiting_user: {
        decision_key: 'row_grain',
        question: 'stale grain?',
        options: [{ id: 'invoice_line', label: 'ใช่ — รายการในบิล' }],
      },
      resolved_decision_key: 'row_grain',
    });
    expect(state.activeDecision).toBeNull();
    expect(state.awaitingUser).toBeNull();
    expect(state.resolvedDecisionKey).toBe('row_grain');
  });

  it('preserves row_grain options from active_decision', () => {
    const opts = [
      { id: 'invoice_line', label: 'ใช่ — รายการในบิล', value: 'invoice_line' },
      { id: 'invoice', label: 'ไม่ใช่ — ทั้งบิล', value: 'invoice' },
    ];
    const state = payloadToCurrentOrchestrationState({
      session: { id: 's1', status: 'awaiting_answers' },
      workflow: { session_id: 's1', steps: [] },
      active_decision: {
        decision_key: 'row_grain',
        status: 'pending',
        question: 'grain?',
        expected_input: 'option_or_text',
        options: opts,
      },
    });
    expect(state.activeDecision.options).toHaveLength(2);
    expect(state.awaitingUser.options[0].label).toBe('ใช่ — รายการในบิล');
  });
});

describe('isActiveDecisionComplete update3', () => {
  it('rejects single_choice with empty options', () => {
    expect(isActiveDecisionComplete({
      decisionKey: 'row_grain',
      status: 'pending',
      question: 'grain?',
      expectedInput: 'single_choice',
      options: [],
      freeTextAllowed: false,
    })).toBe(false);
  });
});

describe('applyCurrentOrchestrationReplacements', () => {
  it('does not let an immediately stale resume response erase the current ask_user controls', () => {
    const activeDecision = {
      decisionKey: 'confirmation',
      status: 'pending',
      question: 'อนุมัติหรือไม่?',
      options: [{ value: 'approve', label: 'ดำเนินการต่อ' }],
    };
    const awaitingUser = {
      decisionKey: 'confirmation',
      question: 'อนุมัติหรือไม่?',
      options: activeDecision.options,
    };
    const merged = applyCurrentOrchestrationReplacements(
      { ...createEmptyCurrentOrchestrationState(), activeDecision, awaitingUser },
      {
        ...createEmptyCurrentOrchestrationState(),
        sessionStatus: 'awaiting_answers',
        stopReason: 'awaiting_user',
      },
    );

    expect(merged.activeDecision).toEqual(activeDecision);
    expect(merged.awaitingUser).toEqual(awaitingUser);
  });

  it('preserves the live ask when a lagging resume still reports processing', () => {
    const activeDecision = {
      decisionKey: 'confirmation',
      status: 'pending',
      question: 'อนุมัติหรือไม่?',
      options: [{ value: 'approve', label: 'ดำเนินการต่อ' }],
    };
    const awaitingUser = {
      decisionKey: 'confirmation',
      question: 'อนุมัติหรือไม่?',
      options: activeDecision.options,
    };
    const merged = applyCurrentOrchestrationReplacements(
      { ...createEmptyCurrentOrchestrationState(), activeDecision, awaitingUser },
      {
        ...createEmptyCurrentOrchestrationState(),
        sessionStatus: 'processing',
        stopReason: null,
      },
    );

    expect(merged.activeDecision).toEqual(activeDecision);
    expect(merged.awaitingUser).toEqual(awaitingUser);
  });

  it('clears the question after the workflow leaves awaiting_answers', () => {
    const merged = applyCurrentOrchestrationReplacements(
      {
        ...createEmptyCurrentOrchestrationState(),
        activeDecision: { decisionKey: 'confirmation', status: 'pending' },
        awaitingUser: { question: 'อนุมัติหรือไม่?' },
      },
      { ...createEmptyCurrentOrchestrationState(), sessionStatus: 'ready' },
    );

    expect(merged.activeDecision).toBeNull();
    expect(merged.awaitingUser).toBeNull();
  });
});

describe('shouldPollSetupState', () => {
  const base = {
    sessionStatus: 'processing',
    workflowPlan: { steps: [{ step_type: 'map', status: 'running' }] },
    activeDecision: null,
    awaitingUser: null,
    pollRecommended: false,
    noProgress: false,
    stopReason: null,
  };

  it('polls only when running step or poll_recommended', () => {
    expect(shouldPollSetupState(base)).toBe(true);
    expect(shouldPollSetupState({ ...base, pollRecommended: true })).toBe(true);
  });

  it('stops polling when awaiting user or stable states', () => {
    expect(shouldPollSetupState({
      ...base,
      sessionStatus: 'awaiting_answers',
      awaitingUser: { question: '?' },
    })).toBe(false);
    expect(shouldPollSetupState({ ...base, sessionStatus: 'ready' })).toBe(false);
    expect(shouldPollSetupState({ ...base, noProgress: true })).toBe(false);
    expect(shouldPollSetupState({ ...base, stopReason: 'action_limit_reached' })).toBe(false);
  });
});

describe('buildStateFingerprint', () => {
  it('changes when workflow step status changes', () => {
    const a = buildStateFingerprint({
      sessionStatus: 'processing',
      workflowPlan: { steps: [{ step_type: 'map', status: 'running', version: 1 }] },
    });
    const b = buildStateFingerprint({
      sessionStatus: 'processing',
      workflowPlan: { steps: [{ step_type: 'map', status: 'completed', version: 1 }] },
    });
    expect(a).not.toBe(b);
  });
});

describe('reconcileSetupState out-of-order guard', () => {
  beforeEach(() => {
    resetReconcileSequenceForTests();
  });

  it('marks stale when a newer reconcile started', async () => {
    const baseSession = {
      id: 's1',
      status: 'processing',
      source_type: 'file',
      source_ref: { file_name: 'a.csv' },
    };
    const authFetch = vi.fn()
      .mockImplementationOnce(async () => {
        await new Promise((r) => setTimeout(r, 40));
        return {
          ok: true,
          json: async () => ({
            session: baseSession,
            workflow: { steps: [] },
            active_decision: null,
          }),
        };
      })
      .mockImplementationOnce(async () => ({
        ok: true,
        json: async () => ({
          session: { ...baseSession, status: 'ready' },
          workflow: { steps: [] },
          active_decision: null,
        }),
      }));

    const slow = reconcileSetupState({
      authFetch,
      getPublicApiUrl: () => 'http://test',
      session: baseSession,
    });
    const fast = reconcileSetupState({
      authFetch,
      getPublicApiUrl: () => 'http://test',
      session: baseSession,
    });
    const fastResult = await fast;
    const slowResult = await slow;
    expect(fastResult.stale).toBe(false);
    expect(fastResult.state.sessionStatus).toBe('ready');
    expect(slowResult.stale).toBe(true);
  });

  it('only calls resume endpoint (no chat stream)', async () => {
    const authFetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session: {
          id: 's1',
          status: 'processing',
          source_type: 'file',
          source_ref: { file_name: 'a.csv' },
        },
        workflow: { steps: [] },
      }),
    });
    await reconcileSetupState({
      authFetch,
      getPublicApiUrl: () => 'http://test',
      sessionId: 's1',
      session: { id: 's1', source_type: 'file', source_ref: { file_name: 'a.csv' } },
    });
    expect(authFetch).toHaveBeenCalledTimes(1);
    expect(authFetch.mock.calls[0][0]).toContain('/data-setup/resume');
  });
});

describe('pollIntervalMs', () => {
  it('uses adaptive backoff intervals', () => {
    expect(pollIntervalMs(1000)).toBe(2000);
    expect(pollIntervalMs(10000)).toBe(3000);
    expect(pollIntervalMs(30000)).toBe(5000);
    expect(pollIntervalMs(70000, 15)).toBe(10000);
  });
});
describe('createEmptyCurrentOrchestrationState', () => {
  it('starts with null live decision fields', () => {
    const empty = createEmptyCurrentOrchestrationState();
    expect(empty.activeDecision).toBeNull();
    expect(empty.awaitingUser).toBeNull();
    expect(empty.workflowPlan).toBeNull();
  });
});
