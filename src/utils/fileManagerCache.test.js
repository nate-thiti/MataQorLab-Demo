import { describe, expect, it } from 'vitest';
import { createFileManagerCache } from './fileManagerCache.js';

describe('fileManagerCache', () => {
  it('stores file lists by user and reports freshness', () => {
    let now = 1000;
    const cache = createFileManagerCache({ ttlMs: 60000, now: () => now });

    cache.setFiles('user-1', { files: [{ name: 'a.csv' }], totalSize: 123 });
    cache.setFiles('user-2', { files: [{ name: 'b.csv' }], totalSize: 456 });

    expect(cache.getFiles('user-1')).toMatchObject({
      files: [{ name: 'a.csv' }],
      totalSize: 123,
      isFresh: true,
    });
    expect(cache.getFiles('user-2')).toMatchObject({
      files: [{ name: 'b.csv' }],
      totalSize: 456,
      isFresh: true,
    });
  });

  it('marks cached data stale after the ttl', () => {
    let now = 1000;
    const cache = createFileManagerCache({ ttlMs: 60000, now: () => now });
    cache.setApiConnections('user-1', { connections: [{ id: 'api-1' }] });

    now += 60001;

    expect(cache.getApiConnections('user-1')).toMatchObject({
      connections: [{ id: 'api-1' }],
      isFresh: false,
    });
  });

  it('clears one user without affecting another user', () => {
    const cache = createFileManagerCache();
    cache.setDatabaseConnections('user-1', { connections: [{ id: 'db-1' }] });
    cache.setDatabaseConnections('user-2', { connections: [{ id: 'db-2' }] });

    cache.clearUser('user-1');

    expect(cache.getDatabaseConnections('user-1')).toBeNull();
    expect(cache.getDatabaseConnections('user-2')).toMatchObject({
      connections: [{ id: 'db-2' }],
    });
  });

  it('stores connection health status with cached connections', () => {
    const cache = createFileManagerCache();
    cache.setApiConnections('user-1', {
      connections: [{ id: 'api-1' }],
      healthStatus: { 'api-1': 'ok' },
    });

    expect(cache.getApiConnections('user-1')).toMatchObject({
      connections: [{ id: 'api-1' }],
      healthStatus: { 'api-1': 'ok' },
      isFresh: true,
    });
  });

  it('merges dashboard cache sections without dropping previous fields', () => {
    const cache = createFileManagerCache();
    cache.setDashboard('user-1', { stats: { files: 2 } });
    cache.setDashboard('user-1', { recentFiles: [{ name: 'latest.csv' }] });

    expect(cache.getDashboard('user-1')).toMatchObject({
      stats: { files: 2 },
      recentFiles: [{ name: 'latest.csv' }],
      isFresh: true,
    });
  });

  it('stores chat conversations and messages by user', () => {
    const cache = createFileManagerCache();
    cache.setChatConversations('user-1', { conversations: [{ id: 'conv-1' }] });
    cache.setChatMessages('user-1', 'conv-1', { messages: [{ role: 'user', content: 'hi' }] });

    expect(cache.getChatConversations('user-1')).toMatchObject({
      conversations: [{ id: 'conv-1' }],
      isFresh: true,
    });
    expect(cache.getChatMessages('user-1', 'conv-1')).toMatchObject({
      messages: [{ role: 'user', content: 'hi' }],
      isFresh: true,
    });
  });
});
