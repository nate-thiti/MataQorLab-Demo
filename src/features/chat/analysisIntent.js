/** Keywords that clearly indicate data analysis intent. */
export const ANALYSIS_KEYWORDS = [
  'วิเคราะห์', 'ข้อมูล', 'กราฟ', 'ไฟล์', 'เปรียบเทียบ', 'สรุป', 'รายงาน', 'ตาราง',
  'analyze', 'analysis', 'data', 'chart', 'graph', 'file', 'compare', 'summarize',
  'excel', 'csv', 'database', 'sql', 'report', 'table',
  'สถิติ', 'metrics', 'kpi', 'dashboard', 'pivot', 'aggregate', 'distribution',
  'correlation', 'forecast', 'segment', 'breakdown', 'export', 'download',
];

/** Regex patterns for analysis-style questions without explicit keywords. */
const ANALYSIS_QUESTION_PATTERNS = [
  /\bกี่\b/u,
  /เท่าไหร่/u,
  /มากที่สุด|น้อยที่สุด|สูงสุด|ต่ำสุด/u,
  /อันดับ\s*\d*/u,
  /top\s+\d+/i,
  /bottom\s+\d+/i,
  /แยกตาม|จัดกลุ่ม|แบ่งตาม/u,
  /แนวโน้ม|รายเดือน|รายปี|รายไตรมาส|ช่วงเวลา/u,
  /คำนวณ|ผลรวม|เฉลี่ย|รวมทั้งหมด/u,
  /how many|how much|what is the total/i,
  /\btotal\b|\baverage\b|\bmean\b|\bmedian\b/i,
  /\bhighest\b|\blowest\b|\btop\b|\brank\b/i,
  /breakdown|by region|per month|over time|year over year/i,
  /\d+\s*%|\d+\s*percent/i,
];

/** Greetings, thanks, meta chat — not data analysis. */
const SMALL_TALK_EXACT = new Set([
  'สวัสดี', 'หวัดดี', 'ดี', 'ไง', 'เป็นไง', 'สบายดี', 'ขอบคุณ', 'ขอบใจ',
  'ครับ', 'ค่ะ', 'ลาก่อน', 'บาย', 'โอเค', 'ok', 'okay', 'ได้', 'เข้าใจแล้ว',
  'hello', 'hi', 'hey', 'thanks', 'thank you', 'thx', 'bye', 'goodbye', 'cool', 'nice',
  'ยินดี', 'ไม่เป็นไร', 'ขอโทษ', 'sorry', 'lol', 'haha',
]);

const SMALL_TALK_PATTERNS = [
  /^(สวัสดี|หวัดดี|ดีครับ|ดีค่ะ|ดีจ้า)[\s!?.。]*$/iu,
  /^(hello|hi|hey)[\s!?.]*$/i,
  /^(thanks|thank you|thx)[\s!?.]*$/i,
  /^(bye|goodbye|see you|ลาก่อน)[\s!?.]*$/iu,
  /^(good morning|good night|good evening)[\s!?.]*$/i,
  /^(โอเค|ok|okay|ได้เลย|เข้าใจแล้ว)[\s!?.]*$/iu,
  /^(ขอบคุณ|ขอบใจ)/iu,
  /คุณคือใคร|คุณเป็นใคร|คุณคืออะไร/u,
  /ทำอะไรได้|ช่วยอะไรได้|ใช้งานยังไง|ใช้ยังไง/u,
  /what can you do/i,
  /who are you/i,
  /how do i use (this|the app)/i,
  /what is (this|mataqor|analyst)/i,
  /^ช่วย(ได้ไหม|ไหม|นะ)[\s?？]*$/iu,
];

/**
 * Strip @connection prefix so "สวัสดี" isn't mixed with connection names.
 * @param {string} content
 */
export function normalizeMessageForIntent(content) {
  return (content || '').replace(/^@[\w-]+\s+/, '').trim();
}

/**
 * Casual / meta messages that should not trigger file analytics.
 * @param {string} content
 */
export function messageLooksLikeSmallTalk(content) {
  const text = normalizeMessageForIntent(content);
  if (!text) return true;

  const lower = text.toLowerCase();
  if (SMALL_TALK_EXACT.has(lower) || SMALL_TALK_EXACT.has(text)) {
    return true;
  }

  for (const pattern of SMALL_TALK_PATTERNS) {
    if (pattern.test(text) || pattern.test(lower)) {
      return true;
    }
  }

  // Very short chit-chat without digits
  if (text.length <= 3 && !/\d/.test(text)) {
    const lowerShort = text.toLowerCase();
    const hasAnalysisKeyword = ANALYSIS_KEYWORDS.some((kw) => lowerShort.includes(kw));
    if (!hasAnalysisKeyword) {
      return true;
    }
  }

  return false;
}

/**
 * @param {string} content
 */
export function messageLooksLikeAnalysis(content) {
  const text = normalizeMessageForIntent(content);
  if (!text) return false;

  if (messageLooksLikeSmallTalk(text)) {
    return false;
  }

  const lower = text.toLowerCase();
  if (ANALYSIS_KEYWORDS.some((keyword) => lower.includes(keyword))) {
    return true;
  }

  return ANALYSIS_QUESTION_PATTERNS.some((pattern) => pattern.test(text) || pattern.test(lower));
}

/**
 * Whether this message should run the data-analysis pipeline (file / connection).
 * @param {string} userContent
 * @param {{ hasAttachedFile?: boolean, hasConnection?: boolean, isAgentClarification?: boolean }} opts
 */
export function isAnalysisRequest(userContent, opts = {}) {
  if (opts.hasAttachedFile || opts.hasConnection || opts.isAgentClarification) {
    return true;
  }
  return messageLooksLikeAnalysis(userContent);
}

/**
 * Whether a cached session file should be sent to the backend for this message.
 * @param {string} userContent
 * @param {{ hasAttachedFile?: boolean, hasConnection?: boolean, isAgentClarification?: boolean }} opts
 */
export function shouldUseSessionFile(userContent, opts = {}) {
  // An active dataset is an explicit user selection (the chip remains visible
  // until the user removes it). Keep sending it on follow-up turns so short
  // prompts such as "แล้วเดือนก่อนล่ะ" do not silently lose data context.
  return true;
}

/**
 * Files and API connections must never reach analytics/AI before the user has
 * explicitly confirmed at least one semantic column mapping.
 */
export function needsUserApprovedMapping({
  hasAttachedFile = false,
  connectionType = null,
  mapping = null,
  cleaningRecipe = null,
  isAgentClarification = false,
} = {}) {
  if (isAgentClarification) return false;
  const isGuardedSource = hasAttachedFile || connectionType === 'api';
  if (!isGuardedSource) return false;
  const hasApprovedEtl = Boolean(
    cleaningRecipe
    && typeof cleaningRecipe === 'object'
    && Object.keys(cleaningRecipe).length > 0
  );
  return countApprovedMappingValues(mapping) === 0 && !hasApprovedEtl;
}

function countApprovedMappingValues(mapping) {
  if (!mapping || typeof mapping !== 'object') return 0;
  return Object.values(mapping).filter((value) => String(value || '').trim()).length;
}
