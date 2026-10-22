// @ts-nocheck
'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  Clock3,
  Copy,
  Download,
  Link2,
  Loader2,
  Save,
  Settings,
  Trash2,
  X,
} from '@/components/icons';
import { visualizationRequest } from '../utils/visualizationApi.js';
import { captureDashboardPng } from '../features/visualization/dashboardExport.js';
import { DeleteConfirmationModal } from './ChatModals';

const VisualizationDeliveryPanel = ({
  userId,
  report,
  dashboard,
  locale,
  isEn,
  onDashboardChange,
}) => {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState('export');
  const [revisions, setRevisions] = useState([]);
  const [shares, setShares] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [templateName, setTemplateName] = useState('');
  const [shareDays, setShareDays] = useState(30);
  const [allowDetails, setAllowDetails] = useState(false);
  const [shareMaxViews, setShareMaxViews] = useState('');
  const [confirmAction, setConfirmAction] = useState(null);

  const loadResources = useCallback(async () => {
    if (!report?.id) return;
    setBusy('load');
    setError('');
    try {
      const [revisionPayload, sharePayload, templatePayload] = await Promise.all([
        visualizationRequest(`/dashboard/revisions?report_id=${encodeURIComponent(report.id)}`, { method: 'GET' }),
        visualizationRequest(`/shares?report_id=${encodeURIComponent(report.id)}`, { method: 'GET' }),
        visualizationRequest('/templates', { method: 'GET' }),
      ]);
      setRevisions(revisionPayload.revisions || []);
      setShares(sharePayload.shares || []);
      setTemplates(templatePayload.templates || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  }, [report]);

  useEffect(() => {
    if (open) loadResources();
  }, [open, loadResources]);

  const exportPng = async () => {
    const node = document.querySelector('[data-dashboard-export]');
    if (!node) return;
    setBusy('png');
    setError('');
    try {
      const dataUrl = await captureDashboardPng(node);
      const link = document.createElement('a');
      link.download = `${String(report?.title || 'dashboard').replace(/[^\w\u0E00-\u0E7F-]+/g, '-')}.png`;
      link.href = dataUrl;
      link.click();
    } catch (err) {
      console.error('Dashboard PNG export failed', err);
      setError(isEn ? 'PNG export failed. Try PDF export instead.' : 'Export PNG ไม่สำเร็จ กรุณาลอง Export PDF');
    } finally {
      setBusy('');
    }
  };

  const exportPdf = async () => {
    const node = document.querySelector('[data-dashboard-export]');
    if (!node) return;
    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      setError(isEn ? 'Allow pop-ups to export PDF.' : 'กรุณาอนุญาต Pop-up เพื่อ Export PDF');
      return;
    }
    printWindow.opener = null;
    setBusy('pdf');
    try {
      const dataUrl = await captureDashboardPng(node);
      printWindow.document.write('<!doctype html><html><head><title>Dashboard PDF</title><style>@page{size:landscape;margin:8mm}body{margin:0}img{display:block;width:100%;height:auto}</style></head><body><img id="dashboard" alt="Dashboard"></body></html>');
      printWindow.document.close();
      const image = printWindow.document.getElementById('dashboard');
      image.onload = () => {
        printWindow.focus();
        printWindow.print();
      };
      image.src = dataUrl;
    } catch (err) {
      console.error('Dashboard PDF export failed', err);
      printWindow.close();
      setError(isEn ? 'PDF export failed.' : 'Export PDF ไม่สำเร็จ');
    } finally {
      setBusy('');
    }
  };

  const createShare = async () => {
    setBusy('share');
    setError('');
    try {
      const payload = await visualizationRequest('/shares', {
        body: {
          user_id: userId,
          report_id: report.id,
          expires_in_days: Number(shareDays),
          allow_detail_rows: allowDetails,
          max_views: shareMaxViews ? Number(shareMaxViews) : null,
        },
      });
      setShares((items) => [payload.share, ...items]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const revokeShare = async (shareId) => {
    setBusy(`share:${shareId}`);
    try {
      await visualizationRequest('/shares', {
        method: 'DELETE',
        body: { user_id: userId, report_id: report.id, share_id: shareId },
      });
      setShares((items) => items.map((item) => (
        item.id === shareId ? { ...item, revoked_at: new Date().toISOString() } : item
      )));
      setConfirmAction(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const restoreRevision = async (revisionId) => {
    setBusy(`revision:${revisionId}`);
    try {
      const payload = await visualizationRequest('/dashboard/revisions/restore', {
        body: { user_id: userId, report_id: report.id, revision_id: revisionId },
      });
      onDashboardChange?.(payload.dashboard, true);
      await loadResources();
      setConfirmAction(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const saveTemplate = async () => {
    if (!templateName.trim()) return;
    setBusy('template');
    try {
      const payload = await visualizationRequest('/templates', {
        body: {
          user_id: userId,
          report_id: report.id,
          name: templateName.trim(),
        },
      });
      setTemplates((items) => [payload.template, ...items]);
      setTemplateName('');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const applyTemplate = async (templateId, persist) => {
    setBusy(`template:${templateId}:${persist}`);
    try {
      const payload = await visualizationRequest('/templates/preview', {
        body: {
          user_id: userId,
          report_id: report.id,
          template_id: templateId,
          persist,
        },
      });
      onDashboardChange?.(payload.dashboard, persist);
      if (persist) await loadResources();
      setOpen(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const deleteTemplate = async (templateId) => {
    setBusy(`template-delete:${templateId}`);
    try {
      await visualizationRequest('/templates', {
        method: 'DELETE',
        body: { user_id: userId, template_id: templateId },
      });
      setTemplates((items) => items.filter((item) => item.id !== templateId));
      setConfirmAction(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const runConfirmAction = () => {
    if (!confirmAction) return;
    if (confirmAction.kind === 'revoke') return revokeShare(confirmAction.id);
    if (confirmAction.kind === 'restore') return restoreRevision(confirmAction.id);
    if (confirmAction.kind === 'delete-template') return deleteTemplate(confirmAction.id);
    return undefined;
  };

  const confirmCopy = (() => {
    if (confirmAction?.kind === 'revoke') {
      return {
        title: isEn ? 'Revoke this share link?' : 'ยกเลิกลิงก์แชร์นี้หรือไม่?',
        message: isEn
          ? 'Anyone with this link will lose access immediately.'
          : 'ผู้ที่มีลิงก์นี้จะเข้าถึงไม่ได้ทันที',
        confirmButtonText: isEn ? 'Revoke link' : 'ยกเลิกลิงก์',
        tone: 'danger',
        icon: 'trash',
        loadingKey: confirmAction?.id ? `share:${confirmAction.id}` : '',
      };
    }
    if (confirmAction?.kind === 'restore') {
      return {
        title: isEn ? 'Restore this revision?' : 'กู้คืนเวอร์ชันนี้หรือไม่?',
        message: isEn
          ? 'The current dashboard will be replaced with this saved revision.'
          : 'Dashboard ปัจจุบันจะถูกแทนที่ด้วยเวอร์ชันที่บันทึกไว้นี้',
        confirmButtonText: isEn ? 'Restore' : 'กู้คืน',
        tone: 'warning',
        icon: 'alert',
        loadingKey: confirmAction?.id ? `revision:${confirmAction.id}` : '',
      };
    }
    return {
      title: isEn ? 'Delete this template?' : 'ลบเทมเพลตนี้หรือไม่?',
      message: isEn
        ? 'This template will be permanently deleted and cannot be recovered.'
        : 'เทมเพลตนี้จะถูกลบอย่างถาวร และกู้คืนไม่ได้',
      confirmButtonText: isEn ? 'Delete template' : 'ลบเทมเพลต',
      tone: 'danger',
      icon: 'trash',
      loadingKey: confirmAction?.id ? `template-delete:${confirmAction.id}` : '',
    };
  })();

  const shareUrl = (token) => (
    `${window.location.origin}/${locale}/shared/visualizations/${token}`
  );

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="btn-secondary inline-flex items-center gap-2 px-3 py-2 text-xs">
        <Settings size={14} />{isEn ? 'Decision packet' : 'Decision packet'}
      </button>
      {open && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/60 p-4 print:hidden">
          <div className="max-h-[88vh] w-full max-w-3xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-800">
              <div className="font-serif text-lg font-bold">{isEn ? 'Decision packet delivery' : 'ส่งมอบ Decision packet'}</div>
              <button type="button" onClick={() => setOpen(false)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"><X size={16} /></button>
            </div>
            <div className="flex gap-1 overflow-x-auto border-b border-slate-200 px-4 pt-3 dark:border-slate-800">
              {[
                ['export', isEn ? 'Export' : 'Export'],
                ['share', isEn ? 'Share links' : 'ลิงก์แชร์'],
                ['history', isEn ? 'History' : 'ประวัติ'],
                ['templates', isEn ? 'Templates' : 'Template'],
              ].map(([value, label]) => (
                <button key={value} type="button" onClick={() => setTab(value)} className={`whitespace-nowrap rounded-t-lg px-4 py-2 text-xs font-semibold ${tab === value ? 'bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-white' : 'text-slate-400'}`}>{label}</button>
              ))}
            </div>
            <div className="max-h-[65vh] overflow-y-auto p-5">
              {error && <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950/20 dark:text-red-300">{error}</div>}
              {busy === 'load' ? <div className="flex justify-center py-12"><Loader2 size={24} className="animate-spin text-amber-600" /></div> : (
                <>
                  {tab === 'export' && (
                    <div className="grid gap-3 sm:grid-cols-2">
                      <button type="button" onClick={exportPng} disabled={busy === 'png'} className="rounded-xl border border-slate-200 p-5 text-left hover:border-amber-300 dark:border-slate-700">
                        <Download size={20} /> <div className="mt-3 text-sm font-semibold">PNG</div><div className="mt-1 text-xs text-slate-400">{isEn ? 'High-resolution dashboard image' : 'รูป Dashboard ความละเอียดสูง'}</div>
                      </button>
                      <button type="button" onClick={exportPdf} disabled={busy === 'pdf'} className="rounded-xl border border-slate-200 p-5 text-left hover:border-amber-300 dark:border-slate-700">
                        <Download size={20} /> <div className="mt-3 text-sm font-semibold">PDF</div><div className="mt-1 text-xs text-slate-400">{isEn ? 'Use the browser Save as PDF option' : 'เลือก Save as PDF จากหน้าต่างพิมพ์'}</div>
                      </button>
                    </div>
                  )}
                  {tab === 'share' && (
                    <div className="space-y-4">
                      <div className="grid gap-3 rounded-xl border border-slate-200 p-4 dark:border-slate-700 sm:grid-cols-[120px_140px_1fr_auto]">
                        <label className="text-[10px] text-slate-400">{isEn ? 'Expires (days)' : 'หมดอายุ (วัน)'}<input type="number" min="1" max="365" value={shareDays} onChange={(event) => setShareDays(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-950" /></label>
                        <label className="text-[10px] text-slate-400">{isEn ? 'View limit' : 'จำกัดครั้งที่เปิด'}<input type="number" min="1" max="1000000" value={shareMaxViews} placeholder={isEn ? 'Unlimited' : 'ไม่จำกัด'} onChange={(event) => setShareMaxViews(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-950" /></label>
                        <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={allowDetails} onChange={(event) => setAllowDetails(event.target.checked)} />{isEn ? 'Include detail tables' : 'รวมตารางรายละเอียด'}</label>
                        <button type="button" onClick={createShare} disabled={busy === 'share'} className="btn-primary px-4 py-2 text-xs">{isEn ? 'Create link' : 'สร้างลิงก์'}</button>
                      </div>
                      {shares.map((share) => {
                        const active = !share.revoked_at
                          && new Date(share.expires_at) > new Date()
                          && (!share.max_views || Number(share.access_count || 0) < Number(share.max_views));
                        return (
                          <div key={share.id} className="flex flex-col gap-3 rounded-xl border border-slate-200 p-4 dark:border-slate-700 sm:flex-row sm:items-center sm:justify-between">
                            <div className="min-w-0"><div className="truncate text-xs font-semibold">{active ? shareUrl(share.token) : (isEn ? 'Revoked or expired link' : 'ลิงก์ถูกยกเลิกหรือหมดอายุ')}</div><div className="mt-1 text-[10px] text-slate-400">{isEn ? 'Expires' : 'หมดอายุ'} {new Date(share.expires_at).toLocaleString()} · {share.access_count || 0}{share.max_views ? ` / ${share.max_views}` : ''} {isEn ? 'views' : 'ครั้ง'}</div></div>
                            <div className="flex gap-2">{active && <button type="button" onClick={() => navigator.clipboard.writeText(shareUrl(share.token))} className="btn-secondary p-2"><Copy size={13} /></button>}<button type="button" disabled={!active || busy === `share:${share.id}`} onClick={() => setConfirmAction({ kind: 'revoke', id: share.id })} className="rounded-lg p-2 text-red-500 hover:bg-red-50 disabled:opacity-30 dark:hover:bg-red-950/20"><Trash2 size={13} /></button></div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                  {tab === 'history' && (
                    <div className="space-y-2">
                      {revisions.length === 0 && <div className="py-10 text-center text-xs text-slate-400">{isEn ? 'No previous revisions yet.' : 'ยังไม่มีเวอร์ชันก่อนหน้า'}</div>}
                      {revisions.map((revision) => (
                        <div key={revision.id} className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 p-4 dark:border-slate-700">
                          <div><div className="text-xs font-semibold">{revision.change_summary || (isEn ? 'Dashboard update' : 'อัปเดต Dashboard')}</div><div className="mt-1 text-[10px] text-slate-400">{new Date(revision.created_at).toLocaleString()}</div></div>
                          <button type="button" onClick={() => setConfirmAction({ kind: 'restore', id: revision.id, subject: revision.change_summary || (isEn ? 'Dashboard update' : 'อัปเดต Dashboard') })} className="btn-secondary inline-flex items-center gap-2 px-3 py-2 text-xs"><Clock3 size={13} />{isEn ? 'Restore' : 'กู้คืน'}</button>
                        </div>
                      ))}
                    </div>
                  )}
                  {tab === 'templates' && (
                    <div className="space-y-4">
                      <div className="flex gap-2"><input value={templateName} onChange={(event) => setTemplateName(event.target.value)} maxLength={160} placeholder={isEn ? 'Template name' : 'ชื่อ Template'} className="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-950" /><button type="button" onClick={saveTemplate} disabled={!templateName.trim() || busy === 'template'} className="btn-primary inline-flex items-center gap-2 px-4 py-2 text-xs"><Save size={13} />{isEn ? 'Save current' : 'บันทึกชุดปัจจุบัน'}</button></div>
                      {templates.map((template) => (
                        <div key={template.id} className="flex flex-col gap-3 rounded-xl border border-slate-200 p-4 dark:border-slate-700 sm:flex-row sm:items-center sm:justify-between">
                          <div><div className="text-xs font-semibold">{template.name}</div><div className="mt-1 text-[10px] text-slate-400">{new Date(template.updated_at).toLocaleString()}</div></div>
                          <div className="flex gap-2"><button type="button" onClick={() => applyTemplate(template.id, false)} className="btn-secondary px-3 py-2 text-xs">{isEn ? 'Preview' : 'ดูตัวอย่าง'}</button><button type="button" onClick={() => applyTemplate(template.id, true)} className="btn-primary px-3 py-2 text-xs">{isEn ? 'Apply' : 'นำไปใช้'}</button><button type="button" onClick={() => setConfirmAction({ kind: 'delete-template', id: template.id, subject: template.name })} className="rounded-lg p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-950/20"><Trash2 size={13} /></button></div>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      <DeleteConfirmationModal
        isOpen={Boolean(confirmAction)}
        onClose={() => !busy && setConfirmAction(null)}
        onConfirm={runConfirmAction}
        title={confirmCopy.title}
        subject={confirmAction?.subject}
        message={confirmCopy.message}
        confirmButtonText={confirmCopy.confirmButtonText}
        cancelButtonText={isEn ? 'Cancel' : 'ยกเลิก'}
        tone={confirmCopy.tone}
        icon={confirmCopy.icon}
        isLoading={Boolean(confirmAction && busy === confirmCopy.loadingKey)}
      />
    </>
  );
};

export default VisualizationDeliveryPanel;
