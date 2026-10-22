// @ts-nocheck
import { useState } from 'react';
import { workflowStepLabel } from './labels.js';
import { buildRetrySendOptions } from './normalize.js';

export default function WorkflowErrorCard({
  orchestration,
  isEn = false,
  disabled = false,
  onRetry,
}) {
  const [pending, setPending] = useState(false);
  if (!orchestration) return null;

  const toolResult = orchestration.toolResult;
  const failedStep = orchestration.workflow?.steps?.find((s) => s.status === 'failed');
  const kind = orchestration.errorKind;
  const isToolFailure = kind === 'tool_failure' || toolResult?.status === 'failed' || failedStep;
  const isOrchestratorFailure = kind === 'orchestrator_failure';

  if (!isToolFailure && !isOrchestratorFailure) return null;

  const stepType = toolResult?.stepType || failedStep?.stepType || null;
  const retryable = Boolean(failedStep?.retryable || toolResult?.metadata?.retryable);

  const title = isOrchestratorFailure
    ? (isEn
      ? 'Could not generate the next recommendation right now'
      : 'ไม่สามารถสร้างคำแนะนำสำหรับขั้นตอนถัดไปได้ในขณะนี้')
    : (isEn
      ? `${workflowStepLabel(stepType, true) || 'Step'} did not complete`
      : `${workflowStepLabel(stepType, false) || 'ขั้นตอน'}ไม่สำเร็จ`);

  const body = isOrchestratorFailure
    ? (isEn
      ? 'Workflow state was not changed. You can try again shortly.'
      : 'สถานะ Workflow ไม่ได้รับผลกระทบ คุณสามารถลองอีกครั้งได้')
    : (isEn
      ? 'Earlier progress is preserved. You can retry safely.'
      : 'ข้อมูลก่อนหน้านี้ยังถูกเก็บไว้ สามารถลองใหม่ได้');

  const handleRetry = async () => {
    if (!onRetry || pending || disabled || !stepType) return;
    setPending(true);
    try {
      await onRetry(buildRetrySendOptions(stepType, isEn));
    } finally {
      /* parent owns generating lock */
    }
  };

  return (
    <section
      className="not-prose mt-3 rounded-xl border border-red-200 bg-red-50/80 px-4 py-3 dark:border-red-900/50 dark:bg-red-950/25"
      role="alert"
    >
      <p className="text-sm font-semibold text-red-800 dark:text-red-200">{title}</p>
      <p className="mt-1 text-xs text-red-700/90 dark:text-red-300/80">{body}</p>
      {isToolFailure && retryable && onRetry && (
        <button
          type="button"
          disabled={disabled || pending}
          onClick={handleRetry}
          className="mt-3 inline-flex min-h-10 items-center rounded-lg border border-red-300 bg-white px-3 py-1.5 text-xs font-semibold text-red-800 hover:bg-red-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-800 dark:bg-red-950/40 dark:text-red-100"
        >
          {isEn ? 'Retry' : 'ลองใหม่'}
        </button>
      )}
    </section>
  );
}
