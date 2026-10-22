/**
 * Map raw API/stream errors to user-friendly messages (no model names or JSON).
 * @param {unknown} err
 * @param {(key: string, fallback: string) => string} t
 */
export function getFriendlyChatError(err, t) {
  const status = /** @type {{ status?: number, message?: string }} */ (err)?.status;
  const msg = (
    /** @type {{ message?: string }} */ (err)?.message ||
    String(err || '')
  ).toLowerCase();

  const isLlmCredits =
    status === 402 ||
    msg.includes('insufficient credits') ||
    msg.includes('never purchased credits');

  const isProviderUnavailable =
    status === 404 ||
    msg.includes('no allowed providers') ||
    msg.includes('requested_providers');

  const isRateLimit =
    status === 429 ||
    msg.includes('rate limit') ||
    msg.includes('rate-limited') ||
    msg.includes('error code: 429') ||
    msg.includes('too many requests');

  const isServerBusy =
    status === 503 ||
    status === 502 ||
    status === 504 ||
    msg.includes('503') ||
    msg.includes('504') ||
    msg.includes('service unavailable') ||
    msg.includes('gateway timeout') ||
    msg.includes('openrouter api error') ||
    msg.includes('llm api error');

  const isProfileError =
    status === 403 ||
    msg.includes('ไม่สามารถตรวจสอบข้อมูลสมาชิก') ||
    msg.includes('ตั้งค่าแผนการใช้งาน');

  const isFileLoadError =
    status === 400 ||
    msg.includes('ไม่สามารถโหลดไฟล์') ||
    msg.includes('timed out');

  if (isFileLoadError) {
    return t(
      'chat.error_file_load',
      'ไม่สามารถโหลดไฟล์ข้อมูลได้ กรุณาลองอัปโหลดใหม่หรือใช้ไฟล์ที่เล็กลง'
    );
  }

  if (isProfileError) {
    return t(
      'chat.error_profile',
      'ไม่สามารถตรวจสอบแผนการใช้งานได้ กรุณาตรวจสอบการตั้งค่าบัญชีหรือลองใหม่อีกครั้ง'
    );
  }

  if (isLlmCredits) {
    return t(
      'chat.error_llm_credits',
      'บัญชี LLM provider ไม่มีเครดit เพียงพอ — เติมเงินที่ OpenRouter หรือตรวจสอบ BYOK ของ DeepInfra'
    );
  }

  if (isProviderUnavailable) {
    return t(
      'chat.error_provider',
      'ตั้งค่า LLM provider ไม่ถูกต้อง — ตรวจสอบ LLM_PROVIDER_ORDER ใน backend/.env'
    );
  }

  if (isRateLimit || isServerBusy) {
    return t(
      'chat.error_busy',
      'ขณะนี้มีผู้ใช้จำนวนมาก กรุณารอสักครู่'
    );
  }

  return t(
    'chat.error_generic',
    'เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้งในภายหลัง'
  );
}

/**
 * Infer HTTP status from raw error detail string.
 * @param {string} detail
 */
export function inferErrorStatus(detail) {
  const lower = (detail || '').toLowerCase();
  if (lower.includes('rate limit') || lower.includes('429') || lower.includes('rate-limited')) {
    return 429;
  }
  if (lower.includes('503') || lower.includes('service unavailable')) {
    return 503;
  }
  if (lower.includes('504') || lower.includes('timeout')) {
    return 504;
  }
  return 502;
}
