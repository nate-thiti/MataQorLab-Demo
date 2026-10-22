// @ts-nocheck
import { useState, useCallback, useRef } from 'react';
import {
  Mic,
  MicOff,
  Database,
  Globe,
  Paperclip,
  Table2,
  ChevronLeft,
  ChevronDown,
  Search,
  FileText,
  X,
  ArrowUp,
  Square,
  BarChart3,
  Layers3,
  Zap,
  Gauge,
  Check,
  Lock,
} from '@/components/icons';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { getMessages, t } from '../utils/i18n.js';
import api from '../utils/api.js';
import { formatConnectionMention } from '../features/chat/connectionMention.js';
import {
  MODEL_MODE_PLAN,
  isModelModeAllowed,
} from '../features/chat/modelModeAccess.js';

const RECORDING_WAVE_HEIGHTS = [12, 18, 14, 20, 16];

const ChatInputArea = ({
  isNewChat,
  isGenerating,
  handleStopGeneration,
  user,
  selectedFile,
  setSelectedFile,
  setShowFileModal,
  fetchAvailableFiles,
  handleSend,
  isRecording,
  input,
  setInput,
  textareaRef,
  toggleRecording,
  isEn,
  getDisplayName,
  mappedColumnCount = 0,
  onEditColumnMapping,
  onClearAttachedFile,
  inputPlaceholder,
  dbConnections = [],
  apiConnections = [],
  activeConnection,
  setActiveConnection,
  connectionMappedColumnCount = 0,
  onEditConnectionMapping,
  sessionFileName = null,
  sessionMappedColumnCount = 0,
  onClearSessionFile,
  onEditSessionColumnMapping,
  modelMode = 'auto',
  setModelMode,
  plan,
  isPlanLoading = false,
  canSendSourceOnly = false,
  panelMode = false,
}) => {
  const { locale } = useLocaleRouting();
  const m = getMessages(locale);
  const firstName = user?.user_metadata?.full_name?.split(' ')[0] || '';
  const [showMentions, setShowMentions] = useState(false);
  const [mentionSearch, setMentionSearch] = useState('');
  const [selectedMentionIndex, setSelectedMentionIndex] = useState(0);
  const [mentionPhase, setMentionPhase] = useState('connection');
  const [mentionConn, setMentionConn] = useState<any>(null);
  const [tablesCache, setTablesCache] = useState<Record<string, any>>({});
  const [tablesLoading, setTablesLoading] = useState(false);
  const [tablesError, setTablesError] = useState('');
  const [tableFilter, setTableFilter] = useState('');
  const [showModelMenu, setShowModelMenu] = useState(false);
  const [modelMenuDirection, setModelMenuDirection] = useState('up');
  const modelControlRef = useRef(null);
  const modelOptions = [
    {
      value: 'auto',
      label: isEn ? 'Auto' : 'อัตโนมัติ',
      desc: isEn ? 'Choose the best model for each request' : 'เลือกรุ่นที่เหมาะกับคำถามให้อัตโนมัติ',
      Icon: Layers3,
      activeClass: 'border-orange-200 bg-orange-50 text-orange-900 dark:border-orange-500/35 dark:bg-orange-500/10 dark:text-orange-200',
      iconClass: 'bg-orange-100 text-orange-800 dark:bg-orange-500/15 dark:text-orange-300',
    },
    {
      value: 'fast',
      label: isEn ? 'Fast' : 'เร็ว',
      desc: isEn ? 'Prioritize speed for straightforward tasks' : 'เน้นตอบไวสำหรับคำถามทั่วไป',
      Icon: Zap,
      activeClass: 'border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-500/50 dark:bg-sky-500/15 dark:text-sky-200',
      iconClass: 'bg-sky-100 text-sky-700 dark:bg-sky-500/20 dark:text-sky-300',
    },
    {
      value: 'deep',
      label: isEn ? 'Deep' : 'เจาะลึก',
      desc: isEn ? 'Use deeper reasoning for complex analysis' : 'วิเคราะห์ละเอียดสำหรับงานซับซ้อน',
      Icon: Gauge,
      activeClass: 'border-slate-300 bg-slate-100 text-slate-800 dark:border-slate-600 dark:bg-slate-800/80 dark:text-slate-100',
      iconClass: 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200',
    },
  ];
  const selectedModelOption =
    modelOptions.find((option) => option.value === modelMode) || modelOptions[0];
  const SelectedModelIcon = selectedModelOption.Icon;

  const toggleModelMenu = () => {
    if (showModelMenu) {
      setShowModelMenu(false);
      return;
    }
    const rect = modelControlRef.current?.getBoundingClientRect();
    if (rect) {
      const spaceAbove = rect.top;
      const spaceBelow = window.innerHeight - rect.bottom;
      setModelMenuDirection(spaceBelow >= 230 || spaceBelow >= spaceAbove ? 'down' : 'up');
    }
    setShowModelMenu(true);
  };

  const allConnections = [
    ...dbConnections.map((c) => ({ ...c, type: 'sql' })),
    ...apiConnections.map((c) => ({ ...c, type: 'api' })),
  ];

  const filteredConnections = allConnections.filter((c) =>
    c.name.toLowerCase().includes(mentionSearch.toLowerCase())
  );

  const tableList = mentionConn ? tablesCache[mentionConn.id] || [] : [];
  const filteredTables = tableList.filter((tbl) =>
    tbl.toLowerCase().includes((mentionPhase === 'table' ? tableFilter : mentionSearch).toLowerCase())
  );

  const mentionListLength =
    mentionPhase === 'table' ? filteredTables.length : filteredConnections.length;

  const loadTables = useCallback(
    async (conn) => {
      if (!conn?.id || !user?.id) return [];
      if (tablesCache[conn.id]) return tablesCache[conn.id];
      setTablesLoading(true);
      setTablesError('');
      try {
        const res = await api.get(`/api/v1/db-connections/${conn.id}/tables`);
        const tables = res.data?.tables || [];
        setTablesCache((prev) => ({ ...prev, [conn.id]: tables }));
        return tables;
      } catch (err: any) {
        const msg =
          err.response?.data?.detail ||
          (isEn ? 'Could not load tables.' : 'โหลดรายชื่อตารางไม่สำเร็จ');
        setTablesError(String(msg));
        return [];
      } finally {
        setTablesLoading(false);
      }
    },
    [tablesCache, user, isEn]
  );

  const closeMentions = () => {
    setShowMentions(false);
    setMentionPhase('connection');
    setMentionConn(null);
    setMentionSearch('');
    setTableFilter('');
    setSelectedMentionIndex(0);
  };

  const selectApiConnection = (conn) => {
    setActiveConnection({ ...conn, sqlTable: undefined });
    closeMentions();
    const cursor = textareaRef.current?.selectionStart ?? input.length;
    const textBeforeCursor = input.slice(0, cursor);
    const textAfterCursor = input.slice(cursor);
    const atIndex = textBeforeCursor.lastIndexOf('@');
    if (atIndex !== -1) {
      setInput(textBeforeCursor.slice(0, atIndex) + textAfterCursor);
    }
    setTimeout(() => textareaRef.current?.focus(), 0);
  };

  const openSqlTablePhase = async (conn) => {
    setMentionConn(conn);
    setMentionPhase('table');
    setMentionSearch('');
    setTableFilter('');
    setSelectedMentionIndex(0);
    setShowMentions(true);
    await loadTables(conn);
  };

  const selectSqlTable = (conn, tableName) => {
    setActiveConnection({ ...conn, sqlTable: tableName });
    closeMentions();
    const cursor = textareaRef.current?.selectionStart ?? input.length;
    const textBeforeCursor = input.slice(0, cursor);
    const textAfterCursor = input.slice(cursor);
    const atIndex = textBeforeCursor.lastIndexOf('@');
    if (atIndex !== -1) {
      setInput(textBeforeCursor.slice(0, atIndex) + textAfterCursor);
    }
    setTimeout(() => textareaRef.current?.focus(), 0);
  };

  const handleSelectConnection = (conn) => {
    if (conn.type === 'sql') {
      openSqlTablePhase(conn);
    } else {
      selectApiConnection(conn);
    }
  };

  const handleSelectMentionItem = () => {
    if (mentionPhase === 'table' && mentionConn && filteredTables.length > 0) {
      selectSqlTable(mentionConn, filteredTables[selectedMentionIndex]);
    } else if (mentionPhase === 'connection' && filteredConnections.length > 0) {
      handleSelectConnection(filteredConnections[selectedMentionIndex]);
    }
  };

  const handleInputChange = (e) => {
    const text = e.target.value;
    setInput(text);

    const cursor = e.target.selectionStart;
    const textBeforeCursor = text.slice(0, cursor);
    const atIndex = textBeforeCursor.lastIndexOf('@');

    if (atIndex !== -1 && !textBeforeCursor.slice(atIndex, cursor).includes(' ')) {
      const search = textBeforeCursor.slice(atIndex + 1, cursor);
      const dashIdx = search.indexOf('-');
      if (dashIdx > 0) {
        const connPart = search.slice(0, dashIdx);
        const tablePart = search.slice(dashIdx + 1);
        const conn = allConnections.find(
          (c) => c.type === 'sql' && c.name.toLowerCase() === connPart.toLowerCase()
        );
        if (conn) {
          setMentionConn(conn);
          setMentionPhase('table');
          setTableFilter(tablePart);
          setMentionSearch('');
          setSelectedMentionIndex(0);
          setShowMentions(true);
          loadTables(conn);
          return;
        }
      }
      setMentionPhase('connection');
      setMentionConn(null);
      setMentionSearch(search);
      setSelectedMentionIndex(0);
      setShowMentions(true);
    } else {
      closeMentions();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Escape' && isGenerating) {
      e.preventDefault();
      handleStopGeneration();
      return;
    }
    if (showMentions && mentionListLength > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedMentionIndex((prev) => (prev + 1) % mentionListLength);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedMentionIndex((prev) => (prev - 1 + mentionListLength) % mentionListLength);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        handleSelectMentionItem();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        if (mentionPhase === 'table') {
          setMentionPhase('connection');
          setMentionConn(null);
          setMentionSearch('');
          setSelectedMentionIndex(0);
        } else {
          closeMentions();
        }
      }
    } else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend(e);
    }
  };

  const clearActiveConnection = () => {
    setActiveConnection(null);
  };

  const highlightTableName = (name, query) => {
    if (!query) return name;
    const idx = name.toLowerCase().indexOf(query.toLowerCase());
    if (idx === -1) return name;
    return (
      <>
        {name.slice(0, idx)}
        <span className="text-orange-700 dark:text-orange-300 font-semibold">{name.slice(idx, idx + query.length)}</span>
        {name.slice(idx + query.length)}
      </>
    );
  };

  return (
    <div className={`chat-composer-wrap relative z-10 ${isNewChat && !panelMode ? 'chat-composer-new flex flex-1 flex-col items-center justify-center px-4 py-8' : 'chat-composer-docked px-3 pb-3 pt-2 sm:px-6 sm:pb-5'}`}>
      <div className="relative z-20 mx-auto w-full max-w-[800px]">
        {isNewChat && !panelMode && (
          <div className="mb-9 flex flex-col items-center text-center">
            <span className="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-stone-200 bg-stone-50 text-stone-700 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-300">
              <BarChart3 size={18} strokeWidth={1.7} />
            </span>
            <h2 className="text-2xl font-semibold leading-tight tracking-[-0.025em] text-stone-950 dark:text-white md:text-[28px]">
              {firstName
                ? t(m, 'chat.hello_name', 'Hi, {name}', { name: firstName })
                : t(m, 'chat.hello', 'Hi')}
            </h2>
            <p className="mt-2 text-sm text-stone-500 dark:text-stone-400">
              {t(m, 'chat.hero_question', 'What should we analyze?')}
            </p>
          </div>
        )}

        {selectedFile && !panelMode && (
          <div className="mb-2 flex items-center gap-2 flex-wrap">
            <div className="enterprise-panel px-3 py-1.5 flex items-center gap-2">
              <div className="w-6 h-6 bg-slate-100 dark:bg-slate-800 rounded flex items-center justify-center text-slate-600 dark:text-slate-400">
                <FileText className="w-3.5 h-3.5" strokeWidth={1.5} />
              </div>
              <span className="text-xs font-sans font-medium truncate max-w-[200px] text-slate-700 dark:text-slate-300">{getDisplayName(selectedFile.name)}</span>
              {mappedColumnCount > 0 && (
                <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-orange-500/10 text-orange-800 dark:text-orange-300">
                  {t(m, 'chat.mapping.mapped_badge', '{count} mapped', { count: mappedColumnCount })}
                </span>
              )}
              <button
                type="button"
                onClick={() => (onClearAttachedFile ? onClearAttachedFile() : setSelectedFile(null))}
                className="text-slate-400 hover:text-red-500 transition-colors"
              >
                <X className="w-4 h-4" strokeWidth={1.5} />
              </button>
            </div>
            {onEditColumnMapping && (
              <button
                type="button"
                onClick={() => onEditColumnMapping()}
                className="rounded-full border border-slate-200 bg-white/90 px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm transition-colors hover:border-orange-300 hover:bg-orange-50 hover:text-orange-900 focus:outline-none focus:ring-2 focus:ring-orange-300/60 dark:border-slate-700 dark:bg-slate-900/80 dark:text-slate-200 dark:hover:border-orange-500/40 dark:hover:bg-orange-500/10 dark:hover:text-orange-200"
              >
                {t(m, 'chat.mapping.edit_mapping', 'Edit column mapping')}
              </button>
            )}
          </div>
        )}

        {sessionFileName && !selectedFile && !panelMode && (
          <div className="mb-2 flex items-center gap-2 flex-wrap">
            <div className="enterprise-panel px-3 py-1.5 flex items-center gap-2 border border-orange-200/80 bg-orange-50/60 dark:border-orange-500/25 dark:bg-orange-500/10">
              <div className="w-6 h-6 bg-orange-500/10 rounded flex items-center justify-center text-orange-800 dark:text-orange-300">
                <FileText className="w-3.5 h-3.5" strokeWidth={1.5} />
              </div>
              <span className="text-[10px] font-semibold uppercase tracking-wide text-orange-800 dark:text-orange-300">
                {t(m, 'chat.session_file_badge', 'Active dataset')}
              </span>
              <span className="text-xs font-sans font-medium truncate max-w-[200px] text-slate-700 dark:text-slate-300">
                {getDisplayName(sessionFileName)}
              </span>
              {sessionMappedColumnCount > 0 && (
                <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-orange-500/10 text-orange-800 dark:text-orange-300">
                  {t(m, 'chat.mapping.mapped_badge', '{count} mapped', { count: sessionMappedColumnCount })}
                </span>
              )}
              {onClearSessionFile && (
                <button
                  type="button"
                  onClick={onClearSessionFile}
                  className="text-slate-400 hover:text-red-500 transition-colors"
                  title={t(m, 'chat.session_file_clear', 'Stop using this file')}
                >
                  <X className="w-4 h-4" strokeWidth={1.5} />
                </button>
              )}
            </div>
            {onEditSessionColumnMapping && (
              <button
                type="button"
                onClick={() => onEditSessionColumnMapping()}
                className="rounded-full border border-slate-200 bg-white/90 px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm transition-colors hover:border-orange-300 hover:bg-orange-50 hover:text-orange-900 focus:outline-none focus:ring-2 focus:ring-orange-300/60 dark:border-slate-700 dark:bg-slate-900/80 dark:text-slate-200 dark:hover:border-orange-500/40 dark:hover:bg-orange-500/10 dark:hover:text-orange-200"
              >
                {t(m, 'chat.mapping.edit_mapping', 'Edit column mapping')}
              </button>
            )}
            {onClearSessionFile && (
              <button
                type="button"
                onClick={onClearSessionFile}
                className="text-xs font-medium text-slate-500 dark:text-slate-400 hover:text-red-500 px-2 py-1"
              >
                {t(m, 'chat.session_file_clear', 'Stop using this file')}
              </button>
            )}
          </div>
        )}

        <div className="relative">
          {showMentions && (
            <div className="absolute bottom-[calc(100%+8px)] left-0 w-full max-w-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-xl z-50 overflow-hidden">
              <div className="px-3 py-2.5 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/80">
                <div className="flex items-center gap-2 mb-2">
                  {mentionPhase === 'table' && (
                    <button
                      type="button"
                      onClick={() => {
                        setMentionPhase('connection');
                        setMentionConn(null);
                        setTableFilter('');
                        setMentionSearch('');
                        setSelectedMentionIndex(0);
                      }}
                      className="p-1 rounded-md hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-500 shrink-0"
                      title={isEn ? 'Back' : 'กลับ'}
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </button>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">
                      {mentionPhase === 'table'
                        ? mentionConn?.name
                        : t(m, 'chat.mention_select_connection', isEn ? 'Database / API' : 'ฐานข้อมูล / API')}
                    </p>
                    {mentionPhase === 'table' && (
                      <p className="text-[11px] text-slate-500 truncate">
                        {tablesLoading
                          ? t(m, 'chat.mention_tables_loading', isEn ? 'Loading tables…' : 'กำลังโหลดตาราง…')
                          : t(m, 'chat.mention_tables_count', isEn ? '{count} tables' : '{count} ตาราง', {
                              count: tableList.length,
                            })}
                      </p>
                    )}
                  </div>
                </div>

                {mentionPhase === 'table' && !tablesLoading && !tablesError && (
                  <div className="relative">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
                    <input
                      type="text"
                      value={tableFilter}
                      onChange={(e) => {
                        setTableFilter(e.target.value);
                        setSelectedMentionIndex(0);
                      }}
                      placeholder={t(m, 'chat.mention_table_search', isEn ? 'Search tables…' : 'ค้นหาตาราง…')}
                      className="w-full pl-8 pr-3 py-2 text-sm bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl outline-none focus:border-orange-500/50 text-slate-800 dark:text-slate-100 placeholder:text-slate-400"
                      onKeyDown={(e) => {
                        if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter') {
                          handleKeyDown(e);
                        }
                      }}
                    />
                  </div>
                )}
              </div>

              {mentionPhase === 'connection' && filteredConnections.length > 0 && (
                <div className="max-h-[240px] overflow-y-auto no-scrollbar py-1">
                  {filteredConnections.map((conn, idx) => (
                    <button
                      key={conn.id}
                      type="button"
                      onClick={() => handleSelectConnection(conn)}
                      className={`w-full text-left px-3 py-2.5 flex items-center justify-between gap-3 transition-colors text-sm ${
                        selectedMentionIndex === idx
                          ? 'bg-orange-500/10 text-orange-800 dark:text-orange-300'
                          : 'hover:bg-slate-50 dark:hover:bg-slate-800/50 text-slate-800 dark:text-slate-200'
                      }`}
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
                          {conn.type === 'sql' ? <Database className="w-4 h-4" /> : <Globe className="w-4 h-4" />}
                        </div>
                        <span className="truncate font-medium">{conn.name}</span>
                      </div>
                      <span className="text-[10px] font-medium bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded-md text-slate-500 uppercase shrink-0">
                        {conn.type === 'sql' ? conn.provider : conn.method}
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {mentionPhase === 'connection' && filteredConnections.length === 0 && (
                <p className="px-4 py-6 text-sm text-center text-slate-500">{isEn ? 'No connections found.' : 'ไม่พบการเชื่อมต่อ'}</p>
              )}

              {mentionPhase === 'table' && tablesError && (
                <p className="px-4 py-6 text-sm text-center text-red-500">{tablesError}</p>
              )}

              {mentionPhase === 'table' && !tablesLoading && !tablesError && filteredTables.length > 0 && (
                <div className="max-h-[280px] overflow-y-auto no-scrollbar py-1">
                  {filteredTables.map((tbl, idx) => (
                    <button
                      key={tbl}
                      type="button"
                      onClick={() => selectSqlTable(mentionConn, tbl)}
                      className={`w-full text-left px-3 py-2 flex items-center gap-2.5 transition-colors text-sm font-mono ${
                        selectedMentionIndex === idx
                          ? 'bg-orange-500/10 text-orange-800 dark:text-orange-300'
                          : 'hover:bg-slate-50 dark:hover:bg-slate-800/50 text-slate-700 dark:text-slate-200'
                      }`}
                    >
                      <Table2 className="w-3.5 h-3.5 shrink-0 opacity-60" />
                      <span className="truncate">{highlightTableName(tbl, tableFilter)}</span>
                    </button>
                  ))}
                </div>
              )}

              {mentionPhase === 'table' && !tablesLoading && !tablesError && filteredTables.length === 0 && (
                <p className="px-4 py-6 text-sm text-center text-slate-500">
                  {tableList.length === 0
                    ? (isEn ? 'No tables in this database.' : 'ไม่มีตารางในฐานข้อมูลนี้')
                    : (isEn ? 'No tables match your search.' : 'ไม่พบตารางที่ตรงกับการค้นหา')}
                </p>
              )}
            </div>
          )}

          <div className={`chat-composer relative flex items-end gap-1 rounded-2xl border border-slate-300/80 bg-white/94 p-2 pr-2.5 shadow-[0_12px_32px_rgba(15,23,42,0.08)] transition-[border-color,box-shadow,margin] focus-within:border-orange-400 focus-within:shadow-[0_14px_36px_rgba(201,106,22,0.11)] dark:border-slate-700 dark:bg-slate-900/94 dark:shadow-[0_16px_40px_rgba(2,6,23,0.28)] dark:focus-within:border-orange-500/70 ${panelMode ? 'flex-wrap items-center' : ''} ${panelMode && showModelMenu && modelMenuDirection === 'down' ? 'mb-[220px]' : ''}`}>
            <button
              onClick={() => { setShowFileModal(true); fetchAvailableFiles(); }}
              className={`rounded-lg p-2.5 text-slate-400 transition-colors dark:text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-300 shrink-0 ${panelMode ? 'mb-0' : 'mb-0.5'}`}
              title={isEn ? 'Attach file' : 'แนบไฟล์'}
            >
              <Paperclip className="w-5 h-5" strokeWidth={1.5} />
            </button>

            {activeConnection && !panelMode && (
              <div className="mb-1 flex max-w-36 shrink-0 items-center gap-1.5 rounded-lg border border-stone-200 bg-stone-50 px-2.5 py-1.5 dark:border-stone-700 dark:bg-stone-800/50 sm:max-w-64">
                <div className="text-slate-600 dark:text-slate-400">
                  {activeConnection.type === 'sql' ? <Database className="w-3.5 h-3.5" /> : <Globe className="w-3.5 h-3.5" />}
                </div>
                <span className="truncate font-sans text-xs font-medium text-stone-700 dark:text-stone-300">
                  {formatConnectionMention(activeConnection.name, activeConnection.sqlTable)}
                </span>
                {connectionMappedColumnCount > 0 && (
                  <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300">
                    {t(m, 'chat.mapping.mapped_badge', '{count} mapped', {
                      count: connectionMappedColumnCount,
                    })}
                  </span>
                )}
                {activeConnection.type === 'api' && onEditConnectionMapping && (
                  <button
                    type="button"
                    onClick={onEditConnectionMapping}
                    className="text-[10px] font-semibold text-orange-800 hover:text-orange-950 dark:text-orange-300 dark:hover:text-orange-100"
                  >
                    {t(m, 'chat.mapping.edit_mapping', 'Edit column mapping')}
                  </button>
                )}
                <button
                  type="button"
                  onClick={clearActiveConnection}
                  className="text-slate-400 hover:text-red-500 transition-colors"
                >
                  <X className="w-4 h-4" strokeWidth={1.5} />
                </button>
              </div>
            )}

            <form onSubmit={handleSend} className={`flex min-w-0 items-end gap-1 ${panelMode ? 'basis-full' : 'flex-1'}`}>
              <textarea
                ref={textareaRef}
                value={input}
                onChange={handleInputChange}
                placeholder={
                  isRecording
                    ? t(m, 'chat.listening', 'Listening...')
                    : inputPlaceholder || t(m, 'chat.placeholder', 'Ask MataQorLab...')
                }
                className={`w-full min-h-[44px] py-3 px-1 bg-transparent border-none outline-none font-sans text-[15px] leading-relaxed text-stone-800 dark:text-stone-100 resize-none max-h-[200px] min-w-0 [field-sizing:content] ${panelMode ? 'chat-panel-textarea max-h-[88px] !min-h-[44px] ![field-sizing:fixed]' : ''} ${
                  isNewChat
                    ? 'placeholder:text-slate-500 dark:placeholder:text-slate-400'
                    : 'placeholder:text-slate-400 dark:placeholder:text-slate-600'
                }`}
                rows="1"
                onKeyDown={handleKeyDown}
                readOnly={isRecording}
                aria-live={isRecording ? 'polite' : undefined}
              />
              {isRecording && (
                <div
                  className="mb-1 flex h-9 shrink-0 items-center gap-1.5 rounded-lg bg-red-50 px-2 text-red-600 dark:bg-red-950/40 dark:text-red-300"
                  title={isEn ? 'Live speech-to-text is active' : 'กำลังพิมพ์ข้อความจากเสียง'}
                >
                  <div className="flex items-center gap-0.5">
                    {RECORDING_WAVE_HEIGHTS.slice(0, 3).map((height, index) => (
                      <span
                        key={height}
                        className="w-0.5 rounded-full bg-current animate-pulse"
                        style={{
                          height: `${Math.max(7, height - 5)}px`,
                          animationDelay: `${index * 0.12}s`,
                        }}
                      />
                    ))}
                  </div>
                  <span className="hidden text-[10px] font-semibold sm:inline">
                    {isEn ? 'LIVE' : 'กำลังฟัง'}
                  </span>
                </div>
              )}
              {setModelMode && (
                <div ref={modelControlRef} className="relative mb-1 shrink-0">
                  {showModelMenu && (
                      <div className={`absolute right-0 z-[70] w-64 overflow-hidden rounded-xl border border-stone-200 bg-white p-1.5 shadow-[0_18px_48px_rgba(15,23,42,.16)] dark:border-stone-700 dark:bg-zinc-950 ${modelMenuDirection === 'down' ? 'top-[calc(100%+8px)]' : 'bottom-[calc(100%+8px)]'}`}>
                      <div className="px-2.5 pb-1.5 pt-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                        {isEn ? 'Response mode' : 'โหมดการตอบ'}
                      </div>
                      {modelOptions.map((option) => {
                        const OptionIcon = option.Icon;
                        const isSelected = option.value === modelMode;
                        const isLocked =
                          !isPlanLoading && !isModelModeAllowed(option.value, plan?.name);
                        const requiredPlan = MODEL_MODE_PLAN[option.value];
                        return (
                          <button
                            key={option.value}
                            type="button"
                            disabled={isLocked}
                            onClick={() => {
                              setModelMode(option.value);
                              setShowModelMenu(false);
                            }}
                            title={isLocked
                              ? (isEn
                                  ? `${requiredPlan} plan or higher is required`
                                  : `ต้องใช้แพลน ${requiredPlan} ขึ้นไป`)
                              : undefined}
                            className={`flex w-full items-center gap-3 rounded-lg px-2.5 py-2.5 text-left transition-colors ${
                              isLocked
                                ? 'cursor-not-allowed text-slate-400 opacity-60 dark:text-slate-500'
                                : isSelected
                                ? option.activeClass
                                : 'text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800/80'
                            }`}
                          >
                            <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${option.iconClass}`}>
                              <OptionIcon size={16} strokeWidth={1.8} />
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block text-xs font-semibold">{option.label}</span>
                              <span className="mt-0.5 block text-[10px] leading-snug opacity-75">{option.desc}</span>
                            </span>
                            {isLocked ? (
                              <span className="flex shrink-0 items-center gap-1 text-[9px] font-semibold uppercase">
                                {requiredPlan}
                                <Lock size={12} strokeWidth={2} />
                              </span>
                            ) : (
                              isSelected && <Check size={15} className="shrink-0" strokeWidth={2.2} />
                            )}
                          </button>
                        );
                      })}
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={toggleModelMenu}
                    className={`flex items-center gap-1.5 rounded-lg border font-semibold transition-all hover:-translate-y-px hover:shadow-sm ${panelMode ? 'h-8 px-2 text-[10px]' : 'h-9 px-2.5 text-xs'} ${selectedModelOption.activeClass}`}
                    title={`${isEn ? 'Model' : 'โมเดล'}: ${selectedModelOption.label} — ${selectedModelOption.desc}`}
                    aria-haspopup="menu"
                    aria-expanded={showModelMenu}
                  >
                    <SelectedModelIcon size={15} strokeWidth={1.8} />
                    <span className="hidden sm:inline">{selectedModelOption.label}</span>
                    <ChevronDown
                      size={13}
                      className={`transition-transform ${showModelMenu ? 'rotate-180' : ''}`}
                    />
                  </button>
                </div>
              )}
              <button type="button" onClick={toggleRecording} className={`p-2 rounded-lg transition-colors mb-1 mr-1 shrink-0 ${isRecording ? 'bg-red-50 dark:bg-red-950/30 text-red-500' : 'text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'}`}>
                {isRecording ? <MicOff size={22} strokeWidth={1.5} /> : <Mic size={22} strokeWidth={1.5} />}
              </button>
              <button
                type={isGenerating ? 'button' : 'submit'}
                onClick={isGenerating ? handleStopGeneration : undefined}
                disabled={!isGenerating && ((!input.trim() && !canSendSourceOnly) || isRecording)}
                title={isGenerating ? (isEn ? 'Stop generating' : 'หยุดการสร้าง') : (isEn ? 'Send message' : 'ส่งข้อความ')}
                className={`p-2 rounded-lg transition-colors mb-1 shrink-0 ${
                  isGenerating
                    ? 'bg-slate-800 text-white hover:bg-slate-900 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white'
                    : (input.trim() || canSendSourceOnly)
                      ? 'btn-primary !py-2 !px-2'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-300 dark:text-slate-600 cursor-not-allowed'
                }`}
              >
                {isGenerating ? (
                  <Square className="w-5 h-5 fill-current" strokeWidth={1.5} />
                ) : (
                  <ArrowUp className="w-5 h-5" strokeWidth={1.5} />
                )}
              </button>
            </form>
          </div>
        </div>
        <p className="mx-auto mt-2.5 w-fit text-center font-sans text-[10px] text-stone-400 dark:text-stone-500">
          {t(m, 'chat.disclaimer', 'AI output may be inaccurate. Verify important data.')}
        </p>
      </div>
    </div>
  );
};

export default ChatInputArea;
