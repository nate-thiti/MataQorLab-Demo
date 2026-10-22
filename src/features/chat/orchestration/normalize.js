import { WORKFLOW_STEP_ORDER, workflowStepLabel } from './labels.js';

/**
 * Normalize Phase 5/6 orchestration payloads into a stable FE view.
 * Never invent step statuses — only surface backend-provided fields.
 */
export function normalizeOrchestration(raw, isEn = false) {
  if (!raw || typeof raw !== 'object') return null;

  const workflowRaw = raw.workflow || raw.workflow_plan || null;
  const steps = normalizeSteps(workflowRaw, isEn);
  const currentStep = workflowRaw?.current_step || workflowRaw?.currentStep || null;
  const sessionStatus = workflowRaw?.status || raw.session_status || null;

  const awaitingUser = raw.awaiting_user || raw.awaitingUser || null;
  const options = Array.isArray(raw.options) ? raw.options : (awaitingUser?.options || []);
  const toolResult = normalizeToolResult(raw.tool_result || raw.toolResult || raw.engine_result);
  const source = raw.source || null;
  const assurance = raw.assurance || null;
  const readyForAnalysis = Boolean(
    raw.ready_for_analysis
    ?? raw.readyForAnalysis
    ?? workflowRaw?.ready_for_analysis
    ?? sessionStatus === 'ready',
  );

  const stampsRaw = Array.isArray(raw.worklog_stamps)
    ? raw.worklog_stamps
    : (Array.isArray(raw.worklogStamps) ? raw.worklogStamps : []);

  return {
    decisionType: raw.decision_type || raw.decisionType || null,
    stepType: raw.step_type || raw.stepType || null,
    options: options.map((option) => normalizeOption(
      option,
      isEn,
      awaitingUser?.decision_key || awaitingUser?.decisionKey,
      awaitingUser?.reason_code || awaitingUser?.reasonCode,
    )).filter(Boolean),
    awaitingUser: awaitingUser
      ? {
        reasonCode: awaitingUser.reason_code || awaitingUser.reasonCode || null,
        question: localizeAwaitingQuestion(awaitingUser, isEn),
        stepType: awaitingUser.step_type || awaitingUser.stepType || null,
        decisionKey: awaitingUser.decision_key || awaitingUser.decisionKey || null,
        expectedInput: awaitingUser.expected_input || awaitingUser.expectedInput || null,
        freeTextAllowed: awaitingUser.free_text_allowed
          ?? awaitingUser.freeTextAllowed
          ?? null,
        context: awaitingUser.context || null,
        options: (awaitingUser.options || options).map((option) => normalizeOption(
          option,
          isEn,
          awaitingUser.decision_key || awaitingUser.decisionKey,
          awaitingUser.reason_code || awaitingUser.reasonCode,
        )).filter(Boolean),
      }
      : null,
    workflow: workflowRaw
      ? {
        sessionId: workflowRaw.session_id || workflowRaw.sessionId || null,
        status: sessionStatus,
        currentStep,
        steps,
        readyForAnalysis,
      }
      : null,
    toolResult,
    source: source
      ? {
        name: source.name || null,
        sourceType: source.source_type || source.sourceType || null,
        rowCount: source.row_count ?? source.rowCount ?? null,
        columnCount: source.column_count ?? source.columnCount ?? null,
        dateRange: source.date_range || source.dateRange || null,
        cleaningProfile: source.cleaning_profile || source.cleaningProfile || null,
      }
      : null,
    assurance: assurance
      ? {
        computation: assurance.computation || null,
        dataReadiness: assurance.data_readiness || assurance.dataReadiness || null,
        businessContext: assurance.business_context || assurance.businessContext || null,
        mappingConfirmed: assurance.mapping_confirmed ?? assurance.mappingConfirmed ?? null,
      }
      : null,
    worklogStamps: stampsRaw.map(normalizeStamp).filter(Boolean),
    readyForAnalysis,
    errorKind: classifyErrorKind(raw, toolResult, sessionStatus),
  };
}

function normalizeStamp(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const facts = Array.isArray(raw.facts)
    ? raw.facts.map((f) => ({
      label: f?.label || '',
      value: f?.value != null ? String(f.value) : '',
    })).filter((f) => f.label || f.value)
    : [];
  return {
    stampId: raw.stamp_id || raw.stampId || null,
    stampType: raw.stamp_type || raw.stampType || null,
    category: raw.category || null,
    status: raw.status || 'completed',
    title: raw.title || null,
    summary: raw.summary || null,
    facts,
    source: raw.source || null,
    capabilityId: raw.capability_id || raw.capabilityId || null,
    decisionKey: raw.decision_key || raw.decisionKey || null,
    timestamp: raw.timestamp || null,
  };
}

function normalizeSteps(workflowRaw, isEn) {
  if (!workflowRaw) return [];
  const rawSteps = Array.isArray(workflowRaw.steps) ? workflowRaw.steps : [];
  const byType = new Map();
  for (const item of rawSteps) {
    if (!item || typeof item !== 'object') continue;
    const stepType = item.step_type || item.stepType || item.step;
    if (!stepType) continue;
    // Prefer non-superseded rows for compact progress.
    const prev = byType.get(stepType);
    if (!prev || item.status !== 'superseded') {
      byType.set(stepType, item);
    }
  }

  return WORKFLOW_STEP_ORDER.map((stepType) => {
    const item = byType.get(stepType) || {};
    const status = item.status || 'pending';
    return {
      stepType,
      label: workflowStepLabel(stepType, isEn),
      status,
      version: item.version,
      attempt: item.attempt,
      summary: item.summary || item.latest_summary || null,
      retryable: Boolean(item.retryable),
      requiresConfirmation: Boolean(
        item.requires_confirmation ?? item.requiresConfirmation,
      ),
      staleReason: item.stale_reason || item.staleReason || null,
    };
  });
}

function normalizeToolResult(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const stepType = raw.step_type || raw.stepType || raw.step || null;
  const status = raw.status || null;
  if (!stepType && !status) return null;
  return {
    stepType,
    status,
    summary: raw.summary || null,
    findings: Array.isArray(raw.findings) ? raw.findings : [],
    warnings: Array.isArray(raw.warnings) ? raw.warnings : [],
    metadata: raw.metadata && typeof raw.metadata === 'object' ? raw.metadata : {},
  };
}

const THAI_TEXT = /[ก-๙]/;

const humanizeOptionValue = (value) => String(value || '')
  .replaceAll('_', ' ')
  .replace(/\b\w/g, (letter) => letter.toUpperCase());

function englishOptionLabel(value, decisionKey, reasonCode) {
  const normalized = String(value || '').trim().toLowerCase();
  const labels = {
    approve: 'Continue',
    approved: decisionKey === 'mapping_confirmed' ? 'Confirm mapping' : 'Ready for analysis',
    reject: 'Cancel',
    rejected: 'Cancel',
    complete: 'Complete',
    partial: 'Not complete yet',
    unknown: 'Not sure yet',
    source_record: 'One source record',
    other: 'Other',
    keep_as_is: 'Keep the source value',
    exclude_negative: 'Exclude from analysis',
    return_or_adjustment: 'Return or adjustment',
    stock_out: 'Stock issue or deduction',
    error: 'Invalid data',
  };
  if (normalized === 'modify' || normalized === 'modified') {
    return reasonCode === 'AGGRESSIVE_CLEANING'
      ? 'Switch to Standard'
      : 'Need changes';
  }
  return labels[normalized] || humanizeOptionValue(value);
}

function localizeAwaitingQuestion(awaitingUser, isEn) {
  const question = String(awaitingUser?.question || '').trim();
  if (!isEn || !THAI_TEXT.test(question)) return question || null;

  const decisionKey = String(
    awaitingUser?.decision_key || awaitingUser?.decisionKey || '',
  );
  const reasonCode = String(
    awaitingUser?.reason_code || awaitingUser?.reasonCode || '',
  );
  if (reasonCode === 'AGGRESSIVE_CLEANING') {
    return 'Deep Clean may modify or remove more records than usual. Continue, switch to Standard, or cancel?';
  }
  if (reasonCode === 'AMBIGUOUS_MAPPING') {
    return 'Some column mappings are ambiguous. Confirm the current mapping, make changes, or cancel for now?';
  }

  const questions = {
    row_grain: 'What does one row represent in this dataset?',
    primary_metric: 'Which column should be the primary metric for this analysis?',
    metric_definition: 'How should the primary metric be calculated?',
    business_purpose: 'What is the main business goal for this analysis?',
    data_owner: 'Who owns this dataset for this analysis?',
    reporting_period_status: 'Is the reporting period complete for the analysis you want to run?',
    period_status: 'Is the reporting period complete for the analysis you want to run?',
    mapping_confirmed: 'Are the important column mappings ready to confirm?',
    business_context_reviewed: 'Is the confirmed business context ready to use for analysis?',
    cleaning_confirmation: 'This cleaning step needs your confirmation before it can continue.',
  };
  if (questions[decisionKey]) return questions[decisionKey];
  if (decisionKey.startsWith('mapping:')) {
    return `What does the “${decisionKey.slice('mapping:'.length)}” column represent?`;
  }
  return 'Please confirm the required information before the workflow continues.';
}

function normalizeOption(opt, isEn = false, decisionKey = '', reasonCode = '') {
  if (!opt || typeof opt !== 'object') return null;
  const value = opt.value ?? opt.id ?? null;
  const id = opt.id ?? opt.value ?? null;
  let label = opt.label ?? opt.text ?? (value != null ? String(value) : null);
  if (value == null || !label) return null;
  if (isEn && THAI_TEXT.test(String(label))) {
    label = englishOptionLabel(value, decisionKey, reasonCode);
  }
  return {
    id: id != null ? String(id) : String(value),
    value: String(value),
    label: String(label),
    decision: opt.decision || inferDecisionFromValue(String(value)),
    contextUpdates: opt.context_updates || opt.contextUpdates || undefined,
  };
}

export function inferDecisionFromValue(value) {
  const v = String(value || '').toLowerCase();
  if (['approved', 'approve', 'continue', 'yes', 'ใช่', 'ดำเนินการต่อ', 'confirm'].includes(v)) {
    return 'approved';
  }
  if (['rejected', 'reject', 'cancel', 'no', 'ไม่ใช่', 'ไม่ดำเนินการ'].includes(v)) {
    return 'rejected';
  }
  if (
    v.includes('standard')
    || v.includes('modify')
    || v.includes('เปลี่ยน')
    || v.includes('conservative')
    || v.includes('financial')
  ) {
    return 'modified';
  }
  // Contract collect options (column names, grain ids, etc.) are not engine decisions.
  return null;
}

/** Deterministic buttons when backend left a contract question without options. */
export function fallbackOptionsForDecision(decisionKey, isEn = false) {
  const key = String(decisionKey || '').trim();
  if (key === 'business_context_reviewed') {
    return [
      { id: 'approved', value: 'true', label: isEn ? 'Ready for analysis' : 'พร้อมแล้ว' },
      { id: 'modify', value: 'false', label: isEn ? 'Not ready yet' : 'ยังไม่พร้อม' },
    ];
  }
  if (key === 'mapping_confirmed') {
    return [
      { id: 'approved', value: 'true', label: isEn ? 'Confirm mapping' : 'ยืนยัน Mapping' },
      { id: 'modify', value: 'false', label: isEn ? 'Need changes' : 'ยังต้องปรับ' },
    ];
  }
  if (key === 'cleaning_confirmation' || key === 'confirmation') {
    return [
      { id: 'approve', value: 'approve', label: isEn ? 'Continue' : 'ดำเนินการต่อ', decision: 'approved' },
      { id: 'modify', value: 'modify', label: isEn ? 'Switch to Standard' : 'เปลี่ยนเป็น Standard', decision: 'modified' },
      { id: 'reject', value: 'reject', label: isEn ? 'Cancel' : 'ไม่ดำเนินการ', decision: 'rejected' },
    ];
  }
  return [];
}

export function classifyErrorKind(raw, toolResult, sessionStatus) {
  if (raw?.decision_type === 'ask_user' || raw?.awaiting_user) return 'awaiting_user';
  if (toolResult?.status === 'failed') return 'tool_failure';
  if (sessionStatus === 'failed') return 'tool_failure';
  if (raw?.audit?.error === 'orchestrator_llm_failed' || raw?.error_kind === 'orchestrator') {
    return 'orchestrator_failure';
  }
  return null;
}

/**
 * Build chat send payload extras for an option click.
 */
export function buildResolutionSendOptions(option, awaitingUser = null) {
  const label = option?.label || String(option?.value || option?.id || '');
  const rawValue = option?.value ?? option?.id ?? label;
  const decision = option?.decision || inferDecisionFromValue(rawValue);
  const contextUpdates = {
    ...(option?.contextUpdates || {}),
  };
  const reason = String(
    awaitingUser?.reasonCode || awaitingUser?.reason_code || '',
  );
  if (decision === 'modified' && !contextUpdates.cleaning_profile) {
    const profile = String(rawValue).toLowerCase();
    if (['standard', 'financial', 'conservative', 'aggressive'].includes(profile)) {
      contextUpdates.cleaning_profile = profile;
    } else if (
      profile === 'modify'
      || reason === 'AGGRESSIVE_CLEANING'
      || String(awaitingUser?.decisionKey || awaitingUser?.decision_key || '') === 'cleaning_confirmation'
    ) {
      contextUpdates.cleaning_profile = 'standard';
    }
  }
  const resolution = {
    value: rawValue,
    step_type: awaitingUser?.stepType || awaitingUser?.step_type || null,
    reason_code: awaitingUser?.reasonCode || awaitingUser?.reason_code || null,
    decision_key: awaitingUser?.decisionKey || awaitingUser?.decision_key || null,
    ...(Object.keys(contextUpdates).length ? { context_updates: contextUpdates } : {}),
  };
  if (decision) {
    resolution.decision = decision;
  }
  return {
    contentOverride: label,
    orchestrationResolution: resolution,
  };
}

/**
 * Build the same decision-aware chat payload for an answer typed directly in
 * the question card. The backend remains responsible for validating whether
 * the text resolves the active decision.
 */
export function buildFreeTextResolutionSendOptions(value, awaitingUser = null) {
  const answer = String(value || '').trim();
  return {
    contentOverride: answer,
    orchestrationResolution: {
      value: answer,
      step_type: awaitingUser?.stepType || awaitingUser?.step_type || null,
      reason_code: awaitingUser?.reasonCode || awaitingUser?.reason_code || null,
      decision_key: awaitingUser?.decisionKey || awaitingUser?.decision_key || null,
    },
  };
}

export function buildRetrySendOptions(stepType, isEn = false) {
  return {
    contentOverride: isEn ? 'Retry' : 'ลองใหม่',
    orchestrationResolution: {
      action: 'retry',
      step_type: stepType,
    },
  };
}

export function isConversationalSetupActive(orchestration, sessionStatus) {
  if (sessionStatus === 'ready') return false;
  if (!orchestration) return false;
  if (orchestration.readyForAnalysis) return false;
  return Boolean(orchestration.workflow || orchestration.awaitingUser || orchestration.toolResult);
}

export function compactProgressView(steps) {
  const list = Array.isArray(steps) ? steps : [];
  const activeIndex = list.findIndex((s) =>
    ['running', 'awaiting_user', 'ready', 'failed'].includes(s.status));
  const completed = list.filter((s) => s.status === 'completed').length;
  return {
    completed,
    total: list.length || WORKFLOW_STEP_ORDER.length,
    activeIndex: activeIndex >= 0 ? activeIndex : completed,
    active: activeIndex >= 0 ? list[activeIndex] : list[Math.min(completed, list.length - 1)] || null,
  };
}
