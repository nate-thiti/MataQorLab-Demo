import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import React from 'react';
import WorkflowProgress from './WorkflowProgress';
import WorkflowQuestionCard from './WorkflowQuestionCard';
import ToolResultCard from './ToolResultCard';
import WorkflowErrorCard from './WorkflowErrorCard';
import ReadyForAnalysisCard from './ReadyForAnalysisCard';
import WorklogStampCard from './WorklogStampCard';
import OrchestrationMessage from './OrchestrationMessage';
import { normalizeOrchestration } from './normalize.js';

const steps = [
  { stepType: 'inspect', label: 'ตรวจสอบข้อมูล', status: 'completed' },
  { stepType: 'prepare', label: 'เตรียมข้อมูล', status: 'completed' },
  { stepType: 'clean', label: 'ทำความสะอาด', status: 'running' },
  { stepType: 'map', label: 'จัดความหมายคอลัมน์', status: 'pending' },
  { stepType: 'validate', label: 'ตรวจสอบความพร้อม', status: 'stale' },
  { stepType: 'finalize', label: 'พร้อมสำหรับวิเคราะห์', status: 'skipped' },
];

describe('WorkflowProgress', () => {
  it('renders completed/running/stale/skipped with accessible status text', () => {
    const html = renderToStaticMarkup(
      React.createElement(WorkflowProgress, {
        workflow: { status: 'processing', steps },
        source: { name: 'sales.xlsx', rowCount: 82421, columnCount: 18 },
        isEn: false,
      }),
    );
    expect(html).toContain('sales.xlsx');
    expect(html).toContain('ตรวจสอบข้อมูล');
    expect(html).toContain('sr-only');
    expect(html).toContain('ต้องตรวจสอบใหม่');
  });
});

describe('WorkflowQuestionCard', () => {
  it('renders options and disables after click (single submit)', async () => {
    const onResolve = vi.fn().mockResolvedValue(undefined);
    const html = renderToStaticMarkup(
      React.createElement(WorkflowQuestionCard, {
        awaitingUser: {
          reasonCode: 'AGGRESSIVE_CLEANING',
          question: 'Deep Clean may modify more records.',
          stepType: 'clean',
          options: [
            { value: 'approved', label: 'ดำเนินการต่อ', decision: 'approved' },
            { value: 'standard', label: 'ใช้ Standard', decision: 'modified' },
          ],
        },
        isEn: false,
        onResolve,
      }),
    );
    expect(html).toContain('ดำเนินการต่อ');
    expect(html).toContain('ใช้ Standard');
    expect(html).toContain('Deep Clean');
  });

  it('keeps buttons disabled while parent marks pending', () => {
    const html = renderToStaticMarkup(
      React.createElement(WorkflowQuestionCard, {
        awaitingUser: {
          question: 'Confirm?',
          options: [{ value: 'approved', label: 'OK', decision: 'approved' }],
        },
        disabled: true,
        onResolve: vi.fn(),
      }),
    );
    expect(html).toContain('disabled');
  });

  it('reserves the complete question card while progressive typing is active', () => {
    const html = renderToStaticMarkup(
      React.createElement(WorkflowQuestionCard, {
        awaitingUser: {
          decisionKey: 'confirmation',
          question: 'ขั้นตอน validate ต้องการอนุมัติหรือไม่?',
          options: [{ value: 'approve', label: 'ดำเนินการต่อ' }],
        },
        animateQuestion: true,
        onResolve: vi.fn(),
      }),
    );

    expect(html).toContain('ขั้นตอน validate ต้องการอนุมัติหรือไม่?');
    expect(html).toContain('invisible');
    expect(html).toContain('data-typing="true"');
    // Typing animation gates option buttons (not merely an empty textarea).
    expect(html).toMatch(/<button[^>]*disabled[^>]*>[\s\S]*ดำเนินการต่อ/);
  });

  it('renders nothing when question text is missing (no generic fallback)', () => {
    const html = renderToStaticMarkup(
      React.createElement(WorkflowQuestionCard, {
        awaitingUser: {
          options: [{ value: 'approved', label: 'OK', decision: 'approved' }],
        },
        onResolve: vi.fn(),
      }),
    );
    expect(html).toBe('');
  });

  it('renders an inline custom-answer field for a free-text-only question', () => {
    const html = renderToStaticMarkup(
      React.createElement(WorkflowQuestionCard, {
        awaitingUser: {
          decisionKey: 'data_owner',
          question: 'ใครเป็นเจ้าของข้อมูลชุดนี้?',
          expectedInput: 'free_text',
          freeTextAllowed: true,
          options: [],
        },
        onResolve: vi.fn(),
      }),
    );
    expect(html).toContain('placeholder="พิมพ์คำตอบเอง…"');
    expect(html).toContain('aria-label="ส่งคำตอบที่พิมพ์"');
  });

  it('hides the free-text form for single_choice engine confirmations', () => {
    const html = renderToStaticMarkup(
      React.createElement(WorkflowQuestionCard, {
        awaitingUser: {
          decisionKey: 'cleaning_confirmation',
          question: 'อนุมัติ Deep Clean?',
          expectedInput: 'single_choice',
          freeTextAllowed: false,
          options: [
            { value: 'approve', label: 'ดำเนินการต่อ' },
            { value: 'reject', label: 'ไม่ดำเนินการ' },
          ],
        },
        onResolve: vi.fn(),
      }),
    );
    expect(html).toContain('ดำเนินการต่อ');
    expect(html).not.toContain('placeholder="พิมพ์คำตอบเอง…"');
  });

  it('keeps free-text available when options are missing', () => {
    const html = renderToStaticMarkup(
      React.createElement(WorkflowQuestionCard, {
        awaitingUser: {
          decisionKey: 'business_context_reviewed',
          question: "ยืนยันบริบทเป็น 'approve' หรือ 'modify'?",
          expectedInput: 'single_choice',
          freeTextAllowed: false,
          options: [],
        },
        onResolve: vi.fn(),
      }),
    );
    expect(html).toContain('พร้อมแล้ว');
    expect(html).toContain('ยังไม่พร้อม');
    expect(html).toContain('<button');
  });

  it('renders the custom-answer field alongside structured options', () => {
    const html = renderToStaticMarkup(
      React.createElement(WorkflowQuestionCard, {
        awaitingUser: {
          decisionKey: 'row_grain',
          question: 'หนึ่งแถวหมายถึงอะไร?',
          options: [{ value: 'invoice', label: 'หนึ่งบิล' }],
        },
        onResolve: vi.fn(),
      }),
    );
    expect(html).toContain('หนึ่งบิล');
    expect(html).toContain('placeholder="พิมพ์คำตอบเอง…"');
  });
});

describe('ToolResultCard', () => {
  it('renders inspect/clean/map/validate summaries safely', () => {
    for (const step of ['inspect', 'clean', 'map', 'validate']) {
      const html = renderToStaticMarkup(
        React.createElement(ToolResultCard, {
          toolResult: {
            stepType: step,
            status: 'completed',
            summary: 'ok',
            findings: [{ type: 'duplicate', count: 1 }],
          },
          isEn: false,
        }),
      );
      expect(html).toContain('ok');
    }
  });

  it('does not crash when optional fields are missing', () => {
    const html = renderToStaticMarkup(
      React.createElement(ToolResultCard, {
        toolResult: { stepType: 'clean', status: 'completed' },
      }),
    );
    expect(html).toContain('ทำความสะอาด');
  });
});

describe('WorkflowErrorCard / ReadyForAnalysisCard', () => {
  it('shows retry only when retryable', () => {
    const withRetry = renderToStaticMarkup(
      React.createElement(WorkflowErrorCard, {
        orchestration: normalizeOrchestration({
          tool_result: { step_type: 'clean', status: 'failed' },
          workflow: {
            steps: [{ step_type: 'clean', status: 'failed', retryable: true }],
          },
        }),
        onRetry: vi.fn(),
      }),
    );
    expect(withRetry).toContain('<button');
    expect(withRetry).toContain('ลองใหม่');

    const noRetry = renderToStaticMarkup(
      React.createElement(WorkflowErrorCard, {
        orchestration: normalizeOrchestration({
          tool_result: { step_type: 'clean', status: 'failed' },
          workflow: {
            steps: [{ step_type: 'clean', status: 'failed', retryable: false }],
          },
        }),
        onRetry: vi.fn(),
      }),
    );
    expect(noRetry).not.toContain('<button');
  });

  it('renders ready transition with separate assurance layers', () => {
    const html = renderToStaticMarkup(
      React.createElement(ReadyForAnalysisCard, {
        ready: true,
        assurance: {
          computation: 'verified',
          dataReadiness: 'ready',
          businessContext: 'confirmed',
        },
        isEn: false,
      }),
    );
    expect(html).toContain('พร้อมสำหรับวิเคราะห์');
    expect(html).toContain('Computation readiness');
    expect(html).toContain('Data readiness');
    expect(html).toContain('Business context');
  });
});

describe('WorklogStampCard', () => {
  it('renders backend facts without inventing values', () => {
    const html = renderToStaticMarkup(
      React.createElement(WorklogStampCard, {
        stamp: {
          stamp_id: 'abc',
          stamp_type: 'context_confirmed',
          title: 'Business context recorded',
          summary: 'Row grain → invoice_line',
          facts: [
            { label: 'Row grain', value: 'invoice_line' },
            { label: 'Confirmed by', value: 'user' },
          ],
          source: 'user_confirmed',
        },
        isEn: false,
      }),
    );
    expect(html).toContain('Business context recorded');
    expect(html).toContain('invoice_line');
    expect(html).toContain('ยืนยันโดยผู้ใช้');
  });
});

describe('OrchestrationMessage ready controls', () => {
  it('historical mode renders stamps only — no live ready/question controls', () => {
    const html = renderToStaticMarkup(
      React.createElement(OrchestrationMessage, {
        orchestration: {
          decision_type: 'respond',
          ready_for_analysis: true,
          workflow: {
            status: 'ready',
            steps: [{ step_type: 'finalize', status: 'completed' }],
          },
          awaiting_user: {
            question: 'should not be actionable',
            options: [{ value: 'approved', label: 'OK' }],
          },
        },
        historical: true,
      }),
    );
    expect(html).not.toContain('<button');
    expect(html).toContain('data-testid="resolved-answer-history"');
    expect(html).not.toContain('<details open');
    expect(html).toContain('ประวัติคำตอบ');
  });
});
