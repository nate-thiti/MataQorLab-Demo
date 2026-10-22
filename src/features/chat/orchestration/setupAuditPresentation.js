function sessionIdFor(orchestration) {
  return orchestration?.workflow?.session_id
    || orchestration?.workflow?.sessionId
    || orchestration?.workflow_plan?.session_id
    || orchestration?.session_id
    || orchestration?.sessionId
    || null;
}

function awaitingUserFor(orchestration) {
  return orchestration?.awaiting_user || orchestration?.awaitingUser || null;
}

function isReady(orchestration) {
  const workflow = orchestration?.workflow || orchestration?.workflow_plan || {};
  return Boolean(
    orchestration?.ready_for_analysis
    || orchestration?.readyForAnalysis
    || workflow?.ready_for_analysis
    || workflow?.readyForAnalysis
    || workflow?.status === 'ready'
    || orchestration?.session_status === 'ready',
  );
}

function stampKey(stamp, index) {
  return stamp?.stamp_id
    || stamp?.stampId
    || [stamp?.stamp_type, stamp?.stampType, stamp?.title, stamp?.summary, index].join('|');
}

function stampPayload(stamp) {
  return {
    stamp_id: stamp?.stamp_id || stamp?.stampId || null,
    stamp_type: stamp?.stamp_type || stamp?.stampType || null,
    status: stamp?.status || 'completed',
    title: stamp?.title || null,
    summary: stamp?.summary || null,
    facts: Array.isArray(stamp?.facts) ? stamp.facts : [],
    source: stamp?.source || null,
  };
}

/**
 * Build one compact audit presentation per attached-data setup session.
 * Workflow answers are inferred for legacy rows and read from metadata for new rows.
 */
export function buildSetupAuditPresentation(messages) {
  const list = Array.isArray(messages) ? messages : [];
  const groups = new Map();
  const explicitAnswerIndexes = new Set();
  let fallbackGroup = null;
  let fallbackSequence = 0;

  list.forEach((message, index) => {
    if (message?.role === 'user' && message.workflowResolution) {
      explicitAnswerIndexes.add(index);
    }
  });

  list.forEach((message, index) => {
    if (message?.role !== 'ai' || !message.orchestration) return;
    const orchestration = message.orchestration;
    let sessionId = sessionIdFor(orchestration);
    if (!sessionId) {
      if (!fallbackGroup) fallbackGroup = `legacy-setup-${fallbackSequence += 1}`;
      sessionId = fallbackGroup;
    }
    if (!groups.has(sessionId)) {
      groups.set(sessionId, {
        sessionId,
        assistantIndexes: [],
        answerIndexes: [],
        exchanges: [],
        stampMap: new Map(),
        ready: false,
        summaryIndex: null,
      });
    }
    const group = groups.get(sessionId);
    group.assistantIndexes.push(index);

    const rawStamps = orchestration.worklog_stamps || orchestration.worklogStamps || [];
    rawStamps.forEach((stamp, stampIndex) => {
      group.stampMap.set(stampKey(stamp, stampIndex), stampPayload(stamp));
    });

    const awaiting = awaitingUserFor(orchestration);
    const next = list[index + 1];
    if (awaiting?.question && next?.role === 'user') {
      const answer = String(next.content || '').trim();
      const decisionKey = awaiting.decision_key || awaiting.decisionKey
        || next.workflowResolution?.decision_key
        || next.workflowResolution?.decisionKey
        || null;
      group.answerIndexes.push(index + 1);
      group.exchanges.push({
        decisionKey,
        question: String(awaiting.question).trim(),
        answer,
      });
    }

    if (isReady(orchestration)) {
      group.ready = true;
      group.summaryIndex = index;
      fallbackGroup = null;
    }
  });

  const hiddenUserAnswerIndexes = new Set(explicitAnswerIndexes);
  const hiddenCompletedAssistantIndexes = new Set();
  const completedBySummaryIndex = new Map();

  for (const group of groups.values()) {
    group.answerIndexes.forEach((index) => hiddenUserAnswerIndexes.add(index));
    if (!group.ready || group.summaryIndex == null) continue;
    group.assistantIndexes.forEach((index) => {
      if (index !== group.summaryIndex) hiddenCompletedAssistantIndexes.add(index);
    });
    completedBySummaryIndex.set(group.summaryIndex, {
      sessionId: group.sessionId,
      exchanges: group.exchanges,
      stamps: [...group.stampMap.values()],
    });
  }

  return {
    groups: [...groups.values()],
    hiddenUserAnswerIndexes,
    hiddenCompletedAssistantIndexes,
    completedBySummaryIndex,
  };
}
