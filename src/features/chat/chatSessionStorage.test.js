import { describe, it, expect, beforeEach } from 'vitest';
import {
  saveChatSession,
  loadChatSession,
  clearChatSession,
  clearChatSessionFile,
  resolveStoredConnection,
  connectionFromMessages,
  fileFromMessages,
  resolveStoredFile,
  saveConversationSnapshot,
  loadConversationSnapshot,
  clearConversationSnapshot,
  dedupeConversationMessages,
  mergeConversationMessages,
} from './chatSessionStorage.js';

function createSessionStorageMock() {
  const store = new Map();
  return {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => {
      store.set(key, String(value));
    },
    removeItem: (key) => {
      store.delete(key);
    },
    clear: () => {
      store.clear();
    },
  };
}

describe('chatSessionStorage', () => {
  beforeEach(() => {
    globalThis.sessionStorage = createSessionStorageMock();
    globalThis.localStorage = createSessionStorageMock();
  });

  it('persists and loads connection context', () => {
    saveChatSession('user1', {
      connection: { id: 'c1', name: 'MyAPI', type: 'api', sqlTable: null },
      conversationId: 'conv-1',
    });
    const loaded = loadChatSession('user1');
    expect(loaded.connection.name).toBe('MyAPI');
    expect(loaded.conversationId).toBe('conv-1');
  });

  it('restores file context from durable storage after session storage is cleared', () => {
    saveChatSession('user1', {
      file: { name: 'sales.xlsx', mapping: { revenue: 'amount' }, mode: 'session' },
      conversationId: 'conv-1',
    });
    globalThis.sessionStorage.clear();

    const loaded = loadChatSession('user1');
    expect(loaded.file.name).toBe('sales.xlsx');
    expect(loaded.file.mapping.revenue).toBe('amount');
  });

  it('resolveStoredConnection matches live connection list', () => {
    const resolved = resolveStoredConnection(
      { id: 'c1', name: 'MyAPI', type: 'api' },
      [{ id: 'c1', name: 'MyAPI', type: 'api' }],
    );
    expect(resolved?.id).toBe('c1');
  });

  it('connectionFromMessages parses latest @mention', () => {
    const conns = [{ id: 'c1', name: 'SalesAPI', type: 'api' }];
    const conn = connectionFromMessages(
      [{ role: 'user', content: '@SalesAPI ยอดขายรวมเท่าไหร่' }],
      conns,
    );
    expect(conn?.id).toBe('c1');
  });

  it('connectionFromMessages restores an approved API mapping from message metadata', () => {
    const conns = [{ id: 'c1', name: 'SalesAPI', type: 'api' }];
    const conn = connectionFromMessages(
      [{
        role: 'user',
        content: 'วิเคราะห์ต่อ',
        connectionContext: {
          id: 'c1',
          type: 'api',
          mapping: { net_sales: 'revenue' },
          cleaningRecipe: { apply: true },
          cleaningProfile: 'financial',
        },
      }],
      conns,
    );
    expect(conn).toMatchObject({
      id: 'c1',
      mapping: { net_sales: 'revenue' },
      cleaningRecipe: { apply: true },
      cleaningProfile: 'financial',
    });
  });

  it('clearChatSession removes saved state', () => {
    saveChatSession('user1', { connection: { id: 'c1' } });
    clearChatSession('user1');
    expect(loadChatSession('user1')).toBeNull();
  });

  it('fileFromMessages reads latest attachment', () => {
    const file = fileFromMessages([
      {
        role: 'user',
        content: 'hello',
        attachment: '123_sales.xlsx',
        attachmentMapping: { revenue: 'amount' },
        attachmentCleaningRecipe: { apply: true },
        attachmentCleaningProfile: 'standard',
      },
    ]);
    expect(file?.name).toBe('123_sales.xlsx');
    expect(file?.mode).toBe('session');
    expect(file?.mapping).toEqual({ revenue: 'amount' });
    expect(file?.cleaningRecipe).toEqual({ apply: true });
    expect(file?.cleaningProfile).toBe('standard');
  });

  it('clearChatSessionFile keeps connection', () => {
    saveChatSession('user1', {
      connection: { id: 'c1' },
      file: { name: 'data.xlsx', mode: 'pending' },
    });
    clearChatSessionFile('user1');
    const loaded = loadChatSession('user1');
    expect(loaded.connection.id).toBe('c1');
    expect(loaded.file).toBeUndefined();
  });

  it('restores a conversation snapshot after refresh', () => {
    const messages = [
      { role: 'user', content: 'วิเคราะห์ต่อ', attachment: 'sales.xlsx' },
      { role: 'ai', content: 'ผลการวิเคราะห์' },
    ];
    saveConversationSnapshot('user1', 'conv-1', messages);
    globalThis.sessionStorage.clear();

    expect(loadConversationSnapshot('user1', 'conv-1')).toEqual(messages);
    clearConversationSnapshot('user1', 'conv-1');
    expect(loadConversationSnapshot('user1', 'conv-1')).toEqual([]);
  });

  it('isolates snapshots between conversation branches', () => {
    saveConversationSnapshot(
      'user1',
      'conv-1',
      [{ role: 'ai', content: 'branch A' }],
      'branch-a',
    );
    saveConversationSnapshot(
      'user1',
      'conv-1',
      [{ role: 'ai', content: 'branch B' }],
      'branch-b',
    );

    expect(loadConversationSnapshot('user1', 'conv-1', 'branch-a')[0].content)
      .toBe('branch A');
    expect(loadConversationSnapshot('user1', 'conv-1', 'branch-b')[0].content)
      .toBe('branch B');
  });

  it('keeps a newer local AI response while hydrating server ids', () => {
    const merged = mergeConversationMessages(
      [{ id: 'u1', role: 'user', content: 'analyze' }],
      [
        { role: 'user', content: 'analyze', attachment: 'sales.xlsx' },
        { role: 'ai', content: 'answer' },
      ],
    );

    expect(merged).toEqual([
      { id: 'u1', role: 'user', content: 'analyze', attachment: 'sales.xlsx' },
      { role: 'ai', content: 'answer' },
    ]);
  });

  it('collapses transient transcript copies with the same persisted id', () => {
    expect(dedupeConversationMessages([
      { id: 'same-id', role: 'user', content: 'answer', workflowResolution: { decision_key: 'metric' } },
      { id: 'same-id', role: 'user', content: 'answer', attachment: 'sales.xlsx' },
      { id: 'reply-id', role: 'ai', content: 'ready' },
    ])).toEqual([
      {
        id: 'same-id',
        role: 'user',
        content: 'answer',
        attachment: 'sales.xlsx',
        workflowResolution: { decision_key: 'metric' },
      },
      { id: 'reply-id', role: 'ai', content: 'ready' },
    ]);
  });

  it('deduplicates a stale local snapshot before choosing it over the server transcript', () => {
    const merged = mergeConversationMessages(
      [{ id: 'same-id', role: 'user', content: 'answer' }],
      [
        { id: 'same-id', role: 'user', content: 'answer' },
        { id: 'same-id', role: 'user', content: 'answer' },
      ],
    );

    expect(merged).toHaveLength(1);
    expect(merged[0].id).toBe('same-id');
  });
});
