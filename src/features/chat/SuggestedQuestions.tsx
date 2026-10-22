// @ts-nocheck
import { useEffect, useState } from 'react';
import { ArrowUpRight } from '@/components/icons';

export function shouldShowSuggestedQuestions({
  isLatestAssistant,
  failed,
  isGenerating,
  conversationalSetupActive,
  promptCount,
  hasHandler,
}) {
  return Boolean(
    isLatestAssistant
    && !failed
    && !isGenerating
    && !conversationalSetupActive
    && promptCount > 0
    && hasHandler,
  );
}

export default function SuggestedQuestions({
  prompts = [],
  isEn = false,
  disabled = false,
  onSelect,
}) {
  const [pendingPrompt, setPendingPrompt] = useState(null);

  useEffect(() => {
    if (!disabled) setPendingPrompt(null);
  }, [disabled, prompts]);

  if (!prompts.length || !onSelect) return null;

  const handleSelect = async (prompt) => {
    if (disabled || pendingPrompt) return;
    setPendingPrompt(prompt);
    try {
      await onSelect(prompt);
    } catch {
      setPendingPrompt(null);
    }
  };

  return (
    <section
      className="chat-suggestions not-prose mt-6"
      aria-label={isEn ? 'Suggested follow-up questions' : 'คำถามต่อยอดที่แนะนำ'}
    >
      <div className="mb-2.5 px-1 text-[11px] font-semibold text-stone-500 dark:text-stone-400">
        {isEn ? 'Continue exploring' : 'สำรวจต่อจากคำตอบนี้'}
      </div>
      <div className="grid gap-2">
        {prompts.slice(0, 3).map((prompt) => {
          const isPending = pendingPrompt === prompt;
          return (
            <button
              key={prompt}
              type="button"
              disabled={disabled || Boolean(pendingPrompt)}
              aria-busy={isPending}
              onClick={() => handleSelect(prompt)}
              className="group/suggestion flex min-h-11 w-full items-center justify-between gap-3 rounded-xl border border-stone-200/90 bg-white/65 px-3.5 py-2.5 text-left text-sm font-medium leading-snug text-stone-700 transition-colors hover:border-orange-300 hover:bg-orange-50/55 hover:text-stone-950 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500 disabled:cursor-not-allowed disabled:opacity-55 dark:border-stone-700/80 dark:bg-stone-900/45 dark:text-stone-200 dark:hover:border-orange-800 dark:hover:bg-orange-950/25 dark:hover:text-white"
            >
              <span>{prompt}</span>
              <ArrowUpRight
                size={15}
                className={`shrink-0 text-stone-400 transition-transform group-hover/suggestion:-translate-y-0.5 group-hover/suggestion:translate-x-0.5 group-hover/suggestion:text-orange-600 dark:group-hover/suggestion:text-orange-400 ${isPending ? 'animate-pulse text-orange-600' : ''}`}
                strokeWidth={1.8}
              />
            </button>
          );
        })}
      </div>
    </section>
  );
}
