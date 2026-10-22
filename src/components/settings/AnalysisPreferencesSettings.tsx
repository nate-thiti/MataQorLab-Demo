// @ts-nocheck
'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Gauge, Save } from '@/components/icons';
import { authFetch } from '../../utils/authFetch.js';
import { getPublicApiUrl } from '../../utils/env.js';
import AppSelect from '../ui/AppSelect';

const CURRENCIES = ['', 'THB', 'USD', 'EUR', 'GBP', 'JPY', 'CNY', 'SGD'];

export default function AnalysisPreferencesSettings({ userId, isEn = false, onSaved }) {
  const [language, setLanguage] = useState('auto');
  const [answerStyle, setAnswerStyle] = useState('auto');
  const [currency, setCurrency] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [savedAt, setSavedAt] = useState('');

  const languageOptions = useMemo(() => ([
    { value: 'auto', label: isEn ? 'Auto' : 'อัตโนมัติ' },
    { value: 'th', label: 'ไทย' },
    { value: 'en', label: 'English' },
  ]), [isEn]);

  const styleOptions = useMemo(() => ([
    { value: 'auto', label: isEn ? 'Auto' : 'อัตโนมัติ' },
    { value: 'concise', label: isEn ? 'Concise' : 'กระชับ' },
    { value: 'detailed', label: isEn ? 'Detailed' : 'ละเอียด' },
  ]), [isEn]);

  const currencyOptions = useMemo(() => (
    CURRENCIES.map((code) => ({
      value: code,
      label: code || (isEn ? 'Auto' : 'อัตโนมัติ'),
    }))
  ), [isEn]);

  const load = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    setError('');
    try {
      const response = await authFetch(`${getPublicApiUrl()}/api/v1/chat/preferences`, { method: 'GET' });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || 'Failed to load preferences');
      const prefs = payload.preferences || {};
      setLanguage(prefs.language || 'auto');
      setAnswerStyle(prefs.answer_style || 'auto');
      setCurrency(prefs.currency || '');
      setSavedAt(prefs.updated_at || '');
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    load();
  }, [load]);

  const save = async (event) => {
    event.preventDefault();
    if (!userId || saving) return;
    setSaving(true);
    setError('');
    try {
      const response = await authFetch(`${getPublicApiUrl()}/api/v1/chat/preferences`, {
        method: 'PUT',
        body: {
          language,
          answer_style: answerStyle,
          currency: currency || 'AUTO',
        },
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || 'Failed to save preferences');
      const prefs = payload.preferences || {};
      setLanguage(prefs.language || 'auto');
      setAnswerStyle(prefs.answer_style || 'auto');
      setCurrency(prefs.currency || '');
      setSavedAt(prefs.updated_at || '');
      onSaved?.(isEn ? 'Analysis preferences saved' : 'บันทึกค่าการวิเคราะห์แล้ว');
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div id="settings-analysis" className="enterprise-panel space-y-5 scroll-mt-24 p-6 md:p-8">
      <div className="flex items-center gap-3 border-b border-slate-200/80 pb-4 dark:border-white/10">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-50 text-[#d97706] dark:bg-amber-500/10">
          <Gauge size={18} strokeWidth={1.6} />
        </div>
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-white">
            {isEn ? 'Analysis preferences' : 'ค่ากำหนดการวิเคราะห์'}
          </h2>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
            {isEn
              ? 'Defaults used in Chat answers. Auto follows each question when unset.'
              : 'ค่าเริ่มต้นที่ใช้ในคำตอบ Chat หากเป็น Auto ระบบจะตามบริบทคำถาม'}
          </p>
        </div>
      </div>

      {error ? <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">{error}</p> : null}
      {loading ? (
        <p className="text-sm text-slate-500">{isEn ? 'Loading preferences…' : 'กำลังโหลดค่ากำหนด…'}</p>
      ) : (
        <form onSubmit={save} className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-3">
            <label className="block text-[11px] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
              {isEn ? 'Answer language' : 'ภาษาคำตอบ'}
              <AppSelect
                className="mt-1.5"
                value={language}
                onChange={setLanguage}
                options={languageOptions}
                aria-label={isEn ? 'Answer language' : 'ภาษาคำตอบ'}
              />
            </label>
            <label className="block text-[11px] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
              {isEn ? 'Answer style' : 'รูปแบบคำตอบ'}
              <AppSelect
                className="mt-1.5"
                value={answerStyle}
                onChange={setAnswerStyle}
                options={styleOptions}
                aria-label={isEn ? 'Answer style' : 'รูปแบบคำตอบ'}
              />
            </label>
            <label className="block text-[11px] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
              {isEn ? 'Currency' : 'สกุลเงิน'}
              <AppSelect
                className="mt-1.5"
                value={currency}
                onChange={setCurrency}
                options={currencyOptions}
                aria-label={isEn ? 'Currency' : 'สกุลเงิน'}
              />
            </label>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200/70 pt-4 dark:border-white/10">
            <p className="text-[11px] text-slate-400">
              {savedAt
                ? `${isEn ? 'Updated' : 'อัปเดต'}: ${new Date(savedAt).toLocaleString(isEn ? 'en-US' : 'th-TH')}`
                : (isEn ? 'Not saved yet' : 'ยังไม่มีการบันทึก')}
            </p>
            <button type="submit" disabled={saving} className="btn-primary inline-flex items-center gap-1.5 px-4 py-2.5 text-xs">
              <Save size={13} />
              {saving ? (isEn ? 'Saving…' : 'กำลังบันทึก…') : (isEn ? 'Save preferences' : 'บันทึกค่ากำหนด')}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
