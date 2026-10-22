import { describe, expect, it } from 'vitest';
import { backendIncident, correlationHeaders } from './correlation.js';

describe('request correlation', () => {
  it('preserves a safe caller-provided correlation id', () => {
    expect(correlationHeaders({ 'X-Correlation-ID': 'chat:request-123' }))
      .toMatchObject({ 'X-Correlation-ID': 'chat:request-123' });
  });

  it('extracts a stable incident id from backend error payloads', () => {
    expect(backendIncident({
      incident_id: 'incident-1',
      error_code: 'internal_error',
      retryable: false,
    })).toEqual({
      incidentId: 'incident-1',
      errorCode: 'internal_error',
      retryable: false,
    });
  });
});
