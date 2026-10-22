// @ts-nocheck
import { ChevronDown } from '@/components/icons';
import { workflowStepLabel } from './labels.js';

/**
 * Read-only historical question — no interactive controls.
 */
export default function ResolvedQuestionSummary({
  awaitingUser,
  answerLabel = null,
  isEn = false,
  resolved = true,
}) {
  if (!awaitingUser?.question) return null;
  const title = awaitingUser.stepType
    ? workflowStepLabel(awaitingUser.stepType, isEn)
    : (isEn ? 'Question' : 'คำถาม');

  return (
    <details
      className="group/answer-history not-prose mt-2 rounded-lg border border-transparent text-stone-500 open:border-stone-200/80 open:bg-stone-50/65 dark:text-stone-400 dark:open:border-stone-800 dark:open:bg-stone-900/40"
      data-testid="resolved-answer-history"
    >
      <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors hover:bg-stone-100 hover:text-stone-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500 dark:hover:bg-stone-800 dark:hover:text-stone-200 [&::-webkit-details-marker]:hidden">
        <ChevronDown
          size={14}
          strokeWidth={1.8}
          className="shrink-0 transition-transform group-open/answer-history:rotate-180"
        />
        <span>{isEn ? 'Answer history' : 'ประวัติคำตอบ'}</span>
      </summary>
      <section className="px-3.5 pb-3 pt-1" aria-label={title}>
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-stone-500 dark:text-stone-400">
          {title}
        </p>
        <p className="mt-1.5 whitespace-pre-wrap text-sm leading-relaxed text-stone-700 dark:text-stone-200">
          {awaitingUser.question}
        </p>
        {answerLabel ? (
          <p className="mt-2 flex items-center gap-2 text-sm text-stone-600 dark:text-stone-300">
            {isEn ? 'Answer: ' : 'คำตอบ: '}
            <span className="rounded-lg bg-white px-2 py-1 font-medium text-stone-800 ring-1 ring-stone-200 dark:bg-stone-800 dark:text-stone-100 dark:ring-stone-700">{answerLabel}</span>
          </p>
        ) : null}
        {resolved && (
          <p className="mt-2 text-[11px] font-medium text-emerald-700 dark:text-emerald-300">
            {isEn ? '✓ Saved' : '✓ บันทึกแล้ว'}
          </p>
        )}
      </section>
    </details>
  );
}
