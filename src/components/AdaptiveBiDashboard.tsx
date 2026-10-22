// @ts-nocheck
'use client';

import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Check,
  Copy,
  Database,
  Eye,
  Filter,
  GripVertical,
  LayoutDashboard,
  Loader2,
  Maximize2,
  Minimize2,
  PencilLine,
  Plus,
  RefreshCw,
  Rows3,
  Save,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Lightbulb,
  Trash2,
  X,
} from '@/components/icons';
import ChartRenderer from './ChartRenderer';
import {
  bindChartField,
  COUNT_FIELD,
  dashboardFieldGroups,
  formatDashboardValue,
  inspectChart,
  makeDashboardKpi,
  makeDashboardWidget,
  dashboardSectionMessageKey,
  orderedDashboardWidgets,
  reorderDashboardWidgets,
  upgradeDashboardSpecV4,
} from '../features/visualization/dashboardModel.js';
import { getMessages, t } from '../utils/i18n.js';

const spanClass = (span) => ({
  4: 'xl:col-span-4',
  6: 'xl:col-span-6',
  8: 'xl:col-span-8',
  12: 'xl:col-span-12',
}[Number(span)] || 'xl:col-span-6');

const clone = (value) => JSON.parse(JSON.stringify(value || {}));
const FIELD_DRAG = 'application/x-mq-chart-field';

const FieldChip = ({ column, label }) => (
  <button
    type="button"
    draggable
    onDragStart={(event) => {
      event.stopPropagation();
      event.dataTransfer.setData(FIELD_DRAG, JSON.stringify(column));
      event.dataTransfer.effectAllowed = 'copy';
    }}
    className="inline-flex max-w-full items-center rounded-lg border border-slate-200 bg-white px-2 py-1 text-[10px] font-semibold text-slate-700 hover:border-amber-400 dark:border-white/12 dark:bg-zinc-950 dark:text-zinc-200"
  >
    <span className="truncate">{label || column.name}</span>
  </button>
);

const FieldWell = ({ label, value, hint, onDropField, onClear, emptyLabel }) => (
  <div
    onDragOver={(event) => {
      event.preventDefault();
      event.stopPropagation();
    }}
    onDrop={(event) => {
      event.preventDefault();
      event.stopPropagation();
      const raw = event.dataTransfer.getData(FIELD_DRAG);
      if (!raw) return;
      try {
        onDropField(JSON.parse(raw));
      } catch {
        /* ignore malformed drag payload */
      }
    }}
    className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-3 dark:border-white/15 dark:bg-zinc-950"
  >
    <div className="mb-1.5 flex items-center justify-between gap-2">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</span>
      {value && onClear && (
        <button type="button" onClick={onClear} className="text-[10px] font-semibold text-slate-400 hover:text-red-600">
          ×
        </button>
      )}
    </div>
    <p className={`truncate text-xs font-semibold ${value ? 'text-slate-900 dark:text-white' : 'text-slate-400'}`}>
      {value || emptyLabel}
    </p>
    {hint && <p className="mt-1 text-[10px] text-slate-400">{hint}</p>}
  </div>
);

const ToolbarButton = ({ children, active, ...props }) => (
  <button
    type="button"
    {...props}
    className={`${active ? 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-300' : ''} btn-secondary inline-flex items-center justify-center gap-1.5 px-3 py-2 text-[11px] disabled:opacity-40`}
  >
    {children}
  </button>
);

const AdaptiveBiDashboard = ({
  dashboard,
  savedSpec,
  savedCharts = [],
  isEn,
  busy,
  onRegenerate,
  onFiltersChange,
  onPreviewSpec,
  onSaveSpec,
  onCancelEdit,
  onAutoLayout,
  onPlanSpec,
  readOnly = false,
  briefMode = false,
  onDirtyChange,
  focusedWidgetId = null,
  onContextChange,
  onAskAboutInsight = null,
  onInsightAction = null,
}) => {
  const locale = isEn ? 'en' : 'th';
  const messages = useMemo(() => getMessages(locale), [locale]);
  const tx = useCallback(
    (key, replacements = {}) => t(messages, `visualization_v4.${key}`, key, replacements),
    [messages],
  );
  const spec = useMemo(
    () => upgradeDashboardSpecV4(dashboard?.spec || { filters: [], kpis: [], widgets: [] }),
    [dashboard?.spec],
  );
  const [filters, setFilters] = useState({});
  const [editMode, setEditMode] = useState(false);
  const [draftSpec, setDraftSpec] = useState(() => clone(spec));
  const [history, setHistory] = useState([]);
  const [future, setFuture] = useState([]);
  const [selectedWidgetId, setSelectedWidgetId] = useState(null);
  const [inspectedWidgetId, setInspectedWidgetId] = useState(null);
  const [draggedWidgetId, setDraggedWidgetId] = useState(null);
  const [addMenuOpen, setAddMenuOpen] = useState(false);
  const [storedDraft, setStoredDraft] = useState(null);
  const [lastDraftSavedAt, setLastDraftSavedAt] = useState(null);
  const [aiPrompt, setAiPrompt] = useState('');
  const schemaByName = useMemo(
    () => Object.fromEntries((dashboard?.schema || []).map((column) => [column.name, column])),
    [dashboard?.schema],
  );
  const fieldGroups = useMemo(
    () => dashboardFieldGroups(dashboard?.schema || []),
    [dashboard?.schema],
  );
  const specSignature = JSON.stringify(spec);
  const savedSpecSignature = JSON.stringify(upgradeDashboardSpecV4(savedSpec || spec));
  const activeSpec = editMode ? draftSpec : spec;
  const sectionTitle = (section) => {
    const key = dashboardSectionMessageKey(section, activeSpec.presentation?.variant);
    return key ? tx(key) : section?.title;
  };
  const orderedWidgets = useMemo(
    () => orderedDashboardWidgets(activeSpec),
    [activeSpec],
  );
  const sectionByFirstWidget = useMemo(() => Object.fromEntries(
    (activeSpec.sections || [])
      .filter((section) => section.widget_ids?.length)
      .map((section) => [section.widget_ids[0], section]),
  ), [activeSpec.sections]);
  const sectionByWidget = useMemo(() => Object.fromEntries(
    (activeSpec.sections || []).flatMap((section) => (
      (section.widget_ids || []).map((widgetId) => [widgetId, section])
    )),
  ), [activeSpec.sections]);
  const dirty = editMode && JSON.stringify(draftSpec) !== savedSpecSignature;
  const draftStorageKey = dashboard?.report_id
    ? `mataqor:visualization-draft:${dashboard.report_id}`
    : null;
  const selectedWidget = (draftSpec.widgets || []).find((item) => item.id === selectedWidgetId);
  const inspectedWidget = (dashboard?.widgets || orderedWidgets).find((item) => item.id === inspectedWidgetId);
  const inspectedChart = inspectedWidget
    ? inspectChart(inspectedWidget, dashboard?.schema || [], {
      row_count: dashboard?.row_count,
      filtered_row_count: dashboard?.filtered_row_count,
      point_count: inspectedWidget.data?.length,
    })
    : null;
  const hasActiveFilters = Object.values(filters).some((value) => (
    typeof value === 'object' ? Object.values(value || {}).some(Boolean) : Boolean(value)
  ));

  useEffect(() => {
    setFilters(dashboard?.applied_filters || {});
    setEditMode(false);
    setSelectedWidgetId(null);
    setInspectedWidgetId(null);
    setHistory([]);
    setFuture([]);
    setStoredDraft(null);
    setLastDraftSavedAt(null);
  }, [dashboard?.applied_filters, dashboard?.report_id]);

  useEffect(() => {
    setDraftSpec(JSON.parse(specSignature));
  }, [specSignature]);

  useEffect(() => {
    if (!editMode || !dirty || !draftStorageKey) return undefined;
    const timer = window.setTimeout(() => {
      window.localStorage.setItem(draftStorageKey, JSON.stringify({
        spec: draftSpec,
        saved_at: new Date().toISOString(),
      }));
      setLastDraftSavedAt(new Date());
    }, 700);
    return () => window.clearTimeout(timer);
  }, [draftSpec, draftStorageKey, dirty, editMode]);

  useEffect(() => {
    if (!dirty) return undefined;
    const message = tx('leave_warning');
    const beforeUnload = (event) => {
      event.preventDefault();
      event.returnValue = message;
    };
    const guardLinks = (event) => {
      const anchor = event.target?.closest?.('a[href]');
      if (!anchor || anchor.target === '_blank' || event.defaultPrevented) return;
      if (!window.confirm(`${message}\n${tx('leave_page')}`)) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener('beforeunload', beforeUnload);
    document.addEventListener('click', guardLinks, true);
    return () => {
      window.removeEventListener('beforeunload', beforeUnload);
      document.removeEventListener('click', guardLinks, true);
    };
  }, [dirty, tx]);

  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => onDirtyChange?.(false);
  }, [dirty, onDirtyChange]);

  const sourceLabel = dashboard?.source?.file_name
    || dashboard?.source?.name
    || dashboard?.source?.sql_table
    || tx('saved_snapshots');

  const commitSpec = (updater) => {
    setDraftSpec((current) => {
      const next = typeof updater === 'function' ? updater(clone(current)) : updater;
      setHistory((items) => [...items.slice(-29), clone(current)]);
      setFuture([]);
      return upgradeDashboardSpecV4(next);
    });
  };

  const undo = () => {
    if (!history.length) return;
    const previous = history[history.length - 1];
    setHistory((items) => items.slice(0, -1));
    setFuture((items) => [clone(draftSpec), ...items].slice(0, 30));
    setDraftSpec(clone(previous));
  };

  const redo = () => {
    if (!future.length) return;
    const next = future[0];
    setHistory((items) => [...items.slice(-29), clone(draftSpec)]);
    setFuture((items) => items.slice(1));
    setDraftSpec(clone(next));
  };

  const updateFilter = (field, value) => {
    setFilters((current) => {
      const next = { ...current, [field]: value };
      onFiltersChange?.(next, editMode ? draftSpec : null);
      onContextChange?.({ widgetId: focusedWidgetId, filters: next });
      return next;
    });
  };

  const clearFilters = () => {
    setFilters({});
    onFiltersChange?.({}, editMode ? draftSpec : null);
    onContextChange?.({ widgetId: focusedWidgetId, filters: {} });
  };

  const applyCrossFilter = (widget, value) => {
    if (!widget.cross_filter || value == null) return;
    updateFilter(
      widget.dimension,
      String(filters[widget.dimension] ?? '') === String(value) ? '' : value,
    );
  };

  const beginEditing = () => {
    setDraftSpec(clone(spec));
    setHistory([]);
    setFuture([]);
    setSelectedWidgetId(null);
    if (draftStorageKey) {
      try {
        const saved = JSON.parse(window.localStorage.getItem(draftStorageKey) || 'null');
        setStoredDraft(saved?.spec && JSON.stringify(saved.spec) !== savedSpecSignature ? saved : null);
      } catch {
        window.localStorage.removeItem(draftStorageKey);
        setStoredDraft(null);
      }
    }
    setEditMode(true);
  };

  const cancelEditing = () => {
    if (dirty && !window.confirm(tx('discard_confirm'))) return;
    if (draftStorageKey) window.localStorage.removeItem(draftStorageKey);
    setEditMode(false);
    setSelectedWidgetId(null);
    setHistory([]);
    setFuture([]);
    onCancelEdit?.();
  };

  const saveEditing = async () => {
    const result = await onSaveSpec?.(draftSpec);
    if (!result) return;
    if (draftStorageKey) window.localStorage.removeItem(draftStorageKey);
    setStoredDraft(null);
    setLastDraftSavedAt(null);
    setEditMode(false);
  };

  const addWidget = (kind) => {
    if (kind === 'kpi') {
      commitSpec((current) => ({
        ...current,
        kpis: [...(current.kpis || []), makeDashboardKpi(dashboard?.schema || [], locale)].slice(0, 6),
      }));
    } else {
      const widget = makeDashboardWidget(dashboard?.schema || [], kind, locale);
      commitSpec((current) => ({
        ...current,
        widgets: [...(current.widgets || []), widget].slice(0, 12),
      }));
      setSelectedWidgetId(widget.id);
    }
    setAddMenuOpen(false);
  };

  const updateWidgetById = (widgetId, updates) => {
    commitSpec((current) => ({
      ...current,
      widgets: (current.widgets || []).map((widget) => (
        widget.id === widgetId ? { ...widget, ...updates } : widget
      )),
    }));
  };

  const updateWidget = (updates) => {
    if (!selectedWidgetId) return;
    updateWidgetById(selectedWidgetId, updates);
  };

  const bindFieldToWidget = (widgetId, well, columnName, aggregation) => {
    commitSpec((current) => ({
      ...current,
      widgets: (current.widgets || []).map((widget) => {
        if (widget.id !== widgetId || widget.kind === 'table') return widget;
        const result = bindChartField(
          widget,
          well,
          columnName,
          dashboard?.schema || [],
          aggregation,
        );
        return result.error ? widget : result.widget;
      }),
    }));
  };

  const removeWidget = (widgetId) => {
    commitSpec((current) => ({
      ...current,
      widgets: (current.widgets || []).filter((widget) => widget.id !== widgetId),
    }));
    if (selectedWidgetId === widgetId) setSelectedWidgetId(null);
  };

  const duplicateWidget = (widget) => {
    const copyWidget = {
      ...clone(widget),
      id: `widget-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      title: `${widget.title} ${tx('copy')}`,
    };
    commitSpec((current) => ({
      ...current,
      widgets: [...(current.widgets || []), copyWidget].slice(0, 12),
    }));
    setSelectedWidgetId(copyWidget.id);
  };

  const removeKpi = (index) => {
    commitSpec((current) => ({
      ...current,
      kpis: (current.kpis || []).filter((_, itemIndex) => itemIndex !== index),
    }));
  };

  const updateKpi = (index, updates) => {
    commitSpec((current) => ({
      ...current,
      kpis: (current.kpis || []).map((kpi, itemIndex) => (
        itemIndex === index ? { ...kpi, ...updates } : kpi
      )),
    }));
  };

  const dropWidget = (targetId) => {
    if (!draggedWidgetId) return;
    commitSpec((current) => ({
      ...current,
      widgets: reorderDashboardWidgets(current.widgets, draggedWidgetId, targetId),
    }));
    setDraggedWidgetId(null);
  };

  return (
    <div data-dashboard-export className="overflow-hidden rounded-2xl border border-slate-200 bg-[#f4f5f7] shadow-sm dark:border-slate-800 dark:bg-zinc-950">
      <div className="flex flex-col gap-4 border-b border-slate-200 bg-white px-5 py-4 dark:border-slate-800 dark:bg-slate-900 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-950 text-white dark:bg-white dark:text-slate-950">
            <LayoutDashboard size={18} />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-bold text-slate-950 dark:text-white">
              {activeSpec.title || tx('adaptive_dashboard')}
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-slate-400">
              <span className="inline-flex items-center gap-1"><Database size={11} />{sourceLabel}</span>
              <span className="inline-flex items-center gap-1">
                <Rows3 size={11} />
                {formatDashboardValue(dashboard?.row_count || 0, locale)} {tx('rows')}
              </span>
              <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                {tx('full_dataset')}
              </span>
              {hasActiveFilters && Number.isFinite(Number(dashboard?.filtered_row_count)) && (
                <span className="font-semibold text-blue-600 dark:text-blue-400">
                  {formatDashboardValue(dashboard.filtered_row_count, locale)} {tx('matching_rows')}
                </span>
              )}
              {dashboard?.analysis_intent?.primary && (
                <span className="font-semibold text-violet-600 dark:text-violet-400">
                  {tx('intent')}: {dashboard.analysis_intent.primary}
                  {Number.isFinite(Number(dashboard?.dashboard_planning?.active_spec_score?.score))
                    ? ` · ${Math.round(Number(dashboard.dashboard_planning.active_spec_score.score))}/100`
                    : ''}
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {editMode ? (
            <>
              <ToolbarButton onClick={undo} disabled={!history.length}>{tx('undo')}</ToolbarButton>
              <ToolbarButton onClick={redo} disabled={!future.length}>{tx('redo')}</ToolbarButton>
              <ToolbarButton onClick={() => onAutoLayout?.()} disabled={busy}>
                <RefreshCw size={13} />{tx('reset_layout')}
              </ToolbarButton>
              <div className="relative">
                <ToolbarButton onClick={() => setAddMenuOpen((open) => !open)}>
                  <Plus size={13} />{tx('add_widget')}
                </ToolbarButton>
                {addMenuOpen && (
                  <div className="absolute right-0 top-10 z-40 w-44 rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl dark:border-slate-700 dark:bg-slate-900">
                    {[
                      ['chart', tx('chart')],
                      ['table', tx('detail_table')],
                      ['kpi', 'KPI'],
                    ].map(([kind, label]) => (
                      <button key={kind} type="button" onClick={() => addWidget(kind)} className="w-full rounded-lg px-3 py-2 text-left text-xs hover:bg-slate-50 dark:hover:bg-slate-800">
                        {label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <ToolbarButton onClick={() => onPreviewSpec?.(draftSpec)} disabled={busy}>
                <Eye size={13} />{tx('preview')}
              </ToolbarButton>
              <ToolbarButton onClick={cancelEditing} disabled={busy}><X size={13} />{tx('cancel')}</ToolbarButton>
              <button type="button" onClick={saveEditing} disabled={busy || !dirty} className="btn-primary inline-flex items-center gap-2 px-3 py-2 text-[11px]">
                {busy ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                {tx('apply_save')}
              </button>
            </>
          ) : !readOnly ? (
            <>
              <ToolbarButton onClick={onRegenerate} disabled={busy}>
                <RefreshCw size={13} className={busy ? 'animate-spin' : ''} />
                {tx('refresh_data')}
              </ToolbarButton>
              <ToolbarButton onClick={beginEditing}><PencilLine size={13} />{tx('customize')}</ToolbarButton>
            </>
          ) : null}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-slate-50/90 px-5 py-2.5 text-[10px] dark:border-slate-800 dark:bg-slate-950/50">
        <span className="font-bold uppercase tracking-[0.14em] text-slate-400">{tx('journey_ask')}</span>
        <span className="text-slate-300">→</span>
        <span className="font-bold uppercase tracking-[0.14em] text-emerald-700 dark:text-emerald-400">{tx('journey_prove')}</span>
        <span className="text-slate-300">→</span>
        <span className="font-bold uppercase tracking-[0.14em] text-violet-700 dark:text-violet-400">{tx('journey_pin')}</span>
        <span className="ml-1 text-slate-500 dark:text-slate-400">{tx('journey_hint')}</span>
      </div>
      {dashboard?.planner?.fallback && (
        <div className="border-b border-amber-200 bg-amber-50 px-5 py-2.5 text-xs text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300">
          {tx('planner_fallback')}
        </div>
      )}

      {editMode && (
        <div className="grid gap-4 border-b border-amber-200 bg-amber-50/70 px-5 py-4 dark:border-amber-900/50 dark:bg-amber-950/10 lg:grid-cols-[1fr_auto]">
          <label className="min-w-0">
            <span className="mb-1 block text-[10px] font-semibold text-amber-800 dark:text-amber-300">{tx('dashboard_title')}</span>
            <input
              value={draftSpec.title || ''}
              maxLength={160}
              onChange={(event) => commitSpec((current) => ({ ...current, title: event.target.value }))}
              className="w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-xs outline-none focus:border-amber-500 dark:border-amber-900 dark:bg-slate-900"
            />
          </label>
          <div className="lg:self-end">
            <label className="block">
              <span className="mb-1 block text-[10px] font-semibold text-amber-800 dark:text-amber-300">{tx('presentation')}</span>
              <select
                value={draftSpec.presentation?.variant || 'executive'}
                onChange={(event) => commitSpec((current) => upgradeDashboardSpecV4(current, event.target.value))}
                className="w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-xs outline-none focus:border-amber-500 dark:border-amber-900 dark:bg-slate-900"
              >
                <option value="executive">{tx('variant_executive')}</option>
                <option value="analytical">{tx('variant_analytical')}</option>
                <option value="operational">{tx('variant_operational')}</option>
              </select>
            </label>
            <div className="mt-1 text-[9px] leading-relaxed text-amber-800/75 dark:text-amber-300/75">
            <div>{dirty ? tx('unsaved_changes') : tx('saved')}</div>
            {lastDraftSavedAt && <div className="mt-0.5">{tx('draft_saved')} {lastDraftSavedAt.toLocaleTimeString(locale === 'en' ? 'en-US' : 'th-TH')}</div>}
            </div>
          </div>
          <form
            className="flex flex-col gap-2 lg:col-span-2 sm:flex-row"
            onSubmit={async (event) => {
              event.preventDefault();
              if (!aiPrompt.trim() || busy) return;
              const result = await onPlanSpec?.(aiPrompt.trim(), draftSpec);
              if (result) setAiPrompt('');
            }}
          >
            <div className="relative min-w-0 flex-1">
              <PencilLine size={14} className="absolute left-3 top-2.5 text-stone-500" />
              <input
                value={aiPrompt}
                onChange={(event) => setAiPrompt(event.target.value)}
                maxLength={1000}
                placeholder={tx('ai_prompt')}
                className="w-full rounded-lg border border-amber-200 bg-white py-2 pl-9 pr-3 text-xs outline-none focus:border-amber-500 dark:border-amber-900 dark:bg-slate-900"
              />
            </div>
            <button type="submit" disabled={!aiPrompt.trim() || busy} className="btn-primary inline-flex items-center justify-center gap-2 px-4 py-2 text-xs">
              {busy ? <Loader2 size={13} className="animate-spin" /> : <LayoutDashboard size={13} />}
              {tx('plan_preview')}
            </button>
          </form>
          {(dashboard?.dashboard_planning?.design_candidates || []).length > 0 && (
            <div className="grid gap-2 lg:col-span-2 sm:grid-cols-3">
              {dashboard.dashboard_planning.design_candidates.map((candidate) => (
                <button
                  key={candidate.name}
                  type="button"
                  disabled={busy}
                  onClick={async () => {
                    const candidateSpec = upgradeDashboardSpecV4(candidate.spec, candidate.variant);
                    commitSpec(candidateSpec);
                    await onPreviewSpec?.(candidateSpec);
                  }}
                  className={`rounded-xl border px-3 py-2.5 text-left text-[10px] transition disabled:opacity-50 ${
                    draftSpec.presentation?.variant === candidate.variant
                      ? 'border-violet-400 bg-violet-50 text-violet-900 dark:border-violet-700 dark:bg-violet-950/30 dark:text-violet-200'
                      : 'border-amber-200 bg-white text-slate-600 hover:border-amber-400 dark:border-amber-900 dark:bg-slate-900 dark:text-slate-300'
                  }`}
                >
                  <div className="font-bold">{tx(`variant_${candidate.variant}`)}</div>
                  <div className="mt-1 opacity-70">{candidate.score}/100 · {(candidate.coverage || []).join(', ')}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {editMode && storedDraft && (
        <div className="flex flex-col gap-3 border-b border-blue-200 bg-blue-50 px-5 py-3 text-xs text-blue-900 dark:border-blue-900/60 dark:bg-blue-950/20 dark:text-blue-200 sm:flex-row sm:items-center sm:justify-between">
          <div>
            {tx('newer_draft')}
            {storedDraft.saved_at && <span className="ml-1 opacity-70">{new Date(storedDraft.saved_at).toLocaleString(locale === 'en' ? 'en-US' : 'th-TH')}</span>}
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={() => { setHistory([clone(savedSpec || spec)]); setDraftSpec(clone(storedDraft.spec)); setStoredDraft(null); }} className="rounded-lg bg-blue-700 px-3 py-1.5 font-semibold text-white">{tx('restore')}</button>
            <button type="button" onClick={() => { if (draftStorageKey) window.localStorage.removeItem(draftStorageKey); setStoredDraft(null); }} className="rounded-lg border border-blue-300 px-3 py-1.5 font-semibold dark:border-blue-800">{tx('discard')}</button>
          </div>
        </div>
      )}

      {activeSpec.presentation?.show_story !== false && dashboard?.story?.headline && (
        <section className="border-b border-slate-200 bg-white px-5 py-5 dark:border-slate-800 dark:bg-slate-900">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
            <div>
              <div className="mb-2 text-[9px] font-bold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                {tx('story')}
              </div>
              <h2 className="max-w-4xl font-serif text-xl font-bold leading-snug text-slate-950 dark:text-white">
                {isEn ? dashboard.story.headline : (dashboard.story.headline_th || dashboard.story.headline)}
              </h2>
              <p className="mt-2 max-w-4xl text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                {isEn ? dashboard.story.summary : (dashboard.story.summary_th || dashboard.story.summary)}
              </p>
            </div>
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-[9px] font-semibold text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/20 dark:text-emerald-300">
              {dashboard.story.evidence_ids?.length || 0} {tx('verified_evidence')}
            </div>
          </div>
          {activeSpec.presentation?.show_evidence !== false && (dashboard.story.evidence || []).length > 0 && (
            <details open className="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-[10px] dark:border-slate-700 dark:bg-slate-950">
              <summary className="cursor-pointer font-semibold text-slate-600 dark:text-slate-300">
                {tx('inspect_evidence')}
              </summary>
              <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                {dashboard.story.evidence.slice(0, 12).map((evidence) => (
                  <div key={evidence.id} className="rounded-lg border border-slate-200 bg-white px-3 py-2 dark:border-slate-800 dark:bg-slate-900">
                    <div className="font-mono text-[9px] text-violet-600 dark:text-violet-400">{evidence.id}</div>
                    {evidence.kind === 'kpi' && <div className="mt-1">{evidence.label}: {formatDashboardValue(evidence.value, locale)} · {evidence.formula}</div>}
                    {evidence.kind === 'widget' && <div className="mt-1">{evidence.points} {tx('aggregate_points')}</div>}
                    {evidence.kind === 'query_context' && <div className="mt-1">{formatDashboardValue(evidence.filtered_row_count ?? evidence.source_row_count, locale)} {tx('rows_scope')}</div>}
                    {['driver', 'movement', 'anomaly', 'action'].includes(evidence.kind) && <div className="mt-1">{isEn ? evidence.summary : (evidence.summary_th || evidence.summary)}</div>}
                  </div>
                ))}
              </div>
            </details>
          )}
        </section>
      )}

      {(dashboard?.decision_insights || []).length > 0 && (
        <div className="border-b border-slate-200 bg-slate-50/80 px-5 py-4 dark:border-slate-800 dark:bg-slate-950/60">
          <div className="mb-3 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-600 dark:text-slate-400">
            <Lightbulb size={13} />
            {tx('decision_insights')}
          </div>
          <div className="grid gap-3 lg:grid-cols-3">
            {dashboard.decision_insights.map((insight, index) => {
              const action = insight.action || { status: 'open' };
              const actionKey = insight.action_key || `${insight.kind}:${index}`;
              return (
              <div
                key={`${insight.kind}-${index}`}
                className={`rounded-xl border bg-white px-4 py-3 shadow-sm dark:bg-slate-900 ${
                  insight.severity === 'warning'
                    ? 'border-amber-300 dark:border-amber-800'
                    : insight.severity === 'action'
                      ? 'border-violet-300 dark:border-violet-800'
                      : 'border-slate-200 dark:border-slate-700'
                }`}
              >
                <div className="text-[10px] font-bold text-slate-800 dark:text-slate-100">
                  {isEn ? insight.title : (insight.title_th || insight.title)}
                </div>
                <div className="mt-1.5 text-[10px] leading-relaxed text-slate-500 dark:text-slate-400">
                  {isEn ? insight.summary : (insight.summary_th || insight.summary)}
                </div>
                {!briefMode && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {onAskAboutInsight && (
                      <button
                        type="button"
                        onClick={() => onAskAboutInsight(insight)}
                        className="rounded-lg border border-amber-200 bg-amber-50 px-2 py-1 text-[9px] font-semibold text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300"
                      >
                        {isEn ? 'Ask why' : 'ถามว่าทำไม'}
                      </button>
                    )}
                    {onInsightAction && !readOnly && (
                      <>
                        <button
                          type="button"
                          disabled={action.status === 'done'}
                          onClick={() => onInsightAction(actionKey, 'done')}
                          className="rounded-lg border border-emerald-200 px-2 py-1 text-[9px] font-semibold text-emerald-700 disabled:opacity-40 dark:border-emerald-900/60 dark:text-emerald-300"
                        >
                          {action.status === 'done' ? (isEn ? 'Done' : 'ทำแล้ว') : (isEn ? 'Mark done' : 'ทำแล้ว')}
                        </button>
                        <button
                          type="button"
                          disabled={action.status === 'dismissed'}
                          onClick={() => onInsightAction(actionKey, 'dismissed')}
                          className="rounded-lg border border-slate-200 px-2 py-1 text-[9px] font-semibold text-slate-500 disabled:opacity-40 dark:border-slate-700"
                        >
                          {isEn ? 'Dismiss' : 'ข้าม'}
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>
              );
            })}
          </div>
        </div>
      )}

      {(dashboard?.chart_guardrails || []).length > 0 && (
        <div className="border-b border-blue-200 bg-blue-50 px-5 py-2.5 text-[10px] text-blue-800 dark:border-blue-900/50 dark:bg-blue-950/20 dark:text-blue-300">
          {tx('guardrails_applied', { count: dashboard.chart_guardrails.length })}
        </div>
      )}

      {(dashboard?.semantic_warnings || []).length > 0 && (
        <div className="border-b border-slate-200 bg-white px-5 py-3 dark:border-slate-800 dark:bg-slate-900">
          <div className="mb-2 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.12em] text-amber-700 dark:text-amber-400">
            <AlertTriangle size={13} />
            {tx('visualization_checks')}
          </div>
          <div className="grid gap-2 lg:grid-cols-2">
            {dashboard.semantic_warnings.map((warning, index) => (
              <button
                key={`${warning.code}-${warning.widget_id}-${index}`}
                type="button"
                onClick={() => editMode && warning.widget_id && setSelectedWidgetId(warning.widget_id)}
                className={`rounded-lg border px-3 py-2 text-left text-[10px] ${
                  warning.severity === 'error'
                    ? 'border-red-200 bg-red-50 text-red-800 dark:border-red-900/60 dark:bg-red-950/20 dark:text-red-300'
                    : 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-200'
                }`}
              >
                <div className="font-semibold">{isEn ? warning.message : warning.message_th}</div>
                <div className="mt-0.5 opacity-75">{isEn ? warning.suggestion : warning.suggestion_th}</div>
              </button>
            ))}
          </div>
        </div>
      )}

      {(editMode || activeSpec.filters?.length > 0) && (
        <div className="border-b border-slate-200 bg-white px-5 py-4 dark:border-slate-800 dark:bg-slate-900">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500">
              <SlidersHorizontal size={13} />
              {tx('report_filters')}
            </div>
            {Object.values(filters).some((value) => (
              typeof value === 'object' ? Object.values(value).some(Boolean) : Boolean(value)
            )) && (
              <button type="button" onClick={clearFilters} className="text-[10px] font-semibold text-amber-700 hover:underline dark:text-amber-400">
                {tx('clear_all')}
              </button>
            )}
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {activeSpec.filters.map((filter) => {
              const column = schemaByName[filter.field] || {};
              if (filter.kind === 'date') {
                const dateValue = filters[filter.field] || {};
                return (
                  <div key={filter.field} className="relative rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-950">
                    <div className="mb-2 flex items-center gap-1 text-[9px] font-semibold text-slate-400">
                      <Filter size={10} /> {filter.field}
                    </div>
                    {editMode && <button type="button" onClick={() => commitSpec((current) => ({ ...current, filters: current.filters.filter((item) => item.field !== filter.field) }))} className="absolute right-2 top-2 text-slate-400 hover:text-red-600"><X size={12} /></button>}
                    <div className="grid grid-cols-2 gap-2">
                      <input type="date" value={dateValue.from || ''} onChange={(event) => updateFilter(filter.field, { ...dateValue, from: event.target.value })} className="min-w-0 rounded-lg border border-slate-200 bg-white px-2 py-2 text-[10px] dark:border-slate-700 dark:bg-slate-900" />
                      <input type="date" value={dateValue.to || ''} onChange={(event) => updateFilter(filter.field, { ...dateValue, to: event.target.value })} className="min-w-0 rounded-lg border border-slate-200 bg-white px-2 py-2 text-[10px] dark:border-slate-700 dark:bg-slate-900" />
                    </div>
                  </div>
                );
              }
              return (
                <label key={filter.field} className="relative rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-950">
                  <span className="mb-2 flex items-center gap-1 text-[9px] font-semibold text-slate-400"><Filter size={10} /> {filter.field}</span>
                  {editMode && <button type="button" onClick={() => commitSpec((current) => ({ ...current, filters: current.filters.filter((item) => item.field !== filter.field) }))} className="absolute right-2 top-2 text-slate-400 hover:text-red-600"><X size={12} /></button>}
                  <select value={filters[filter.field] || ''} onChange={(event) => updateFilter(filter.field, event.target.value)} className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-xs font-medium outline-none focus:border-amber-500 dark:border-slate-700 dark:bg-slate-900">
                    <option value="">{tx('all')}</option>
                    {(column.options || []).map((value) => <option key={value} value={value}>{value}</option>)}
                  </select>
                </label>
              );
            })}
            {editMode && activeSpec.filters.length < 8 && (
              <label className="rounded-xl border border-dashed border-slate-300 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
                <span className="mb-2 block text-[9px] font-semibold text-slate-400">{tx('add_filter')}</span>
                <select
                  value=""
                  onChange={(event) => {
                    const column = schemaByName[event.target.value];
                    if (column) commitSpec((current) => ({ ...current, filters: [...current.filters, { field: column.name, kind: column.kind }] }));
                  }}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-xs dark:border-slate-700 dark:bg-slate-950"
                >
                  <option value="">{tx('choose_field')}</option>
                  {(dashboard?.schema || []).filter((column) => !activeSpec.filters.some((filter) => filter.field === column.name)).map((column) => <option key={column.name} value={column.name}>{column.name}</option>)}
                </select>
              </label>
            )}
          </div>
        </div>
      )}

      <div className="p-4 md:p-5">
        {hasActiveFilters && dashboard?.filtered_row_count === 0 && (
          <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-200">
            {tx('no_filter_rows')}
          </div>
        )}
        <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {(activeSpec.kpis || []).map((kpi, index) => {
            const computedKpi = dashboard?.kpis?.[index] || kpi;
            return (
              <div key={`${kpi.label}-${index}`} className="relative rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                {editMode && (
                  <button type="button" onClick={() => removeKpi(index)} className="absolute right-2 top-2 rounded p-1 text-slate-300 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/30">
                    <Trash2 size={12} />
                  </button>
                )}
                <div className="text-xl font-bold tracking-tight text-slate-950 dark:text-white">{formatDashboardValue(computedKpi.value, locale, kpi.format, kpi.currency)}</div>
                {editMode ? (
                  <div className="mt-2 space-y-2">
                    <input value={kpi.label || ''} onChange={(event) => updateKpi(index, { label: event.target.value })} className="w-full rounded border border-slate-200 px-2 py-1 text-[10px] dark:border-slate-700 dark:bg-slate-950" />
                    <div className="grid grid-cols-2 gap-1">
                      <select value={kpi.kind} onChange={(event) => updateKpi(index, { kind: event.target.value, field: event.target.value === 'count' ? null : (kpi.field || fieldGroups.measures[0]?.name) })} className="rounded border border-slate-200 px-1 py-1 text-[9px] dark:border-slate-700 dark:bg-slate-950">
                        <option value="count">COUNT</option><option value="sum">SUM</option><option value="average">AVG</option>
                      </select>
                      <select disabled={kpi.kind === 'count'} value={kpi.field || ''} onChange={(event) => updateKpi(index, { field: event.target.value })} className="min-w-0 rounded border border-slate-200 px-1 py-1 text-[9px] dark:border-slate-700 dark:bg-slate-950">
                        {fieldGroups.measures.map((column) => <option key={column.name} value={column.name}>{column.name}</option>)}
                      </select>
                    </div>
                    <div className="grid grid-cols-2 gap-1">
                      <select value={kpi.format || 'auto'} onChange={(event) => updateKpi(index, { format: event.target.value })} className="rounded border border-slate-200 px-1 py-1 text-[9px] dark:border-slate-700 dark:bg-slate-950">
                        <option value="auto">AUTO</option><option value="number">NUMBER</option><option value="compact">COMPACT</option><option value="percent">PERCENT</option><option value="currency">CURRENCY</option>
                      </select>
                      {kpi.format === 'currency' && <input value={kpi.currency || 'THB'} maxLength={3} onChange={(event) => updateKpi(index, { currency: event.target.value.toUpperCase() })} className="min-w-0 rounded border border-slate-200 px-1 py-1 text-[9px] uppercase dark:border-slate-700 dark:bg-slate-950" />}
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="mt-1 truncate text-[10px] font-medium text-slate-400">{kpi.label}</div>
                    <div className="mt-1 text-[9px] text-slate-300 dark:text-slate-600">{kpi.kind === 'count' ? 'COUNT(*)' : `${kpi.kind === 'average' ? 'AVG' : 'SUM'}(${kpi.field})`}</div>
                  </>
                )}
              </div>
            );
          })}
        </div>

        <div className={`grid grid-cols-1 gap-5 xl:grid-cols-12 ${busy ? 'opacity-60' : ''}`}>
          {orderedWidgets.map((widget) => {
            const computedWidget = (dashboard?.widgets || []).find((item) => item.id === widget.id) || widget;
            const selected = editMode && selectedWidgetId === widget.id;
            const contextFocused = !editMode && focusedWidgetId === widget.id;
            const section = sectionByWidget[widget.id];
            const sectionStart = sectionByFirstWidget[widget.id];
            const effectiveSpan = section?.layout === 'featured' || section?.layout === 'detail'
              ? 12
              : section?.layout === 'dense' ? 4 : widget.span;
            return (
              <Fragment key={widget.id}>
              {sectionStart && (
                <div className="xl:col-span-12 mt-2 border-t border-slate-200 pt-5 first:mt-0 first:border-t-0 first:pt-0 dark:border-slate-800">
                  <div className="flex flex-wrap items-end justify-between gap-2">
                    <div>
                      <div className="text-[9px] font-bold uppercase tracking-[0.14em] text-violet-600 dark:text-violet-400">{tx(`section_purpose_${sectionStart.purpose}`)}</div>
                      {editMode ? (
                        <input
                          value={sectionStart.title || ''}
                          maxLength={160}
                          onChange={(event) => commitSpec((current) => ({
                            ...current,
                            sections: (current.sections || []).map((item) => (
                              item.id === sectionStart.id ? { ...item, title: event.target.value } : item
                            )),
                          }))}
                          className="mt-1 w-full max-w-xl rounded-lg border border-slate-200 bg-white px-3 py-2 font-serif text-base font-bold dark:border-slate-700 dark:bg-slate-950"
                        />
                      ) : (
                        <h3 className="mt-1 font-serif text-lg font-bold text-slate-950 dark:text-white">{sectionTitle(sectionStart)}</h3>
                      )}
                      {sectionStart.subtitle && <p className="mt-1 text-[10px] text-slate-400">{sectionStart.subtitle}</p>}
                    </div>
                    {editMode ? (
                      <select
                        value={sectionStart.layout || 'balanced'}
                        onChange={(event) => commitSpec((current) => ({
                          ...current,
                          sections: (current.sections || []).map((item) => (
                            item.id === sectionStart.id ? { ...item, layout: event.target.value } : item
                          )),
                        }))}
                        className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[9px] font-semibold text-slate-500 dark:border-slate-700 dark:bg-slate-950"
                      >
                        <option value="featured">{tx('layout_featured')}</option>
                        <option value="balanced">{tx('layout_balanced')}</option>
                        <option value="dense">{tx('layout_dense')}</option>
                        <option value="detail">{tx('layout_detail')}</option>
                      </select>
                    ) : (
                      <div className="rounded-full border border-slate-200 px-2.5 py-1 text-[9px] font-semibold text-slate-400 dark:border-slate-700">{tx(`layout_${sectionStart.layout}`)}</div>
                    )}
                  </div>
                </div>
              )}
              <article
                onDragOver={(event) => {
                  if (editMode) event.preventDefault();
                }}
                onDrop={(event) => {
                  const raw = event.dataTransfer.getData(FIELD_DRAG);
                  if (raw) {
                    event.preventDefault();
                    event.stopPropagation();
                    try {
                      const column = JSON.parse(raw);
                      const well = column.kind === 'number' || column.name === COUNT_FIELD ? 'y' : 'x';
                      bindFieldToWidget(widget.id, well, column.name);
                      setSelectedWidgetId(widget.id);
                    } catch {
                      /* ignore */
                    }
                    return;
                  }
                  dropWidget(widget.id);
                }}
                onClick={() => {
                  if (editMode) setSelectedWidgetId(widget.id);
                  else onContextChange?.({ widgetId: widget.id, filters });
                }}
                onKeyDown={(event) => {
                  if (editMode || !['Enter', ' '].includes(event.key)) return;
                  event.preventDefault();
                  onContextChange?.({ widgetId: widget.id, filters });
                }}
                role={!editMode ? 'button' : undefined}
                tabIndex={!editMode ? 0 : undefined}
                aria-pressed={!editMode ? contextFocused : undefined}
                className={`${spanClass(effectiveSpan)} ${selected ? 'ring-2 ring-amber-500' : ''} ${contextFocused ? 'ring-2 ring-orange-400 ring-offset-2 dark:ring-offset-slate-950' : ''} min-w-0 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-400 dark:border-slate-800 dark:bg-slate-900`}
              >
                {editMode && (
                  <div
                    draggable
                    onDragStart={(event) => {
                      event.dataTransfer.effectAllowed = 'move';
                      setDraggedWidgetId(widget.id);
                    }}
                    className="flex cursor-grab items-center justify-between border-b border-slate-100 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-950"
                  >
                    <span className="flex min-w-0 flex-1 items-center gap-1.5 text-[10px] font-semibold text-slate-500">
                      <GripVertical size={12} />
                      {widget.kind === 'chart' ? (
                        <input
                          value={widget.title || ''}
                          maxLength={160}
                          placeholder={tx('chart_name')}
                          onClick={(event) => event.stopPropagation()}
                          onChange={(event) => updateWidgetById(widget.id, { title: event.target.value })}
                          className="min-w-0 flex-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-800 outline-none focus:border-amber-500 dark:border-white/12 dark:bg-zinc-950 dark:text-zinc-100"
                        />
                      ) : (
                        <span className="truncate">{widget.title}</span>
                      )}
                    </span>
                    <div className="flex items-center gap-1">
                      <button type="button" onClick={(event) => { event.stopPropagation(); updateWidgetById(widget.id, { span: widget.span === 12 ? 6 : 12 }); }} className="rounded p-1.5 text-slate-400 hover:bg-white hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-white" title={tx('resize')}>
                        {widget.span === 12 ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
                      </button>
                      <button type="button" onClick={(event) => { event.stopPropagation(); duplicateWidget(widget); }} className="rounded p-1.5 text-slate-400 hover:bg-white hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-white"><Copy size={12} /></button>
                      <button type="button" onClick={(event) => { event.stopPropagation(); removeWidget(widget.id); }} className="rounded p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/30"><Trash2 size={12} /></button>
                    </div>
                  </div>
                )}
                {widget.kind === 'table' ? (
                  <>
                    {!editMode && <div className="border-b border-slate-100 px-4 py-3 text-xs font-semibold dark:border-slate-800">{widget.title}</div>}
                    {dashboard?.planner?.rationale?.[widget.id] && <div className="border-b border-blue-100 bg-blue-50/60 px-4 py-2 text-[9px] text-blue-700 dark:border-blue-900/40 dark:bg-blue-950/20 dark:text-blue-300">{dashboard.planner.rationale[widget.id]}</div>}
                    <div className="max-h-[440px] overflow-auto">
                      <table className="w-full min-w-[760px] border-collapse text-left text-[10px]">
                        <thead className="sticky top-0 z-10 bg-slate-50 text-slate-500 dark:bg-slate-950">
                          <tr>{(widget.columns || []).map((column) => <th key={column} className="border-b border-slate-200 px-3 py-2.5 font-semibold dark:border-slate-800">{column}</th>)}</tr>
                        </thead>
                        <tbody>
                          {(computedWidget.data || []).map((row, index) => (
                            <tr key={index} className="border-b border-slate-100 odd:bg-white even:bg-slate-50/60 dark:border-slate-800 dark:odd:bg-slate-900 dark:even:bg-slate-950/40">
                              {(widget.columns || []).map((column) => <td key={column} className="max-w-[260px] truncate px-3 py-2">{formatDashboardValue(row[column], locale)}</td>)}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                ) : (
                  <div className="p-4">
                    {!editMode && (
                      <div className="mb-2 flex items-start justify-between gap-2">
                        <p className="truncate text-xs font-semibold text-slate-800 dark:text-zinc-100">{widget.title}</p>
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            setInspectedWidgetId(widget.id);
                          }}
                          className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-slate-200 px-2 py-1 text-[10px] font-semibold text-slate-600 hover:border-amber-400 dark:border-white/12 dark:text-zinc-300"
                        >
                          <ShieldCheck size={12} />
                          {tx('inspect_chart')}
                        </button>
                      </div>
                    )}
                    {dashboard?.planner?.rationale?.[widget.id] && <div className="mb-2 rounded-lg bg-blue-50 px-3 py-2 text-[9px] text-blue-700 dark:bg-blue-950/20 dark:text-blue-300">{dashboard.planner.rationale[widget.id]}</div>}
                    <ChartRenderer
                      embedded
                      hideTitle
                      data={{
                        chart_type: widget.chart_type,
                        config: {
                          title: widget.title,
                          xAxis: 'name',
                          xAxisLabel: widget.dimension || tx('x_axis'),
                          yAxisLabel: widget.aggregation === 'count' || !widget.measure ? 'COUNT(*)' : widget.measure,
                          color: widget.color,
                          palette: activeSpec.presentation?.palette,
                        },
                        data: computedWidget.data || [],
                      }}
                      onCategoryClick={!editMode && widget.cross_filter ? (value) => applyCrossFilter(widget, value) : undefined}
                      selectedCategory={filters[widget.dimension]}
                    />
                    {!editMode && widget.cross_filter && <div className="mt-1 text-center text-[9px] text-slate-400">{tx('cross_filter_hint')}</div>}
                    {!editMode && (
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setInspectedWidgetId(widget.id);
                        }}
                        className="mt-1 w-full text-center text-[9px] text-slate-400 hover:text-amber-700 dark:hover:text-amber-300"
                      >
                        {widget.aggregation === 'count' ? 'COUNT(*)' : `${widget.aggregation === 'average' ? 'AVG' : 'SUM'}(${widget.measure})`} · {tx('grouped_by')} {widget.dimension} · Top {widget.limit || 20}
                      </button>
                    )}
                  </div>
                )}
              </article>
              </Fragment>
            );
          })}
          {!editMode && savedCharts.map((chart) => (
            <article key={chart.id} className="min-w-0 rounded-xl border border-amber-200 bg-white p-4 shadow-sm dark:border-amber-900/60 dark:bg-slate-900 xl:col-span-6">
              <div className="mb-2 text-[9px] font-bold uppercase tracking-wider text-amber-700 dark:text-amber-400">{tx('saved_snapshot')}</div>
              <ChartRenderer embedded data={{ chart_type: chart.chart_type, config: { ...chart.config, title: chart.title }, data: chart.data }} />
            </article>
          ))}
        </div>

        {editMode && selectedWidget && (
          <div className="fixed inset-y-0 right-0 z-[80] w-full max-w-sm overflow-y-auto border-l border-slate-200 bg-white p-5 shadow-2xl dark:border-slate-800 dark:bg-slate-900">
            <div className="mb-5 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-bold"><Settings size={16} />{tx('widget_settings')}</div>
              <button type="button" onClick={() => setSelectedWidgetId(null)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"><X size={15} /></button>
            </div>
            <div className="space-y-4 text-xs">
              <label className="block"><span className="mb-1.5 block text-[10px] font-semibold text-slate-500">{tx('chart_name')}</span><input value={selectedWidget.title || ''} onChange={(event) => updateWidget({ title: event.target.value })} maxLength={160} placeholder={tx('chart_name_placeholder')} className="w-full rounded-lg border border-slate-200 px-3 py-2.5 dark:border-slate-700 dark:bg-slate-950" /></label>
              <label className="block"><span className="mb-1.5 block text-[10px] font-semibold text-slate-500">{tx('width')}</span><select value={selectedWidget.span || 6} onChange={(event) => updateWidget({ span: Number(event.target.value) })} className="w-full rounded-lg border border-slate-200 px-3 py-2.5 dark:border-slate-700 dark:bg-slate-950"><option value="4">1/3</option><option value="6">1/2</option><option value="8">2/3</option><option value="12">{tx('full_width')}</option></select></label>
              {selectedWidget.kind === 'chart' ? (
                <>
                  <label className="block"><span className="mb-1.5 block text-[10px] font-semibold text-slate-500">{tx('chart_type')}</span><select value={selectedWidget.chart_type} onChange={(event) => updateWidget({ chart_type: event.target.value, limit: event.target.value === 'pie' ? Math.min(12, selectedWidget.limit || 12) : selectedWidget.limit })} className="w-full rounded-lg border border-slate-200 px-3 py-2.5 dark:border-slate-700 dark:bg-slate-950"><option value="bar">Bar</option><option value="line">Line</option><option value="area">Area</option><option value="pie">Pie</option><option value="pareto">Pareto</option></select></label>
                  <label className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2.5 dark:border-slate-700"><span>{tx('primary_color')}</span><input type="color" value={selectedWidget.color || '#2563eb'} onChange={(event) => updateWidget({ color: event.target.value })} className="h-8 w-12 cursor-pointer rounded border-0 bg-transparent p-0" /></label>
                  <div>
                    <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">{tx('fields')}</p>
                    <div className="flex flex-wrap gap-1.5">
                      {fieldGroups.dimensions.map((column) => <FieldChip key={column.name} column={column} />)}
                      {fieldGroups.measures.map((column) => <FieldChip key={column.name} column={column} />)}
                      <FieldChip column={{ name: COUNT_FIELD, kind: 'count' }} label="COUNT(*)" />
                    </div>
                    <p className="mt-2 text-[10px] text-slate-400">{tx('drag_fields_hint')}</p>
                  </div>
                  <FieldWell
                    label={tx('x_axis')}
                    value={selectedWidget.dimension}
                    hint={tx('x_axis_hint')}
                    emptyLabel={tx('drop_x_axis')}
                    onDropField={(column) => bindFieldToWidget(selectedWidget.id, 'x', column.name)}
                    onClear={() => updateWidget({ dimension: '', time_grain: null })}
                  />
                  <FieldWell
                    label={tx('y_axis')}
                    value={selectedWidget.aggregation === 'count' || !selectedWidget.measure ? 'COUNT(*)' : selectedWidget.measure}
                    hint={tx('y_axis_hint')}
                    emptyLabel={tx('drop_y_axis')}
                    onDropField={(column) => bindFieldToWidget(selectedWidget.id, 'y', column.name, selectedWidget.aggregation)}
                    onClear={() => updateWidget({ measure: null, aggregation: 'count' })}
                  />
                  <label className="block"><span className="mb-1.5 block text-[10px] font-semibold text-slate-500">{tx('aggregation')}</span><select value={selectedWidget.aggregation} onChange={(event) => {
                    const aggregation = event.target.value;
                    if (aggregation === 'count') {
                      bindFieldToWidget(selectedWidget.id, 'y', COUNT_FIELD);
                      return;
                    }
                    updateWidget({
                      aggregation,
                      measure: selectedWidget.measure || fieldGroups.measures[0]?.name || null,
                    });
                  }} className="w-full rounded-lg border border-slate-200 px-3 py-2.5 dark:border-slate-700 dark:bg-slate-950"><option value="sum">SUM</option><option value="average">AVERAGE</option><option value="count">COUNT</option></select></label>
                  {schemaByName[selectedWidget.dimension]?.kind === 'date' && <label className="block"><span className="mb-1.5 block text-[10px] font-semibold text-slate-500">{tx('time_grain')}</span><select value={selectedWidget.time_grain || 'month'} onChange={(event) => updateWidget({ time_grain: event.target.value })} className="w-full rounded-lg border border-slate-200 px-3 py-2.5 dark:border-slate-700 dark:bg-slate-950"><option value="day">{tx('day')}</option><option value="week">{tx('week')}</option><option value="month">{tx('month')}</option><option value="quarter">{tx('quarter')}</option><option value="year">{tx('year')}</option></select></label>}
                  <label className="block"><span className="mb-1.5 block text-[10px] font-semibold text-slate-500">Top N</span><input type="number" min="5" max={selectedWidget.chart_type === 'pie' ? 12 : 50} value={selectedWidget.limit || 20} onChange={(event) => updateWidget({ limit: Number(event.target.value) })} className="w-full rounded-lg border border-slate-200 px-3 py-2.5 dark:border-slate-700 dark:bg-slate-950" /></label>
                  {schemaByName[selectedWidget.dimension]?.kind !== 'date' && <label className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2.5 dark:border-slate-700"><span>{tx('cross_filter')}</span><input type="checkbox" checked={Boolean(selectedWidget.cross_filter)} onChange={(event) => updateWidget({ cross_filter: event.target.checked })} /></label>}
                </>
              ) : (
                <div>
                  <span className="mb-2 block text-[10px] font-semibold text-slate-500">{tx('visible_columns')}</span>
                  <div className="max-h-72 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2 dark:border-slate-700">
                    {(dashboard?.schema || []).map((column) => <label key={column.name} className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-slate-50 dark:hover:bg-slate-800"><input type="checkbox" checked={(selectedWidget.columns || []).includes(column.name)} onChange={(event) => updateWidget({ columns: event.target.checked ? [...(selectedWidget.columns || []), column.name].slice(0, 12) : (selectedWidget.columns || []).filter((name) => name !== column.name) })} /><span className="truncate">{column.name}</span></label>)}
                  </div>
                </div>
              )}
              <button type="button" onClick={() => setSelectedWidgetId(null)} className="btn-primary inline-flex w-full items-center justify-center gap-2 px-4 py-2.5"><Check size={14} />{tx('done')}</button>
            </div>
          </div>
        )}

        {!editMode && inspectedChart && (
          <div className="fixed inset-0 z-[85] flex justify-end bg-black/20 dark:bg-black/50" onClick={() => setInspectedWidgetId(null)}>
            <aside
              className="h-full w-full max-w-sm overflow-y-auto border-l border-slate-200 bg-white p-5 shadow-2xl dark:border-white/12 dark:bg-zinc-950"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <ShieldCheck size={16} className="text-[#d97706]" />
                  {tx('inspect_chart')}
                </div>
                <button type="button" onClick={() => setInspectedWidgetId(null)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-zinc-800">
                  <X size={15} />
                </button>
              </div>
              <p className="text-sm font-semibold text-slate-900 dark:text-white">{inspectedChart.title}</p>
              <p className="mt-1 text-[11px] uppercase tracking-wider text-slate-500">{inspectedChart.chart_type}</p>
              <dl className="mt-4 space-y-3 text-xs">
                <div>
                  <dt className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{tx('x_axis')}</dt>
                  <dd className="mt-1 font-medium text-slate-800 dark:text-zinc-100">{inspectedChart.wells.x?.field || inspectedChart.wells.axis?.field || '—'}</dd>
                </div>
                <div>
                  <dt className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{tx('y_axis')}</dt>
                  <dd className="mt-1 font-medium text-slate-800 dark:text-zinc-100">
                    {inspectedChart.wells.values?.aggregation === 'count'
                      ? 'COUNT(*)'
                      : `${String(inspectedChart.wells.values?.aggregation || 'sum').toUpperCase()}(${inspectedChart.wells.values?.field || '—'})`}
                  </dd>
                </div>
                <div>
                  <dt className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{tx('formula')}</dt>
                  <dd className="mt-1 font-mono text-[11px] text-slate-700 dark:text-zinc-200">{inspectedChart.formula}</dd>
                </div>
                <div>
                  <dt className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{tx('engine')}</dt>
                  <dd className="mt-1 font-medium">{inspectedChart.engine}</dd>
                </div>
                <div>
                  <dt className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{tx('source_columns')}</dt>
                  <dd className="mt-1">{(inspectedChart.source_columns || []).join(', ') || '—'}</dd>
                </div>
                <div>
                  <dt className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{tx('rows_scope')}</dt>
                  <dd className="mt-1">
                    {formatDashboardValue(inspectedChart.filtered_row_count ?? inspectedChart.row_count ?? 0, locale)}
                    {inspectedChart.point_count != null ? ` · ${inspectedChart.point_count} ${tx('aggregate_points')}` : ''}
                  </dd>
                </div>
              </dl>
            </aside>
          </div>
        )}

        {!busy && (dashboard?.widgets || []).length === 0 && <div className="py-12 text-center text-xs text-slate-400">{tx('no_widgets')}</div>}
      </div>
    </div>
  );
};

export default AdaptiveBiDashboard;
