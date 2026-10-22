import { getStepLabel } from './reasoningProgress.js';

type AgentThinkingIndicatorProps = {
  elapsedSec?: number;
  isEn?: boolean;
  stage?: string | null;
  detail?: Record<string, unknown>;
  /** Optional override (e.g. setup controllerActivity). */
  label?: string | null;
  t?: (key: string, fallback: string, vars?: Record<string, string | number>) => string;
};

export default function AgentThinkingIndicator({
  elapsedSec = 0,
  isEn = false,
  stage = null,
  detail = {},
  label = null,
  t = (_key, fallback) => fallback,
}: AgentThinkingIndicatorProps) {
  const fallback = isEn ? 'MataQorLab is thinking…' : 'MataQorLab กำลังคิด…';
  const status = (label && String(label).trim())
    || (stage ? getStepLabel(stage, detail || {}, isEn, t) : null)
    || fallback;
  const elapsedLabel = elapsedSec > 0
    ? (isEn ? `${elapsedSec}s` : `${elapsedSec} วินาที`)
    : null;

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={elapsedLabel ? `${status} ${elapsedLabel}` : status}
      data-testid="agent-thinking-indicator"
      className="mb-8 flex justify-start"
    >
      <div className="inline-flex items-center gap-2 text-stone-500 dark:text-stone-400">
        <span className="flex items-center gap-1" aria-hidden="true">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-orange-400 [animation-delay:-0.2s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-orange-400 [animation-delay:-0.1s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-orange-400" />
        </span>
        {elapsedLabel && (
          <span className="text-[11px] tabular-nums text-stone-400 dark:text-stone-500">
            {elapsedLabel}
          </span>
        )}
      </div>
    </div>
  );
}
