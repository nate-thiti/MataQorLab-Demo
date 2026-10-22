const SAFE_ID = /^[A-Za-z0-9._:-]{1,128}$/;

export const createCorrelationId = () => {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `web-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
};

export const correlationHeaders = (headers = {}) => {
  const supplied = headers['X-Correlation-ID'] || headers['x-correlation-id'];
  return {
    ...headers,
    'X-Correlation-ID': SAFE_ID.test(String(supplied || ''))
      ? supplied
      : createCorrelationId(),
  };
};

export const backendIncident = (payload, response) => ({
  incidentId: payload?.incident_id
    || response?.headers?.get?.('X-Correlation-ID')
    || response?.headers?.get?.('X-Request-ID')
    || null,
  errorCode: payload?.error_code || null,
  retryable: Boolean(payload?.retryable),
});

