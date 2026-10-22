import { useState } from 'react';
import { Check, Loader2 } from '@/components/icons';
import { authFetch } from '../../utils/authFetch.js';
import { getPublicApiUrl } from '../../utils/env';

export default function DaxAnalysisCard({ proposal, userId, isEn = false }) {
  const [busy, setBusy] = useState(false);
  const [published, setPublished] = useState<any>(null);
  const [error, setError] = useState('');
  const isMeasure = proposal.mode === 'measure';

  const publish = async () => {
    if (!userId || busy || !proposal.approved_action_id) return;
    setBusy(true); setError('');
    try {
      const response = await authFetch(`${getPublicApiUrl()}/api/v1/analysis/dax/publish`, {
        body: {
          user_id: userId,
          dataset_key: proposal.dataset_key,
          name: proposal.name,
          label: proposal.label || proposal.name,
          expression: proposal.expression,
          mode: proposal.mode,
          governed_relationships: Boolean(proposal.governed_relationships),
          approved_action_id: proposal.approved_action_id,
        },
      } as any);
      const payload = await response.json();
      if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Publish failed');
      setPublished(payload);
    } catch (nextError: any) {
      setError(nextError.message);
    } finally { setBusy(false); }
  };

  const preview = proposal.preview || {};
  return (
    <section className="my-5 overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
      <div className="flex items-start justify-between gap-3 px-4 py-3">
        <div>
          <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{proposal.name}</div>
          <div className="text-[11px] text-slate-500">{isMeasure ? 'DAX subset measure' : 'DAX subset calculated column'}</div>
        </div>
        <span className="rounded-full bg-violet-50 px-2 py-1 text-[10px] font-semibold text-violet-700 dark:bg-violet-950/30 dark:text-violet-300">{isEn ? 'Preview' : 'ตัวอย่าง'}</span>
      </div>
      <pre className="overflow-auto border-y border-slate-200 bg-slate-950 p-4 text-xs text-slate-100 dark:border-slate-800"><code>{proposal.expression}</code></pre>
      <div className="px-4 py-3 text-xs text-slate-600 dark:text-slate-300">
        {isMeasure ? (
          <span><strong>{isEn ? 'Preview value:' : 'ค่าพรีวิว:'}</strong> {String(preview.value ?? 'BLANK')}</span>
        ) : (
          <span>
            <strong>{isEn ? 'Preview:' : 'ตัวอย่าง:'}</strong>{' '}
            {preview.rows?.length || 0} {isEn ? 'rows' : 'แถว'} ·{' '}
            {preview.null_count || 0} {isEn ? 'null values' : 'ค่าว่าง'} ·{' '}
            {preview.distinct_count ?? '—'} {isEn ? 'distinct values' : 'ค่าที่ไม่ซ้ำ'}
          </span>
        )}
      </div>
      {error && <div className="mx-4 mb-3 rounded-xl bg-red-50 p-3 text-xs text-red-700 dark:bg-red-950/20 dark:text-red-300">{error}</div>}
      {published ? (
        <div className="m-4 flex items-center gap-2 rounded-xl bg-emerald-50 p-3 text-xs font-semibold text-emerald-800 dark:bg-emerald-950/20 dark:text-emerald-300"><Check size={14} />{isMeasure ? (isEn ? 'Measure saved' : 'บันทึก Measure แล้ว') : (isEn ? 'Dataset version published' : 'สร้าง Dataset Version แล้ว')}</div>
      ) : (
        <div className="flex justify-end border-t border-slate-200 px-4 py-3 dark:border-slate-800">
          <button type="button" onClick={publish} disabled={busy || !proposal.approved_action_id} className="btn-primary inline-flex items-center gap-1.5 px-3 py-2 text-xs disabled:opacity-50">{busy ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}{isMeasure ? (isEn ? 'Confirm and save' : 'ยืนยันและบันทึก') : (isEn ? 'Confirm and publish' : 'ยืนยันและสร้างเวอร์ชัน')}</button>
        </div>
      )}
    </section>
  );
}
