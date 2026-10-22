export { WORKFLOW_STEP_ORDER, workflowStepLabel, workflowStatusLabel, runningStepCopy } from './labels.js';
export {
  normalizeOrchestration,
  buildResolutionSendOptions,
  buildFreeTextResolutionSendOptions,
  buildRetrySendOptions,
  inferDecisionFromValue,
  isConversationalSetupActive,
  compactProgressView,
} from './normalize.js';
export { default as WorkflowProgress } from './WorkflowProgress';
export { default as WorkflowQuestionCard } from './WorkflowQuestionCard';
export { default as ToolResultCard } from './ToolResultCard';
export { default as WorkflowErrorCard } from './WorkflowErrorCard';
export { default as ReadyForAnalysisCard } from './ReadyForAnalysisCard';
export { default as WorklogStampCard } from './WorklogStampCard';
export { default as WorklogStampStack } from './WorklogStampStack';
export { buildSetupAuditPresentation } from './setupAuditPresentation.js';
export { default as OrchestrationMessage } from './OrchestrationMessage';
export { default as CurrentWorkflowPanel } from './CurrentWorkflowPanel';
export { default as ResolvedQuestionSummary } from './ResolvedQuestionSummary';
export {
  reconcileSetupState,
  payloadToCurrentOrchestrationState,
  deriveLiveAwaitingUser,
  shouldPollSetupState,
  createEmptyCurrentOrchestrationState,
  resetReconcileSequenceForTests,
  buildStateFingerprint,
  pollIntervalMs,
  NO_PROGRESS_POLL_THRESHOLD,
} from './reconcileSetupState.js';
export { useSetupReconciliation } from './useSetupReconciliation.js';

/**
 * Frontend may hint via NEXT_PUBLIC_*, but backend /capabilities is authoritative.
 * When unset, leave null so Chat waits for capabilitiesReady before kickoff —
 * never assume conversational setup is on while the BE flag may be off.
 */
export function readLocalConversationalFlag() {
  try {
    const value = process.env.NEXT_PUBLIC_ENABLE_CONVERSATIONAL_DATA_SETUP;
    if (value == null || value === '') return null;
    return value === 'true' || value === '1';
  } catch {
    return null;
  }
}
