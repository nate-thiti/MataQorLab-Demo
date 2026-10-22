// @ts-nocheck
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'next/navigation';
import { Download, Loader2, LockKeyhole } from '@/components/icons';
import AdaptiveBiDashboard from '../components/AdaptiveBiDashboard';
import { getPublicApiUrl } from '../utils/env.js';

const SharedVisualization = () => {
  const params = useParams();
  const token = Array.isArray(params?.token) ? params.token[0] : params?.token;
  const isEn = params?.locale === 'en';
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const timerRef = useRef(null);
  const controllerRef = useRef(null);

  const load = useCallback(async (filters = null) => {
    if (!token) return;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setError('');
    try {
      const response = await fetch(
        `${getPublicApiUrl()}/api/v1/visualizations/shared/${encodeURIComponent(token)}`,
        {
          method: filters ? 'POST' : 'GET',
          headers: filters ? { 'Content-Type': 'application/json' } : undefined,
          body: filters ? JSON.stringify({ filters }) : undefined,
          signal: controller.signal,
        },
      );
      const next = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(next.detail || 'Shared dashboard unavailable');
      setPayload(next);
    } catch (err) {
      if (err?.name !== 'AbortError') setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
    return () => {
      controllerRef.current?.abort();
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, [load]);

  const filter = (filters) => {
    if (timerRef.current) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => load(filters), 300);
  };

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center bg-slate-50 dark:bg-zinc-950"><Loader2 size={28} className="animate-spin text-amber-600" /></div>;
  }

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-6 text-slate-900 dark:bg-zinc-950 dark:text-white md:px-8">
      <div className="mx-auto max-w-[1500px]">
        <header className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between print:hidden">
          <div>
            <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-emerald-700 dark:text-emerald-400"><LockKeyhole size={13} />{isEn ? 'Read-only shared decision packet' : 'Decision packet แบบอ่านอย่างเดียว'}</div>
            <h1 className="mt-2 font-serif text-2xl font-bold">{payload?.report?.title || (isEn ? 'Pinned findings' : 'ข้อค้นพบที่ปักไว้')}</h1>
            {payload?.report?.executive_summary && <p className="mt-1 max-w-3xl text-sm text-slate-500 dark:text-slate-400">{payload.report.executive_summary}</p>}
          </div>
          <button type="button" onClick={() => window.print()} className="btn-secondary inline-flex items-center justify-center gap-2 px-4 py-2.5 text-xs"><Download size={14} />{isEn ? 'Print / Save PDF' : 'พิมพ์ / บันทึก PDF'}</button>
        </header>
        {error ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/20 dark:text-red-300">{error}</div>
        ) : payload?.dashboard ? (
          <div className="space-y-5">
            {(payload.decision_brief || payload.report?.decision_packet) && (
              <section className="rounded-2xl border border-violet-200 bg-white p-5 shadow-sm dark:border-violet-900/50 dark:bg-slate-900">
                <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-violet-700 dark:text-violet-400">
                  {isEn ? 'Decision brief' : 'สรุปเพื่อการตัดสินใจ'}
                </div>
                <h2 className="mt-2 font-serif text-xl font-bold">
                  {(payload.decision_brief || payload.report.decision_packet).headline
                    || payload.report?.title}
                </h2>
                <p className="mt-2 text-sm leading-relaxed text-slate-500 dark:text-slate-400">
                  {(payload.decision_brief || payload.report.decision_packet).summary
                    || payload.report?.executive_summary}
                </p>
                <div className="mt-3 flex flex-wrap gap-3 text-[10px] font-semibold text-slate-500">
                  <span>
                    {(payload.decision_brief || payload.report.decision_packet).verified_evidence_count || 0}
                    {' '}
                    {isEn ? 'verified evidence links' : 'หลักฐานที่เชื่อมโยง'}
                  </span>
                  <span>
                    {(payload.decision_brief || payload.report.decision_packet).pin_count || 0}
                    {' '}
                    {isEn ? 'pins' : 'ข้อค้นพบที่ปัก'}
                  </span>
                  <span>
                    {(payload.decision_brief || payload.report.decision_packet).open_actions || 0}
                    {' '}
                    {isEn ? 'open actions' : 'action ที่ยังเปิด'}
                  </span>
                </div>
              </section>
            )}
            <AdaptiveBiDashboard
              dashboard={payload.dashboard}
              isEn={isEn}
              readOnly
              briefMode
              onFiltersChange={filter}
            />
          </div>
        ) : null}
      </div>
    </main>
  );
};

export default SharedVisualization;
