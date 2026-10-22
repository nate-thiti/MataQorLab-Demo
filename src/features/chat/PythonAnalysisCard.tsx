import { useEffect, useState } from 'react';
import { AlertTriangle, Check, Loader2, X } from '@/components/icons';
import { authFetch } from '../../utils/authFetch.js';
import { getPublicApiUrl } from '../../utils/env';

const TERMINAL = new Set(['completed', 'failed', 'cancelled', 'expired']);

export default function PythonAnalysisCard({ proposal, userId, isEn = false }) {
  const [status, setStatus] = useState(String(proposal.status || 'awaiting_confirmation'));
  const [result, setResult] = useState<any>(proposal.result_manifest || null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const jobId = String(proposal.job_id || '');

  useEffect(() => {
    if (!jobId || status !== 'queued' && status !== 'running') return undefined;
    let active = true;
    const poll = async () => {
      try {
        const response = await authFetch(
          `${getPublicApiUrl()}/api/v1/analysis/python/jobs/${encodeURIComponent(jobId)}`,
        );
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || 'Status unavailable');
        if (!active) return;
        setStatus(payload.status);
        setResult(payload.result_manifest || null);
        setError(payload.error_code || '');
      } catch (nextError: any) {
        if (active) setError(nextError.message);
      }
    };
    poll();
    const timer = window.setInterval(poll, 2000);
    return () => { active = false; window.clearInterval(timer); };
  }, [jobId, status]);

  const act = async (action: 'confirm' | 'cancel') => {
    if (!jobId || !userId || busy) return;
    setBusy(true); setError('');
    try {
      const response = await authFetch(
        `${getPublicApiUrl()}/api/v1/analysis/python/jobs/${encodeURIComponent(jobId)}/${action}`,
        { body: action === 'confirm'
          ? { user_id: userId, approval_id: proposal.approval_id }
          : { user_id: userId } } as any,
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Action failed');
      setStatus(payload.status);
    } catch (nextError: any) {
      setError(nextError.message);
    } finally { setBusy(false); }
  };

  const limits = proposal.limits || {};
  const packages = proposal.packages || {};
  return (
    <section className="my-5 overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
      <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <div>
          <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            {isEn ? 'Python analysis preview' : 'พรีวิวการวิเคราะห์ด้วย Python'}
          </div>
          <div className="mt-0.5 text-[11px] text-slate-500">
            {isEn ? 'Runs only after confirming this exact code and dataset version.' : 'จะรันเมื่อยืนยันโค้ดและเวอร์ชันข้อมูลชุดนี้เท่านั้น'}
          </div>
        </div>
        <span className="rounded-full bg-amber-50 px-2 py-1 text-[10px] font-semibold text-amber-800 dark:bg-amber-950/30 dark:text-amber-300">{status}</span>
      </div>
      <pre className="max-h-80 overflow-auto bg-slate-950 p-4 text-xs leading-5 text-slate-100"><code>{String(proposal.code || '')}</code></pre>
      <div className="grid gap-3 px-4 py-3 text-xs text-slate-600 dark:text-slate-300 sm:grid-cols-2">
        <div><span className="font-semibold">{isEn ? 'Packages:' : 'แพ็กเกจ:'}</span> {Object.entries(packages).map(([name, version]) => `${name} ${version}`).join(', ') || (isEn ? 'standard library' : 'ไลบรารีมาตรฐาน')}</div>
        <div><span className="font-semibold">{isEn ? 'Limits:' : 'ขีดจำกัด:'}</span> {limits.cpu || 2} CPU · {limits.memory_mb || 2048} MB · {limits.runtime_seconds || 60}s</div>
        <div className="sm:col-span-2"><span className="font-semibold">{isEn ? 'Outputs:' : 'ผลลัพธ์:'}</span> {(proposal.expected_outputs || []).join(', ') || (isEn ? 'structured findings' : 'ข้อค้นพบแบบมีโครงสร้าง')}</div>
      </div>
      {error && <div className="mx-4 mb-3 flex gap-2 rounded-xl bg-red-50 p-3 text-xs text-red-700 dark:bg-red-950/20 dark:text-red-300"><AlertTriangle size={15} />{error}</div>}
      {result && <div className="mx-4 mb-3 rounded-xl bg-emerald-50 p-3 text-xs text-emerald-800 dark:bg-emerald-950/20 dark:text-emerald-300">{isEn ? 'Verified sandbox result is ready.' : 'ผลลัพธ์จาก sandbox พร้อมแล้ว'}</div>}
      {!TERMINAL.has(status) && (
        <div className="flex justify-end gap-2 border-t border-slate-200 px-4 py-3 dark:border-slate-800">
          <button type="button" onClick={() => act('cancel')} disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 disabled:opacity-50 dark:text-slate-300 dark:hover:bg-slate-800"><X size={13} />{isEn ? 'Cancel' : 'ยกเลิก'}</button>
          {status === 'awaiting_confirmation' && <button type="button" onClick={() => act('confirm')} disabled={busy || !proposal.approval_id} className="btn-primary inline-flex items-center gap-1.5 px-3 py-2 text-xs disabled:opacity-50">{busy ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}{isEn ? 'Confirm and run' : 'ยืนยันและรัน'}</button>}
        </div>
      )}
    </section>
  );
}
