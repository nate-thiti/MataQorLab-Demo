import { describe, expect, it } from 'vitest';
import {
  normalizeOrchestration,
  buildFreeTextResolutionSendOptions,
  buildResolutionSendOptions,
  buildRetrySendOptions,
  compactProgressView,
  isConversationalSetupActive,
  inferDecisionFromValue,
} from './normalize.js';
import { workflowStepLabel } from './labels.js';

const samplePayload = {
  decision_type: 'ask_user',
  options: [
    { value: 'approved', label: 'ดำเนินการต่อ' },
    { value: 'standard', label: 'ใช้ Standard', decision: 'modified' },
    { value: 'rejected', label: 'ไม่ดำเนินการ' },
  ],
  awaiting_user: {
    reason_code: 'AGGRESSIVE_CLEANING',
    question: 'Deep Clean may modify more records.',
    step_type: 'clean',
    context: { count: 327, percent: 1.4 },
  },
  workflow: {
    session_id: 'sess-1',
    status: 'awaiting_user',
    current_step: 'clean',
    steps: [
      { step_type: 'inspect', status: 'completed' },
      { step_type: 'prepare', status: 'completed' },
      { step_type: 'clean', status: 'awaiting_user', retryable: false },
      { step_type: 'map', status: 'pending' },
      { step_type: 'validate', status: 'stale', stale_reason: 'map_changed' },
      { step_type: 'finalize', status: 'skipped' },
    ],
  },
  tool_result: {
    step_type: 'inspect',
    status: 'completed',
    summary: '82,421 rows',
    findings: [{ type: 'duplicate', count: 147 }],
    warnings: [],
    metadata: { columns: 18 },
  },
  source: { name: 'sales.xlsx', row_count: 82421, column_count: 18 },
  assurance: {
    computation: 'pending',
    data_readiness: 'pending',
    business_context: 'pending',
  },
  ready_for_analysis: false,
};

describe('workflowStepLabel', () => {
  it('keeps backend IDs and maps Thai labels', () => {
    expect(workflowStepLabel('inspect', false)).toBe('ตรวจสอบข้อมูล');
    expect(workflowStepLabel('clean', true)).toBe('Cleaning');
  });
});

describe('normalizeOrchestration', () => {
  it('normalizes backend-grounded step statuses without inventing progress', () => {
    const view = normalizeOrchestration(samplePayload, false);
    expect(view.workflow.steps).toHaveLength(6);
    expect(view.workflow.steps.find((s) => s.stepType === 'inspect').status).toBe('completed');
    expect(view.workflow.steps.find((s) => s.stepType === 'clean').status).toBe('awaiting_user');
    expect(view.workflow.steps.find((s) => s.stepType === 'validate').status).toBe('stale');
    expect(view.workflow.steps.find((s) => s.stepType === 'finalize').status).toBe('skipped');
    expect(view.awaitingUser.reasonCode).toBe('AGGRESSIVE_CLEANING');
    expect(view.toolResult.findings[0].count).toBe(147);
    expect(view.source.rowCount).toBe(82421);
  });

  it('marks ready transition from backend flag', () => {
    const view = normalizeOrchestration({
      decision_type: 'respond',
      workflow: {
        status: 'ready',
        ready_for_analysis: true,
        steps: [
          { step_type: 'finalize', status: 'completed' },
        ],
      },
      ready_for_analysis: true,
      assurance: {
        computation: 'verified',
        data_readiness: 'ready',
        business_context: 'confirmed',
      },
    });
    expect(view.readyForAnalysis).toBe(true);
    expect(view.assurance.businessContext).toBe('confirmed');
  });

  it('tolerates missing optional tool fields', () => {
    const view = normalizeOrchestration({
      tool_result: { step_type: 'map', status: 'completed' },
    });
    expect(view.toolResult.findings).toEqual([]);
    expect(view.toolResult.summary).toBeNull();
  });

  it('preserves the active question input mode for free-text guidance', () => {
    const view = normalizeOrchestration({
      awaiting_user: {
        decision_key: 'data_owner',
        question: 'Who owns this dataset?',
        expected_input: 'free_text',
        free_text_allowed: true,
        options: [],
      },
    });
    expect(view.awaitingUser.expectedInput).toBe('free_text');
    expect(view.awaitingUser.freeTextAllowed).toBe(true);
  });

  it('localizes deterministic Thai fallback questions and options for English UI', () => {
    const view = normalizeOrchestration({
      awaiting_user: {
        decision_key: 'row_grain',
        question: 'ข้อมูลหนึ่งแถวแทนหน่วยใด?',
        options: [
          { id: 'source_record', value: 'source_record', label: 'หนึ่งระเบียนจากข้อมูลต้นทาง' },
          { id: 'other', value: 'other', label: 'หน่วยอื่น' },
        ],
      },
    }, true);

    expect(view.awaitingUser.question).toBe('What does one row represent in this dataset?');
    expect(view.awaitingUser.options.map((option) => option.label)).toEqual([
      'One source record',
      'Other',
    ]);
  });

  it('detects failed retryable steps', () => {
    const view = normalizeOrchestration({
      workflow: {
        status: 'failed',
        steps: [
          { step_type: 'clean', status: 'failed', retryable: true },
        ],
      },
      tool_result: { step_type: 'clean', status: 'failed', summary: 'boom' },
    });
    expect(view.errorKind).toBe('tool_failure');
    expect(view.workflow.steps.find((s) => s.stepType === 'clean').retryable).toBe(true);
  });
});

describe('option / retry send contracts', () => {
  it('builds a single structured resolution payload', () => {
    const option = { value: 'standard', label: 'ใช้ Standard', decision: 'modified' };
    const send = buildResolutionSendOptions(option, { stepType: 'clean', reasonCode: 'AGGRESSIVE_CLEANING' });
    expect(send.contentOverride).toBe('ใช้ Standard');
    expect(send.orchestrationResolution.decision).toBe('modified');
    expect(send.orchestrationResolution.context_updates.cleaning_profile).toBe('standard');
  });

  it('builds a decision-aware payload for an answer typed in the question card', () => {
    const send = buildFreeTextResolutionSendOptions('  ฝ่ายการเงิน  ', {
      decisionKey: 'data_owner',
      stepType: 'prepare',
      reasonCode: 'MISSING_BUSINESS_CONTEXT',
    });
    expect(send).toEqual({
      contentOverride: 'ฝ่ายการเงิน',
      orchestrationResolution: {
        value: 'ฝ่ายการเงิน',
        step_type: 'prepare',
        reason_code: 'MISSING_BUSINESS_CONTEXT',
        decision_key: 'data_owner',
      },
    });
  });

  it('builds retry through chat/orchestrator path', () => {
    const send = buildRetrySendOptions('clean', false);
    expect(send.orchestrationResolution).toEqual({
      action: 'retry',
      step_type: 'clean',
    });
  });

  it('infers reject/approve from values', () => {
    expect(inferDecisionFromValue('rejected')).toBe('rejected');
    expect(inferDecisionFromValue('ดำเนินการต่อ')).toBe('approved');
    expect(inferDecisionFromValue('invoice_line')).toBeNull();
  });

  it('maps modify on aggressive cleaning to standard profile', () => {
    const send = buildResolutionSendOptions(
      { value: 'modify', label: 'เปลี่ยนเป็น Standard' },
      { stepType: 'clean', reasonCode: 'AGGRESSIVE_CLEANING', decisionKey: 'cleaning_confirmation' },
    );
    expect(send.orchestrationResolution.decision).toBe('modified');
    expect(send.orchestrationResolution.context_updates.cleaning_profile).toBe('standard');
  });

  it('preserves option id alongside value', () => {
    const view = normalizeOrchestration({
      awaiting_user: {
        question: 'Q?',
        options: [{ id: 'approve', label: 'OK' }],
      },
    });
    expect(view.awaitingUser.options[0]).toMatchObject({
      id: 'approve',
      value: 'approve',
      label: 'OK',
      decision: 'approved',
    });
  });
});

describe('compact progress + setup active', () => {
  it('summarizes active step for mobile', () => {
    const view = normalizeOrchestration(samplePayload);
    const compact = compactProgressView(view.workflow.steps);
    expect(compact.completed).toBe(2);
    expect(compact.active.stepType).toBe('clean');
  });

  it('disables setup controls when ready', () => {
    expect(isConversationalSetupActive(
      { readyForAnalysis: true, workflow: { status: 'ready' } },
      'ready',
    )).toBe(false);
  });
});
