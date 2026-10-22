/** Persist chat session context (active @connection, file) across page navigations. */

const KEY_PREFIX = 'mql_chat_session';
const CONVERSATION_KEY_PREFIX = 'mql_chat_conversation';

function storageKey(userId) {
  return `${KEY_PREFIX}:${userId}`;
}

function conversationStorageKey(userId, conversationId, branchId = null) {
  const base = `${CONVERSATION_KEY_PREFIX}:${userId}:${conversationId}`;
  return branchId ? `${base}:branch:${branchId}` : base;
}

function readStorage(key) {
  for (const storage of [globalThis.localStorage, globalThis.sessionStorage]) {
    try {
      const raw = storage?.getItem(key);
      if (raw) return raw;
    } catch {
      // Try the other browser storage.
    }
  }
  return null;
}

function writeStorage(key, value) {
  for (const storage of [globalThis.localStorage, globalThis.sessionStorage]) {
    try {
      storage?.setItem(key, value);
    } catch {
      // A disabled/quota-limited storage must not break chat.
    }
  }
}

function removeStorage(key) {
  for (const storage of [globalThis.localStorage, globalThis.sessionStorage]) {
    try {
      storage?.removeItem(key);
    } catch {
      // A disabled storage must not break chat.
    }
  }
}

export function loadChatSession(userId) {
  if (!userId) return null;
  try {
    const raw = readStorage(storageKey(userId));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function saveChatSession(userId, patch) {
  if (!userId) return;
  try {
    const prev = loadChatSession(userId) || {};
    writeStorage(
      storageKey(userId),
      JSON.stringify({ ...prev, ...patch }),
    );
  } catch {
    // ignore quota / private mode
  }
}

export function clearChatSession(userId) {
  if (!userId) return;
  removeStorage(storageKey(userId));
}

export function clearChatSessionConnection(userId) {
  if (!userId) return;
  const prev = loadChatSession(userId);
  if (!prev) return;
  const next = { ...prev };
  delete next.connection;
  try {
    if (Object.keys(next).length === 0) {
      removeStorage(storageKey(userId));
    } else {
      writeStorage(storageKey(userId), JSON.stringify(next));
    }
  } catch {
    // ignore
  }
}

export function clearChatSessionFile(userId) {
  if (!userId) return;
  const prev = loadChatSession(userId);
  if (!prev) return;
  const next = { ...prev };
  delete next.file;
  try {
    if (Object.keys(next).length === 0) {
      removeStorage(storageKey(userId));
    } else {
      writeStorage(storageKey(userId), JSON.stringify(next));
    }
  } catch {
    // ignore
  }
}

/**
 * Keep a lightweight local copy of the visible transcript. Supabase remains
 * the source of truth; this snapshot closes the gap where a refresh happens
 * while the final streamed answer is still being persisted.
 */
export function saveConversationSnapshot(userId, conversationId, messages, branchId = null) {
  if (!userId || !conversationId || !Array.isArray(messages) || messages.length === 0) return;
  const snapshot = dedupeConversationMessages(messages).slice(-100).map((message) => {
    const next = { ...message };
    delete next.streaming;
    delete next.retryContext;
    return next;
  });
  try {
    writeStorage(
      conversationStorageKey(userId, conversationId, branchId),
      JSON.stringify({ messages: snapshot, savedAt: Date.now() }),
    );
  } catch {
    // Storage quota/private mode must not break chat.
  }
}

export function loadConversationSnapshot(userId, conversationId, branchId = null) {
  if (!userId || !conversationId) return [];
  try {
    const raw = readStorage(conversationStorageKey(userId, conversationId, branchId));
    const parsed = raw ? JSON.parse(raw) : null;
    return Array.isArray(parsed?.messages) ? dedupeConversationMessages(parsed.messages) : [];
  } catch {
    return [];
  }
}

export function clearConversationSnapshot(userId, conversationId, branchId = null) {
  if (!userId || !conversationId) return;
  removeStorage(conversationStorageKey(userId, conversationId, branchId));
}

export function dedupeConversationMessages(messages = []) {
  if (!Array.isArray(messages) || messages.length < 2) return Array.isArray(messages) ? messages : [];
  const result = [];
  const indexById = new Map();
  messages.forEach((message) => {
    const id = message?.id ? String(message.id) : null;
    if (!id || !indexById.has(id)) {
      if (id) indexById.set(id, result.length);
      result.push(message);
      return;
    }
    const existingIndex = indexById.get(id);
    const existing = result[existingIndex];
    const merged = { ...existing, ...message };
    ['attachment', 'orchestration', 'workflowResolution'].forEach((field) => {
      if (merged[field] == null && existing[field] != null) merged[field] = existing[field];
    });
    result[existingIndex] = merged;
  });
  return result;
}

export function mergeConversationMessages(serverMessages = [], localMessages = []) {
  const uniqueServerMessages = dedupeConversationMessages(serverMessages);
  const uniqueLocalMessages = dedupeConversationMessages(localMessages);
  if (!uniqueLocalMessages.length) return uniqueServerMessages;
  if (!uniqueServerMessages.length) return uniqueLocalMessages;

  const serverBySignature = new Map();
  uniqueServerMessages.forEach((message) => {
    const signature = `${message.role}:${message.content || ''}`;
    const matches = serverBySignature.get(signature) || [];
    matches.push(message);
    serverBySignature.set(signature, matches);
  });

  const hydratedLocal = uniqueLocalMessages.map((message) => {
    const signature = `${message.role}:${message.content || ''}`;
    const match = serverBySignature.get(signature)?.shift();
    return match ? { ...message, ...match, attachment: message.attachment || match.attachment } : message;
  });

  // The snapshot represents the exact UI order and may contain the newest
  // streamed answer that has not reached Supabase yet.
  if (hydratedLocal.length >= uniqueServerMessages.length) {
    return dedupeConversationMessages(hydratedLocal);
  }
  return uniqueServerMessages;
}

/**
 * Restore file context from the latest user message with an attachment.
 */
export function fileFromMessages(messages) {
  if (!messages?.length) return null;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const msg = messages[i];
    if (msg.role === 'user' && msg.attachment) {
      return {
        name: msg.attachment,
        mapping: msg.attachmentMapping || null,
        cleaningRecipe: msg.attachmentCleaningRecipe || null,
        cleaningProfile: msg.attachmentCleaningProfile || null,
        mode: 'session',
      };
    }
  }
  return null;
}

/**
 * @param {{ name: string, mapping?: object|null, mode?: 'pending'|'session' }} savedFile
 */
export function resolveStoredFile(savedFile) {
  if (!savedFile?.name) return null;
  return {
    name: savedFile.name,
    mapping: savedFile.mapping || null,
    cleaningRecipe: savedFile.cleaningRecipe || null,
    cleaningProfile: savedFile.cleaningProfile || null,
    mode: savedFile.mode === 'pending' ? 'pending' : 'session',
  };
}

/**
 * @param {Array<{ id: string, name: string, type: 'sql'|'api' }>} connections
 */
export function resolveStoredConnection(savedConnection, connections) {
  if (!savedConnection?.id || !connections?.length) return null;
  const match = connections.find((c) => c.id === savedConnection.id);
  if (!match) return null;
  return {
    ...match,
    type: savedConnection.type || match.type,
    sqlTable: savedConnection.sqlTable || undefined,
    mapping: savedConnection.mapping || undefined,
    cleaningRecipe: savedConnection.cleaningRecipe || undefined,
    cleaningProfile: savedConnection.cleaningProfile || undefined,
  };
}

/**
 * Restore @connection from the latest user message that mentions one.
 */
export function connectionFromMessages(messages, connections) {
  if (!messages?.length || !connections?.length) return null;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const msg = messages[i];
    if (msg.role === 'user' && msg.connectionContext?.id) {
      const match = connections.find((conn) => conn.id === msg.connectionContext.id);
      if (match) {
        return {
          ...match,
          type: msg.connectionContext.type || match.type,
          sqlTable: msg.connectionContext.sqlTable || undefined,
          mapping: msg.connectionContext.mapping || undefined,
          cleaningRecipe: msg.connectionContext.cleaningRecipe || undefined,
          cleaningProfile: msg.connectionContext.cleaningProfile || undefined,
        };
      }
    }
    if (msg.role !== 'user' || !msg.content?.includes('@')) continue;
    const sorted = [...connections].sort((a, b) => b.name.length - a.name.length);
    for (const conn of sorted) {
      const prefix = `@${conn.name}`;
      if (!msg.content.includes(prefix)) continue;
      let sqlTable = null;
      const after = msg.content.slice(msg.content.indexOf(prefix) + prefix.length);
      if (after.startsWith('-')) {
        const match = after.slice(1).match(/^([a-zA-Z0-9_.]+)/);
        if (match) sqlTable = match[1];
      }
      return { ...conn, sqlTable: sqlTable || undefined };
    }
  }
  return null;
}
