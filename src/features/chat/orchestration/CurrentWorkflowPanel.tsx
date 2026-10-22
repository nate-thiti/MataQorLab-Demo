// @ts-nocheck
import { useEffect, useState } from 'react';
import { normalizeOrchestration } from './normalize.js';
import WorkflowProgress from './WorkflowProgress';
import WorkflowQuestionCard from './WorkflowQuestionCard';
import WorkflowErrorCard from './WorkflowErrorCard';
import ReadyForAnalysisCard from './ReadyForAnalysisCard';
import WorklogStampCard from './WorklogStampCard';
import WorklogStampStack from './WorklogStampStack';
import { deriveLiveAwaitingUser, isActiveDecisionComplete } from './reconcileSetupState.js';

const INCOMPLETE_DECISION_COPY = {
  missing_active_decision: {
    en: 'The current question is missing. Continue so the controller can ask again.',
    th: 'คำถามปัจจุบันหายไป ดำเนินการต่อเพื่อให้ Controller ถามใหม่',
  },
  missing_decision_key: {
    en: 'The current question has no decision key. Continue to recover.',
    th: 'คำถามปัจจุบันไม่มี decision key ดำเนินการต่อเพื่อกู้คืน',
  },
  missing_question: {
    en: 'The current question text is incomplete. Continue so the controller can ask again.',
    th: 'ข้อความคำถามไม่สมบูรณ์ ดำเนินการต่อเพื่อให้ Controller ถามใหม่',
  },
  missing_options_for_single_choice: {
    en: 'Choice options are missing for this question. Continue to recover.',
    th: 'ตัวเลือกของคำถามหายไป ดำเนินการต่อเพื่อกู้คืน',
  },
  missing_options_for_option_or_text: {
    en: 'Choice options are missing for this question. Continue to recover.',
    th: 'ตัวเลือกของคำถามหายไป ดำเนินการต่อเพื่อกู้คืน',
  },
  no_input_mode: {
    en: 'This question has no valid answer mode. Continue to recover.',
    th: 'คำถามนี้ไม่มีช่องทางตอบที่ถูกต้อง ดำเนินการต่อเพื่อกู้คืน',
  },
};

function incompleteDecisionMessage(code, isEn) {
  const entry = INCOMPLETE_DECISION_COPY[code];
  if (!entry) {
    return isEn
      ? 'The previous question could not be shown. Continue so the controller can select the next required question.'
      : 'แสดงคำถามก่อนหน้าไม่ได้ ดำเนินการต่อเพื่อให้ Controller เลือกคำถามที่จำเป็นข้อถัดไป';
  }
  return isEn ? entry.en : entry.th;
}

function stampPayload(stamp) {
  if (!stamp || typeof stamp !== 'object') return null;
  return {
    stamp_id: stamp.stampId || stamp.stamp_id,
    stamp_type: stamp.stampType || stamp.stamp_type,
    status: stamp.status,
    title: stamp.title,
    summary: stamp.summary,
    facts: stamp.facts,
    source: stamp.source,
  };
}

/**
 * Singleton live workflow view — exactly one per active setup session.
 * Historical messages must not render interactive setup controls.
 */
export default function CurrentWorkflowPanel({
  currentOrchestration,
  isEn = false,
  disabled = false,
  onResolve,
  onRetry,
  onReconcile,
  onContinue,
}) {
  const [submitting, setSubmitting] = useState(false);
  const {
    workflowPlan,
    source,
    activeDecision,
    incompleteActiveDecision,
    awaitingUser,
    currentBlocker,
    sessionStatus,
    worklogStamps,
    reconcileError,
    reconciling,
    noProgress,
    continuationAvailable,
    controllerActivity,
  } = currentOrchestration || {};

  const orchestrationRaw = {
    workflow: workflowPlan,
    source,
    awaiting_user: deriveLiveAwaitingUser(activeDecision, awaitingUser),
    active_decision: activeDecision,
    session_status: sessionStatus,
  };
  const view = normalizeOrchestration(orchestrationRaw, isEn);
  const liveAwaiting = view?.awaitingUser;
  const incompleteDecision = activeDecision?.status === 'pending'
    && !isActiveDecisionComplete(activeDecision);
  const backendIncomplete = Boolean(incompleteActiveDecision);
  const hasFailedStep = Boolean(
    (workflowPlan?.steps || []).some((step) => {
      const status = step?.status || step?.Status;
      return status === 'failed';
    }),
  );
  const recoveryRequired = !reconciling
    && !liveAwaiting
    && (incompleteDecision
      || backendIncomplete
      || sessionStatus === 'awaiting_answers'
      || hasFailedStep
      || view?.errorKind === 'awaiting_user');

  const liveStamps = Array.isArray(worklogStamps)
    ? worklogStamps.map(stampPayload).filter(Boolean)
    : [];

  useEffect(() => {
    setSubmitting(false);
  }, [
    activeDecision?.decisionKey,
    activeDecision?.status,
    liveAwaiting?.decisionKey,
  ]);

  const handleResolve = async (sendOptions) => {
    if (!onResolve || submitting) return;
    setSubmitting(true);
    try {
      await onResolve(sendOptions);
    } catch {
      setSubmitting(false);
    }
  };

  const activityLabel = controllerActivity
    ? (isEn ? `Latest step: ${controllerActivity}` : `ขั้นตอนล่าสุด: ${controllerActivity}`)
    : null;

  if (!view?.workflow?.steps?.length && !liveAwaiting && !view?.readyForAnalysis
    && !currentBlocker && !recoveryRequired && !noProgress && !continuationAvailable
    && liveStamps.length === 0) {
    return null;
  }

  return (
    <div className="not-prose space-y-2" data-testid="current-workflow-panel">
      {activityLabel && disabled && (
        <p className="text-xs text-slate-600 dark:text-slate-300" aria-live="polite">
          {isEn ? 'Still working — ' : 'ยังทำงานอยู่ — '}
          {activityLabel}
        </p>
      )}
      {(view?.workflow || view?.source) && (
        <WorkflowProgress
          workflow={view.workflow}
          source={view.source}
          isEn={isEn}
        />
      )}

      {liveStamps.length === 1 && (
        <WorklogStampCard stamp={liveStamps[0]} isEn={isEn} />
      )}
      {liveStamps.length > 1 && (
        <WorklogStampStack stamps={liveStamps} isEn={isEn} />
      )}

      {liveAwaiting && activeDecision?.status === 'pending' && (
        <WorkflowQuestionCard
          awaitingUser={liveAwaiting}
          isEn={isEn}
          animateQuestion
          disabled={disabled || submitting}
          decisionStatus={submitting ? 'submitting' : 'pending'}
          onResolve={handleResolve}
        />
      )}

      {recoveryRequired && !liveAwaiting && (
        <div
          className="rounded-2xl border border-indigo-200/80 bg-indigo-50/50 px-4 py-3.5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-slate-700/80 dark:bg-[#161922] dark:shadow-[0_12px_28px_rgba(0,0,0,0.18)]"
          data-testid="incomplete-active-decision-recovery"
          data-incomplete-reason={incompleteActiveDecision || undefined}
        >
          <p className="text-sm font-semibold tracking-[-0.01em] text-slate-900 dark:text-slate-100">
            {isEn ? 'Ready to continue setup' : 'พร้อมดำเนินการตั้งค่าต่อ'}
          </p>
          <p className="mt-1 text-xs leading-5 text-slate-600 dark:text-slate-300">
            {backendIncomplete || incompleteDecision
              ? incompleteDecisionMessage(incompleteActiveDecision || 'missing_question', isEn)
              : hasFailedStep
                ? (isEn
                  ? 'A setup step failed. Continue to retry the next required step.'
                  : 'มีขั้นตอนที่ล้มเหลว ดำเนินการต่อเพื่อลองรันขั้นตอนที่จำเป็นอีกครั้ง')
                : (isEn
                  ? 'The previous answer was recorded. Continue so the controller can select the next required question.'
                  : 'บันทึกคำตอบก่อนหน้าแล้ว ดำเนินการต่อเพื่อให้ Controller เลือกคำถามที่จำเป็นข้อถัดไป')}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {onContinue && (
              <button
                type="button"
                disabled={disabled}
                onClick={() => onContinue()}
                className="rounded-lg border border-indigo-600 bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-indigo-700 disabled:border-slate-700 disabled:bg-slate-800 disabled:text-slate-500 disabled:shadow-none dark:border-indigo-500 dark:bg-indigo-500 dark:text-white dark:hover:bg-indigo-400"
              >
                {isEn ? 'Continue setup' : 'ดำเนินการต่อ'}
              </button>
            )}
            {onReconcile && (
            <button
              type="button"
              disabled={reconciling}
              onClick={() => onReconcile()}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition-colors hover:border-slate-400 hover:bg-slate-50 disabled:border-slate-700 disabled:bg-slate-800 disabled:text-slate-500 dark:border-slate-600 dark:bg-slate-800/80 dark:text-slate-200 dark:hover:border-slate-500 dark:hover:bg-slate-800"
            >
              {isEn ? 'Reload state' : 'ลองโหลดสถานะใหม่'}
            </button>
            )}
          </div>
        </div>
      )}

      {currentBlocker && (
        <WorkflowErrorCard
          orchestration={currentBlocker.orchestration}
          isEn={isEn}
          disabled={disabled || submitting}
          onRetry={onRetry}
        />
      )}

      {view?.readyForAnalysis && (
        <ReadyForAnalysisCard
          ready
          assurance={view.assurance}
          isEn={isEn}
        />
      )}

      {reconcileError && !reconciling && (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {isEn ? 'Syncing setup state…' : 'กำลังเชื่อมต่อสถานะใหม่…'}
        </p>
      )}

      {noProgress && (
        <div className="rounded-xl border border-slate-200 bg-slate-50/90 px-4 py-3 text-sm dark:border-slate-700 dark:bg-slate-900/40">
          <p className="font-medium text-slate-800 dark:text-slate-100">
            {isEn ? 'Workflow has not progressed' : 'Workflow ยังไม่มีความคืบหน้า'}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {onContinue && continuationAvailable && (
              <button
                type="button"
                disabled={disabled}
                onClick={() => onContinue()}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
              >
                {isEn ? 'Continue' : 'ดำเนินการต่อ'}
              </button>
            )}
            {onReconcile && (
              <button
                type="button"
                disabled={reconciling}
                onClick={() => onReconcile()}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
              >
                {isEn ? 'Reload state' : 'โหลดสถานะใหม่'}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
