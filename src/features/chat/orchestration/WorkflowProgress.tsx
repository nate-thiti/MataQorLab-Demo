// @ts-nocheck
import { workflowStatusLabel } from './labels.js';
import { compactProgressView } from './normalize.js';

function statusGlyph(status) {
  switch (status) {
    case 'completed':
      return '✓';
    case 'running':
      return '●';
    case 'awaiting_user':
      return '◉';
    case 'failed':
      return '!';
    case 'skipped':
      return '–';
    case 'stale':
      return '↻';
    default:
      return '○';
  }
}

function statusClass(status) {
  switch (status) {
    case 'completed':
      return 'text-emerald-700 dark:text-emerald-300';
    case 'running':
      return 'text-indigo-700 dark:text-indigo-300 font-semibold';
    case 'awaiting_user':
      return 'text-indigo-700 dark:text-indigo-200 font-semibold';
    case 'failed':
      return 'text-red-700 dark:text-red-300 font-semibold';
    case 'stale':
      return 'text-slate-600 dark:text-slate-300';
    case 'skipped':
      return 'text-slate-400 dark:text-slate-500';
    default:
      return 'text-slate-500 dark:text-slate-400';
  }
}

/**
 * Backend-grounded workflow progress. Never infer status from assistant text.
 */
export default function WorkflowProgress({
  workflow,
  source = null,
  isEn = false,
  className = '',
}) {
  if (!workflow?.steps?.length) return null;
  const steps = workflow.steps.filter((s) => s.status !== 'superseded');
  const compact = compactProgressView(steps);
  const sourceName = source?.name || null;
  const metaBits = [];
  if (source?.rowCount != null) {
    metaBits.push(
      isEn
        ? `${Number(source.rowCount).toLocaleString()} rows`
        : `${Number(source.rowCount).toLocaleString()} แถว`,
    );
  }
  if (source?.columnCount != null) {
    metaBits.push(
      isEn
        ? `${source.columnCount} columns`
        : `${source.columnCount} คอลัมน์`,
    );
  }
  if (source?.dateRange) {
    metaBits.push(String(source.dateRange));
  }

  return (
    <section
      className={`not-prose rounded-2xl border border-slate-200/80 bg-white/75 px-4 py-3.5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-slate-700/70 dark:bg-[#17191f] dark:shadow-[0_12px_28px_rgba(0,0,0,0.16)] ${className}`}
      aria-label={isEn ? 'Data setup progress' : 'ความคืบหน้าการเตรียมข้อมูล'}
    >
      {(sourceName || metaBits.length > 0) && (
        <header className="mb-2.5 min-w-0">
          {sourceName && (
            <p className="truncate text-sm font-semibold tracking-[-0.01em] text-slate-800 dark:text-slate-100">
              {sourceName}
            </p>
          )}
          {metaBits.length > 0 && (
            <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
              {metaBits.join(' · ')}
            </p>
          )}
        </header>
      )}

      {/* Mobile compact */}
      <div className="sm:hidden">
        <p className="text-xs font-medium text-slate-600 dark:text-slate-200">
          {compact.completed} / {compact.total}
          {compact.active ? ` · ${compact.active.label}` : ''}
        </p>
        <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
          {compact.active
            ? workflowStatusLabel(compact.active.status, isEn)
            : workflowStatusLabel(workflow.status, isEn)}
        </p>
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-slate-600 dark:text-slate-300">
            {isEn ? 'Show all steps' : 'ดูทุกขั้นตอน'}
          </summary>
          <ol className="mt-2 space-y-1.5">
            {steps.map((step) => (
              <li
                key={step.stepType}
                className={`flex items-start gap-2 text-sm ${statusClass(step.status)}`}
              >
                <span aria-hidden="true" className="w-4 shrink-0 text-center">
                  {statusGlyph(step.status)}
                </span>
                <span>
                  {step.label}
                  <span className="sr-only">
                    {`, ${workflowStatusLabel(step.status, isEn)}`}
                  </span>
                </span>
              </li>
            ))}
          </ol>
        </details>
      </div>

      {/* Desktop / tablet list */}
      <ol className="hidden grid-cols-2 gap-x-4 gap-y-1.5 sm:grid">
        {steps.map((step) => (
          <li
            key={step.stepType}
            className={`flex items-center gap-2 text-sm ${statusClass(step.status)}`}
          >
            <span aria-hidden="true" className="w-4 shrink-0 text-center">
              {statusGlyph(step.status)}
            </span>
            <span>
              {step.label}
              <span className="sr-only">
                {`, ${workflowStatusLabel(step.status, isEn)}`}
              </span>
              {step.status === 'stale' && (
                <span className="ml-1 text-xs opacity-80">
                  ({workflowStatusLabel('stale', isEn)})
                </span>
              )}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
