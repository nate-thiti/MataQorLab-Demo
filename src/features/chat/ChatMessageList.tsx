// @ts-nocheck
import { useRef, useCallback, useEffect, useState, useMemo } from 'react';
import {
  BarChart3,
  LineChart,
  PieChart,
  AreaChart,
  FileDown,
  Globe,
  ShieldCheck,
  ThumbsUp,
  ThumbsDown,
  BadgeCheck,
  AlertTriangle,
  FileSearch,
  Filter,
  LayoutDashboard,
  Loader2,
  Paperclip,
  Save,
  Table2,
  Copy,
  Check,
  Pencil,
  RefreshCw,
  Volume2,
  VolumeX,
  ArrowDown,
  X,
} from '@/components/icons';
import RememberFindingButton from './RememberFindingButton';
import { useLocaleRouting } from '../../context/LocaleRoutingContext';
import ChartRenderer from '../../components/ChartRenderer';
import TypewriterMarkdown from './TypewriterMarkdown';
import { getMessages, t } from '../../utils/i18n.js';
import api from '../../utils/api.js';
import { supabase } from '../../utils/supabaseClient.js';
import { cleanMsgContent, extractSystemCommands, tryParseSystemCommand } from './messageContent.js';
import { buildVisualizationPath, isUuid } from '../../utils/dashboardRoutes.js';
import { visualizationRequest } from '../../utils/visualizationApi.js';
import AnalysisAuditPanel from './AnalysisAuditPanel';
import {
  getElapsedSeconds,
  getStepLabel,
} from './reasoningProgress.js';
import {
  followUpPrompts,
  lastAssistantMessageIndex,
  messageActionKey,
  uniqueMessageKeys,
} from './chatInteractions.js';
import OrchestrationMessage from './orchestration/OrchestrationMessage';
import WorklogStampStack from './orchestration/WorklogStampStack';
import { buildSetupAuditPresentation } from './orchestration/setupAuditPresentation.js';
import AgentThinkingIndicator from './AgentThinkingIndicator';
import SuggestedQuestions, { shouldShowSuggestedQuestions } from './SuggestedQuestions';
import PythonAnalysisCard from './PythonAnalysisCard';
import DaxAnalysisCard from './DaxAnalysisCard';

const SaveVisualizationDialog = ({
  open,
  onClose,
  chartData,
  reportData,
  userId,
  conversationId,
  sourceMessageId,
  summary,
  isEn,
  message = null,
}) => {
  const routing = useLocaleRouting();
  const [reports, setReports] = useState([]);
  const [selectedReportId, setSelectedReportId] = useState('');
  const [newTitle, setNewTitle] = useState(
    reportData?.title || chartData?.config?.title || (isEn ? 'Analysis report' : 'รายงานผลการวิเคราะห์'),
  );
  const [mode, setMode] = useState('new');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [savedReportId, setSavedReportId] = useState(null);

  useEffect(() => {
    if (!open || !userId) return;
    setError('');
    setSavedReportId(null);
    visualizationRequest('/reports', { method: 'GET' })
      .then((payload) => {
        const items = payload.reports || [];
        setReports(items);
        if (items.length > 0) {
          setSelectedReportId(items[0].id);
          setMode('existing');
        } else {
          setMode('new');
        }
      })
      .catch((err) => setError(err.message));
  }, [open, userId]);

  const normalizedChart = chartData ? {
    chart_type: chartData.chart_type,
    title: chartData.config?.title || chartData.title || (isEn ? 'Analysis chart' : 'กราฟผลการวิเคราะห์'),
    subtitle: chartData.config?.subtitle || '',
    config: chartData.config || {},
    data: chartData.data || [],
    insight: chartData.insight || '',
  } : null;

  const buildPin = (title) => {
    // Lazy import path kept inline-compatible for the chat list bundle.
    const verification = message?.verification || null;
    const claims = Array.isArray(message?.analysisAudit?.claims)
      ? message.analysisAudit.claims.map((claim) => (
        typeof claim === 'string' ? claim : (claim?.text || claim?.claim || '')
      )).filter(Boolean).slice(0, 8)
      : [];
    return {
      kind: chartData ? 'chart' : (reportData ? 'report' : 'finding'),
      title: title || normalizedChart?.title || newTitle,
      summary: String(reportData?.summary || summary || message?.content || '').slice(0, 4000),
      source_message_id: isUuid(sourceMessageId) ? sourceMessageId : (isUuid(message?.id) ? message.id : null),
      conversation_id: isUuid(conversationId) ? conversationId : null,
      verification_status: verification?.status || null,
      verification: verification || {},
      claims,
      evidence: {
        verification,
        analysis_audit: message?.analysisAudit || null,
        chart_type: chartData?.chart_type || null,
      },
    };
  };

  const save = async () => {
    if (!userId) return;
    setBusy(true);
    setError('');
    try {
      if (mode === 'existing' && selectedReportId && normalizedChart) {
        await visualizationRequest('/charts', {
          body: {
            user_id: userId,
            report_id: selectedReportId,
            source_message_id: isUuid(sourceMessageId) ? sourceMessageId : null,
            chart: normalizedChart,
          },
        });
        await visualizationRequest('/reports', {
          method: 'PATCH',
          body: {
            user_id: userId,
            report_id: selectedReportId,
            pin: buildPin(normalizedChart.title),
          },
        });
        setSavedReportId(selectedReportId);
      } else {
        const payload = await visualizationRequest('/reports', {
          body: {
            user_id: userId,
            title: newTitle.trim() || (isEn ? 'Analysis report' : 'รายงานผลการวิเคราะห์'),
            executive_summary: String(reportData?.summary || summary || '').slice(0, 20000),
            dataset_key: reportData?.dataset_key || null,
            conversation_id: isUuid(conversationId) ? conversationId : null,
            source_message_id: isUuid(sourceMessageId) ? sourceMessageId : null,
            created_via: reportData ? 'ai' : 'chat',
            status: 'draft',
            chart: normalizedChart,
            pin: buildPin(newTitle.trim()),
          },
        });
        setSavedReportId(payload.report.id);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/55 p-4 backdrop-blur-sm" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 text-left shadow-2xl dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="font-serif text-lg font-bold text-slate-950 dark:text-white">
              {isEn ? 'Pin finding' : 'ปักข้อค้นพบ'}
            </h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {isEn ? 'Only you can access this report.' : 'รายงานนี้เข้าถึงได้เฉพาะบัญชีของคุณ'}
            </p>
          </div>
          <button onClick={onClose} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"><X size={15} /></button>
        </div>

        {savedReportId ? (
          <div className="mt-6 rounded-xl border border-emerald-200 bg-emerald-50 p-4 dark:border-emerald-900/60 dark:bg-emerald-950/20">
            <div className="text-sm font-semibold text-emerald-800 dark:text-emerald-200">
              {isEn ? 'Saved successfully' : 'บันทึกเรียบร้อยแล้ว'}
            </div>
            <a
              href={buildVisualizationPath(routing, savedReportId)}
              className="mt-3 inline-flex items-center gap-2 text-xs font-semibold text-emerald-700 underline underline-offset-2 dark:text-emerald-300"
            >
              <LayoutDashboard size={14} />
              {isEn ? 'Open pinned packet' : 'เปิด Decision packet ที่ปักไว้'}
            </a>
          </div>
        ) : (
          <>
            {normalizedChart && reports.length > 0 && (
              <div className="mt-5 grid grid-cols-2 gap-2">
                <button
                  onClick={() => setMode('existing')}
                  className={`rounded-xl border px-3 py-2.5 text-xs font-semibold ${mode === 'existing' ? 'border-amber-500 bg-amber-50 text-amber-800 dark:bg-amber-950/30 dark:text-amber-300' : 'border-slate-200 text-slate-500 dark:border-slate-700'}`}
                >
                  {isEn ? 'Existing report' : 'รายงานเดิม'}
                </button>
                <button
                  onClick={() => setMode('new')}
                  className={`rounded-xl border px-3 py-2.5 text-xs font-semibold ${mode === 'new' ? 'border-amber-500 bg-amber-50 text-amber-800 dark:bg-amber-950/30 dark:text-amber-300' : 'border-slate-200 text-slate-500 dark:border-slate-700'}`}
                >
                  {isEn ? 'New report' : 'รายงานใหม่'}
                </button>
              </div>
            )}
            {mode === 'existing' && normalizedChart && reports.length > 0 ? (
              <label className="mt-4 block text-xs font-semibold text-slate-600 dark:text-slate-300">
                {isEn ? 'Choose report' : 'เลือกรายงาน'}
                <select
                  value={selectedReportId}
                  onChange={(event) => setSelectedReportId(event.target.value)}
                  className="theme-select mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm dark:border-slate-700 dark:bg-slate-950"
                >
                  {reports.map((report) => (
                    <option key={report.id} value={report.id}>{report.title}</option>
                  ))}
                </select>
              </label>
            ) : (
              <label className="mt-4 block text-xs font-semibold text-slate-600 dark:text-slate-300">
                {isEn ? 'Report title' : 'ชื่อรายงาน'}
                <input
                  value={newTitle}
                  onChange={(event) => setNewTitle(event.target.value)}
                  maxLength={160}
                  className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm outline-none focus:border-amber-500 dark:border-slate-700 dark:bg-slate-950"
                />
              </label>
            )}
            {error && <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/20 dark:text-red-300">{error}</div>}
            <button
              onClick={save}
              disabled={busy || (mode === 'new' && !newTitle.trim())}
              className="btn-primary mt-5 inline-flex w-full items-center justify-center gap-2 py-3 text-sm disabled:opacity-50"
            >
              {busy ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
              {isEn ? 'Save report' : 'บันทึกรายงาน'}
            </button>
          </>
        )}
      </div>
    </div>
  );
};

const ClickableChartRenderer = ({
  chartData,
  onCommitToBottom,
  m,
  userId,
  conversationId,
  sourceMessageId,
  summary,
  message = null,
}) => {
  const { locale } = useLocaleRouting();
  const isEn = locale === 'en';
  const [showPopup, setShowPopup] = useState(false);
  const [showSave, setShowSave] = useState(false);
  const [selectedTypes, setSelectedTypes] = useState([chartData.chart_type]); // Default to recommended
  const [isCommitted, setIsCommitted] = useState(true);
  const [inlineChartType, setInlineChartType] = useState<any>(chartData.chart_type); // Render the AI recommendation immediately

  const chartId = useMemo(
    () => chartData.config?.title || JSON.stringify(chartData.data?.[0]) || `chart-${chartData.chart_type}`,
    [chartData],
  );

  const toggleType = (type) => {
    setSelectedTypes(prev => {
      if (prev.includes(type)) {
        if (prev.length === 1) return prev; // Keep at least one
        return prev.filter(t => t !== type);
      } else {
        return [...prev, type];
      }
    });
  };

  const handleClosePopup = () => {
    setShowPopup(false);

    if (selectedTypes.length === 1) {
      // หากเลือกเพียงกราฟเดียว ให้เรนเดอร์ในข้อความแชทตรงนี้ทันที ไม่ต้องนำไปแบ่งส่วนที่ท้ายแชท
      setInlineChartType(selectedTypes[0]);
      setIsCommitted(true);
    } else {
      // หากเลือกหลายกราฟ ให้เจนไปด้านล่างคู่ขนานกันแบบเดิม
      setInlineChartType(null);
      setIsCommitted(true);
      if (onCommitToBottom) {
        onCommitToBottom(chartId, chartData, selectedTypes);
      }
    }
  };

  const chartTypeOptions = [
    { type: 'bar', label: t(m, 'chat.chart_bar', 'กราฟแท่ง'), desc: 'Bar Chart', Icon: BarChart3 },
    { type: 'line', label: t(m, 'chat.chart_line', 'กราฟเส้น'), desc: 'Line Chart', Icon: LineChart },
    { type: 'area', label: t(m, 'chat.chart_area', 'พื้นที่'), desc: 'Area Chart', Icon: AreaChart },
    { type: 'pie', label: t(m, 'chat.chart_pie', 'วงกลม'), desc: 'Pie Chart', Icon: PieChart },
  ];

  // หากเรนเดอร์แบบ Inline (เลือกเพียงชนิดเดียว)
  if (inlineChartType) {
    const specificChartData = { ...chartData, chart_type: inlineChartType };
    return (
      <div className="my-6 relative enterprise-panel p-5 overflow-hidden">
        <div className="absolute top-2 left-2 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 text-[9px] font-medium px-2 py-0.5 rounded capitalize z-10">
          {inlineChartType}
        </div>
        <ChartRenderer embedded data={specificChartData} />
        <div className="mt-2 flex items-center justify-end gap-3">
          <button
            onClick={() => setShowSave(true)}
            className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-amber-700 hover:text-amber-800 dark:text-amber-400"
          >
            <Save size={12} />
            {isEn ? 'Pin finding' : 'ปักข้อค้นพบ'}
          </button>
          <span
            onClick={() => {
              setInlineChartType(null);
              setIsCommitted(false);
              setShowPopup(true);
            }}
            className="text-[10px] text-[#d97706] hover:text-[#b45309] font-medium cursor-pointer underline transition-colors select-none"
          >
            {t(m, 'chat.inline_chart_customize', 'ปรับแต่งหรือเปลี่ยนเป็นหลายกราฟ')}
          </span>
        </div>
        <SaveVisualizationDialog
          open={showSave}
          onClose={() => setShowSave(false)}
          chartData={specificChartData}
          userId={userId}
          conversationId={conversationId}
          sourceMessageId={sourceMessageId}
          summary={summary}
          isEn={isEn}
          message={message}
        />
      </div>
    );
  }

  return (
    <>
      <span className="my-2 inline-flex flex-wrap items-center gap-2">
        <button
          onClick={() => setShowPopup(true)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-100 px-3 py-1.5 text-xs font-medium text-[#d97706] transition-colors hover:bg-slate-200 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700"
        >
          {isCommitted ? t(m, 'chat.choose_chart_btn_active', 'ปรับแต่งกราฟใหม่') : t(m, 'chat.choose_chart_btn', 'เลือกสร้างกราฟ')}
        </button>
        <button
          onClick={() => setShowSave(true)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-800 hover:bg-amber-100 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-300"
        >
          <Save size={12} />
          {isEn ? 'Pin finding' : 'ปักข้อค้นพบ'}
        </button>
      </span>

      <SaveVisualizationDialog
        open={showSave}
        onClose={() => setShowSave(false)}
        chartData={chartData}
        userId={userId}
        conversationId={conversationId}
        sourceMessageId={sourceMessageId}
        summary={summary}
        isEn={isEn}
        message={message}
      />

      {showPopup && (
        <div className="fixed inset-0 z-[999] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="w-full max-w-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 md:p-8 flex flex-col shadow-xl relative">

            <div className="flex flex-col items-center mb-6 relative w-full">
              <h4 className="font-semibold text-slate-900 dark:text-slate-100 text-center text-base">
                {t(m, 'chat.choose_chart_title', 'เลือกประเภทกราฟที่ต้องการสร้าง')}
              </h4>
              <p className="text-xs text-slate-500 mt-1 text-center dark:text-slate-400">
                {t(m, 'chat.choose_chart_desc', 'เลือกประเภทกราฟที่ต้องการ (เลือกได้มากกว่า 1 ชนิด) หากเลือกชนิดเดียวจะแสดงผลในแชททันที หากเลือกหลายชนิดจะจัดเรียงคู่ขนานท้ายสุดแชท')}
              </p>

              <button
                onClick={() => setShowPopup(false)}
                className="absolute top-0 right-0 p-2 rounded-lg transition-colors text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                title={t(m, 'chat.cancel', 'ยกเลิก')}
              >
                ✕
              </button>
            </div>

            <div className="grid grid-cols-4 gap-2 mb-8">
              {chartTypeOptions.map(opt => {
                const active = selectedTypes.includes(opt.type);
                const Icon = opt.Icon;
                return (
                  <button
                    key={opt.type}
                    onClick={() => toggleType(opt.type)}
                    className={`flex flex-col items-center justify-center p-3 rounded-lg text-[11px] font-medium transition-colors border gap-1.5 ${active
                        ? 'bg-[#d97706] text-white border-[#d97706]'
                        : 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-600'
                      }`}
                  >
                    <Icon size={20} strokeWidth={1.5} />
                    <div className="text-center leading-tight">
                      <div className="font-medium text-[10px]">{opt.label}</div>
                      <div className={`text-[8px] font-normal ${active ? 'text-white/80' : 'text-slate-400'}`}>{opt.desc}</div>
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="pt-4 border-t border-slate-200 dark:border-slate-800 flex flex-col gap-3">
              <button
                onClick={handleClosePopup}
                className="w-full py-3 btn-primary text-sm flex items-center justify-center gap-2"
              >
                {t(m, 'chat.generate_and_render', 'สร้างและเรนเดอร์กราฟ')} ({selectedTypes.length})
              </button>
              <button
                onClick={() => setShowPopup(false)}
                className="w-full py-3 btn-secondary text-sm"
              >
                {t(m, 'chat.cancel', 'ยกเลิก')}
              </button>
            </div>

          </div>
        </div>
      )}
    </>
  );
};

const ReportCommandCard = ({
  reportData,
  userId,
  conversationId,
  sourceMessageId,
  summary,
  isEn,
  onDownload,
  message = null,
}) => {
  const [showSave, setShowSave] = useState(false);
  return (
    <div className="not-prose my-6 rounded-2xl border border-amber-200 bg-gradient-to-br from-amber-50 to-white p-5 dark:border-amber-900/60 dark:from-amber-950/20 dark:to-slate-900">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
            <LayoutDashboard size={19} />
          </div>
          <div>
            <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              {reportData.title || (isEn ? 'Analysis report' : 'รายงานผลการวิเคราะห์')}
            </h4>
            <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
              {isEn
                ? 'Ready to pin as a private decision packet with evidence.'
                : 'พร้อมปักเป็น Decision packet ส่วนตัวพร้อมหลักฐาน'}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {reportData.report_type === 'excel' && (
            <button onClick={onDownload} className="btn-secondary inline-flex items-center gap-2 px-3 py-2 text-xs">
              <FileDown size={14} />
              {isEn ? 'Download Excel' : 'ดาวน์โหลด Excel'}
            </button>
          )}
          <button onClick={() => setShowSave(true)} className="btn-primary inline-flex items-center gap-2 px-3 py-2 text-xs">
            <Save size={14} />
            {isEn ? 'Pin finding' : 'ปักข้อค้นพบ'}
          </button>
        </div>
      </div>
      <SaveVisualizationDialog
        open={showSave}
        onClose={() => setShowSave(false)}
        reportData={reportData}
        userId={userId}
        conversationId={conversationId}
        sourceMessageId={sourceMessageId}
        summary={summary}
        isEn={isEn}
        message={message}
      />
    </div>
  );
};

const VisualizationProposalCard = ({
  proposal,
  userId,
  conversationId,
  sourceMessageId,
  summary,
  isEn,
  message = null,
}) => {
  const routing = useLocaleRouting();
  const widgets = Array.isArray(proposal.widgets) ? proposal.widgets : [];
  const filters = Array.isArray(proposal.filters) ? proposal.filters : [];
  const [title, setTitle] = useState(
    proposal.title || (isEn ? 'Deep analysis dashboard' : 'แดชบอร์ดวิเคราะห์เชิงลึก'),
  );
  const [selectedWidgets, setSelectedWidgets] = useState(
    () => new Set(widgets.map((widget) => widget.id)),
  );
  const [selectedFilters, setSelectedFilters] = useState(
    () => new Set(filters.map((filter) => filter.field)),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reportId, setReportId] = useState(null);

  useEffect(() => {
    if (!userId || !isUuid(sourceMessageId)) return undefined;
    let cancelled = false;
    visualizationRequest(
      `/reports?source_message_id=${encodeURIComponent(sourceMessageId)}`,
      { method: 'GET' },
    )
      .then((payload) => {
        if (!cancelled && payload.reports?.[0]?.id) {
          setReportId(payload.reports[0].id);
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [sourceMessageId, userId]);

  const toggle = (setter, key) => {
    setter((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const createVisualization = async () => {
    if (!userId || selectedWidgets.size === 0) return;
    setBusy(true);
    setError('');
    let createdReportId = null;
    try {
      const dashboardSpec = {
        ...(proposal.spec || {}),
        version: 4,
        title: title.trim(),
        filters: filters.filter((filter) => selectedFilters.has(filter.field)),
        kpis: Array.isArray(proposal.kpis) ? proposal.kpis : [],
        widgets: widgets.filter((widget) => selectedWidgets.has(widget.id)),
      };
      const payload = await visualizationRequest('/reports', {
        body: {
          user_id: userId,
          title: title.trim(),
          executive_summary: String(summary || '').slice(0, 20000),
          conversation_id: isUuid(conversationId) ? conversationId : null,
          source_message_id: isUuid(sourceMessageId) ? sourceMessageId : null,
          created_via: 'ai',
          status: 'draft',
          dashboard_spec: dashboardSpec,
          source_config: proposal.source_config || {},
          pin: {
            kind: 'proposal',
            title: title.trim(),
            summary: String(summary || '').slice(0, 4000),
            source_message_id: isUuid(sourceMessageId) ? sourceMessageId : null,
            conversation_id: isUuid(conversationId) ? conversationId : null,
            verification_status: message?.verification?.status || null,
            verification: message?.verification || {},
            claims: Array.isArray(message?.analysisAudit?.claims)
              ? message.analysisAudit.claims.map((claim) => (
                typeof claim === 'string' ? claim : (claim?.text || claim?.claim || '')
              )).filter(Boolean).slice(0, 8)
              : [],
            evidence: {
              widget_ids: widgets.filter((widget) => selectedWidgets.has(widget.id)).map((widget) => widget.id),
              verification: message?.verification || null,
            },
          },
        },
      });
      createdReportId = payload.created ? payload.report.id : null;
      const dashboardPayload = await visualizationRequest('/dashboard/generate', {
        body: {
          user_id: userId,
          report_id: payload.report.id,
          filters: {},
        },
      });
      if (!dashboardPayload?.dashboard || Number(dashboardPayload.dashboard.row_count || 0) <= 0) {
        throw new Error(isEn
          ? 'The data source returned no rows. The Visualization was not saved.'
          : 'แหล่งข้อมูลไม่คืนแถว ระบบจึงยังไม่บันทึก Visualization');
      }
      setReportId(payload.report.id);
    } catch (err) {
      if (createdReportId) {
        try {
          await visualizationRequest('/reports', {
            method: 'DELETE',
            body: { user_id: userId, report_id: createdReportId },
          });
        } catch {
          // The original source error is more useful than cleanup failure.
        }
      }
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="not-prose my-6 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="border-b border-slate-200 bg-slate-950 px-5 py-4 text-white dark:border-slate-800">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-500/20 text-amber-300">
            <LayoutDashboard size={18} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold">
              {isEn ? 'Prove, then pin these findings' : 'พิสูจน์แล้วปักข้อค้นพบเหล่านี้'}
            </div>
            <div className="mt-1 text-[11px] leading-relaxed text-slate-300">
              {isEn
                ? `Suggestions are based on the full ${Number(proposal.row_count || 0).toLocaleString('en-US')}-row source.`
                : `ระบบเสนอจากโครงสร้างข้อมูลเต็ม ${Number(proposal.row_count || 0).toLocaleString('th-TH')} แถว`}
            </div>
          </div>
        </div>
      </div>

      {reportId ? (
        <div className="p-5">
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-semibold text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/20 dark:text-emerald-200">
            {isEn ? 'Findings pinned successfully.' : 'ปักข้อค้นพบเรียบร้อยแล้ว'}
          </div>
          <a href={buildVisualizationPath(routing, reportId)} className="btn-primary mt-3 inline-flex items-center gap-2 px-4 py-2.5 text-xs">
            <LayoutDashboard size={14} />
            {isEn ? 'Open pinned packet' : 'เปิด Decision packet ที่ปักไว้'}
          </a>
          {error && (
            <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950/20 dark:text-amber-200">
              {error}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-5 p-5">
          <label className="block text-[11px] font-semibold text-slate-600 dark:text-slate-300">
            {isEn ? 'Decision packet title' : 'ชื่อ Decision packet'}
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={160}
              className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-amber-500 dark:border-slate-700 dark:bg-slate-950"
            />
          </label>

          <div>
            <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-400">
              {isEn ? 'Charts and tables' : 'กราฟและตาราง'}
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {widgets.map((widget) => {
                const active = selectedWidgets.has(widget.id);
                return (
                  <button
                    key={widget.id}
                    type="button"
                    onClick={() => toggle(setSelectedWidgets, widget.id)}
                    className={`flex items-start gap-3 rounded-xl border p-3 text-left transition-colors ${
                      active
                        ? 'border-amber-400 bg-amber-50 dark:border-amber-700 dark:bg-amber-950/20'
                        : 'border-slate-200 opacity-60 dark:border-slate-700'
                    }`}
                  >
                    <div className={`mt-0.5 ${active ? 'text-amber-700 dark:text-amber-300' : 'text-slate-400'}`}>
                      {widget.kind === 'table' ? <Table2 size={15} /> : <BarChart3 size={15} />}
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-slate-800 dark:text-slate-100">{widget.title}</div>
                      <div className="mt-1 text-[10px] text-slate-400">
                        {widget.kind === 'table'
                          ? (isEn ? 'Detail table' : 'ตารางรายละเอียด')
                          : `${widget.chart_type} · ${widget.dimension}`}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {filters.length > 0 && (
            <div>
              <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                {isEn ? 'Report filters' : 'ตัวกรองทั้งรายงาน'}
              </div>
              <div className="flex flex-wrap gap-2">
                {filters.map((filter) => {
                  const active = selectedFilters.has(filter.field);
                  return (
                    <button
                      key={filter.field}
                      type="button"
                      onClick={() => toggle(setSelectedFilters, filter.field)}
                      className={`inline-flex items-center gap-2 rounded-full border px-3 py-2 text-[11px] font-semibold ${
                        active
                          ? 'border-slate-900 bg-slate-900 text-white dark:border-white dark:bg-white dark:text-slate-950'
                          : 'border-slate-200 text-slate-400 dark:border-slate-700'
                      }`}
                    >
                      <Filter size={12} />
                      {filter.field}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/20 dark:text-red-300">{error}</div>}
          <button
            type="button"
            onClick={createVisualization}
            disabled={busy || !title.trim() || selectedWidgets.size === 0}
            className="btn-primary inline-flex w-full items-center justify-center gap-2 py-3 text-sm disabled:opacity-50"
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
            {isEn ? 'Pin to decision packet' : 'ปักเข้า Decision packet'}
          </button>
        </div>
      )}
    </div>
  );
};

const CLEANING_PROFILE_LABEL_KEYS = {
  standard: 'chat.cleaning_profile_standard',
  financial: 'chat.cleaning_profile_financial',
  conservative: 'chat.cleaning_profile_careful',
  aggressive: 'chat.cleaning_profile_deep_clean',
};

const CleaningReportSummary = ({ cleaningReport, m, isEn }) => {
  const report = cleaningReport?.report || cleaningReport;
  if (!report || typeof report !== 'object') return null;
  const score = cleaningReport?.dataQualityScore ?? report.quality_score;
  const profileKey = CLEANING_PROFILE_LABEL_KEYS[report.profile] || null;
  const profileLabel = profileKey
    ? t(m, profileKey, report.profile || 'Standard')
    : (report.profile || 'Standard');
  const droppedColumns = report.dropped_columns || [];
  const coercedNumeric = report.coerced_numeric || {};
  const invalidDates = report.invalid_dates || {};
  const metricItems = [
    [isEn ? 'Profile' : 'Profile', profileLabel],
    [isEn ? 'Rows' : 'แถว', `${report.rows_before ?? '-'} → ${report.rows_after ?? '-'}`],
    [isEn ? 'Columns' : 'คอลัมน์', `${(report.columns_before || []).length} → ${(report.columns_after || []).length}`],
    [isEn ? 'Empty rows' : 'แถวว่าง', report.dropped_empty_rows || 0],
    [isEn ? 'Duplicates' : 'แถวซ้ำ', report.dropped_duplicates || 0],
    [isEn ? 'Dropped cols' : 'คอลัมน์ที่ลบ', droppedColumns.length],
  ];
  return (
    <div className="not-prose mt-4 rounded-lg border border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/60 dark:bg-emerald-950/20 px-4 py-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-emerald-900 dark:text-emerald-100">
          <ShieldCheck className="h-4 w-4" strokeWidth={2} />
          <span>{t(m, 'chat.cleaning_report_title', isEn ? 'Cleaning report' : 'รายงานการทำความสะอาดข้อมูล')}</span>
        </div>
        {score !== undefined && score !== null && (
          <span className="rounded-md bg-white/80 dark:bg-slate-900/70 px-2 py-1 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
            {isEn ? 'Quality' : 'Quality'} {score}/100
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        {metricItems.map(([label, value]) => (
          <div key={label} className="rounded-md bg-white/70 dark:bg-slate-900/50 px-2.5 py-2">
            <div className="text-[10px] uppercase text-slate-500 dark:text-slate-400">{label}</div>
            <div className="mt-0.5 text-sm font-semibold text-slate-800 dark:text-slate-100">{value}</div>
          </div>
        ))}
      </div>
      {(Object.keys(coercedNumeric).length > 0 || Object.keys(invalidDates).length > 0) && (
        <div className="mt-3 text-xs text-slate-600 dark:text-slate-300">
          {Object.keys(coercedNumeric).length > 0 && (
            <span>{isEn ? 'Numeric issues' : 'ค่าตัวเลขผิดรูป'}: {Object.entries(coercedNumeric).map(([k, v]) => `${k} ${v}`).join(', ')}</span>
          )}
          {Object.keys(invalidDates).length > 0 && (
            <span className="ml-2">{isEn ? 'Date issues' : 'วันที่ผิดรูป'}: {Object.entries(invalidDates).map(([k, v]) => `${k} ${v}`).join(', ')}</span>
          )}
        </div>
      )}
    </div>
  );
};

const renderMessageContent = (content) => {
  if (!content) return '';
  const parts = content.split(/(@[\w\-./:]+)/g);
  return parts.map((part, index) => {
    if (part.startsWith('@')) {
      return (
        <span 
          key={index} 
          className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-xs font-sans font-medium bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 mx-0.5 align-middle"
        >
          {part}
        </span>
      );
    }
    return part;
  });
};

const ChatMessageList = ({
  isNewChat,
  messages,
  isTyping,
  stopTyping,
  setIsGenerating,
  messagesEndRef,
  getDisplayName,
  selectedFile, // Pass selectedFile
  columnMapping, // Pass columnMapping
  userId, // Pass userId
  conversationId,
  bottomCharts = [], // Prop
  handleCommitToBottom, // Prop
  reasoningProgress = { stage: null, detail: {}, history: [], startedAt: null },
  showReasoningProgress = false,
  isGenerating = false,
  onEditPrompt,
  onRegenerateResponse,
  onRetryFailed,
  onSuggestedQuestion = null,
  dataSetupCard = null,
  onOrchestrationResolve = null,
  conversationalSetupActive = false,
}) => {
  const { locale } = useLocaleRouting(); // Assuming useLocaleRouting is available here
  const m = getMessages(locale);
  const isEn = locale === 'en';

  const labelFor = useCallback(
    (stage, detail = {}) =>
      getStepLabel(stage, detail, isEn, (key, fallback, vars) => t(m, key, fallback, vars)),
    [m, isEn]
  );

  // สถานะการดาวน์โหลดรายงาน
  const [downloadStatus, setDownloadStatus] = useState<any>(null); // null | 'loading' | 'success' | 'error'
  const [feedbackByMessage, setFeedbackByMessage] = useState<Record<string, number>>({});
  const [auditMessage, setAuditMessage] = useState<any>(null);
  const [copiedMessageKey, setCopiedMessageKey] = useState<string | null>(null);
  const [speakingMessageKey, setSpeakingMessageKey] = useState<string | null>(null);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);
  const [, setTick] = useState(0);

  const copyMessage = useCallback(async (message, index, renderKey = null) => {
    const text = cleanMsgContent(message?.content || '');
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      const key = renderKey || messageActionKey(message, index);
      setCopiedMessageKey(key);
      window.setTimeout(() => setCopiedMessageKey((current) => current === key ? null : current), 1600);
    } catch {
      setCopiedMessageKey(null);
    }
  }, []);

  const toggleSpeech = useCallback((message, index, renderKey = null) => {
    if (typeof window === 'undefined' || !window.speechSynthesis) return;
    const key = renderKey || messageActionKey(message, index);
    if (speakingMessageKey === key) {
      window.speechSynthesis.cancel();
      setSpeakingMessageKey(null);
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(cleanMsgContent(message?.content || ''));
    utterance.lang = isEn ? 'en-US' : 'th-TH';
    utterance.onend = () => setSpeakingMessageKey(null);
    utterance.onerror = () => setSpeakingMessageKey(null);
    setSpeakingMessageKey(key);
    window.speechSynthesis.speak(utterance);
  }, [isEn, speakingMessageKey]);

  useEffect(() => () => {
    if (typeof window !== 'undefined') window.speechSynthesis?.cancel();
  }, []);

  const submitFeedback = useCallback(async (message, rating) => {
    if (!userId || !message?.id || feedbackByMessage[message.id]) return;
    setFeedbackByMessage((prev) => ({ ...prev, [message.id]: rating }));
    const { error } = await supabase.from('chat_quality_events').insert({
      user_id: userId,
      conversation_id: message.conversation_id || null,
      message_id: message.id,
      event_type: 'user_feedback',
      payload: { rating },
    });
    if (error) {
      setFeedbackByMessage((prev) => {
        const next = { ...prev };
        delete next[message.id];
        return next;
      });
    }
  }, [feedbackByMessage, userId]);

  const recordCitationOpen = useCallback((message, source) => {
    if (!userId || !message?.id || !source?.url) return;
    supabase.from('chat_quality_events').insert({
      user_id: userId,
      conversation_id: message.conversation_id || null,
      message_id: message.id,
      event_type: 'citation_opened',
      payload: { url: source.url, title: source.title || source.url },
    }).then(({ error }) => {
      if (error) console.warn('Could not record citation metric:', error.message);
    });
  }, [userId]);

  useEffect(() => {
    if (!reasoningProgress.startedAt) return undefined;
    const timer = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(timer);
  }, [reasoningProgress.startedAt]);

  const elapsedSec = reasoningProgress.startedAt
    ? getElapsedSeconds(reasoningProgress.startedAt)
    : 0;

  // ดึงชื่อไฟล์ที่แนบมาจากประวัติข้อความหากไม่มี selectedFile ใน State (เช่นกรณีรีเฟรชหน้าแชท)
  const getAttachedFilename = useCallback(() => {
    if (selectedFile?.name) return selectedFile.name;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].attachment) {
        return messages[i].attachment;
      }
    }
    return '';
  }, [selectedFile, messages]);

  const handleDownloadReport = useCallback(async (reportData, fileAttachmentName, columnMapping, userId) => {
    try {
      setDownloadStatus('loading');

      const response = await api.post(
        '/api/v1/report/excel',
        {
          file_attachment_name: fileAttachmentName,
          column_mapping: columnMapping,
          title: reportData.title,
          summary: reportData.summary,
          user_id: userId,
          locale: locale
        },
        {
          responseType: 'blob',
        }
      );

      // สร้าง URL สำหรับดาวน์โหลดไฟล์
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${reportData.title.replace(/\s+/g, '_')}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();

      setDownloadStatus('success');
      setTimeout(() => setDownloadStatus(null), 4000);
    } catch (error: any) {
      console.error("Report generation failed:", error);
      setDownloadStatus('error');
      setTimeout(() => setDownloadStatus(null), 4000);
    }
  }, [locale]);

  // บันทึกฟังก์ชันและพรอพลงใน Ref เพื่อหลีกเลี่ยงการสร้าง markdownComponents ใหม่เมื่อพรอพเปลี่ยน
  const downloadReportRef = useRef(handleDownloadReport);
  const getFilenameRef = useRef(getAttachedFilename);
  const colMappingRef = useRef(columnMapping);
  const uIdRef = useRef(userId);

  useEffect(() => {
    downloadReportRef.current = handleDownloadReport;
    getFilenameRef.current = getAttachedFilename;
    colMappingRef.current = columnMapping;
    uIdRef.current = userId;
  }, [handleDownloadReport, getAttachedFilename, columnMapping, userId]);

  // Memoize markdown components เพื่อป้องกันไม่ให้เกิดการ Unmount และ Remount ใหม่ของคอมโพเนนต์ชาร์ตและรายงานเมื่อพิมข้อความใหม่
  const markdownComponents = useMemo(() => ({
    code({ inline, className, children, ...props }) {
      const match = /language-(\w+)/.exec(className || '');
      if (!inline && match && match[1] === 'json') {
        const rawContent = String(children).trim();
        const systemCommand = tryParseSystemCommand(rawContent);

        if (systemCommand) {
          if (systemCommand.action === '__streaming__') return null;

          if (systemCommand.action === 'render_chart') {
            return (
              <ClickableChartRenderer
                chartData={systemCommand}
                onCommitToBottom={handleCommitToBottom}
                m={m}
                userId={userId}
                conversationId={conversationId}
                summary=""
              />
            );
          }

          if (systemCommand.action === 'generate_report') {
            return (
              <div className="my-6 p-6 enterprise-panel flex flex-col items-center gap-4 text-center">
                <div className="w-12 h-12 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 rounded-lg flex items-center justify-center border border-slate-200 dark:border-slate-700">
                  <FileDown className="w-6 h-6" strokeWidth={1.5} />
                </div>
                <div>
                  <h4 className="font-semibold text-slate-900 dark:text-slate-100">{systemCommand.title}</h4>
                  <p className="text-xs text-slate-500 mt-1">{isEn ? 'Analysis complete. You can download the full summary report below.' : 'วิเคราะห์ข้อมูลเสร็จสิ้น คุณสามารถดาวน์โหลดรายงานสรุปฉบับเต็มได้ที่นี่'}</p>
                </div>
                <button onClick={() => downloadReportRef.current(systemCommand, getFilenameRef.current(), colMappingRef.current, uIdRef.current)} className="px-6 py-2.5 btn-primary text-xs">{isEn ? 'Download Report' : 'ดาวน์โหลดรายงาน'}</button>
              </div>
            );
          }

          if (systemCommand.action === 'propose_visualization') {
            return (
              <VisualizationProposalCard
                proposal={systemCommand}
                userId={userId}
                conversationId={conversationId}
                sourceMessageId={null}
                summary=""
                isEn={isEn}
              />
            );
          }

          if (systemCommand.action === 'propose_python_analysis') {
            return (
              <PythonAnalysisCard
                proposal={systemCommand}
                userId={userId}
                isEn={isEn}
              />
            );
          }

          if (systemCommand.action === 'preview_dax_definition') {
            return <DaxAnalysisCard proposal={systemCommand} userId={userId} isEn={isEn} />;
          }
        }
      }
      return <code className={className} {...props}>{children}</code>;
    }
  }), [conversationId, handleCommitToBottom, isEn, m, userId]);

  const containerRef = useRef(null);
  const isAtBottom = useRef(true);
  const latestAssistantIndex = lastAssistantMessageIndex(messages);
  const messageRenderKeys = useMemo(() => uniqueMessageKeys(messages), [messages]);
  const setupAuditPresentation = useMemo(
    () => buildSetupAuditPresentation(messages),
    [messages],
  );

  // ตรวจสอบว่าผู้ใช้กำลังเลื่อนดูประวัติอยู่หรือไม่
  const handleScroll = () => {
    if (containerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
      // หากระยะห่างจากล่างสุดน้อยกว่า 100px ถือว่าผู้ใช้ต้องการให้ Auto-scroll ต่อ
      const atBottom = scrollHeight - scrollTop - clientHeight < 100;
      isAtBottom.current = atBottom;
      setShowJumpToLatest(!atBottom);
    }
  };

  const scrollToBottom = useCallback((behavior = "auto", force = false) => {
    if ((force || isAtBottom.current) && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior });
      if (force) {
        isAtBottom.current = true;
        setShowJumpToLatest(false);
      }
    }
  }, [messagesEndRef]);

  useEffect(() => {
    scrollToBottom("smooth");
  }, [messages.length, bottomCharts.length, dataSetupCard, scrollToBottom]);

  if (isNewChat && !dataSetupCard) return null;

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="chat-message-scroll theme-scrollbar relative z-10 flex-1 overflow-y-auto overscroll-contain px-3 pb-8 pt-7 sm:px-6 sm:pt-10"
    >
      <div className="mx-auto w-full max-w-[800px]">
        {messages.map((msg, idx) => {
          if (setupAuditPresentation.hiddenUserAnswerIndexes.has(idx)) return null;
          if (setupAuditPresentation.hiddenCompletedAssistantIndexes.has(idx)) return null;
          if (conversationalSetupActive && msg.role === 'ai' && msg.orchestration) return null;

          const completedSetupAudit = setupAuditPresentation.completedBySummaryIndex.get(idx);
          const actionKey = messageRenderKeys[idx] || messageActionKey(msg, idx);
          const copied = copiedMessageKey === actionKey;
          const speaking = speakingMessageKey === actionKey;
          const isLatestAssistant = idx === latestAssistantIndex;
          const suggestedPrompts = msg.role === 'ai'
            ? followUpPrompts(
              msg,
              isEn,
              (key, fallback) => t(m, key, fallback),
              { messages, messageIndex: idx },
            )
            : [];
          const showSuggestedQuestions = shouldShowSuggestedQuestions({
            isLatestAssistant,
            failed: msg.failed,
            isGenerating,
            conversationalSetupActive,
            promptCount: suggestedPrompts.length,
            hasHandler: Boolean(onSuggestedQuestion),
          });
          return (
          <div key={actionKey} className={`group flex ${msg.role === 'user' ? 'mb-7 justify-end' : 'mb-10 justify-start'}`}>
            <div className={`leading-relaxed ${msg.role === 'user'
                ? 'max-w-[88%] rounded-2xl rounded-br-md border border-stone-200/80 bg-[#f3efe9] px-4 py-3 font-sans text-[15px] text-stone-800 dark:border-stone-700/80 dark:bg-stone-800/75 dark:text-stone-100 sm:max-w-[78%]'
                : 'w-full max-w-none px-1 py-1 text-[15px] text-stone-800 dark:text-stone-200 sm:px-2'
              }`}>
              {msg.role === 'ai' ? (
                <div className="chat-ai-response prose prose-stone dark:prose-invert max-w-none prose-p:leading-[1.75] prose-headings:tracking-[-0.02em] prose-strong:text-stone-950 dark:prose-strong:text-stone-100">
                  {msg.agentClarify && !msg.orchestration && (
                    <div className="not-prose mb-3 flex items-start gap-2.5 rounded-lg border border-amber-200 dark:border-amber-800/50 bg-amber-50 dark:bg-amber-950/40 px-3.5 py-2.5 text-sm">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900/50 text-amber-700 dark:text-amber-300 text-xs font-bold">
                        ?
                      </span>
                      <div className="min-w-0">
                        <p className="font-medium text-amber-900 dark:text-amber-100">
                          {t(m, 'chat.agent_clarify_badge', isEn ? 'Analyst needs your input' : 'นักวิเคราะห์ต้องการข้อมูลเพิ่ม')}
                        </p>
                        {msg.agentReason && (
                          <p className="mt-0.5 text-xs text-amber-800/80 dark:text-amber-300/70 leading-snug">
                            {msg.agentReason}
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                  {completedSetupAudit ? (
                    <WorklogStampStack
                      stamps={completedSetupAudit.stamps}
                      exchanges={completedSetupAudit.exchanges}
                      isEn={isEn}
                    />
                  ) : msg.orchestration && (() => {
                    const nextMsg = messages[idx + 1];
                    const answerLabel = msg.orchestration?.awaiting_user
                      && nextMsg?.role === 'user'
                      ? String(nextMsg.content || '').trim() || null
                      : null;
                    return (
                      <OrchestrationMessage
                        orchestration={msg.orchestration}
                        isEn={isEn}
                        historical
                        resolvedAnswerLabel={answerLabel}
                        hideUnresolvedQuestion={Boolean(
                          conversationalSetupActive
                          && isLatestAssistant
                          && !answerLabel,
                        )}
                      />
                    );
                  })()}
                  {msg.failed ? (
                    <div className="not-prose rounded-xl border border-red-200 bg-red-50/80 p-4 text-sm text-red-800 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
                      <div className="flex items-start gap-3">
                        <AlertTriangle size={18} className="mt-0.5 shrink-0" />
                        <div className="min-w-0 flex-1">
                          <p className="font-semibold">
                            {t(m, 'chat.interactions.response_failed', isEn ? 'The response was interrupted' : 'การตอบกลับถูกขัดจังหวะ')}
                          </p>
                          <p className="mt-1 text-xs opacity-80">
                            {t(m, 'chat.interactions.response_failed_desc', isEn ? 'Retry safely without creating a duplicate message.' : 'ลองใหม่ได้อย่างปลอดภัยโดยไม่สร้างข้อความซ้ำ')}
                          </p>
                          {onRetryFailed && (
                            <button
                              type="button"
                              onClick={() => onRetryFailed(msg)}
                              disabled={isGenerating}
                              className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-red-300 bg-white px-3 py-1.5 text-xs font-semibold text-red-700 transition-colors hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-800 dark:bg-red-950/50 dark:text-red-200 dark:hover:bg-red-900/60"
                            >
                              <RefreshCw size={13} />
                              {t(m, 'chat.interactions.retry_response', isEn ? 'Retry response' : 'ลองตอบใหม่')}
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  ) : msg.setupAwaitingUser && msg.orchestration?.awaiting_user?.question
                    && cleanMsgContent(msg.content || '') === String(msg.orchestration.awaiting_user.question || '').trim()
                    ? null
                    : (
                    <TypewriterMarkdown
                      content={cleanMsgContent(msg.content || '')}
                      animate={idx === messages.length - 1 && !isTyping && !stopTyping && !msg.skipAnimate}
                      onType={() => scrollToBottom("auto")}
                      onComplete={() => setIsGenerating(false)}
                      stopTyping={stopTyping}
                      components={markdownComponents}
                    />
                  )}
                  {msg.cleaningReport && (
                    <CleaningReportSummary cleaningReport={msg.cleaningReport} m={m} isEn={isEn} />
                  )}
                  {Array.isArray(msg.webSources) && msg.webSources.length > 0 && (
                    <div className="chat-data-card not-prose mt-4 rounded-xl border px-4 py-3">
                      <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-600 dark:text-slate-300">
                        <Globe className="h-3.5 w-3.5 shrink-0" strokeWidth={2} />
                        <span>{t(m, 'chat.web_sources_title', isEn ? 'Web sources' : 'แหล่งข้อมูลจากเว็บ')}</span>
                      </div>
                      <ul className="space-y-2 text-sm">
                        {msg.webSources.map((source) => (
                          <li key={source.url} className="leading-snug">
                            <a
                              href={source.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={() => recordCitationOpen(msg, source)}
                              className="font-medium text-[#d97706] hover:text-[#b45309] underline-offset-2 hover:underline"
                            >
                              {source.title || source.url}
                            </a>
                            {source.snippet && (
                              <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400 line-clamp-2">
                                {source.snippet}
                              </p>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {(msg.verification || msg.routing || msg.responseMode || msg.analysisAudit || msg.toolExecution) && (
                    <div className="not-prose mt-3 flex flex-wrap items-center gap-2 text-[10px] text-slate-500 dark:text-slate-400">
                      {msg.verification?.status === 'grounded' ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-1 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
                          <BadgeCheck size={12} />
                          {isEn ? 'Proved with evidence' : 'พิสูจน์ด้วยหลักฐานแล้ว'}
                        </span>
                      ) : msg.verification?.status === 'needs_review' ? (
                        <span
                          className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-1 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300"
                          title={(msg.verification.warnings || []).join('\n')}
                        >
                          <AlertTriangle size={12} />
                          {isEn ? 'Needs more proof' : 'ต้องการหลักฐานเพิ่ม'}
                        </span>
                      ) : msg.verification?.status === 'not_required' ? (
                        <span
                          className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-1 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                          title={isEn ? 'No tool evidence package for this answer' : 'คำตอบนี้ไม่มีชุดหลักฐานจากเครื่องมือ'}
                        >
                          <AlertTriangle size={12} />
                          {isEn ? 'Model answer · no tool evidence' : 'คำตอบโมเดล · ไม่มีหลักฐานเครื่องมือ'}
                        </span>
                      ) : null}
                      {msg.verification?.anti_hallucination_gate?.applied ? (
                        <span
                          className="inline-flex items-center gap-1 rounded-full bg-sky-50 px-2 py-1 text-sky-700 dark:bg-sky-950/40 dark:text-sky-300"
                          title={isEn ? 'Server removed ungrounded claims' : 'เซิร์ฟเวอร์ตัดข้อความที่ไม่มีหลักฐานแล้ว'}
                        >
                          <ShieldCheck size={12} />
                          {isEn ? 'Ungrounded claims filtered' : 'กรองข้อความไม่มีหลักฐานแล้ว'}
                        </span>
                      ) : null}
                      {typeof msg.verification?.evidence_count === 'number' && msg.verification.evidence_count > 0 ? (
                        <span className="rounded-full bg-emerald-50/80 px-2 py-1 text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-200">
                          {isEn ? 'Evidence' : 'หลักฐาน'}: {msg.verification.evidence_count}
                        </span>
                      ) : null}
                      {msg.routing?.primary && (
                        <span className="rounded-full bg-slate-100 px-2 py-1 dark:bg-slate-800">
                          {msg.routing.primary}
                        </span>
                      )}
                      {msg.toolExecution?.calls?.length > 0 && (
                        <span
                          className={`inline-flex items-center gap-1 rounded-full px-2 py-1 font-medium ${
                            msg.toolExecution.satisfied
                              ? 'bg-cyan-50 text-cyan-700 dark:bg-cyan-950/50 dark:text-cyan-300'
                              : 'bg-red-50 text-red-700 dark:bg-red-950/50 dark:text-red-300'
                          }`}
                          title={msg.toolExecution.calls
                            .map((call) => `${call.tool}: ${call.status} (${call.engine})`)
                            .join('\n')}
                        >
                          <ShieldCheck size={12} />
                          {isEn ? 'Tools' : 'เครื่องมือ'}: {' '}
                          {msg.toolExecution.calls.map((call) => call.tool).join(', ')}
                        </span>
                      )}
                      {msg.responseMode?.effective && (
                        <span
                          className={`rounded-full px-2 py-1 font-medium ${
                            msg.responseMode.requested === 'auto'
                              ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300'
                              : msg.responseMode.effective === 'deep'
                              ? 'bg-violet-100 text-violet-700 dark:bg-violet-950/50 dark:text-violet-300'
                              : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300'
                          }`}
                          title={`${msg.responseMode.max_agent_steps} steps · ${msg.responseMode.max_search_queries} searches · ${msg.responseMode.max_output_tokens} tokens`}
                        >
                          {msg.responseMode.requested === 'auto' ? 'Auto → ' : ''}
                          {msg.responseMode.effective === 'deep' ? 'Deep' : 'Fast'}
                          {' · '}
                          {msg.responseMode.max_agent_steps} {isEn ? 'steps' : 'ขั้น'}
                          {' · '}
                          {msg.responseMode.max_search_queries} {isEn ? 'searches' : 'คำค้น'}
                        </span>
                      )}
                      {msg.analysisAudit && (
                        <>
                          {[
                            ['computation', isEn ? 'Computed' : 'คำนวณแล้ว'],
                            ['data_readiness', isEn ? 'Data ready' : 'ข้อมูลพร้อม'],
                            ['business_context', isEn ? 'Context reviewed' : 'ตรวจบริบทแล้ว'],
                          ].map(([key, label]) => {
                            const verified = msg.analysisAudit?.verification_layers?.[key]?.status === 'verified';
                            return (
                              <span
                                key={key}
                                className={`inline-flex items-center gap-1 rounded-full px-2 py-1 ${
                                  verified
                                    ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300'
                                    : 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300'
                                }`}
                              >
                                {verified ? <BadgeCheck size={12} /> : <AlertTriangle size={12} />}
                                {label}: {verified ? (isEn ? 'verified' : 'ผ่าน') : (isEn ? 'review' : 'ตรวจเพิ่ม')}
                              </span>
                            );
                          })}
                          <button
                            type="button"
                            onClick={() => setAuditMessage(msg)}
                            className="inline-flex items-center gap-1 rounded-full bg-cyan-50 px-2 py-1 font-medium text-cyan-700 transition-colors hover:bg-cyan-100 hover:text-cyan-900 focus:outline-none focus:ring-2 focus:ring-cyan-500/60 dark:bg-cyan-950/50 dark:text-cyan-300 dark:hover:bg-cyan-800 dark:hover:text-white dark:focus:ring-cyan-400/70"
                          >
                            <FileSearch size={12} />
                            {isEn ? 'Analysis audit' : 'ตรวจสอบการวิเคราะห์'}
                          </button>
                        </>
                      )}
                    </div>
                  )}
                  {Array.isArray(msg.searchQueries) && msg.searchQueries.length > 0 && (
                    <details className="not-prose mt-2 text-xs text-slate-500 dark:text-slate-400">
                      <summary className="cursor-pointer select-none">
                        {isEn ? 'Search queries used' : 'คำค้นที่ระบบใช้'}
                      </summary>
                      <ul className="mt-1 list-disc space-y-1 pl-5">
                        {msg.searchQueries.map((query) => <li key={query}>{query}</li>)}
                      </ul>
                    </details>
                  )}
                  {Array.isArray(msg.reasoningTrace) && msg.reasoningTrace.length > 0 && (
                    <details className="not-prose mt-2 text-xs text-slate-500 dark:text-slate-400">
                      <summary className="cursor-pointer select-none">
                        {isEn ? 'Saved processing history' : 'ประวัติขั้นตอนการทำงาน'}
                      </summary>
                      <ol className="mt-1 space-y-1 pl-4">
                        {msg.reasoningTrace.map((step, traceIndex) => (
                          <li key={`${step.stage}-${traceIndex}`}>
                            {traceIndex + 1}. {labelFor(step.stage, step.detail)}
                          </li>
                        ))}
                      </ol>
                    </details>
                  )}
                  {!msg.failed && (
                  <div className="not-prose mt-3 flex flex-wrap items-center gap-1 text-slate-400">
                      <button
                        type="button"
                        onClick={() => copyMessage(msg, idx, actionKey)}
                        aria-label={isEn ? 'Copy answer' : 'คัดลอกคำตอบ'}
                        title={isEn ? 'Copy' : 'คัดลอก'}
                        className="rounded-md p-1.5 transition-colors hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"
                      >
                        {copied ? <Check size={14} /> : <Copy size={14} />}
                      </button>
                      <RememberFindingButton message={msg} userId={userId} isEn={isEn} />
                      <button
                        type="button"
                        onClick={() => toggleSpeech(msg, idx, actionKey)}
                        aria-label={speaking ? (isEn ? 'Stop reading' : 'หยุดอ่าน') : (isEn ? 'Read aloud' : 'อ่านออกเสียง')}
                        title={speaking ? (isEn ? 'Stop reading' : 'หยุดอ่าน') : (isEn ? 'Read aloud' : 'อ่านออกเสียง')}
                        className={`rounded-md p-1.5 transition-colors hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 ${speaking ? 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200' : ''}`}
                      >
                        {speaking ? <VolumeX size={14} /> : <Volume2 size={14} />}
                      </button>
                      {isLatestAssistant && onRegenerateResponse && !isGenerating
                        && !conversationalSetupActive && (
                        <button
                          type="button"
                          onClick={() => onRegenerateResponse(msg, idx)}
                          aria-label={isEn ? 'Edit prompt to try again' : 'แก้ข้อความเพื่อสร้างคำตอบใหม่'}
                          title={isEn ? 'Edit prompt to try again' : 'แก้ข้อความเพื่อสร้างคำตอบใหม่'}
                          className="rounded-md p-1.5 transition-colors hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"
                        >
                          <RefreshCw size={14} />
                        </button>
                      )}
                    {msg.id && (
                      <>
                      <button
                        type="button"
                        onClick={() => submitFeedback(msg, 1)}
                        aria-label={isEn ? 'Helpful answer' : 'คำตอบมีประโยชน์'}
                        className={`rounded-md p-1.5 transition-colors ${
                          feedbackByMessage[msg.id] === 1
                            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300'
                            : 'text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800'
                        }`}
                      >
                        <ThumbsUp size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => submitFeedback(msg, -1)}
                        aria-label={isEn ? 'Unhelpful answer' : 'คำตอบยังไม่ดี'}
                        className={`rounded-md p-1.5 transition-colors ${
                          feedbackByMessage[msg.id] === -1
                            ? 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300'
                            : 'text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800'
                        }`}
                      >
                        <ThumbsDown size={14} />
                      </button>
                      </>
                    )}
                  </div>
                  )}
                  {extractSystemCommands(msg.content || '')
                    .map((command, commandIdx) => {
                      const summary = cleanMsgContent(msg.content || '');
                      if (command.action === 'render_chart') {
                        return (
                          <ClickableChartRenderer
                            key={`chart-${idx}-${commandIdx}`}
                            chartData={command}
                            onCommitToBottom={handleCommitToBottom}
                            m={m}
                            userId={userId}
                            conversationId={conversationId || msg.conversation_id || null}
                            sourceMessageId={msg.id || null}
                            summary={summary}
                            message={msg}
                          />
                        );
                      }
                      if (command.action === 'generate_report') {
                        return (
                          <ReportCommandCard
                            key={`report-${idx}-${commandIdx}`}
                            reportData={command}
                            userId={userId}
                            conversationId={conversationId || msg.conversation_id || null}
                            sourceMessageId={msg.id || null}
                            summary={summary}
                            isEn={isEn}
                            message={msg}
                            onDownload={() => handleDownloadReport(
                              command,
                              getAttachedFilename(),
                              columnMapping,
                              userId,
                            )}
                          />
                        );
                      }
                      if (command.action === 'propose_visualization') {
                        return (
                          <VisualizationProposalCard
                            key={`visualization-proposal-${idx}-${commandIdx}`}
                            proposal={command}
                            userId={userId}
                            conversationId={conversationId || msg.conversation_id || null}
                            sourceMessageId={msg.id || null}
                            summary={summary}
                            isEn={isEn}
                            message={msg}
                          />
                        );
                      }
                      if (command.action === 'propose_python_analysis') {
                        return (
                          <PythonAnalysisCard
                            key={`python-analysis-${idx}-${commandIdx}`}
                            proposal={command}
                            userId={userId}
                            isEn={isEn}
                          />
                        );
                      }
                      if (command.action === 'preview_dax_definition') {
                        return (
                          <DaxAnalysisCard
                            key={`dax-preview-${idx}-${commandIdx}`}
                            proposal={command}
                            userId={userId}
                            isEn={isEn}
                          />
                        );
                      }
                      return null;
                    })}
                  {showSuggestedQuestions && (
                    <SuggestedQuestions
                      prompts={suggestedPrompts}
                      isEn={isEn}
                      disabled={isGenerating}
                      onSelect={onSuggestedQuestion}
                    />
                  )}
                </div>
              ) : (
                <>
                  {msg.attachment && (
                    <div className="mb-2 text-[10px] bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded-md border border-slate-200 dark:border-slate-700 inline-flex items-center gap-1 text-slate-600 dark:text-slate-400">
                      <Paperclip className="w-3 h-3" strokeWidth={1.5} />
                      {getDisplayName(msg.attachment)}
                    </div>
                  )}
                  <p className="whitespace-pre-wrap leading-relaxed">{renderMessageContent(msg.content)}</p>
                  <div className="mt-2 flex justify-end gap-1 text-slate-400 opacity-70 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                    <button
                      type="button"
                      onClick={() => copyMessage(msg, idx, actionKey)}
                      aria-label={isEn ? 'Copy prompt' : 'คัดลอกข้อความ'}
                      title={isEn ? 'Copy' : 'คัดลอก'}
                      className="rounded-md p-1.5 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"
                    >
                      {copied ? <Check size={14} /> : <Copy size={14} />}
                    </button>
                    {onEditPrompt && (
                      <button
                        type="button"
                        onClick={() => onEditPrompt(msg.content || '', msg, idx)}
                        aria-label={isEn ? 'Reuse and edit prompt' : 'นำข้อความกลับมาแก้ไข'}
                        title={isEn ? 'Reuse and edit' : 'นำกลับมาแก้ไข'}
                        className="rounded-md p-1.5 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"
                      >
                        <Pencil size={14} />
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
          );
        })}

        {bottomCharts.map((chart, cIdx) => {
          const isSingle = chart.types.length === 1;
          if (isSingle) {
            const specificChartData = { ...chart.data, chart_type: chart.types[0] };
            return (
              <div key={chart.id || cIdx} className="my-8 enterprise-panel p-5 overflow-hidden">
                <ChartRenderer data={specificChartData} />
              </div>
            );
          }
          return (
            <div key={chart.id || cIdx} className="my-8 enterprise-panel p-6">
              <div className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-4 flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-green-600"></span>
                {t(m, 'chat.latest_active_chart', 'กราฟที่เปิดแสดงผลล่าสุด')} ({chart.data.config?.title})
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {chart.types.map(type => {
                  const specificChartData = { ...chart.data, chart_type: type };
                  return (
                    <div key={type} className="relative enterprise-panel p-4 overflow-hidden col-span-2 md:col-span-1 last:only:col-span-2">
                      <div className="absolute top-2 left-2 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 text-[9px] font-medium px-2 py-0.5 rounded capitalize z-10">
                        {type}
                      </div>
                      <ChartRenderer data={specificChartData} />
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}

        {showReasoningProgress && (
          <AgentThinkingIndicator
            elapsedSec={elapsedSec}
            isEn={isEn}
            label={
              reasoningProgress.stage
                ? labelFor(reasoningProgress.stage, reasoningProgress.detail)
                : null
            }
          />
        )}
        {dataSetupCard}
        <div ref={messagesEndRef} />
      </div>

      {showJumpToLatest && !(dataSetupCard && messages.length === 0) && (
        <button
          type="button"
          onClick={() => scrollToBottom('smooth', true)}
          className="sticky bottom-4 left-1/2 z-20 flex h-9 w-9 -translate-x-1/2 items-center justify-center rounded-full border border-amber-200/80 bg-white text-amber-700 shadow-lg transition-transform hover:scale-105 hover:text-amber-900 dark:border-amber-800/60 dark:bg-slate-900 dark:text-amber-300"
          aria-label={isEn ? 'Jump to latest message' : 'ไปยังข้อความล่าสุด'}
          title={isEn ? 'Jump to latest' : 'ไปข้อความล่าสุด'}
        >
          <ArrowDown size={16} />
        </button>
      )}

      {auditMessage?.analysisAudit && (
        <AnalysisAuditPanel
          audit={auditMessage.analysisAudit}
          message={auditMessage}
          userId={userId}
          isEn={isEn}
          onClose={() => setAuditMessage(null)}
        />
      )}

      {/* Premium Download Toast Notification */}
      {downloadStatus && (
        <div className="fixed bottom-6 right-6 z-[999]">
          <div className={`flex items-center gap-3 px-5 py-4 rounded-xl border shadow-lg ${
            downloadStatus === 'loading'
              ? 'bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 border-slate-200 dark:border-slate-700'
              : downloadStatus === 'success'
                ? 'bg-white dark:bg-slate-900 text-green-700 dark:text-green-400 border-green-200 dark:border-green-900/40'
                : 'bg-white dark:bg-slate-900 text-red-600 dark:text-red-400 border-red-200 dark:border-red-900/40'
            }`}>
            {downloadStatus === 'loading' && (
              <>
                <div className="w-5 h-5 border-2 border-slate-300 border-t-slate-600 dark:border-slate-600 dark:border-t-slate-300 rounded-full animate-spin"></div>
                <div className="text-sm font-medium">
                  {t(m, 'chat.excel_preparing', 'กำลังเตรียมรายงาน Excel...')}
                </div>
              </>
            )}
            {downloadStatus === 'success' && (
              <>
                <div className="w-5 h-5 bg-green-600 text-white rounded-full flex items-center justify-center text-xs font-bold font-sans">✓</div>
                <div className="text-sm font-medium">
                  {t(m, 'chat.excel_success', 'ดาวน์โหลดรายงาน Excel สำเร็จ!')}
                </div>
              </>
            )}
            {downloadStatus === 'error' && (
              <>
                <div className="w-5 h-5 bg-red-600 text-white rounded-full flex items-center justify-center text-xs font-bold font-sans">✗</div>
                <div className="text-sm font-medium">
                  {t(m, 'chat.excel_error', 'ไม่สามารถดาวน์โหลดรายงานได้')}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default ChatMessageList;
