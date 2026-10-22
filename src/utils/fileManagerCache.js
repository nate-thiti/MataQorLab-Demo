export const FILE_MANAGER_CACHE_TTL_MS = 60 * 1000;

export function createFileManagerCache({ ttlMs = FILE_MANAGER_CACHE_TTL_MS, now = () => Date.now() } = {}) {
  const users = new Map();
  let authUser = null;

  const userEntry = (userId) => {
    if (!userId) return null;
    if (!users.has(userId)) {
      users.set(userId, {
        files: null,
        plan: null,
        dashboard: null,
        paymentHistory: null,
        settingsProfile: null,
        chatConversations: null,
        chatMessages: new Map(),
        databaseConnections: null,
        apiConnections: null,
      });
    }
    return users.get(userId);
  };

  const isFresh = (entry) => Boolean(entry?.lastFetchedAt && now() - entry.lastFetchedAt < ttlMs);

  const setSection = (userId, section, value) => {
    const entry = userEntry(userId);
    if (!entry) return null;
    const next = { ...value, lastFetchedAt: now() };
    entry[section] = next;
    return next;
  };

  const mergeSection = (userId, section, value) => {
    const entry = userEntry(userId);
    if (!entry) return null;
    const current = entry[section] || {};
    const next = { ...current, ...value, lastFetchedAt: now() };
    entry[section] = next;
    return next;
  };

  const getSection = (userId, section) => {
    const entry = userEntry(userId);
    const cached = entry?.[section] || null;
    return cached ? { ...cached, isFresh: isFresh(cached) } : null;
  };

  return {
    getAuthUser() {
      return authUser ? { ...authUser, isFresh: isFresh(authUser) } : null;
    },
    setAuthUser(user) {
      authUser = user ? { user, lastFetchedAt: now() } : null;
      return authUser;
    },
    clearAuthUser() {
      authUser = null;
    },
    getFiles(userId) {
      return getSection(userId, 'files');
    },
    setFiles(userId, { files, totalSize }) {
      return setSection(userId, 'files', { files: files || [], totalSize: totalSize || 0 });
    },
    getPlan(userId) {
      return getSection(userId, 'plan');
    },
    setPlan(userId, { plan }) {
      return setSection(userId, 'plan', { plan });
    },
    getDashboard(userId) {
      return getSection(userId, 'dashboard');
    },
    setDashboard(userId, value) {
      return mergeSection(userId, 'dashboard', value || {});
    },
    getPaymentHistory(userId) {
      return getSection(userId, 'paymentHistory');
    },
    setPaymentHistory(userId, value) {
      return mergeSection(userId, 'paymentHistory', value || {});
    },
    getSettingsProfile(userId) {
      return getSection(userId, 'settingsProfile');
    },
    setSettingsProfile(userId, value) {
      return mergeSection(userId, 'settingsProfile', value || {});
    },
    getChatConversations(userId) {
      return getSection(userId, 'chatConversations');
    },
    setChatConversations(userId, { conversations, hasMore = false }) {
      return setSection(userId, 'chatConversations', {
        conversations: conversations || [],
        hasMore,
      });
    },
    getChatMessages(userId, conversationId) {
      const entry = userEntry(userId);
      const cached = entry?.chatMessages?.get(conversationId) || null;
      return cached ? { ...cached, isFresh: isFresh(cached) } : null;
    },
    setChatMessages(userId, conversationId, { messages }) {
      const entry = userEntry(userId);
      if (!entry || !conversationId) return null;
      const next = { messages: messages || [], lastFetchedAt: now() };
      entry.chatMessages.set(conversationId, next);
      return next;
    },
    clearChatMessage(userId, conversationId) {
      const entry = userEntry(userId);
      entry?.chatMessages?.delete(conversationId);
    },
    getDatabaseConnections(userId) {
      return getSection(userId, 'databaseConnections');
    },
    setDatabaseConnections(userId, { connections, healthStatus }) {
      return setSection(userId, 'databaseConnections', {
        connections: connections || [],
        healthStatus: healthStatus || {},
      });
    },
    getApiConnections(userId) {
      return getSection(userId, 'apiConnections');
    },
    setApiConnections(userId, { connections, healthStatus }) {
      return setSection(userId, 'apiConnections', {
        connections: connections || [],
        healthStatus: healthStatus || {},
      });
    },
    clearUser(userId) {
      if (userId) users.delete(userId);
    },
    clearAll() {
      users.clear();
      authUser = null;
    },
  };
}
