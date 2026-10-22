// @ts-nocheck

/**
 * Compact audit-like worklog stamp. Facts must come from backend stamps only.
 */
export default function WorklogStampCard({ stamp, isEn = false, className = '' }) {
  if (!stamp) return null;
  const title = stamp.title || stamp.stamp_type || (isEn ? 'Update' : 'อัปเดต');
  const facts = Array.isArray(stamp.facts) ? stamp.facts : [];
  const summary = stamp.summary || null;
  const status = stamp.status || 'completed';
  const glyph = status === 'failed' ? '!' : '✓';

  return (
    <section
      className={`not-prose rounded-xl border border-emerald-200/80 bg-emerald-50/50 px-3.5 py-2.5 dark:border-emerald-900/60 dark:bg-emerald-950/30 ${className}`}
      aria-label={isEn ? 'Worklog stamp' : 'บันทึกการทำงาน'}
      data-stamp-id={stamp.stamp_id || undefined}
      data-stamp-type={stamp.stamp_type || undefined}
    >
      <header className="flex items-start gap-2">
        <span className="mt-0.5 text-sm font-semibold text-emerald-700 dark:text-emerald-300" aria-hidden>
          {glyph}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
            {title}
          </p>
          {summary && (
            <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-300">
              {summary}
            </p>
          )}
        </div>
      </header>
      {facts.length > 0 && (
        <dl className="mt-2 grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 text-xs">
          {facts.map((fact, index) => (
            <div key={`${fact.label}-${index}`} className="contents">
              <dt className="truncate text-slate-500 dark:text-slate-400">{fact.label}</dt>
              <dd className="text-right font-medium text-slate-800 dark:text-slate-100">
                {fact.value}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {stamp.source && (
        <p className="mt-2 text-[11px] text-slate-400 dark:text-slate-500">
          {stamp.source === 'user_confirmed'
            ? (isEn ? 'Confirmed by user' : 'ยืนยันโดยผู้ใช้')
            : stamp.source}
        </p>
      )}
    </section>
  );
}
