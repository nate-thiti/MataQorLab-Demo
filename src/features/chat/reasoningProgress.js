/** @typedef {{ stage: string, detail?: Record<string, unknown> }} ProgressStep */
/** @typedef {{ stage: string|null, detail: Record<string, unknown>, history: ProgressStep[], startedAt: number|null }} ReasoningProgressState */
/** @typedef {{ hasFile?: boolean, hasConnection?: boolean, connectionType?: string|null, isAnalysis?: boolean }} AnalysisContext */

export const INITIAL_REASONING_PROGRESS = /** @type {ReasoningProgressState} */ ({
  stage: null,
  detail: {},
  history: [],
  startedAt: null,
});

/** Fresh progress state for a new stream attempt. */
export function createReasoningProgress(hint, startedAt = Date.now()) {
  return {
    stage: 'intent',
    detail: { hint: (hint || '').slice(0, 80) },
    history: [],
    startedAt,
  };
}

const STAGE_WEIGHTS = {
  intent: 5,
  mode_selected: 7,
  loading_data: 10,
  connecting: 10,
  querying: 15,
  parsing: 12,
  merging: 18,
  analytics: 22,
  agent_plan: 26,
  agent_clarify: 24,
  pandas_query: 28,
  web_search: 29,
  agent_step: 30,
  web_search_done: 31,
  calculating: 32,
  classifying: 32,
  analyzing_done: 38,
  computing_findings: 40,
  findings_ready: 43,
  tools_ready: 44,
  generating: 45,
  continuing: 70,
  verifying: 92,
  done: 100,
};

/**
 * Expected pipeline stages based on request context (level 4).
 * @param {AnalysisContext} ctx
 */
export function buildExpectedStages(ctx = {}) {
  const { hasFile, hasConnection, connectionType, isAnalysis } = ctx;

  if (!isAnalysis && !hasFile && !hasConnection) {
    return ['intent', 'generating'];
  }
  if (hasConnection && connectionType === 'sql') {
    return ['intent', 'connecting', 'querying', 'agent_clarify', 'agent_plan', 'agent_step', 'analyzing_done', 'computing_findings', 'findings_ready', 'generating'];
  }
  if (hasConnection && connectionType === 'api') {
    return ['intent', 'connecting', 'merging', 'agent_clarify', 'agent_plan', 'agent_step', 'analyzing_done', 'computing_findings', 'findings_ready', 'generating'];
  }
  if (hasFile) {
    return ['intent', 'loading_data', 'merging', 'analytics', 'agent_clarify', 'agent_plan', 'agent_step', 'analyzing_done', 'classifying', 'computing_findings', 'findings_ready', 'generating'];
  }
  return ['intent', 'generating'];
}

/**
 * Progress bar percent (level 5).
 * @param {string|null} currentStage
 * @param {ProgressStep[]} history
 * @param {AnalysisContext} ctx
 */
export function computeProgressPercent(currentStage, history = [], ctx = {}) {
  const expected = buildExpectedStages(ctx);
  const seen = new Set(history.map((h) => h.stage));
  if (currentStage) seen.add(currentStage);

  let matched = 0;
  for (const stage of expected) {
    if (seen.has(stage)) matched += 1;
  }
  const base = expected.length > 0 ? (matched / expected.length) * 85 : 0;
  const stageBoost = currentStage && STAGE_WEIGHTS[currentStage]
    ? STAGE_WEIGHTS[currentStage] * 0.15
    : 0;
  return Math.min(98, Math.round(base + stageBoost));
}

/**
 * Elapsed seconds since start.
 * @param {number|null} startedAt
 */
export function getElapsedSeconds(startedAt) {
  if (!startedAt) return 0;
  return Math.floor((Date.now() - startedAt) / 1000);
}

/**
 * Strip @connection prefix from display message.
 * @param {string} message
 */
export function stripConnectionPrefix(message) {
  return (message || '').replace(/^@[\w.-]+(?:-[\w.]+)?\s+/, '').trim();
}

/**
 * Dynamic step label from backend detail (level 3).
 * @param {string} stage
 * @param {Record<string, unknown>} detail
 * @param {boolean} isEn
 * @param {(key: string, fallback: string, vars?: Record<string, string|number>) => string} t
 */
export function getStepLabel(stage, detail = {}, isEn, t) {
  const file = detail.file ? String(detail.file) : '';
  const displayFile = file.includes('_') ? file.split('_').slice(1).join('_') || file : file;
  const rows = typeof detail.rows === 'number' ? detail.rows : null;
  const cols = typeof detail.cols === 'number' ? detail.cols : null;
  const hint = detail.hint ? String(detail.hint) : '';
  const preview = detail.preview ? String(detail.preview) : '';
  const conn = detail.connection ? String(detail.connection) : '';

  switch (stage) {
    case 'intent':
      return hint
        ? t('chat.status_intent_hint', isEn ? `Parsing intent: "${hint}"…` : `วิเคราะห์เจตนา: "${hint}"…`, { hint })
        : t('chat.status_sending', isEn ? 'Analyzing user intent…' : 'วิเคราะห์เจตนาของผู้ใช้…');
    case 'planning_tools':
      return t(
        'chat.status_planning_tools',
        isEn ? 'Choosing tools for this question…' : 'กำลังเลือกเครื่องมือตามคำถาม…',
      );
    case 'mode_selected': {
      const effective = detail.effective === 'deep' ? 'Deep' : 'Fast';
      const requested = detail.requested === 'auto' ? 'Auto → ' : '';
      return isEn
        ? `${requested}${effective}: applying server processing budget…`
        : `${requested}${effective}: กำหนดงบการประมวลผลฝั่งเซิร์ฟเวอร์…`;
    }
    case 'loading_data':
      return displayFile
        ? t('chat.status_loading_file', isEn ? `Loading ${displayFile}…` : `กำลังโหลด ${displayFile}…`, { file: displayFile })
        : t('chat.status_loading', isEn ? 'Loading data…' : 'กำลังโหลดข้อมูล…');
    case 'connecting':
      return detail.type === 'sql'
        ? t('chat.status_connecting_sql', isEn ? 'Connecting to database…' : 'กำลังเชื่อมต่อฐานข้อมูล…')
        : t('chat.status_connecting_api', isEn ? 'Connecting to API…' : 'กำลังเชื่อมต่อ API…');
    case 'querying':
      return hint
        ? t('chat.status_querying_hint', isEn ? `Running SQL: "${hint}"…` : `รัน SQL: "${hint}"…`, { hint })
        : t('chat.db_querying', isEn ? 'Connecting and querying database…' : 'กำลังเชื่อมต่อและรันคำสั่งบนฐานข้อมูล…');
    case 'parsing':
      return displayFile
        ? t('chat.status_parsing', isEn ? `Parsing ${displayFile}…` : `กำลังแปลง ${displayFile}…`, { file: displayFile })
        : t('chat.status_parsing_json', isEn ? 'Parsing JSON structure…' : 'กำลังแปลงโครงสร้าง JSON…');
    case 'merging':
      if (rows != null && cols != null) {
        const localeTag = isEn ? 'en-US' : 'th-TH';
        const engineTag = detail.engine ? ` [${String(detail.engine).toUpperCase()}]` : '';
        return t(
          'chat.status_merging_rows',
          isEn ? `Cleaning ${rows.toLocaleString(localeTag)} rows × ${cols} columns${engineTag}…` : `ล้างข้อมูล ${rows.toLocaleString(localeTag)} แถว × ${cols} คอลัมน์${engineTag}…`,
          { rows: rows.toLocaleString(localeTag), cols, engine: detail.engine ? String(detail.engine) : '' }
        );
      }
      return t('chat.status_merging', isEn ? 'Merging and cleaning data…' : 'กำลังรวบรวมและล้างข้อมูล…');
    case 'analytics':
      if (rows != null) {
        const localeTag = isEn ? 'en-US' : 'th-TH';
        const engineTag = detail.engine === 'duckdb'
          ? (isEn ? 'DuckDB' : 'DuckDB')
          : detail.engine === 'pandas'
            ? (isEn ? 'Pandas' : 'Pandas')
            : '';
        const engineSuffix = engineTag ? (isEn ? ` via ${engineTag}` : ` ด้วย ${engineTag}`) : '';
        return t(
          'chat.status_analytics_engine',
          isEn ? `Computing stats on ${rows.toLocaleString(localeTag)} rows${engineSuffix}…` : `คำนวณสถิติจาก ${rows.toLocaleString(localeTag)} แถว${engineSuffix}…`,
          { rows: rows.toLocaleString(localeTag), engine: engineTag }
        );
      }
      return t('chat.status_analyzing', isEn ? 'Processing statistics…' : 'กำลังประมวลผลสถิติ…');
    case 'pandas_query':
      return hint
        ? t('chat.status_pandas_hint', isEn ? `Running query: "${hint}"…` : `รันคำสั่ง: "${hint}"…`, { hint })
        : t('chat.status_analyzing', isEn ? 'Processing statistics and trends…' : 'กำลังประมวลผลสถิติและวิเคราะห์แนวโน้ม…');
    case 'agent_plan':
      return t('chat.status_agent_plan', isEn ? 'Planning multi-step analysis…' : 'วางแผนการวิเคราะห์หลายขั้นตอน…');
    case 'agent_clarify':
      if (detail.action === 'waiting') {
        return hint
          ? t('chat.status_agent_waiting_hint', isEn ? `Waiting for your answer: "${hint}"` : `รอคำตอบจากคุณ: "${hint}"`, { hint })
          : t('chat.status_agent_waiting', isEn ? 'Waiting for your answer…' : 'รอคำตอบจากคุณ…');
      }
      return hint
        ? t('chat.status_agent_clarify_hint', isEn ? `Need clarification: "${hint}"…` : `ต้องการข้อมูลเพิ่ม: "${hint}"…`, { hint })
        : t('chat.status_agent_clarify', isEn ? 'Checking if clarification is needed…' : 'ตรวจสอบว่าต้องถามเพิ่มหรือไม่…');
    case 'agent_step': {
      const step = typeof detail.step === 'number' ? detail.step : 1;
      const total = typeof detail.total === 'number' ? detail.total : step;
      const stepHint = hint || t('chat.status_analyzing', isEn ? 'Processing…' : 'กำลังประมวลผล…');
      return t(
        'chat.status_agent_step',
        isEn ? `Step ${step}/${total}: "${stepHint}"…` : `ขั้นที่ ${step}/${total}: "${stepHint}"…`,
        { step, total, hint: stepHint }
      );
    }
    case 'web_search': {
      const step = typeof detail.step === 'number' ? detail.step : 1;
      const total = typeof detail.total === 'number' ? detail.total : step;
      const searchHint = hint || t('chat.status_analyzing', isEn ? 'external data' : 'ข้อมูลภายนอก');
      return t(
        'chat.status_web_search',
        isEn
          ? `Step ${step}/${total}: Searching web for "${searchHint}"…`
          : `ขั้นที่ ${step}/${total}: กำลังค้นหาเว็บ "${searchHint}"…`,
        { step, total, hint: searchHint }
      );
    }
    case 'web_search_done': {
      const count = typeof detail.source_count === 'number'
        ? detail.source_count
        : Array.isArray(detail.sources)
          ? detail.sources.length
          : 0;
      return t(
        'chat.status_web_search_done',
        isEn ? `Found ${count} web source${count === 1 ? '' : 's'}` : `พบ ${count} แหล่งข้อมูลจากเว็บ`,
        { count }
      );
    }
    case 'calculating':
      return detail.expression
        ? t(
          'chat.status_calculating_expression',
          isEn
            ? `Calculating ${String(detail.expression)}…`
            : `กำลังคำนวณ ${String(detail.expression)}…`,
          { expression: String(detail.expression) },
        )
        : t('chat.status_calculating', isEn ? 'Calculating…' : 'กำลังคำนวณ…');
    case 'correcting':
      return t(
        'chat.status_correcting',
        isEn ? 'Fixing numbers to match verified findings…' : 'กำลังแก้ตัวเลขให้ตรงกับผลที่ยืนยันแล้ว…',
      );
    case 'verifying':
      return detail.status === 'needs_review'
        ? t(
          'chat.status_verifying_review',
          isEn ? 'Checking evidence — some claims need review…' : 'ตรวจหลักฐาน — บางข้อความอาจต้องทบทวน…',
        )
        : t(
          'chat.status_verifying',
          isEn ? 'Checking evidence and numbers…' : 'กำลังตรวจหลักฐานและตัวเลข…',
        );
    case 'classifying':
      return t('chat.status_classifying', isEn ? 'Classifying dataset type…' : 'จำแนกประเภทข้อมูล…');
    case 'analyzing_done':
      if (detail.cached) {
        return t('chat.status_cache_hit', isEn ? 'Reused cached analytics' : 'ใช้ผลวิเคราะห์ที่คำนวณไว้แล้ว');
      }
      if (preview) {
        return t('chat.status_query_done', isEn ? `Query done — ${preview}` : `ได้ผลแล้ว — ${preview}`, { preview });
      }
      if (conn) {
        return t('chat.status_conn_done', isEn ? `Data loaded from ${conn}` : `โหลดข้อมูลจาก ${conn} แล้ว`, { conn });
      }
      return t('chat.status_analyze_done', isEn ? 'Analysis complete' : 'วิเคราะห์ข้อมูลเสร็จแล้ว');
    case 'computing_findings': {
      const depth = detail.compute_depth === 'deep' ? 'Deep' : 'Base';
      const count = typeof detail.rows === 'number' ? detail.rows.toLocaleString(isEn ? 'en-US' : 'th-TH') : '';
      return isEn
        ? `${depth} compute: deriving verified findings${count ? ` from ${count} rows` : ''}…`
        : `${depth} compute: กำลังสร้างข้อค้นพบที่ตรวจสอบได้${count ? `จาก ${count} แถว` : ''}…`;
    }
    case 'findings_ready': {
      const count = typeof detail.finding_count === 'number' ? detail.finding_count : 0;
      return isEn
        ? `${count} verified findings ready`
        : `พร้อมแล้ว ${count} ข้อค้นพบที่ตรวจสอบได้`;
    }
    case 'tools_ready': {
      const calls = Array.isArray(detail.calls) ? detail.calls : [];
      const completed = calls.filter((call) => call?.status === 'completed').length;
      return detail.satisfied === false
        ? (isEn
          ? 'Required analytical tool did not complete — blocking model fallback…'
          : 'เครื่องมือวิเคราะห์ที่จำเป็นไม่สำเร็จ — กำลังป้องกันไม่ให้โมเดลคำนวณแทน…')
        : (isEn
          ? `${completed} server tool${completed === 1 ? '' : 's'} completed; evidence sealed`
          : `เครื่องมือฝั่งเซิร์ฟเวอร์สำเร็จ ${completed} รายการ และล็อกหลักฐานแล้ว`);
    }
    case 'generating':
      return t('chat.status_summarizing', isEn ? 'Summarizing strategic insights…' : 'กำลังสรุปผลเชิงกลยุทธ์…');
    case 'continuing':
      return t(
        'chat.status_continuing',
        isEn ? 'Completing the response and chart instructions…' : 'กำลังเขียนคำตอบและคำสั่งสร้างกราฟให้ครบ…',
      );
    case 'done':
      return t('chat.status_success', isEn ? 'Success' : 'สำเร็จ');
    default:
      return stage;
  }
}

/**
 * Merge stream status into progress state.
 * @param {ReasoningProgressState} prev
 * @param {string} stage
 * @param {Record<string, unknown>} detail
 */
export function applyStreamStatus(prev, stage, detail = {}) {
  if (prev.stage === stage) {
    return {
      ...prev,
      detail: { ...prev.detail, ...detail },
    };
  }
  const nextHistory = prev.stage
    ? [...prev.history, { stage: prev.stage, detail: prev.detail }]
    : prev.history;
  return {
    ...prev,
    stage,
    detail,
    history: nextHistory,
  };
}
