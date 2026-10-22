// @ts-nocheck
import { useEffect, useState } from 'react';
import { ArrowUp, ArrowUpRight, MessageSquare, LoaderCircle } from '@/components/icons';
import { workflowStepLabel } from './labels.js';
import {
  buildFreeTextResolutionSendOptions,
  buildResolutionSendOptions,
  fallbackOptionsForDecision,
} from './normalize.js';

/**
 * Structured ask_user / awaiting_user options.
 * Buttons send chat resolutions — never call tools directly.
 */
export default function WorkflowQuestionCard({
  awaitingUser,
  options = [],
  isEn = false,
  animateQuestion = false,
  disabled = false,
  decisionStatus = 'pending',
  onResolve,
}) {
  const [pendingValue, setPendingValue] = useState(null);
  const [textValue, setTextValue] = useState('');
  const [typedQuestion, setTypedQuestion] = useState('');
  const decisionKey = awaitingUser?.decisionKey || awaitingUser?.decision_key || null;
  const rawOpts = (awaitingUser?.options?.length ? awaitingUser.options : options) || [];
  const opts = rawOpts.length
    ? rawOpts
    : fallbackOptionsForDecision(decisionKey, isEn);
  const questionText = String(awaitingUser?.question || '').trim();
  // Skip typing animation when we had to invent controls — user must answer now.
  const shouldAnimate = Boolean(animateQuestion && rawOpts.length > 0);
  const [typingComplete, setTypingComplete] = useState(!shouldAnimate);

  useEffect(() => {
    setPendingValue(null);
    setTextValue('');
  }, [decisionKey, decisionStatus]);

  useEffect(() => {
    if (!shouldAnimate) {
      setTypedQuestion(questionText);
      setTypingComplete(true);
      return undefined;
    }

    const characters = Array.from(questionText);
    let intervalId;
    let safetyId;
    setTypedQuestion('');
    setTypingComplete(false);
    const startId = window.setTimeout(() => {
      const startedAt = window.performance.now();
      const durationMs = Math.min(1400, Math.max(520, characters.length * 18));
      intervalId = window.setInterval(() => {
        const elapsed = window.performance.now() - startedAt;
        const index = Math.min(
          characters.length,
          Math.max(1, Math.ceil((elapsed / durationMs) * characters.length)),
        );
        setTypedQuestion(characters.slice(0, index).join(''));
        if (index >= characters.length) {
          window.clearInterval(intervalId);
          setTypingComplete(true);
        }
      }, 24);
      // Fail-safe for throttled/background tabs: controls must never remain
      // permanently gated by a decorative typing animation.
      safetyId = window.setTimeout(() => {
        window.clearInterval(intervalId);
        setTypedQuestion(questionText);
        setTypingComplete(true);
      }, 2200);
    }, 120);

    return () => {
      window.clearTimeout(startId);
      if (intervalId) window.clearInterval(intervalId);
      if (safetyId) window.clearTimeout(safetyId);
    };
  }, [shouldAnimate, decisionKey, questionText]);

  if (!awaitingUser && !options?.length) return null;
  if (!questionText) return null;

  const reason = awaitingUser?.reasonCode || awaitingUser?.reason_code;
  const isConfirmation = [
    'AGGRESSIVE_CLEANING',
    'AMBIGUOUS_MAPPING',
    'BUSINESS_CONTRACT_CHANGE',
  ].includes(reason);

  const title = isConfirmation
    ? (isEn ? 'Confirmation required' : 'ต้องการการยืนยัน')
    : (awaitingUser?.stepType || awaitingUser?.step_type
      ? workflowStepLabel(awaitingUser.stepType || awaitingUser.step_type, isEn)
      : (isEn ? 'Need your input' : 'ต้องการข้อมูลจากคุณ'));

  const question = questionText;

  const contextBits = [];
  const ctx = awaitingUser?.context;
  if (ctx && typeof ctx === 'object') {
    if (ctx.count != null) {
      contextBits.push(
        isEn
          ? `Found ${Number(ctx.count).toLocaleString()} items`
          : `พบ ${Number(ctx.count).toLocaleString()} รายการ`,
      );
    }
    if (ctx.pct != null || ctx.percent != null) {
      const pct = ctx.pct ?? ctx.percent;
      contextBits.push(isEn ? `${pct}% of rows` : `คิดเป็น ${pct}% ของข้อมูล`);
    }
    if (ctx.column) contextBits.push(String(ctx.column));
    if (ctx.note) contextBits.push(String(ctx.note));
  }

  const isPending = decisionStatus === 'pending';
  const isSubmitting = decisionStatus === 'submitting' || pendingValue != null;
  // Decorative typing must gate controls until complete (or the 2.2s fail-safe).
  const busy = disabled || isSubmitting || !isPending || !typingComplete;

  const handleClick = async (option) => {
    if (busy || !onResolve) return;
    setPendingValue(option.value);
    try {
      await onResolve(buildResolutionSendOptions(option, awaitingUser));
    } catch {
      setPendingValue(null);
    }
  };

  const handleTextSubmit = async (event) => {
    event.preventDefault();
    const answer = textValue.trim();
    if (!answer || busy || !onResolve) return;
    setPendingValue(`custom:${answer}`);
    try {
      await onResolve(buildFreeTextResolutionSendOptions(answer, awaitingUser));
    } catch {
      setPendingValue(null);
    }
  };

  const expectedInput = String(
    awaitingUser?.expectedInput || awaitingUser?.expected_input || '',
  ).toLowerCase();
  // Never render a dead card: if there are no options, keep free-text open.
  const freeTextAllowed = opts.length === 0
    || (
      awaitingUser?.freeTextAllowed !== false
      && awaitingUser?.free_text_allowed !== false
      && expectedInput !== 'single_choice'
    );
  const incompleteChoice = (expectedInput === 'single_choice' || expectedInput === 'option_or_text')
    && opts.length === 0
    && !freeTextAllowed;

  if (incompleteChoice) {
    return (
      <section
        className="chat-decision-card not-prose mt-4 rounded-2xl border border-slate-200/90 bg-slate-50/70 px-4 py-4 dark:border-slate-700 dark:bg-slate-900/75"
        data-decision-key={decisionKey || undefined}
        data-testid="incomplete-active-decision"
      >
        <p className="text-sm font-medium text-stone-800 dark:text-stone-100">
          {isEn ? 'Question data is incomplete' : 'ข้อมูลคำถามไม่สมบูรณ์'}
        </p>
      </section>
    );
  }

  return (
    <section
      className={`chat-decision-card not-prose mt-4 overflow-hidden rounded-2xl border px-4 py-4 sm:px-5 ${
        isConfirmation
          ? 'border-indigo-200/80 bg-indigo-50/50 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-slate-700/80 dark:bg-[#161922] dark:shadow-[0_12px_28px_rgba(0,0,0,0.18)]'
          : 'border-slate-200 bg-white/80 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-slate-700/80 dark:bg-[#17191f] dark:shadow-[0_12px_28px_rgba(0,0,0,0.16)]'
      }`}
      aria-label={title}
      role="group"
      data-decision-key={decisionKey || undefined}
      data-typing={shouldAnimate && !typingComplete ? 'true' : 'false'}
    >
      <div className="flex items-start gap-3">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-stone-200 bg-stone-50 text-stone-600 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-300">
          <MessageSquare size={16} strokeWidth={1.8} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold tracking-wide text-stone-600 dark:text-stone-300">
            {title}
          </p>
          {reason === 'AGGRESSIVE_CLEANING' && (
            <p className="mt-0.5 text-xs font-medium text-stone-500 dark:text-stone-400">
              Deep Clean
            </p>
          )}
          <p
            className="relative mt-2 text-[15px] font-medium leading-relaxed text-slate-900 whitespace-pre-wrap dark:text-slate-100"
            aria-label={question}
            aria-live="polite"
          >
            {shouldAnimate && (
              <span className="invisible" aria-hidden="true">{question}</span>
            )}
            <span
              className={shouldAnimate ? 'absolute inset-0' : undefined}
              aria-hidden={shouldAnimate ? 'true' : undefined}
            >
              {shouldAnimate ? typedQuestion : question}
              {shouldAnimate && !typingComplete && (
                <span className="ml-0.5 inline-block h-[1em] w-[2px] animate-pulse bg-indigo-500 align-[-0.08em]" />
              )}
            </span>
          </p>
        </div>
      </div>
      {contextBits.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5 pl-0 sm:pl-11">
          {contextBits.map((bit) => (
            <span key={bit} className="rounded-full bg-stone-100 px-2.5 py-1 text-[11px] font-medium text-stone-600 dark:bg-stone-800 dark:text-stone-300">
              {bit}
            </span>
          ))}
        </div>
      )}
      {isPending && opts.length > 0 && onResolve && (
        <div className="mt-4 grid gap-2 sm:pl-11">
          {opts.map((option) => (
            <button
              key={option.id || option.value}
              type="button"
              disabled={busy}
              aria-busy={pendingValue === option.value}
              onClick={() => handleClick(option)}
              className="group/decision inline-flex min-h-11 w-full items-center justify-between gap-3 rounded-xl border border-stone-200 bg-white/85 px-3.5 py-2.5 text-left text-sm font-semibold text-stone-700 transition-colors hover:border-indigo-300 hover:bg-indigo-50/60 hover:text-stone-950 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-stone-700 dark:bg-stone-950/55 dark:text-stone-200 dark:hover:border-indigo-800 dark:hover:bg-indigo-950/25 dark:hover:text-white"
            >
              <span>
                <span className="block">{option.label}</span>
                {option.description && (
                  <span className="mt-0.5 block text-xs font-normal text-stone-500 dark:text-stone-400">
                    {option.description}
                  </span>
                )}
              </span>
              {pendingValue === option.value ? (
                <LoaderCircle size={15} className="shrink-0 animate-spin text-indigo-600" />
              ) : (
                <ArrowUpRight size={15} className="shrink-0 text-stone-400 transition-transform group-hover/decision:-translate-y-0.5 group-hover/decision:translate-x-0.5 group-hover/decision:text-indigo-600" />
              )}
            </button>
          ))}
        </div>
      )}
      {isPending && onResolve && freeTextAllowed && (
        <form
          className="mt-3 sm:pl-11"
          onSubmit={handleTextSubmit}
          aria-label={isEn ? 'Custom answer' : 'พิมพ์คำตอบเอง'}
        >
          <div className="flex items-end gap-2 rounded-xl border border-stone-200 bg-white p-1.5 focus-within:border-indigo-400 focus-within:ring-2 focus-within:ring-indigo-100 dark:border-stone-700 dark:bg-stone-950/55 dark:focus-within:border-indigo-700 dark:focus-within:ring-indigo-950/50">
            <textarea
              value={textValue}
              disabled={busy}
              rows={1}
              onChange={(event) => setTextValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder={isEn ? 'Type your own answer…' : 'พิมพ์คำตอบเอง…'}
              aria-label={isEn ? 'Type your own answer' : 'พิมพ์คำตอบเอง'}
              className="min-h-9 max-h-28 flex-1 resize-y bg-transparent px-2 py-2 text-sm leading-5 text-stone-900 outline-none placeholder:text-stone-400 disabled:cursor-not-allowed disabled:opacity-50 dark:text-stone-100 dark:placeholder:text-stone-500"
            />
            <button
              type="submit"
              disabled={busy || !textValue.trim()}
              aria-label={isEn ? 'Send custom answer' : 'ส่งคำตอบที่พิมพ์'}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white transition-colors hover:bg-indigo-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 disabled:cursor-not-allowed disabled:bg-stone-200 disabled:text-stone-400 dark:disabled:bg-stone-800 dark:disabled:text-stone-600"
            >
              {pendingValue?.startsWith?.('custom:') ? (
                <LoaderCircle size={15} className="animate-spin" />
              ) : (
                <ArrowUp size={16} strokeWidth={2} />
              )}
            </button>
          </div>
          <p className="mt-1.5 text-[11px] text-stone-500 dark:text-stone-400">
            {isEn
              ? 'Enter to send · Shift+Enter for a new line'
              : 'Enter เพื่อส่ง · Shift+Enter เพื่อขึ้นบรรทัดใหม่'}
          </p>
        </form>
      )}
    </section>
  );
}
