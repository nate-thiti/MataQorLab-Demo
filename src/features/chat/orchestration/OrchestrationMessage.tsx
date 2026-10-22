// @ts-nocheck
import { normalizeOrchestration } from './normalize.js';
import { runningStepCopy } from './labels.js';
import ToolResultCard from './ToolResultCard';
import WorklogStampCard from './WorklogStampCard';
import WorklogStampStack from './WorklogStampStack';
import ResolvedQuestionSummary from './ResolvedQuestionSummary';

function stampPayload(stamp) {
  return {
    stamp_id: stamp.stampId,
    stamp_type: stamp.stampType,
    status: stamp.status,
    title: stamp.title,
    summary: stamp.summary,
    facts: stamp.facts,
    source: stamp.source,
  };
}

/**
 * Historical orchestration audit view for one assistant message.
 * Live workflow controls live in CurrentWorkflowPanel only.
 *
 * Rule: historical orchestration metadata is audit context;
 * latest backend orchestration state is interactive state.
 */
export default function OrchestrationMessage({
  orchestration,
  isEn = false,
  historical = true,
  resolvedAnswerLabel = null,
  hideUnresolvedQuestion = false,
}) {
  const view = normalizeOrchestration(orchestration, isEn);
  if (!view) return null;

  const runningStep = view.workflow?.steps?.find((s) => s.status === 'running');

  return (
    <div className="not-prose space-y-2">
      {runningStep && !view.awaitingUser && (
        <p
          className="text-sm text-amber-800 dark:text-amber-200"
          aria-live="polite"
        >
          {runningStepCopy(runningStep.stepType, isEn)}
        </p>
      )}

      {view.toolResult
        && view.toolResult.status !== 'failed'
        && (
          <ToolResultCard toolResult={view.toolResult} isEn={isEn} />
        )}

      {Array.isArray(view.worklogStamps) && view.worklogStamps.length === 1 && (
        <WorklogStampCard
          stamp={stampPayload(view.worklogStamps[0])}
          isEn={isEn}
        />
      )}

      {Array.isArray(view.worklogStamps) && view.worklogStamps.length > 1 && (
        <WorklogStampStack
          stamps={view.worklogStamps.map(stampPayload)}
          isEn={isEn}
        />
      )}

      {historical && view.awaitingUser
        && (!hideUnresolvedQuestion || Boolean(resolvedAnswerLabel)) && (
        <ResolvedQuestionSummary
          awaitingUser={view.awaitingUser}
          answerLabel={resolvedAnswerLabel}
          isEn={isEn}
          resolved={Boolean(resolvedAnswerLabel)}
        />
      )}
    </div>
  );
}
