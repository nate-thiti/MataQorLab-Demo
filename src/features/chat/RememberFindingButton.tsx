// @ts-nocheck
'use client';

import { useMemo, useState } from 'react';
import { Check, Loader2, Save } from '@/components/icons';
import { authFetch } from '../../utils/authFetch.js';
import { getPublicApiUrl } from '../../utils/env.js';
import { cleanMsgContent } from './messageContent.js';

function extractRememberPayload(message, isEn) {
  const raw = String(message?.content || '');
  const cleaned = cleanMsgContent(raw).replace(/\s+/g, ' ').trim();
  const findings = Array.isArray(message?.structuredFindings)
    ? message.structuredFindings
    : Array.isArray(message?.structured_findings)
      ? message.structured_findings
      : [];

  if (findings.length) {
    const top = findings.slice(0, 6).map((item) => {
      const metric = item?.metric || item?.type || 'metric';
      const value = item?.value;
      const unit = item?.unit ? ` ${item.unit}` : '';
      return `${metric} = ${value}${unit}`.trim();
    });
    return {
      title: (isEn ? 'Verified finding' : 'ข้อค้นพบที่ยืนยันแล้ว') + (top[0] ? `: ${String(top[0]).slice(0, 80)}` : ''),
      content: top.join('\n'),
      structured_value: { findings: findings.slice(0, 12) },
      memory_type: 'dataset_fact',
    };
  }

  const snippet = cleaned.slice(0, 900);
  const titleSeed = cleaned.split(/[.!?\n]/)[0]?.trim() || (isEn ? 'Chat finding' : 'ข้อค้นพบจากแชท');
  return {
    title: titleSeed.slice(0, 120),
    content: snippet || titleSeed,
    structured_value: {},
    memory_type: 'business_definition',
  };
}

export default function RememberFindingButton({ message, userId, isEn = false }) {
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  const payload = useMemo(() => extractRememberPayload(message, isEn), [message, isEn]);
  const canRemember = Boolean(userId && payload.content?.trim());

  const remember = async () => {
    if (!canRemember || busy) return;
    setBusy(true);
    setError('');
    try {
      const response = await authFetch(`${getPublicApiUrl()}/api/v1/governance/memories`, {
        method: 'POST',
        body: {
          title: payload.title,
          content: payload.content,
          memory_type: payload.memory_type,
          scope: 'personal',
          confidence: 0.85,
          source_type: 'verified_finding',
          source_ref: message?.id || null,
          structured_value: payload.structured_value,
        },
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || (isEn ? 'Could not save memory' : 'บันทึกความจำไม่สำเร็จ'));
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  if (!canRemember) return null;

  return (
    <span className="inline-flex items-center gap-1">
      <button
        type="button"
        onClick={remember}
        disabled={busy || saved}
        aria-label={isEn ? 'Remember this finding' : 'จำข้อค้นพบนี้'}
        title={isEn ? 'Remember this finding' : 'จำข้อค้นพบนี้'}
        className={`rounded-md p-1.5 transition-colors hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 ${saved ? 'text-emerald-600' : ''}`}
      >
        {busy ? <Loader2 size={14} className="animate-spin" /> : saved ? <Check size={14} /> : <Save size={14} />}
      </button>
      {error ? <span className="text-[10px] text-red-500">{error}</span> : null}
    </span>
  );
}
