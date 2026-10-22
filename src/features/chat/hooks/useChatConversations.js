import { useState, useCallback, useMemo, useRef } from 'react';
import { supabase } from '../../../utils/supabaseClient.js';
import { sanitizeChatMessage } from '../messageContent.js';
import {
  clearConversationSnapshot,
  loadConversationSnapshot,
  mergeConversationMessages,
} from '../chatSessionStorage.js';
import { branchCacheKey, isBranchingUnavailable } from '../chatBranches.js';
import { upsertConversationList } from '../chatConversationList.js';

const CONVERSATION_PAGE_SIZE = 50;

/**
 * Conversation list, pinning, load/delete/rename for the chat sidebar.
 */
export function useChatConversations({
  userId,
  dataCache,
  isEn,
  setAiError,
  stopGeneration,
  setMessages,
  setSelectedFile,
  setInput,
  setConfirmedMapping,
  setFileColumnMappings,
  setSessionFileContext,
  setAgentSession,
  onWorkspaceReset = null,
}) {
  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [branches, setBranches] = useState([]);
  const [activeBranchId, setActiveBranchId] = useState(null);
  const [hasMoreConversations, setHasMoreConversations] = useState(false);
  const [loadingMoreConversations, setLoadingMoreConversations] = useState(false);
  const loadRequestRef = useRef(0);
  const [pinnedConvIds, setPinnedConvIds] = useState(() => {
    try {
      const saved = localStorage.getItem('pinned_conversations');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [deleteModal, setDeleteConfirm] = useState({ show: false, convId: null, title: '' });

  const applyConversations = useCallback((userId, rows) => {
    const nextRows = rows || [];
    setConversations(nextRows);
    dataCache?.setChatConversations(userId, { conversations: nextRows });

    const dbPinnedIds = nextRows.filter((c) => c.is_pinned).map((c) => c.id);
    if (dbPinnedIds.length > 0) {
      setPinnedConvIds((prev) => {
        const merged = Array.from(new Set([...prev, ...dbPinnedIds]));
        localStorage.setItem('pinned_conversations', JSON.stringify(merged));
        return merged;
      });
    }
  }, [dataCache]);

  const fetchConversations = useCallback(async (userId) => {
    const cached = dataCache?.getChatConversations(userId);
    if (cached) {
      applyConversations(userId, cached.conversations || []);
      setHasMoreConversations(Boolean(cached.hasMore));
      if (cached.isFresh) return;
    }

    const { data, error } = await supabase
      .from('conversations')
      .select('*')
      .eq('user_id', userId)
      .order('created_at', { ascending: false })
      .range(0, CONVERSATION_PAGE_SIZE);

    if (!error && data) {
      const hasMore = data.length > CONVERSATION_PAGE_SIZE;
      applyConversations(userId, data.slice(0, CONVERSATION_PAGE_SIZE));
      setHasMoreConversations(hasMore);
      dataCache?.setChatConversations(userId, {
        conversations: data.slice(0, CONVERSATION_PAGE_SIZE),
        hasMore,
      });
    }
  }, [applyConversations, dataCache]);

  const registerConversation = useCallback((conversation) => {
    if (!conversation?.id) return;
    setConversations((current) => {
      const next = upsertConversationList(current, conversation, CONVERSATION_PAGE_SIZE);
      if (userId) {
        dataCache?.setChatConversations(userId, {
          conversations: next,
          hasMore: hasMoreConversations,
        });
      }
      return next;
    });
  }, [dataCache, hasMoreConversations, userId]);

  const loadMoreConversations = useCallback(async () => {
    if (!userId || !hasMoreConversations || loadingMoreConversations) return;
    setLoadingMoreConversations(true);
    try {
      const offset = conversations.length;
      const { data, error } = await supabase
        .from('conversations')
        .select('*')
        .eq('user_id', userId)
        .order('created_at', { ascending: false })
        .range(offset, offset + CONVERSATION_PAGE_SIZE);
      if (error) throw error;
      const rows = data || [];
      const hasMore = rows.length > CONVERSATION_PAGE_SIZE;
      const page = rows.slice(0, CONVERSATION_PAGE_SIZE);
      setConversations((current) => {
        const known = new Set(current.map((conversation) => conversation.id));
        const merged = [...current, ...page.filter((conversation) => !known.has(conversation.id))];
        dataCache?.setChatConversations(userId, { conversations: merged, hasMore });
        return merged;
      });
      setHasMoreConversations(hasMore);
    } catch (error) {
      console.error('Error loading more conversations:', error);
    } finally {
      setLoadingMoreConversations(false);
    }
  }, [
    conversations.length,
    dataCache,
    hasMoreConversations,
    loadingMoreConversations,
    userId,
  ]);

  const togglePinConversation = useCallback((convId) => {
    setPinnedConvIds((prev) => {
      const isPinned = prev.includes(convId);
      const updated = isPinned
        ? prev.filter((id) => id !== convId)
        : [...prev, convId];
      localStorage.setItem('pinned_conversations', JSON.stringify(updated));

      supabase
        .from('conversations')
        .update({ is_pinned: !isPinned })
        .eq('id', convId)
        .then(({ error }) => {
          if (error) {
            console.warn('is_pinned column may not exist in database, fallback to localStorage');
          }
        });
      return updated;
    });
  }, []);

  const renameConversation = useCallback(async (convId, newTitle) => {
    if (!newTitle.trim()) return;

    const { error } = await supabase
      .from('conversations')
      .update({ title: newTitle.trim() })
      .eq('id', convId);

    if (error) {
      console.error('Error renaming conversation:', error);
      setAiError(
        isEn
          ? `Failed to rename: ${error.message}`
          : `เปลี่ยนชื่อไม่สำเร็จ: ${error.message}`,
      );
    } else {
      setConversations((prev) => {
        const next = prev.map((c) => (c.id === convId ? { ...c, title: newTitle.trim() } : c));
        if (userId) {
          dataCache?.setChatConversations(userId, {
            conversations: next,
            hasMore: hasMoreConversations,
          });
        }
        return next;
      });
    }
  }, [dataCache, hasMoreConversations, isEn, setAiError, userId]);

  const sortedConversations = useMemo(() => {
    return [...conversations].sort((a, b) => {
      const aPinned = pinnedConvIds.includes(a.id) || a.is_pinned;
      const bPinned = pinnedConvIds.includes(b.id) || b.is_pinned;
      if (aPinned && !bPinned) return -1;
      if (!aPinned && bPinned) return 1;
      return new Date(b.created_at) - new Date(a.created_at);
    });
  }, [conversations, pinnedConvIds]);

  const loadBranchState = useCallback(async (convId, preferredBranchId = null) => {
    if (preferredBranchId) {
      const { error: activateError } = await supabase.rpc('activate_chat_branch', {
        p_conversation_id: convId,
        p_branch_id: preferredBranchId,
      });
      if (activateError && !isBranchingUnavailable(activateError)) throw activateError;
    }

    const [conversationResult, branchResult] = await Promise.all([
      supabase
        .from('conversations')
        .select('active_branch_id')
        .eq('id', convId)
        .maybeSingle(),
      supabase
        .from('chat_branches')
        .select('*')
        .eq('conversation_id', convId)
        .order('branch_index', { ascending: true }),
    ]);

    if (conversationResult.error || branchResult.error) {
      const unsupported = isBranchingUnavailable(conversationResult.error)
        || isBranchingUnavailable(branchResult.error);
      if (!unsupported) throw conversationResult.error || branchResult.error;
      setBranches([]);
      setActiveBranchId(null);
      return null;
    }

    const nextBranches = branchResult.data || [];
    const requestedBranch = preferredBranchId
      && nextBranches.some((branch) => branch.id === preferredBranchId)
      ? preferredBranchId
      : null;
    const nextBranchId = requestedBranch
      || conversationResult.data?.active_branch_id
      || nextBranches.find((branch) => branch.is_root)?.id
      || nextBranches[0]?.id
      || null;
    setBranches(nextBranches);
    setActiveBranchId(nextBranchId);
    return nextBranchId;
  }, []);

  const loadConversation = useCallback(
    async (convId, onLoaded, preferredBranchId = null) => {
      const requestId = loadRequestRef.current + 1;
      loadRequestRef.current = requestId;
      stopGeneration();
      setActiveConversationId(convId);
      setSelectedFile(null);
      setInput('');
      setConfirmedMapping(null);
      setFileColumnMappings({});
      setSessionFileContext(null);
      setAgentSession(null);

      let branchId = null;
      try {
        branchId = await loadBranchState(convId, preferredBranchId);
      } catch (error) {
        console.error('Error loading conversation branches:', error);
        setAiError(isEn ? 'Could not load this chat version.' : 'โหลดเวอร์ชันของแชทไม่สำเร็จ');
        return [];
      }

      const cacheKey = branchCacheKey(convId, branchId);

      const localMessages = loadConversationSnapshot(userId, convId, branchId).map(sanitizeChatMessage);
      if (localMessages.length > 0) {
        setMessages(localMessages);
        onLoaded?.(localMessages);
      }

      const cached = dataCache?.getChatMessages(userId, cacheKey);
      if (cached) {
        const cachedMessages = mergeConversationMessages(
          cached.messages || [],
          localMessages,
        );
        setMessages(cachedMessages);
        onLoaded?.(cachedMessages);
        if (cached.isFresh) return cachedMessages;
      } else if (localMessages.length === 0) {
        setMessages([]);
      }

      let messageQuery = supabase
        .from('chat_messages')
        .select('*')
        .eq('conversation_id', convId);
      if (branchId) messageQuery = messageQuery.eq('branch_id', branchId);
      const { data, error } = await messageQuery
        .order('created_at', { ascending: true })
        .order('role', { ascending: false });

      if (requestId !== loadRequestRef.current) return [];

      if (!error && data) {
        const serverMessages = data.length > 0 ? data.map(sanitizeChatMessage) : [];
        const loaded = mergeConversationMessages(serverMessages, localMessages);
        setMessages(loaded);
        dataCache?.setChatMessages(userId, cacheKey, { messages: loaded });
        onLoaded?.(loaded);
        return loaded;
      } else if (localMessages.length === 0) {
        onLoaded?.([]);
        return [];
      }
      return localMessages;
    },
    [
      dataCache,
      stopGeneration,
      setMessages,
      setSelectedFile,
      setInput,
      setConfirmedMapping,
      setFileColumnMappings,
      setSessionFileContext,
      setAgentSession,
      loadBranchState,
      setAiError,
      isEn,
      userId,
    ],
  );

  const switchConversationBranch = useCallback(async (branchId, onLoaded) => {
    if (!activeConversationId || !branchId || branchId === activeBranchId) return null;
    return loadConversation(activeConversationId, onLoaded, branchId);
  }, [activeBranchId, activeConversationId, loadConversation]);

  const forkConversationBranch = useCallback(async ({ forkMessageId, title, onLoaded }) => {
    if (!activeConversationId || !activeBranchId || !forkMessageId) {
      throw new Error('Conversation branch context is incomplete');
    }
    const { data, error } = await supabase.rpc('fork_chat_branch', {
      p_conversation_id: activeConversationId,
      p_source_branch_id: activeBranchId,
      p_fork_message_id: forkMessageId,
      p_title: title || null,
    });
    if (error) throw error;
    const branchId = data;
    const loaded = await loadConversation(activeConversationId, onLoaded, branchId);
    return { branchId, messages: loaded || [] };
  }, [activeBranchId, activeConversationId, loadConversation]);

  const startNewChat = useCallback(() => {
    loadRequestRef.current += 1;
    stopGeneration();
    setActiveConversationId(null);
    setActiveBranchId(null);
    setBranches([]);
    setMessages([]);
    setSelectedFile(null);
    setInput('');
    setConfirmedMapping(null);
    setFileColumnMappings({});
    setSessionFileContext(null);
    setAgentSession(null);
    onWorkspaceReset?.();
  }, [
    stopGeneration,
    setMessages,
    setSelectedFile,
    setInput,
    setConfirmedMapping,
    setFileColumnMappings,
    setSessionFileContext,
    setAgentSession,
    onWorkspaceReset,
  ]);

  const triggerDeleteConversation = useCallback((e, convId, title) => {
    e.stopPropagation();
    setDeleteConfirm({ show: true, convId, title });
  }, []);

  const confirmDeleteConversation = useCallback(async () => {
    const { convId } = deleteModal;
    const { error } = await supabase.from('conversations').delete().eq('id', convId);

    if (error) {
      console.error('Error deleting conversation:', error);
      setAiError(
        isEn
          ? `Failed to delete chat: ${error.message}`
          : `ลบไม่สำเร็จ: ${error.message}`,
      );
    } else {
      setConversations((prev) => {
        const next = prev.filter((c) => c.id !== convId);
        if (userId) {
          dataCache?.setChatConversations(userId, {
            conversations: next,
            hasMore: hasMoreConversations,
          });
        }
        return next;
      });
      if (userId) dataCache?.clearChatMessage(userId, convId);
      if (userId) clearConversationSnapshot(userId, convId);
      if (activeConversationId === convId) {
        startNewChat();
      }
    }
    setDeleteConfirm({ show: false, convId: null, title: '' });
  }, [
    activeConversationId,
    dataCache,
    deleteModal,
    hasMoreConversations,
    isEn,
    setAiError,
    startNewChat,
    userId,
  ]);

  return {
    conversations,
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
  };
}
