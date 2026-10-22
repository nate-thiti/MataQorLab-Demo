/**
 * AI message normalization: LaTeX → readable text, markdown repair, system JSON extraction.
 * Mirrors backend/app/schemas/chat.py::sanitize_message_content
 */

const LATEX_SYMBOLS = [
  [/\\rightarrow/g, '→'],
  [/\\leftarrow/g, '←'],
  [/\\Rightarrow/g, '⇒'],
  [/\\Leftarrow/g, '⇐'],
  [/\\leftrightarrow/g, '↔'],
  [/\\uparrow/g, '↑'],
  [/\\downarrow/g, '↓'],
  [/\\div/g, '÷'],
  [/\\times/g, '×'],
  [/\\cdot/g, '·'],
  [/\\pm/g, '±'],
  [/\\approx/g, '≈'],
  [/\\leq/g, '≤'],
  [/\\geq/g, '≥'],
  [/\\neq/g, '≠'],
  [/\\star/g, '⭐'],
  [/\\bullet/g, '•'],
  [/\\sum/g, 'Σ'],
  [/\\infty/g, '∞'],
  [/\\%/g, '%'],
  [/\\percent/g, '%'],
  [/\\left/g, ''],
  [/\\right/g, ''],
  [/\\,/g, ' '],
  [/\\;/g, ' '],
  [/\\:/g, ' '],
  [/\\quad/g, '  '],
  [/\\qquad/g, '    '],
  [/\\hline/g, ''],
  [/\\_/g, '_'],
];

const SYSTEM_JSON_PATTERN = /```json\s*([\s\S]*?)\s*```/gi;
const FENCED_CODE_PATTERN = /(```[\s\S]*?```)/g;
const INTERNAL_CONTEXT_TAG_PATTERN =
  /<\/?(?:calculated_metrics|web_sources|external_web_context|attached_file|column_profile|chart_data_hints|request_routing|response_mode|older_conversation_summary|prior_analysis_memory|chat_memory|tool_result|structured_findings|server_response_outline|analysis_contract)(?:\s[^>]*)?>/gi;
const INTERNAL_CONTEXT_LABEL_PATTERN =
  /^\s*(?:External Web Context\s*\([^)]*(?:platform|ระบบ)[^)]*\)|บริบทจากเว็บภายนอก\s*\([^)]*\))\s*:?\s*$/gim;
const SECTION_HEADING_PATTERN =
  /^(สรุป(?:ภาพรวม|ผล|ประเด็นสำคัญ)?|ข้อเสนอแนะ|คำแนะนำ|สิ่งที่พบ|ประเด็นสำคัญ|แนวโน้ม|ผลการวิเคราะห์|แหล่งอ้างอิง|Summary|Key findings|Findings|Recommendations?|Next steps?|Analysis|Sources?)\s*:?\s*$/gim;

const isSystemCommandPayload = (obj) =>
  obj &&
  typeof obj === 'object' &&
  typeof obj.action === 'string' &&
  ['render_chart', 'generate_report', 'propose_visualization', 'propose_python_analysis', 'preview_dax_definition'].includes(obj.action);

/** Unescape double-backslashes common in API/JSON payloads (\\frac → \frac) */
const normalizeEscapes = (text) =>
  text.replace(/\\\\([a-zA-Z[\]{}_$%])/g, '\\$1');

const replaceLatexSymbols = (text) => {
  let result = text;
  for (const [pattern, replacement] of LATEX_SYMBOLS) {
    result = result.replace(pattern, replacement);
  }
  return result;
};

const extractBalancedBraces = (text, openIndex) => {
  if (text[openIndex] !== '{') return null;
  let depth = 0;
  for (let i = openIndex; i < text.length; i += 1) {
    if (text[i] === '{') depth += 1;
    if (text[i] === '}') {
      depth -= 1;
      if (depth === 0) {
        return { inner: text.slice(openIndex + 1, i), end: i };
      }
    }
  }
  return null;
};

const convertLatexInner = (latex) => {
  let text = latex.trim();

  for (let pass = 0; pass < 30; pass += 1) {
    const fracIdx = text.indexOf('\\frac');
    if (fracIdx === -1) break;
    const numStart = fracIdx + 5;
    const num = extractBalancedBraces(text, numStart);
    if (!num) break;
    const den = extractBalancedBraces(text, num.end + 1);
    if (!den) break;
    const replacement = `(${convertLatexInner(num.inner)}) / (${convertLatexInner(den.inner)})`;
    text = text.slice(0, fracIdx) + replacement + text.slice(den.end + 1);
  }

  const convertBracedCommand = (commandPattern, replacer) => {
    text = text.replace(commandPattern, (match, ...groups) => {
      const inner = groups[0];
      return replacer(convertLatexInner(inner));
    });
  };

  convertBracedCommand(
    /\\(?:text|mathrm|textit|textrm|textbf|emph)\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}/g,
    (inner) => inner,
  );
  convertBracedCommand(
    /\\mathbf\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}/g,
    (inner) => `**${inner}**`,
  );
  convertBracedCommand(/\\sqrt\{([^{}]*)\}/g, (inner) => `√(${inner})`);

  // Simple superscript / subscript: x^{2}, x_2
  text = text.replace(/\^\{([^{}]+)\}/g, (_, exp) => {
    const map = { '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹', '-': '⁻', '+': '⁺' };
    return [...exp].map((c) => map[c] ?? c).join('');
  });
  text = text.replace(/\^([0-9+-])/g, (_, c) => {
    const map = { '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹', '-': '⁻', '+': '⁺' };
    return map[c] ?? c;
  });

  text = replaceLatexSymbols(text);
  text = text.replace(/\\[a-zA-Z]+/g, '');
  text = text.replace(/\\./g, '');
  text = text.replace(/[{}]/g, '');

  return text.replace(/\s{2,}/g, ' ').trim();
};

const convertMathDelimiters = (content) => {
  let text = content;

  const convertBlock = (inner) => {
    const converted = convertLatexInner(inner);
    if (!converted) return '';
    return `\n\n**${converted}**\n\n`;
  };

  text = text.replace(/\$\$([\s\S]*?)\$\$/g, (_, inner) => convertBlock(inner));
  text = text.replace(/\\\[([\s\S]*?)\\\]/g, (_, inner) => convertBlock(inner));

  text = text.replace(/(?<!\$)\$(?!\$)([^$\n]+?)\$(?!\$)/g, (_, inner) => convertLatexInner(inner));
  text = text.replace(/\\\(([^)]+?)\\\)/g, (_, inner) => convertLatexInner(inner));

  return text;
};

const parseTableCells = (line) => {
  const trimmed = line.trim();
  const normalized = trimmed.startsWith('|') ? trimmed : `| ${trimmed}`;
  const withEnd = normalized.endsWith('|') ? normalized : `${normalized} |`;
  return withEnd
    .split('|')
    .map((c) => c.trim())
    .filter((_, idx, arr) => idx > 0 && idx < arr.length - 1);
};

const isTableRow = (line) => {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith('```')) return false;
  const cells = parseTableCells(trimmed);
  return cells.length >= 2;
};

const isSeparatorRow = (cells) =>
  cells.length > 0 && cells.every((cell) => /^:?-{2,}:?$/.test(cell));

const isJunkTableRow = (cells) =>
  cells.length > 0 &&
  cells.every((cell) => !cell || /^[:.\-–—\s]+$/.test(cell));

const buildSeparator = (colCount) =>
  `| ${Array.from({ length: colCount }, () => '---').join(' | ')} |`;

/** Repair broken markdown tables from AI output */
export const fixMarkdownTables = (content) => {
  if (!content) return '';
  const lines = content.split('\n');
  const out = [];
  let i = 0;

  while (i < lines.length) {
    if (!isTableRow(lines[i])) {
      out.push(lines[i]);
      i += 1;
      continue;
    }

    const tableLines = [];
    while (i < lines.length && isTableRow(lines[i])) {
      tableLines.push(lines[i]);
      i += 1;
    }

    const parsed = tableLines.map((line) => parseTableCells(line));
    const colCount = Math.max(...parsed.map((row) => row.length), 1);
    const padded = parsed.map((row) => {
      const next = [...row];
      while (next.length < colCount) next.push('');
      return next;
    });

    const separatorIndex = padded.findIndex(isSeparatorRow);
    const header = padded[0];
    const body = padded
      .slice(1)
      .filter((row, index) => index + 1 !== separatorIndex)
      .filter((row) => !isJunkTableRow(row));

    out.push(`| ${header.join(' | ')} |`);
    out.push(
      separatorIndex >= 0
        ? `| ${padded[separatorIndex].join(' | ')} |`
        : buildSeparator(colCount),
    );
    body.forEach((row) => out.push(`| ${row.join(' | ')} |`));
  }

  return out.join('\n');
};

const stripSystemJsonBlocks = (content) =>
  content.replace(SYSTEM_JSON_PATTERN, (block, inner) => {
    try {
      const parsed = JSON.parse(inner.trim());
      if (isSystemCommandPayload(parsed)) return '';
    } catch {
      /* keep non-system json blocks */
    }
    return block;
  });

/**
 * Extract chart, report and Visualization proposal payloads from raw AI content.
 * @param {string} content
 * @returns {Array<Record<string, unknown>>}
 */
export const extractSystemCommands = (content) => {
  if (!content) return [];
  const commands = [];
  let match;
  SYSTEM_JSON_PATTERN.lastIndex = 0;
  while ((match = SYSTEM_JSON_PATTERN.exec(content)) !== null) {
    try {
      const parsed = JSON.parse(match[1].trim());
      if (isSystemCommandPayload(parsed)) {
        commands.push(parsed);
      }
    } catch {
      /* ignore partial/invalid json while streaming */
    }
  }
  const hasVisualizationProposal = commands.some(
    (command) => command.action === 'propose_visualization',
  );
  if (!hasVisualizationProposal) return commands;

  // A dashboard proposal supersedes chart snapshots in the same Chat response.
  // The full set of widgets is rendered only after it is saved in Visualizations.
  return commands.filter((command) => command.action !== 'render_chart');
};

const processTextSegment = (segment) => {
  let text = normalizeEscapes(segment);
  text = text.replace(INTERNAL_CONTEXT_TAG_PATTERN, '');
  text = text.replace(INTERNAL_CONTEXT_LABEL_PATTERN, '');
  text = text.replace(SECTION_HEADING_PATTERN, (_, heading) => `### ${heading}`);
  text = convertMathDelimiters(text);
  text = replaceLatexSymbols(text);
  text = fixMarkdownTables(text);
  return text;
};

/**
 * @param {string | null | undefined} content
 * @returns {string}
 */
export const sanitizeMessageContent = (content) => {
  if (!content) return '';

  const parts = [];
  let lastIndex = 0;
  let match;

  FENCED_CODE_PATTERN.lastIndex = 0;
  while ((match = FENCED_CODE_PATTERN.exec(content)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'text', value: content.slice(lastIndex, match.index) });
    }
    parts.push({ type: 'code', value: match[0] });
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < content.length) {
    parts.push({ type: 'text', value: content.slice(lastIndex) });
  }

  if (parts.length === 0) {
    parts.push({ type: 'text', value: content });
  }

  const sanitized = parts
    .map(({ type, value }) => (type === 'code' ? value : processTextSegment(value)))
    .join('');

  return sanitized.replace(/\n{3,}/g, '\n\n').trim();
};

/**
 * @param {string | null | undefined} content
 * @returns {{ displayText: string, commands: Array<Record<string, unknown>> }}
 */
export const prepareAiMessageContent = (content) => {
  const commands = extractSystemCommands(content || '');
  const displayText = cleanMsgContent(content);
  return { displayText, commands };
};

/**
 * @param {string | null | undefined} content
 * @returns {string}
 */
export const cleanMsgContent = (content) => {
  if (!content) return '';
  let cleaned = sanitizeMessageContent(content);
  cleaned = stripSystemJsonBlocks(cleaned);
  cleaned = cleaned.replace(
    /(?:\r?\n)*[📉🎨📊📈\s]*\d+\.?\s*(?:การแสดงผลด้วยภาพ|Visualizations|การวาดกราฟ)[\s\S]*?(?=\r?\n\s*(?:[#\d📈📉🎨📊]|\r?\n|$))/giu,
    '',
  );
  return cleaned.trim();
};

/**
 * Try parsing a JSON code block as a system command (for streaming markdown renderer).
 * @param {string} rawContent
 * @returns {Record<string, unknown> | null}
 */
export const tryParseSystemCommand = (rawContent) => {
  const trimmed = rawContent.trim();
  if (!trimmed.startsWith('{')) return null;
  const looksLikeSystem =
    trimmed.includes('"action"') ||
    trimmed.includes('"render_chart"') ||
    trimmed.includes('"generate_report"') ||
    trimmed.includes('"propose_visualization"');
  if (!looksLikeSystem) return null;
  try {
    const parsed = JSON.parse(trimmed.replace(/\n$/, ''));
    return isSystemCommandPayload(parsed) ? parsed : null;
  } catch {
    return looksLikeSystem && trimmed.length < 120 ? { action: '__streaming__' } : null;
  }
};

/**
 * @param {{ role?: string, content?: string } & Record<string, unknown>} message
 */
export const sanitizeChatMessage = (message) => {
  if (!message) return message;
  const branchFields = {
    ...(message.branch_id ? { branchId: message.branch_id } : {}),
    ...(message.client_request_id ? { clientRequestId: message.client_request_id } : {}),
    ...(message.origin_message_id ? { originMessageId: message.origin_message_id } : {}),
  };
  const role = message.role;
  if (role !== 'ai' && role !== 'assistant') {
    return {
      ...message,
      ...branchFields,
      ...(message.response_metadata?.attachment
        ? { attachment: message.response_metadata.attachment }
        : {}),
      ...(message.response_metadata?.column_mapping
        ? { attachmentMapping: message.response_metadata.column_mapping }
        : {}),
      ...(message.response_metadata?.cleaning_recipe
        ? { attachmentCleaningRecipe: message.response_metadata.cleaning_recipe }
        : {}),
      ...(message.response_metadata?.cleaning_profile
        ? { attachmentCleaningProfile: message.response_metadata.cleaning_profile }
        : {}),
      ...(message.response_metadata?.connection
        ? { connectionContext: message.response_metadata.connection }
        : {}),
      ...(message.response_metadata?.orchestration_resolution
        ? { workflowResolution: message.response_metadata.orchestration_resolution }
        : {}),
    };
  }
  return {
    ...message,
    ...branchFields,
    content: sanitizeMessageContent(message.content),
    ...(Array.isArray(message.web_sources)
      ? { webSources: message.web_sources }
      : {}),
    ...(message.verification ? { verification: message.verification } : {}),
    ...(message.model_used ? { modelUsed: message.model_used } : {}),
    ...(message.response_metadata?.routing
      ? { routing: message.response_metadata.routing }
      : {}),
    ...(message.response_metadata?.response_mode
      ? { responseMode: message.response_metadata.response_mode }
      : {}),
    ...(Array.isArray(message.response_metadata?.search_queries)
      ? { searchQueries: message.response_metadata.search_queries }
      : {}),
    ...(Array.isArray(message.response_metadata?.reasoning_trace)
      ? { reasoningTrace: message.response_metadata.reasoning_trace }
      : {}),
    ...(message.response_metadata?.analysis_audit
      ? { analysisAudit: message.response_metadata.analysis_audit }
      : {}),
    ...(message.response_metadata?.tool_execution
      ? { toolExecution: message.response_metadata.tool_execution }
      : {}),
    ...(message.response_metadata?.orchestration
      ? { orchestration: message.response_metadata.orchestration }
      : {}),
    ...(message.response_metadata?.setup_awaiting_user
      ? { setupAwaitingUser: true }
      : {}),
  };
};
