// @ts-nocheck
'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Cloud, ExternalLink, LoaderCircle, MessageCircle, Trash2 } from '@/components/icons';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { authFetch } from '../utils/authFetch.js';
import { getPublicApiUrl } from '../utils/env.js';
import { localePath } from '../utils/locale.js';
import { DeleteConfirmationModal } from './ChatModals';
import AppSelect from './ui/AppSelect';

const emptyForm = {
  provider: 'google',
  display_name: '',
  source_url: '',
  sheet_name: '',
};

export default function CloudDatasetView({ isEn, user }) {
  const router = useRouter();
  const routing = useLocaleRouting();
  const [connections, setConnections] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  const [deleteTarget, setDeleteTarget] = useState(null);
  const apiUrl = getPublicApiUrl();
  const userId = user?.id;

  const loadConnections = useCallback(async () => {
    if (!userId) return;
    const response = await authFetch(`${apiUrl}/api/v1/cloud-datasets`, { method: 'GET' });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || 'Could not load cloud connections');
    setConnections(payload.connections || []);
  }, [apiUrl, userId]);

  useEffect(() => {
    loadConnections().catch((error) => setMessage(error.message));
  }, [loadConnections]);

  const connect = async (event) => {
    event.preventDefault();
    setBusy('create');
    setMessage('');
    const body = {
      user_id: userId,
      ...form,
      sheet_name: form.sheet_name || null,
    };
    try {
      const saveResponse = await authFetch(`${apiUrl}/api/v1/cloud-datasets`, { body });
      const saved = await saveResponse.json().catch(() => ({}));
      if (!saveResponse.ok) throw new Error(saved.detail || 'Could not save connection');
      setForm(emptyForm);
      await loadConnections();
      setMessage(isEn
        ? 'Connection saved. Open it in Chat to scan and set up the dataset.'
        : 'บันทึกการเชื่อมต่อแล้ว เปิดผ่าน Chat เพื่อตรวจและตั้งค่า Dataset');
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy('');
    }
  };

  const remove = async () => {
    if (!deleteTarget) return;
    const connection = deleteTarget;
    setBusy(connection.id);
    try {
      const response = await authFetch(`${apiUrl}/api/v1/cloud-datasets`, {
        method: 'DELETE',
        body: { user_id: userId, connection_id: connection.id },
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || 'Delete failed');
      }
      setDeleteTarget(null);
      await loadConnections();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy('');
    }
  };

  const openInDataSetup = (connection) => {
    const params = new URLSearchParams({
      cloud: connection.id,
      cloudName: connection.display_name,
    });
    router.push(localePath(`/chat/new?${params.toString()}`, routing));
  };

  return (
    <div className="icon-motion-scope space-y-6">
      <section className="enterprise-panel p-6">
        <div className="flex items-start gap-3 mb-5">
          <Cloud className="w-6 h-6 text-[#d97706] mt-0.5" strokeWidth={1.5} />
          <div>
            <h2 className="font-semibold text-slate-900 dark:text-slate-100">
              {isEn ? 'Cloud spreadsheets' : 'เชื่อมไฟล์ Spreadsheet บน Cloud'}
            </h2>
            <p className="text-sm text-slate-500 mt-1">
              {isEn
                ? 'The source stays in Google or Microsoft. Adaptive Data Setup scans it transiently, asks for approval, and publishes a versioned Parquet result.'
                : 'ไฟล์ต้นฉบับอยู่ที่ Google หรือ Microsoft โดย Adaptive Data Setup จะตรวจชั่วคราว ถามข้อมูลให้ครบ และ Publish ผล Parquet แบบมีเวอร์ชันหลังอนุมัติ'}
            </p>
          </div>
        </div>

        <form onSubmit={connect} className="grid gap-4">
          <div className="grid md:grid-cols-2 gap-4">
            <label className="text-sm text-slate-600 dark:text-slate-300">
              {isEn ? 'Provider' : 'ผู้ให้บริการ'}
              <AppSelect
                className="mt-1.5"
                value={form.provider}
                onChange={(provider) => setForm({ ...form, provider })}
                options={[
                  { value: 'google', label: 'Google Drive / Google Sheets' },
                  { value: 'microsoft', label: 'OneDrive / SharePoint' },
                ]}
                aria-label={isEn ? 'Provider' : 'ผู้ให้บริการ'}
              />
            </label>
            <label className="text-sm text-slate-600 dark:text-slate-300">
              {isEn ? 'Dataset name' : 'ชื่อ Dataset'}
              <input
                required
                value={form.display_name}
                onChange={(event) => setForm({ ...form, display_name: event.target.value })}
                placeholder="Sales report"
                className="app-input mt-1.5 w-full px-3 py-3 text-sm"
              />
            </label>
          </div>
          <label className="text-sm text-slate-600 dark:text-slate-300">
            {isEn ? 'Share link' : 'ลิงก์แชร์ไฟล์'}
            <input
              required
              type="url"
              value={form.source_url}
              onChange={(event) => setForm({ ...form, source_url: event.target.value })}
              placeholder={form.provider === 'google' ? 'https://docs.google.com/spreadsheets/d/…' : 'https://…sharepoint.com/… or https://1drv.ms/…'}
              className="app-input mt-1.5 w-full px-3 py-3 text-sm"
            />
          </label>
          <label className="text-sm text-slate-600 dark:text-slate-300">
            {isEn ? 'Sheet name (optional)' : 'ชื่อชีต (ไม่บังคับ)'}
            <input
              value={form.sheet_name}
              onChange={(event) => setForm({ ...form, sheet_name: event.target.value })}
              className="app-input mt-1.5 w-full px-3 py-3 text-sm"
            />
          </label>
          <div>
            <button disabled={busy === 'create'} className="btn-primary px-5 py-2 text-sm inline-flex items-center gap-2">
              {busy === 'create' && <LoaderCircle className="w-4 h-4 animate-spin" />}
              {isEn ? 'Save connection' : 'บันทึกการเชื่อมต่อ'}
            </button>
          </div>
        </form>
      </section>

      {message && <div className="enterprise-panel px-4 py-3 text-sm text-slate-700 dark:text-slate-200">{message}</div>}

      <div className="grid gap-4">
        {connections.map((connection) => (
          <article key={connection.id} className="enterprise-panel p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="min-w-0">
              <p className="font-semibold text-slate-900 dark:text-slate-100 truncate">{connection.display_name}</p>
              <p className="text-xs text-slate-500 mt-1">
                {connection.provider === 'google' ? 'Google' : 'Microsoft'} · {connection.file_type?.toUpperCase() || 'Spreadsheet'} · {connection.last_status}
              </p>
              <p className="text-xs text-slate-400 mt-1">
                {connection.last_synced_at
                  ? `${isEn ? 'Last refresh' : 'รีเฟรชล่าสุด'} ${new Date(connection.last_synced_at).toLocaleString()}`
                  : (isEn ? 'Not refreshed yet' : 'ยังไม่เคย Refresh')}
              </p>
              {connection.last_error && <p className="text-xs text-red-500 mt-1">{connection.last_error}</p>}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={() => openInDataSetup(connection)}
                className="btn-primary px-4 py-2 text-sm inline-flex items-center gap-2"
              >
                <MessageCircle className="w-4 h-4" />
                {isEn ? 'Set up in Chat' : 'ตั้งค่าผ่าน Chat'}
              </button>
              <a href={connection.source_url} target="_blank" rel="noreferrer" className="p-2 text-slate-500 hover:text-slate-900" title={isEn ? 'Open source' : 'เปิดไฟล์ต้นฉบับ'}>
                <ExternalLink className="w-5 h-5" />
              </a>
              <button onClick={() => setDeleteTarget(connection)} disabled={busy === connection.id} className="p-2 text-slate-400 hover:text-red-500">
                <Trash2 className="w-5 h-5" />
              </button>
            </div>
          </article>
        ))}
      </div>

      <DeleteConfirmationModal
        isOpen={Boolean(deleteTarget)}
        onClose={() => !busy && setDeleteTarget(null)}
        onConfirm={remove}
        title={isEn ? 'Delete this connection?' : 'ลบการเชื่อมต่อนี้หรือไม่?'}
        subject={deleteTarget?.display_name}
        message={
          isEn
            ? 'This cloud spreadsheet connection will be permanently removed and cannot be recovered.'
            : 'การเชื่อมต่อ spreadsheet บน cloud นี้จะถูกลบอย่างถาวร และกู้คืนไม่ได้'
        }
        confirmButtonText={isEn ? 'Delete connection' : 'ลบการเชื่อมต่อ'}
        cancelButtonText={isEn ? 'Cancel' : 'ยกเลิก'}
        isLoading={Boolean(deleteTarget && busy === deleteTarget.id)}
      />
    </div>
  );
}
