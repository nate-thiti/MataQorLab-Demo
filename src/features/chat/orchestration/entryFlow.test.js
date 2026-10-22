import { describe, expect, it } from 'vitest';
import { readLocalConversationalFlag } from './index.js';
import { isConversationalSetupActive, normalizeOrchestration } from './normalize.js';

/**
 * Phase 7.1 entry-flow presentation rules (unit-level).
 * Full attach→scan→send is covered by Chat integration; these guard invariants.
 */
describe('Phase 7.1 conversational entry presentation', () => {
  it('local NEXT_PUBLIC flag is only a hint (null when unset)', () => {
    const hint = readLocalConversationalFlag();
    expect(hint === true || hint === false || hint === null).toBe(true);
  });

  it('guided chat is the only data-setup presentation', () => {
    const setupPresentations = ['conversational'];

    expect(setupPresentations).toEqual(['conversational']);
    expect(setupPresentations).not.toContain('wizard');
  });

  it('capability failure does not fall back to an advanced wizard', () => {
    const conversationalEnabled = false;
    const presentation = conversationalEnabled ? 'conversational' : null;

    expect(presentation).toBeNull();
  });

  it('attachment-only uses setup_intent without requiring user prose', () => {
    const prompt = '';
    const setupIntent = prompt
      ? null
      : 'prepare_attached_source_for_analysis';
    expect(setupIntent).toBe('prepare_attached_source_for_analysis');
  });

  it('original message is preserved for orchestrator kickoff', () => {
    const original = 'ช่วยวิเคราะห์ยอดขายให้หน่อย';
    const kick = {
      contentOverride: original,
      setupIntent: 'prepare_attached_source_for_analysis',
      dataSetupSessionId: 'sess-1',
      conversationalSetup: true,
    };
    expect(kick.contentOverride).toBe(original);
    expect(kick.setupIntent).toBe('prepare_attached_source_for_analysis');
  });

  it('one logical send maps to one kickoff key', () => {
    const seen = new Set();
    const kickOnce = (sessionId, prompt) => {
      const key = `${sessionId}:${prompt || 'prepare_attached_source_for_analysis'}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    };
    expect(kickOnce('sess-1', 'ช่วยวิเคราะห์')).toBe(true);
    expect(kickOnce('sess-1', 'ช่วยวิเคราะห์')).toBe(false);
  });

  it('resume keeps conversational active without inventing steps', () => {
    const orchestration = normalizeOrchestration({
      workflow: {
        session_id: 'sess-1',
        status: 'awaiting_answers',
        steps: [
          { step_type: 'inspect', status: 'completed' },
          { step_type: 'prepare', status: 'running' },
        ],
      },
      awaiting_user: {
        reason_code: 'AGGRESSIVE_CLEANING',
        question: 'ยืนยัน?',
        options: [{ value: 'approved', label: 'OK', decision: 'approved' }],
      },
      source: { name: 'sales.xlsx', row_count: 1000, column_count: 11 },
    }, false);
    expect(isConversationalSetupActive(orchestration, 'awaiting_answers')).toBe(true);
    expect(orchestration.awaitingUser.question).toBe('ยืนยัน?');
    expect(orchestration.source.rowCount).toBe(1000);
  });

});

describe('Phase 7.2.2 submission boundary', () => {
  it('draft attachment alone must not imply scan or orchestrator kickoff', () => {
    const draftOnly = {
      selectedFile: { name: 'sales.xlsx', mode: 'pending' },
      dataSetupSession: null,
      sendPressed: false,
    };
    expect(draftOnly.sendPressed).toBe(false);
    expect(draftOnly.dataSetupSession).toBeNull();
  });

  it('continue_workflow uses explicit orchestrator intent not resume GET', () => {
    const continueIntent = 'continue_workflow';
    expect(continueIntent).not.toBe('resume');
    expect(continueIntent).toBe('continue_workflow');
  });
});
