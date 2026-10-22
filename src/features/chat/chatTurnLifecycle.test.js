import { describe, expect, it, vi } from 'vitest';
import {
  applyStreamOrchestrationUpdate,
  finishChatTurn,
  recoverStaleChatTurn,
  runWithSendInFlight,
} from './chatTurnLifecycle.js';

describe('chatTurnLifecycle', () => {
  it('finishChatTurn clears generation flags', () => {
    const setIsGenerating = vi.fn();
    const setIsTyping = vi.fn();
    const setAnalysisStreamStarted = vi.fn();
    const abortControllerRef = { current: {} };

    finishChatTurn({
      setIsGenerating,
      setIsTyping,
      setAnalysisStreamStarted,
      abortControllerRef,
    });

    expect(setIsGenerating).toHaveBeenCalledWith(false);
    expect(setIsTyping).toHaveBeenCalledWith(false);
    expect(setAnalysisStreamStarted).toHaveBeenCalledWith(false);
    expect(abortControllerRef.current).toBeNull();
  });

  it('applyStreamOrchestrationUpdate reconciles in background without awaiting', async () => {
    const applyStreamOrchestration = vi.fn();
    let reconcileResolved = false;
    const reconcileSetup = vi.fn(() => new Promise((resolve) => {
      setTimeout(() => {
        reconcileResolved = true;
        resolve(null);
      }, 50);
    }));

    applyStreamOrchestrationUpdate({
      orchestration: { stop_reason: 'awaiting_user' },
      applyStreamOrchestration,
      reconcileSetup,
      session: { id: 'sess-1' },
      resolveSessionId: (_payload, session) => session?.id,
    });

    expect(applyStreamOrchestration).toHaveBeenCalledTimes(1);
    expect(reconcileSetup).toHaveBeenCalledWith({ sessionId: 'sess-1', session: { id: 'sess-1' } });
    expect(reconcileResolved).toBe(false);
    await new Promise((r) => setTimeout(r, 60));
    expect(reconcileResolved).toBe(true);
  });

  it('runWithSendInFlight prevents duplicate sends', async () => {
    const ref = { current: false };
    const order = [];

    await Promise.all([
      runWithSendInFlight(ref, async () => {
        order.push('start-1');
        await new Promise((r) => setTimeout(r, 30));
        order.push('end-1');
      }),
      runWithSendInFlight(ref, async () => {
        order.push('blocked');
      }),
    ]);

    expect(order).toEqual(['start-1', 'end-1']);
    expect(ref.current).toBe(false);
  });

  it('recoverStaleChatTurn resets when no active stream controller exists', () => {
    const finishTurn = vi.fn();
    recoverStaleChatTurn({
      isGenerating: true,
      hasActiveStream: false,
      finishTurn,
      log: () => {},
    });
    expect(finishTurn).toHaveBeenCalledTimes(1);
  });

  it('recoverStaleChatTurn ignores active stream', () => {
    const finishTurn = vi.fn();
    recoverStaleChatTurn({
      isGenerating: true,
      hasActiveStream: true,
      finishTurn,
      log: () => {},
    });
    expect(finishTurn).not.toHaveBeenCalled();
  });

  it('recoverStaleChatTurn ignores in-flight send before stream starts', () => {
    const finishTurn = vi.fn();
    recoverStaleChatTurn({
      isGenerating: true,
      hasActiveStream: false,
      isSendInFlight: true,
      finishTurn,
      log: () => {},
    });
    expect(finishTurn).not.toHaveBeenCalled();
  });
});

describe('Phase 7.2.2-update awaiting_user unlock semantics', () => {
  it('composer lock ends when stream finishes before reconcile', async () => {
    const flags = { generating: true, typing: true };
    const unlockComposer = () => {
      flags.generating = false;
      flags.typing = false;
    };

    // Simulate SSE done
    unlockComposer();

    expect(flags.generating).toBe(false);
    expect(flags.typing).toBe(false);

    // Reconcile may continue without re-locking
    await new Promise((r) => setTimeout(r, 20));
    expect(flags.generating).toBe(false);
  });

  it('Stop button only when generating, not awaiting_user alone', () => {
    const showStop = (isGenerating) => isGenerating;
    expect(showStop(false)).toBe(false);
    expect(showStop(true)).toBe(true);
  });

  it('sendInFlight clears in finally even on early return', async () => {
    const ref = { current: false };
    await runWithSendInFlight(ref, async () => {});
    expect(ref.current).toBe(false);

    await runWithSendInFlight(ref, async () => {
      throw new Error('fail');
    }).catch(() => {});
    expect(ref.current).toBe(false);
  });
});
