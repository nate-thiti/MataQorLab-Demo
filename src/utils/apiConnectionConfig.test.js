import { describe, expect, it } from 'vitest';
import {
  buildApiTestPayload,
  headersFromConnection,
  normalizeHeaders,
  parseRequestBodyText,
  validateApiForm,
} from './apiConnectionConfig.js';

describe('apiConnectionConfig', () => {
  it('builds multi-header POST payload with JSON body', () => {
    const payload = buildApiTestPayload({
      method: 'POST',
      url: 'https://acccloud.me/api/support/SaleOrderProduct/get',
      headers: [
        { key: 'x-api-key', value: 'key1' },
        { key: 'x-secret-key', value: 'secret1' },
      ],
      requestBodyText: '{"companyCode":"TESTER01","soDocNo":"SO-1"}',
    });

    expect(payload.request_headers).toHaveLength(2);
    expect(payload.request_body).toEqual({ companyCode: 'TESTER01', soDocNo: 'SO-1' });
    expect(payload.auth_header_name).toBe('x-api-key');
  });

  it('migrates legacy single header from stored connection', () => {
    const headers = headersFromConnection({
      auth_header_name: 'Authorization',
      auth_header_value: 'Bearer tok',
    });
    expect(headers).toEqual([{ key: 'Authorization', value: 'Bearer tok' }]);
  });

  it('rejects invalid JSON body for POST', () => {
    const result = validateApiForm({
      name: 'Inventory API',
      url: 'https://api.example.com/v1/data',
      method: 'POST',
      requestBodyText: '{bad json',
    });
    expect(result.ok).toBe(false);
    expect(result.code).toBe('invalid_json_body');
  });

  it('normalizes header keys', () => {
    expect(normalizeHeaders([{ key: '  x-api-key ', value: 'v' }])).toEqual([
      { key: 'x-api-key', value: 'v' },
    ]);
  });

  it('parses empty body as null', () => {
    expect(parseRequestBodyText('')).toBeNull();
    expect(parseRequestBodyText('{}')).toBeNull();
  });
});
