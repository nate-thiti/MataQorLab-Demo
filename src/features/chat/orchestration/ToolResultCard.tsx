// @ts-nocheck
import { useState } from 'react';
import { workflowStepLabel } from './labels.js';

function findingLine(item) {
  if (!item || typeof item !== 'object') return null;
  const parts = [];
  if (item.type) parts.push(String(item.type));
  if (item.column) parts.push(String(item.column));
  if (item.count != null) parts.push(String(item.count));
  if (item.status) parts.push(String(item.status));
  return parts.length ? parts.join(' · ') : null;
}

/**
 * Safe structured tool summary — only fields present in backend payload.
 */
export default function ToolResultCard({ toolResult, isEn = false }) {
  const [open, setOpen] = useState(false);
  if (!toolResult) return null;

  const title = toolResult.stepType
    ? workflowStepLabel(toolResult.stepType, isEn)
    : (isEn ? 'Step result' : 'ผลลัพธ์ขั้นตอน');
  const ok = toolResult.status === 'completed' || toolResult.status === 'success';
  const failed = toolResult.status === 'failed';
  const findings = (toolResult.findings || []).map(findingLine).filter(Boolean);
  const warnings = (toolResult.warnings || []).map(findingLine).filter(Boolean);
  const meta = toolResult.metadata || {};
  const metaRows = Object.entries(meta)
    .filter(([, v]) => v != null && v !== '')
    .slice(0, 12);

  return (
    <section
      className={`not-prose mt-3 rounded-xl border px-4 py-3 ${
        failed
          ? 'border-red-200 bg-red-50/70 dark:border-red-900/50 dark:bg-red-950/20'
          : 'border-emerald-200 bg-emerald-50/60 dark:border-emerald-900/50 dark:bg-emerald-950/20'
      }`}
      aria-label={title}
    >
      <div className="flex items-start justify-between gap-3">
        <p className={`text-sm font-semibold ${
          failed
            ? 'text-red-800 dark:text-red-200'
            : 'text-emerald-900 dark:text-emerald-100'
        }`}
        >
          {ok ? '✓ ' : failed ? '! ' : ''}
          {title}
        </p>
      </div>
      {toolResult.summary && (
        <p className="mt-1.5 text-sm text-slate-700 dark:text-slate-200 whitespace-pre-wrap">
          {toolResult.summary}
        </p>
      )}
      {findings.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs text-slate-600 dark:text-slate-300">
          {findings.slice(0, 6).map((line) => (
            <li key={line}>• {line}</li>
          ))}
        </ul>
      )}
      {(warnings.length > 0 || metaRows.length > 0) && (
        <div className="mt-2">
          <button
            type="button"
            className="text-xs font-medium text-slate-600 underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-500 dark:text-slate-300"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
          >
            {open
              ? (isEn ? 'Hide details' : 'ซ่อนรายละเอียด')
              : (isEn ? 'View details' : 'ดูรายละเอียด')}
          </button>
          {open && (
            <div className="mt-2 space-y-1 text-xs text-slate-600 dark:text-slate-300">
              {warnings.map((line) => (
                <p key={`w-${line}`}>{isEn ? 'Warning' : 'คำเตือน'}: {line}</p>
              ))}
              {metaRows.map(([k, v]) => (
                <p key={k}>
                  <span className="font-medium">{k}</span>
                  {': '}
                  {String(v)}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
