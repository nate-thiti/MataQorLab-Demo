// @ts-nocheck
import { useEffect, useMemo, useState } from 'react';
import {
  BadgeCheck,
  Calculator,
  Database,
  GitBranch,
  ShieldCheck,
  ThumbsUp,
  TriangleAlert,
  X,
} from '@/components/icons';
import { supabase } from '../../utils/supabaseClient.js';

const formatValue = (value, unit) => {
  if (typeof value !== 'number') return String(value ?? '—');
  const rendered = new Intl.NumberFormat(undefined, { maximumFractionDigits: 4 }).format(value);
  if (unit === '%') return `${rendered}%`;
  if (!unit || unit === 'native') return rendered;
  return `${rendered} ${unit}`;
};

const AnalysisAuditPanel = ({ audit, message, userId, isEn, onClose }) => {
  const [feedback, setFeedback] = useState({});
  const findings = Array.isArray(audit?.findings) ? audit.findings : [];
  const grain = audit?.grain_intelligence || {};
  const verificationLayers = audit?.verification_layers || {};
  const dataContract = audit?.data_contract || {};
  const assurance = audit?.decision_assurance || {};
  const confidence = assurance?.confidence_matrix || {};
  const claimGraph = assurance?.claim_graph || {};
  const evidenceRequests = Array.isArray(assurance?.evidence_requests) ? assurance.evidence_requests : [];
  const timeline = assurance?.event_timeline || {};
  const causalEligibility = assurance?.causal_eligibility || {};
  const causalResults = assurance?.causal_results?.results || {};
  const eligibleCount = useMemo(
    () => Object.values(audit?.eligibility || {}).filter((item) => item?.eligible).length,
    [audit],
  );

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') onClose?.();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const submitFindingFeedback = async (finding, verdict) => {
    if (!userId || !finding?.id || feedback[finding.id]) return;
    setFeedback((prev) => ({ ...prev, [finding.id]: verdict }));
    const { error } = await supabase.from('chat_quality_events').insert({
      user_id: userId,
      conversation_id: message?.conversation_id || null,
      message_id: message?.id || null,
      event_type: 'finding_feedback',
      payload: {
        audit_id: audit.audit_id,
        finding_id: finding.id,
        metric: finding.metric,
        verdict,
      },
    });
    if (error) {
      console.warn('Could not save finding feedback:', error.message);
      setFeedback((prev) => {
        const next = { ...prev };
        delete next[finding.id];
        return next;
      });
    }
  };

  return (
    <div
      className="fixed inset-0 z-[1000] flex justify-end bg-slate-950/45 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={isEn ? 'Analysis audit' : 'ตรวจสอบการวิเคราะห์'}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose?.();
      }}
    >
      <section
        className="h-full w-full max-w-3xl overflow-y-auto bg-white shadow-2xl dark:bg-slate-950"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="sticky top-0 z-10 flex items-start justify-between border-b border-slate-200 bg-white/95 px-5 py-4 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
              <ShieldCheck size={18} className="text-emerald-600" />
              {isEn ? 'Analysis audit' : 'ตรวจสอบการวิเคราะห์'}
            </div>
            <p className="mt-1 text-xs text-slate-500">
              {audit?.audit_id} · {audit?.compute_depth} · {findings.length} {isEn ? 'findings' : 'ข้อค้นพบ'}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={isEn ? 'Close analysis audit' : 'ปิดหน้าตรวจสอบการวิเคราะห์'}
            title={isEn ? 'Close (Esc)' : 'ปิด (Esc)'}
            className="shrink-0 rounded-lg p-2 text-slate-500 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-cyan-500 dark:hover:bg-slate-800"
          >
            <X size={18} />
          </button>
        </header>

        <div className="space-y-5 p-5">
          <div>
            <h2 className="mb-2 text-sm font-semibold text-slate-900 dark:text-white">
              {isEn ? 'Assurance status' : 'สถานะการรับรอง'}
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {[
                ['computation', isEn ? 'Computation' : 'การคำนวณ'],
                ['data_readiness', isEn ? 'Data readiness' : 'ความพร้อมของข้อมูล'],
                ['business_context', isEn ? 'Business context' : 'บริบทธุรกิจ'],
                ['evidence_assurance', isEn ? 'Evidence' : 'หลักฐาน'],
                ['causal_assurance', isEn ? 'Causal design' : 'แบบเชิงเหตุผล'],
              ].map(([key, label]) => {
                const layer = verificationLayers[key] || {};
                const verified = layer.status === 'verified';
                return (
                  <div
                    key={key}
                    className={`rounded-xl border p-3 ${
                      verified
                        ? 'border-emerald-200 bg-emerald-50/60 dark:border-emerald-900/60 dark:bg-emerald-950/20'
                        : 'border-amber-200 bg-amber-50/60 dark:border-amber-900/60 dark:bg-amber-950/20'
                    }`}
                  >
                    <div className={`flex items-center gap-2 text-xs font-semibold ${
                      verified ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'
                    }`}>
                      {verified ? <BadgeCheck size={15} /> : <TriangleAlert size={15} />}
                      {label}
                    </div>
                    <div className="mt-1 text-[11px] text-slate-600 dark:text-slate-400">
                      {verified
                        ? (isEn ? 'Verified for this scope' : 'ผ่านการตรวจในขอบเขตนี้')
                        : (isEn ? 'Needs review' : 'ต้องตรวจเพิ่ม')}
                    </div>
                    {!verified && Array.isArray(layer.missing) && layer.missing.length > 0 && (
                      <div className="mt-1 break-words text-[10px] text-slate-500">
                        {layer.missing.join(' · ')}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
              {isEn
                ? 'Computed verification confirms consistency with the supplied data and formulas; it does not independently establish business truth.'
                : 'การตรวจการคำนวณยืนยันความสอดคล้องกับข้อมูลและสูตรที่ได้รับ แต่ไม่ได้ยืนยันความจริงทางธุรกิจโดยอิสระ'}
            </p>
          </div>

          {confidence?.version && (
            <section className="rounded-xl border border-cyan-200 bg-cyan-50/40 p-4 dark:border-cyan-900/60 dark:bg-cyan-950/10">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-semibold text-slate-900 dark:text-white">
                  {isEn ? 'Evidence confidence matrix' : 'เมทริกซ์ความมั่นใจในหลักฐาน'}
                </h2>
                <span className="rounded-full bg-cyan-100 px-3 py-1 text-xs font-semibold text-cyan-800 dark:bg-cyan-950 dark:text-cyan-200">
                  {Math.round(Number(confidence.overall_score || 0) * 100)}% · {confidence.label}
                </span>
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                {Object.entries(confidence.dimensions || {}).map(([key, item]) => (
                  <div key={key} className="rounded-lg border border-white/80 bg-white/70 p-2.5 dark:border-slate-800 dark:bg-slate-950/50">
                    <div className="flex justify-between gap-2 text-[11px]">
                      <span className="font-medium capitalize text-slate-700 dark:text-slate-300">{key.replaceAll('_', ' ')}</span>
                      <span className="font-mono">{Math.round(Number(item?.score || 0) * 100)}%</span>
                    </div>
                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
                      <div className="h-full rounded-full bg-cyan-500" style={{ width: `${Math.round(Number(item?.score || 0) * 100)}%` }} />
                    </div>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-[10px] text-slate-500">{confidence.score_meaning}</p>
            </section>
          )}

          {claimGraph?.version && (
            <details className="rounded-xl border border-slate-200 p-4 text-xs dark:border-slate-800">
              <summary className="cursor-pointer font-semibold text-slate-800 dark:text-slate-200">
                {isEn ? 'Claim & evidence graph' : 'กราฟข้ออ้างและหลักฐาน'} · {claimGraph.claim_count || 0} claims · {claimGraph.evidence_count || 0} evidence
              </summary>
              <div className="mt-3 space-y-2">
                {(claimGraph.nodes || []).filter((node) => node.kind === 'claim').slice(0, 20).map((claim) => {
                  const support = (claimGraph.edges || []).filter((edge) => edge.to === claim.id);
                  return (
                    <div key={claim.id} className="rounded-lg bg-slate-50 p-3 dark:bg-slate-900/70">
                      <div className="font-medium text-slate-800 dark:text-slate-200">{claim.label}</div>
                      <div className="mt-1 text-slate-500">{claim.statement || '—'}</div>
                      <div className="mt-1 text-[10px] text-emerald-700 dark:text-emerald-300">
                        {support.length} {isEn ? 'linked evidence/context items' : 'รายการหลักฐาน/บริบทที่เชื่อมโยง'}
                      </div>
                    </div>
                  );
                })}
              </div>
            </details>
          )}

          {evidenceRequests.length > 0 && (
            <section className="rounded-xl border border-amber-200 bg-amber-50/50 p-4 dark:border-amber-900/60 dark:bg-amber-950/20">
              <h2 className="text-sm font-semibold text-amber-900 dark:text-amber-200">
                {isEn ? 'Evidence needed next' : 'หลักฐานที่ควรเพิ่ม'}
              </h2>
              <ul className="mt-2 space-y-2">
                {evidenceRequests.slice(0, 12).map((request) => (
                  <li key={request.id} className="rounded-lg bg-white/70 p-2.5 text-xs dark:bg-slate-950/40">
                    <span className="mr-2 rounded-full border border-amber-300 px-2 py-0.5 text-[9px] font-semibold uppercase">{request.priority}</span>
                    <span className="font-medium">{request.field}</span>
                    <p className="mt-1 text-slate-600 dark:text-slate-400">{request.reason}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {(timeline.events || []).length > 0 && (
            <details className="rounded-xl border border-slate-200 p-4 text-xs dark:border-slate-800">
              <summary className="cursor-pointer font-semibold text-slate-800 dark:text-slate-200">
                {isEn ? 'Internal & external event timeline' : 'ไทม์ไลน์เหตุการณ์ภายในและภายนอก'} · {(timeline.events || []).length}
              </summary>
              <ol className="mt-3 border-l border-slate-300 pl-4 dark:border-slate-700">
                {(timeline.events || []).slice(0, 30).map((event) => (
                  <li key={event.id} className="mb-3">
                    <div className="text-[10px] uppercase text-slate-500">{event.date || 'undated'} · {event.kind}</div>
                    <div className="font-medium text-slate-700 dark:text-slate-300">{event.label}</div>
                  </li>
                ))}
              </ol>
              <p className="text-[10px] text-amber-700 dark:text-amber-300">{timeline.warning}</p>
            </details>
          )}

          {causalEligibility?.version && (
            <section className="rounded-xl border border-violet-200 p-4 dark:border-violet-900/60">
              <h2 className="text-sm font-semibold text-slate-900 dark:text-white">
                {isEn ? 'Causal eligibility gate' : 'ด่านตรวจความพร้อมเชิงเหตุผล'}
              </h2>
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                {Object.entries(causalEligibility.methods || {}).map(([key, method]) => (
                  <div key={key} className={`rounded-lg border p-3 ${method?.status === 'eligible' ? 'border-emerald-300 bg-emerald-50 dark:bg-emerald-950/20' : 'border-slate-200 dark:border-slate-800'}`}>
                    <div className="text-xs font-semibold capitalize">{key.replaceAll('_', ' ')}</div>
                    <div className="mt-1 text-[10px] uppercase text-slate-500">{method?.status}</div>
                    {(method?.missing || []).length > 0 && <div className="mt-2 text-[10px] text-amber-700 dark:text-amber-300">{method.missing.join(' · ')}</div>}
                    {causalResults[key] && (
                      <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded bg-slate-950 p-2 text-[9px] text-slate-100">
                        {JSON.stringify(causalResults[key], null, 2)}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
              <p className="mt-2 text-[10px] text-slate-500">{causalEligibility.policy}</p>
            </section>
          )}

          <details className="rounded-xl border border-slate-200 p-4 text-xs dark:border-slate-800">
            <summary className="cursor-pointer font-semibold text-slate-800 dark:text-slate-200">
              {isEn ? 'Data contract snapshot' : 'สำเนาข้อตกลงข้อมูล'}
            </summary>
            <dl className="mt-3 grid gap-2 sm:grid-cols-2 text-slate-600 dark:text-slate-400">
              {[
                ['Data owner', dataContract.data_owner],
                ['Purpose', dataContract.business_purpose],
                ['Row grain', dataContract.row_grain],
                ['Period status', dataContract.period_status],
                ['Metric definition', dataContract.metric_definition],
                ['Cancellation / returns', dataContract.cancellation_policy],
                ['Known context', dataContract.context_notes],
                ['Reviewed at', dataContract.reviewed_at],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="font-medium text-slate-700 dark:text-slate-300">{label}</dt>
                  <dd className="whitespace-pre-wrap break-words">{value || '—'}</dd>
                </div>
              ))}
            </dl>
          </details>

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
              <Database size={16} className="mb-2 text-indigo-500" />
              <div className="text-lg font-semibold">{grain.row_count?.toLocaleString?.() || '—'}</div>
              <div className="text-xs text-slate-500">{isEn ? 'Rows analysed' : 'แถวที่วิเคราะห์'}</div>
            </div>
            <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
              <GitBranch size={16} className="mb-2 text-violet-500" />
              <div className="text-lg font-semibold">{grain.grain || '—'}</div>
              <div className="text-xs text-slate-500">{isEn ? 'Detected grain' : 'ระดับข้อมูลที่ตรวจพบ'}</div>
            </div>
            <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
              <BadgeCheck size={16} className="mb-2 text-emerald-500" />
              <div className="text-lg font-semibold">{eligibleCount}</div>
              <div className="text-xs text-slate-500">{isEn ? 'Eligible advanced checks' : 'การตรวจขั้นสูงที่พร้อมใช้'}</div>
            </div>
          </div>

          {Array.isArray(grain.join_risks) && grain.join_risks.length > 0 && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
              <div className="mb-2 flex items-center gap-2 font-medium"><TriangleAlert size={16} /> {isEn ? 'Grain / join risks' : 'ความเสี่ยง grain / join'}</div>
              <ul className="list-disc space-y-1 pl-5">{grain.join_risks.map((risk) => <li key={risk}>{risk}</li>)}</ul>
            </div>
          )}

          <div className="space-y-3">
            {findings.map((finding) => (
              <article key={finding.id} className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{finding.type}</div>
                    <h3 className="mt-1 font-semibold text-slate-900 dark:text-white">{finding.metric}</h3>
                  </div>
                  <div className="rounded-lg bg-slate-100 px-3 py-1.5 font-mono text-sm dark:bg-slate-900">
                    {formatValue(finding.value, finding.unit)}
                  </div>
                </div>
                <p className="mt-3 text-sm text-slate-700 dark:text-slate-300">{finding.evidence}</p>
                {finding.interpretation && <p className="mt-2 text-xs text-slate-500">{finding.interpretation}</p>}

                <details className="mt-3 rounded-lg bg-slate-50 p-3 text-xs dark:bg-slate-900/70">
                  <summary className="flex cursor-pointer items-center gap-2 font-medium text-slate-700 dark:text-slate-300">
                    <Calculator size={14} /> {isEn ? 'Formula, SQL and provenance' : 'สูตร SQL และที่มาของข้อมูล'}
                  </summary>
                  <dl className="mt-3 grid gap-2 text-slate-600 dark:text-slate-400">
                    <div><dt className="font-medium">{isEn ? 'Engine' : 'กลไกคำนวณ'}</dt><dd>{finding.provenance?.engine || '—'}</dd></div>
                    <div><dt className="font-medium">{isEn ? 'Columns' : 'คอลัมน์'}</dt><dd>{(finding.provenance?.source_columns || []).join(', ') || '—'}</dd></div>
                    <div><dt className="font-medium">{isEn ? 'Formula' : 'สูตร'}</dt><dd className="break-all font-mono">{finding.audit?.formula || '—'}</dd></div>
                    {finding.audit?.sql && <div><dt className="font-medium">SQL</dt><dd className="mt-1 overflow-x-auto rounded bg-slate-950 p-2 font-mono text-slate-100">{finding.audit.sql}</dd></div>}
                    <div><dt className="font-medium">{isEn ? 'Hashes' : 'ค่าแฮช'}</dt><dd className="font-mono">query {finding.provenance?.query_hash || '—'} · result {finding.provenance?.result_hash}</dd></div>
                    <div><dt className="font-medium">{isEn ? 'Rows / period' : 'แถว / ช่วงเวลา'}</dt><dd>{finding.provenance?.row_count?.toLocaleString?.() || '—'} · {finding.provenance?.period || (isEn ? 'all' : 'ทั้งหมด')}</dd></div>
                  </dl>
                </details>

                <div className="mt-3 flex flex-wrap gap-2">
                  {[
                    ['correct', isEn ? 'Correct' : 'ถูกต้อง'],
                    ['useful', isEn ? 'Useful' : 'มีประโยชน์'],
                    ['needs_review', isEn ? 'Needs review' : 'ควรตรวจเพิ่ม'],
                  ].map(([verdict, label]) => (
                    <button
                      key={verdict}
                      type="button"
                      onClick={() => submitFindingFeedback(finding, verdict)}
                      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs ${
                        feedback[finding.id] === verdict
                          ? 'border-emerald-400 bg-emerald-50 text-emerald-700 dark:bg-emerald-950'
                          : 'border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-900'
                      }`}
                    >
                      <ThumbsUp size={12} /> {label}
                    </button>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
};

export default AnalysisAuditPanel;
