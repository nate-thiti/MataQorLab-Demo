export function isInvalidRefreshTokenError(error) {
  if (!error) return false;
  const code = String(error.code || '');
  const message = String(error.message || '');
  return (
    code === 'refresh_token_not_found' ||
    message.includes('Refresh Token Not Found') ||
    /Invalid Refresh Token/i.test(message)
  );
}

export function isSupabaseAuthCookie(name) {
  return (
    /^sb-.*-auth-token(?:\.\d+)?$/.test(String(name || '')) ||
    String(name || '').endsWith('-auth-token-code-verifier')
  );
}
