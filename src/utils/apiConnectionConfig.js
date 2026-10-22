/** REST API connection form helpers (Postman-style headers + JSON body). */

export const EMPTY_HEADER = { key: '', value: '' };

export const POST_BODY_PLACEHOLDER = `{
  "startDate": "2026-01-01",
  "limit": 100
}`;

export function normalizeHeaders(headers) {
  return (headers || [])
    .map((row) => ({
      key: String(row?.key ?? '').trim(),
      value: row?.value == null ? '' : String(row.value),
    }))
    .filter((row) => row.key.length > 0);
}

export function parseRequestBodyText(text) {
  const trimmed = (text || '').trim();
  if (!trimmed) return null;
  const parsed = JSON.parse(trimmed);
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && Object.keys(parsed).length === 0) {
    return null;
  }
  return parsed;
}

export function formatRequestBodyForForm(body) {
  if (body == null) return '';
  if (typeof body === 'string') {
    const trimmed = body.trim();
    if (!trimmed) return '';
    try {
      return JSON.stringify(JSON.parse(trimmed), null, 2);
    } catch {
      return body;
    }
  }
  if (typeof body === 'object') {
    return JSON.stringify(body, null, 2);
  }
  return '';
}

export function headersFromConnection(conn) {
  if (Array.isArray(conn?.request_headers) && conn.request_headers.length > 0) {
    return conn.request_headers.map((row) => ({
      key: row?.key ?? '',
      value: row?.value ?? '',
    }));
  }
  if (conn?.auth_header_name) {
    return [{ key: conn.auth_header_name, value: conn.auth_header_value || '' }];
  }
  return [{ key: 'Authorization', value: '' }];
}

export function buildApiTestPayload({ method, url, headers, requestBodyText }) {
  const request_headers = normalizeHeaders(headers);
  let request_body = null;
  if ((method || 'GET').toUpperCase() !== 'GET') {
    request_body = parseRequestBodyText(requestBodyText);
  }
  const legacy = request_headers[0];
  return {
    method,
    url,
    request_headers,
    request_body,
    auth_header_name: legacy?.key || undefined,
    auth_header_value: legacy?.value || undefined,
  };
}

export function buildApiConnectionRecord({
  user_id,
  name,
  method,
  url,
  headers,
  requestBodyText,
  status = 'active',
}) {
  const payload = buildApiTestPayload({ method, url, headers, requestBodyText });
  return {
    user_id,
    name,
    method: payload.method,
    url: payload.url,
    request_headers: payload.request_headers,
    request_body: payload.request_body,
    auth_header_name: payload.auth_header_name || 'Authorization',
    auth_header_value: payload.auth_header_value || '',
    status,
  };
}

export function buildApiConnectionUpdate({ name, method, url, headers, requestBodyText }) {
  const payload = buildApiTestPayload({ method, url, headers, requestBodyText });
  return {
    name,
    method: payload.method,
    url: payload.url,
    request_headers: payload.request_headers,
    request_body: payload.request_body,
    auth_header_name: payload.auth_header_name || 'Authorization',
    auth_header_value: payload.auth_header_value || '',
  };
}

export function validateApiForm({ name, url, method, requestBodyText }) {
  if (!name?.trim() || !url?.trim()) {
    return { ok: false, code: 'required_fields' };
  }
  if ((method || 'GET').toUpperCase() !== 'GET' && (requestBodyText || '').trim()) {
    try {
      parseRequestBodyText(requestBodyText);
    } catch {
      return { ok: false, code: 'invalid_json_body' };
    }
  }
  return { ok: true };
}
