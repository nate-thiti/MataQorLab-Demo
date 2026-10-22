// @ts-nocheck
'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CalendarClock,
  CheckCircle2,
  Clock3,
  Database,
  LoaderCircle,
  Pause,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Trash2,
  TriangleAlert,
  X,
} from '@/components/icons';

import { authFetch } from '../utils/authFetch.js';
import { getPublicApiUrl } from '../utils/env.js';
import { DeleteConfirmationModal } from './ChatModals';
import AppSelect from './ui/AppSelect';

const CRON_PRESETS = [
  { value: '0 * * * *', en: 'Every hour', th: 'ทุกชั่วโมง' },
  { value: '0 8 * * *', en: 'Daily at 08:00', th: 'ทุกวัน เวลา 08:00' },
  { value: '0 2 * * *', en: 'Daily at 02:00', th: 'ทุกวัน เวลา 02:00' },
  { value: '0 8 * * 1-5', en: 'Weekdays at 08:00', th: 'จันทร์–ศุกร์ เวลา 08:00' },
  { value: '0 9 * * 1', en: 'Every Monday at 09:00', th: 'ทุกวันจันทร์ เวลา 09:00' },
];

const WEEKDAYS = [
  { value: 1, en: 'Monday', th: 'วันจันทร์' },
  { value: 2, en: 'Tuesday', th: 'วันอังคาร' },
  { value: 3, en: 'Wednesday', th: 'วันพุธ' },
  { value: 4, en: 'Thursday', th: 'วันพฤหัสบดี' },
  { value: 5, en: 'Friday', th: 'วันศุกร์' },
  { value: 6, en: 'Saturday', th: 'วันเสาร์' },
  { value: 7, en: 'Sunday', th: 'วันอาทิตย์' },
];

const freshForm = (timezone = 'UTC') => ({
  schedule_id: null,
  recipe_id: '',
  schedule_kind: 'cron',
  cron_expression: '0 8 * * *',
  timezone,
  output_name: '',
  enabled: true,
  chat_delivery_enabled: false,
  chat_delivery_weekday: 1,
  chat_delivery_hour: 9,
  chat_delivery_minute: 0,
  chat_target_conversation_id: '',
  chat_delivery_prompt: '',
  alert_config: {
    delivery_enabled: false,
    recipient_opt_in: false,
    recipient: '',
    muted: false,
    minimum_severity: 'info',
    cooldown_minutes: 1440,
    significant_change_percent: 0,
    significant_kpi_change_percent: 0,
    require_complete_period: true,
    max_source_age_hours: 48,
    preview_acknowledged: false,
    ai_narration_enabled: true,
    locale: 'th',
  },
});

const formatDate = (value, isEn) => {
  if (!value) return isEn ? 'Not yet' : 'ยังไม่มี';
  return new Intl.DateTimeFormat(isEn ? 'en-GB' : 'th-TH', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
};

const statusStyle = {
  completed: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/20 dark:text-emerald-400 dark:border-emerald-900/40',
  running: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/20 dark:text-blue-400 dark:border-blue-900/40',
  failed: 'bg-red-50 text-red-700 border-red-200 dark:bg-red-950/20 dark:text-red-400 dark:border-red-900/40',
  scheduled: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/20 dark:text-amber-400 dark:border-amber-900/40',
  paused: 'bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700',
};

const selectClass = 'app-input mt-1.5 w-full px-3 py-3 text-sm';

export default function ScheduledEtlView({ isEn, user }) {
  const localTimezone = useMemo(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
    [],
  );
  const [recipes, setRecipes] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [runs, setRuns] = useState([]);
  const [form, setForm] = useState(() => freshForm(localTimezone));
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [guardrailPreview, setGuardrailPreview] = useState(null);
  const [deliveryMetrics, setDeliveryMetrics] = useState(null);
  const [scheduleLimit, setScheduleLimit] = useState(10);

  const request = useCallback(async (path, init = {}) => {
    const response = await authFetch(`${getPublicApiUrl()}/api/v1${path}`, init);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || (isEn ? 'Request failed' : 'ดำเนินการไม่สำเร็จ'));
    }
    return payload;
  }, [isEn]);

  const load = useCallback(async ({ quiet = false } = {}) => {
    if (!user?.id) return;
    if (!quiet) setLoading(true);
    try {
      const [recipePayload, schedulePayload] = await Promise.all([
        request('/etl/recipes', { method: 'GET' }),
        request('/etl/schedules', { method: 'GET' }),
      ]);
      setRecipes(recipePayload.recipes || []);
      setSchedules(schedulePayload.schedules || []);
      setRuns(schedulePayload.runs || []);
      setConversations(schedulePayload.conversations || []);
      setDeliveryMetrics(schedulePayload.delivery_metrics || null);
      setScheduleLimit(schedulePayload.schedule_limit || 10);
      setForm((current) => ({
        ...current,
        recipe_id: current.recipe_id || recipePayload.recipes?.[0]?.id || '',
      }));
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    } finally {
      setLoading(false);
    }
  }, [request, user?.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const openCreate = () => {
    const next = {
      ...freshForm(localTimezone),
      recipe_id: recipes[0]?.id || '',
      chat_target_conversation_id: conversations[0]?.id || '',
    };
    next.alert_config.locale = isEn ? 'en' : 'th';
    setForm(next);
    setShowForm(true);
    setMessage(null);
  };

  const openEdit = (schedule) => {
    setForm({
      schedule_id: schedule.id,
      recipe_id: schedule.recipe_id,
      schedule_kind: schedule.schedule_kind,
      cron_expression: schedule.cron_expression || '0 8 * * *',
      timezone: schedule.timezone || localTimezone,
      output_name: schedule.output_name || '',
      enabled: schedule.enabled,
      chat_delivery_enabled: Boolean(schedule.chat_delivery_enabled),
      chat_delivery_weekday: schedule.chat_delivery_weekday || 1,
      chat_delivery_hour: schedule.chat_delivery_hour ?? 9,
      chat_delivery_minute: schedule.chat_delivery_minute ?? 0,
      chat_target_conversation_id: schedule.chat_target_conversation_id || '',
      chat_delivery_prompt: schedule.chat_delivery_prompt || '',
      alert_config: {
        ...freshForm(localTimezone).alert_config,
        ...(schedule.alert_config || {}),
        preview_acknowledged: false,
      },
    });
    setGuardrailPreview(null);
    setShowForm(true);
    setMessage(null);
  };

  const save = async (event) => {
    event.preventDefault();
    if (!form.recipe_id) {
      setMessage({ type: 'error', text: isEn ? 'Select an ETL recipe first.' : 'กรุณาเลือก ETL recipe ก่อน' });
      return;
    }
    if (form.enabled && !form.alert_config?.preview_acknowledged) {
      setMessage({ type: 'error', text: isEn ? 'Preview automation guardrails before enabling this schedule.' : 'กรุณา Preview Automation Guardrails ก่อนเปิดใช้งาน Schedule' });
      return;
    }
    if (
      form.chat_delivery_enabled
      && (!form.chat_target_conversation_id || !form.chat_delivery_weekday)
    ) {
      setMessage({
        type: 'error',
        text: isEn
          ? 'Choose one weekday and one destination chat.'
          : 'กรุณาเลือก 1 วันและแชทปลายทาง',
      });
      return;
    }
    setBusy('save');
    setMessage(null);
    try {
      await request('/etl/schedules', {
        body: {
          user_id: user.id,
          ...form,
          cron_expression: form.schedule_kind === 'cron' ? form.cron_expression : null,
        },
      });
      setShowForm(false);
      setMessage({ type: 'success', text: isEn ? 'Schedule saved.' : 'บันทึกตารางเวลาแล้ว' });
      await load({ quiet: true });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const previewGuardrails = async () => {
    if (!form.recipe_id) return;
    setBusy('preview');
    setMessage(null);
    try {
      const payload = await request('/etl/schedules/preview', {
        body: {
          user_id: user.id,
          recipe_id: form.recipe_id,
          schedule_id: form.schedule_id,
          alert_config: form.alert_config,
          chat_delivery_enabled: form.chat_delivery_enabled,
          chat_target_conversation_id: form.chat_target_conversation_id || null,
        },
      });
      setGuardrailPreview(payload.preview);
      setForm((current) => ({
        ...current,
        alert_config: { ...payload.config, preview_acknowledged: true },
      }));
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const setGuardrail = (key, value) => {
    setGuardrailPreview(null);
    setForm((current) => ({
      ...current,
      alert_config: {
        ...(current.alert_config || {}),
        [key]: value,
        preview_acknowledged: false,
      },
    }));
  };

  const toggle = async (schedule) => {
    setBusy(`toggle:${schedule.id}`);
    try {
      await request('/etl/schedules', {
        body: {
          user_id: user.id,
          schedule_id: schedule.id,
          recipe_id: schedule.recipe_id,
          schedule_kind: schedule.schedule_kind,
          cron_expression: schedule.cron_expression,
          timezone: schedule.timezone || localTimezone,
          output_name: schedule.output_name,
          incremental_column: schedule.incremental_column,
          alert_config: schedule.alert_config || {},
          enabled: !schedule.enabled,
          chat_delivery_enabled: Boolean(schedule.chat_delivery_enabled),
          chat_delivery_weekday: schedule.chat_delivery_weekday,
          chat_delivery_hour: schedule.chat_delivery_hour ?? 9,
          chat_delivery_minute: schedule.chat_delivery_minute ?? 0,
          chat_target_conversation_id: schedule.chat_target_conversation_id,
          chat_delivery_prompt: schedule.chat_delivery_prompt,
        },
      });
      await load({ quiet: true });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const runNow = async (schedule) => {
    setBusy(`run:${schedule.id}`);
    setMessage(null);
    try {
      const result = await request('/etl/schedules/run', {
        body: { user_id: user.id, schedule_id: schedule.id },
      });
      setMessage({
        type: 'success',
        text: isEn
          ? `ETL completed: ${result.rows ?? 0} rows · ${result.dataset_key || ''}`
          : `ETL สำเร็จ: ${result.rows ?? 0} แถว · ${result.dataset_key || ''}`,
      });
      await load({ quiet: true });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
      await load({ quiet: true });
    } finally {
      setBusy('');
    }
  };

  const remove = async () => {
    if (!deleteTarget?.schedule) return;
    const schedule = deleteTarget.schedule;
    setBusy(`delete:${schedule.id}`);
    try {
      await request('/etl/schedules', {
        method: 'DELETE',
        body: { user_id: user.id, schedule_id: schedule.id },
      });
      setDeleteTarget(null);
      await load({ quiet: true });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const runBySchedule = useMemo(() => {
    const grouped = new Map();
    runs.forEach((run) => {
      if (!grouped.has(run.schedule_id)) grouped.set(run.schedule_id, []);
      grouped.get(run.schedule_id).push(run);
    });
    return grouped;
  }, [runs]);

  if (loading) {
    return (
      <div className="enterprise-panel min-h-64 flex items-center justify-center">
        <LoaderCircle className="w-6 h-6 animate-spin text-[#d97706]" />
      </div>
    );
  }

  return (
    <div className="app-module icon-motion-scope space-y-6">
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        <div>
          <div className="app-page-kicker mb-2">AUTOMATION CONTROL</div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-white flex items-center gap-2">
            <CalendarClock className="w-5 h-5 text-[#d97706]" />
            Scheduled ETL Execution
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-2 max-w-2xl">
            {isEn
              ? 'Run approved cleaning recipes automatically. Each schedule publishes versions under one stable dataset identity for Chat and Visualization.'
              : 'รัน Cleaning recipe อัตโนมัติ โดยแต่ละ Schedule มี Dataset ID ถาวรหนึ่งตัวสำหรับ Chat และ Visualization ส่วนแต่ละรอบยังเก็บเป็นเวอร์ชันตรวจย้อนหลังได้'}
          </p>
        </div>
        <button
          onClick={openCreate}
          disabled={!recipes.length}
          className="btn-primary px-5 py-2.5 text-sm inline-flex items-center gap-2 disabled:opacity-40"
        >
          <Plus className="w-4 h-4" />
          {isEn ? 'New schedule' : 'เพิ่มตารางเวลา'}
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {[
          [isEn ? 'Workspace schedules' : 'Schedule ใน Workspace', `${schedules.length} / ${scheduleLimit}`],
          [isEn ? 'Delivered reports' : 'รายงานที่ส่งแล้ว', deliveryMetrics?.delivered ?? 0],
          [isEn ? 'Open rate' : 'อัตราการเปิดอ่าน', deliveryMetrics?.open_rate == null ? 'N/A' : `${Math.round(deliveryMetrics.open_rate * 100)}%`],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
            <div className="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
            <div className="mt-1 font-semibold text-slate-800 dark:text-slate-200">{value}</div>
          </div>
        ))}
      </div>

      {message && (
        <div className={`rounded-lg border px-4 py-3 text-sm flex items-start gap-2 ${
          message.type === 'error'
            ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-400'
            : 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-400'
        }`}>
          {message.type === 'error'
            ? <TriangleAlert className="w-4 h-4 mt-0.5 shrink-0" />
            : <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />}
          <span>{message.text}</span>
        </div>
      )}

      {!recipes.length && (
        <div className="enterprise-panel p-8 text-center">
          <TriangleAlert className="w-10 h-10 mx-auto text-amber-500 mb-3" />
          <h3 className="font-semibold text-slate-900 dark:text-white">
            {isEn ? 'No approved ETL recipes yet' : 'ยังไม่มี ETL recipe ที่อนุมัติ'}
          </h3>
          <p className="text-sm text-slate-500 mt-2 max-w-lg mx-auto">
            {isEn
              ? 'Open a data file in Chat, confirm column mapping and cleaning rules, then save the recipe.'
              : 'เปิดไฟล์ข้อมูลใน Chat จากนั้นยืนยัน Column mapping และกฎการทำความสะอาด ระบบจึงจะสร้าง recipe สำหรับตั้งเวลา'}
          </p>
        </div>
      )}

      {showForm && (
        <form onSubmit={save} className="enterprise-panel p-6 space-y-5">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-slate-900 dark:text-white">
              {form.schedule_id
                ? (isEn ? 'Edit schedule' : 'แก้ไขตารางเวลา')
                : (isEn ? 'Create schedule' : 'สร้างตารางเวลา')}
            </h3>
            <button type="button" onClick={() => setShowForm(false)} className="p-2 text-slate-400 hover:text-slate-700">
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
              ETL recipe
              <AppSelect
                className="mt-1.5"
                value={form.recipe_id}
                onChange={(value) => setForm((current) => ({ ...current, recipe_id: value }))}
                disabled={Boolean(form.schedule_id)}
                options={recipes.map((recipe) => ({
                  value: recipe.id,
                  label: `${recipe.name} · ${recipe.dataset_key} · v${recipe.version}`,
                }))}
                aria-label="ETL recipe"
              />
            </label>

            <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
              {isEn ? 'Trigger' : 'รูปแบบการเรียกงาน'}
              <AppSelect
                className="mt-1.5"
                value={form.schedule_kind}
                onChange={(value) => setForm((current) => ({ ...current, schedule_kind: value }))}
                disabled={Boolean(form.chat_delivery_enabled)}
                options={[
                  { value: 'cron', label: isEn ? 'Recurring schedule' : 'ตามตารางเวลา' },
                  { value: 'on_upload', label: isEn ? 'When source is uploaded' : 'เมื่ออัปโหลดไฟล์ต้นทาง' },
                  { value: 'manual', label: isEn ? 'Manual / Run now only' : 'สั่งรันเองเท่านั้น' },
                ]}
                aria-label={isEn ? 'Trigger' : 'รูปแบบการเรียกงาน'}
              />
            </label>

            {form.schedule_kind === 'cron' && (
              <>
                {!form.chat_delivery_enabled && (
                  <>
                    <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                      {isEn ? 'Quick schedule' : 'รูปแบบสำเร็จรูป'}
                      <AppSelect
                        className="mt-1.5"
                        value={CRON_PRESETS.some((item) => item.value === form.cron_expression) ? form.cron_expression : 'custom'}
                        onChange={(value) => {
                          if (value !== 'custom') {
                            setForm((current) => ({ ...current, cron_expression: value }));
                          }
                        }}
                        options={[
                          ...CRON_PRESETS.map((preset) => ({
                            value: preset.value,
                            label: isEn ? preset.en : preset.th,
                          })),
                          { value: 'custom', label: isEn ? 'Custom cron' : 'กำหนด Cron เอง' },
                        ]}
                        aria-label={isEn ? 'Quick schedule' : 'รูปแบบสำเร็จรูป'}
                      />
                    </label>

                    <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                      Cron expression
                      <input
                        value={form.cron_expression}
                        onChange={(event) => setForm((current) => ({ ...current, cron_expression: event.target.value }))}
                        placeholder="0 8 * * *"
                        className="mt-1.5 w-full p-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm font-mono"
                      />
                    </label>
                  </>
                )}

                <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                  Timezone
                  <input
                    value={form.timezone}
                    onChange={(event) => setForm((current) => ({ ...current, timezone: event.target.value }))}
                    className="mt-1.5 w-full p-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
                  />
                </label>
              </>
            )}

            <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
              {isEn ? 'Dataset label (optional)' : 'ชื่อเรียก Dataset (ไม่บังคับ)'}
              <input
                value={form.output_name}
                onChange={(event) => setForm((current) => ({ ...current, output_name: event.target.value }))}
                placeholder={isEn ? 'Clean daily sales' : 'ยอดขายรายวันที่ทำความสะอาดแล้ว'}
                className={selectClass}
              />
            </label>
          </div>

          <section className="rounded-xl border border-blue-200 bg-blue-50/40 p-4 dark:border-blue-900/50 dark:bg-blue-950/10">
            <label className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
              <input
                type="checkbox"
                checked={Boolean(form.chat_delivery_enabled)}
                disabled={!conversations.length}
                onChange={(event) => {
                  const checked = event.target.checked;
                  setGuardrailPreview(null);
                  setForm((current) => ({
                    ...current,
                    chat_delivery_enabled: checked,
                    schedule_kind: checked ? 'cron' : current.schedule_kind,
                    chat_target_conversation_id: checked
                      ? (current.chat_target_conversation_id || conversations[0]?.id || '')
                      : current.chat_target_conversation_id,
                    alert_config: {
                      ...current.alert_config,
                      preview_acknowledged: false,
                    },
                  }));
                }}
                className="accent-[#d97706]"
              />
              {isEn ? 'Send weekly analysis into Chat' : 'ส่งบทวิเคราะห์รายสัปดาห์เข้า Chat'}
            </label>
            <p className="mt-1 text-[11px] text-slate-500">
              {conversations.length
                ? (isEn
                  ? 'Choose exactly one weekday and one chat. The same source dataset cannot be assigned to another chat schedule.'
                  : 'เลือกได้ 1 วันและ 1 แชทเท่านั้น ข้อมูลต้นทางชุดเดิมจะตั้งส่งซ้ำไปแชทอื่นไม่ได้')
                : (isEn
                  ? 'Create a chat conversation first, then return here to select it.'
                  : 'กรุณาสร้างห้องแชทก่อน แล้วกลับมาเลือกห้องปลายทางที่นี่')}
            </p>
            {form.chat_delivery_enabled && (
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                  {isEn ? 'Weekly delivery day' : 'วันที่ส่งประจำสัปดาห์'}
                  <AppSelect
                    className="mt-1.5"
                    value={form.chat_delivery_weekday}
                    onChange={(value) => {
                      setGuardrailPreview(null);
                      setForm((current) => ({
                        ...current,
                        chat_delivery_weekday: Number(value),
                        alert_config: { ...current.alert_config, preview_acknowledged: false },
                      }));
                    }}
                    options={WEEKDAYS.map((day) => ({
                      value: day.value,
                      label: isEn ? day.en : day.th,
                    }))}
                    aria-label={isEn ? 'Weekly delivery day' : 'วันที่ส่งประจำสัปดาห์'}
                  />
                </label>
                <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                  {isEn ? 'Delivery time' : 'เวลาที่ส่ง'}
                  <input
                    type="time"
                    value={`${String(form.chat_delivery_hour).padStart(2, '0')}:${String(form.chat_delivery_minute).padStart(2, '0')}`}
                    onChange={(event) => {
                      const [hour, minute] = event.target.value.split(':').map(Number);
                      setGuardrailPreview(null);
                      setForm((current) => ({
                        ...current,
                        chat_delivery_hour: hour,
                        chat_delivery_minute: minute,
                        alert_config: { ...current.alert_config, preview_acknowledged: false },
                      }));
                    }}
                    className={selectClass}
                  />
                </label>
                <label className="text-xs font-semibold text-slate-600 dark:text-slate-300 md:col-span-2">
                  {isEn ? 'Destination chat' : 'แชทปลายทาง'}
                  <AppSelect
                    className="mt-1.5"
                    value={form.chat_target_conversation_id}
                    onChange={(value) => {
                      setGuardrailPreview(null);
                      setForm((current) => ({
                        ...current,
                        chat_target_conversation_id: value,
                        alert_config: { ...current.alert_config, preview_acknowledged: false },
                      }));
                    }}
                    options={conversations.map((conversation) => ({
                      value: conversation.id,
                      label: conversation.title || (isEn ? 'Untitled chat' : 'แชทไม่มีชื่อ'),
                    }))}
                    aria-label={isEn ? 'Destination chat' : 'แชทปลายทาง'}
                  />
                </label>
                <label className="text-xs font-semibold text-slate-600 dark:text-slate-300 md:col-span-2">
                  {isEn ? 'Analysis emphasis (optional)' : 'ประเด็นที่อยากเน้น (ไม่บังคับ)'}
                  <textarea
                    maxLength={1000}
                    rows={3}
                    value={form.chat_delivery_prompt}
                    onChange={(event) => {
                      setGuardrailPreview(null);
                      setForm((current) => ({
                        ...current,
                        chat_delivery_prompt: event.target.value,
                        alert_config: { ...current.alert_config, preview_acknowledged: false },
                      }));
                    }}
                    placeholder={isEn ? 'Focus on weekly sales changes and anomalies.' : 'เช่น เน้นยอดขายที่เปลี่ยนแปลงและความผิดปกติประจำสัปดาห์'}
                    className={selectClass}
                  />
                </label>
              </div>
            )}
          </section>

          <section className="rounded-xl border border-amber-200 bg-amber-50/40 p-4 dark:border-amber-900/50 dark:bg-amber-950/10">
            <h4 className="text-sm font-semibold text-slate-900 dark:text-white">
              {isEn ? 'Automation guardrails' : 'Automation Guardrails'}
            </h4>
            <p className="mt-1 text-[11px] text-slate-500">
              {isEn
                ? 'When every gate passes, MataQorLab delivers an evidence-bounded report to each enabled channel.'
                : 'เมื่อผ่านทุก Gate ระบบจะส่งรายงานที่อ้างอิงเฉพาะหลักฐานไปยังช่องทางที่เปิดไว้'}
            </p>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                {isEn ? 'Opted-in recipient' : 'ผู้รับที่ Opt-in แล้ว'}
                <input
                  type="email"
                  value={form.alert_config?.recipient || ''}
                  onChange={(event) => setGuardrail('recipient', event.target.value)}
                  placeholder="manager@example.com"
                  className={selectClass}
                />
              </label>
              <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                {isEn ? 'Minimum severity' : 'Severity ขั้นต่ำ'}
                <AppSelect
                  className="mt-1.5"
                  value={form.alert_config?.minimum_severity || 'info'}
                  onChange={(value) => setGuardrail('minimum_severity', value)}
                  options={[
                    { value: 'info', label: 'Info' },
                    { value: 'warning', label: 'Warning' },
                    { value: 'critical', label: 'Critical' },
                  ]}
                  aria-label={isEn ? 'Minimum severity' : 'Severity ขั้นต่ำ'}
                />
              </label>
              <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                {isEn ? 'Cooldown (minutes)' : 'Cooldown (นาที)'}
                <input type="number" min="0" max="43200" value={form.alert_config?.cooldown_minutes ?? 1440} onChange={(event) => setGuardrail('cooldown_minutes', Number(event.target.value))} className={selectClass} />
              </label>
              <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                {isEn ? 'Maximum source age (hours)' : 'อายุข้อมูลสูงสุด (ชั่วโมง)'}
                <input type="number" min="1" max="8760" value={form.alert_config?.max_source_age_hours ?? 48} onChange={(event) => setGuardrail('max_source_age_hours', Number(event.target.value))} className={selectClass} />
              </label>
              <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                {isEn ? 'Minimum row change (%)' : 'การเปลี่ยนจำนวนแถวขั้นต่ำ (%)'}
                <input type="number" min="0" max="100" step="0.1" value={form.alert_config?.significant_change_percent ?? 0} onChange={(event) => setGuardrail('significant_change_percent', Number(event.target.value))} className={selectClass} />
              </label>
              <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                {isEn ? 'Minimum semantic KPI change (%)' : 'การเปลี่ยน KPI เชิงธุรกิจขั้นต่ำ (%)'}
                <input type="number" min="0" max="100" step="0.1" value={form.alert_config?.significant_kpi_change_percent ?? 0} onChange={(event) => setGuardrail('significant_kpi_change_percent', Number(event.target.value))} className={selectClass} />
              </label>
              <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                {isEn ? 'Report language' : 'ภาษาของรายงาน'}
                <AppSelect
                  className="mt-1.5"
                  value={form.alert_config?.locale || (isEn ? 'en' : 'th')}
                  onChange={(value) => setGuardrail('locale', value)}
                  options={[
                    { value: 'th', label: 'ไทย' },
                    { value: 'en', label: 'English' },
                  ]}
                  aria-label={isEn ? 'Report language' : 'ภาษาของรายงาน'}
                />
              </label>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2 text-xs text-slate-600 dark:text-slate-300">
              {[
                ['delivery_enabled', isEn ? 'Also send by email (SMTP)' : 'ส่งทางอีเมลด้วย (SMTP)'],
                ['recipient_opt_in', isEn ? 'Recipient has explicitly opted in' : 'ผู้รับยืนยัน Opt-in แล้ว'],
                ['ai_narration_enabled', isEn ? 'Generate evidence-bounded narration' : 'สร้างคำอธิบายจากหลักฐานที่คำนวณแล้ว'],
                ['require_complete_period', isEn ? 'Require complete reporting period' : 'ต้องเป็นงวดข้อมูลที่ครบแล้ว'],
                ['muted', isEn ? 'Mute this schedule' : 'Mute Schedule นี้'],
              ].map(([key, label]) => (
                <label key={key} className="inline-flex items-center gap-2">
                  <input type="checkbox" checked={Boolean(form.alert_config?.[key])} onChange={(event) => setGuardrail(key, event.target.checked)} className="accent-[#d97706]" />
                  {label}
                </label>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button type="button" onClick={previewGuardrails} disabled={busy === 'preview'} className="btn-secondary px-4 py-2 text-xs">
                {busy === 'preview' ? (isEn ? 'Previewing…' : 'กำลัง Preview…') : (isEn ? 'Preview guardrails' : 'Preview Guardrails')}
              </button>
              {guardrailPreview && (
                <span className={`text-xs font-semibold ${guardrailPreview.decision === 'eligible' ? 'text-emerald-600' : 'text-amber-600'}`}>
                  {guardrailPreview.decision} · {(guardrailPreview.reason_codes || []).join(', ') || (isEn ? 'all gates passed' : 'ผ่านทุก Gate')}
                </span>
              )}
            </div>
          </section>

          <label className="inline-flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))}
              className="accent-[#d97706]"
            />
            {isEn ? 'Enable immediately' : 'เปิดใช้งานทันที'}
          </label>

          <div className="flex justify-end gap-3">
            <button type="button" onClick={() => setShowForm(false)} className="btn-secondary px-5 py-2.5 text-sm">
              {isEn ? 'Cancel' : 'ยกเลิก'}
            </button>
            <button disabled={busy === 'save'} className="btn-primary px-5 py-2.5 text-sm inline-flex items-center gap-2">
              {busy === 'save' && <LoaderCircle className="w-4 h-4 animate-spin" />}
              {isEn ? 'Save schedule' : 'บันทึกตารางเวลา'}
            </button>
          </div>
        </form>
      )}

      {recipes.length > 0 && schedules.length === 0 && !showForm && (
        <button onClick={openCreate} className="enterprise-panel border-dashed w-full p-12 text-center hover:border-[#d97706]/50 transition-colors">
          <CalendarClock className="w-10 h-10 mx-auto text-slate-300 dark:text-slate-600 mb-3" />
          <span className="block font-semibold text-slate-800 dark:text-slate-200">
            {isEn ? 'Create your first ETL schedule' : 'สร้างตาราง ETL แรกของคุณ'}
          </span>
        </button>
      )}

      <div className="grid gap-4">
        {schedules.map((schedule) => {
          const recipe = schedule.etl_recipes || {};
          const recentRuns = runBySchedule.get(schedule.id) || [];
          const running = schedule.last_status === 'running' || Boolean(schedule.locked_at);
          const status = schedule.enabled ? (schedule.last_status || 'scheduled') : 'paused';
          return (
            <article key={schedule.id} className="enterprise-panel p-5">
              <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-semibold text-slate-900 dark:text-white truncate">
                      {recipe.name || 'ETL recipe'}
                    </h3>
                    <span className={`px-2 py-0.5 rounded-md border text-[10px] uppercase font-semibold ${statusStyle[status] || statusStyle.paused}`}>
                      {status}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mt-1 truncate">
                    {recipe.dataset_key} · v{recipe.version || 1}
                  </p>
                  {schedule.chat_delivery_enabled && (
                    <p className="mt-2 text-xs font-medium text-blue-600 dark:text-blue-400">
                      {isEn ? 'Weekly Chat' : 'ส่งเข้า Chat รายสัปดาห์'} ·{' '}
                      {(isEn ? WEEKDAYS.find((day) => day.value === schedule.chat_delivery_weekday)?.en : WEEKDAYS.find((day) => day.value === schedule.chat_delivery_weekday)?.th) || '—'}{' '}
                      {String(schedule.chat_delivery_hour ?? 9).padStart(2, '0')}:{String(schedule.chat_delivery_minute ?? 0).padStart(2, '0')}
                    </p>
                  )}
                  <div className="mt-4 grid gap-3 text-xs sm:grid-cols-2 xl:grid-cols-4">
                    <div>
                      <span className="text-slate-400 block mb-1">{isEn ? 'Output dataset' : 'Dataset ผลลัพธ์'}</span>
                      <span className="inline-flex max-w-full items-center gap-1.5 rounded-md bg-slate-100 px-2 py-1 font-mono text-[10px] font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        <Database className="h-3 w-3 shrink-0 text-[#d97706]" />
                        <span className="truncate">{schedule.output_dataset_key}</span>
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-400 block mb-1">{isEn ? 'Trigger' : 'การเรียกงาน'}</span>
                      <span className="font-medium text-slate-700 dark:text-slate-300">
                        {schedule.schedule_kind === 'cron'
                          ? `${schedule.cron_expression} · ${schedule.timezone}`
                          : schedule.schedule_kind}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-400 block mb-1">{isEn ? 'Next run' : 'รอบถัดไป'}</span>
                      <span className="font-medium text-slate-700 dark:text-slate-300">
                        {formatDate(schedule.next_run_at, isEn)}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-400 block mb-1">{isEn ? 'Last run' : 'รอบล่าสุด'}</span>
                      <span className="font-medium text-slate-700 dark:text-slate-300">
                        {formatDate(schedule.last_run_at, isEn)}
                      </span>
                    </div>
                  </div>
                  {schedule.latest_output_file && (
                    <p className="mt-3 truncate text-[10px] text-slate-400">
                      {isEn ? 'Current file' : 'ไฟล์ปัจจุบัน'}: {schedule.latest_output_file}
                      {schedule.latest_output_version
                        ? ` · ${isEn ? 'version' : 'เวอร์ชัน'}: ${schedule.latest_output_version}`
                        : ''}
                    </p>
                  )}
                  {schedule.last_error && (
                    <p className="mt-3 text-xs text-red-600 dark:text-red-400 line-clamp-2">
                      {schedule.last_error}
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => runNow(schedule)}
                    disabled={running || Boolean(busy)}
                    className="btn-primary px-3.5 py-2 text-xs inline-flex items-center gap-2 disabled:opacity-40"
                    title={isEn ? 'Run now' : 'รันทันที'}
                  >
                    {busy === `run:${schedule.id}`
                      ? <LoaderCircle className="w-4 h-4 animate-spin" />
                      : <Play className="w-4 h-4" />}
                    {isEn ? 'Run now' : 'รันทันที'}
                  </button>
                  <button onClick={() => toggle(schedule)} disabled={running || Boolean(busy)} className="p-2 text-slate-400 hover:text-slate-700 disabled:opacity-40" title={schedule.enabled ? 'Pause' : 'Enable'}>
                    {schedule.enabled ? <Pause className="w-4 h-4" /> : <RefreshCw className="w-4 h-4" />}
                  </button>
                  <button onClick={() => openEdit(schedule)} disabled={running} className="p-2 text-slate-400 hover:text-slate-700 disabled:opacity-40" title={isEn ? 'Edit' : 'แก้ไข'}>
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button onClick={() => setDeleteTarget({ schedule, label: recipe.name || schedule.output_dataset_key || schedule.id })} disabled={running || Boolean(busy)} className="p-2 text-slate-400 hover:text-red-500 disabled:opacity-40" title={isEn ? 'Delete' : 'ลบ'}>
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {recentRuns.length > 0 && (
                <div className="mt-5 pt-4 border-t border-slate-100 dark:border-slate-800">
                  <p className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold mb-2">
                    {isEn ? 'Recent executions' : 'ประวัติการทำงานล่าสุด'}
                  </p>
                  <div className="space-y-2">
                    {recentRuns.slice(0, 3).map((run) => (
                      <div key={run.id} className="flex items-center justify-between gap-3 text-xs">
                        <span className="flex items-center gap-2 min-w-0">
                          {run.status === 'completed'
                            ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                            : run.status === 'running'
                              ? <LoaderCircle className="w-3.5 h-3.5 text-blue-500 animate-spin shrink-0" />
                              : <TriangleAlert className="w-3.5 h-3.5 text-red-500 shrink-0" />}
                          <span className="truncate text-slate-600 dark:text-slate-300">
                            {run.status} · {run.trigger_kind}
                            {run.output_version ? ` · ${run.output_version}` : ''}
                          </span>
                        </span>
                        <span className="text-slate-400 shrink-0 flex items-center gap-1">
                          <Clock3 className="w-3 h-3" />
                          {formatDate(run.started_at, isEn)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </article>
          );
        })}
      </div>

      <DeleteConfirmationModal
        isOpen={Boolean(deleteTarget)}
        onClose={() => !busy && setDeleteTarget(null)}
        onConfirm={remove}
        title={isEn ? 'Delete this schedule?' : 'ลบตารางเวลานี้หรือไม่?'}
        subject={deleteTarget?.label}
        message={
          isEn
            ? 'This schedule will be permanently deleted and will no longer run.'
            : 'ตารางเวลานี้จะถูกลบอย่างถาวร และจะไม่รันอีกต่อไป'
        }
        confirmButtonText={isEn ? 'Delete schedule' : 'ลบตารางเวลา'}
        cancelButtonText={isEn ? 'Cancel' : 'ยกเลิก'}
        isLoading={Boolean(deleteTarget?.schedule && busy === `delete:${deleteTarget.schedule.id}`)}
      />
    </div>
  );
}
