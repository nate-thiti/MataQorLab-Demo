import { inferErrorStatus } from './chatErrors.js';
import { extractSystemCommands } from './messageContent.js';
import { createCorrelationId } from '../../utils/correlation.js';
import { getClientLocale } from '../../utils/locale.js';

const commandKey = (command) => JSON.stringify(command);

/**
 * Numeric correction can replace the final narration returned by the `done`
 * event. Preserve validated UI commands that were already received as streamed
 * tokens so charts/reports do not disappear when the final message replaces
 * the temporary streaming message.
 */
export const preserveStreamedSystemCommands = (streamedContent, finalContent) => {
  const streamedCommands = extractSystemCommands(streamedContent || '');
  if (streamedCommands.length === 0) return finalContent || streamedContent || '';

  const finalCommands = new Set(
    extractSystemCommands(finalContent || '').map(commandKey),
  );
  const finalHasVisualizationProposal = extractSystemCommands(finalContent || '')
    .some((command) => command.action === 'propose_visualization');
  const missingBlocks = streamedCommands
    .filter((command) => (
      !finalHasVisualizationProposal
      || command.action === 'propose_visualization'
    ))
    .filter((command) => !finalCommands.has(commandKey(command)))
    .map((command) => `\`\`\`json\n${JSON.stringify(command, null, 2)}\n\`\`\``);

  if (missingBlocks.length === 0) return finalContent || streamedContent || '';
  return [finalContent || '', ...missingBlocks].filter(Boolean).join('\n\n');
};

/**
 * Consume POST /api/v1/chat/stream SSE response.
 * @param {string} url
 * @param {object} payload
 * @param {AbortSignal} signal
 * @param {{ onStatus?: (stage: string, detail?: Record<string, unknown>) => void, onToken?: (content: string) => void }} handlers
 */
export async function consumeChatStream(url, payload, signal, handlers = {}) {
  const locale = getClientLocale();
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: payload.authorization,
      'X-Correlation-ID': payload.correlationId || createCorrelationId(),
      'Accept-Language': locale,
      'X-User-Locale': locale,
    },
    body: JSON.stringify(payload.body),
    signal,
  });

  if (!response.ok) {
    let detail = `Server responded with status: ${response.status}`;
    let quotaDetail = null;
    try {
      const data = await response.json();
      if (typeof data.detail === 'string') {
        detail = data.detail;
      } else if (data.detail && typeof data.detail === 'object') {
        quotaDetail = data.detail;
        detail = data.detail.message || detail;
      }
    } catch {
      /* ignore */
    }
    const error = new Error(detail);
    error.status = response.status;
    if (quotaDetail) error.quotaDetail = quotaDetail;
    throw error;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result = {
    content: '',
    usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
    model_used: null,
    agent_paused: false,
    agent_session_id: null,
    agent_reason: null,
    verification: null,
    routing: null,
    response_mode: null,
    search_queries: [],
    latency_ms: null,
    analysis_audit: null,
    tool_execution: null,
    finish_reason: null,
    generation_continuations: 0,
    generation_truncated: false,
    orchestration: null,
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const segments = buffer.split('\n\n');
    buffer = segments.pop() || '';

    for (const segment of segments) {
      const line = segment.trim();
      if (!line.startsWith('data: ')) continue;

      const event = JSON.parse(line.slice(6));

      if (event.type === 'status' && event.stage) {
        handlers.onStatus?.(event.stage, event.detail || {});
      }

      if (event.type === 'agent_pause') {
        result.agent_paused = true;
        result.agent_session_id = event.session_id ?? null;
        result.agent_reason = event.reason ?? null;
        if (event.question) {
          result.content = event.question;
        }
      }

      if (event.type === 'token' && event.content) {
        result.content += event.content;
        handlers.onToken?.(event.content);
      }

      if (event.type === 'done') {
        result.content = preserveStreamedSystemCommands(
          result.content,
          event.message?.content ?? result.content,
        );
        result.usage = event.usage ?? result.usage;
        result.model_used = event.model_used ?? null;
        result.verification = event.verification ?? null;
        result.routing = event.routing ?? null;
        result.response_mode = event.response_mode ?? null;
        result.search_queries = event.search_queries ?? [];
        result.latency_ms = event.latency_ms ?? null;
        result.analysis_audit = event.analysis_audit ?? null;
        result.tool_execution = event.tool_execution ?? null;
        result.finish_reason = event.finish_reason ?? null;
        result.generation_continuations = event.generation_continuations ?? 0;
        result.generation_truncated = event.generation_truncated === true;
        if (event.agent_paused) {
          result.agent_paused = true;
          result.agent_session_id = event.agent_session_id ?? result.agent_session_id;
          result.agent_reason = event.agent_reason ?? result.agent_reason;
        }
        if (event.orchestration) {
          result.orchestration = event.orchestration;
        }
      }

      if (event.type === 'orchestration' && event.orchestration) {
        result.orchestration = event.orchestration;
      }

      if (event.type === 'error') {
        const detail = event.detail || 'Stream error';
        const error = new Error(detail);
        if (event.code === 'rate_limit') {
          error.status = 429;
        } else if (event.code === 'llm_credits') {
          error.status = 402;
        } else if (event.code === 'provider_unavailable') {
          error.status = 404;
        } else if (event.code === 'file_error') {
          error.status = 400;
        } else if (event.code === 'server_error') {
          error.status = 503;
        } else {
          error.status = inferErrorStatus(detail);
        }
        throw error;
      }
    }
  }

  return result;
}
