import { describe, expect, it } from 'vitest';
import { isInvalidRefreshTokenError, isSupabaseAuthCookie } from './supabaseAuthError.js';

describe('isInvalidRefreshTokenError', () => {
  it('matches the GoTrue refresh-token-not-found payload', () => {
    expect(isInvalidRefreshTokenError({
      code: 'refresh_token_not_found',
      message: 'Invalid Refresh Token: Refresh Token Not Found',
    })).toBe(true);
  });

  it('ignores transient network errors', () => {
    expect(isInvalidRefreshTokenError({ message: 'Failed to fetch' })).toBe(false);
    expect(isInvalidRefreshTokenError(null)).toBe(false);
  });
});

describe('isSupabaseAuthCookie', () => {
  it('matches chunked SSR auth cookies', () => {
    expect(isSupabaseAuthCookie('sb-xyz-auth-token')).toBe(true);
    expect(isSupabaseAuthCookie('sb-xyz-auth-token.0')).toBe(true);
    expect(isSupabaseAuthCookie('sb-xyz-auth-token-code-verifier')).toBe(true);
    expect(isSupabaseAuthCookie('theme')).toBe(false);
  });
});
