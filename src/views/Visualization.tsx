// @ts-nocheck
'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowRight,
  BarChart3,
  Check,
  Copy,
  ChevronDown,
  FilePlus2,
  LayoutDashboard,
  Loader2,
  LockKeyhole,
  MessageSquareText,
  PencilLine,
  Pin,
  RefreshCw,
  Trash2,
  X,
} from '@/components/icons';
import ChartRenderer from '../components/ChartRenderer';
import AdaptiveBiDashboard from '../components/AdaptiveBiDashboard';
import VisualizationDeliveryPanel from '../components/VisualizationDeliveryPanel';
import MappingRoleSelect from '../components/MappingRoleSelect';
import Chat from './Chat';
import { DeleteConfirmationModal } from '../components/ChatModals';
import DashboardSidebar from '../components/DashboardSidebar';
import { useAppSidebar } from '../context/AppSidebarContext';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { supabase } from '../utils/supabaseClient.js';
import {
  buildChatPath,
  buildVisualizationPath,
  isUuid,
} from '../utils/dashboardRoutes.js';
import { localePath } from '../utils/locale.js';
import { getE2eMockUser } from '../utils/e2eAuth.js';
import { getMessages } from '../utils/i18n.js';
import { visualizationRequest } from '../utils/visualizationApi.js';
import { fetchFilePage } from '../utils/fileListApi.js';
import { authFetch } from '../utils/authFetch.js';
import { getPublicApiUrl } from '../utils/env.js';
import { buildMappingOptionGroups, SEMANTIC_ROLE_VALUES } from '../features/chat/columnMappingOptions.js';
import {
  clampVisualizationChatWidth,
  visualizationChatWidthFromKey,
  visualizationChatWidthFromPointer,
} from '../features/visualization/visualizationWorkspace.js';
import { packetLifecycleLabel } from '../features/visualization/decisionPacket.js';

const formatDate = (value, isEn) => {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat(isEn ? 'en-GB' : 'th-TH', {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  } catch {
    return value;
  }
};

const MANUAL_CLEANING_RECIPE = `{
  "trim_strings": true,
  "drop_duplicates": false,
  "drop_empty_rows": true
}`;

const WorkspaceSelect = ({ value, onChange, options, placeholder }) => {
  const [open, setOpen] = useState(false);
  const selected = options.find((option) => option.value === value);
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className={`flex w-full items-center justify-between gap-2 rounded-xl border bg-white px-3 py-2 text-sm font-normal text-stone-700 outline-none transition-colors dark:bg-zinc-950 dark:text-stone-200 ${open ? 'border-amber-500 ring-2 ring-amber-500/15' : 'border-stone-200 hover:border-stone-300 dark:border-stone-700 dark:hover:border-stone-600'}`}
      >
        <span className="truncate">{selected?.label || placeholder}</span>
        <ChevronDown size={15} className={`shrink-0 text-stone-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <>
          <button type="button" aria-label="Close options" className="fixed inset-0 z-40 cursor-default" onClick={() => setOpen(false)} />
          <div className="absolute left-0 right-0 top-[calc(100%+6px)] z-50 max-h-60 overflow-y-auto rounded-xl border border-stone-200 bg-white p-1.5 shadow-[0_18px_48px_rgba(15,23,42,0.16)] dark:border-stone-800 dark:bg-zinc-950">
            {options.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => { onChange(option.value); setOpen(false); }}
                className={`w-full rounded-lg px-3 py-2 text-left text-sm transition-colors ${option.value === value ? 'bg-amber-50 font-semibold text-amber-800 dark:bg-amber-950/35 dark:text-amber-300' : 'text-stone-600 hover:bg-stone-50 hover:text-stone-900 dark:text-stone-300 dark:hover:bg-zinc-900 dark:hover:text-white'}`}
              >
                <span className="block truncate">{option.label}</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
};

const Visualization = () => {
  const router = useRouter();
  const params = useParams();
  const routing = useLocaleRouting();
  const isEn = routing.locale === 'en';
  const { isOpen, setIsOpen } = useAppSidebar();
  const routeReportId = Array.isArray(params?.reportId) ? params.reportId[0] : params?.reportId;
  const messages = useMemo(() => getMessages(isEn ? 'en' : 'th'), [isEn]);
  const mappingOptionGroups = useMemo(() => buildMappingOptionGroups(messages), [messages]);

  const [user, setUser] = useState(null);
  const [plan, setPlan] = useState({ name: 'Free' });
  const [reports, setReports] = useState([]);
  const [selectedId, setSelectedId] = useState(isUuid(routeReportId) ? routeReportId : null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState('');
  const [draftSummary, setDraftSummary] = useState('');
  const [dashboards, setDashboards] = useState({});
  const [dashboardBusy, setDashboardBusy] = useState(false);
  const [dashboardDirty, setDashboardDirty] = useState(false);
  const [reportLibraryOpen, setReportLibraryOpen] = useState(false);
  const [manualBuilderOpen, setManualBuilderOpen] = useState(false);
  const [manualFiles, setManualFiles] = useState([]);
  const [manualConnections, setManualConnections] = useState({ database: [], api: [], cloud: [] });
  const [manualSourcesLoaded, setManualSourcesLoaded] = useState(false);
  const [manualFilesLoading, setManualFilesLoading] = useState(false);
  const [manualScan, setManualScan] = useState(null);
  const [manualDraft, setManualDraft] = useState({
    title: '',
    fileName: '',
    columnMapping: {},
    cleaningProfile: 'standard',
    cleaningRecipe: MANUAL_CLEANING_RECIPE,
    sourceType: 'file',
    connectionId: '',
    connectionName: '',
    sqlTable: '',
  });
  const [chatOpen, setChatOpen] = useState(() => (
    typeof window === 'undefined' ? true : window.localStorage.getItem('visualization_chat_open') !== 'false'
  ));
  const [chatWidth, setChatWidth] = useState(() => {
    if (typeof window === 'undefined') return 420;
    const stored = window.localStorage.getItem('visualization_chat_width');
    const saved = stored === null ? Number.NaN : Number(stored);
    return clampVisualizationChatWidth(saved);
  });
  const [chatBusy, setChatBusy] = useState(false);
  const [askWhyPreset, setAskWhyPreset] = useState(null);
  const [proveDiff, setProveDiff] = useState([]);
  const [pendingConversationId, setPendingConversationId] = useState(null);
  const [dashboardContext, setDashboardContext] = useState({ widgetId: null, filters: {} });
  const [dashboardPreview, setDashboardPreview] = useState(null);
  const dashboardRequestRef = useRef(0);
  const dashboardAbortRef = useRef(null);
  const dashboardFilterTimerRef = useRef(null);
  const selectedReportRef = useRef(null);
  const [deleteModal, setDeleteModal] = useState({
    show: false,
    type: null,
    id: null,
  });

  const selected = useMemo(
    () => reports.find((report) => report.id === selectedId) || null,
    [reports, selectedId],
  );
  useEffect(() => {
    selectedReportRef.current = selected;
  }, [selected]);
  const selectedDashboard = selected?.id ? dashboards[selected.id] : null;
  const focusedWidget = useMemo(() => (
    (selectedDashboard?.spec?.widgets || selected?.dashboard_spec?.widgets || [])
      .find((widget) => widget.id === dashboardContext.widgetId) || null
  ), [dashboardContext.widgetId, selected?.dashboard_spec?.widgets, selectedDashboard?.spec?.widgets]);
  const visualizationChatContext = useMemo(() => selected ? ({
    reportId: selected.id,
    reportTitle: selected.title,
    widgetId: dashboardContext.widgetId,
    widgetTitle: focusedWidget?.title || null,
    filters: dashboardContext.filters,
    sourceConfig: selected.source_config || {},
  }) : null, [dashboardContext, focusedWidget?.title, selected]);
  const chartCount = useMemo(
    () => reports.reduce(
      (total, report) => total
        + (report.charts?.length || 0)
        + (report.dashboard_spec?.widgets || []).filter((widget) => widget.kind === 'chart').length,
      0,
    ),
    [reports],
  );

  const loadReports = useCallback(async ({ quiet = false } = {}) => {
    if (!quiet) setLoading(true);
    setError('');
    try {
      const payload = await visualizationRequest('/reports', { method: 'GET' });
      const nextReports = payload.reports || [];
      setReports(nextReports);
      const requested = isUuid(routeReportId) ? routeReportId : nextReports[0]?.id;
      const nextSelected = nextReports.some((item) => item.id === requested)
        ? requested
        : nextReports[0]?.id || null;
      setSelectedId(nextSelected);
      if (routeReportId && !nextReports.some((item) => item.id === routeReportId)) {
        router.replace(buildVisualizationPath(routing, nextSelected));
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [routeReportId, router, routing]);

  useEffect(() => {
    let cancelled = false;
    const initialize = async () => {
      const mockUser = getE2eMockUser();
      const authUser = mockUser || (await supabase.auth.getUser()).data.user;
      if (!authUser) {
        router.replace(localePath('/login', routing));
        return;
      }
      if (cancelled) return;
      setUser(authUser);
      if (!mockUser) {
        const { data: profile } = await supabase
          .from('profiles')
          .select('plans(name)')
          .eq('id', authUser.id)
          .maybeSingle();
        const profilePlan = Array.isArray(profile?.plans) ? profile.plans[0] : profile?.plans;
        if (profilePlan?.name) setPlan(profilePlan);
      }
    };
    initialize();
    return () => {
      cancelled = true;
    };
  }, [router, routing]);

  useEffect(() => {
    if (user?.id) loadReports();
  }, [user?.id, loadReports]);

  useEffect(() => {
    if (isUuid(routeReportId)) setSelectedId(routeReportId);
  }, [routeReportId]);

  useEffect(() => {
    setEditing(false);
    setDraftTitle(selected?.title || '');
    setDraftSummary(selected?.executive_summary || '');
  }, [selected?.id, selected?.title, selected?.executive_summary]);

  useEffect(() => {
    const currentReport = selectedReportRef.current;
    setDashboardContext({
      widgetId: null,
      filters: currentReport?.filter_state || {},
    });
    setDashboardPreview(null);
    setPendingConversationId(null);
  }, [selected?.id]);

  useEffect(() => {
    window.localStorage.setItem('visualization_chat_open', String(chatOpen));
    if (chatOpen && window.matchMedia('(min-width: 1280px)').matches && isOpen) {
      setIsOpen(false);
    }
  }, [chatOpen, isOpen, setIsOpen]);

  useEffect(() => {
    window.localStorage.setItem('visualization_chat_width', String(chatWidth));
  }, [chatWidth]);

  const generateDashboard = useCallback(async (
    force = false,
    filters = {},
    dashboardSpec = null,
    persist = true,
    quiet = false,
  ) => {
    if (!selected?.id || !user?.id) return;
    dashboardAbortRef.current?.abort();
    const controller = new AbortController();
    dashboardAbortRef.current = controller;
    const requestId = dashboardRequestRef.current + 1;
    dashboardRequestRef.current = requestId;
    setDashboardBusy(!quiet);
    setError('');
    try {
      const payload = await visualizationRequest('/dashboard/generate', {
        body: {
          user_id: user.id,
          report_id: selected.id,
          force,
          filters,
          dashboard_spec: dashboardSpec,
          persist,
        },
        signal: controller.signal,
      });
      if (requestId !== dashboardRequestRef.current) return payload.dashboard;
      setDashboards((current) => ({
        ...current,
        [selected.id]: payload.dashboard,
      }));
      if (persist) {
        setReports((current) => current.map((report) => (
          report.id === selected.id
            ? {
                ...report,
                dashboard_spec: payload.dashboard.spec,
                filter_state: payload.dashboard.applied_filters || filters,
                updated_at: new Date().toISOString(),
              }
            : report
        )));
      }
      return payload.dashboard;
    } catch (err) {
      if (err?.name === 'AbortError') return null;
      if (requestId === dashboardRequestRef.current) setError(err.message);
      return null;
    } finally {
      if (!quiet && requestId === dashboardRequestRef.current) setDashboardBusy(false);
    }
  }, [selected, user]);

  const scheduleDashboardFilters = useCallback((filters, dashboardSpec) => {
    if (dashboardFilterTimerRef.current) {
      window.clearTimeout(dashboardFilterTimerRef.current);
    }
    dashboardAbortRef.current?.abort();
    dashboardFilterTimerRef.current = window.setTimeout(() => {
      generateDashboard(false, filters, dashboardSpec, true, true);
    }, 300);
  }, [generateDashboard]);

  useEffect(() => () => {
    if (dashboardFilterTimerRef.current) window.clearTimeout(dashboardFilterTimerRef.current);
    dashboardAbortRef.current?.abort();
  }, []);

  useEffect(() => {
    if (selected?.id && user?.id && !dashboards[selected.id]) {
      generateDashboard(false, selected.filter_state || {});
    }
  }, [dashboards, generateDashboard, selected?.filter_state, selected?.id, user?.id]);

  const selectReport = (reportId) => {
    if (chatBusy) return;
    if (dashboardDirty && !window.confirm(isEn ? 'Leave with unsaved dashboard changes?' : 'ออกจากรายงานโดยยังไม่ได้บันทึก Dashboard หรือไม่?')) return;
    setSelectedId(reportId);
    setReportLibraryOpen(false);
    router.push(buildVisualizationPath(routing, reportId));
  };

  const openManualBuilder = async () => {
    setError('');
    setManualBuilderOpen(true);
    if (manualSourcesLoaded) return;
    setManualFilesLoading(true);
    try {
      const [page, connectionsResponse, cloudResponse] = await Promise.all([
        fetchFilePage({ limit: 100 }),
        authFetch(`${getPublicApiUrl()}/api/v1/connections`, { method: 'GET' }),
        authFetch(`${getPublicApiUrl()}/api/v1/cloud-datasets`, { method: 'GET' }),
      ]);
      const [connectionPayload, cloudPayload] = await Promise.all([
        connectionsResponse.json().catch(() => ({})),
        cloudResponse.json().catch(() => ({})),
      ]);
      if (!connectionsResponse.ok) throw new Error(connectionPayload.detail || 'Could not load database and API connections');
      if (!cloudResponse.ok) throw new Error(cloudPayload.detail || 'Could not load cloud files');
      setManualFiles(page.files || []);
      setManualConnections({
        database: connectionPayload.database_connections || [],
        api: connectionPayload.api_connections || [],
        cloud: cloudPayload.connections || [],
      });
      setManualSourcesLoaded(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setManualFilesLoading(false);
    }
  };

  const scanManualSource = async (source = {}) => {
    if (!user?.id || !source.sourceType) return;
    setBusy('manual-scan');
    setError('');
    setManualScan(null);
    try {
      const payload = await visualizationRequest('/manual-source/scan', {
        body: {
          user_id: user.id,
          source_type: source.sourceType,
          file_name: source.fileName || null,
          connection_id: source.connectionId || null,
          table_name: source.sqlTable || null,
          original_prompt: '',
          sample_rows: [],
          reuse_existing: true,
        },
      });
      const scan = payload.scan || {};
      const suggested = scan.suggested_mapping || {};
      setManualScan(scan);
      setManualDraft((current) => ({
        ...current,
        sourceType: source.sourceType,
        fileName: source.fileName || '',
        connectionId: source.connectionId || '',
        connectionName: source.connectionName || '',
        sqlTable: source.sqlTable || '',
        title: current.title || String(source.connectionName || source.fileName || source.sqlTable || '').replace(/\.[^.]+$/, ''),
        columnMapping: suggested,
      }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  const createManualReport = async () => {
    if (!user?.id || !manualDraft.title.trim() || (!manualDraft.fileName && !manualDraft.connectionId)) return;
    let cleaningRecipe;
    try {
      cleaningRecipe = JSON.parse(manualDraft.cleaningRecipe || '{}');
      if (!cleaningRecipe || Array.isArray(cleaningRecipe) || typeof cleaningRecipe !== 'object') {
        throw new Error('Cleaning recipe must be a JSON object');
      }
    } catch (err) {
      setError(isEn ? `Cleaning recipe is invalid: ${err.message}` : `Cleaning recipe ไม่ถูกต้อง: ${err.message}`);
      return;
    }
    setBusy('manual-create');
    setError('');
    try {
      const payload = await visualizationRequest('/reports', {
        body: {
          user_id: user.id,
          title: manualDraft.title.trim(),
          description: isEn ? 'Created manually from a user-configured data source.' : 'สร้างเองจากแหล่งข้อมูลที่ผู้ใช้กำหนด',
          created_via: 'workspace',
          status: 'draft',
          source_config: {
            type: manualDraft.sourceType,
            file_name: manualDraft.fileName || undefined,
            connection_id: manualDraft.connectionId || undefined,
            name: manualDraft.connectionName || undefined,
            sql_table: manualDraft.sqlTable || undefined,
            column_mapping: manualDraft.columnMapping,
            cleaning_profile: manualDraft.cleaningProfile,
            cleaning_recipe: cleaningRecipe,
          },
        },
      });
      const report = payload.report;
      setReports((current) => [report, ...current]);
      setSelectedId(report.id);
      setManualBuilderOpen(false);
      setManualScan(null);
      setManualDraft({ title: '', fileName: '', columnMapping: {}, cleaningProfile: 'standard', cleaningRecipe: MANUAL_CLEANING_RECIPE, sourceType: 'file', connectionId: '', connectionName: '', sqlTable: '' });
      router.push(buildVisualizationPath(routing, report.id));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  const setManualColumnRole = (columnName, value) => {
    setManualDraft((current) => {
      const currentValue = current.columnMapping[columnName] || '';
      let nextValue = value;
      if (value === '__none__') nextValue = '';
      if (value === '__original__') nextValue = columnName;
      if (value === '__custom__') nextValue = SEMANTIC_ROLE_VALUES.includes(currentValue) ? '' : currentValue;
      return {
        ...current,
        columnMapping: { ...current.columnMapping, [columnName]: nextValue },
      };
    });
  };

  const bindReportConversation = useCallback(async (conversationId) => {
    if (!selected?.id || !user?.id || selected.conversation_id === conversationId) return;
    try {
      const payload = await visualizationRequest('/reports', {
        method: 'PATCH',
        body: {
          user_id: user.id,
          report_id: selected.id,
          conversation_id: conversationId,
        },
      });
      setReports((current) => current.map((report) => (
        report.id === selected.id ? { ...report, ...payload.report } : report
      )));
      setPendingConversationId(null);
    } catch (bindError) {
      setPendingConversationId(conversationId);
      setError(bindError.message);
      throw bindError;
    }
  }, [selected, user]);

  const beginChatResize = useCallback((event) => {
    event.preventDefault();
    const move = (moveEvent) => {
      setChatWidth(visualizationChatWidthFromPointer(window.innerWidth, moveEvent.clientX));
    };
    const stop = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', stop);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', stop);
  }, []);

  const saveReport = async (updates) => {
    if (!selected || !user?.id) return;
    setBusy('save');
    setError('');
    try {
      const payload = await visualizationRequest('/reports', {
        method: 'PATCH',
        body: {
          user_id: user.id,
          report_id: selected.id,
          ...updates,
        },
      });
      setReports((current) =>
        current.map((item) =>
          item.id === selected.id ? { ...item, ...payload.report } : item,
        ),
      );
      setEditing(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  const reprovePacket = async () => {
    if (!selected || !user?.id) return;
    setBusy('reprove');
    setError('');
    try {
      const payload = await visualizationRequest('/decision/reprove', {
        body: {
          user_id: user.id,
          report_id: selected.id,
          filters: dashboardContext.filters || {},
        },
      });
      if (payload.report) {
        setReports((current) =>
          current.map((item) =>
            item.id === selected.id ? { ...item, ...payload.report } : item,
          ),
        );
      }
      if (payload.dashboard) {
        setDashboards((current) => ({
          ...current,
          [selected.id]: payload.dashboard,
        }));
      }
      setProveDiff(payload.prove_diff || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  const handleInsightAction = async (actionKey, status) => {
    if (!selected || !user?.id || !actionKey) return;
    try {
      const payload = await visualizationRequest('/reports', {
        method: 'PATCH',
        body: {
          user_id: user.id,
          report_id: selected.id,
          insight_action: { action_key: actionKey, status },
        },
      });
      setReports((current) =>
        current.map((item) =>
          item.id === selected.id ? { ...item, ...payload.report } : item,
        ),
      );
      setDashboards((current) => {
        const existing = current[selected.id];
        if (!existing) return current;
        return {
          ...current,
          [selected.id]: {
            ...existing,
            decision_packet: payload.report?.decision_packet || existing.decision_packet,
            decision_insights: (existing.decision_insights || []).map((insight) => (
              insight.action_key === actionKey
                ? { ...insight, action: { ...(insight.action || {}), status } }
                : insight
            )),
          },
        };
      });
    } catch (err) {
      setError(err.message);
    }
  };

  const handleAskAboutInsight = (insight) => {
    const widgetId = insight?.evidence?.widget_id || null;
    setDashboardContext((current) => ({
      ...current,
      widgetId,
    }));
    setAskWhyPreset(
      isEn
        ? `Prove why this insight is true and what changed: ${insight?.title || ''}. ${insight?.summary || ''}`
        : `พิสูจน์ว่าทำไมข้อค้นพบนี้ถึงเป็นจริง และอะไรเปลี่ยน: ${insight?.title_th || insight?.title || ''}. ${insight?.summary_th || insight?.summary || ''}`,
    );
    setChatOpen(true);
  };

  const removeReport = async (reportId) => {
    if (!reportId || !user?.id) return;
    setBusy('delete-report');
    try {
      await visualizationRequest('/reports', {
        method: 'DELETE',
        body: { user_id: user.id, report_id: reportId },
      });
      const nextReports = reports.filter((item) => item.id !== reportId);
      setReports(nextReports);
      const nextId = nextReports[0]?.id || null;
      setSelectedId(nextId);
      setDeleteModal({ show: false, type: null, id: null });
      router.replace(buildVisualizationPath(routing, nextId));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  const removeChart = async (chartId) => {
    if (!user?.id || !selected) return;
    setBusy(`chart:${chartId}`);
    try {
      await visualizationRequest('/charts', {
        method: 'DELETE',
        body: { user_id: user.id, chart_id: chartId },
      });
      setReports((current) =>
        current.map((report) =>
          report.id === selected.id
            ? { ...report, charts: report.charts.filter((chart) => chart.id !== chartId) }
            : report,
          ),
      );
      setDeleteModal({ show: false, type: null, id: null });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  const duplicateReport = async () => {
    if (!selected?.id || !user?.id) return;
    if (dashboardDirty && !window.confirm(isEn ? 'Duplicate the last saved dashboard and leave this draft?' : 'ทำสำเนาจากเวอร์ชันที่บันทึกล่าสุดและออกจาก Draft นี้หรือไม่?')) return;
    setBusy('duplicate-report');
    setError('');
    try {
      const payload = await visualizationRequest('/reports/duplicate', {
        body: {
          user_id: user.id,
          report_id: selected.id,
          title: `${selected.title} ${isEn ? 'copy' : 'สำเนา'}`,
        },
      });
      setReports((current) => [payload.report, ...current]);
      setSelectedId(payload.report.id);
      router.push(buildVisualizationPath(routing, payload.report.id));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  const planDashboard = async (instruction, currentSpec) => {
    if (!selected?.id || !user?.id) return null;
    dashboardAbortRef.current?.abort();
    const controller = new AbortController();
    dashboardAbortRef.current = controller;
    setDashboardBusy(true);
    setError('');
    try {
      const payload = await visualizationRequest('/dashboard/plan', {
        body: {
          user_id: user.id,
          report_id: selected.id,
          instruction,
          current_spec: currentSpec,
        },
        signal: controller.signal,
      });
      setDashboards((current) => ({ ...current, [selected.id]: payload.dashboard }));
      return payload.dashboard;
    } catch (err) {
      if (err?.name !== 'AbortError') setError(err.message);
      return null;
    } finally {
      setDashboardBusy(false);
    }
  };

  const previewDashboardFromChat = async (instruction) => {
    if (!selected?.id || !String(instruction || '').trim()) return null;
    const original = dashboards[selected.id] || null;
    const preview = await planDashboard(
      String(instruction).trim(),
      original?.spec || selected.dashboard_spec || null,
    );
    if (preview) {
      setDashboardPreview({ reportId: selected.id, original, preview });
    }
    return preview;
  };

  const applyDashboardPreview = async () => {
    if (!selected?.id || dashboardPreview?.reportId !== selected.id) return;
    const saved = await generateDashboard(
      false,
      dashboardContext.filters || {},
      dashboardPreview.preview?.spec,
      true,
    );
    if (saved) setDashboardPreview(null);
  };

  const cancelDashboardPreview = () => {
    if (!selected?.id || dashboardPreview?.reportId !== selected.id) return;
    setDashboards((current) => ({
      ...current,
      [selected.id]: dashboardPreview.original,
    }));
    setDashboardPreview(null);
  };

  const handleDashboardChange = (nextDashboard, persisted = false) => {
    if (!selected?.id || !nextDashboard) return;
    setDashboards((current) => ({ ...current, [selected.id]: nextDashboard }));
    if (persisted) {
      setReports((current) => current.map((report) => (
        report.id === selected.id
          ? { ...report, dashboard_spec: nextDashboard.spec, updated_at: new Date().toISOString() }
          : report
      )));
    }
  };

  const confirmDelete = () => {
    if (deleteModal.type === 'report') {
      removeReport(deleteModal.id);
    } else if (deleteModal.type === 'chart') {
      removeChart(deleteModal.id);
    }
  };

  const handleLogout = async () => {
    if (dashboardDirty && !window.confirm(isEn ? 'Sign out with unsaved dashboard changes?' : 'ออกจากระบบโดยยังไม่ได้บันทึก Dashboard หรือไม่?')) return;
    await supabase.auth.signOut();
    router.replace(localePath('/login', routing));
  };

  const chatPreset = isEn
    ? 'Ask about my ready dataset, prove the numbers with evidence, then propose charts I can pin to a decision packet.'
    : 'ถามเกี่ยวกับชุดข้อมูลที่พร้อมแล้ว พิสูจน์ตัวเลขด้วยหลักฐาน แล้วเสนอกราฟที่ฉันปักเข้า Decision packet ได้';

  return (
    <div className="app-shell flex h-screen w-full overflow-hidden bg-[#f8f8f6] text-slate-900 dark:bg-zinc-950 dark:text-slate-100">
      <DashboardSidebar
        isOpen={isOpen}
        setIsOpen={setIsOpen}
        user={user}
        plan={plan}
        routing={routing}
        isEn={isEn}
        onLogout={handleLogout}
      />

      <main className="app-main relative flex min-w-0 flex-1 overflow-hidden">
        <div className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1500px] px-5 py-7 md:px-8 lg:px-10">
          <header className="mb-7 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                {isEn ? 'Ask → Prove → Pin' : 'ถาม → พิสูจน์ → ปัก'}
              </div>
              <h1 className="font-serif text-3xl font-bold tracking-tight text-slate-950 dark:text-white">
                {isEn ? 'Findings' : 'Findings'}
              </h1>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-500 dark:text-slate-400">
                {isEn
                  ? 'Pin verified findings from Chat into a decision packet. Inspect evidence first—field editing is optional refine, not the starting point.'
                  : 'ปักข้อค้นพบที่พิสูจน์แล้วจาก Chat เข้า Decision packet ตรวจหลักฐานก่อน — การปรับฟิลด์เป็นโหมดละเอียดเสริม ไม่ใช่จุดเริ่ม'}
              </p>
              <div className="mt-3 flex flex-wrap gap-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300">
                  1. {isEn ? 'Ask' : 'ถาม'}
                </span>
                <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-300">
                  2. {isEn ? 'Prove' : 'พิสูจน์'}
                </span>
                <span className="rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 text-violet-800 dark:border-violet-900/50 dark:bg-violet-950/30 dark:text-violet-300">
                  3. {isEn ? 'Pin' : 'ปัก'}
                </span>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => router.push(buildChatPath(routing, { preset: chatPreset }))}
                className="btn-primary inline-flex items-center gap-2 px-4 py-2.5 text-xs"
              >
                <MessageSquareText size={14} />
                {isEn ? 'Ask in Chat' : 'ถามใน Chat'}
              </button>
              <button
                onClick={() => setReportLibraryOpen(true)}
                className="btn-secondary inline-flex items-center gap-2 px-4 py-2.5 text-xs"
              >
                <LayoutDashboard size={14} />
                {isEn ? 'Decision packets' : 'Decision packets'}
              </button>
              {selected && (
                <button
                  onClick={() => setChatOpen((open) => !open)}
                  disabled={chatBusy && chatOpen}
                  className="btn-secondary inline-flex items-center gap-2 px-4 py-2.5 text-xs disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <MessageSquareText size={14} />
                  {chatOpen ? (isEn ? 'Hide Chat' : 'ซ่อน Chat') : (isEn ? 'Show Chat' : 'แสดง Chat')}
                </button>
              )}
              {pendingConversationId && (
                <button
                  onClick={() => bindReportConversation(pendingConversationId)}
                  className="btn-secondary inline-flex items-center gap-2 px-4 py-2.5 text-xs"
                >
                  <RefreshCw size={14} />
                  {isEn ? 'Retry Chat link' : 'ลองผูก Chat ใหม่'}
                </button>
              )}
              <button
                onClick={openManualBuilder}
                className="btn-secondary inline-flex items-center gap-2 px-4 py-2.5 text-xs"
              >
                <FilePlus2 size={14} />
                {isEn ? 'Advanced: manual' : 'ขั้นสูง: สร้างเอง'}
              </button>
              <button
                onClick={() => loadReports()}
                disabled={loading}
                className="btn-secondary inline-flex items-center gap-2 px-4 py-2.5 text-xs"
              >
                <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
                {isEn ? 'Refresh' : 'รีเฟรช'}
              </button>
            </div>
          </header>

          {manualBuilderOpen && (
            <div className="mb-6 overflow-hidden rounded-2xl border border-amber-200 bg-white shadow-sm dark:border-amber-900/60 dark:bg-slate-950">
              <div className="flex items-start justify-between gap-4 border-b border-amber-100 bg-amber-50/70 px-5 py-4 dark:border-amber-900/40 dark:bg-amber-950/20">
                <div>
                  <h2 className="text-sm font-semibold text-slate-900 dark:text-white">
                    {isEn ? 'Advanced: build without Ask → Prove' : 'ขั้นสูง: สร้างโดยไม่ผ่าน ถาม → พิสูจน์'}
                  </h2>
                  <p className="mt-1 max-w-3xl text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                    {isEn
                      ? 'Map columns and set cleaning yourself. Prefer Ask in Chat when you want evidence-linked findings you can pin.'
                      : 'กำหนด mapping และ cleaning เอง แนะนำให้ถามใน Chat เมื่อต้องการข้อค้นพบที่ผูกหลักฐานแล้วปักได้'}
                  </p>
                </div>
                <button type="button" onClick={() => setManualBuilderOpen(false)} className="rounded-lg p-2 text-slate-400 hover:bg-white/80 hover:text-slate-700 dark:hover:bg-slate-900" title={isEn ? 'Close' : 'ปิด'}>
                  <X size={16} />
                </button>
              </div>
              <div className="grid gap-5 p-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
                <div className="space-y-4">
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-200">
                    {isEn ? 'Report title' : 'ชื่อรายงาน'}
                    <input
                      value={manualDraft.title}
                      onChange={(event) => setManualDraft((current) => ({ ...current, title: event.target.value }))}
                      maxLength={160}
                      placeholder={isEn ? 'Monthly sales dashboard' : 'Dashboard ยอดขายรายเดือน'}
                      className="mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-normal outline-none focus:border-amber-500 dark:border-slate-700 dark:bg-slate-900"
                    />
                  </label>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-200">
                    {isEn ? 'Data source' : 'แหล่งข้อมูล'}
                    <div className="mt-1.5"><WorkspaceSelect value={manualDraft.sourceType} onChange={(sourceType) => setManualDraft((current) => ({ ...current, sourceType, fileName: '', connectionId: '', connectionName: '', sqlTable: '' }))} options={[{ value: 'file', label: isEn ? 'File (Parquet, XLSX, XLS, CSV, JSON)' : 'ไฟล์ (Parquet, XLSX, XLS, CSV, JSON)' }, { value: 'sql', label: 'Database' }, { value: 'api', label: 'API' }, { value: 'cloud', label: isEn ? 'Cloud file (Google Drive / OneDrive)' : 'Cloud File (Google Drive / OneDrive)' }]} placeholder={isEn ? 'Select source type' : 'เลือกประเภทแหล่งข้อมูล'} /></div>
                  </label>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-200">
                    {manualDraft.sourceType === 'file' ? (isEn ? 'Source file' : 'ไฟล์ต้นทาง') : (isEn ? 'Connection' : 'การเชื่อมต่อ')}
                    <div className="mt-1.5"><WorkspaceSelect value={manualDraft.sourceType === 'file' ? manualDraft.fileName : manualDraft.connectionId} onChange={(value) => { if (manualDraft.sourceType === 'file') scanManualSource({ sourceType: 'file', fileName: value }); else { const list = manualConnections[manualDraft.sourceType === 'sql' ? 'database' : manualDraft.sourceType] || []; const item = list.find((connection) => connection.id === value); const source = { sourceType: manualDraft.sourceType, connectionId: value, connectionName: item?.name || item?.display_name || '' }; if (manualDraft.sourceType === 'sql') setManualDraft((current) => ({ ...current, ...source, sqlTable: '' })); else scanManualSource(source); } }} options={(manualDraft.sourceType === 'file' ? manualFiles.map((file) => ({ value: file.name, label: file.name })) : (manualConnections[manualDraft.sourceType === 'sql' ? 'database' : manualDraft.sourceType] || []).map((connection) => ({ value: connection.id, label: connection.name || connection.display_name || connection.id })))} placeholder={manualFilesLoading ? (isEn ? 'Loading sources…' : 'กำลังโหลดแหล่งข้อมูล…') : (isEn ? 'Select a source' : 'เลือกแหล่งข้อมูล')} /></div>
                  </label>
                  {manualDraft.sourceType === 'sql' && <label className="block text-xs font-semibold text-slate-700 dark:text-slate-200">{isEn ? 'Table name' : 'ชื่อตาราง'}<input value={manualDraft.sqlTable} onChange={(event) => setManualDraft((current) => ({ ...current, sqlTable: event.target.value }))} onBlur={() => { if (manualDraft.connectionId && manualDraft.sqlTable.trim()) scanManualSource({ sourceType: 'sql', connectionId: manualDraft.connectionId, connectionName: manualDraft.connectionName, sqlTable: manualDraft.sqlTable.trim() }); }} placeholder="schema.table" className="mt-1.5 w-full rounded-xl border border-stone-200 bg-white px-3 py-2 text-sm font-normal outline-none focus:border-amber-500 dark:border-stone-700 dark:bg-zinc-950" /></label>}
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-200">
                    {isEn ? 'Cleaning profile' : 'รูปแบบการทำความสะอาด'}
                    <div className="mt-1.5">
                      <WorkspaceSelect
                        value={manualDraft.cleaningProfile}
                        onChange={(value) => setManualDraft((current) => ({ ...current, cleaningProfile: value }))}
                        options={[
                          { value: 'standard', label: 'Standard' },
                          { value: 'conservative', label: 'Conservative' },
                          { value: 'financial', label: 'Financial' },
                          { value: 'aggressive', label: 'Aggressive' },
                        ]}
                        placeholder={isEn ? 'Select profile' : 'เลือกโปรไฟล์'}
                      />
                    </div>
                  </label>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-200">
                    {isEn ? 'Cleaning recipe (JSON)' : 'Cleaning recipe (JSON)'}
                    <textarea
                      value={manualDraft.cleaningRecipe}
                      onChange={(event) => setManualDraft((current) => ({ ...current, cleaningRecipe: event.target.value }))}
                      rows={8}
                      spellCheck={false}
                      className="mt-1.5 w-full resize-y rounded-lg border border-slate-200 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100 outline-none focus:border-amber-500 dark:border-slate-700"
                    />
                  </label>
                </div>
                <div className="min-w-0">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="text-xs font-semibold text-slate-700 dark:text-slate-200">{isEn ? 'Column mapping' : 'กำหนด Mapping คอลัมน์'}</h3>
                    {busy === 'manual-scan' && <Loader2 size={14} className="animate-spin text-amber-600" />}
                  </div>
                  {(!manualDraft.fileName && !manualDraft.connectionId) || (manualDraft.sourceType === 'sql' && !manualDraft.sqlTable) ? (
                    <div className="mt-3 rounded-xl border border-dashed border-slate-200 px-4 py-10 text-center text-xs text-slate-400 dark:border-slate-800">
                      {isEn ? 'Select a source file to inspect its columns.' : 'เลือกไฟล์ต้นทางเพื่อดูคอลัมน์'}
                    </div>
                  ) : !manualScan ? (
                    <div className="mt-3 rounded-xl border border-dashed border-slate-200 px-4 py-10 text-center text-xs text-slate-400 dark:border-slate-800">
                      {isEn ? 'Scanning the selected file…' : 'กำลังสแกนไฟล์ที่เลือก…'}
                    </div>
                  ) : (
                    <div className="mt-3 max-h-[460px] space-y-2 overflow-y-auto pr-1">
                      {(manualScan.columns || []).map((column) => {
                        const name = typeof column === 'string' ? column : column.name;
                        if (!name) return null;
                        const value = manualDraft.columnMapping[name] ?? '';
                        const isOriginal = value === name;
                        const isCustom = Boolean(value) && !isOriginal && !SEMANTIC_ROLE_VALUES.includes(value);
                        return (
                          <div key={name} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] items-center gap-3 rounded-xl border border-slate-200 p-3 dark:border-slate-800">
                            <div className="min-w-0">
                              <div className="truncate text-xs font-semibold text-slate-800 dark:text-slate-100">{name}</div>
                              {typeof column === 'object' && column.inferred_type && <div className="mt-0.5 text-[10px] text-slate-400">{column.inferred_type}</div>}
                            </div>
                            <div className="min-w-0 space-y-2">
                              <MappingRoleSelect
                                value={isCustom ? '__custom__' : (isOriginal ? '__original__' : (value || '__none__'))}
                                onChange={(nextValue) => setManualColumnRole(name, nextValue)}
                                optionGroups={mappingOptionGroups}
                                m={messages}
                              />
                              {isCustom && (
                                <input
                                  value={value}
                                  onChange={(event) => setManualDraft((current) => ({
                                    ...current,
                                    columnMapping: { ...current.columnMapping, [name]: event.target.value.replace(/[^a-zA-Z0-9_-]/g, '') },
                                  }))}
                                  placeholder={isEn ? 'Custom field name' : 'ชื่อฟิลด์กำหนดเอง'}
                                  className="w-full rounded-lg border border-dashed border-slate-300 bg-white px-2.5 py-1.5 font-mono text-xs outline-none focus:border-amber-500 dark:border-slate-700 dark:bg-slate-900"
                                />
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-5 py-4 dark:border-slate-800">
                <p className="text-[11px] text-slate-400">
                  {isEn ? 'You can edit charts, KPIs, filters and layout after creating the report.' : 'หลังสร้างรายงานแล้ว คุณสามารถแก้กราฟ KPI ตัวกรอง และ layout ได้ทั้งหมด'}
                </p>
                <div className="flex gap-2">
                  <button type="button" onClick={() => setManualBuilderOpen(false)} className="btn-secondary px-3 py-2 text-xs">{isEn ? 'Cancel' : 'ยกเลิก'}</button>
                  <button
                    type="button"
                    onClick={createManualReport}
                    disabled={!manualScan || !manualDraft.title.trim() || busy === 'manual-create'}
                    className="btn-primary inline-flex items-center gap-2 px-3 py-2 text-xs disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {busy === 'manual-create' ? <Loader2 size={14} className="animate-spin" /> : <FilePlus2 size={14} />}
                    {isEn ? 'Create dashboard' : 'สร้าง Dashboard'}
                  </button>
                </div>
              </div>
            </div>
          )}

          <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
            {[
              [LayoutDashboard, isEn ? 'Private reports' : 'รายงานส่วนตัว', reports.length],
              [BarChart3, isEn ? 'Saved charts' : 'กราฟที่บันทึก', chartCount],
              [LockKeyhole, isEn ? 'Access' : 'สิทธิ์เข้าถึง', isEn ? 'Owner only' : 'เจ้าของเท่านั้น'],
            ].map(([Icon, label, value]) => (
              <div key={label} className="enterprise-panel flex items-center gap-3 p-4">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300">
                  <Icon size={17} strokeWidth={1.6} />
                </div>
                <div>
                  <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">{label}</div>
                  <div className="mt-0.5 text-sm font-semibold text-slate-800 dark:text-slate-100">{value}</div>
                </div>
              </div>
            ))}
          </div>

          {error && (
            <div className="mb-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/20 dark:text-red-300">
              {error}
            </div>
          )}

          {loading ? (
            <div className="enterprise-panel flex min-h-[420px] items-center justify-center">
              <Loader2 className="animate-spin text-amber-600" size={26} />
            </div>
          ) : (
            <div className="grid min-h-[620px] grid-cols-1 gap-5">
              {reportLibraryOpen && (
                <button
                  type="button"
                  aria-label={isEn ? 'Close report library' : 'ปิดคลังรายงาน'}
                  className="fixed inset-0 z-[70] bg-black/25 backdrop-blur-[1px]"
                  onClick={() => setReportLibraryOpen(false)}
                />
              )}
              <aside className={`${reportLibraryOpen ? 'translate-x-0' : '-translate-x-full'} fixed inset-y-0 left-0 z-[80] w-[min(360px,88vw)] overflow-hidden border-r border-slate-200 bg-white shadow-2xl transition-transform dark:border-slate-800 dark:bg-slate-950`}>
                <div className="border-b border-slate-200 px-4 py-4 dark:border-slate-800">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-xs font-semibold text-slate-800 dark:text-slate-100">
                      {isEn ? 'Report library' : 'คลังรายงาน'}
                    </div>
                    <button type="button" onClick={() => setReportLibraryOpen(false)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-900">
                      <X size={15} />
                    </button>
                  </div>
                  <div className="mt-1 text-[10px] text-slate-400">
                    {isEn ? 'Saved in your Supabase workspace' : 'บันทึกในพื้นที่ Supabase ของคุณ'}
                  </div>
                </div>
                <div className="max-h-[690px] space-y-1 overflow-y-auto p-2">
                  {reports.length === 0 ? (
                    <div className="px-4 py-12 text-center">
                      <FilePlus2 className="mx-auto text-slate-300 dark:text-slate-700" size={30} />
                      <p className="mt-3 text-xs text-slate-500">
                        {isEn ? 'No reports yet' : 'ยังไม่มีรายงาน'}
                      </p>
                    </div>
                  ) : reports.map((report) => {
                    const active = report.id === selectedId;
                    return (
                      <button
                        key={report.id}
                        onClick={() => selectReport(report.id)}
                        disabled={chatBusy}
                        className={`w-full rounded-xl border px-3 py-3 text-left transition-colors ${
                          active
                            ? 'border-amber-200 bg-amber-50/80 dark:border-amber-900/70 dark:bg-amber-950/20'
                            : 'border-transparent hover:bg-slate-50 dark:hover:bg-slate-900'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <span className="line-clamp-2 text-xs font-semibold text-slate-800 dark:text-slate-100">{report.title}</span>
                          <span className={`shrink-0 rounded-full px-2 py-0.5 text-[9px] font-semibold ${
                            report.status === 'final'
                              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300'
                              : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
                          }`}>
                            {report.status}
                          </span>
                        </div>
                        <div className="mt-2 flex items-center justify-between text-[10px] text-slate-400">
                          <span>
                            {(report.charts?.length || 0)
                              + (report.dashboard_spec?.widgets || []).filter((widget) => widget.kind === 'chart').length}{' '}
                            {isEn ? 'charts' : 'กราฟ'}
                          </span>
                          <span>{formatDate(report.updated_at, isEn)}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </aside>

              <section className="enterprise-panel min-w-0 overflow-hidden">
                {!selected ? (
                  <div className="flex min-h-[620px] flex-col items-center justify-center px-6 text-center">
                    <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300">
                      <Pin size={25} />
                    </div>
                    <h2 className="mt-5 font-serif text-xl font-bold">
                      {isEn ? 'Pin your first finding' : 'ปักข้อค้นพบแรก'}
                    </h2>
                    <p className="mt-2 max-w-lg text-sm leading-relaxed text-slate-500 dark:text-slate-400">
                      {isEn
                        ? 'Start in Chat: ask a business question, prove the numbers, then pin charts into a decision packet. Manual field building stays available as an advanced path.'
                        : 'เริ่มใน Chat: ถามคำถามธุรกิจ พิสูจน์ตัวเลข แล้วปักกราฟเข้า Decision packet การสร้างด้วยฟิลด์เองยังมีเป็นทางขั้นสูง'}
                    </p>
                    <div className="mt-5 flex justify-center">
                      <button
                        onClick={() => router.push(buildChatPath(routing, { preset: chatPreset }))}
                        className="btn-primary mr-2 inline-flex items-center gap-2 px-4 py-2.5 text-xs"
                      >
                        <MessageSquareText size={14} />
                        {isEn ? 'Ask → Prove in Chat' : 'ถาม → พิสูจน์ใน Chat'}
                      </button>
                      <button
                        onClick={openManualBuilder}
                        className="btn-secondary inline-flex items-center gap-2 px-4 py-2.5 text-xs"
                      >
                        <FilePlus2 size={14} />
                        {isEn ? 'Advanced: manual' : 'ขั้นสูง: สร้างเอง'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="border-b border-slate-200 px-5 py-5 dark:border-slate-800 md:px-7">
                      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                        <div className="min-w-0 flex-1">
                          {editing ? (
                            <div className="space-y-3">
                              <input
                                value={draftTitle}
                                onChange={(event) => setDraftTitle(event.target.value)}
                                maxLength={160}
                                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-base font-semibold outline-none focus:border-amber-500 dark:border-slate-700 dark:bg-slate-950"
                              />
                              <textarea
                                value={draftSummary}
                                onChange={(event) => setDraftSummary(event.target.value)}
                                maxLength={20000}
                                rows={4}
                                placeholder={isEn ? 'Executive summary' : 'บทสรุปผู้บริหาร'}
                                className="w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-amber-500 dark:border-slate-700 dark:bg-slate-950"
                              />
                            </div>
                          ) : (
                            <>
                              <div className="flex flex-wrap items-center gap-2">
                                <h2 className="font-serif text-2xl font-bold text-slate-950 dark:text-white">{selected.title}</h2>
                                <span className="rounded-full border border-slate-200 px-2 py-0.5 text-[9px] font-semibold uppercase text-slate-500 dark:border-slate-700 dark:text-slate-400">
                                  {selected.status}
                                </span>
                                {(() => {
                                  const packet = dashboards[selected.id]?.decision_packet
                                    || selected.decision_packet
                                    || selected.dashboard_spec?.decision_packet
                                    || {};
                                  const lifecycle = packet.lifecycle || 'draft';
                                  const isStale = Boolean(packet.is_stale || dashboards[selected.id]?.provenance?.is_stale);
                                  return (
                                    <span className={`rounded-full border px-2 py-0.5 text-[9px] font-semibold uppercase ${
                                      isStale || lifecycle === 'stale'
                                        ? 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-300'
                                        : lifecycle === 'proved'
                                          ? 'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-300'
                                          : 'border-slate-200 text-slate-500 dark:border-slate-700 dark:text-slate-400'
                                    }`}>
                                      {packetLifecycleLabel(isStale ? 'stale' : lifecycle, isEn)}
                                    </span>
                                  );
                                })()}
                              </div>
                              <p className="mt-2 max-w-3xl whitespace-pre-wrap text-sm leading-relaxed text-slate-500 dark:text-slate-400">
                                {selected.executive_summary || (isEn
                                  ? 'No executive summary yet. Edit this report after the analysis is ready.'
                                  : 'ยังไม่มีบทสรุปผู้บริหาร กดแก้ไขเมื่อผลวิเคราะห์พร้อม')}
                              </p>
                            </>
                          )}
                          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-slate-400">
                            <span>{isEn ? 'Updated' : 'อัปเดต'} {formatDate(selected.updated_at, isEn)}</span>
                            {selected.dataset_key && <span>Dataset: {selected.dataset_key}</span>}
                            <span>{isEn ? 'Created from' : 'สร้างจาก'} {selected.created_via}</span>
                          </div>
                        </div>
                        <div className="flex shrink-0 flex-wrap gap-2">
                          {editing ? (
                            <>
                              <button onClick={() => setEditing(false)} className="btn-secondary p-2.5" title={isEn ? 'Cancel' : 'ยกเลิก'}>
                                <X size={15} />
                              </button>
                              <button
                                onClick={() => saveReport({ title: draftTitle, executive_summary: draftSummary })}
                                disabled={busy === 'save' || !draftTitle.trim()}
                                className="btn-primary inline-flex items-center gap-2 px-3 py-2 text-xs"
                              >
                                {busy === 'save' ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                                {isEn ? 'Save' : 'บันทึก'}
                              </button>
                            </>
                          ) : (
                            <button onClick={() => setEditing(true)} className="btn-secondary inline-flex items-center gap-2 px-3 py-2 text-xs">
                              <PencilLine size={14} />
                              {isEn ? 'Edit' : 'แก้ไข'}
                            </button>
                          )}
                          <button
                            onClick={duplicateReport}
                            disabled={busy === 'duplicate-report'}
                            className="btn-secondary inline-flex items-center gap-2 px-3 py-2 text-xs"
                            title={isEn ? 'Duplicate decision packet' : 'ทำสำเนา Decision packet'}
                          >
                            {busy === 'duplicate-report' ? <Loader2 size={14} className="animate-spin" /> : <Copy size={14} />}
                            {isEn ? 'Duplicate' : 'ทำสำเนา'}
                          </button>
                          <button
                            onClick={reprovePacket}
                            disabled={busy === 'reprove' || dashboardBusy}
                            className="btn-secondary inline-flex items-center gap-2 px-3 py-2 text-xs"
                            title={isEn ? 'Re-prove with latest evidence' : 'พิสูจน์ใหม่ด้วยหลักฐานล่าสุด'}
                          >
                            {busy === 'reprove' ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                            {isEn ? 'Re-prove' : 'พิสูจน์ใหม่'}
                          </button>
                          <VisualizationDeliveryPanel
                            userId={user.id}
                            report={selected}
                            dashboard={dashboards[selected.id]}
                            locale={routing.locale}
                            isEn={isEn}
                            onDashboardChange={handleDashboardChange}
                          />
                          <button
                            onClick={() => saveReport({ status: selected.status === 'final' ? 'draft' : 'final' })}
                            className="btn-secondary px-3 py-2 text-xs"
                          >
                            {selected.status === 'final'
                              ? (isEn ? 'Return to draft' : 'กลับเป็นฉบับร่าง')
                              : (isEn ? 'Mark final' : 'ตั้งเป็นฉบับสมบูรณ์')}
                          </button>
                          <button
                            onClick={() => setDeleteModal({
                              show: true,
                              type: 'report',
                              id: selected.id,
                            })}
                            className="rounded-lg p-2.5 text-slate-400 transition-colors hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/30"
                            title={isEn ? 'Delete report' : 'ลบรายงาน'}
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      </div>
                    </div>

                    <div className="p-5 md:p-7">
                      {(dashboards[selected.id]?.provenance?.is_stale
                        || dashboards[selected.id]?.decision_packet?.lifecycle === 'stale'
                        || selected.decision_packet?.lifecycle === 'stale') && (
                        <div className="mb-4 flex flex-col gap-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 dark:border-amber-900/70 dark:bg-amber-950/25 sm:flex-row sm:items-center sm:justify-between">
                          <div>
                            <div className="text-xs font-semibold text-amber-900 dark:text-amber-200">
                              {isEn ? 'Evidence may be stale' : 'หลักฐานอาจล้าสมัย'}
                            </div>
                            <div className="mt-1 text-[10px] text-amber-800/80 dark:text-amber-300/80">
                              {isEn
                                ? 'The source fingerprint changed since the last prove. Re-prove before trusting or marking final.'
                                : 'ลายนิ้วมือแหล่งข้อมูลเปลี่ยนตั้งแต่พิสูจน์ครั้งล่าสุด พิสูจน์ใหม่ก่อนเชื่อหรือตั้งเป็นฉบับสมบูรณ์'}
                            </div>
                          </div>
                          <button type="button" onClick={reprovePacket} disabled={busy === 'reprove'} className="btn-primary px-3 py-2 text-xs">
                            {busy === 'reprove' ? (isEn ? 'Re-proving…' : 'กำลังพิสูจน์…') : (isEn ? 'Re-prove now' : 'พิสูจน์ใหม่เลย')}
                          </button>
                        </div>
                      )}
                      {proveDiff.length > 0 && (
                        <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-[11px] text-emerald-900 dark:border-emerald-900/60 dark:bg-emerald-950/20 dark:text-emerald-200">
                          <div className="font-semibold">{isEn ? 'Re-prove diff' : 'ผลต่างหลังพิสูจน์ใหม่'}</div>
                          <ul className="mt-2 space-y-1">
                            {proveDiff.slice(0, 5).map((item) => (
                              <li key={`${item.label}-${item.field}`}>
                                {item.label}: {String(item.before)} → {String(item.after)}
                                {Number.isFinite(Number(item.change_pct)) ? ` (${item.change_pct > 0 ? '+' : ''}${item.change_pct}%)` : ''}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {dashboardPreview?.reportId === selected.id && (
                        <div className="mb-4 flex flex-col gap-3 rounded-xl border border-orange-300 bg-orange-50 px-4 py-3 dark:border-orange-900/70 dark:bg-orange-950/25 sm:flex-row sm:items-center sm:justify-between">
                          <div>
                            <div className="text-xs font-semibold text-orange-900 dark:text-orange-200">
                              {isEn ? 'Pin preview' : 'ตัวอย่างก่อนปัก'}
                            </div>
                            <div className="mt-1 text-[10px] text-orange-700/80 dark:text-orange-300/80">
                              {isEn ? 'Review evidence-linked layout before pinning it to this packet.' : 'ตรวจเลย์เอาต์ที่ผูกหลักฐานก่อนปักลง packet นี้'}
                            </div>
                          </div>
                          <div className="flex gap-2">
                            <button type="button" onClick={cancelDashboardPreview} disabled={dashboardBusy} className="btn-secondary px-3 py-2 text-xs">
                              {isEn ? 'Cancel' : 'ยกเลิก'}
                            </button>
                            <button type="button" onClick={applyDashboardPreview} disabled={dashboardBusy} className="btn-primary px-3 py-2 text-xs">
                              {dashboardBusy ? (isEn ? 'Applying…' : 'กำลังใช้…') : (isEn ? 'Apply' : 'นำไปใช้')}
                            </button>
                          </div>
                        </div>
                      )}
                      {dashboards[selected.id] ? (
                        <AdaptiveBiDashboard
                          dashboard={dashboards[selected.id]}
                          savedSpec={selected.dashboard_spec}
                          savedCharts={selected.charts || []}
                          isEn={isEn}
                          busy={dashboardBusy}
                          onRegenerate={() => generateDashboard(false, {})}
                          onFiltersChange={scheduleDashboardFilters}
                          onPreviewSpec={(dashboardSpec) => generateDashboard(false, {}, dashboardSpec, false)}
                          onSaveSpec={(dashboardSpec) => generateDashboard(false, {}, dashboardSpec, true)}
                          onCancelEdit={() => generateDashboard(false, {}, null, false)}
                          onAutoLayout={() => generateDashboard(true, {}, null, false)}
                          onPlanSpec={planDashboard}
                          onDirtyChange={setDashboardDirty}
                          focusedWidgetId={dashboardContext.widgetId}
                          onContextChange={setDashboardContext}
                          onAskAboutInsight={handleAskAboutInsight}
                          onInsightAction={handleInsightAction}
                        />
                      ) : dashboardBusy ? (
                        <div className="flex min-h-[460px] flex-col items-center justify-center rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
                          <Loader2 className="animate-spin text-amber-600" size={28} />
                          <div className="mt-4 text-sm font-semibold">
                            {isEn ? 'Proving layout from the ready source…' : 'กำลังพิสูจน์เลย์เอาต์จากแหล่งข้อมูลที่พร้อม…'}
                          </div>
                          <div className="mt-1 text-xs text-slate-400">
                            {isEn ? 'Checking dimensions, measures, filters and evidence links' : 'กำลังตรวจ dimension, measure, filter และลิงก์หลักฐาน'}
                          </div>
                        </div>
                      ) : selected.charts?.length ? (
                        <div className="grid grid-cols-1 gap-5 2xl:grid-cols-2">
                          {selected.charts.map((chart, index) => (
                            <article
                              key={chart.id}
                              className={`${selected.charts.length === 1 ? '2xl:col-span-2' : ''} rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900`}
                            >
                              <div className="mb-3 flex items-center justify-between gap-3">
                                <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                                  <span>{String(index + 1).padStart(2, '0')}</span>
                                  <span>{chart.chart_type}</span>
                                </div>
                                <button
                                  onClick={() => setDeleteModal({
                                    show: true,
                                    type: 'chart',
                                    id: chart.id,
                                  })}
                                  disabled={busy === `chart:${chart.id}`}
                                  className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/30"
                                  title={isEn ? 'Remove chart' : 'นำกราฟออก'}
                                >
                                  {busy === `chart:${chart.id}` ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                                </button>
                              </div>
                              <ChartRenderer
                                embedded
                                data={{
                                  chart_type: chart.chart_type,
                                  config: { ...chart.config, title: chart.title },
                                  data: chart.data,
                                }}
                              />
                              {chart.insight && (
                                <p className="mt-4 border-t border-slate-100 pt-4 text-xs leading-relaxed text-slate-500 dark:border-slate-800 dark:text-slate-400">
                                  {chart.insight}
                                </p>
                              )}
                            </article>
                          ))}
                        </div>
                      ) : (
                        <div className="flex min-h-[390px] flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 px-6 text-center dark:border-slate-800">
                          <BarChart3 size={30} className="text-slate-300 dark:text-slate-700" />
                          <h3 className="mt-4 text-sm font-semibold">
                            {isEn ? 'Nothing pinned yet' : 'ยังไม่มีอะไรที่ปักไว้'}
                          </h3>
                          <p className="mt-2 max-w-md text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                            {isEn
                              ? 'Ask in Chat, verify the evidence on the answer, then pin charts into this decision packet.'
                              : 'ถามใน Chat ตรวจหลักฐานในคำตอบ แล้วปักกราฟเข้า Decision packet นี้'}
                          </p>
                        </div>
                      )}

                      <div className="mt-6 flex flex-col gap-3 rounded-2xl border border-amber-200 bg-amber-50/70 p-4 dark:border-amber-900/50 dark:bg-amber-950/15 sm:flex-row sm:items-center sm:justify-between">
                        <div>
                          <div className="text-xs font-semibold text-amber-900 dark:text-amber-200">
                            {isEn ? 'Continue Ask → Prove → Pin' : 'ทำต่อ: ถาม → พิสูจน์ → ปัก'}
                          </div>
                          <div className="mt-1 text-[11px] text-amber-800/70 dark:text-amber-300/70">
                            {selected.conversation_id
                              ? (isEn ? 'Return to the source conversation to prove more findings.' : 'กลับไปบทสนทนาต้นทางเพื่อพิสูจน์ข้อค้นพบเพิ่ม')
                              : (isEn ? 'Ask a new question, prove it, then pin charts back here.' : 'ถามคำถามใหม่ พิสูจน์ แล้วปักกราฟกลับมาที่นี่')}
                          </div>
                        </div>
                        <button
                          onClick={() => {
                            setChatOpen(true);
                          }}
                          className="inline-flex items-center justify-center gap-2 rounded-lg bg-amber-700 px-4 py-2.5 text-xs font-semibold text-white hover:bg-amber-800"
                        >
                          <MessageSquareText size={14} />
                          {isEn ? 'Open Chat to pin' : 'เปิด Chat เพื่อปัก'}
                          <ArrowRight size={13} />
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </section>
            </div>
          )}
        </div>
        </div>

        {selected && chatOpen && (
          <>
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label={isEn ? 'Resize Chat panel' : 'ปรับความกว้าง Chat'}
              tabIndex={0}
              onPointerDown={beginChatResize}
              onKeyDown={(event) => {
                if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
                event.preventDefault();
                setChatWidth((width) => visualizationChatWidthFromKey(width, event.key));
              }}
              className="relative z-30 hidden w-2 shrink-0 cursor-col-resize bg-transparent outline-none after:absolute after:inset-y-0 after:left-1/2 after:w-px after:bg-slate-200 hover:after:bg-orange-400 focus-visible:after:bg-orange-500 dark:after:bg-slate-800 xl:block"
            />
            <aside
              style={{ '--chat-panel-width': `${chatWidth}px` }}
              className="fixed inset-x-2 bottom-16 top-16 z-40 w-[calc(100%-1rem)] overflow-hidden rounded-2xl border border-slate-200 bg-[#faf9f7] shadow-2xl dark:border-slate-800 dark:bg-zinc-950 xl:static xl:inset-auto xl:z-20 xl:h-full xl:w-(--chat-panel-width) xl:shrink-0 xl:rounded-none xl:border-y-0 xl:border-r-0 xl:shadow-none"
            >
              <Chat
                key={selected.id}
                mode="panel"
                conversationId={selected.conversation_id || null}
                visualizationContext={visualizationChatContext}
                onConversationCreated={bindReportConversation}
                onGenerationChange={setChatBusy}
                onOpenFullChat={(conversationId) => router.push(buildChatPath(routing, {
                  conversationId: conversationId || selected.conversation_id,
                  preset: conversationId || selected.conversation_id ? undefined : chatPreset,
                }))}
                onClosePanel={() => setChatOpen(false)}
                onClearVisualizationWidget={() => setDashboardContext((current) => ({
                  ...current,
                  widgetId: null,
                }))}
                onPreviewDashboard={previewDashboardFromChat}
                dashboardPreviewBusy={dashboardBusy}
                panelPreset={askWhyPreset}
              />
            </aside>
          </>
        )}
        {selected && (
          <div className="fixed bottom-2 left-1/2 z-[60] flex -translate-x-1/2 rounded-xl border border-slate-200 bg-white/95 p-1 shadow-xl backdrop-blur dark:border-slate-800 dark:bg-slate-950/95 xl:hidden">
            <button type="button" disabled={chatBusy && chatOpen} onClick={() => setChatOpen(false)} className={`${!chatOpen ? 'bg-stone-900 text-white dark:bg-white dark:text-stone-900' : 'text-slate-500'} rounded-lg px-4 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-40`}>
              {isEn ? 'Dashboard' : 'Dashboard'}
            </button>
            <button type="button" onClick={() => setChatOpen(true)} className={`${chatOpen ? 'bg-orange-600 text-white' : 'text-slate-500'} rounded-lg px-4 py-2 text-xs font-semibold`}>
              Chat
            </button>
          </div>
        )}
      </main>

      <DeleteConfirmationModal
        isOpen={deleteModal.show}
        onClose={() => {
          if (!busy) setDeleteModal({ show: false, type: null, id: null });
        }}
        onConfirm={confirmDelete}
        title={
          deleteModal.type === 'report'
            ? (isEn ? 'Delete this report?' : 'ลบรายงานนี้หรือไม่?')
            : (isEn ? 'Remove this chart?' : 'นำกราฟนี้ออกหรือไม่?')
        }
        message={
          deleteModal.type === 'report'
            ? (isEn
              ? 'The report and every saved chart inside it will be permanently deleted and cannot be recovered.'
              : 'รายงานและกราฟที่บันทึกไว้ภายในทั้งหมดจะถูกลบอย่างถาวร และกู้คืนไม่ได้')
            : (isEn
              ? 'This saved chart will be permanently removed from the report and cannot be recovered.'
              : 'กราฟที่บันทึกนี้จะถูกนำออกจากรายงานอย่างถาวร และกู้คืนไม่ได้')
        }
        confirmButtonText={
          deleteModal.type === 'report'
            ? (isEn ? 'Delete report' : 'ลบรายงาน')
            : (isEn ? 'Remove chart' : 'นำกราฟออก')
        }
        cancelButtonText={isEn ? 'Cancel' : 'ยกเลิก'}
        isLoading={
          busy === 'delete-report'
          || (deleteModal.type === 'chart' && busy === `chart:${deleteModal.id}`)
        }
      />
    </div>
  );
};

export default Visualization;
