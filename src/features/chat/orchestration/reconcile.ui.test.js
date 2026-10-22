import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import React from 'react';
import OrchestrationMessage from './OrchestrationMessage';
import CurrentWorkflowPanel from './CurrentWorkflowPanel';
import WorkflowQuestionCard from './WorkflowQuestionCard';
import { payloadToCurrentOrchestrationState } from './reconcileSetupState.js';
import { buildSetupAuditPresentation } from './setupAuditPresentation.js';

describe('OrchestrationMessage historical mode', () => {
  it('does not render WorkflowProgress or interactive buttons', () => {
    const html = renderToStaticMarkup(
      React.createElement(OrchestrationMessage, {
        orchestration: {
          workflow: {
            status: 'processing',
            steps: [{ step_type: 'inspect', status: 'completed' }],
          },
          awaiting_user: {
            question: 'Confirm grain?',
            options: [{ value: 'yes', label: 'Yes' }],
          },
        },
        historical: true,
      }),
    );
    expect(html).not.toContain('data-testid="workflow-progress"');
    expect(html).not.toContain('<button');
    expect(html).toContain('data-testid="resolved-answer-history"');
    expect(html).not.toContain('<details open');
    expect(html).toContain('ประวัติคำตอบ');
  });

  it('renders worklog stamps in timeline', () => {
    const html = renderToStaticMarkup(
      React.createElement(OrchestrationMessage, {
        orchestration: {
          worklog_stamps: [{
            stamp_id: 's1',
            stamp_type: 'decision_confirmed',
            title: 'Row grain confirmed',
            summary: 'invoice_line',
          }],
        },
        historical: true,
      }),
    );
    expect(html).toContain('Row grain confirmed');
  });

  it('collapses multiple mapping and context stamps into one stack', () => {
    const html = renderToStaticMarkup(
      React.createElement(OrchestrationMessage, {
        orchestration: {
          worklog_stamps: [
            {
              stamp_id: 's1',
              stamp_type: 'context_confirmed',
              title: 'Business context recorded',
              summary: 'Primary metric → sales',
            },
            {
              stamp_id: 's2',
              stamp_type: 'mapping_confirmed',
              title: 'Mapping confirmed',
              summary: 'Order ID → invoice',
            },
            {
              stamp_id: 's3',
              stamp_type: 'validation_completed',
              title: 'Validation completed',
            },
          ],
        },
        historical: true,
        isEn: false,
      }),
    );

    expect(html).toContain('data-testid="worklog-stamp-stack"');
    expect(html).toContain('คำถาม Mapping และประวัติการทำงาน');
    expect(html).toContain('3 บันทึก');
    expect(html).toContain('Business context recorded');
    expect(html).not.toContain('<details open');
  });

  it('combines a completed setup loop and hides workflow answer bubbles', () => {
    const presentation = buildSetupAuditPresentation([
      { role: 'user', content: 'sales.xlsx', attachment: 'sales.xlsx' },
      {
        role: 'ai',
        content: 'Primary metric?',
        orchestration: {
          workflow: { session_id: 'setup-1', status: 'awaiting_user' },
          awaiting_user: { decision_key: 'primary_metric', question: 'Primary metric?' },
          worklog_stamps: [{ stamp_id: 's1', title: 'Source inspected' }],
        },
      },
      { role: 'user', content: 'Sales', workflowResolution: { decision_key: 'primary_metric' } },
      {
        role: 'ai',
        content: 'Invoice column?',
        orchestration: {
          workflow: { session_id: 'setup-1', status: 'awaiting_user' },
          awaiting_user: { decision_key: 'mapping:invoice', question: 'Invoice column?' },
          worklog_stamps: [
            { stamp_id: 's1', title: 'Source inspected' },
            { stamp_id: 's2', title: 'Business context recorded' },
          ],
        },
      },
      { role: 'user', content: 'Order ID', workflowResolution: { decision_key: 'mapping:invoice' } },
      {
        role: 'ai',
        content: 'Setup ready',
        orchestration: {
          ready_for_analysis: true,
          workflow: { session_id: 'setup-1', status: 'ready' },
          worklog_stamps: [
            { stamp_id: 's1', title: 'Source inspected' },
            { stamp_id: 's2', title: 'Business context recorded' },
            { stamp_id: 's3', title: 'Dataset ready' },
          ],
        },
      },
      { role: 'user', content: 'วิเคราะห์ยอดขายต่อ' },
    ]);

    expect([...presentation.hiddenUserAnswerIndexes]).toEqual([2, 4]);
    expect([...presentation.hiddenCompletedAssistantIndexes]).toEqual([1, 3]);
    expect(presentation.hiddenUserAnswerIndexes.has(6)).toBe(false);
    expect(presentation.completedBySummaryIndex.get(5).exchanges).toHaveLength(2);
    expect(presentation.completedBySummaryIndex.get(5).stamps).toHaveLength(3);
  });
});

describe('CurrentWorkflowPanel singleton', () => {
  it('renders one live progress and one active question', () => {
    const state = payloadToCurrentOrchestrationState({
      session: { id: 's1', status: 'awaiting_answers' },
      workflow: {
        steps: [
          { step_type: 'inspect', status: 'completed' },
          { step_type: 'map', status: 'running' },
        ],
      },
      active_decision: {
        decision_key: 'row_grain',
        status: 'pending',
        question: 'Grain?',
        options: [{ value: 'invoice_line', label: 'Line' }],
      },
    });
    const html = renderToStaticMarkup(
      React.createElement(CurrentWorkflowPanel, {
        currentOrchestration: state,
        onResolve: vi.fn(),
      }),
    );
    expect(html).toContain('data-testid="current-workflow-panel"');
    expect(html).toContain('Grain?');
    expect(html).toContain('<button');
  });

  it('turns a missing active question into an actionable continuation', () => {
    const html = renderToStaticMarkup(
      React.createElement(CurrentWorkflowPanel, {
        currentOrchestration: payloadToCurrentOrchestrationState({
          session: { id: 's1', status: 'awaiting_answers' },
          workflow: {
            steps: [
              { step_type: 'inspect', status: 'completed' },
              { step_type: 'map', status: 'running' },
            ],
          },
          active_decision: null,
          awaiting_user: null,
          continuation_available: true,
          stop_reason: 'missing_active_decision',
        }),
        onContinue: vi.fn(),
        onReconcile: vi.fn(),
      }),
    );

    expect(html).toContain('พร้อมดำเนินการตั้งค่าต่อ');
    expect(html).toContain('ดำเนินการต่อ');
    expect(html).not.toContain('สถานะคำถามไม่สมบูรณ์');
  });

  it('surfaces recovery when finalize failed without a live question', () => {
    const html = renderToStaticMarkup(
      React.createElement(CurrentWorkflowPanel, {
        currentOrchestration: payloadToCurrentOrchestrationState({
          session: { id: 's1', status: 'processing' },
          workflow: {
            steps: [
              { step_type: 'clean', status: 'completed' },
              { step_type: 'finalize', status: 'failed' },
            ],
          },
          active_decision: null,
          awaiting_user: null,
        }),
        onContinue: vi.fn(),
        onReconcile: vi.fn(),
      }),
    );

    expect(html).toContain('data-testid="incomplete-active-decision-recovery"');
    expect(html).toContain('มีขั้นตอนที่ล้มเหลว');
    expect(html).toContain('ดำเนินการต่อ');
  });

  it('surfaces backend incomplete_active_decision in the recovery card', () => {
    const html = renderToStaticMarkup(
      React.createElement(CurrentWorkflowPanel, {
        currentOrchestration: payloadToCurrentOrchestrationState({
          session: { id: 's1', status: 'awaiting_answers' },
          workflow: { steps: [{ step_type: 'validate', status: 'awaiting_user' }] },
          active_decision: null,
          incomplete_active_decision: 'missing_question',
        }),
        onContinue: vi.fn(),
        onReconcile: vi.fn(),
      }),
    );

    expect(html).toContain('data-testid="incomplete-active-decision-recovery"');
    expect(html).toContain('data-incomplete-reason="missing_question"');
    expect(html).toContain('ข้อความคำถามไม่สมบูรณ์');
  });

  it('renders live worklog stamps in the singleton panel', () => {
    const html = renderToStaticMarkup(
      React.createElement(CurrentWorkflowPanel, {
        currentOrchestration: payloadToCurrentOrchestrationState({
          session: { id: 's1', status: 'processing' },
          workflow: { steps: [{ step_type: 'inspect', status: 'completed' }] },
          worklog_stamps: [
            {
              stamp_id: 's1',
              stamp_type: 'tool_completed',
              title: 'Source inspected',
              summary: '18 columns',
            },
            {
              stamp_id: 's2',
              stamp_type: 'decision_confirmed',
              title: 'Row grain confirmed',
              summary: 'invoice_line',
            },
          ],
        }),
      }),
    );

    expect(html).toContain('data-testid="worklog-stamp-stack"');
    expect(html).toContain('Source inspected');
    expect(html).toContain('Row grain confirmed');
  });
});

describe('WorkflowQuestionCard failure unlock', () => {
  it('allows buttons when decisionStatus returns to pending', () => {
    const html = renderToStaticMarkup(
      React.createElement(WorkflowQuestionCard, {
        awaitingUser: {
          decisionKey: 'row_grain',
          question: 'Q?',
          options: [{ value: 'yes', label: 'Yes', decision: 'approved' }],
        },
        decisionStatus: 'pending',
        onResolve: vi.fn(),
      }),
    );
    expect(html).toContain('<button type="button" aria-busy="false"');
  });
});

describe('duplicate active question guard', () => {
  it('historical message is read-only while panel owns interactive question', () => {
    const historical = renderToStaticMarkup(
      React.createElement(OrchestrationMessage, {
        orchestration: {
          awaiting_user: {
            decision_key: 'row_grain',
            question: 'Old?',
            options: [{ value: 'yes', label: 'Yes' }],
          },
        },
        historical: true,
      }),
    );
    const live = renderToStaticMarkup(
      React.createElement(CurrentWorkflowPanel, {
        currentOrchestration: payloadToCurrentOrchestrationState({
          session: { id: 's1', status: 'awaiting_answers' },
          workflow: { steps: [{ step_type: 'map', status: 'running' }] },
          active_decision: {
            decision_key: 'primary_metric',
            status: 'pending',
            question: 'Metric?',
            options: [{ value: 'sales', label: 'Sales' }],
          },
        }),
        onResolve: vi.fn(),
      }),
    );
    expect(historical).not.toContain('<button');
    expect(live).toContain('Metric?');
    expect(live).toContain('<button');
  });

  it('renders validate approval controls when streamed ask_user arrives before active decision refresh', () => {
    const live = renderToStaticMarkup(
      React.createElement(CurrentWorkflowPanel, {
        currentOrchestration: payloadToCurrentOrchestrationState({
          session: { id: 's1', status: 'awaiting_answers' },
          decision_type: 'ask_user',
          workflow: {
            session_id: 's1',
            status: 'awaiting_answers',
            steps: [{ step_type: 'validate', status: 'awaiting_user' }],
          },
          active_decision: null,
          awaiting_user: {
            decision_key: 'confirmation',
            step_type: 'validate',
            question: 'ขั้นตอน validate ต้องการอนุมัติหรือไม่?',
            expected_input: 'option_or_text',
            options: [
              { id: 'approve', label: 'ดำเนินการต่อ' },
              { id: 'reject', label: 'ไม่ดำเนินการ' },
            ],
          },
        }),
        onResolve: vi.fn(),
      }),
    );

    expect(live).toContain('ขั้นตอน validate ต้องการอนุมัติหรือไม่?');
    expect(live).toContain('ดำเนินการต่อ');
    expect(live).toContain('ไม่ดำเนินการ');
    expect(live).toContain('พิมพ์คำตอบเอง');
  });

  it('hides the unresolved latest historical question while the live panel owns it', () => {
    const historical = renderToStaticMarkup(
      React.createElement(OrchestrationMessage, {
        orchestration: {
          awaiting_user: {
            decision_key: 'primary_metric',
            question: 'Is Sales the primary metric?',
            options: [{ value: 'sales', label: 'Sales' }],
          },
        },
        historical: true,
        hideUnresolvedQuestion: true,
      }),
    );

    expect(historical).not.toContain('Is Sales the primary metric?');
  });

  it('keeps a resolved historical question inside a collapsed answer history', () => {
    const historical = renderToStaticMarkup(
      React.createElement(OrchestrationMessage, {
        orchestration: {
          awaiting_user: {
            decision_key: 'primary_metric',
            question: 'Is Sales the primary metric?',
          },
        },
        historical: true,
        hideUnresolvedQuestion: true,
        resolvedAnswerLabel: 'Sales',
      }),
    );

    expect(historical).toContain('Is Sales the primary metric?');
    expect(historical).toContain('Sales');
    expect(historical).toContain('บันทึกแล้ว');
    expect(historical).toContain('data-testid="resolved-answer-history"');
    expect(historical).not.toContain('<details open');
  });
});
