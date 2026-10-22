// @ts-nocheck
'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { supabase } from '../utils/supabaseClient.js';
import { useRouter, usePathname, useParams, useSearchParams } from 'next/navigation';
import { PanelLeftOpen, BarChart3, LineChart, PieChart, AreaChart, ShieldCheck, MessageSquare, Layers3, FileText, Database, Globe } from '@/components/icons';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { useFileManagerCache } from '../context/FileManagerCacheContext';
import { localePath } from '../utils/locale.js';
import { buildChatPath, isUuid, normalizeAppPath } from '../utils/dashboardRoutes.js';

import ChatMessageList from '../features/chat/ChatMessageList';
import ChatMemoryPanel from '../features/chat/ChatMemoryPanel';
import ChatBranchSelector from '../features/chat/ChatBranchSelector';
import ChatSidebar from '../components/ChatSidebar';
import ChatInputArea from '../components/ChatInputArea';
import { FileSelectionModal, DeleteConfirmationModal, ColumnMappingModal, QuotaExceededModal } from '../components/ChatModals';
import { getMessages, t } from '../utils/i18n.js';
import { INITIAL_REASONING_PROGRESS } from '../features/chat/reasoningProgress.js';
import { countMappedColumns } from '../features/chat/columnMappingOptions.js';
import { parseFileSample } from '../features/chat/parseFileSample.js';
import { useChatQuota } from '../features/chat/hooks/useChatQuota.js';
import { useChatConversations } from '../features/chat/hooks/useChatConversations.js';
import { useChatSend } from '../features/chat/hooks/useChatSend.js';
import {
  applyStreamOrchestrationUpdate,
  finishChatTurn,
  recoverStaleChatTurn,
} from '../features/chat/chatTurnLifecycle.js';
import {
  readLocalConversationalFlag,
  CurrentWorkflowPanel,
  useSetupReconciliation,
  createEmptyCurrentOrchestrationState,
} from '../features/chat/orchestration/index.js';
import { shouldResetConversationOnNewRoute } from '../features/chat/chatRouteTransition.js';
import { resolveModelModeForPlan } from '../features/chat/modelModeAccess.js';
import { precedingUserMessage } from '../features/chat/chatBranches.js';
import { extractSystemCommands, sanitizeChatMessage } from '../features/chat/messageContent.js';
import { getE2eMockUser } from '../utils/e2eAuth.js';
import { authFetch } from '../utils/authFetch.js';
import { formatApiErrorDetail } from '../utils/formatApiErrorDetail.js';
import { getPublicApiUrl } from '../utils/env.js';
import { fetchFilePage } from '../utils/fileListApi.js';
import {
  loadChatSession,
  saveChatSession,
  clearChatSession,
  clearChatSessionConnection,
  clearChatSessionFile,
  resolveStoredConnection,
  connectionFromMessages,
  fileFromMessages,
  resolveStoredFile,
  saveConversationSnapshot,
} from '../features/chat/chatSessionStorage.js';
import {
  getSpeechRecognitionConstructor,
  joinSpeechTranscript,
  speechRecognitionErrorMessage,
} from '../features/chat/speechRecognition.js';

const stableJson = (value) => {
  if (!value) return '';
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};

const sameMapping = (a, b) => stableJson(a || null) === stableJson(b || null);

const sameConnection = (a, b) => {
  if (!a && !b) return true;
  if (!a || !b) return false;
  return (
    a.id === b.id &&
    a.name === b.name &&
    a.type === b.type &&
    (a.sqlTable || null) === (b.sqlTable || null) &&
    sameMapping(a.mapping, b.mapping) &&
    stableJson(a.cleaningRecipe || null) === stableJson(b.cleaningRecipe || null) &&
    (a.cleaningProfile || null) === (b.cleaningProfile || null)
  );
};

const sameSessionFile = (a, b) => {
  if (!a && !b) return true;
  if (!a || !b) return false;
  return (
    a.name === b.name
    && sameMapping(a.mapping, b.mapping)
    && stableJson(a.cleaningRecipe || null) === stableJson(b.cleaningRecipe || null)
    && (a.cleaningProfile || null) === (b.cleaningProfile || null)
  );
};

const SIDEBAR_OPEN_STORAGE_KEY = 'chat_sidebar_open';
const MODEL_MODE_STORAGE_KEY = 'chat_model_mode';

const Chat = ({
  mode = 'full',
  conversationId: embeddedConversationId = null,
  visualizationContext = null,
  onConversationCreated: onEmbeddedConversationCreated = null,
  onGenerationChange = null,
  onOpenFullChat = null,
  onClosePanel = null,
  onClearVisualizationWidget = null,
  onPreviewDashboard = null,
  dashboardPreviewBusy = false,
  panelPreset = null,
}) => {
  const isPanel = mode === 'panel';
  const router = useRouter();
  const fileManagerCache = useFileManagerCache();
  const pathname = usePathname();
  const { conversationId: routeConversationParam } = useParams();
  const routeConversationId = embeddedConversationId || routeConversationParam;
  const searchParams = useSearchParams();
  const navigate = useCallback((path, options) => {
    if (options?.replace) router.replace(path);
    else router.push(path);
  }, [router]);
  const replaceBrowserUrl = useCallback((path) => {
    router.replace(path);
  }, [router]);
  const promoteConversationUrl = useCallback((path) => {
    // Replacing the URL through Next navigation swaps the `/chat/new` page
    // segment and can unmount the component that owns the active SSE stream.
    // The native History API is integrated with the App Router and keeps this
    // client component alive while the first response is being generated.
    window.history.replaceState(window.history.state, '', path);
  }, []);
  const urlHydratedRef = useRef(false);
  const promotedConversationIdRef = useRef<string | null>(null);
  const routeChatId = isUuid(routeConversationId) ? routeConversationId : null;

  // --- การจัดการ State หลัก ---
  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState('');
  const [user, setUser] = useState<any>(null);

  const routing = useLocaleRouting();
  const chatAppPath = normalizeAppPath(pathname, routing.localePrefix);
  const isNewChatRoute = chatAppPath === '/chat/new' || (isPanel && !routeConversationId);
  const m = getMessages(routing.locale);
  const isEn = routing.locale === 'en';
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);
  const speechRecognitionRef = useRef<any>(null);
  const speechShouldContinueRef = useRef(false);
  const speechBaseInputRef = useRef('');
  const speechCurrentTextRef = useRef('');
  const speechConfirmedTextRef = useRef('');
  const speechRestartTimerRef = useRef<any>(null);
  const stopGenerationRef = useRef(() => {});
  const stopActiveGeneration = useCallback(() => {
    stopGenerationRef.current();
  }, []);

  // --- State สำหรับ UI และฟังก์ชันเสริม ---
  const [showFileModal, setShowFileModal] = useState(false);
  const [availableFiles, setAvailableFiles] = useState<any[]>([]);
  const [nextAvailableFilesOffset, setNextAvailableFilesOffset] = useState<number | null>(null);
  const [selectedFile, setSelectedFile] = useState<any>(null);
  const [isFilesLoading, setIsFilesLoading] = useState(false);
  const [showMappingModal, setShowMappingModal] = useState(false);
  const [parsedDataForMapping, setParsedDataForMapping] = useState<any>(null);
  const [jsonPathOptions, setJsonPathOptions] = useState<string[]>([]);
  const [selectedJsonPath, setSelectedJsonPath] = useState<string | null>(null);
  const [confirmedMapping, setConfirmedMapping] = useState<any>(null);
  const [mappingTarget, setMappingTarget] = useState<any>(null);
  const [fileColumnMappings, setFileColumnMappings] = useState<Record<string, any>>({});
  const [sessionFileContext, setSessionFileContext] = useState<any>(null);
  const [isTyping, setIsTyping] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [stopTyping, setStopTyping] = useState(false);
  const [dbConnections, setDbConnections] = useState<any[]>([]);
  const [apiConnections, setApiConnections] = useState<any[]>([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(() => {
    if (typeof window === 'undefined') return false;
    return localStorage.getItem(SIDEBAR_OPEN_STORAGE_KEY) === 'true';
  });
  const [isRecording, setIsRecording] = useState(false);
  const [aiError, setAiError] = useState<any>(null);
  const [reasoningProgress, setReasoningProgress] = useState(INITIAL_REASONING_PROGRESS);
  const [analysisContext, setAnalysisContext] = useState<Record<string, any>>({});
  const [isAnalysisQuery, setIsAnalysisQuery] = useState(true);
  const [analysisStreamStarted, setAnalysisStreamStarted] = useState(false);
  const [activeConnection, setActiveConnection] = useState<any>(null);
  const [agentSession, setAgentSession] = useState<any>(null);
  const [cleaningProfile, setCleaningProfile] = useState('standard');
  const [cleaningRecipe, setCleaningRecipe] = useState<any>(null);
  const [modelMode, setModelMode] = useState(() => {
    if (typeof window === 'undefined') return 'auto';
    const saved = localStorage.getItem(MODEL_MODE_STORAGE_KEY);
    return ['auto', 'fast', 'deep'].includes(saved) ? saved : 'auto';
  });
  const [bottomCharts, setBottomCharts] = useState<any[]>([]);
  const [showChartModal, setShowChartModal] = useState(false);
  const [selectedTypes, setSelectedTypes] = useState<any[]>([]);
  const [showMemoryPanel, setShowMemoryPanel] = useState(false);
  const [dataSetupSession, setDataSetupSession] = useState<any>(null);
  const [conversationalSetupEnabled, setConversationalSetupEnabled] = useState(() => {
    const local = readLocalConversationalFlag();
    return local === true;
  });
  const [capabilitiesReady, setCapabilitiesReady] = useState(false);
  const conversationalFlagRef = useRef(conversationalSetupEnabled);
  const capabilitiesPromiseRef = useRef<Promise<boolean> | null>(null);
  const conversationalKickoffRef = useRef<string | null>(null);
  const analysisKickoffRef = useRef<string | null>(null);
  const sendInFlightRef = useRef(false);
  const workspaceResetRef = useRef(() => {});
  const [isSendInFlight, setIsSendInFlight] = useState(false);

  const withSendGuard = useCallback(async (fn) => {
    if (sendInFlightRef.current) return;
    sendInFlightRef.current = true;
    setIsSendInFlight(true);
    try {
      await fn();
    } finally {
      sendInFlightRef.current = false;
      setIsSendInFlight(false);
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(MODEL_MODE_STORAGE_KEY, modelMode);
  }, [modelMode]);

  const {
    plan,
    isPlanLoading,
    profileUsage,
    quotaModal,
    setQuotaModal,
    fetchPlanAndUsage,
    openQuotaExceededModal,
    applyQuotaCheckResult,
    syncAfterMessage,
  } = useChatQuota({ m, isEn });

  useEffect(() => {
    if (isPlanLoading) return;
    setModelMode((currentMode) => resolveModelModeForPlan(currentMode, plan?.name));
  }, [isPlanLoading, plan?.name]);

  const {
    activeConversationId,
    setActiveConversationId,
    branches,
    activeBranchId,
    setActiveBranchId,
    pinnedConvIds,
    deleteModal,
    setDeleteConfirm,
    sortedConversations,
    fetchConversations,
    registerConversation,
    hasMoreConversations,
    loadingMoreConversations,
    loadMoreConversations,
    togglePinConversation,
    renameConversation,
    loadConversation,
    switchConversationBranch,
    forkConversationBranch,
    startNewChat,
    triggerDeleteConversation,
    confirmDeleteConversation,
  } = useChatConversations({
    userId: user?.id,
    dataCache: fileManagerCache,
    isEn,
    setAiError,
    stopGeneration: stopActiveGeneration,
    setMessages,
    setSelectedFile,
    setInput,
    setConfirmedMapping,
    setFileColumnMappings,
    setSessionFileContext,
    setAgentSession,
    onWorkspaceReset: () => workspaceResetRef.current(),
  });

  const allConnections = useCallback(() => {
    return [
      ...dbConnections.map((c) => ({ ...c, type: 'sql' })),
      ...apiConnections.map((c) => ({ ...c, type: 'api' })),
    ];
  }, [dbConnections, apiConnections]);

  const persistActiveConnection = useCallback((conn, conversationId = activeConversationId) => {
    const nextConnection = conn && activeConnection?.id === conn.id
      ? {
          ...activeConnection,
          ...conn,
          mapping: conn.mapping ?? activeConnection.mapping,
          cleaningRecipe: conn.cleaningRecipe ?? activeConnection.cleaningRecipe,
          cleaningProfile: conn.cleaningProfile ?? activeConnection.cleaningProfile,
        }
      : conn;
    setActiveConnection((prev) => (
      sameConnection(prev, nextConnection) ? prev : nextConnection
    ));
    if (!user?.id) return;
    if (nextConnection) {
      saveChatSession(user.id, {
        connection: {
          id: nextConnection.id,
          name: nextConnection.name,
          type: nextConnection.type,
          sqlTable: nextConnection.sqlTable || null,
          mapping: nextConnection.mapping || null,
          cleaningRecipe: nextConnection.cleaningRecipe || null,
          cleaningProfile: nextConnection.cleaningProfile || null,
        },
        conversationId: conversationId || null,
      });
    } else {
      clearChatSessionConnection(user.id);
    }
  }, [user, activeConversationId, activeConnection]);

  const restoreConnectionContext = useCallback((messages = [], conversationId = activeConversationId) => {
    const conns = allConnections();
    if (!conns.length) return;

    const fromMessages = connectionFromMessages(messages, conns);
    if (fromMessages) {
      persistActiveConnection(fromMessages, conversationId);
      if (fromMessages.mapping) setConfirmedMapping(fromMessages.mapping);
      if (fromMessages.cleaningRecipe) setCleaningRecipe(fromMessages.cleaningRecipe);
      if (fromMessages.cleaningProfile) setCleaningProfile(fromMessages.cleaningProfile);
      return;
    }

    if (!user?.id) return;
    const saved = loadChatSession(user.id);
    if (!saved?.connection) return;
    if (saved.conversationId && conversationId && saved.conversationId !== conversationId) return;

    const resolved = resolveStoredConnection(saved.connection, conns);
    if (resolved) {
      setActiveConnection((prev) => (sameConnection(prev, resolved) ? prev : resolved));
      if (resolved.mapping) setConfirmedMapping(resolved.mapping);
      if (resolved.cleaningRecipe) setCleaningRecipe(resolved.cleaningRecipe);
      if (resolved.cleaningProfile) setCleaningProfile(resolved.cleaningProfile);
    }
  }, [allConnections, persistActiveConnection, user, activeConversationId]);

  const applyStoredFile = useCallback((file) => {
    if (!file?.name) return;
    if (file.mode === 'pending') {
      setSelectedFile((prev) => (prev?.name === file.name ? prev : { name: file.name }));
      setSessionFileContext((prev) => (prev === null ? prev : null));
    } else {
      const nextContext = {
        name: file.name,
        mapping: file.mapping || undefined,
        cleaningRecipe: file.cleaningRecipe || undefined,
        cleaningProfile: file.cleaningProfile || undefined,
      };
      setSelectedFile((prev) => (prev === null ? prev : null));
      setSessionFileContext((prev) => (sameSessionFile(prev, nextContext) ? prev : nextContext));
    }
    if (file.mapping) {
      setFileColumnMappings((prev) => {
        if (sameMapping(prev[file.name], file.mapping)) return prev;
        return { ...prev, [file.name]: file.mapping };
      });
      setConfirmedMapping((prev) => (sameMapping(prev, file.mapping) ? prev : file.mapping));
    }
    if (file.cleaningRecipe) setCleaningRecipe(file.cleaningRecipe);
    if (file.cleaningProfile) setCleaningProfile(file.cleaningProfile);
  }, []);

  const restoreFileContext = useCallback((msgs = [], conversationId = activeConversationId) => {
    const fromMessages = fileFromMessages(msgs);
    if (fromMessages) {
      if (!user?.id) {
        applyStoredFile(fromMessages);
        return;
      }
      const saved = loadChatSession(user.id);
      if (saved?.file?.name === fromMessages.name && saved.file.mapping) {
        applyStoredFile({ ...fromMessages, mapping: saved.file.mapping });
      } else {
        applyStoredFile(fromMessages);
      }
      return;
    }

    if (!user?.id) return;
    const saved = loadChatSession(user.id);
    if (!saved?.file) return;
    if (saved.conversationId && conversationId && saved.conversationId !== conversationId) return;
    if (!conversationId && saved.conversationId) return;

    const resolved = resolveStoredFile(saved.file);
    if (resolved) applyStoredFile(resolved);
  }, [user, activeConversationId, applyStoredFile]);

  const restoreSessionContext = useCallback((msgs = [], conversationId = activeConversationId) => {
    restoreConnectionContext(msgs, conversationId);
    restoreFileContext(msgs, conversationId);
  }, [activeConversationId, restoreConnectionContext, restoreFileContext]);

  useEffect(() => {
    if (!isPanel || !panelPreset) return;
    setInput(String(panelPreset));
  }, [isPanel, panelPreset]);

  useEffect(() => {
    if (!isPanel || !visualizationContext?.sourceConfig) return;
    const source = visualizationContext.sourceConfig;
    if (source.type === 'file' && source.file_name) {
      setSelectedFile(null);
      setSessionFileContext({
        name: source.file_name,
        mapping: source.column_mapping || undefined,
        cleaningRecipe: source.cleaning_recipe || undefined,
        cleaningProfile: source.cleaning_profile || 'standard',
      });
      if (source.column_mapping) setConfirmedMapping(source.column_mapping);
      if (source.cleaning_recipe) setCleaningRecipe(source.cleaning_recipe);
      if (source.cleaning_profile) setCleaningProfile(source.cleaning_profile);
      return;
    }
    if (source.connection_id && ['api', 'sql'].includes(source.type)) {
      const connection = allConnections().find((item) => item.id === source.connection_id);
      if (connection) {
        persistActiveConnection({
          ...connection,
          sqlTable: source.sql_table || connection.sqlTable,
          mapping: source.column_mapping || connection.mapping,
          cleaningRecipe: source.cleaning_recipe || connection.cleaningRecipe,
          cleaningProfile: source.cleaning_profile || connection.cleaningProfile,
        }, embeddedConversationId || activeConversationId);
      }
    }
  }, [
    activeConversationId,
    allConnections,
    apiConnections.length,
    dbConnections.length,
    embeddedConversationId,
    isPanel,
    persistActiveConnection,
    visualizationContext?.reportId,
    visualizationContext?.sourceConfig,
  ]);

  const resolveColumnMapping = useCallback((mappingOverride, fileName) => {
    if (mappingOverride && countMappedColumns(mappingOverride) > 0) return mappingOverride;
    if (fileName && fileColumnMappings[fileName]) return fileColumnMappings[fileName];
    if (confirmedMapping && countMappedColumns(confirmedMapping) > 0) return confirmedMapping;
    if (sessionFileContext?.name === fileName && sessionFileContext.mapping) {
      return sessionFileContext.mapping;
    }
    return null;
  }, [fileColumnMappings, confirmedMapping, sessionFileContext]);

  const parseSampleData = useCallback(
    async (fileInfo, options = {}) => {
      const name = typeof fileInfo?.name === 'string' ? fileInfo.name.trim() : '';
      if (!name) throw new Error('Invalid file name');
      return parseFileSample(supabase, user.id, name, options);
    },
    [user],
  );

  const requestConnectionMapping = useCallback(async (connection) => {
    if (!connection?.id || connection.type !== 'api' || !user?.id) return false;
    setIsGenerating(true);
    try {
      const response = await authFetch(
        `${getPublicApiUrl()}/api/v1/api-connections/mapping-preview`,
        {
          body: {
            connection_id: connection.id,
            user_id: user.id,
            max_rows: 20,
          },
        },
      );
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || 'Could not load API preview');
      }
      const payload = await response.json();
      if (!Array.isArray(payload.rows) || payload.rows.length === 0) {
        throw new Error('API returned no tabular rows');
      }
      setParsedDataForMapping(payload.rows);
      setJsonPathOptions([]);
      setSelectedJsonPath(null);
      setMappingTarget({ type: 'connection', connection });
      setShowMappingModal(true);
      return true;
    } catch (error: any) {
      console.error('API mapping preview error:', error);
      setAiError(
        isEn
          ? `Could not prepare API mapping: ${error.message}`
          : `เตรียมข้อมูล API สำหรับจับคู่คอลัมน์ไม่สำเร็จ: ${error.message}`,
      );
      return false;
    } finally {
      setIsGenerating(false);
    }
  }, [user, isEn]);

  const handleDataSetupReadyRef = useRef(null);

  const conversationalSetupActive = Boolean(
    conversationalSetupEnabled
    && dataSetupSession
    && !['ready', 'failed', 'cancelled'].includes(dataSetupSession.status),
  );

  const {
    currentOrchestration,
    reconcileSetup,
    applyStreamOrchestration,
    resetPollTracking,
    setCurrentOrchestration,
  } = useSetupReconciliation({
    authFetch,
    getPublicApiUrl,
    enabled: conversationalSetupActive,
    session: dataSetupSession,
    conversationId: activeConversationId || routeConversationId || null,
  });

  const resetDataSetupWorkspace = useCallback(() => {
    setDataSetupSession(null);
    conversationalKickoffRef.current = null;
    resetPollTracking();
    setCurrentOrchestration(createEmptyCurrentOrchestrationState());
  }, [resetPollTracking, setCurrentOrchestration]);

  useEffect(() => {
    workspaceResetRef.current = resetDataSetupWorkspace;
  }, [resetDataSetupWorkspace]);

  // Drop setup UI that belongs to another conversation or a deleted chat on /chat/new.
  useEffect(() => {
    if (!dataSetupSession?.id) return;
    const convId = activeConversationId || routeConversationId;
    const setupConvId = dataSetupSession.conversation_id;
    if (isNewChatRoute && !isUuid(convId) && setupConvId) {
      resetDataSetupWorkspace();
      return;
    }
    if (isUuid(convId) && setupConvId && setupConvId !== convId) {
      resetDataSetupWorkspace();
    }
  }, [
    activeConversationId,
    dataSetupSession,
    isNewChatRoute,
    resetDataSetupWorkspace,
    routeConversationId,
  ]);

  const handleOrchestrationUpdate = useCallback((orchestration) => {
    applyStreamOrchestrationUpdate({
      orchestration,
      applyStreamOrchestration,
      reconcileSetup,
      session: dataSetupSession,
      resolveSessionId: (payload, session) => (
        session?.id
        || payload?.session_id
        || payload?.workflow?.session_id
        || payload?.workflow?.sessionId
        || null
      ),
    });
  }, [
    applyStreamOrchestration,
    dataSetupSession,
    reconcileSetup,
  ]);

  const handleOrchestrationReady = useCallback(async (orchestration) => {
    handleOrchestrationUpdate(orchestration);
    const sessionId = dataSetupSession?.id
      || orchestration?.workflow?.session_id
      || orchestration?.workflow?.sessionId;
    if (!sessionId || !user?.id) return;
    try {
      const response = await authFetch(
        `${getPublicApiUrl()}/api/v1/data-setup/${sessionId}`,
      );
      const payload = await response.json().catch(() => ({}));
      const session = payload.session || payload;
      if (!response.ok || !session?.id) return;
      setDataSetupSession(session);
      if (session.status === 'ready') {
        handleDataSetupReadyRef.current?.(session, session.cleaning_recipe);
      }
    } catch (err) {
      console.warn('Could not refresh ready data-setup session', err);
    }
  }, [dataSetupSession?.id, handleOrchestrationUpdate, user?.id]);

  const {
    sendMessage: handleSend,
    stopGeneration: handleStopGeneration,
    retryFailedMessage: handleRetryFailedMessage,
    abortControllerRef,
  } = useChatSend({
    m,
    routing,
    navigate,
    onConversationCreated: async (convId) => {
      if (isPanel) {
        await onEmbeddedConversationCreated?.(convId);
        return;
      }
      promotedConversationIdRef.current = convId;
      promoteConversationUrl(buildChatPath(routing, { conversationId: convId }));
    },
    user,
    plan,
    profileUsage,
    input,
    selectedFile,
    sessionFileContext,
    messages,
    activeConversationId,
    setActiveConversationId,
    activeBranchId,
    setActiveBranchId,
    activeConnection,
    setActiveConnection: persistActiveConnection,
    dbConnections,
    apiConnections,
    agentSession,
    setAgentSession,
    fileColumnMappings,
    setFileColumnMappings,
    setConfirmedMapping,
    setSessionFileContext,
    resolveColumnMapping,
    parseSampleData,
    requestConnectionMapping,
    setParsedDataForMapping,
    setJsonPathOptions,
    setSelectedJsonPath,
    setShowMappingModal,
    setMappingTarget,
    openQuotaExceededModal,
    applyQuotaCheckResult,
    syncAfterMessage,
    registerConversation,
    setAiError,
    setInput,
    setSelectedFile,
    setMessages,
    setIsTyping,
    setIsGenerating,
    setStopTyping,
    setIsAnalysisQuery,
    setAnalysisStreamStarted,
    setAnalysisContext,
    setReasoningProgress,
    cleaningProfile,
    cleaningRecipe,
    selectedJsonPath,
    modelMode,
    dataSetupSessionId: dataSetupSession?.id || null,
    onOrchestrationReady: handleOrchestrationReady,
    onOrchestrationUpdate: handleOrchestrationUpdate,
    visualizationContext,
  });

  useEffect(() => {
    stopGenerationRef.current = handleStopGeneration;
  }, [handleStopGeneration]);

  useEffect(() => {
    onGenerationChange?.(isGenerating || isSendInFlight);
  }, [isGenerating, isSendInFlight, onGenerationChange]);

  useEffect(() => () => {
    onGenerationChange?.(false);
  }, [onGenerationChange]);

  useEffect(() => {
    if (!isGenerating) return undefined;
    const timer = window.setTimeout(() => {
      recoverStaleChatTurn({
        isGenerating,
        hasActiveStream: Boolean(abortControllerRef?.current),
        isSendInFlight,
        finishTurn: () => finishChatTurn({
          setIsGenerating,
          setIsTyping,
          setAnalysisStreamStarted,
          abortControllerRef,
        }),
      });
    }, 500);
    return () => window.clearTimeout(timer);
  }, [
    abortControllerRef,
    isGenerating,
    isSendInFlight,
    setAnalysisStreamStarted,
    setIsGenerating,
    setIsTyping,
  ]);

  const sourceNeedsDataSetup = useCallback(() => {
    if (agentSession) return false;
    if (selectedFile?.name) {
      const recipe = sessionFileContext?.name === selectedFile.name
        ? sessionFileContext.cleaningRecipe
        : selectedFile.cleaningRecipe;
      return !recipe?.data_contract?.business_context_reviewed;
    }
    if (activeConnection?.id) {
      return !activeConnection.cleaningRecipe?.data_contract?.business_context_reviewed;
    }
    return false;
  }, [activeConnection, agentSession, selectedFile, sessionFileContext]);

  const ensureConversationalCapability = useCallback(async () => {
    if (!capabilitiesPromiseRef.current) {
      capabilitiesPromiseRef.current = (async () => {
        try {
          const response = await authFetch(`${getPublicApiUrl()}/api/v1/capabilities`);
          if (!response.ok) {
            return conversationalFlagRef.current;
          }
          const payload = await response.json().catch(() => ({}));
          if (typeof payload.conversational_data_setup === 'boolean') {
            conversationalFlagRef.current = payload.conversational_data_setup;
            return payload.conversational_data_setup;
          }
        } catch {
          // Keep local NEXT_PUBLIC hint / default false.
        }
        return conversationalFlagRef.current;
      })();
    }
    const enabled = await capabilitiesPromiseRef.current;
    conversationalFlagRef.current = enabled;
    return enabled;
  }, []);

  const startDataSetup = useCallback(async () => {
    if (!user?.id) return null;
    const conversational = await ensureConversationalCapability();
    if (!conversational) {
      setAiError(
        isEn
          ? 'Guided data setup is unavailable. Enable conversational data setup on the backend.'
          : 'ระบบตั้งค่าข้อมูลแบบสนทนายังไม่พร้อมใช้งาน กรุณาเปิดใช้งานที่ Backend',
      );
      return null;
    }
    if (dataSetupSession && !['ready', 'failed', 'cancelled'].includes(dataSetupSession.status)) {
      return {
        session: dataSetupSession,
        prompt: input.trim(),
        workflow: currentOrchestration.workflowPlan,
        source: currentOrchestration.source,
      };
    }
    const sourceType = selectedFile?.name ? 'file' : activeConnection?.type;
    if (!sourceType || !['file', 'api', 'sql', 'cloud'].includes(sourceType)) return null;
    if (sourceType === 'sql' && !activeConnection?.sqlTable) {
      setAiError(isEn ? 'Select a database table first.' : 'กรุณาเลือกตาราง Database ก่อน');
      return null;
    }
    setIsGenerating(true);
    setAiError(null);
    try {
      // Quick Scan is server-side so large files are not downloaded into the
      // browser merely to inspect a bounded schema/sample.
      const sampleRows = [];
      const prompt = input.trim();
      const scanBody = {
        user_id: user.id,
        source_type: sourceType,
        file_name: sourceType === 'file' ? selectedFile.name : null,
        connection_id: sourceType !== 'file' ? activeConnection.id : null,
        table_name: sourceType === 'sql' ? activeConnection.sqlTable : null,
        conversation_id: isUuid(activeConversationId || routeConversationId)
          ? (activeConversationId || routeConversationId)
          : null,
        original_prompt: prompt,
        sample_rows: sampleRows.slice(0, 200),
        row_count_estimate: selectedFile?.row_count ?? null,
        row_count_exact: Boolean(selectedFile?.row_count),
        reuse_existing: false,
      };
      let response = await authFetch(`${getPublicApiUrl()}/api/v1/data-setup/scan`, {
        body: scanBody,
      });
      let result = await response.json().catch(() => ({}));
      if (response.status === 409 && result?.resumable && result?.existing_session_id) {
        response = await authFetch(`${getPublicApiUrl()}/api/v1/data-setup/scan`, {
          body: { ...scanBody, reuse_existing: true },
        });
        result = await response.json().catch(() => ({}));
      }
      // Storage load can fail even when the file chip is visible — retry once with
      // a bounded browser sample so setup can still start.
      if (
        !response.ok
        && sourceType === 'file'
        && selectedFile?.name
        && !(Array.isArray(scanBody.sample_rows) && scanBody.sample_rows.length)
      ) {
        try {
          const sample = await parseSampleData(selectedFile, {});
          const rows = Array.isArray(sample) ? sample : sample?.rows;
          if (Array.isArray(rows) && rows.length) {
            response = await authFetch(`${getPublicApiUrl()}/api/v1/data-setup/scan`, {
              body: {
                ...scanBody,
                sample_rows: rows.slice(0, 200),
                row_count_estimate: selectedFile?.row_count ?? rows.length,
              },
            });
            result = await response.json().catch(() => ({}));
          }
        } catch {
          // Keep the original scan failure below.
        }
      }
      if (!response.ok) {
        const detail = formatApiErrorDetail(result, '');
        if (result?.code === 'ACTIVE_SETUP_EXISTS' && result?.resumable) {
          throw new Error(
            isEn
              ? 'Found an in-progress setup for this source — continuing it.'
              : 'พบการเตรียมข้อมูลที่ยังไม่เสร็จ — กำลังทำต่อ',
          );
        }
        throw new Error(
          detail
          || (isEn
            ? `Quick Scan failed (HTTP ${response.status})`
            : `Quick Scan ไม่สำเร็จ (HTTP ${response.status})`),
        );
      }
      setDataSetupSession(result.session);
      return {
        session: result.session,
        prompt,
        workflow: result.workflow || null,
        source: result.source || null,
      };
    } catch (error: any) {
      setAiError(
        isEn
          ? `Could not start Data Setup: ${error.message}`
          : `เริ่ม Data Setup ไม่สำเร็จ: ${error.message}`,
      );
      return null;
    } finally {
      setIsGenerating(false);
    }
  }, [
    activeConnection, activeConversationId, currentOrchestration.source,
    currentOrchestration.workflowPlan, dataSetupSession, ensureConversationalCapability,
    input, isEn, parseSampleData, routeConversationId, selectedFile, user,
  ]);

  const kickConversationalSetup = useCallback(async ({
    sessionId,
    prompt = '',
    requestId = null,
  }) => {
    if (!sessionId) return;
    const kickKey = `${sessionId}:${prompt || 'prepare_attached_source_for_analysis'}`;
    if (conversationalKickoffRef.current === kickKey) return;
    conversationalKickoffRef.current = kickKey;
    const trimmed = String(prompt || '').trim();
    if (trimmed) {
      await handleSend(null, null, null, {
        contentOverride: trimmed,
        setupIntent: 'prepare_attached_source_for_analysis',
        dataSetupSessionId: sessionId,
        conversationalSetup: true,
        ...(requestId ? { requestId } : {}),
      });
      return;
    }
    await handleSend(null, null, null, {
      setupIntent: 'prepare_attached_source_for_analysis',
      dataSetupSessionId: sessionId,
      conversationalSetup: true,
      ...(requestId ? { requestId } : {}),
    });
  }, [handleSend]);

  const handleAdaptiveSend = useCallback(async (event) => {
    event?.preventDefault?.();
    const content = input.trim();
    await withSendGuard(async () => {
      const conversational = await ensureConversationalCapability();
      const activeSetup = dataSetupSession
        && !['ready', 'failed', 'cancelled'].includes(dataSetupSession.status);

      // Conversational setup: chat remains the primary path once a session exists.
      if (conversational && activeSetup) {
        if (!content && (selectedFile?.name || activeConnection?.id || sessionFileContext?.name)) {
          await kickConversationalSetup({ sessionId: dataSetupSession.id, prompt: '' });
          return;
        }
        await handleSend(event, null, null, {
          dataSetupSessionId: dataSetupSession.id,
          conversationalSetup: true,
        });
        return;
      }

      if (sourceNeedsDataSetup()) {
        const started = await startDataSetup();
        if (conversational && started?.session?.id) {
          setInput('');
          await kickConversationalSetup({
            sessionId: started.session.id,
            prompt: started.prompt || content,
          });
        }
        return;
      }
      if (!content && (selectedFile?.name || activeConnection?.id || sessionFileContext?.name)) {
        await handleSend(null, null, null, {
          contentOverride: isEn
            ? 'Analyze this dataset and summarize the most important findings.'
            : 'วิเคราะห์ข้อมูลชุดนี้และสรุปประเด็นสำคัญที่สุด',
        });
        return;
      }
      await handleSend(event);
    });
  }, [
    activeConnection?.id, dataSetupSession, ensureConversationalCapability,
    handleSend, input, isEn, kickConversationalSetup, selectedFile?.name,
    sessionFileContext?.name, sourceNeedsDataSetup, startDataSetup,
    withSendGuard,
  ]);

  const handleOrchestrationResolve = useCallback(async (sendOptions) => {
    if (!sendOptions) return;
    await withSendGuard(async () => {
      await handleSend(null, null, null, {
        ...sendOptions,
        dataSetupSessionId: dataSetupSession?.id || sendOptions.dataSetupSessionId,
      });
    });
  }, [dataSetupSession?.id, handleSend, withSendGuard]);

  const handleSuggestedQuestion = useCallback(async (prompt) => {
    const content = String(prompt || '').trim();
    if (!content) return;
    await withSendGuard(async () => {
      await handleSend(null, null, null, { contentOverride: content });
    });
  }, [handleSend, withSendGuard]);

  const handleDataSetupReady = useCallback((readySession, recipe) => {
    if (!readySession?.output_file) return;
    const mapping = readySession.column_mapping || recipe?.column_mapping || {};
    const analysisRecipe = {
      ...(readySession.cleaning_recipe || recipe || {}),
      materialized_prepared: true,
      data_setup_session_id: readySession.id,
      dataset_version_id: readySession.dataset_version_id || readySession.output_dataset_key || readySession.id,
      source_fingerprint: readySession.source_fingerprint || null,
      contract_hash: readySession.contract_hash || null,
      recipe_hash: readySession.recipe_hash || null,
    };
    const nextContext = {
      name: readySession.output_file,
      mapping,
      cleaningRecipe: analysisRecipe,
      cleaningProfile: readySession.cleaning_profile || 'standard',
      dataSetupSessionId: readySession.id,
    };
    setSelectedFile(null);
    persistActiveConnection(null);
    setSessionFileContext(nextContext);
    setConfirmedMapping(mapping);
    setCleaningRecipe(analysisRecipe);
    setCleaningProfile(nextContext.cleaningProfile);
    setFileColumnMappings((previous) => ({ ...previous, [nextContext.name]: mapping }));
    setDataSetupSession(null);
    conversationalKickoffRef.current = null;
    if (user?.id) {
      saveChatSession(user.id, {
        file: nextContext,
        conversationId: activeConversationId || routeConversationId || null,
      });
    }
    const originalPrompt = String(readySession.original_prompt || '').trim();
    const setupish = /สร้างข้อมูล|เตรียมข้อมูล|เตรียมแหล่ง|setup|upload|แนบไฟล์|map column/i
      .test(originalPrompt);
    const kickoff = (!setupish && originalPrompt)
      ? originalPrompt
      : (isEn
        ? 'Analyze this dataset. Summarize key insights with the main numbers.'
        : 'วิเคราะห์ข้อมูลชุดนี้ให้หน่อย สรุป insight สำคัญพร้อมตัวเลขหลัก');
    setInput(kickoff);
    const sessionId = String(readySession.id || '');
    if (sessionId && analysisKickoffRef.current !== sessionId) {
      analysisKickoffRef.current = sessionId;
      window.setTimeout(() => {
        void withSendGuard(async () => {
          await handleSend(null, null, null, { contentOverride: kickoff });
        });
      }, 120);
    } else {
      window.setTimeout(() => textareaRef.current?.focus(), 0);
    }
  }, [
    activeConversationId,
    handleSend,
    isEn,
    persistActiveConnection,
    routeConversationId,
    user,
    withSendGuard,
  ]);

  useEffect(() => {
    handleDataSetupReadyRef.current = handleDataSetupReady;
  }, [handleDataSetupReady]);

  useEffect(() => {
    let cancelled = false;
    ensureConversationalCapability().then((enabled) => {
      if (cancelled) return;
      setConversationalSetupEnabled(enabled);
      conversationalFlagRef.current = enabled;
      setCapabilitiesReady(true);
    });
    return () => { cancelled = true; };
  }, [ensureConversationalCapability]);

  const handleContinueWorkflow = useCallback(async () => {
    if (!dataSetupSession?.id) return;
    await withSendGuard(async () => {
      await handleSend(null, null, null, {
        setupIntent: 'continue_workflow',
        dataSetupSessionId: dataSetupSession.id,
        conversationalSetup: true,
      });
    });
  }, [dataSetupSession, handleSend, withSendGuard]);

  // Resume in-progress setup after refresh only — never on draft file attach.
  useEffect(() => {
    if (!capabilitiesReady || !conversationalSetupEnabled || !user?.id) return;
    if (dataSetupSession?.id) return;
    const setupSessionId = sessionFileContext?.dataSetupSessionId;
    const convId = activeConversationId || routeConversationId;
    const hasConversation = isUuid(convId);
    let cancelled = false;
    (async () => {
      try {
        if (setupSessionId) {
          const response = await authFetch(
            `${getPublicApiUrl()}/api/v1/data-setup/${setupSessionId}`,
          );
          if (!response.ok || cancelled) return;
          const payload = await response.json().catch(() => ({}));
          const session = payload.session || payload;
          if (!session?.id || ['ready', 'failed', 'cancelled'].includes(session.status)) return;
          if (session.conversation_id && hasConversation && session.conversation_id !== convId) return;
          if (session.conversation_id && isNewChatRoute && !hasConversation) return;
          setDataSetupSession(session);
          return;
        }
        // Fresh /chat/new must not resurrect orphan setup by file name alone.
        if (!hasConversation) return;
        if (!sessionFileContext?.name || sessionFileContext?.mode === 'pending') return;
        if (selectedFile?.name) return;
        const sourceType = sessionFileContext.name ? 'file' : null;
        if (!sourceType) return;
        const params = new URLSearchParams({ source_type: sourceType, file_name: sessionFileContext.name });
        params.set('conversation_id', convId);
        const response = await authFetch(
          `${getPublicApiUrl()}/api/v1/data-setup/resume?${params.toString()}`,
        );
        if (!response.ok || cancelled) return;
        const payload = await response.json().catch(() => ({}));
        const session = payload.session;
        if (!session?.id || cancelled) return;
        if (['ready', 'failed', 'cancelled'].includes(session.status)) return;
        if (session.conversation_id && session.conversation_id !== convId) return;
        setDataSetupSession(session);
      } catch {
        // No resumable session is fine.
      }
    })();
    return () => { cancelled = true; };
  }, [
    activeConversationId, capabilitiesReady, conversationalSetupEnabled,
    dataSetupSession?.id, isNewChatRoute, routeConversationId, selectedFile?.name,
    sessionFileContext, user?.id,
  ]);

  const handleCommitToBottom = useCallback((chartId, data, chartTypes) => {
    setBottomCharts(prev => {
      const filtered = prev.filter(c => c.id !== chartId);
      return [...filtered, { id: chartId, data, types: chartTypes }];
    });
  }, []);

  // ดึงข้อมูลกราฟที่พ่นมาล่าสุดจาก AI เพื่อให้ปุ่มขึ้นข้างปุ่มสร้างคำตอบใหม่
  const getLatestChartData = useCallback(() => {
    for (const msg of [...messages].reverse()) {
      if (msg.role !== 'ai' || !msg.content) continue;
      const commands = extractSystemCommands(msg.content);
      if (commands.some((command) => command.action === 'propose_visualization')) {
        return null;
      }
      const chart = commands.find((command) => command.action === 'render_chart');
      if (chart) return chart;
    }
    return null;
  }, [messages]);

  const latestChartData = getLatestChartData();

  const modalSelectedTypes =
    showChartModal && latestChartData?.chart_type && selectedTypes.length === 0
      ? [latestChartData.chart_type]
      : selectedTypes;

  const toggleType = (type) => {
    setSelectedTypes(prev => {
      if (prev.includes(type)) {
        if (prev.length === 1) return prev;
        return prev.filter(t => t !== type);
      } else {
        return [...prev, type];
      }
    });
  };

  const handleConfirmCharts = () => {
    setShowChartModal(false);
    if (latestChartData) {
      const chartId = latestChartData.config?.title || JSON.stringify(latestChartData.data?.[0]) || Math.random().toString();
      handleCommitToBottom(chartId, latestChartData, modalSelectedTypes);
    }
  };

  // ฟังก์ชันตัดชื่อไฟล์เพื่อเอา Timestamp ด้านหน้าออกในการแสดงผล
  const getDisplayName = (fileName) =>
    fileName ? (fileName.split('_').slice(1).join(' ') || fileName) : "";

  const clearSessionFileContext = useCallback(() => {
    setSessionFileContext(null);
    if (!selectedFile) {
      setConfirmedMapping(null);
    }
    if (user?.id) clearChatSessionFile(user.id);
  }, [selectedFile, user]);

  const clearAttachedFile = useCallback(() => {
    setSelectedFile(null);
    if (user?.id) clearChatSessionFile(user.id);
  }, [user]);

  useEffect(() => {
    localStorage.setItem(SIDEBAR_OPEN_STORAGE_KEY, String(isSidebarOpen));
  }, [isSidebarOpen]);

  // 3. ปรับความสูงกล่องข้อความอัตโนมัติ (Auto-resize Textarea)
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [input]);

  const handleLoadConversation = useCallback(
    (convId) => {
      promotedConversationIdRef.current = null;
      navigate(buildChatPath(routing, { conversationId: convId }));
    },
    [navigate, routing],
  );

  const handleStartNewChat = useCallback(() => {
    promotedConversationIdRef.current = null;
    urlHydratedRef.current = false;
    if (user?.id) clearChatSession(user.id);
    startNewChat();
    persistActiveConnection(null);
    navigate(buildChatPath(routing, {}));
  }, [navigate, routing, startNewChat, persistActiveConnection, user]);

  const handleConfirmDeleteConversation = useCallback(async () => {
    const deletingId = deleteModal.convId;
    const deletingActiveConversation = deletingId && deletingId === activeConversationId;
    await confirmDeleteConversation();
    if (deletingActiveConversation || (deletingId && routeConversationId === deletingId)) {
      if (user?.id) clearChatSession(user.id);
      replaceBrowserUrl(buildChatPath(routing, {}));
    }
  }, [activeConversationId, confirmDeleteConversation, deleteModal.convId, replaceBrowserUrl, routeConversationId, routing, user]);

  useEffect(() => {
    if (!user) return;

    if (routeConversationId && isUuid(routeConversationId)) {
      if (promotedConversationIdRef.current === routeConversationId) {
        promotedConversationIdRef.current = null;
      }
      if (routeConversationId !== activeConversationId) {
        persistActiveConnection(null, routeConversationId);
        loadConversation(routeConversationId, (loadedMessages) => {
          restoreSessionContext(loadedMessages, routeConversationId);
        });
      } else {
        restoreSessionContext(messages, routeConversationId);
      }
      return;
    }

    if (routeConversationId && !isUuid(routeConversationId)) {
      replaceBrowserUrl(buildChatPath(routing, {}));
      return;
    }

    if (isNewChatRoute) {
      if (shouldResetConversationOnNewRoute(
        activeConversationId,
        promotedConversationIdRef.current,
      )) {
        startNewChat();
        persistActiveConnection(null);
      }
      if (!urlHydratedRef.current) {
        const preset = searchParams.get('q');
        const fileParam = searchParams.get('file');
        const cloudId = searchParams.get('cloud');
        const cloudName = searchParams.get('cloudName');
        if (preset) setInput(preset);
        if (fileParam) setSelectedFile({ name: fileParam });
        if (cloudId) {
          persistActiveConnection({
            id: cloudId,
            name: cloudName || (isEn ? 'Cloud dataset' : 'ข้อมูล Cloud'),
            type: 'cloud',
          });
        }
        urlHydratedRef.current = true;
      }
    }
  }, [
    user,
    routeConversationId,
    isNewChatRoute,
    activeConversationId,
    loadConversation,
    startNewChat,
    persistActiveConnection,
    replaceBrowserUrl,
    routing,
    searchParams,
    isEn,
    messages,
    restoreSessionContext,
  ]);

  useEffect(() => {
    if (!user?.id || dbConnections.length + apiConnections.length === 0) return;
    if (activeConnection) return;
    restoreConnectionContext(messages, activeConversationId || routeConversationId);
  }, [
    user,
    dbConnections,
    apiConnections,
    activeConnection,
    messages,
    activeConversationId,
    routeConversationId,
    restoreConnectionContext,
  ]);

  useEffect(() => {
    if (!user?.id) return;
    if (selectedFile || sessionFileContext) return;
    restoreFileContext(messages, activeConversationId || routeConversationId);
  }, [
    user,
    selectedFile,
    sessionFileContext,
    messages,
    activeConversationId,
    routeConversationId,
    restoreFileContext,
  ]);

  useEffect(() => {
    if (!user?.id) return;
    const convId = activeConversationId || routeConversationId || null;

    if (sessionFileContext?.name) {
      saveChatSession(user.id, {
        file: {
          name: sessionFileContext.name,
          mapping: sessionFileContext.mapping || null,
          cleaningRecipe: sessionFileContext.cleaningRecipe || null,
          cleaningProfile: sessionFileContext.cleaningProfile || null,
          dataSetupSessionId: sessionFileContext.dataSetupSessionId || null,
          mode: 'session',
        },
        conversationId: convId,
      });
      return;
    }

    if (selectedFile?.name) {
      saveChatSession(user.id, {
        file: {
          name: selectedFile.name,
          mapping: fileColumnMappings[selectedFile.name] || confirmedMapping || null,
          cleaningRecipe: cleaningRecipe || null,
          cleaningProfile,
          mode: 'pending',
        },
        conversationId: convId,
      });
    }
  }, [
    user,
    selectedFile,
    sessionFileContext,
    fileColumnMappings,
    confirmedMapping,
    cleaningRecipe,
    cleaningProfile,
    activeConversationId,
    routeConversationId,
  ]);

  useEffect(() => {
    const conversationId = activeConversationId || routeConversationId;
    if (!user?.id || !conversationId || messages.length === 0) return;
    saveConversationSnapshot(user.id, conversationId, messages, activeBranchId);
  }, [user, activeConversationId, routeConversationId, activeBranchId, messages]);

  useEffect(() => {
    if (!user?.id || !activeConnection) return;
    saveChatSession(user.id, {
      connection: {
        id: activeConnection.id,
        name: activeConnection.name,
        type: activeConnection.type,
        sqlTable: activeConnection.sqlTable || null,
        mapping: activeConnection.mapping || null,
        cleaningRecipe: activeConnection.cleaningRecipe || null,
        cleaningProfile: activeConnection.cleaningProfile || null,
      },
      conversationId: activeConversationId || routeConversationId || null,
    });
  }, [user, activeConnection, activeConversationId, routeConversationId]);

  useEffect(() => {
    const conversationId = activeConversationId || routeConversationId;
    if (!user?.id || !conversationId) return undefined;
    const channelName = `scheduled-chat-messages-${user.id}-${conversationId}`;
    const channel = supabase
      .channel(channelName)
      .on('postgres_changes', {
        event: 'INSERT',
        schema: 'public',
        table: 'chat_messages',
        filter: `conversation_id=eq.${conversationId}`,
      }, (event) => {
        const row = event.new;
        if (
          row?.user_id !== user.id
          || row?.response_metadata?.message_type !== 'scheduled_analysis'
        ) return;
        const incoming = {
          ...sanitizeChatMessage(row),
          role: 'ai',
          skipAnimate: true,
        };
        setMessages((current) => (
          current.some((message) => message.id === incoming.id)
            ? current
            : [...current, incoming]
        ));
      })
      .subscribe();
    return () => {
      supabase.removeChannel(channel);
    };
  }, [user?.id, activeConversationId, routeConversationId]);

  useEffect(() => {
    urlHydratedRef.current = false;
  }, [chatAppPath, searchParams]);

  const fetchConnections = useCallback(async (userId) => {
    if (!userId) return;
    const cachedDb = fileManagerCache.getDatabaseConnections(userId);
    const cachedApi = fileManagerCache.getApiConnections(userId);
    if (cachedDb) setDbConnections(cachedDb.connections || []);
    if (cachedApi) setApiConnections(cachedApi.connections || []);
    if (cachedDb?.isFresh && cachedApi?.isFresh) return;

    try {
      const response = await authFetch(`${getPublicApiUrl()}/api/v1/connections`);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || 'Could not load connections');
      const nextDb = payload.database_connections || [];
      const nextApi = payload.api_connections || [];
      setDbConnections(nextDb);
      setApiConnections(nextApi);
      fileManagerCache.setDatabaseConnections(userId, { connections: nextDb, healthStatus: cachedDb?.healthStatus || {} });
      fileManagerCache.setApiConnections(userId, { connections: nextApi, healthStatus: cachedApi?.healthStatus || {} });
    } catch (err: any) {
      console.error('Error fetching connections:', err);
    }
  }, [fileManagerCache]);

  // 4. ตรวจสอบสถานะการตรวจสอบสิทธิ์ (Authentication) และตั้งค่า Real-time Listener
  useEffect(() => {
    let channel;
    const checkUser = async () => {
      const e2eUser = getE2eMockUser();
      if (e2eUser) {
        setUser(e2eUser);
        fetchConversations(e2eUser.id);
        return;
      }
      const cachedAuth = fileManagerCache.getAuthUser();
      if (cachedAuth?.user) {
        setUser(cachedAuth.user);
        fetchConversations(cachedAuth.user.id);
        fetchPlanAndUsage(cachedAuth.user.id);
        fetchConnections(cachedAuth.user.id);
        if (cachedAuth.isFresh) return;
      }
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) {
        router.push(localePath('/login', routing));
      } else {
        setUser(user);
        fileManagerCache.setAuthUser(user);
        fetchConversations(user.id);
        fetchPlanAndUsage(user.id);
        fetchConnections(user.id);

        // In dev/StrictMode, this effect can run twice quickly.
        // Remove stale channels with the same topic before re-registering callbacks.
        const channelName = `chat-plan-updates-${user.id}`;
        supabase
          .getChannels()
          .filter((ch) => ch.topic === `realtime:${channelName}`)
          .forEach((ch) => {
            supabase.removeChannel(ch);
          });

        // ดักฟังการเปลี่ยนแปลงของ Table profiles เพื่ออัปเดต Plan แบบเรียลไทม์
        channel = supabase
          .channel(channelName)
          .on('postgres_changes', {
            event: 'UPDATE',
            schema: 'public',
            table: 'profiles',
            filter: `id=eq.${user.id}`
          }, () => fetchPlanAndUsage(user.id))
          .subscribe();
      }
    };
    checkUser();
    return () => {
      if (channel) supabase.removeChannel(channel);
    };
  }, [fileManagerCache, router, fetchPlanAndUsage, fetchConversations, fetchConnections, routing]);

  const focusPrompt = useCallback((content) => {
    setInput(String(content || ''));
    setTimeout(() => {
      textareaRef.current?.focus();
      const length = textareaRef.current?.value?.length || 0;
      textareaRef.current?.setSelectionRange?.(length, length);
    }, 0);
  }, []);

  const restoreBranchedContext = useCallback((loadedMessages) => {
    const conversationId = activeConversationId || routeConversationId || null;
    restoreSessionContext(loadedMessages || [], conversationId);
  }, [activeConversationId, routeConversationId, restoreSessionContext]);

  const handleEditPrompt = useCallback(async (content, sourceMessage = null) => {
    if (
      sourceMessage?.role === 'user'
      && sourceMessage.id
      && activeConversationId
      && activeBranchId
    ) {
      try {
        await forkConversationBranch({
          forkMessageId: sourceMessage.id,
          title: isEn ? 'Edited prompt' : 'แก้ไขคำถาม',
          onLoaded: restoreBranchedContext,
        });
      } catch (error: any) {
        console.error('Could not fork edited prompt:', error);
        setAiError(
          isEn
            ? 'Could not create a new chat version. The original was not changed.'
            : 'สร้างเวอร์ชันแชทใหม่ไม่สำเร็จ โดยประวัติเดิมไม่ได้ถูกแก้ไข',
        );
        return;
      }
    }
    focusPrompt(content);
  }, [
    activeBranchId,
    activeConversationId,
    focusPrompt,
    forkConversationBranch,
    isEn,
    restoreBranchedContext,
  ]);

  const handleRegenerate = useCallback(async (assistantMessage, assistantIndex) => {
    const source = precedingUserMessage(messages, assistantIndex);
    if (!source?.message?.content) return;

    if (!source.message.id || !activeConversationId || !activeBranchId) {
      focusPrompt(source.message.content);
      return;
    }

    setAiError(null);
    setIsGenerating(true);
    try {
      const forked = await forkConversationBranch({
        forkMessageId: source.message.id,
        title: isEn ? 'Regenerated answer' : 'สร้างคำตอบใหม่',
        onLoaded: restoreBranchedContext,
      });
      await handleSend(null, null, null, {
        contentOverride: source.message.content,
        conversationId: activeConversationId,
        branchId: forked.branchId,
        historyMessages: forked.messages,
      });
      if (user?.id) {
        supabase.from('chat_quality_events').insert({
          user_id: user.id,
          conversation_id: activeConversationId,
          message_id: assistantMessage?.id || null,
          event_type: 'regenerated',
          payload: {
            source: 'assistant_branch_regenerate',
            source_branch_id: activeBranchId,
            new_branch_id: forked.branchId,
          },
        }).then(({ error }) => {
          if (error) console.warn('Could not record regenerate metric:', error.message);
        });
      }
    } catch (error: any) {
      console.error('Could not regenerate on a new branch:', error);
      setIsGenerating(false);
      setAiError(
        isEn
          ? 'Could not regenerate this answer. The original version is still available.'
          : 'สร้างคำตอบใหม่ไม่สำเร็จ โดยเวอร์ชันเดิมยังอยู่ครบ',
      );
    }
  }, [
    activeBranchId,
    activeConversationId,
    focusPrompt,
    forkConversationBranch,
    handleSend,
    isEn,
    messages,
    restoreBranchedContext,
    user,
  ]);

  const handleSwitchBranch = useCallback(async (branchId) => {
    if (!branchId || branchId === activeBranchId) return;
    setAiError(null);
    try {
      await switchConversationBranch(branchId, restoreBranchedContext);
    } catch (error: any) {
      console.error('Could not switch chat branch:', error);
      setAiError(isEn ? 'Could not switch chat version.' : 'เปลี่ยนเวอร์ชันแชทไม่สำเร็จ');
    }
  }, [activeBranchId, isEn, restoreBranchedContext, switchConversationBranch]);

  // 9. ดึงรายชื่อไฟล์จาก Supabase Storage Bucket 'business-data'
  const fetchAvailableFiles = useCallback(async () => {
    if (!user) return;
    setIsFilesLoading(true);
    try {
      const [filePage, schedulesResponse] = await Promise.all([
        fetchFilePage({ limit: 50 }),
        authFetch(
          `${getPublicApiUrl()}/api/v1/etl/schedules`,
          { method: 'GET' },
        ).catch(() => null),
      ]);
      const schedulePayload = schedulesResponse?.ok
        ? await schedulesResponse.json()
        : { schedules: [] };
      const schedules = schedulePayload.schedules || [];
      const physicalOutputs = new Set(
        schedules.flatMap((schedule) => [
          schedule.latest_output_file,
          schedule.latest_output_version,
        ]).filter(Boolean),
      );
      const regularFiles = filePage.files.filter(
        (file) => !physicalOutputs.has(file.name),
      );
      const etlDatasets = schedules
        .filter((schedule) => schedule.output_dataset_key && schedule.latest_output_file)
        .map((schedule) => ({
          id: `etl-dataset:${schedule.id}`,
          name: schedule.output_dataset_key,
          display_name: `${schedule.output_name || schedule.etl_recipes?.name || 'Scheduled ETL'} · ${
            isEn ? 'latest dataset' : 'ข้อมูลล่าสุด'
          }`,
          is_etl_dataset: true,
          updated_at: schedule.last_run_at,
        }));
      setAvailableFiles([...etlDatasets, ...regularFiles]);
      setNextAvailableFilesOffset(filePage.nextOffset);
    } catch (error: any) {
      console.error('Error fetching files for chat:', error.message);
    } finally {
      setIsFilesLoading(false);
    }
  }, [isEn, user]);

  const loadMoreAvailableFiles = useCallback(async () => {
    if (nextAvailableFilesOffset === null || isFilesLoading) return;
    setIsFilesLoading(true);
    try {
      const page = await fetchFilePage({
        limit: 50,
        offset: nextAvailableFilesOffset,
      });
      setAvailableFiles((current) => {
        const known = new Set(current.map((file) => file.name));
        return [...current, ...page.files.filter((file) => !known.has(file.name))];
      });
      setNextAvailableFilesOffset(page.nextOffset);
    } catch (error: any) {
      console.error('Error loading more chat files:', error.message);
    } finally {
      setIsFilesLoading(false);
    }
  }, [isFilesLoading, nextAvailableFilesOffset]);

  const openColumnMappingModal = useCallback(async (fileNameOverride = null) => {
    const nameOverride = typeof fileNameOverride === 'string' ? fileNameOverride.trim() : '';
    const fileRef = nameOverride
      ? { name: nameOverride }
      : selectedFile;
    if (!fileRef?.name || typeof fileRef.name !== 'string' || !user) return;

    setIsGenerating(true);
    try {
      const result = await parseSampleData(fileRef, { includeJsonPaths: true, jsonPath: selectedJsonPath });
      const sample = Array.isArray(result) ? result : result.rows;
      if (!sample?.length) {
        throw new Error('No preview rows in file');
      }
      setParsedDataForMapping(sample);
      setMappingTarget({ type: 'file', fileName: fileRef.name });
      const paths = Array.isArray(result?.jsonPaths) ? result.jsonPaths : [];
      setJsonPathOptions(paths);
      if (paths.length) setSelectedJsonPath(result?.selectedJsonPath || paths[0]);
      setShowMappingModal(true);
    } catch (err: any) {
      console.error('Mapping preview error:', err);
      setAiError(t(m, 'chat.mapping.preview_error', 'Could not load file preview for mapping.'));
    } finally {
      setIsGenerating(false);
    }
  }, [selectedFile, user, m, parseSampleData, selectedJsonPath]);

  const onJsonPathChange = useCallback(async (jsonPath) => {
    const fileRef = selectedFile || (sessionFileContext?.name ? { name: sessionFileContext.name } : null);
    if (!fileRef?.name) return;
    const result = await parseSampleData(fileRef, { includeJsonPaths: true, jsonPath });
    const rows = Array.isArray(result) ? result : result.rows;
    if (!rows?.length) throw new Error('Selected JSON path has no record objects');
    setSelectedJsonPath(jsonPath || null);
    setParsedDataForMapping(rows);
  }, [selectedFile, sessionFileContext, parseSampleData]);

  const onConfirmMapping = (mapping, recipe = null) => {
    setShowMappingModal(false);
    setConfirmedMapping(mapping);
    setCleaningRecipe(recipe);
    if (mappingTarget?.type === 'connection' && mappingTarget.connection) {
      persistActiveConnection({
        ...mappingTarget.connection,
        mapping,
        cleaningRecipe: recipe,
        cleaningProfile,
      });
    } else {
      const fileName = mappingTarget?.fileName || selectedFile?.name;
      if (fileName) {
        setFileColumnMappings((prev) => ({ ...prev, [fileName]: mapping }));
        if (sessionFileContext?.name === fileName) {
          setSessionFileContext({
            ...sessionFileContext,
            mapping,
            cleaningRecipe: recipe || undefined,
            cleaningProfile,
          });
        }
      }
    }
    setMappingTarget(null);
  };

  // Speech-to-text: keep the textarea visible while final/interim words arrive.
  const stopSpeechRecognition = useCallback(() => {
    speechShouldContinueRef.current = false;
    if (speechRestartTimerRef.current) {
      clearTimeout(speechRestartTimerRef.current);
      speechRestartTimerRef.current = null;
    }
    const recognition = speechRecognitionRef.current;
    speechRecognitionRef.current = null;
    if (recognition) {
      recognition.onend = null;
      try {
        recognition.stop();
      } catch {
        // It may already be stopped after a browser-level error.
      }
    }
    setIsRecording(false);
  }, []);

  const toggleRecording = useCallback(() => {
    if (isRecording) {
      stopSpeechRecognition();
      setTimeout(() => textareaRef.current?.focus(), 0);
      return;
    }

    const SpeechRecognition = getSpeechRecognitionConstructor(
      typeof window !== 'undefined' ? window : null,
    );
    if (!SpeechRecognition) {
      setAiError(
        isEn
          ? 'Live speech-to-text is not supported in this browser. Try Chrome or Edge.'
          : 'เบราว์เซอร์นี้ไม่รองรับการพิมพ์ด้วยเสียงแบบสด กรุณาใช้ Chrome หรือ Edge',
      );
      return;
    }

    setAiError(null);
    speechBaseInputRef.current = input;
    speechCurrentTextRef.current = input;
    speechConfirmedTextRef.current = input;
    speechShouldContinueRef.current = true;
    const recognition = new SpeechRecognition();
    speechRecognitionRef.current = recognition;
    recognition.lang = routing.locale === 'th' ? 'th-TH' : 'en-US';
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onstart = () => setIsRecording(true);
    recognition.onresult = (event) => {
      let finalTranscript = '';
      let interimTranscript = '';
      for (let index = 0; index < event.results.length; index += 1) {
        const transcript = event.results[index]?.[0]?.transcript || '';
        if (event.results[index].isFinal) finalTranscript += ` ${transcript}`;
        else interimTranscript += ` ${transcript}`;
      }
      const nextText = joinSpeechTranscript(
        speechBaseInputRef.current,
        finalTranscript,
        interimTranscript,
      );
      speechConfirmedTextRef.current = joinSpeechTranscript(
        speechBaseInputRef.current,
        finalTranscript,
        '',
      );
      speechCurrentTextRef.current = nextText;
      setInput(nextText);
    };
    recognition.onerror = (event) => {
      if (event.error === 'no-speech' || event.error === 'aborted') return;
      speechShouldContinueRef.current = false;
      setIsRecording(false);
      setAiError(speechRecognitionErrorMessage(event.error, isEn));
    };
    recognition.onend = () => {
      if (!speechShouldContinueRef.current) {
        setIsRecording(false);
        return;
      }
      speechBaseInputRef.current = speechConfirmedTextRef.current;
      speechCurrentTextRef.current = speechConfirmedTextRef.current;
      speechRestartTimerRef.current = setTimeout(() => {
        try {
          recognition.start();
        } catch {
          speechShouldContinueRef.current = false;
          setIsRecording(false);
        }
      }, 150);
    };

    try {
      recognition.start();
    } catch (error: any) {
      speechShouldContinueRef.current = false;
      speechRecognitionRef.current = null;
      setIsRecording(false);
      setAiError(
        speechRecognitionErrorMessage(error?.name || 'unknown', isEn),
      );
    }
  }, [
    input,
    isEn,
    isRecording,
    routing.locale,
    stopSpeechRecognition,
  ]);

  useEffect(() => () => {
    speechShouldContinueRef.current = false;
    if (speechRestartTimerRef.current) {
      clearTimeout(speechRestartTimerRef.current);
    }
    try {
      speechRecognitionRef.current?.abort();
    } catch {
      // Recognition may already be inactive during unmount.
    }
  }, []);

  const userInitial = user?.email?.charAt(0).toUpperCase() || '?';
  const displayConversationId = activeConversationId || routeChatId;
  const isNewChat = !displayConversationId;
  // Data Setup Copilot needs the normal chat column layout; the centered new-chat
  // hero steals flex space and nests scroll with the message list.
  const isComposerNewChat = isNewChat && !dataSetupSession;
  const showNewChatBackdrop =
    isComposerNewChat && messages.length === 0 && !isGenerating && !isTyping;
  const activeConversationTitle = sortedConversations.find((conversation) => conversation.id === displayConversationId)?.title;
  const reportSource = visualizationContext?.sourceConfig || {};
  const visualizationSourceOverridden = Boolean(
    (selectedFile?.name && selectedFile.name !== reportSource.file_name)
    || (activeConnection?.id && activeConnection.id !== reportSource.connection_id),
  );
  const panelSourceLabel = activeConnection
    ? `${activeConnection.name}${activeConnection.sqlTable ? ` · ${activeConnection.sqlTable}` : ''}`
    : (selectedFile?.name || sessionFileContext?.name || null);

  return (
    <div className={`app-shell chat-shell icon-motion-scope relative flex ${isPanel ? `chat-panel-shell h-full min-h-0${isComposerNewChat ? ' chat-panel-new' : ''}` : 'h-[100svh]'} font-sans text-slate-800 dark:text-slate-200 overflow-hidden transition-colors duration-500`}>
      {/* Global Animations & Theme Styles */}
      <style>
        {`
          @keyframes chat-aurora-float-left {
            0%, 100% { transform: translate3d(-12%, -4%, 40px) scale(1); }
            50% { transform: translate3d(-4%, 5%, 90px) scale(1.08); }
          }
          @keyframes chat-aurora-float-right {
            0%, 100% { transform: translate3d(11%, 4%, 20px) scale(1.04); }
            50% { transform: translate3d(3%, -6%, 110px) scale(0.96); }
          }
          @keyframes chat-aurora-breathe {
            0%, 100% { opacity: 0.42; transform: translateZ(10px) scale(0.94); }
            50% { opacity: 0.72; transform: translateZ(80px) scale(1.08); }
          }
          @keyframes chat-aurora-ring {
            0%, 100% { transform: rotateX(68deg) rotateZ(-7deg) scale(0.96); opacity: 0.38; }
            50% { transform: rotateX(72deg) rotateZ(7deg) scale(1.04); opacity: 0.6; }
          }
          @keyframes chat-aurora-ring-reverse {
            0%, 100% { transform: rotateX(76deg) rotateZ(12deg) scale(1.02); opacity: 0.24; }
            50% { transform: rotateX(70deg) rotateZ(-10deg) scale(0.94); opacity: 0.5; }
          }
          @keyframes chat-aurora-ribbon-left {
            0%, 100% { transform: translate3d(-8%, -5%, -20px) rotate(-14deg) scaleX(0.96); }
            50% { transform: translate3d(7%, 5%, 80px) rotate(-6deg) scaleX(1.08); }
          }
          @keyframes chat-aurora-ribbon-right {
            0%, 100% { transform: translate3d(9%, 4%, 10px) rotate(13deg) scaleX(1.04); }
            50% { transform: translate3d(-5%, -6%, 100px) rotate(5deg) scaleX(0.94); }
          }
          @keyframes chat-aurora-prism {
            0% { transform: translateZ(65px) rotate(0deg) scale(0.92); }
            50% { transform: translateZ(125px) rotate(180deg) scale(1.08); }
            100% { transform: translateZ(65px) rotate(360deg) scale(0.92); }
          }
          @keyframes chat-aurora-stars {
            0%, 100% { opacity: 0.26; transform: translate3d(0, 0, 0) scale(1); }
            50% { opacity: 0.62; transform: translate3d(0, -8px, 45px) scale(1.02); }
          }
          @keyframes chat-aurora-grid {
            0%, 100% { transform: perspective(620px) rotateX(64deg) translateY(31%) scale(1.35); }
            50% { transform: perspective(620px) rotateX(67deg) translateY(29%) scale(1.4); }
          }
          .chat-new-aurora {
            background:
              radial-gradient(circle at 50% 44%, rgba(255,255,255,0.94) 0%, rgba(224,242,254,0.64) 27%, transparent 61%),
              radial-gradient(circle at 17% 22%, rgba(103,232,249,0.2), transparent 36%),
              radial-gradient(circle at 84% 71%, rgba(129,140,248,0.22), transparent 40%),
              linear-gradient(145deg, rgba(248,250,252,0.72), rgba(219,234,254,0.52));
          }
          .chat-new-scene {
            perspective: 900px;
            transform-style: preserve-3d;
          }
          .chat-new-orb {
            border-radius: 9999px;
            filter: blur(58px);
            transform-style: preserve-3d;
            will-change: transform, opacity;
          }
          .chat-new-orb-left {
            width: min(56vw, 760px);
            height: min(34vw, 460px);
            background: radial-gradient(ellipse, rgba(56,189,248,0.42) 0%, rgba(14,165,233,0.22) 42%, transparent 72%);
            animation: chat-aurora-float-left 13s ease-in-out infinite;
          }
          .chat-new-orb-right {
            width: min(52vw, 700px);
            height: min(32vw, 430px);
            background: radial-gradient(ellipse, rgba(99,102,241,0.3) 0%, rgba(59,130,246,0.2) 43%, transparent 72%);
            animation: chat-aurora-float-right 15s ease-in-out infinite;
          }
          .chat-new-orb-core {
            width: min(34vw, 470px);
            height: min(24vw, 320px);
            background: radial-gradient(ellipse, rgba(186,230,253,0.7) 0%, rgba(125,211,252,0.28) 46%, transparent 72%);
            filter: blur(42px);
            animation: chat-aurora-breathe 9s ease-in-out infinite;
          }
          .chat-new-ring {
            width: min(64vw, 860px);
            height: min(28vw, 360px);
            border: 1px solid rgba(56,189,248,0.48);
            border-radius: 9999px;
            box-shadow:
              0 0 85px rgba(56,189,248,0.22),
              inset 0 0 85px rgba(147,197,253,0.2);
            animation: chat-aurora-ring 12s ease-in-out infinite;
            will-change: transform, opacity;
          }
          .chat-new-ring-secondary {
            width: min(49vw, 650px);
            height: min(19vw, 245px);
            border-color: rgba(129,140,248,0.4);
            animation: chat-aurora-ring-reverse 10s ease-in-out infinite;
          }
          .chat-new-ring-outer {
            width: min(78vw, 1080px);
            height: min(34vw, 445px);
            border-color: rgba(14,165,233,0.2);
            box-shadow: 0 0 110px rgba(14,165,233,0.12);
            animation-duration: 17s;
          }
          .chat-new-floor {
            width: min(78vw, 1050px);
            height: min(35vw, 450px);
            border-radius: 50%;
            background: radial-gradient(ellipse, rgba(14,165,233,0.26), rgba(59,130,246,0.09) 44%, transparent 72%);
            filter: blur(16px);
            transform: rotateX(72deg) translateY(18%);
          }
          .chat-new-ribbon {
            width: min(82vw, 1120px);
            height: min(18vw, 250px);
            border-radius: 50%;
            filter: blur(34px);
            transform-style: preserve-3d;
            opacity: 0.68;
            will-change: transform;
          }
          .chat-new-ribbon-left {
            background: linear-gradient(90deg, transparent 2%, rgba(34,211,238,0.38) 25%, rgba(56,189,248,0.2) 54%, transparent 94%);
            animation: chat-aurora-ribbon-left 14s ease-in-out infinite;
          }
          .chat-new-ribbon-right {
            background: linear-gradient(90deg, transparent 4%, rgba(99,102,241,0.16) 28%, rgba(59,130,246,0.38) 66%, transparent 97%);
            animation: chat-aurora-ribbon-right 16s ease-in-out infinite;
          }
          .chat-new-prism {
            width: min(29vw, 390px);
            aspect-ratio: 1;
            border-radius: 42% 58% 53% 47%;
            background: conic-gradient(
              from 20deg,
              rgba(34,211,238,0.5),
              rgba(59,130,246,0.18),
              rgba(129,140,248,0.42),
              rgba(186,230,253,0.54),
              rgba(34,211,238,0.5)
            );
            filter: blur(42px);
            mix-blend-mode: multiply;
            opacity: 0.54;
            animation: chat-aurora-prism 20s linear infinite;
            will-change: transform;
          }
          .chat-new-stars {
            background-image:
              radial-gradient(circle, rgba(14,165,233,0.62) 0 1px, transparent 1.7px),
              radial-gradient(circle, rgba(99,102,241,0.46) 0 1px, transparent 1.8px),
              radial-gradient(circle, rgba(125,211,252,0.7) 0 1.4px, transparent 2px);
            background-position: 0 0, 33px 47px, 81px 19px;
            background-size: 113px 113px, 149px 149px, 191px 191px;
            animation: chat-aurora-stars 7s ease-in-out infinite;
            mask-image: radial-gradient(ellipse at center, black 8%, transparent 75%);
          }
          .chat-new-grid {
            top: 48%;
            left: -12%;
            right: -12%;
            bottom: -30%;
            background-image:
              linear-gradient(rgba(56,189,248,0.16) 1px, transparent 1px),
              linear-gradient(90deg, rgba(56,189,248,0.16) 1px, transparent 1px);
            background-size: 48px 48px;
            mask-image: linear-gradient(to bottom, transparent, black 28%, transparent 88%);
            animation: chat-aurora-grid 11s ease-in-out infinite;
            transform-origin: center top;
          }
          .chat-new-vignette {
            background:
              linear-gradient(to bottom, rgba(255,255,255,0.28), transparent 22%, transparent 76%, rgba(248,250,252,0.46)),
              radial-gradient(ellipse at center, transparent 34%, rgba(241,245,249,0.36) 100%);
          }
          @media (prefers-reduced-motion: reduce) {
            .chat-new-orb,
            .chat-new-ring,
            .chat-new-ribbon,
            .chat-new-prism,
            .chat-new-stars,
            .chat-new-grid {
              animation: none;
            }
          }
          .dark .chat-new-aurora {
            background:
              radial-gradient(circle at 50% 44%, rgba(30,41,59,0.44) 0%, rgba(15,23,42,0.2) 38%, transparent 68%),
              radial-gradient(circle at 16% 25%, rgba(8,145,178,0.18), transparent 38%),
              radial-gradient(circle at 85% 72%, rgba(79,70,229,0.2), transparent 42%),
              linear-gradient(145deg, rgba(2,6,23,0.56), rgba(15,23,42,0.3));
          }
          .dark .chat-new-orb {
            mix-blend-mode: screen;
            opacity: 0.86;
          }
          .dark .chat-new-ring {
            border-color: rgba(56,189,248,0.38);
            box-shadow:
              0 0 90px rgba(14,165,233,0.2),
              inset 0 0 90px rgba(59,130,246,0.14);
          }
          .dark .chat-new-prism {
            mix-blend-mode: screen;
            opacity: 0.42;
          }
          .dark .chat-new-ribbon {
            mix-blend-mode: screen;
            opacity: 0.54;
          }
          .dark .chat-new-grid {
            opacity: 0.66;
          }
          .dark .chat-new-vignette {
            background:
              linear-gradient(to bottom, rgba(2,6,23,0.18), transparent 22%, transparent 76%, rgba(2,6,23,0.32)),
              radial-gradient(ellipse at center, transparent 30%, rgba(2,6,23,0.42) 100%);
          }
        `}
      </style>

      {/* Calm warm ambient scene — only before the first message */}
      {showNewChatBackdrop && (
        <div className="chat-empty-ambient absolute inset-0 pointer-events-none z-0 overflow-hidden select-none">
          <div className="chat-empty-glow" />
          <div className="chat-empty-grain" />
        </div>
      )}

      {/* Mobile Backdrop */}
      {!isPanel && isSidebarOpen && typeof window !== 'undefined' && window.innerWidth < 768 && (
        <div
          className="fixed inset-0 bg-black/20 dark:bg-black/60 backdrop-blur-sm z-40 md:hidden"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* Sidebar - ประวัติการสนทนา */}
      {!isPanel && <ChatSidebar
        isSidebarOpen={isSidebarOpen}
        setIsSidebarOpen={setIsSidebarOpen}
        navigate={navigate}
        routing={routing}
        isEn={isEn}
        startNewChat={handleStartNewChat}
        conversations={sortedConversations}
        hasMoreConversations={hasMoreConversations}
        loadingMoreConversations={loadingMoreConversations}
        loadMoreConversations={loadMoreConversations}
        pinnedConvIds={pinnedConvIds}
        togglePinConversation={togglePinConversation}
        renameConversation={renameConversation}
        activeConversationId={displayConversationId}
        loadConversation={handleLoadConversation}
        triggerDeleteConversation={triggerDeleteConversation}
        user={user}
        userInitial={userInitial}
        plan={plan}
        tokensUsedToday={profileUsage.used_today}
        tokensUsedThisWeek={profileUsage.used_week}
        dailyResetAt={profileUsage.daily_reset_at}
        weeklyResetAt={profileUsage.weekly_reset_at}
        timezone={profileUsage.timezone}
      />}

      {/* Main Chat Content */}
      <main className="min-w-0 flex-1 flex flex-col relative overflow-hidden z-10">
        <header className={`chat-toolbar relative z-30 shrink-0 px-3 md:px-5 flex items-center justify-between gap-3 ${isPanel ? 'h-[52px]' : 'h-14'}`}>
          <div className="flex items-center gap-3 min-w-0">
            {!isPanel && <button
              disabled={isPanel && (isGenerating || isSendInFlight)}
              onClick={() => {
                if (isPanel) {
                  onOpenFullChat?.(displayConversationId);
                  return;
                }
                setIsSidebarOpen((open) => !open);
              }}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-stone-200 bg-white/70 text-stone-500 transition-colors hover:border-orange-300 hover:bg-orange-50 hover:text-orange-700 disabled:cursor-not-allowed disabled:opacity-40 dark:border-stone-800 dark:bg-stone-900/65 dark:text-stone-400 dark:hover:border-orange-800 dark:hover:bg-orange-950/30 dark:hover:text-orange-300"
              title={isPanel
                ? (isEn ? 'Open full Chat' : 'เปิดแชทเต็มหน้า')
                : (isSidebarOpen ? (isEn ? "Hide menu" : "ซ่อนเมนู") : (isEn ? "Show menu" : "แสดงเมนู"))}
            >
              {isPanel
                ? <PanelLeftOpen size={19} strokeWidth={1.5} />
                : (isSidebarOpen ? <PanelLeftOpen size={19} strokeWidth={1.5} className="rotate-180" /> : <PanelLeftOpen size={19} strokeWidth={1.5} />)}
            </button>}
            <div className="min-w-0">
              <h1 className="truncate text-sm font-semibold text-stone-900 dark:text-stone-100">
                {activeConversationTitle || (isEn ? 'New analysis' : 'การวิเคราะห์ใหม่')}
              </h1>
            </div>
            {isPanel && panelSourceLabel && (
              <div className="flex min-w-0 max-w-[220px] items-center gap-1.5 rounded-lg border border-stone-200 bg-stone-50 px-2 py-1 text-[10px] text-stone-600 dark:border-stone-700 dark:bg-zinc-900 dark:text-stone-300">
                {activeConnection
                  ? (activeConnection.type === 'sql' ? <Database className="h-3.5 w-3.5 shrink-0" /> : <Globe className="h-3.5 w-3.5 shrink-0" />)
                  : <FileText className="h-3.5 w-3.5 shrink-0" />}
                <span className="truncate">{panelSourceLabel}</span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            {branches.length > 1 && activeBranchId && (
              <ChatBranchSelector
                branches={branches}
                activeBranchId={activeBranchId}
                disabled={isGenerating || isSendInFlight}
                isEn={isEn}
                onSwitch={handleSwitchBranch}
              />
            )}
            {!isPanel && <button
              type="button"
              onClick={() => setShowMemoryPanel(true)}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-stone-200/80 bg-white/60 px-2.5 text-[10px] font-medium text-stone-500 hover:border-orange-300 hover:text-orange-700 dark:border-stone-800 dark:bg-stone-900/55 dark:text-stone-400 dark:hover:border-orange-800 dark:hover:text-orange-300"
              title={isEn ? 'View and manage conversation memory' : 'ดูและจัดการความจำการสนทนา'}
            >
              <Layers3 size={14} className="text-stone-500 dark:text-stone-400" />
              <span className="hidden sm:inline">{isEn ? 'Memory' : 'ความจำ'}</span>
            </button>}
            {!isPanel && <div className="hidden h-9 items-center gap-2 rounded-lg px-2 text-[10px] font-medium text-stone-500 dark:text-stone-400 lg:flex">
              <ShieldCheck size={14} className="text-amber-700 dark:text-amber-400" strokeWidth={1.6} />
              {isEn ? 'Private workspace' : 'พื้นที่ทำงานส่วนตัว'}
            </div>}
            {isPanel && (
              <button type="button" disabled={isGenerating || isSendInFlight} onClick={onClosePanel} className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-stone-200 text-stone-500 hover:border-orange-300 hover:text-orange-700 disabled:cursor-not-allowed disabled:opacity-40 dark:border-stone-800 dark:text-stone-400" title={isEn ? 'Close Chat panel' : 'ปิด Chat'}>
                <span aria-hidden="true" className="text-base leading-none">×</span>
              </button>
            )}
          </div>
        </header>

        <ChatMemoryPanel
          open={showMemoryPanel}
          onClose={() => setShowMemoryPanel(false)}
          userId={user?.id}
          conversationId={activeConversationId || routeConversationId || null}
          isEn={isEn}
        />

        {!isPanel && visualizationContext?.reportId && (
          <div className="mx-3 mt-2 flex shrink-0 items-center justify-between gap-2 rounded-xl border border-amber-200/80 bg-amber-50/70 px-3 py-2.5 text-[10px] text-amber-950 dark:border-amber-900/60 dark:bg-amber-950/25 dark:text-amber-100">
            <div className="min-w-0 truncate">
              {visualizationSourceOverridden ? (
                <span className="font-semibold">{isEn ? 'This turn uses a different attached source' : 'คำถามนี้ใช้แหล่งข้อมูลที่แนบใหม่'}</span>
              ) : (
                <>
                  <span className="font-semibold">{isEn ? 'Viewing' : 'กำลังดู'}:</span>{' '}
                  {visualizationContext.reportTitle || (isEn ? 'Decision packet' : 'Decision packet')}
                  {visualizationContext.widgetTitle ? ` · ${visualizationContext.widgetTitle}` : ''}
                </>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {!visualizationSourceOverridden && String(input || '').trim() && onPreviewDashboard && (
                <button type="button" disabled={dashboardPreviewBusy || isGenerating} onClick={() => onPreviewDashboard(input)} className="font-semibold text-orange-700 hover:underline disabled:opacity-40 dark:text-orange-300">
                  {dashboardPreviewBusy ? (isEn ? 'Previewing…' : 'กำลัง Preview…') : (isEn ? 'Preview change' : 'Preview การปรับ')}
                </button>
              )}
              {visualizationContext.widgetId && (
                <button type="button" onClick={onClearVisualizationWidget} className="font-semibold text-orange-700 hover:underline dark:text-orange-300">
                  {isEn ? 'Clear focus' : 'ล้างจุดโฟกัส'}
                </button>
              )}
            </div>
          </div>
        )}

        {aiError && (
          <div className="absolute top-20 left-4 right-4 z-30 bg-red-50/95 dark:bg-red-900/40 backdrop-blur-md border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-2xl text-sm font-sans flex justify-between items-center shadow-lg">
            <span>{aiError}</span>
            <button onClick={() => setAiError(null)} className="text-red-500 hover:text-red-700 font-bold">✕</button>
          </div>
        )}

        {isPanel && isComposerNewChat && messages.length === 0 && !isGenerating && !isTyping && (
          <div className="chat-panel-empty relative z-10 flex flex-1 items-start px-4 py-5">
            <div className="w-full">
              <div className="mx-auto max-w-sm rounded-2xl border border-stone-200/90 bg-white/75 p-3.5 shadow-sm dark:border-stone-800 dark:bg-zinc-900/55">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300"><MessageSquare size={15} /></div>
                  <div><h2 className="text-xs font-bold text-stone-900 dark:text-stone-100">{isEn ? 'Ask the report' : 'ถามเกี่ยวกับรายงาน'}</h2><p className="mt-0.5 text-[10px] text-stone-500 dark:text-stone-400">{isEn ? 'Use a prompt or write your own below.' : 'เลือกคำถามหรือพิมพ์คำถามของคุณด้านล่าง'}</p></div>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {[
                    isEn ? 'Summarize the key decisions from this dashboard' : 'สรุปประเด็นสำคัญจาก Dashboard นี้',
                    isEn ? 'Explain the largest change and its likely drivers' : 'อธิบายการเปลี่ยนแปลงที่มากที่สุดและปัจจัยที่น่าจะเกี่ยวข้อง',
                    isEn ? 'Suggest a useful follow-up chart' : 'แนะนำกราฟที่ควรดูต่อ',
                  ].map((prompt) => (
                    <button key={prompt} type="button" onClick={() => { setInput(prompt); window.setTimeout(() => textareaRef.current?.focus(), 0); }} className="rounded-lg border border-stone-200 bg-stone-50 px-2.5 py-1.5 text-left text-[10px] font-medium text-stone-600 transition-colors hover:border-amber-300 hover:bg-amber-50 hover:text-amber-900 dark:border-stone-800 dark:bg-zinc-950/70 dark:text-stone-300 dark:hover:border-amber-800 dark:hover:bg-amber-950/20 dark:hover:text-amber-200">
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        <ChatMessageList
          isNewChat={isComposerNewChat}
          messages={messages}
          isGenerating={isGenerating}
          isTyping={isTyping}
          stopTyping={stopTyping}
          setIsGenerating={setIsGenerating}
          messagesEndRef={messagesEndRef}
          getDisplayName={getDisplayName}
          selectedFile={selectedFile}
          columnMapping={confirmedMapping ?? sessionFileContext?.mapping}
          userId={user?.id}
          conversationId={activeConversationId || routeConversationId || null}
          bottomCharts={bottomCharts}
          handleCommitToBottom={handleCommitToBottom}
          reasoningProgress={reasoningProgress}
          analysisContext={analysisContext}
          showReasoningProgress={
            (isTyping || isGenerating || isSendInFlight)
            && !(
              messages.length > 0
              && messages[messages.length - 1]?.role === 'ai'
              && String(messages[messages.length - 1]?.content || '').trim().length > 0
            )
          }
          onEditPrompt={handleEditPrompt}
          onRegenerateResponse={handleRegenerate}
          onRetryFailed={handleRetryFailedMessage}
          onSuggestedQuestion={handleSuggestedQuestion}
          conversationalSetupActive={Boolean(
            conversationalSetupEnabled
            && dataSetupSession
            && !['ready', 'failed', 'cancelled'].includes(dataSetupSession.status),
          )}
          onOrchestrationResolve={handleOrchestrationResolve}
          dataSetupCard={dataSetupSession && conversationalSetupEnabled ? (
            <div className="mt-4 space-y-2">
              <CurrentWorkflowPanel
                currentOrchestration={{
                  ...currentOrchestration,
                  sessionStatus: currentOrchestration.sessionStatus
                    || dataSetupSession.status,
                }}
                isEn={isEn}
                disabled={isGenerating || isSendInFlight}
                onResolve={handleOrchestrationResolve}
                onRetry={handleOrchestrationResolve}
                onReconcile={() => reconcileSetup({
                  sessionId: dataSetupSession.id,
                  session: dataSetupSession,
                })}
                onContinue={handleContinueWorkflow}
              />
            </div>
          ) : null}
        />

        {/* ส่วนกล่อง Input ท้ายหน้าจอ */}
        <ChatInputArea
          isNewChat={isComposerNewChat}
          isGenerating={isGenerating}
          handleStopGeneration={handleStopGeneration}
          user={user}
          selectedFile={selectedFile}
          setSelectedFile={setSelectedFile}
          setShowFileModal={setShowFileModal}
          fetchAvailableFiles={fetchAvailableFiles}
          handleSend={handleAdaptiveSend}
          isRecording={isRecording}
          input={input}
          setInput={setInput}
          textareaRef={textareaRef}
          toggleRecording={toggleRecording}
          isEn={isEn}
          getDisplayName={getDisplayName}
          mappedColumnCount={countMappedColumns(
            confirmedMapping ?? (selectedFile ? fileColumnMappings[selectedFile.name] : null) ?? sessionFileContext?.mapping
          )}
          onEditColumnMapping={openColumnMappingModal}
          onClearAttachedFile={clearAttachedFile}
          inputPlaceholder={agentSession ? t(m, 'chat.agent_clarify_placeholder', isEn ? 'Answer the analyst\'s question to continue…' : 'ตอบคำถามจากนักวิเคราะห์เพื่อดำเนินการต่อ…') : undefined}
          modelMode={modelMode}
          setModelMode={setModelMode}
          plan={plan}
          isPlanLoading={isPlanLoading}
          canSendSourceOnly={Boolean(
            selectedFile?.name || activeConnection?.id || sessionFileContext?.name
          )}
          panelMode={isPanel}
          dbConnections={dbConnections}
          apiConnections={apiConnections}
          activeConnection={activeConnection}
          setActiveConnection={persistActiveConnection}
          connectionMappedColumnCount={countMappedColumns(activeConnection?.mapping)}
          onEditConnectionMapping={
            activeConnection?.type === 'api'
              ? () => requestConnectionMapping(activeConnection)
              : undefined
          }
          sessionFileName={!selectedFile && sessionFileContext?.name ? sessionFileContext.name : null}
          sessionMappedColumnCount={
            !selectedFile && sessionFileContext?.mapping
              ? countMappedColumns(sessionFileContext.mapping)
              : 0
          }
          onClearSessionFile={clearSessionFileContext}
          onEditSessionColumnMapping={
            sessionFileContext?.name && !selectedFile
              ? () => openColumnMappingModal(sessionFileContext.name)
              : undefined
          }
        />
      </main>

      <FileSelectionModal
        showFileModal={showFileModal}
        setShowFileModal={setShowFileModal}
        isFilesLoading={isFilesLoading}
        availableFiles={availableFiles}
        hasMoreFiles={nextAvailableFilesOffset !== null}
        loadMoreFiles={loadMoreAvailableFiles}
        setSelectedFile={setSelectedFile}
        getDisplayName={getDisplayName}
        navigate={navigate}
        routing={routing}
      />

      <ColumnMappingModal
        isOpen={showMappingModal}
        onClose={() => {
          setShowMappingModal(false);
          setMappingTarget(null);
        }}
        onConfirm={onConfirmMapping}
        parsedData={parsedDataForMapping}
        fileName={
          mappingTarget?.type === 'connection'
            ? mappingTarget.connection?.name
            : getDisplayName(
                mappingTarget?.fileName || selectedFile?.name || sessionFileContext?.name,
              )
        }
        storageFileName={
          mappingTarget?.type === 'connection'
            ? null
            : mappingTarget?.fileName || selectedFile?.name || sessionFileContext?.name
        }
        datasetKey={
          mappingTarget?.type === 'connection'
            ? `api:${mappingTarget.connection?.id}`
            : mappingTarget?.fileName || selectedFile?.name || sessionFileContext?.name
        }
        jsonPaths={jsonPathOptions}
        selectedJsonPath={selectedJsonPath}
        onJsonPathChange={onJsonPathChange}
        userId={user?.id}
        cleaningProfile={cleaningProfile}
        onCleaningProfileChange={setCleaningProfile}
        initialMapping={
          mappingTarget?.type === 'connection'
            ? mappingTarget.connection?.mapping
            : confirmedMapping ??
              (selectedFile ? fileColumnMappings[selectedFile.name] : null) ??
              sessionFileContext?.mapping
        }
        initialRecipe={
          mappingTarget?.type === 'connection'
            ? mappingTarget.connection?.cleaningRecipe
            : cleaningRecipe ?? sessionFileContext?.cleaningRecipe
        }
      />

      <DeleteConfirmationModal
        isOpen={deleteModal.show}
        onClose={() => setDeleteConfirm({ show: false, convId: null, title: '' })}
        onConfirm={handleConfirmDeleteConversation}
        title={t(m, 'chat.delete_conv_title', 'Delete conversation?')}
        subject={deleteModal.title}
        message={t(
          m,
          'chat.delete_conv_message',
          'All chat history in this conversation will be permanently deleted and cannot be recovered.',
        )}
        confirmButtonText={t(m, 'chat.delete_conv_confirm', 'Delete chat')}
        cancelButtonText={t(m, 'chat.delete_conv_cancel', 'Cancel')}
      />

      <QuotaExceededModal
        isOpen={quotaModal.show}
        onClose={() => setQuotaModal((prev) => ({ ...prev, show: false }))}
        onUpgrade={() => {
          setQuotaModal((prev) => ({ ...prev, show: false }));
          router.push(localePath('/pricing', routing));
        }}
        title={t(m, 'chat.quota_exceeded_title', 'Token quota reached')}
        message={quotaModal.message}
        used={quotaModal.used}
        limit={quotaModal.limit}
        resetAt={quotaModal.resetAt}
        resetAtLabel={t(m, 'chat.quota_reset_at', 'Next reset')}
        closeLabel={t(m, 'chat.quota_close', 'Close')}
        upgradeLabel={t(m, 'chat.quota_upgrade', 'View plans')}
      />

      {/* Premium Chart Selection Popup Modal */}
      {showChartModal && latestChartData && (
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
                onClick={() => setShowChartModal(false)}
                className="absolute top-0 right-0 p-2 rounded-lg transition-colors text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                title={t(m, 'chat.cancel', 'ยกเลิก')}
              >
                ✕
              </button>
            </div>

            <div className="grid grid-cols-4 gap-2 mb-8">
              {[
                { type: 'bar', label: t(m, 'chat.chart_bar', 'กราฟแท่ง'), desc: 'Bar Chart', Icon: BarChart3 },
                { type: 'line', label: t(m, 'chat.chart_line', 'กราฟเส้น'), desc: 'Line Chart', Icon: LineChart },
                { type: 'area', label: t(m, 'chat.chart_area', 'พื้นที่'), desc: 'Area Chart', Icon: AreaChart },
                { type: 'pie', label: t(m, 'chat.chart_pie', 'วงกลม'), desc: 'Pie Chart', Icon: PieChart }
              ].map(opt => {
                const active = modalSelectedTypes.includes(opt.type);
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
                onClick={handleConfirmCharts}
                className="w-full py-3 btn-primary text-sm flex items-center justify-center gap-2"
              >
                {t(m, 'chat.generate_and_render', 'สร้างและเรนเดอร์กราฟ')} ({modalSelectedTypes.length})
              </button>
              <button
                onClick={() => setShowChartModal(false)}
                className="w-full py-3 btn-secondary text-sm"
              >
                {t(m, 'chat.cancel', 'ยกเลิก')}
              </button>
            </div>

          </div>
        </div>
      )}
    </div>
  );
};

export default Chat;
