// @ts-nocheck
'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CircleAlert,
  Database,
  Link2,
  LoaderCircle,
  MessageCircle,
  Network,
  Plus,
  RefreshCw,
  Shield,
  X,
} from '@/components/icons';
import DashboardSidebar from '../components/DashboardSidebar';
import { useAppSidebar } from '../context/AppSidebarContext';
import { useFileManagerCache } from '../context/FileManagerCacheContext';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { supabase } from '../utils/supabaseClient.js';
import { getE2eMockUser } from '../utils/e2eAuth.js';
import { customerExperienceRequest } from '../utils/customerExperienceApi.js';
import { hasOrganizationCustomerAccess } from '../utils/customerCenterAccess.js';
import {
  buildCustomerCenterPath,
  buildSettingsPath,
  buildVisualizationPath,
} from '../utils/dashboardRoutes.js';
import { localePath } from '../utils/locale.js';

const emptyOverview = {
  onboarding: { completed_steps: [], completion_percent: 0, next_step: 'profile' },
  data_assets: [],
  lineage: [],
  collaboration: [],
  alerts: [],
  alert_events: [],
  available_reports: [],
  integrations: [],
  embeds: [],
  invitations: [],
  governance: { organizations: [], workspaces: [] },
  summary: {
    healthy_assets: 0,
    asset_issues: 0,
    open_collaboration: 0,
    enabled_alerts: 0,
    active_integrations: 0,
  },
};

const inputClass = 'app-input w-full rounded-lg px-3 py-2 text-sm';

const copy = (isEn, en, th) => (isEn ? en : th);

const statusClass = (status) => {
  const value = String(status || '').toLowerCase();
  if (['healthy', 'delivered', 'accepted', 'on', 'enabled', 'open'].includes(value) || value === 'true') {
    return 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300';
  }
  if (['failed', 'revoked', 'rejected'].includes(value)) {
    return 'bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-300';
  }
  return 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300';
};

const CustomerCenter = () => {
  const router = useRouter();
  const searchParams = useSearchParams();
  const routing = useLocaleRouting();
  const isEn = routing.locale === 'en';
  const { isOpen, setIsOpen } = useAppSidebar();
  const fileManagerCache = useFileManagerCache();
  const [user, setUser] = useState(null);
  const [plan, setPlan] = useState({ name: 'Free' });
  const [overview, setOverview] = useState(emptyOverview);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [alertDraft, setAlertDraft] = useState({
    name: '',
    report_id: '',
    metric_key: 'revenue',
    operator: 'change_gt',
    threshold: '10',
    evaluation_interval_minutes: '5',
  });
  const [inviteDraft, setInviteDraft] = useState({ email: '', role: 'member' });
  const [inviteLink, setInviteLink] = useState('');

  const organizations = overview.governance?.organizations || [];
  const primaryMembership = organizations[0];
  const primaryOrganization = primaryMembership?.organizations;
  const hasOrganizationFeatures = hasOrganizationCustomerAccess(
    plan,
    overview.governance,
  );
  const selectedAlertReport = overview.available_reports?.find(
    (report) => report.id === alertDraft.report_id,
  );
  const alertMetricOptions = useMemo(() => {
    const kpis = selectedAlertReport?.dashboard_spec?.kpis || [];
    return [...new Set(kpis.map((kpi) => kpi.field || kpi.label).filter(Boolean))];
  }, [selectedAlertReport]);
  const openCollaboration = (overview.collaboration || []).filter((item) => item.status === 'open');
  const hasReports = Boolean(overview.available_reports?.length);

  const flash = (message) => {
    setNotice(message);
    setError('');
  };

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const payload = await customerExperienceRequest('/overview', { method: 'GET' });
      setOverview({ ...emptyOverview, ...payload });
      setAlertDraft((current) => {
        const reportId = current.report_id || payload.available_reports?.[0]?.id || '';
        const selected = payload.available_reports?.find((report) => report.id === reportId);
        const firstKpi = selected?.dashboard_spec?.kpis?.[0];
        return {
          ...current,
          report_id: reportId,
          metric_key: current.report_id
            ? current.metric_key
            : (firstKpi?.field || firstKpi?.label || current.metric_key),
        };
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!notice) return undefined;
    const timer = setTimeout(() => setNotice(''), 4000);
    return () => clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    let cancelled = false;
    const initialize = async () => {
      const mock = getE2eMockUser();
      const authUser = mock || (await supabase.auth.getUser()).data.user;
      if (!authUser) {
        setLoading(false);
        return;
      }
      if (cancelled) return;
      setUser(authUser);
      if (!mock) {
        const { data: profile } = await supabase
          .from('profiles')
          .select('plans(name)')
          .eq('id', authUser.id)
          .maybeSingle();
        const value = Array.isArray(profile?.plans) ? profile.plans[0] : profile?.plans;
        if (value?.name) setPlan(value);
      }
      await loadOverview();
    };
    initialize();
    return () => { cancelled = true; };
  }, [loadOverview, router, routing]);

  useEffect(() => {
    const invitationToken = searchParams.get('invite');
    if (!user || !invitationToken) return;
    let cancelled = false;
    const accept = async () => {
      setBusy('accept-invite');
      try {
        await customerExperienceRequest('/organization-invitations/accept', {
          method: 'POST',
          body: { token: invitationToken },
        });
        if (cancelled) return;
        flash(copy(isEn, 'Organization invitation accepted.', 'เข้าร่วมองค์กรแล้ว'));
        router.replace(buildCustomerCenterPath(routing));
        await loadOverview();
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setBusy('');
      }
    };
    accept();
    return () => { cancelled = true; };
  }, [isEn, loadOverview, router, routing, searchParams, user]);

  const createAlert = async (event) => {
    event.preventDefault();
    setBusy('alert');
    setError('');
    try {
      await customerExperienceRequest('/alerts', {
        method: 'POST',
        body: {
          ...alertDraft,
          threshold: Number(alertDraft.threshold),
          evaluation_interval_minutes: Number(alertDraft.evaluation_interval_minutes),
          channels: ['in_app', 'email'],
          recipients: user?.email ? [user.email] : [],
          organization_id: primaryOrganization?.id || null,
        },
      });
      setAlertDraft((current) => ({ ...current, name: '' }));
      flash(copy(isEn, 'Smart alert created.', 'สร้าง Smart Alert แล้ว'));
      await loadOverview();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const evaluateAlert = async (ruleId) => {
    setBusy(`alert:${ruleId}`);
    setError('');
    try {
      const payload = await customerExperienceRequest(`/alerts/${ruleId}/evaluate`, {
        method: 'POST',
      });
      const status = payload.evaluation?.status || 'completed';
      flash(copy(isEn, `Alert evaluation: ${status}`, `ประเมิน Alert แล้ว: ${status}`));
      await loadOverview();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const toggleAlert = async (alert) => {
    setBusy(`alert-toggle:${alert.id}`);
    setError('');
    try {
      await customerExperienceRequest(`/alerts/${alert.id}`, {
        method: 'PATCH',
        body: { enabled: !alert.enabled },
      });
      flash(alert.enabled
        ? copy(isEn, 'Alert turned off.', 'ปิด Alert แล้ว')
        : copy(isEn, 'Alert turned on.', 'เปิด Alert แล้ว'));
      await loadOverview();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const resolveCollaboration = async (itemId) => {
    setBusy(`collab:${itemId}`);
    setError('');
    try {
      await customerExperienceRequest(`/collaboration/${itemId}`, {
        method: 'PATCH',
        body: { status: 'resolved' },
      });
      flash(copy(isEn, 'Marked as resolved.', 'ปิดงานร่วมแล้ว'));
      await loadOverview();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const saveIntegration = async (kind, provider, displayName) => {
    setBusy(`integration-${provider}`);
    setError('');
    try {
      await customerExperienceRequest('/integrations', {
        method: 'PUT',
        body: {
          organization_id: primaryOrganization?.id || null,
          integration_kind: kind,
          provider,
          display_name: displayName,
          status: 'draft',
          enabled: false,
          configuration: { setup_required: true },
        },
      });
      flash(
        copy(
          isEn,
          `${displayName} draft created. Credentials stay in server secret storage.`,
          `สร้างฉบับร่าง ${displayName} แล้ว Credential เก็บฝั่งเซิร์ฟเวอร์เท่านั้น`,
        ),
      );
      await loadOverview();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const createInvitation = async (event) => {
    event.preventDefault();
    if (!primaryOrganization?.id) return;
    setBusy('invite');
    setError('');
    try {
      const result = await customerExperienceRequest('/organization-invitations', {
        method: 'POST',
        body: {
          organization_id: primaryOrganization.id,
          email: inviteDraft.email,
          role: inviteDraft.role,
          expires_in_days: 7,
        },
      });
      const localizedPath = buildCustomerCenterPath(routing);
      setInviteLink(
        `${window.location.origin}${localizedPath}?invite=${encodeURIComponent(result.token)}`,
      );
      setInviteDraft((current) => ({ ...current, email: '' }));
      flash(copy(isEn, 'Secure invitation created.', 'สร้างคำเชิญแบบปลอดภัยแล้ว'));
      await loadOverview();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const logout = async () => {
    if (user?.id) fileManagerCache.clearUser(user.id);
    fileManagerCache.clearAuthUser();
    await supabase.auth.signOut();
    router.replace(localePath('/login', routing));
  };

  const stats = [
    [copy(isEn, 'Healthy sources', 'แหล่งข้อมูลปกติ'), overview.summary?.healthy_assets || 0, Database],
    [copy(isEn, 'Source issues', 'แหล่งข้อมูลมีปัญหา'), overview.summary?.asset_issues || 0, CircleAlert],
    [copy(isEn, 'Enabled alerts', 'Alert ที่เปิด'), overview.summary?.enabled_alerts || 0, AlertTriangle],
    [copy(isEn, 'Open collaboration', 'งานร่วมที่ยังเปิด'), overview.summary?.open_collaboration || 0, MessageCircle],
  ];

  return (
    <div className="app-shell icon-motion-scope relative flex h-[100svh] overflow-hidden bg-slate-50 text-slate-700 dark:bg-zinc-950 dark:text-zinc-300">
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/20 dark:bg-black/60 backdrop-blur-sm z-50 md:hidden"
          onClick={() => setIsOpen(false)}
        />
      )}

      <DashboardSidebar
        isOpen={isOpen}
        setIsOpen={setIsOpen}
        user={user}
        plan={plan}
        routing={routing}
        isEn={isEn}
        onLogout={logout}
      />

      <main className="app-main-scroll min-w-0 flex-1 overflow-y-auto p-5 md:p-8">
        <div className="app-page-frame mx-auto w-full max-w-[1180px] space-y-6">
          <header className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <div className="app-page-kicker mb-3">{copy(isEn, 'CUSTOMER CENTER', 'ศูนย์ดูแลลูกค้า')}</div>
              <h1 className="text-xl font-semibold tracking-tight text-slate-900 dark:text-white">
                {copy(isEn, 'Customer Center', 'ศูนย์ดูแลลูกค้า')}
              </h1>
              <p className="mt-1 max-w-2xl text-sm text-slate-500 dark:text-slate-400">
                {copy(
                  isEn,
                  'Track source health, lineage, alerts, and organization delivery from one workspace.',
                  'ติดตามสุขภาพแหล่งข้อมูล Lineage Alert และการทำงานขององค์กรในที่เดียว',
                )}
              </p>
            </div>
            <button
              type="button"
              onClick={loadOverview}
              disabled={loading}
              className="inline-flex self-start items-center gap-2 rounded-[0.75rem] border border-slate-200 dark:border-white/12 px-3.5 py-2 text-sm font-semibold hover:bg-white dark:hover:bg-zinc-900 disabled:opacity-50"
            >
              <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
              {copy(isEn, 'Refresh health', 'ตรวจสถานะใหม่')}
            </button>
          </header>

          {error && (
            <div className="flex items-start justify-between gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/20 dark:text-red-300">
              <p>{error}</p>
              <button type="button" onClick={() => setError('')} className="shrink-0 p-0.5" aria-label={copy(isEn, 'Dismiss', 'ปิด')}>
                <X className="h-4 w-4" />
              </button>
            </div>
          )}
          {notice && (
            <div className="flex items-start justify-between gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-300">
              <p>{notice}</p>
              <button type="button" onClick={() => setNotice('')} className="shrink-0 p-0.5" aria-label={copy(isEn, 'Dismiss', 'ปิด')}>
                <X className="h-4 w-4" />
              </button>
            </div>
          )}

          <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {stats.map(([label, value, Icon]) => (
              <div key={label} className="enterprise-panel p-5">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-50 text-[#d97706] dark:bg-amber-500/10">
                  <Icon size={18} strokeWidth={1.6} />
                </div>
                <p className="mt-3 text-[11px] font-medium uppercase tracking-wider text-slate-500">{label}</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900 dark:text-white">{loading ? '—' : value}</p>
              </div>
            ))}
          </section>

          <section className="grid gap-5 lg:grid-cols-2">
            <div className="enterprise-panel p-5">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-slate-900 dark:text-white">{copy(isEn, 'Data Health Center', 'ศูนย์ตรวจสุขภาพข้อมูล')}</h2>
                  <p className="mt-1 text-xs text-slate-500">{copy(isEn, 'Freshness, quality, failures and schema drift.', 'ความสด คุณภาพ ความล้มเหลว และ Schema drift')}</p>
                </div>
                <Database size={18} className="text-[#d97706]" />
              </div>
              <div className="mt-4 space-y-2">
                {overview.data_assets?.length ? overview.data_assets.slice(0, 6).map((asset) => (
                  <div key={asset.id || `${asset.asset_kind}-${asset.asset_key}`} className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 p-3 text-sm dark:border-white/10">
                    <div className="min-w-0">
                      <p className="truncate font-medium text-slate-900 dark:text-white">{asset.display_name}</p>
                      <p className="text-xs text-slate-500">{asset.asset_kind} · {asset.freshness_status}</p>
                    </div>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${statusClass(asset.connection_status)}`}>{asset.connection_status}</span>
                  </div>
                )) : (
                  <p className="rounded-xl border border-dashed border-slate-200 p-5 text-center text-sm text-slate-500 dark:border-white/12">
                    {copy(isEn, 'Health records appear after a source is connected or refreshed.', 'สถานะสุขภาพจะแสดงหลังเชื่อมหรือ Refresh แหล่งข้อมูล')}
                  </p>
                )}
              </div>
            </div>

            <div className="enterprise-panel p-5">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-slate-900 dark:text-white">{copy(isEn, 'Explain this number', 'อธิบายที่มาของตัวเลข')}</h2>
                  <p className="mt-1 text-xs text-slate-500">{copy(isEn, 'Formula, source, filters, data version and confidence.', 'สูตร แหล่งข้อมูล Filter เวอร์ชันข้อมูล และ Confidence')}</p>
                </div>
                <Link2 size={18} className="text-[#d97706]" />
              </div>
              <div className="mt-4 space-y-2">
                {overview.lineage?.length ? overview.lineage.slice(0, 5).map((item) => (
                  <div key={item.id} className="rounded-xl border border-slate-100 p-3 dark:border-white/10">
                    <div className="flex justify-between gap-3">
                      <p className="font-medium text-slate-900 dark:text-white">{item.metric_key || item.dataset_key}</p>
                      <span className="text-xs tabular-nums text-slate-500">{Math.round(Number(item.confidence || 0) * 100)}%</span>
                    </div>
                    <p className="mt-1 truncate text-xs text-slate-500">{item.formula || item.executed_sql || item.data_version || 'Verified compute record'}</p>
                  </div>
                )) : (
                  <p className="rounded-xl border border-dashed border-slate-200 p-5 text-center text-sm text-slate-500 dark:border-white/12">
                    {copy(isEn, 'Lineage appears when a verified finding or dashboard metric is saved.', 'Lineage จะแสดงเมื่อบันทึก Finding หรือ Metric ที่ตรวจสอบแล้ว')}
                  </p>
                )}
              </div>
            </div>
          </section>

          <section className="enterprise-panel p-5">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-slate-900 dark:text-white">{copy(isEn, 'Open collaboration', 'งานร่วมที่ยังเปิด')}</h2>
                <p className="mt-1 text-xs text-slate-500">{copy(isEn, 'Comments, assignments, and approvals on saved dashboards.', 'ความคิดเห็น งานที่มอบหมาย และการอนุมัติบน Dashboard ที่บันทึก')}</p>
              </div>
              <MessageCircle size={18} className="text-[#d97706]" />
            </div>
            <div className="mt-4 space-y-2">
              {openCollaboration.length ? openCollaboration.slice(0, 6).map((item) => (
                <div key={item.id} className="flex items-start justify-between gap-3 rounded-xl border border-slate-100 p-3 text-sm dark:border-white/10">
                  <div className="min-w-0">
                    <p className="font-medium text-slate-900 dark:text-white">{item.item_kind}</p>
                    <p className="mt-0.5 truncate text-xs text-slate-500">{item.body || '—'}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => resolveCollaboration(item.id)}
                    disabled={busy === `collab:${item.id}`}
                    className="shrink-0 rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-semibold dark:border-white/12"
                  >
                    {copy(isEn, 'Resolve', 'ปิดงาน')}
                  </button>
                </div>
              )) : (
                <p className="rounded-xl border border-dashed border-slate-200 p-5 text-center text-sm text-slate-500 dark:border-white/12">
                  {copy(isEn, 'No open collaboration items.', 'ยังไม่มีงานร่วมที่เปิดอยู่')}
                </p>
              )}
            </div>
          </section>

          <section className={`grid gap-5 ${hasOrganizationFeatures ? 'lg:grid-cols-2' : ''}`}>
            <form onSubmit={createAlert} className="enterprise-panel p-5">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-slate-900 dark:text-white">{copy(isEn, 'Create smart alert', 'สร้าง Smart Alert')}</h2>
                  <p className="mt-1 text-xs text-slate-500">{copy(isEn, 'In-app and email with cooldown by default.', 'แจ้งในแอปและอีเมล พร้อม Cooldown')}</p>
                </div>
                <AlertTriangle size={18} className="text-[#d97706]" />
              </div>

              {hasReports ? (
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <input aria-label={copy(isEn, 'Alert name', 'ชื่อ Alert')} className={`${inputClass} sm:col-span-2`} placeholder={copy(isEn, 'Revenue changed materially', 'ยอดขายเปลี่ยนมาก')} value={alertDraft.name} onChange={(event) => setAlertDraft({ ...alertDraft, name: event.target.value })} required />
                  <select aria-label={copy(isEn, 'Dashboard source', 'Dashboard ต้นทาง')} className={`${inputClass} sm:col-span-2`} value={alertDraft.report_id} onChange={(event) => {
                    const reportId = event.target.value;
                    const report = overview.available_reports?.find((item) => item.id === reportId);
                    const firstKpi = report?.dashboard_spec?.kpis?.[0];
                    setAlertDraft({
                      ...alertDraft,
                      report_id: reportId,
                      metric_key: firstKpi?.field || firstKpi?.label || '',
                    });
                  }} required>
                    <option value="">{copy(isEn, 'Select a verified dashboard', 'เลือก Dashboard ที่ตรวจสอบแล้ว')}</option>
                    {overview.available_reports?.map((report) => (
                      <option key={report.id} value={report.id}>{report.title}</option>
                    ))}
                  </select>
                  <select aria-label={copy(isEn, 'Metric key', 'Metric key')} className={inputClass} value={alertDraft.metric_key} onChange={(event) => setAlertDraft({ ...alertDraft, metric_key: event.target.value })} required>
                    <option value="">{copy(isEn, 'Select KPI', 'เลือก KPI')}</option>
                    {alertMetricOptions.map((metric) => <option key={metric} value={metric}>{metric}</option>)}
                  </select>
                  <select aria-label={copy(isEn, 'Comparison operator', 'เงื่อนไขเปรียบเทียบ')} className={inputClass} value={alertDraft.operator} onChange={(event) => setAlertDraft({ ...alertDraft, operator: event.target.value })}>
                    <option value="gt">&gt;</option>
                    <option value="gte">≥</option>
                    <option value="lt">&lt;</option>
                    <option value="lte">≤</option>
                    <option value="eq">=</option>
                    <option value="change_gt">{copy(isEn, 'Absolute change % >', 'เปลี่ยนแปลงสัมบูรณ์ % >')}</option>
                    <option value="change_lt">{copy(isEn, 'Decrease % >', 'ลดลง % >')}</option>
                  </select>
                  <input aria-label={copy(isEn, 'Threshold', 'เกณฑ์')} className={inputClass} type="number" value={alertDraft.threshold} onChange={(event) => setAlertDraft({ ...alertDraft, threshold: event.target.value })} required />
                  <input aria-label={copy(isEn, 'Evaluation interval minutes', 'รอบประเมิน (นาที)')} className={inputClass} type="number" min="1" max="1440" value={alertDraft.evaluation_interval_minutes} onChange={(event) => setAlertDraft({ ...alertDraft, evaluation_interval_minutes: event.target.value })} required />
                </div>
              ) : (
                <div className="mt-4 rounded-xl border border-dashed border-slate-200 p-5 text-center dark:border-white/12">
                  <p className="text-sm text-slate-500">{copy(isEn, 'Save a verified dashboard first, then create an alert from its KPIs.', 'บันทึก Dashboard ที่ตรวจสอบแล้วก่อน จากนั้นค่อยสร้าง Alert จาก KPI')}</p>
                  <button type="button" onClick={() => router.push(buildVisualizationPath(routing))} className="btn-primary mt-3 inline-flex items-center gap-2 px-3 py-2 text-xs">
                    {copy(isEn, 'Build dashboard', 'สร้าง Dashboard')} <ArrowRight size={14} />
                  </button>
                </div>
              )}

              {hasReports && (
                <button disabled={busy === 'alert'} className="btn-primary mt-4 inline-flex items-center gap-2 px-4 py-2 text-sm">
                  {busy === 'alert' ? <LoaderCircle size={15} className="animate-spin" /> : <Plus size={15} />}
                  {copy(isEn, 'Create alert', 'สร้าง Alert')}
                </button>
              )}

              <div className="mt-4 space-y-2">
                {overview.alerts?.slice(0, 4).map((alert) => (
                  <div key={alert.id} className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 p-3 text-sm dark:border-white/10">
                    <div className="min-w-0">
                      <p className="truncate font-medium">{alert.name}</p>
                      <p className="mt-0.5 text-xs text-slate-500">{alert.last_status || 'idle'}</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <button type="button" onClick={() => evaluateAlert(alert.id)} disabled={busy === `alert:${alert.id}` || !alert.enabled} className="rounded-lg border border-slate-200 px-2 py-1 text-xs font-medium disabled:opacity-50 dark:border-white/12">
                        {busy === `alert:${alert.id}` ? '…' : copy(isEn, 'Test', 'ทดสอบ')}
                      </button>
                      <button
                        type="button"
                        onClick={() => toggleAlert(alert)}
                        disabled={busy === `alert-toggle:${alert.id}`}
                        className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${alert.enabled ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' : 'bg-slate-100 text-slate-500 dark:bg-zinc-800'}`}
                      >
                        {alert.enabled ? 'ON' : 'OFF'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-5 border-t border-slate-100 pt-4 dark:border-white/10">
                <p className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
                  {copy(isEn, 'Recent in-app events', 'เหตุการณ์ล่าสุดในแอป')}
                </p>
                <div className="mt-2 space-y-2">
                  {overview.alert_events?.slice(0, 4).map((event) => {
                    const rule = overview.alerts?.find((item) => item.id === event.rule_id);
                    return (
                      <div key={event.id} className="rounded-xl bg-slate-50 px-3 py-2 text-xs dark:bg-zinc-950">
                        <div className="flex items-center justify-between gap-3">
                          <span className="font-medium text-slate-800 dark:text-zinc-100">{rule?.name || event.rule_id}</span>
                          <span className={event.status === 'delivered' ? 'text-emerald-600' : event.status === 'failed' ? 'text-red-600' : 'text-amber-600'}>{event.status}</span>
                        </div>
                        <p className="mt-1 text-slate-500">{event.metric_value ?? '—'} · {event.reason || 'threshold matched'}</p>
                      </div>
                    );
                  })}
                  {!overview.alert_events?.length && <p className="text-xs text-slate-500">{copy(isEn, 'No alert events yet.', 'ยังไม่มีเหตุการณ์ Alert')}</p>}
                </div>
              </div>
            </form>

            {hasOrganizationFeatures && (
              <div className="enterprise-panel p-5">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-sm font-semibold text-slate-900 dark:text-white">{copy(isEn, 'Organization Center', 'ศูนย์จัดการองค์กร')}</h2>
                    <p className="mt-1 text-xs text-slate-500">{primaryOrganization?.name || copy(isEn, 'Personal workspace', 'พื้นที่ส่วนตัว')}</p>
                  </div>
                  <Building2 size={18} className="text-[#d97706]" />
                </div>
                {primaryOrganization?.id ? (
                  <form onSubmit={createInvitation} className="mt-4 space-y-3">
                    <input aria-label={copy(isEn, 'Invite email', 'อีเมลผู้รับคำเชิญ')} type="email" className={inputClass} placeholder="teammate@company.com" value={inviteDraft.email} onChange={(event) => setInviteDraft({ ...inviteDraft, email: event.target.value })} required />
                    <div className="flex gap-2">
                      <select aria-label={copy(isEn, 'Organization role', 'Role ในองค์กร')} className={inputClass} value={inviteDraft.role} onChange={(event) => setInviteDraft({ ...inviteDraft, role: event.target.value })}>
                        <option value="member">{copy(isEn, 'Member', 'สมาชิก')}</option>
                        <option value="reviewer">{copy(isEn, 'Reviewer', 'ผู้ตรวจสอบ')}</option>
                        <option value="admin">{copy(isEn, 'Admin', 'ผู้ดูแลระบบ')}</option>
                      </select>
                      <button disabled={busy === 'invite'} className="btn-primary shrink-0 px-4 py-2 text-sm">{copy(isEn, 'Invite', 'เชิญ')}</button>
                    </div>
                    <p className="text-xs text-slate-500">{copy(isEn, 'Invitation tokens are hashed, expire in 7 days and remain subject to paid seat limits.', 'Token คำเชิญถูก Hash หมดอายุใน 7 วัน และยังถูกจำกัดตาม Seat ที่ชำระ')}</p>
                    {inviteLink && (
                      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 dark:border-emerald-900/50 dark:bg-emerald-950/20">
                        <p className="text-xs font-semibold text-emerald-800 dark:text-emerald-300">{copy(isEn, 'Copy this one-time invitation link', 'คัดลอกลิงก์คำเชิญนี้')}</p>
                        <div className="mt-2 flex gap-2">
                          <input readOnly aria-label={copy(isEn, 'Invitation link', 'ลิงก์คำเชิญ')} className={inputClass} value={inviteLink} />
                          <button type="button" onClick={() => navigator.clipboard.writeText(inviteLink)} className="rounded-lg border border-emerald-300 px-3 text-xs font-semibold text-emerald-800 dark:border-emerald-800 dark:text-emerald-300">{copy(isEn, 'Copy', 'คัดลอก')}</button>
                        </div>
                      </div>
                    )}
                    <div className="space-y-2 pt-2">
                      {(overview.invitations || []).slice(0, 5).map((invite) => (
                        <div key={invite.id} className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 px-3 py-2 text-xs dark:border-white/10">
                          <span className="truncate text-slate-700 dark:text-slate-200">{invite.email} · {invite.role}</span>
                          <span className={`rounded-full px-2 py-0.5 font-semibold ${statusClass(invite.status)}`}>{invite.status}</span>
                        </div>
                      ))}
                    </div>
                  </form>
                ) : (
                  <button onClick={() => router.push(buildSettingsPath(routing))} className="mt-4 inline-flex items-center gap-2 rounded-[0.75rem] border border-slate-200 px-3 py-2 text-sm font-medium dark:border-white/12">
                    {copy(isEn, 'Open organization settings', 'เปิดการตั้งค่าองค์กร')} <ArrowRight size={14} />
                  </button>
                )}
              </div>
            )}
          </section>

          {hasOrganizationFeatures && (
            <section className="enterprise-panel p-5">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-slate-900 dark:text-white">{copy(isEn, 'Enterprise integrations', 'Enterprise Integrations')}</h2>
                  <p className="mt-1 text-xs text-slate-500">{copy(isEn, 'Creates a draft setup contract only. Secrets stay on the server and are not connected yet.', 'สร้างฉบับร่างการตั้งค่าเท่านั้น Secret อยู่ฝั่งเซิร์ฟเวอร์ และยังไม่ได้เชื่อมจริง')}</p>
                </div>
                <span className="text-xs text-slate-500">{overview.summary?.active_integrations || 0} {copy(isEn, 'active', 'เปิดใช้งาน')}</span>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {[
                  ['notification', 'slack', 'Slack'],
                  ['notification', 'teams', 'Microsoft Teams'],
                  ['sso', 'saml', 'SAML SSO'],
                  ['scim', 'scim', 'SCIM provisioning'],
                ].map(([kind, provider, label]) => {
                  const existing = (overview.integrations || []).find((item) => item.provider === provider);
                  return (
                    <button
                      key={`${kind}-${provider}`}
                      type="button"
                      onClick={() => saveIntegration(kind, provider, label)}
                      disabled={busy === `integration-${provider}`}
                      className="rounded-xl border border-slate-200 p-4 text-left transition hover:border-amber-300 hover:bg-amber-50/30 disabled:opacity-50 dark:border-white/12 dark:hover:bg-amber-950/10"
                    >
                      <div className="flex items-center justify-between">
                        <Network size={17} className="text-[#d97706]" />
                        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500 dark:bg-zinc-800">
                          {existing?.status || 'draft'}
                        </span>
                      </div>
                      <p className="mt-3 text-sm font-semibold text-slate-900 dark:text-white">{label}</p>
                      <p className="mt-1 text-xs text-slate-500">{copy(isEn, 'Create draft contract', 'สร้างฉบับร่าง')}</p>
                    </button>
                  );
                })}
              </div>
            </section>
          )}

          <div className="trust-banner">
            <Shield size={14} className="text-slate-500 dark:text-slate-400 shrink-0" />
            <span>
              {copy(
                isEn,
                'Customer workflows are enforced by authenticated backend APIs and owner/organization checks.',
                'Workflow ลูกค้าถูกบังคับผ่าน Backend API ที่ตรวจตัวตนและสิทธิ์เจ้าของ/องค์กร',
              )}
            </span>
          </div>
        </div>
      </main>
    </div>
  );
};

export default CustomerCenter;
