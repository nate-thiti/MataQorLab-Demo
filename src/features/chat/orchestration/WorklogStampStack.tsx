// @ts-nocheck
import WorklogStampCard from './WorklogStampCard';

/**
 * Collapse consecutive backend worklog stamps into one audit stack.
 * The complete immutable facts remain available inside the native details view.
 */
export default function WorklogStampStack({ stamps, exchanges = [], isEn = false }) {
  const items = Array.isArray(stamps) ? stamps.filter(Boolean) : [];
  const answers = Array.isArray(exchanges) ? exchanges.filter(Boolean) : [];
  if (items.length === 0 && answers.length === 0) return null;
  if (items.length === 1 && answers.length === 0) {
    return <WorklogStampCard stamp={items[0]} isEn={isEn} />;
  }

  const summaries = items
    .map((stamp) => stamp.summary || stamp.title)
    .filter(Boolean)
    .slice(0, 2);

  return (
    <details
      className="group not-prose"
      data-testid="worklog-stamp-stack"
    >
      <summary className="relative z-10 mb-3 cursor-pointer list-none rounded-xl border border-emerald-200/90 bg-emerald-50 px-3.5 py-3 shadow-sm transition-colors marker:content-none hover:bg-emerald-100/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50 dark:border-emerald-900/70 dark:bg-emerald-950/60 dark:hover:bg-emerald-950 [&::-webkit-details-marker]:hidden">
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-2 -bottom-1.5 -z-10 h-full rounded-xl border border-emerald-200/70 bg-emerald-50/80 dark:border-emerald-900/50 dark:bg-emerald-950/40"
        />
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-4 -bottom-3 -z-20 h-full rounded-xl border border-emerald-200/50 bg-emerald-50/60 dark:border-emerald-900/40 dark:bg-emerald-950/30"
        />

        <span className="flex items-start gap-2.5">
          <span className="mt-0.5 text-sm font-semibold text-emerald-700 dark:text-emerald-300" aria-hidden>
            ✓
          </span>
          <span className="min-w-0 flex-1">
            <span className="flex items-center justify-between gap-3">
              <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                {isEn ? 'Data setup questions & worklog' : 'คำถาม Mapping และประวัติการทำงาน'}
              </span>
              <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-800 dark:bg-emerald-900/70 dark:text-emerald-200">
                {items.length + answers.length} {isEn ? 'records' : 'บันทึก'}
              </span>
            </span>
            {summaries.length > 0 && (
              <span className="mt-1 block truncate text-xs text-slate-600 dark:text-slate-300">
                {summaries.join(' · ')}
              </span>
            )}
            <span className="mt-1.5 flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400">
              <span>{isEn ? 'Open to inspect every recorded detail' : 'เปิดดูรายละเอียดที่บันทึกไว้ทั้งหมด'}</span>
              <span className="ml-2 transition-transform duration-200 group-open:rotate-180" aria-hidden>
                ▾
              </span>
            </span>
          </span>
        </span>
      </summary>

      <div className="space-y-2 pt-1" data-testid="worklog-stamp-stack-details">
        {answers.length > 0 && (
          <section className="rounded-xl border border-slate-200 bg-white/80 p-3 dark:border-slate-700 dark:bg-slate-900/70">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {isEn ? 'Questions and answers' : 'คำถามและคำตอบ'}
            </h4>
            <ol className="mt-2 space-y-2.5">
              {answers.map((exchange, index) => (
                <li key={`${exchange.decisionKey || 'answer'}-${index}`} className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 text-xs">
                  <span className="font-semibold text-emerald-700 dark:text-emerald-300">Q{index + 1}</span>
                  <span className="min-w-0">
                    <span className="block text-slate-700 dark:text-slate-200">{exchange.question}</span>
                    <span className="mt-1 block rounded-lg bg-slate-100 px-2.5 py-1.5 font-medium text-slate-800 dark:bg-slate-800 dark:text-slate-100">
                      {isEn ? 'Answer' : 'คำตอบ'}: {exchange.answer || (isEn ? 'Recorded' : 'บันทึกแล้ว')}
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          </section>
        )}

        {items.map((stamp, index) => (
          <WorklogStampCard
            key={stamp.stamp_id || `${stamp.stamp_type}-${stamp.title}-${index}`}
            stamp={stamp}
            isEn={isEn}
          />
        ))}
      </div>
    </details>
  );
}
