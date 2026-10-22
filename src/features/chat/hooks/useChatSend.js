import { useRef, useCallback } from 'react';
import { finishChatTurn } from '../chatTurnLifecycle.js';
import { supabase } from '../../../utils/supabaseClient.js';
import { localePath } from '../../../utils/locale.js';
import { t } from '../../../utils/i18n.js';
import { checkMessageQuota } from '../../../utils/profileQuota.js';
import { sanitizeMessageContent } from '../messageContent.js';
import { consumeChatStream } from '../chatStream.js';
import {
  INITIAL_REASONING_PROGRESS,
  applyStreamStatus,
  createReasoningProgress,
} from '../reasoningProgress.js';
import { getFriendlyChatError } from '../chatErrors.js';
import { mergeWebSources } from '../webSources.js';
import {
  isAnalysisRequest,
  needsUserApprovedMapping,
  shouldUseSessionFile,
} from '../analysisIntent.js';
import { countMappedColumns } from '../columnMappingOptions.js';
import { formatConnectionMention, resolveConnectionContext } from '../connectionMention.js';
import { resolveModelModeForPlan } from '../modelModeAccess.js';
import {
  generationRequestId,
  isBranchingUnavailable,
  retryHistory,
} from '../chatBranches.js';

import { getPublicApiUrl } from '../../../utils/env.js';
import { visualizationContextForRequest } from '../visualizationChatContext.js';
import { dedupeConversationMessages } from '../chatSessionStorage.js';

/**
 * Chat message send, SSE stream handling, and generation abort.
 */
export function useChatSend({
  m,
  routing,
  navigate,
  onConversationCreated,
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
  setActiveConnection,
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
  cleaningProfile = 'standard',
  cleaningRecipe = null,
  selectedJsonPath = null,
  modelMode = 'auto',
  dataSetupSessionId = null,
  onOrchestrationReady = null,
  onOrchestrationUpdate = null,
  visualizationContext = null,
}) {
  const abortControllerRef = useRef(null);
  const webSourcesRef = useRef([]);
  const cleaningReportRef = useRef(null);
  const reasoningTraceRef = useRef([]);

  const turnCleanup = useCallback(() => finishChatTurn({
    setIsGenerating,
    setIsTyping,
    setAnalysisStreamStarted,
    abortControllerRef,
  }), [setIsGenerating, setIsTyping, setAnalysisStreamStarted]);

  const stopGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setStopTyping(true);
    turnCleanup();
    setMessages((current) => current.map((message) => (
      message.role === 'ai' && message.streaming
        ? { ...message, streaming: false, stopped: true }
        : message
    )));
  }, [setMessages, setStopTyping, turnCleanup]);

  const sendMessage = useCallback(
    async (e, mappingOverride = null, cleaningRecipeOverride = null, sendOptions = null) => {
      if (e) e.preventDefault();
      const options = sendOptions || {};
      const setupIntent = options.setupIntent || null;
      const userContent = String(options.contentOverride ?? input).trim();
      // Attachment-only conversational setup may omit visible user text.
      if (!userContent && !setupIntent) return;

      const attachedFile = options.fileOverride || selectedFile;
      const clarificationSessionId = agentSession?.sessionId ?? null;
      const effectiveCleaningRecipe = cleaningRecipeOverride ?? cleaningRecipe;
      const clientRequestId = options.requestId || generationRequestId();
      const isInlineRetry = options.retry === true;
      const requestHistory = Array.isArray(options.historyMessages)
        ? options.historyMessages
        : messages;
      const effectiveSetupSessionId = options.dataSetupSessionId
        || dataSetupSessionId
        || sessionFileContext?.dataSetupSessionId
        || effectiveCleaningRecipe?.data_setup_session_id
        || null;
      // A ready Data Setup session owns the analytical identity.  The browser
      // can retain the original upload briefly while React state settles; never
      // let that raw filename override the approved output Dataset Version.
      const approvedSessionFileName = effectiveSetupSessionId
        && sessionFileContext?.dataSetupSessionId === effectiveSetupSessionId
        && sessionFileContext?.name
        ? sessionFileContext.name
        : null;
      const skipMappingGate = Boolean(
        effectiveSetupSessionId || setupIntent || options.conversationalSetup,
      );

      let connId = null;
      let connType = null;
      let sqlTable = null;
      const allConns = [
        ...dbConnections.map((c) => ({ ...c, type: 'sql' })),
        ...apiConnections.map((c) => ({ ...c, type: 'api' })),
      ];
      const connCtx = options.ignoreConnection
        ? { connId: null, connType: null, sqlTable: null, connection: null }
        : resolveConnectionContext(userContent, allConns, activeConnection);
      if (connCtx.connId) {
        connId = connCtx.connId;
        connType = connCtx.connType;
        sqlTable = connCtx.sqlTable;
        if (connCtx.connection) {
          setActiveConnection({
            ...connCtx.connection,
            sqlTable: connCtx.sqlTable || undefined,
          });
        }
      }

      const useSessionFile =
        !!sessionFileContext
        && !connId
        && (Boolean(approvedSessionFileName) || shouldUseSessionFile(userContent, {
          hasAttachedFile: !!attachedFile,
          hasConnection: !!connId,
          isAgentClarification: !!clarificationSessionId,
        }));
      const contextFileName =
        approvedSessionFileName
        ?? attachedFile?.name
        ?? (useSessionFile ? sessionFileContext?.name : null);
      const connectionForRequest = connCtx.connection
        ? {
            ...connCtx.connection,
            ...(activeConnection?.id === connCtx.connection.id ? activeConnection : {}),
            sqlTable: connCtx.sqlTable || undefined,
          }
        : activeConnection;
      const activeMapping = connType === 'api'
        ? mappingOverride || connectionForRequest?.mapping || null
        : resolveColumnMapping(mappingOverride, contextFileName);
      const fileForMapping = approvedSessionFileName
        ? { name: approvedSessionFileName }
        : attachedFile || (
        useSessionFile && sessionFileContext?.name
          ? { name: sessionFileContext.name }
          : null
      );
      const sourceFileMapping = attachedFile
        && !approvedSessionFileName
        ? fileColumnMappings[attachedFile.name]
        : sessionFileContext?.mapping;
      const sourceFileRecipe = attachedFile && !approvedSessionFileName
        ? (
            sessionFileContext?.name === attachedFile.name
              ? sessionFileContext.cleaningRecipe
              : null
          )
        : sessionFileContext?.cleaningRecipe;

      if (
        !skipMappingGate
        && fileForMapping
        && !mappingOverride
        && needsUserApprovedMapping({
          hasAttachedFile: true,
          mapping: sourceFileMapping,
          cleaningRecipe: sourceFileRecipe,
          isAgentClarification: !!clarificationSessionId,
        })
      ) {
        setIsGenerating(true);
        try {
          const result = await parseSampleData(fileForMapping, { includeJsonPaths: true });
          const sample = Array.isArray(result) ? result : result.rows;
          setParsedDataForMapping(sample);
          const paths = Array.isArray(result?.jsonPaths) ? result.jsonPaths : [];
          setJsonPathOptions?.(paths);
          setSelectedJsonPath?.(paths[0] || null);
          setMappingTarget?.({ type: 'file', fileName: fileForMapping.name });
          setShowMappingModal(true);
          return;
        } catch (err) {
          console.error('Mapping error:', err);
          return;
        } finally {
          setIsGenerating(false);
        }
      }

      if (
        !skipMappingGate
        && !mappingOverride
        && needsUserApprovedMapping({
          connectionType: connType,
          mapping: activeMapping,
          cleaningRecipe: connectionForRequest?.cleaningRecipe,
          isAgentClarification: !!clarificationSessionId,
        })
      ) {
        await requestConnectionMapping?.(connectionForRequest);
        return;
      }

      if (user?.id) {
        const quotaCheck = await checkMessageQuota(supabase, user.id);
        if (!quotaCheck.ok) {
          if (quotaCheck.exceeded) {
            openQuotaExceededModal(quotaCheck.exceeded, profileUsage.timezone);
          } else {
            setAiError(
              quotaCheck.error
              || t(
                m,
                'chat.error_profile',
                'Could not verify your plan. Check your account settings or try again.',
              ),
            );
          }
          return;
        }
        applyQuotaCheckResult(quotaCheck);
      }

      setAiError(null);
      setStopTyping(false);
      // Reset wait UI before locking the composer so the spinner is not suppressed
      // by analysisStreamStarted left over from the previous turn.
      setAnalysisStreamStarted(false);
      setIsTyping(true);
      setIsGenerating(true);

      const { data: { session } } = await supabase.auth.getSession();
      if (!session) {
        setAiError(t(m, 'chat.not_signed_in', 'You are not signed in. Please sign in again.'));
        setIsTyping(false);
        setIsGenerating(false);
        navigate(localePath('/login', routing));
        return;
      }

      let convId = options.conversationId || activeConversationId;
      let branchId = options.branchId || activeBranchId || null;
      const displayContent = connId
        ? `${formatConnectionMention(connectionForRequest?.name, sqlTable)} ${userContent}`.trim()
        : userContent;
      // Attachment-only: keep bubble attachment-centric; no fake prose.
      const visibleUserContent = displayContent
        || (setupIntent
          ? (attachedFile?.name || connectionForRequest?.name || '')
          : '');

      const userMsg = {
        role: 'user',
        content: visibleUserContent,
        clientRequestId,
        branchId,
        workflowResolution: options.orchestrationResolution || undefined,
        setupIntent: setupIntent || undefined,
        attachment: contextFileName || undefined,
        attachmentMapping: contextFileName ? activeMapping || null : undefined,
        attachmentCleaningRecipe: contextFileName
          ? effectiveCleaningRecipe || null
          : undefined,
        attachmentCleaningProfile: contextFileName ? cleaningProfile : undefined,
        connectionContext: connId
          ? {
              id: connId,
              name: connectionForRequest?.name,
              type: connType,
              sqlTable: sqlTable || null,
              mapping: activeMapping || null,
              cleaningRecipe: effectiveCleaningRecipe || null,
              cleaningProfile,
            }
          : undefined,
      };
      setMessages((prev) => {
        const withoutFailedAttempt = prev.filter((message) => !(
          message.role === 'ai'
          && message.clientRequestId === clientRequestId
          && (message.failed || message.streaming)
        ));
        if (
          isInlineRetry
          && withoutFailedAttempt.some(
            (message) => message.role === 'user' && message.clientRequestId === clientRequestId,
          )
        ) return withoutFailedAttempt;
        return [...withoutFailedAttempt, userMsg];
      });
      // Promote an attached file to the conversation context immediately.
      // Do not wait for the response/mapping: a refresh or failed stream must
      // still leave the same dataset active for the next question.
      if (attachedFile?.name) {
        setSessionFileContext({
          name: attachedFile.name,
          mapping: activeMapping || undefined,
          cleaningRecipe: effectiveCleaningRecipe || undefined,
          cleaningProfile,
        });
      }
      setSelectedFile(null);
      setInput('');

      const isAnalysis = isAnalysisRequest(userContent, {
        hasAttachedFile: !!attachedFile,
        hasConnection: !!connId,
        isAgentClarification: !!clarificationSessionId,
      });
      setIsAnalysisQuery(isAnalysis);
      setAnalysisContext({
        hasFile: !!(attachedFile || (useSessionFile && sessionFileContext)),
        hasConnection: !!connId,
        connectionType: connType,
        isAnalysis,
        mappedColumns: countMappedColumns(activeMapping),
      });
      setReasoningProgress(createReasoningProgress(userContent));
      webSourcesRef.current = [];
      cleaningReportRef.current = null;
      reasoningTraceRef.current = [];

      if (user && !convId) {
        const { data: newConv, error: convError } = await supabase
          .from('conversations')
          .insert({
            user_id: user.id,
            title: userContent.substring(0, 30) + (userContent.length > 30 ? '...' : ''),
          })
          .select()
          .single();

        if (!convError && newConv) {
          convId = newConv.id;
          setActiveConversationId(convId);
          registerConversation?.(newConv);
          await onConversationCreated?.(convId);
        }
      }

      if (convId && !branchId) {
        const { data: ensuredBranchId, error: branchError } = await supabase.rpc(
          'ensure_chat_branch',
          { p_conversation_id: convId },
        );
        if (branchError && !isBranchingUnavailable(branchError)) {
          console.error('Could not prepare chat branch:', branchError);
          setMessages((current) => [...current.filter((message) => !(
            message.role === 'ai'
            && message.clientRequestId === clientRequestId
            && message.streaming
          )), {
            role: 'ai',
            content: '',
            failed: true,
            clientRequestId,
            branchId,
            retryContext: { requestId: clientRequestId, userContent },
          }]);
          setAiError(getFriendlyChatError(branchError, (key, fallback) => t(m, key, fallback)));
          setIsTyping(false);
          setIsGenerating(false);
          return;
        }
        if (!branchError && ensuredBranchId) {
          branchId = ensuredBranchId;
          setActiveBranchId?.(branchId);
          setMessages((current) => current.map((message) => (
            message.clientRequestId === clientRequestId
              ? { ...message, branchId }
              : message
          )));
        }
      }

      // Persist the optimistic user message before starting the response
      // stream. This makes the first message survive route changes, refreshes,
      // provider failures, and aborted generations.
      let userMessagePersisted = false;
      let savedUserMessageId = null;
      if (user && convId) {
        let existingUserMessage = null;
        if (branchId) {
          const { data: existingRows } = await supabase
            .from('chat_messages')
            .select('id')
            .eq('user_id', user.id)
            .eq('branch_id', branchId)
            .eq('client_request_id', clientRequestId)
            .eq('role', 'user')
            .limit(1);
          existingUserMessage = existingRows?.[0] || null;
        }
        const userInsert = {
          user_id: user.id,
          role: 'user',
          content: userContent,
          conversation_id: convId,
          prompt_tokens: 0,
          completion_tokens: 0,
          total_tokens: 0,
          response_metadata: {
            attachment: userMsg.attachment || null,
            column_mapping: activeMapping || null,
            json_path: selectedJsonPath || null,
            cleaning_recipe: effectiveCleaningRecipe || null,
            cleaning_profile: cleaningProfile,
            connection: userMsg.connectionContext || null,
            orchestration_resolution: options.orchestrationResolution || null,
          },
          ...(branchId ? {
            branch_id: branchId,
            client_request_id: clientRequestId,
          } : {}),
        };
        let { data: savedUserMessage, error: savedUserError } = existingUserMessage
          ? { data: existingUserMessage, error: null }
          : await supabase
          .from('chat_messages')
          .insert(userInsert)
          .select('id')
          .single();
        // A retry can race with the first request after the server committed.
        // Resolve the unique conflict to the existing row instead of inserting
        // the same prompt again after streaming finishes.
        if (savedUserError?.code === '23505' && branchId) {
          const { data: existingRows, error: existingError } = await supabase
            .from('chat_messages')
            .select('id')
            .eq('user_id', user.id)
            .eq('branch_id', branchId)
            .eq('client_request_id', clientRequestId)
            .eq('role', 'user')
            .limit(1);
          savedUserMessage = existingRows?.[0] || null;
          savedUserError = existingError || (savedUserMessage ? null : savedUserError);
        }
        if (!savedUserError) {
          userMessagePersisted = true;
          savedUserMessageId = savedUserMessage?.id ?? null;
          if (savedUserMessageId) {
            setMessages((current) => dedupeConversationMessages(current.map((message) => (
              message.role === 'user' && message.clientRequestId === clientRequestId
                ? { ...message, id: savedUserMessageId, branchId }
                : message
            ))));
          }
        } else {
          console.warn('Could not persist user message before streaming:', savedUserError.message);
        }
      }

      try {
        const chatContents = [];
        requestHistory.forEach((msg) => {
          if (msg.role === 'ai' && chatContents.length === 0) return;
          chatContents.push({
            role: msg.role === 'ai' ? 'assistant' : msg.role,
            content: msg.content,
          });
        });
        if (visibleUserContent || !setupIntent) {
          chatContents.push({ role: 'user', content: visibleUserContent || userContent });
        } else {
          // Internal attachment intent — backend uses setup_intent; avoid empty history noise.
          chatContents.push({
            role: 'user',
            content: '',
          });
        }

        const mappingForBackend = connType === 'api'
          ? mappingOverride || connectionForRequest?.mapping || null
          : resolveColumnMapping(mappingOverride, contextFileName);
        const fileAttachmentName = contextFileName ?? null;
        const trustedVisualizationContext = visualizationContextForRequest(
          visualizationContext,
          {
            attachedFileName: attachedFile?.name || null,
            connectionId: connId,
            ignore: options.ignoreVisualizationContext,
          },
        );

        const backendPayload = {
          messages: chatContents,
          locale: routing.locale,
          tier: plan.name.toLowerCase(),
          temperature: 0.4,
          file_attachment_name: fileAttachmentName,
          json_path: selectedJsonPath || null,
          column_mapping: mappingForBackend,
          user_id: user?.id || session.user.id,
          connection_id: connId,
          connection_type: connType,
          sql_table: sqlTable || null,
          agent_session_id: clarificationSessionId,
          agent_clarification_answer: clarificationSessionId ? userContent : null,
          cleaning_profile: ['standard', 'financial', 'conservative', 'aggressive'].includes(cleaningProfile)
            ? cleaningProfile
            : 'standard',
          cleaning_recipe: effectiveCleaningRecipe,
          data_setup_session_id: effectiveSetupSessionId,
          dataset_version_id: effectiveCleaningRecipe?.dataset_version_id || null,
          conversation_id: convId,
          model_mode: resolveModelModeForPlan(modelMode, plan.name),
          client_request_id: clientRequestId,
          ...(trustedVisualizationContext
            ? { visualization_context: trustedVisualizationContext }
            : {}),
          ...(setupIntent ? { setup_intent: setupIntent } : {}),
          ...(options.orchestrationResolution
            ? { orchestration_resolution: options.orchestrationResolution }
            : {}),
        };

        let streamResult = null;
        const retries = 2;
        let delay = 2000;
        let pendingTokenText = '';
        let tokenFlushScheduled = false;
        let streamUiFinalized = false;
        const flushPendingTokens = () => {
          tokenFlushScheduled = false;
          if (streamUiFinalized || !pendingTokenText) return;
          const content = pendingTokenText;
          pendingTokenText = '';
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.role === 'ai' && last.streaming) {
              return [
                ...prev.slice(0, -1),
                { ...last, content: last.content + content },
              ];
            }
            return [...prev, {
              role: 'ai',
              content,
              streaming: true,
              clientRequestId,
              branchId,
            }];
          });
          // Hide the wait spinner only after visible text is on screen.
          if (content.trim()) {
            setAnalysisStreamStarted(true);
          }
        };

        for (let i = 0; i < retries; i++) {
          try {
            const controller = new AbortController();
            abortControllerRef.current = controller;

            streamResult = await consumeChatStream(
              `${getPublicApiUrl()}/api/v1/chat/stream`,
              {
                authorization: `Bearer ${session.access_token}`,
                body: backendPayload,
              },
              controller.signal,
              {
                onStatus: (stage, detail) => {
                  reasoningTraceRef.current.push({
                    stage,
                    detail: detail || {},
                    at: new Date().toISOString(),
                  });
                  if (stage === 'web_search_done' && Array.isArray(detail?.sources)) {
                    webSourcesRef.current = mergeWebSources(webSourcesRef.current, detail.sources);
                  }
                  if (stage === 'analyzing_done' && Array.isArray(detail?.web_sources)) {
                    webSourcesRef.current = mergeWebSources(webSourcesRef.current, detail.web_sources);
                  }
                  if (stage === 'cleaning_report' && detail?.report) {
                    cleaningReportRef.current = {
                      report: detail.report,
                      dataQualityScore: detail.data_quality_score ?? detail.report.quality_score ?? null,
                    };
                  }
                  setReasoningProgress((prev) => applyStreamStatus(prev, stage, detail));
                },
                onToken: (token) => {
                  pendingTokenText += token;
                  if (!tokenFlushScheduled) {
                    tokenFlushScheduled = true;
                    queueMicrotask(flushPendingTokens);
                  }
                },
              },
            );
            break;
          } catch (fetchErr) {
            if (fetchErr.name === 'AbortError') {
              turnCleanup();
              return;
            }
            const retryable =
              fetchErr.status === 429
              || fetchErr.status === 503
              || fetchErr.status === 504;
            if (retryable && i < retries - 1) {
              console.warn(`Chat stream retry ${i + 1}/${retries}...`);
              setReasoningProgress((prev) =>
                createReasoningProgress(userContent, prev.startedAt ?? Date.now()),
              );
              setMessages((prev) => prev.filter((m) => !m.streaming));
              await new Promise((r) => setTimeout(r, delay));
              delay *= 2;
              continue;
            }
            throw fetchErr;
          }
        }

        streamUiFinalized = true;
        pendingTokenText = '';
        const aiResponseContent = sanitizeMessageContent(streamResult.content);
        const usage = streamResult.usage || {
          prompt_tokens: 0,
          completion_tokens: 0,
          total_tokens: 0,
        };

        const isSetupOrchestration = Boolean(
          streamResult.orchestration
          || streamResult.routing?.path === 'conversational_data_setup',
        );

        if (streamResult.agent_paused && !isSetupOrchestration) {
          setAgentSession({
            sessionId: streamResult.agent_session_id,
            question: aiResponseContent,
            reason: streamResult.agent_reason,
          });
          setReasoningProgress((prev) => ({
            ...applyStreamStatus(prev, 'agent_clarify', {
              hint: aiResponseContent.slice(0, 80),
              action: 'waiting',
            }),
            stage: 'agent_clarify',
          }));
          setMessages((prev) => [
            ...prev.filter((m) => !m.streaming),
            {
              role: 'ai',
              content: aiResponseContent,
              agentClarify: true,
              agentReason: streamResult.agent_reason,
            },
          ]);
          setIsTyping(false);
          turnCleanup();
          setAnalysisStreamStarted(false);
          return;
        }

        if (!isSetupOrchestration) {
          setAgentSession(null);
        }

        if (fileAttachmentName && mappingForBackend) {
          setFileColumnMappings((prev) => ({ ...prev, [fileAttachmentName]: mappingForBackend }));
          setSessionFileContext({
            name: fileAttachmentName,
            mapping: mappingForBackend,
            cleaningRecipe: effectiveCleaningRecipe || undefined,
            cleaningProfile,
          });
          setConfirmedMapping(mappingForBackend);
        }

        const finalWebSources = [...webSourcesRef.current];
        const finalReasoningTrace = [...reasoningTraceRef.current];
        setReasoningProgress((prev) => ({
          ...applyStreamStatus(prev, 'done', {}),
          stage: 'done',
        }));
        setMessages((prev) => [
          ...prev.filter((m) => !m.streaming),
          {
            role: 'ai',
            content: aiResponseContent,
            clientRequestId,
            branchId,
            skipAnimate: true,
            ...(finalWebSources.length
              ? { webSources: finalWebSources }
              : {}),
            ...(cleaningReportRef.current
              ? { cleaningReport: cleaningReportRef.current }
              : {}),
            ...(streamResult.verification
              ? { verification: streamResult.verification }
              : {}),
            ...(streamResult.routing ? { routing: streamResult.routing } : {}),
            ...(streamResult.response_mode ? { responseMode: streamResult.response_mode } : {}),
            ...(streamResult.model_used ? { modelUsed: streamResult.model_used } : {}),
            ...(streamResult.search_queries?.length
              ? { searchQueries: streamResult.search_queries }
              : {}),
            ...(streamResult.analysis_audit
              ? { analysisAudit: streamResult.analysis_audit }
              : {}),
            ...(streamResult.tool_execution
              ? { toolExecution: streamResult.tool_execution }
              : {}),
            ...(streamResult.orchestration
              ? { orchestration: streamResult.orchestration }
              : {}),
            ...(isSetupOrchestration && streamResult.agent_paused
              ? { setupAwaitingUser: true }
              : {}),
            reasoningTrace: finalReasoningTrace,
          },
        ]);
        webSourcesRef.current = [];
        cleaningReportRef.current = null;
        reasoningTraceRef.current = [];

        // SSE done → unlock composer immediately; post-stream work must not hold the lock.
        turnCleanup();

        if (streamResult.orchestration && typeof onOrchestrationUpdate === 'function') {
          void Promise.resolve(onOrchestrationUpdate(streamResult.orchestration)).catch(
            (updateErr) => console.warn('Orchestration update handler failed:', updateErr),
          );
        }

        if (
          streamResult.orchestration?.ready_for_analysis
          && typeof onOrchestrationReady === 'function'
        ) {
          void Promise.resolve(onOrchestrationReady(streamResult.orchestration)).catch(
            (readyErr) => console.warn('Orchestration ready handler failed:', readyErr),
          );
        }

        if (user && convId) {
          if (savedUserMessageId) {
            await supabase
              .from('chat_messages')
              .update({
                prompt_tokens: usage.prompt_tokens,
                total_tokens: usage.prompt_tokens,
              })
              .eq('id', savedUserMessageId);
          } else if (!userMessagePersisted) {
            await supabase.from('chat_messages').insert({
              user_id: user.id,
              role: 'user',
              content: userContent,
              conversation_id: convId,
              prompt_tokens: usage.prompt_tokens,
              completion_tokens: 0,
              total_tokens: usage.prompt_tokens,
              response_metadata: {
                attachment: userMsg.attachment || null,
                column_mapping: mappingForBackend || null,
                json_path: selectedJsonPath || null,
                cleaning_recipe: effectiveCleaningRecipe || null,
                cleaning_profile: cleaningProfile,
                connection: userMsg.connectionContext || null,
                orchestration_resolution: options.orchestrationResolution || null,
              },
              ...(branchId ? {
                branch_id: branchId,
                client_request_id: clientRequestId,
              } : {}),
            });
          }
          let existingAiMessage = null;
          if (branchId) {
            const { data: existingRows } = await supabase
              .from('chat_messages')
              .select('id')
              .eq('user_id', user.id)
              .eq('branch_id', branchId)
              .eq('client_request_id', clientRequestId)
              .eq('role', 'ai')
              .limit(1);
            existingAiMessage = existingRows?.[0] || null;
          }
          const aiInsert = {
            user_id: user.id,
            role: 'ai',
            content: aiResponseContent,
            conversation_id: convId,
            prompt_tokens: 0,
            completion_tokens: usage.completion_tokens,
            total_tokens: usage.completion_tokens,
            web_sources: finalWebSources,
            verification: streamResult.verification,
            model_used: streamResult.model_used,
            response_metadata: {
              routing: streamResult.routing,
              response_mode: streamResult.response_mode,
              search_queries: streamResult.search_queries,
              latency_ms: streamResult.latency_ms,
              finish_reason: streamResult.finish_reason,
              generation_continuations: streamResult.generation_continuations,
              generation_truncated: streamResult.generation_truncated,
              reasoning_trace: finalReasoningTrace,
              analysis_audit: streamResult.analysis_audit,
              tool_execution: streamResult.tool_execution,
              ...(streamResult.orchestration
                ? { orchestration: streamResult.orchestration }
                : {}),
              ...(isSetupOrchestration && streamResult.agent_paused
                ? { setup_awaiting_user: true }
                : {}),
            },
            ...(branchId ? {
              branch_id: branchId,
              client_request_id: clientRequestId,
            } : {}),
          };
          let { data: savedAiMessage, error: savedAiError } = existingAiMessage
            ? { data: existingAiMessage, error: null }
            : await supabase
            .from('chat_messages')
            .insert(aiInsert)
            .select('id')
            .single();
          if (savedAiError?.code === '23505' && branchId) {
            const { data: existingRows, error: existingError } = await supabase
              .from('chat_messages')
              .select('id')
              .eq('user_id', user.id)
              .eq('branch_id', branchId)
              .eq('client_request_id', clientRequestId)
              .eq('role', 'ai')
              .limit(1);
            savedAiMessage = existingRows?.[0] || null;
            savedAiError = existingError || (savedAiMessage ? null : savedAiError);
          }
          if (!savedAiError && savedAiMessage?.id) {
            setMessages((prev) => dedupeConversationMessages(prev.map((message, index) => (
              index === prev.length - 1 && message.role === 'ai'
                ? { ...message, id: savedAiMessage.id }
                : message
            ))));
          } else if (savedAiError) {
            console.error('Could not persist AI response:', savedAiError.message);
          }
          await syncAfterMessage(user.id);
        }

        if (isAnalysis) {
          setReasoningProgress(INITIAL_REASONING_PROGRESS);
        }
      } catch (err) {
        console.error('Error calling backend chat API:', err);
        setMessages((prev) => {
          const next = prev.filter((message) => !(
            message.role === 'ai'
            && message.clientRequestId === clientRequestId
            && message.streaming
          ));
          return [...next, {
            role: 'ai',
            content: '',
            failed: true,
            clientRequestId,
            branchId,
            retryContext: { requestId: clientRequestId, userContent },
          }];
        });
        turnCleanup();
        if (err?.status === 403 && err?.quotaDetail?.error === 'Quota Exceeded') {
          openQuotaExceededModal(err.quotaDetail, profileUsage.timezone);
        } else {
          setAiError(getFriendlyChatError(err, (key, fallback) => t(m, key, fallback)));
        }
        setReasoningProgress(INITIAL_REASONING_PROGRESS);
      }
    },
    [
      input,
      selectedFile,
      sessionFileContext,
      agentSession,
      dbConnections,
      apiConnections,
      activeConnection,
      setActiveConnection,
      resolveColumnMapping,
      fileColumnMappings,
      parseSampleData,
      requestConnectionMapping,
      setParsedDataForMapping,
      setJsonPathOptions,
      setSelectedJsonPath,
      setShowMappingModal,
      setMappingTarget,
      user,
      openQuotaExceededModal,
      applyQuotaCheckResult,
      profileUsage.timezone,
      setAiError,
      setStopTyping,
      setIsGenerating,
      m,
      navigate,
      routing,
      activeConversationId,
      activeBranchId,
      setActiveBranchId,
      messages,
      setMessages,
      setIsTyping,
      setSelectedFile,
      setInput,
      setIsAnalysisQuery,
      setAnalysisStreamStarted,
      setAnalysisContext,
      setReasoningProgress,
      setActiveConversationId,
      registerConversation,
      plan.name,
      setAgentSession,
      setFileColumnMappings,
      setSessionFileContext,
      setConfirmedMapping,
      syncAfterMessage,
      onConversationCreated,
      cleaningProfile,
      cleaningRecipe,
      selectedJsonPath,
      modelMode,
      dataSetupSessionId,
      onOrchestrationReady,
      onOrchestrationUpdate,
      visualizationContext,
      turnCleanup,
    ],
  );

  const retryFailedMessage = useCallback((failedMessage) => {
    const requestId = failedMessage?.clientRequestId;
    const userContent = failedMessage?.retryContext?.userContent;
    if (!requestId || !userContent) return;
    return sendMessage(null, null, null, {
      contentOverride: userContent,
      requestId,
      retry: true,
      conversationId: activeConversationId,
      branchId: failedMessage.branchId || activeBranchId,
      historyMessages: retryHistory(messages, requestId),
    });
  }, [activeBranchId, activeConversationId, messages, sendMessage]);

  return { sendMessage, stopGeneration, retryFailedMessage, abortControllerRef };
}
