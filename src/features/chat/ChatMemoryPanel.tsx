// @ts-nocheck
'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Layers3, Save, Trash2, X } from '@/components/icons';
import { supabase } from '../../utils/supabaseClient.js';
import GovernedMemoryManager from './GovernedMemoryManager';

const SECTION_ORDER = ['user', 'conversation', 'project', 'evidence'];

const scopeMeta = (scope, isEn) => {
  const labels = {
    user: {
      title: isEn ? 'Preferences' : 'ค่ากำหนด',
      hint: isEn ? 'Language, currency, and answer style' : 'ภาษา สกุลเงิน และรูปแบบคำตอบ',
    },
    conversation: {
      title: isEn ? 'Working context' : 'บริบทงานปัจจุบัน',
      hint: isEn ? 'Focus and verified notes from this chat' : 'ประเด็นและบันทึกที่ยืนยันแล้วในแชทนี้',
    },
    project: {
      title: isEn ? 'Dataset facts' : 'ข้อเท็จจริงของชุดข้อมูล',
      hint: isEn ? 'Verified metrics tied to a dataset or connection' : 'ตัวชี้วัดที่ยืนยันแล้วผูกกับชุดข้อมูล',
    },
    evidence: {
      title: isEn ? 'Evidence notes' : 'หลักฐานอ้างอิง',
      hint: isEn ? 'Web sources used recently (may become stale)' : 'แหล่งเว็บที่ใช้ล่าสุด (อาจล้าสมัยได้)',
    },
  };
  return labels[scope] || { title: scope, hint: '' };
};

function preferenceLines(value, isEn) {
  if (!value || typeof value !== 'object') return [];
  const labels = {
    language: isEn ? 'Language' : 'ภาษา',
    answer_style: isEn ? 'Answer style' : 'รูปแบบคำตอบ',
    currency: isEn ? 'Currency' : 'สกุลเงิน',
  };
  return Object.entries(value)
    .filter(([, val]) => val != null && String(val).trim())
    .map(([key, val]) => `${labels[key] || key}: ${val}`);
}

function workingLines(row) {
  const value = row?.value && typeof row.value === 'object' ? row.value : {};
  if (Array.isArray(value.bullets) && value.bullets.length) {
    return value.bullets.map((item) => String(item));
  }
  if (Array.isArray(value.decisions) && value.decisions.length) {
    return value.decisions.map((item) => item?.statement || JSON.stringify(item)).filter(Boolean);
  }
  if (Array.isArray(value.computed_facts) && value.computed_facts.length) {
    return value.computed_facts.slice(0, 8).map((item) => {
      const metric = item?.metric || item?.type || 'metric';
      const unit = item?.unit ? ` ${item.unit}` : '';
      return `${metric} = ${item?.value}${unit}`.trim();
    });
  }
  if (Array.isArray(value.sources) && value.sources.length) {
    return value.sources.slice(0, 6).map((item) => item?.title || item?.url || 'source');
  }
  const summary = String(row?.summary || '').trim();
  if (!summary) return [];
  return summary.split('\n').map((line) => line.replace(/^[-•]\s*/, '').trim()).filter(Boolean);
}

export default function ChatMemoryPanel({ open, onClose, userId, isEn }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!open || !userId) return;
    setLoading(true);
    setError('');
    const { data, error: loadError } = await supabase
      .from('chat_memories')
      .select('id,scope,memory_key,summary,value,updated_at')
      .eq('user_id', userId)
      .order('updated_at', { ascending: false });
    if (loadError) setError(loadError.message);
    else setRows((data || []).map((row) => ({
      ...row,
      summaryDraft: row.summary || '',
      valueDraft: JSON.stringify(row.value || {}, null, 2),
    })));
    setLoading(false);
  }, [open, userId]);

  useEffect(() => {
    load();
  }, [load]);

  const grouped = useMemo(() => {
    const buckets = { user: [], conversation: [], project: [], evidence: [] };
    for (const row of rows) {
      if (buckets[row.scope]) buckets[row.scope].push(row);
      else buckets.conversation.push(row);
    }
    return buckets;
  }, [rows]);

  const updateDraft = (id, field, value) => {
    setRows((current) => current.map((row) => (
      row.id === id ? { ...row, [field]: value } : row
    )));
  };

  const save = async (row) => {
    setError('');
    try {
      const parsedValue = JSON.parse(row.valueDraft || '{}');
      const { error: saveError } = await supabase
        .from('chat_memories')
        .update({
          summary: row.summaryDraft,
          value: parsedValue,
          updated_at: new Date().toISOString(),
        })
        .eq('id', row.id)
        .eq('user_id', userId);
      if (saveError) throw saveError;
      await load();
    } catch (saveError) {
      setError(saveError.message || String(saveError));
    }
  };

  const remove = async (id) => {
    const { error: removeError } = await supabase
      .from('chat_memories')
      .delete()
      .eq('id', id)
      .eq('user_id', userId);
    if (removeError) setError(removeError.message);
    else setRows((current) => current.filter((row) => row.id !== id));
  };

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
      <div className="max-h-[85vh] w-full max-w-2xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-700">
          <div className="flex items-center gap-2">
            <Layers3 size={18} className="text-stone-500" />
            <div>
              <h2 className="font-semibold">
                {isEn ? 'Conversation memory' : 'ความจำการสนทนา'}
              </h2>
              <p className="text-[11px] text-slate-500">
                {isEn
                  ? 'Working notes, preferences, and approved definitions used in analysis.'
                  : 'บันทึกงาน ค่ากำหนด และนิยามที่อนุมัติแล้วสำหรับการวิเคราะห์'}
              </p>
            </div>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-2 hover:bg-slate-100 dark:hover:bg-slate-800">
            <X size={18} />
          </button>
        </div>
        <div className="app-main-scroll max-h-[72vh] space-y-5 overflow-y-auto p-5">
          <GovernedMemoryManager open={open} userId={userId} isEn={isEn} showOrganizationAdmin={false} />

          <section className="space-y-3">
            <div>
              <h3 className="text-sm font-semibold">
                {isEn ? 'Session & preferences' : 'บริบทเซสชันและค่ากำหนด'}
              </h3>
              <p className="mt-1 text-[11px] text-slate-500">
                {isEn
                  ? 'Auto-maintained notes from chat. Edit carefully — these shape follow-up context.'
                  : 'บันทึกอัตโนมัติจากแชท แก้ไขอย่างระมัดระวัง เพราะมีผลต่อบริบทคำถามถัดไป'}
              </p>
            </div>
            {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">{error}</p>}
            {loading && <p className="text-sm text-slate-500">{isEn ? 'Loading memory…' : 'กำลังโหลดความจำ…'}</p>}
            {!loading && rows.length === 0 && (
              <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-700">
                {isEn
                  ? 'No working notes yet. They appear after you analyze a question, or tap Remember on an answer.'
                  : 'ยังไม่มีบันทึกงาน ระบบจะสร้างหลังวิเคราะห์คำถาม หรือกดจำจากคำตอบ'}
              </p>
            )}
            {SECTION_ORDER.map((scope) => {
              const items = grouped[scope] || [];
              if (!items.length) return null;
              const meta = scopeMeta(scope, isEn);
              return (
                <div key={scope} className="space-y-2">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{meta.title}</p>
                    <p className="text-[10px] text-slate-400">{meta.hint}</p>
                  </div>
                  {items.map((row) => {
                    const lines = scope === 'user'
                      ? preferenceLines(row.value, isEn)
                      : workingLines(row);
                    return (
                      <article key={row.id} className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
                        <div className="mb-3 flex items-start justify-between gap-3">
                          <div>
                            <p className="text-xs font-medium text-slate-700 dark:text-slate-200">
                              {row.updated_at
                                ? new Date(row.updated_at).toLocaleString(isEn ? 'en-US' : 'th-TH')
                                : row.memory_key}
                            </p>
                            <p className="text-[10px] text-slate-400">{row.memory_key}</p>
                          </div>
                          <button type="button" onClick={() => remove(row.id)} className="rounded-lg p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-950/40" title={isEn ? 'Forget' : 'ลืมรายการนี้'}>
                            <Trash2 size={15} />
                          </button>
                        </div>
                        {lines.length > 0 ? (
                          <ul className="space-y-1.5 text-sm text-slate-700 dark:text-slate-200">
                            {lines.map((line) => (
                              <li key={line} className="flex gap-2">
                                <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-stone-400" />
                                <span>{line}</span>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-sm text-slate-500">{row.summary || (isEn ? 'Empty note' : 'ยังไม่มีเนื้อหา')}</p>
                        )}
                        <details className="mt-3 text-xs text-slate-500">
                          <summary className="cursor-pointer">{isEn ? 'Advanced edit' : 'แก้ไขขั้นสูง'}</summary>
                          <textarea
                            value={row.summaryDraft}
                            onChange={(event) => updateDraft(row.id, 'summaryDraft', event.target.value)}
                            className="mt-2 min-h-20 w-full rounded-lg border border-slate-200 bg-transparent p-3 text-sm dark:border-slate-700"
                            aria-label={isEn ? 'Memory summary' : 'สรุปความจำ'}
                          />
                          <textarea
                            value={row.valueDraft}
                            onChange={(event) => updateDraft(row.id, 'valueDraft', event.target.value)}
                            className="mt-2 min-h-28 w-full rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-xs dark:border-slate-700 dark:bg-slate-950"
                            aria-label={isEn ? 'Structured memory JSON' : 'JSON ความจำแบบโครงสร้าง'}
                          />
                          <button type="button" onClick={() => save(row)} className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-3 py-2 text-xs font-medium text-white hover:bg-stone-800 dark:bg-stone-100 dark:text-stone-900">
                            <Save size={13} />
                            {isEn ? 'Save changes' : 'บันทึกการแก้ไข'}
                          </button>
                        </details>
                      </article>
                    );
                  })}
                </div>
              );
            })}
          </section>
        </div>
      </div>
    </div>
  );
}
