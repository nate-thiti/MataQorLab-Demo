/**
 * @connection and @connection-table mention helpers (separator: hyphen).
 */

export function formatConnectionMention(connName, tableName) {
  if (!connName) return '';
  if (tableName) return `@${connName}-${tableName}`;
  return `@${connName}`;
}

/**
 * @param {string} text
 * @param {Array<{ id: string, name: string, type: 'sql' | 'api' }>} connections
 */
export function parseConnectionMention(text, connections) {
  const content = (text || '').trim();
  if (!content || !connections?.length) return null;

  const sorted = [...connections].sort((a, b) => b.name.length - a.name.length);
  for (const conn of sorted) {
    const prefix = `@${conn.name}`;
    const idx = content.indexOf(prefix);
    if (idx === -1) continue;

    let sqlTable = null;
    const after = content.slice(idx + prefix.length);
    if (after.startsWith('-')) {
      const match = after.slice(1).match(/^([a-zA-Z0-9_.]+)/);
      if (match) sqlTable = match[1];
    }
    return { connection: conn, sqlTable };
  }
  return null;
}

/** Strip @connection or @connection-table prefix from user question text. */
export function stripConnectionMentionPrefix(message) {
  return (message || '').replace(/^@[\w.-]+(?:-[\w.]+)?\s+/, '').trim();
}

/**
 * Resolve connection + table from message text or active selection state.
 */
export function resolveConnectionContext(userContent, connections, activeConnection) {
  const parsed = parseConnectionMention(userContent, connections);
  if (parsed) {
    return {
      connId: parsed.connection.id,
      connType: parsed.connection.type,
      sqlTable: parsed.sqlTable || null,
      connection: parsed.connection,
    };
  }
  if (activeConnection) {
    return {
      connId: activeConnection.id,
      connType: activeConnection.type,
      sqlTable: activeConnection.sqlTable || null,
      connection: activeConnection,
    };
  }
  return { connId: null, connType: null, sqlTable: null, connection: null };
}
